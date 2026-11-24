# BeanPostProcessor, Proxies, and When a Bean Reference Is Complete

## 1. Why can the same bean have two different Java objects?

When writing Spring Boot code, we often define a service and ask Spring to inject it into another component:

```java
@Service
public class OrderService {
    public String createOrder() {
        return "created";
    }
}
```

```java
@Component
public class OrderClient {
    private final OrderService orderService;

    public OrderClient(OrderService orderService) {
        this.orderService = orderService;
    }
}
```

Reading these two snippets, a beginner might assume the `orderService` variable definitely references **the exact object created by the `new OrderService()` constructor**. That is not always true. Spring may hold a **target** object to execute business logic while providing other components with a **proxy** object. The proxy intercepts external calls, performs additional processing such as transactions, caching, security, retries, or logging, and then delegates the call to the target.

This capability is typically wired into the bean lifecycle via infrastructure implementing the `BeanPostProcessor` interface. Therefore, it is important to distinguish:

- **Bean definition:** the metadata Spring uses to create and configure the bean.
- **Target instance:** the actual business instance that is created and initialized.
- **Bean reference from the container:** the final instance that `ApplicationContext.getBean(...)` or dependency injection may return, which in some cases is a **proxy** wrapping the target.
- **BeanPostProcessor:** an infrastructure component given the opportunity to inspect/modify/swap instances during bean creation. Not every processor creates a proxy.

This topic answers three questions: **Where does BeanPostProcessor intervene? When do proxies appear? When should you rely on a complete bean reference?**

## 2. Simplified lifecycle diagram of a singleton bean

Assume a regular Spring-managed bean without special circular dependency situations:

```text
OrderService BeanDefinition
              |
              v
       Create target instance
              |
              v
       Inject dependencies / populate properties
              |
              v
 Pre-initialization BeanPostProcessor
  postProcessBeforeInitialization(...)
              |
              |  @PostConstruct is processed by a
              |  dedicated BeanPostProcessor in this phase
              v
       afterPropertiesSet() / init-method
              |
              v
 Post-initialization BeanPostProcessor
  postProcessAfterInitialization(...)
              |
              |  A processor may return a PROXY
              v
     Bean exposed via BeanFactory
              |
              v
      getBean(...) / dependency injection
              |
        Reference may be a proxy
              |
     Call method via proxy -> advice -> target
```

The diagram above depicts the **conceptual boundaries** of a single bean creation. There is not just one `BeanPostProcessor` running before and one running after: the container can register **multiple processors**. In Spring, behaviors such as processing `@Autowired`, `@PostConstruct`, or creating AOP proxies also rely on processor infrastructure.

**Important detail about `@PostConstruct`:** detection and invocation of this annotation are handled by `CommonAnnotationBeanPostProcessor`/initialization infrastructure based on `BeanPostProcessor`, typically taking place during the *before initialization* loop. Therefore, you should not claim that **every** custom `postProcessBeforeInitialization` is guaranteed to run **before `@PostConstruct`**. Ordering among processors depends on registration and ordering rules. What is more certain in the standard case is that a processor's **after initialization** callback for a bean is called after that bean's initialization callbacks.

When multiple processors intervene, the `bean` value passed into a subsequent processor may already have been replaced by an earlier processor. Consequently, **even inside a `postProcessAfterInitialization` callback, you cannot automatically conclude you are seeing the final reference that all processors will return**.

## 3. What is BeanPostProcessor?

The core interface resides at:

```java
org.springframework.beans.factory.config.BeanPostProcessor
```

Two commonly used methods:

```java
Object postProcessBeforeInitialization(Object bean, String beanName);

Object postProcessAfterInitialization(Object bean, String beanName);
```

In modern Spring Framework, the interface provides default implementations; when defining your own processor, you can override one or both methods.

- `bean`: the **current instance**, which may be the target or a wrapper created earlier.
- `beanName`: the bean's name in the Spring container.
- Return value: the **reference that will continue through the processing chain**. Normally return `bean` itself if only observing; when justified, you may return a compatible proxy or replacement.
- `postProcessBeforeInitialization`: a callback in the phase before traditional initialization methods such as `InitializingBean.afterPropertiesSet()` or a custom init method.
- `postProcessAfterInitialization`: a callback in the post-initialization phase, where many proxies and wrappers are applied.

An example processor that merely logs callbacks:

```java
import org.springframework.beans.factory.config.BeanPostProcessor;

public class TraceProcessor implements BeanPostProcessor {

    @Override
    public Object postProcessBeforeInitialization(
            Object bean, String beanName) {
        if ("orderService".equals(beanName)) {
            System.out.println("BPP before: " + beanName);
        }
        return bean;
    }

    @Override
    public Object postProcessAfterInitialization(
            Object bean, String beanName) {
        if ("orderService".equals(beanName)) {
            System.out.println("BPP after: " + beanName);
        }
        return bean;
    }
}
```

This is a **valid Java class**, but it only takes effect when registered as a bean/infrastructure component in an `ApplicationContext`. Do not manually call `new TraceProcessor().postProcessAfterInitialization(...)` and assume Spring used it.

`BeanPostProcessor` operates on **container-managed bean instances**, not every Java object created with the `new` keyword. If you instantiate `new OrderService()` yourself outside Spring, the context's `BeanPostProcessor`s do not automatically run for that object.

## 4. Distinguishing BeanPostProcessor from BeanFactoryPostProcessor

The two names sound similar, yet their **levels of intervention differ**:

| Criterion | `BeanFactoryPostProcessor` | `BeanPostProcessor` |
|---|---|---|
| Primary input | Bean definitions / configuration metadata | Bean instance currently being created |
| Typical timing | Before regular application beans are instantiated | Around the initialization of each bean |
| Used for | Adjusting definition metadata/properties, configuring the registry | Adding object-level processing, validation, decoration, or proxying |
| Example methods | `postProcessBeanFactory(...)` | `postProcessBeforeInitialization(...)`, `postProcessAfterInitialization(...)` |
| Can replace bean reference with a proxy? | Not its typical responsibility | Yes, this is the standard mechanism |
| Should call business services? | No; easily triggers premature bean creation | Must also be careful; right in the middle of the bean lifecycle |

For needs involving **adding bean definitions**, some cases require `BeanDefinitionRegistryPostProcessor`, which operates at the registry level and runs earlier than application bean creation.

Do not work around proxy issues by calling `beanFactory.getBean(MyService.class)` inside a `BeanFactoryPostProcessor`: doing so can force the bean to be created **before all post-processors are ready**, producing behavior different from the standard lifecycle.

## 5. When is a proxy created?

In proxy-based Spring AOP, auto-proxy infrastructure selects beans requiring advice, creates an appropriate wrapper/proxy, and provides the proxy to external callers. This infrastructure typically implements extended `BeanPostProcessor` interfaces. On the common path, the proxy appears during `postProcessAfterInitialization(...)`.

Imagine a service calling a `pay()` method:

```text
Target bean: PaymentService
        |
    @PostConstruct
        |
     init done
        |
   Auto-proxy creator
        |
   +-------------------------+
   | PaymentService proxy    | <--- External callers receive bean reference
   |  logging / transaction  |
   +------------+------------+
                |
             target.pay()
                |
              result
```

Calling through the proxy lets Spring enforce additional conditions **before/after** entering the target. For example, a transaction-protected method can pass through the proxy to open/close a transaction, provided the application has properly configured transaction infrastructure and a transaction manager.

**Having `@Service` does not automatically mean a proxy exists.** When no advice, AOP mechanism, or other proxy requirement applies, the bean can be returned directly as the target. Nor can you assert that every proxy is created **exclusively** in the post-initialization callback: Spring has specialized infrastructure mechanisms to handle early references (see Section 11).

Specifically, `BeanPostProcessor` is a **broader concept than AOP**: some processors handle annotations, validate, or wrap objects without directly involving AOP.

## 6. Spring Boot 3.3.x + Java 17+ example: observing the target bean and proxy

The example has complete code and Gradle build setup. It shows `@PostConstruct` running on the target, a custom processor observing the initialization callbacks, and an `ApplicationRunner` receiving a bean that has passed through context post-processing.

The project uses `spring-boot-starter-aop` for AspectJ annotations and Spring AOP infrastructure. No HTTP server is needed, so it uses `spring-boot-starter` and `WebApplicationType.NONE`.

### 6.1. Directory structure

```text
bean-proxy-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/beanproxy/
    ├── BeanProxyApplication.java
    ├── GreetingService.java
    ├── GreetingAspect.java
    └── TraceBeanPostProcessor.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'bean-proxy-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

These versions are solely for this hands-on exercise; in a real repository, use the Gradle/Spring Boot/JDK versions managed by your project. To run the Wrapper commands below, the project needs `gradlew`/`gradlew.bat` and `gradle/wrapper`; generate the project via Spring Initializr or create the Wrapper with a compatible Gradle version if missing.

### 6.2. Service with @PostConstruct and internal self-call

**`src/main/java/com/example/beanproxy/GreetingService.java`:**

```java
package com.example.beanproxy;

import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    @PostConstruct
    public void initialize() {
        System.out.println("Service: @PostConstruct");
        System.out.println("Service: self call = " + greet("internal"));
    }

    public String greet(String person) {
        return "Hello " + person;
    }
}
```

`GreetingService` is a regular class without `final` on the class or on the `greet` method. We want Spring to create a subclass proxy, so overriding must be allowed. The `greet("internal")` call inside `initialize` directly uses the target's `this`; the example uses it to distinguish **self-invocation** from a call through the proxy.

### 6.3. Aspect tracing an external greet call

**`src/main/java/com/example/beanproxy/GreetingAspect.java`:**

```java
package com.example.beanproxy;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class GreetingAspect {

    @Around("execution(* com.example.beanproxy.GreetingService.greet(..))")
    public Object aroundGreeting(ProceedingJoinPoint joinPoint)
            throws Throwable {
        System.out.println("Advice: before greet");
        Object result = joinPoint.proceed();
        System.out.println("Advice: after greet");
        return result;
    }
}
```

`@Around` creates advice wrapping calls to the method matched by the pointcut. The example does not open a transaction or use a database; it simply prints two lines to prove whether a call goes through the proxy. `joinPoint.proceed()` actually forwards the call to the target; omitting it would alter or skip the method's execution.

### 6.4. BeanPostProcessor to observe callbacks

**`src/main/java/com/example/beanproxy/TraceBeanPostProcessor.java`:**

```java
package com.example.beanproxy;

import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.config.BeanPostProcessor;

public class TraceBeanPostProcessor implements BeanPostProcessor {

    private boolean interested(String beanName) {
        return "greetingService".equals(beanName);
    }

    @Override
    public Object postProcessBeforeInitialization(
            Object bean, String beanName) {
        if (interested(beanName)) {
            System.out.println("BPP: before initialization");
        }
        return bean;
    }

    @Override
    public Object postProcessAfterInitialization(
            Object bean, String beanName) {
        if (interested(beanName)) {
            System.out.println(
                    "BPP: after initialization; proxy at callback = "
                    + AopUtils.isAopProxy(bean));
        }
        return bean;
    }
}
```

This processor **does not create a proxy itself**; it only prints the state visible at the callback and returns `bean`. Because multiple post-processors can run in different orders, `AopUtils.isAopProxy(bean)` inside **this processor's own callback** may be `true` or `false`. Do not treat that value as the final verdict.

### 6.5. Startup class and runner checking the final reference

**`src/main/java/com/example/beanproxy/BeanProxyApplication.java`:**

```java
package com.example.beanproxy;

import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@SpringBootApplication
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class BeanProxyApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(BeanProxyApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context =
                application.run(args)) {
            // Close context after the runner has printed the evidence.
        }
    }

    @Bean
    public static BeanPostProcessor traceBeanPostProcessor() {
        return new TraceBeanPostProcessor();
    }

    @Bean
    ApplicationRunner verifyProxy(GreetingService service) {
        return args -> {
            System.out.println(
                    "Runner: AOP proxy = " + AopUtils.isAopProxy(service));
            System.out.println(
                    "Runner: CGLIB proxy = " + AopUtils.isCglibProxy(service));

            String result = service.greet("Lan");
            System.out.println("Runner: result = " + result);
        };
    }
}
```

Key choices in the code:

- `@EnableAspectJAutoProxy(proxyTargetClass = true)` selects subclass-based proxying so the example can inject `GreetingService` by its **concrete class**. Spring Boot has auto-configuration for AOP, but this exercise states the choice explicitly to avoid depending on project defaults.
- `@Bean public static BeanPostProcessor ...` makes the return type `BeanPostProcessor` explicit and uses **static** so Spring creates the processor early without forcing instantiation of the configuration class before necessary.
- `ApplicationRunner` is invoked **after context refresh succeeds**; in this non-circular scenario, it receives the reference provided by the container once the bean has passed through the post-processing chain.
- `AopUtils.isAopProxy(service)` confirms AOP proxying, while `AopUtils.isCglibProxy(service)` confirms the proxy type in this exercise.
- `try-with-resources` is only to close the context after the non-web demo finishes; a real web application should not close its context right after startup.

### 6.6. Run and observe

If you have the Gradle Wrapper, from the project directory:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

In the program output, the key lines have the following content:

```text
Service: @PostConstruct
Service: self call = Hello internal
BPP: after initialization; proxy at callback = <true-or-false>
Runner: AOP proxy = true
Runner: CGLIB proxy = true
Advice: before greet
Advice: after greet
Runner: result = Hello Lan
```

This is an **illustrative log excerpt**, not the full stdout. `BPP: before initialization` will also be printed, but its **position relative to `Service: @PostConstruct` is not a fixed contract**, because `@PostConstruct` itself is processed in another BeanPostProcessor during the before phase. Spring Boot/Gradle logs may interleave between lines.

The relationships to verify are:

1. `GreetingService`'s `@PostConstruct` completes before the corresponding after-initialization callback runs.
2. `Runner: AOP proxy = true` and `Runner: CGLIB proxy = true` when the aspect is registered successfully, because the runner receives the container-processed reference.
3. Calling `greet("internal")` **inside the target itself** does not print the two `Advice` lines.
4. Calling `service.greet("Lan")` **from the runner through the proxy** prints `Advice: before greet` then `Advice: after greet`, then returns `Hello Lan`.

Do not use the position of the single `BPP: before initialization` line to assert an absolute order across all `@PostConstruct` methods in every project. That is precisely the hazard of mistaking a callback name for global state.

## 7. Why is @PostConstruct not the time of a complete bean reference?

In the example, `@PostConstruct` runs while the target bean is being initialized. With regular AOP proxying, the wrapper handed to external callers appears **after** the target's initialization callbacks. Therefore:

```text
Creating GreetingService (target)
        |
        v
@PostConstruct called on target
        |      |
        |      +--> this.greet(...)   (direct call)
        |
        v
Post-initialization BeanPostProcessor
        |
        v
May create wrapper/proxy
        |
        v
Caller retrieves GreetingService from context
        |
        +--> proxy.greet(...)         (advised)
```

**You should not** call an `@Transactional`, `@Async`, or `@Cacheable` method from `@PostConstruct` on the same bean and blindly expect advice to apply. In proxy-based AOP, `this.method()` bypasses the proxy. Moreover, these annotations only work if the application has the corresponding infrastructure enabled: `@EnableAsync` for proxy-based async execution, caching enabled with a cache manager, or transaction management configured with a transaction manager.

When you need to run advice-dependent business logic **after the bean is exposed**, a clean approach is to move that work into **another bean** that receives the dependency via constructor injection, and then call the service method from an `ApplicationRunner` or another appropriate entry point. There is no need to use `AopContext.currentProxy()` in business code just to dodge lifecycle rules.

### Illustrative example: separating the call into another bean

```java
@Service
public class PaymentService {
    @Transactional
    public void pay() {
        // Logic requiring a transaction (in a project with transaction configured).
    }
}

@Component
public class StartupPayment {
    private final PaymentService paymentService;

    public StartupPayment(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void afterReady() {
        paymentService.pay(); // Call goes through the container-injected reference.
    }
}
```

This is an **integration snippet**, not a complete project: it requires Spring and transaction API imports, a configured `PlatformTransactionManager`, and matching dependencies. The example shows how a **bean boundary** allows the call to pass through the proxy. `ApplicationReadyEvent` is appropriate if the work happens after runners complete; if it must finish **before Ready**, use an `ApplicationRunner` instead of this listener.

## 8. Two common proxy types: JDK and CGLIB

In proxy-based Spring AOP, the choice depends on configuration and target capabilities:

| Characteristic | JDK dynamic proxy | CGLIB/class-based proxy |
|---|---|---|
| Mechanism | Proxy implements interfaces | Proxy is a runtime subclass of the target |
| Can be injected by interface? | Yes | Yes, if target implements the interface |
| Can be injected directly by concrete class? | Usually no: JDK proxy is not a subclass of the target class | Usually yes, if the class can be proxied |
| Notable limitations | Only methods exposed through the proxied interface | Cannot subclass `final` classes; cannot override `final`/`private` methods |
| Runtime check | `AopUtils.isJdkDynamicProxy(bean)` | `AopUtils.isCglibProxy(bean)` |

Having an interface **does not guarantee** a JDK proxy in Spring Boot: Spring Boot settings can select class-based proxies by default configuration or via `@EnableAspectJAutoProxy(proxyTargetClass = true)`. If you need to know for sure, check the **runtime reference** instead of guessing from `getClass().getSimpleName()`.

In Section 6's example, `proxyTargetClass = true` intentionally selects a class-based proxy, and `GreetingService` is non-`final`. That is why the runner can declare parameter type `GreetingService` and verify `isCglibProxy(...)`.

### Avoid comparing proxy class to target class with ==

```java
System.out.println(service.getClass() == GreetingService.class);
```

With a class-based proxy, this expression can be `false` because the runtime class is a generated subclass. That **does not mean the bean is the wrong type**. You can check:

```java
System.out.println(AopUtils.isAopProxy(service));
System.out.println(AopUtils.getTargetClass(service));
```

`getTargetClass` reports the target class identified by AOP infrastructure when applicable; `service.getClass()` is the class of the current reference (which may be a proxy). Do not assume every bean has a proxy or that every proxy is a Spring AOP proxy; choose checking APIs accordingly.

## 9. Internal calls: why does self-invocation bypass the proxy?

Suppose inside the same bean:

```java
public void outer() {
    inner();
}

@Transactional
public void inner() {
    // Business logic
}
```

If an external caller invokes `proxy.outer()`, AOP can apply advice to `outer` if a matching rule exists. Inside the target, however, calling `inner()` is equivalent to `this.inner()`; it is invoked **directly on the target**, bypassing going back through the proxy. Consequently, transaction advice placed only on `inner` typically **does not** run on this self-invocation.

Distinction:

```text
Called from another bean:
Client -> Proxy -> Advice(inner) -> Target.inner()      [goes through proxy]

Called within the same target:
Client -> Proxy -> Target.outer() -> this.inner()        [bypasses advice(inner)]
```

The clean design fix is to **extract the advised method into another bean**, so the caller genuinely receives a container reference and calls through the proxy. Workarounds like self-injection or `AopContext.currentProxy()` exist, but they complicate lifecycle dependencies and Spring AOP coupling and should not be the default choice.

Also distinguish **proxy-based Spring AOP** from **direct bytecode AspectJ weaving**: weaving does not share the same self-invocation limitation. This topic covers standard proxy lifecycles in Spring Boot and does not assume the application uses bytecode weaving.

## 10. When are BeanPostProcessors registered and which beans do they apply to?

In a standard `ApplicationContext`, Spring **detects, creates, and registers BeanPostProcessors early enough** before creating regular application beans. Only beans created **after the appropriate processors have been registered** have the chance to pass through the full chain.

Therefore, some infrastructure beans initialized early may **not be eligible** to receive full post-processing or AOP auto-proxying. You may encounter a log message:

```text
Bean 'someBean' of type [...] is not eligible for getting processed
by all BeanPostProcessors (for example: not eligible for auto-proxying)
```

This message does not necessarily mean every bean in the context is broken. It reports that a bean was created too early to be processed by all processors. Identify which bean it is, why it was created early, and whether it genuinely needs proxying.

### Rules for declaring a custom processor

In a `@Configuration` class, write:

```java
@Bean
public static BeanPostProcessor myProcessor() {
    return new MyProcessor();
}
```

Here `MyProcessor` must be a real implementation of `BeanPostProcessor`. Declaring it **`static`** allows Spring to create the processor without necessarily instantiating the configuration class before the right time. At the same time, the method return type should clearly expose `BeanPostProcessor` (the implementation class itself or the interface).

Do not declare a processor with an overly generic return type like `Object` and expect the container to always detect it at the right time. Also avoid injecting too many business beans into a processor's constructor, because that can **trigger premature creation of other beans**, making them ineligible for AOP.

### Processor ordering

When multiple processors participate, you can use `Ordered`, `PriorityOrdered`, or appropriate Spring-supported ordering mechanisms. However:

- Exact ordering depends on how the processor was registered (auto-detected vs. programmatic).
- Processors registered programmatically via `BeanFactory.addBeanPostProcessor(...)` follow different ordering rules than auto-detected bean processors.
- The order of **before** callbacks does not necessarily mirror the order of another business operation in a simple way.
- Changing processor order can change when wrappers/proxies are seen by other processors.

When verifying behavior, observe **the reference returned by the container after the bean has finished initializing**, rather than relying solely on an intermediate log from a custom processor.

## 11. Early references and dependency cycles

When certain singleton beans have a circular dependency, Spring has an internal mechanism that can expose an **early reference** to a bean currently being created. Specialized implementations of `SmartInstantiationAwareBeanPostProcessor` can participate via `getEarlyBeanReference(...)` to help maintain consistency between the early reference and the final proxy.

This is an **important infrastructure exception** to the simple “proxies only appear after init” diagram. You should not deduce from this exception that every bean, every proxy type, or every circular dependency is safely supported by Spring.

Spring Boot 3.3 by default **disallows circular bean references** (`spring.main.allow-circular-references=false`). For instance, a constructor-injection cycle will normally fail rather than producing an early reference to use:

```text
ServiceA constructor needs ServiceB
ServiceB constructor needs ServiceA
              |
         Circular dependency
              |
    Cannot construct both objects
```

Do not enable `spring.main.allow-circular-references=true` just to bypass flawed dependency design. The proper fix is to refactor responsibilities or extract shared collaboration so the dependency path is clear and acyclic.

If you are inspecting early-reference behavior while investigating an existing bug, distinguish:

- **Raw target:** the instance before initialization steps complete.
- **Early reference:** the object provided before bean creation finishes, possibly wrapped depending on processors.
- **Final exposed reference:** the container's reference after the initialization/post-processing chain completes.

Do not store raw targets from intermediate callbacks in a global registry and hand them to callers, as you could cause two callers to observe different objects for the same bean.

## 12. Inspecting the complete bean at the right time

For a typical application, when verifying that a service has been created and its proxy is active, clearer observation points include:

- **A client bean's constructor**: it receives dependencies resolved by the container; for non-circular dependencies, the injected reference has normally been processed, though **the constructor of the bean currently initializing** does not mean the whole system is ready.
- **ApplicationRunner/CommandLineRunner**: invoked after the context is refreshed, suited for calling services and verifying behavior before Ready.
- **ApplicationStartedEvent**: after refresh, before runners; suited for observing post-refresh context availability without tying into a single bean's initialization.
- **ApplicationReadyEvent**: after runners; suited for observing/reporting that the application finished its startup sequence, not for modifying already-processed bean definitions.
- **ApplicationContext.getBean(...)**: retrieves the Spring-managed reference once the context is running; if the bean has an AOP proxy, this is normally the exposed proxy.

Crucially, **“bean complete” and “entire application ready” are not the same milestone**. An individual bean can finish initializing very early while the application still has to initialize other beans, start the server, and finish runners. Conversely, a `@Lazy` bean may not exist yet even when the application is Ready; when requested, it goes through its initialization lifecycle then.

Do not use `Thread.sleep(...)` inside `@PostConstruct` to “wait for the proxy to appear”. It does not make `this.method()` calls pass through a proxy, slows down startup, and masks ordering problems.

## 13. Distinguishing @Transactional, @Async, and @Cacheable proxies

Proxy-based features share the same **call-path** rules, while their required enabling infrastructure differs:

| Case | Required infrastructure | Why it is commonly misunderstood |
|---|---|---|
| `@Transactional` | Transaction management and an appropriate transaction manager | Calling an `@Transactional` method on the same target bypasses the transaction proxy. |
| `@Async` | Async processing enabled, e.g., `@EnableAsync`, with an appropriate executor | Self-invocation may run synchronously because it bypasses advice. |
| `@Cacheable` | `@EnableCaching` and an appropriate cache manager | Self-invocation may fail to hit the cache because it bypasses the proxy. |
| `@Aspect` and `@Around` | Spring AOP/AspectJ annotations infrastructure as in the example | Calls through the proxy are advised; direct calls on the target do not get the same handling. |

Putting an annotation on a method is **not enough** to guarantee a proxy. If dependencies/infrastructure are missing, conditions are unmet, or the method cannot be intercepted, the effect may not happen. With class-based proxies, `final` classes and `final/private` methods are key limitations.

For instance, `@Transactional` does not create a database or transaction manager by itself. To prove a real transaction is open, you must use a project with valid transaction management configured and inspect transaction/rollback state, not merely see the annotation.

## 14. Common diagnostic errors

| Symptom | Possible cause | How to check and fix |
|---|---|---|
| BPP sees `proxy=false` but runner sees `proxy=true` | An auto-proxy creator ran after the custom BPP in the after-init chain | Inspect the reference in a runner/context after the entire processor chain completes. |
| `@PostConstruct` calls `@Transactional` method without transaction | Self-invocation on target occurred before callers had the proxy | Move the call to another bean via injected dependency and pick an appropriate post-init hook. |
| Calling `new Service()` breaks `@Autowired`/AOP | Object is not managed by Spring | Let the container create the bean, inject dependencies via constructor, or use `getBean` from context when appropriate. |
| `ClassCastException` casting proxy to concrete class | JDK proxy implements only interfaces, not a subclass of the target | Inject by interface or configure class-based proxying if the design requires it. |
| `final` class/method is not advised under CGLIB | Subclass proxy cannot override | Adjust design to allow proxying, prefer appropriate public methods, or use another mechanism if truly required. |
| No advice seen when calling from the same bean | `this.method()` bypasses the proxy | Extract the call to a collaborating bean; do not use self-calls to test proxies. |
| Log shows “not eligible for getting processed by all BeanPostProcessors” | Bean initialized too early due to processor/infrastructure | Reduce early dependencies; use `@Bean static` for processors; inspect the bean named in the log. |
| BPP causes circular dependency when injecting a service | Processor initialized before the service and inadvertently forces early creation | Keep processors lightweight and avoid direct dependencies on business beans. |
| BPP replaces instance by returning `null` | Violates processing chain intent; `null` has special meaning and can stop the chain | When only observing, always return `bean`; when wrapping, return the valid compatible replacement. |
| Trying to edit bean definitions inside a BPP | BPP operates on instances, likely too late to edit creation metadata | Use `BeanFactoryPostProcessor`/registry post-processors before instantiation. |
| Relying on order of all before-init/@PostConstruct logs | `@PostConstruct` is also driven by a processor in the before phase | Do not assume inter-processor order unless explicitly configured and verified. |
| Calling a service from a very early bootstrap listener | Context/bean may not exist yet | Choose a runner or post-refresh event when complete dependencies are needed. |

### Evidence-based investigation workflow

1. Identify **which bean** and **which method** need advice; verify the exact annotation/pointcut and corresponding infrastructure.
2. Identify **where the reference is called from**: another bean, `this`, `new`, or `ApplicationContext.getBean`.
3. At an appropriately late milestone, inspect `AopUtils.isAopProxy(reference)`, `isJdkDynamicProxy`/`isCglibProxy`, and the target class; do not conclude from the class name alone.
4. Check early bean initialization logs and `BeanPostProcessor` registration style; find out why if a bean needing proxying was excluded from processing.
5. Check whether the method is interceptable: visibility, `final`, interface/proxy type, pointcut, and feature conditions.
6. Make a call **from another bean** to that method and observe advice behavior; do not use a call from `@PostConstruct` on the same target as sole evidence.

## 15. Verifiable hands-on exercises

Use the `bean-proxy-demo` project from Section 6. Make one change at a time, returning to the baseline state when finished:

**Experiment A — before and after objects:** run the baseline and observe that `BPP: after initialization; proxy at callback = ...` can vary by BPP order, while `Runner: AOP proxy = true` holds with the example configuration. Explain why **an intermediate checkpoint** is not the final reference.

**Experiment B — self-invocation:** keep `GreetingService.initialize()` calling `greet("internal")`. No `Advice` log appears for that call. Compare with `service.greet("Lan")` in the runner, where advice logs appear.

**Experiment C — no advice:** temporarily remove `@Component` from `GreetingAspect` or remove the aspect bean from the project and rerun. `GreetingService` is still a Spring bean, but may no longer have an AOP proxy because no advice applies. Check `AopUtils.isAopProxy` directly.

**Experiment D — class proxy:** add `final` to `GreetingService` (then revert it) and try running while subclass proxying is still requested. Observe the error or inability to proxy under that configuration to understand why CGLIB is limited with `final` classes.

**Experiment E — processor returning the bean:** keep `return bean` in both callbacks of `TraceBeanPostProcessor`. Change the log to print only `beanName` or the current class; do not swap the instance when only measuring. Try observing another bean by adjusting the `interested` condition and explain why a processor can run on many beans in the context.

**Experiment F — callback timing:** add logs from `@PostConstruct`, BPP, and `ApplicationRunner`. Mark the relationships that are **guaranteed** (after-init before runner) and those that **depend on BPP order** (custom before-init vs. `@PostConstruct`). Do not turn a single run's log order into a contract for every application.

Self-assessment questions: **(1)** Why is `@PostConstruct` on the target not proof that a complete proxy has been received? **(2)** Why does `BeanFactoryPostProcessor` differ from `BeanPostProcessor`? **(3)** Why can a Spring-injected service be a proxy even though the code declares only one `@Service` class? **(4)** Why does `this.method()` bypass advice? **(5)** When is `ApplicationRunner` appropriate for verifying a proxy? Being able to answer these five questions shows you grasp the relationship between bean initialization, post-processing, and the reference used by callers.

## Official documentation

- Spring Framework 6.1, Container Extension Points (`BeanPostProcessor` / `BeanFactoryPostProcessor`): https://docs.spring.io/spring-framework/reference/6.1/core/beans/factory-extension.html
- Spring Framework 6.1, `BeanPostProcessor` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/config/BeanPostProcessor.html
- Spring Framework, `@PostConstruct` / `@PreDestroy`: https://docs.spring.io/spring-framework/reference/6.1/core/beans/annotation-config/postconstruct-and-predestroy-annotations.html
- Spring Framework 6.1, Spring AOP Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/6.1/core/aop/proxying.html
- Spring Boot 3.3, Spring Application Events and Runners: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html

**Key takeaway:** `BeanPostProcessor` is an extension point operating on **instances** that can create a proxy or return a different reference after initialization. `@PostConstruct` runs during the target's initialization and **does not guarantee internal calls go through a proxy**. When observing a bean exposed by Spring, use the reference provided by context/constructor injection at an appropriate stage and verify actual advice behavior, while keeping in mind exceptions for early-created beans and circular dependencies.
# Calls During Initialization and Limitations of @PostConstruct in Spring AOP

## 1. Practical Problem: Same Method, Yet Advice Only Runs After the Bean Is Ready

In Spring AOP using auto-proxying, a Spring bean method may **fail to trigger advice when called from a constructor or an `@PostConstruct` initialization callback**, even though afterward the same method is advised when called through the bean retrieved from `ApplicationContext`.

Two separate conditions must be distinguished:

1. **Lifecycle:** at the time of the call, has Spring already created and published the complete proxy of the target bean?
2. **Call path:** is the code calling **the target instance itself (`this`)** or a **Spring proxy reference**?

Simply adding `@Aspect`, writing a valid pointcut, and enabling `@EnableAspectJAutoProxy` does not guarantee that every call during initialization is intercepted. This situation relates directly to **Spring's BeanPostProcessor and auto-proxy ordering**.

In this lesson, `@PostConstruct` always refers to `jakarta.annotation.PostConstruct` from Spring Framework 6.x / Spring Boot 3.x and later. If studying an older Spring 5 / Boot 2 project, you will commonly see `javax.annotation.PostConstruct`; do not swap packages arbitrarily across generations.

## 2. Lifecycle Order Related to Auto-Proxying

For a normal singleton bean in Spring Framework using `@EnableAspectJAutoProxy`, the high-level diagram is:

```text
Spring ApplicationContext
        |
        v
Register BeanDefinitions and BeanPostProcessors, including AOP auto-proxy creator
        |
        v
Create target instance (constructor / factory method)
        |
        v
Dependency injection and Aware callbacks
        |
        v
BeanPostProcessor.postProcessBeforeInitialization(...)
  └─ processes @PostConstruct (when the corresponding processor is present)
        |
        v
Other init callbacks (InitializingBean, @Bean(initMethod), ...)
        |
        v
BeanPostProcessor.postProcessAfterInitialization(...)
  └─ AOP auto-proxy creator can wrap target with a proxy
        |
        v
Expose finished bean/proxy in container for clients to use
        |
        v
Call through proxy -> advisor/pointcut -> advice -> target method
```

The diagram intentionally shows **the normal path**, not a claim that every bean goes through one exception-free process. Spring supports early bean creation hooks, `FactoryBean`, circular dependency handling, and special proxy types; those cases can alter when a proxy is created. However, **you must not rely on lifecycle exceptions to guarantee AOP on initialization callbacks**.

Key facts in Spring:

- `CommonAnnotationBeanPostProcessor` (inheriting lifecycle annotation processing) executes `@PostConstruct` **before** the bean finishes initialization.
- `BeanPostProcessor#postProcessAfterInitialization` is the normal point where the AOP auto-proxy creator can return **a proxy in place of the original target**.
- According to Spring Framework documentation on initialization callbacks, initialization callbacks are invoked on the **raw bean**, so AOP interceptors normally **do not apply** to the init method invocation.
- After the bean finishes, **callers using the proxy reference** trigger advice for methods selected by pointcuts.
- `@PostConstruct` is meant to establish the bean's internal invariants/structures; Spring 6.2 notes that the callback runs under a singleton creation lock and **is unsuitable for triggering heavy work, accessing many other beans, or starting complex background threads**.

### 2.1. Relative Order of Init Callbacks

For a bean with multiple callbacks on different methods, Spring describes the typical order:

1. Method annotated with `@PostConstruct`.
2. `InitializingBean.afterPropertiesSet()`, if the bean implements the interface.
3. Custom initialization method, such as `@Bean(initMethod = "init")`.

These steps belong to **target initialization**, not a consumer's public business method call through a proxy. Therefore, the callback being invoked once by Spring does not mean it counts as an AOP-advised method invocation.

If an init method fails and throws an exception, bean/context creation can fail. `@AfterThrowing` advice on business methods does not automatically catch or convert initialization errors: they only observe method calls going through the proxy within scope.

## 3. Distinguishing Four Commonly Conflated Cases

| Case | Object / call path in Spring | Spring AOP proxy advice |
| --- | --- | --- |
| Bean's constructor calls `this.process()` | Runs directly on the object being constructed; no complete bean proxy exists for callers yet | **Cannot** intercept that internal call via Spring AOP. |
| `@PostConstruct` of **the target itself** calls `this.process()` | Callback runs on the raw target; `process()` is self-invocation | **Cannot** intercept the `process()` call through a proxy. |
| Spring calls **the `@PostConstruct` method itself** on the target | Lifecycle callback invoked by a post-processor during initialization | **Should not expect** advice to apply to that callback in the normal lifecycle. |
| `@PostConstruct` of **bean A** calls `targetProxy.process()` on bean B, which is already initialized and injected | Invocation goes through **bean B's proxy** | **Possible**, if B is already proxied, the pointcut matches, and the method is interceptable. |
| `main`/service/controller after context refresh calls `targetProxy.process()` | Call into the proxy of the Spring-managed target | **Yes**, if an advisor matches and the proxy can intercept the method. |

The fourth row is an easy point of misunderstanding: **not all code inside `@PostConstruct` bypasses AOP**. If bean A is injected with bean B that has already finished initialization and B has a proxy, the call **A → proxy B** can still go through advice. Even so, do not use this as an excuse to run a heavy workflow right inside A's `@PostConstruct`: remaining beans may not be initialized yet and deadlock/lifecycle risks remain.

### 3.1. Self-Invocation and Lifecycle Are Two Different Limits

Even when the target **is already fully proxied by Spring**, an internal call `this.process()` from another method on the same target can still bypass the proxy. Therefore avoid inferring that "after context refresh, every self-call is advised".

```java
// Illustrative: code inside an already-proxied Spring service
public void outer() {
    this.inner();  // does not go back through the Spring proxy
}

public void inner() {
    // only advised when called through the proxy at an appropriate boundary
}
```

This is an illustrative snippet, not a complete Java class. Changing `proxyTargetClass=true` or using CGLIB **does not fix** self-invocation in the normal Spring AOP proxy model. `private` and `final` methods do not become interceptable simply by changing the proxy type either.

## 4. Standalone Demo: Observing Constructor, @PostConstruct, Cross-Bean Calls, and Post-Refresh

The example uses:

- **Java 17+**, **Spring Framework 6.2.19**, and **AspectJ Weaver 1.9.25.1**.
- `jakarta.annotation-api:2.1.1` to declare `@PostConstruct` explicitly.
- Plain Spring Framework Java configuration so auto-proxying is visibly enabled with `@EnableAspectJAutoProxy`.
- Two beans `WorkService` (target) and `StartupCaller` (consumer), and one `TraceAspect` with a pointcut explicitly restricted to public methods of `WorkService`.

The example **does not use Spring Boot** to avoid depending on Boot AOP auto-configuration when explaining the lifecycle. Dependency/framework versions should be aligned to a real project.

### 4.1. Directory Structure and Gradle

```text
spring-aop-init-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/initdemo/
    ├── Main.java
    ├── AppConfig.java
    ├── WorkService.java
    ├── StartupCaller.java
    └── TraceAspect.java
```

**`settings.gradle`**

```gradle
rootProject.name = 'spring-aop-init-demo'
```

**`build.gradle`**

```gradle
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
    implementation 'org.springframework:spring-aop:6.2.19'
    implementation 'org.aspectj:aspectjweaver:1.9.25.1'
    implementation 'jakarta.annotation:jakarta.annotation-api:2.1.1'
}

application {
    mainClass = 'com.example.initdemo.Main'
}
```

Spring Context brings the annotation configuration infrastructure; `@EnableAspectJAutoProxy` activates the Spring AOP auto-proxy creator. In `AnnotationConfigApplicationContext`, standard annotation processors are registered for the `@PostConstruct` lifecycle. No `-javaagent` JVM agent is needed: the lesson uses **Spring proxy-based AOP**, not AspectJ load-time weaving.

### 4.2. Target Bean: Intentionally Creating Three Kinds of Calls

**`WorkService.java`**

```java
package com.example.initdemo;

import jakarta.annotation.PostConstruct;

public class WorkService {
    public WorkService() {
        System.out.println("constructor:begin");
        process("from-constructor");
        System.out.println("constructor:end");
    }

    @PostConstruct
    public void initialize() {
        System.out.println("postConstruct:begin");
        process("from-postConstruct");
        System.out.println("postConstruct:end");
    }

    public String process(String source) {
        System.out.println("target:" + source);
        return "done:" + source;
    }
}
```

In the constructor and `initialize()`, `process()` is called directly on **the object itself**, not through the Spring proxy. Even though `initialize()` is public and can match the `execution(...)` expression by signature, **Spring invokes it as a target lifecycle callback**, not as a client calling through the AOP proxy. Do not call `initialize()` directly as a business method just to capture advice.

### 4.3. Aspect Intercepting Public Methods on WorkService

**`TraceAspect.java`**

```java
package com.example.initdemo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TraceAspect {
    @Before("execution(public * com.example.initdemo.WorkService.*(..))")
    public void beforeWork(JoinPoint point) {
        System.out.println("advice:" + point.getSignature().getName());
    }
}
```

The pointcut applies to selected public methods of `WorkService`. In the demo, both `process()` and `initialize()` belong to this class per the expression. There is no need to use `@Component` because `TraceAspect` is registered via `@Bean` in the configuration below.

**What to observe:** `@PostConstruct` being invoked by the container **does not** automatically produce `advice:initialize`. When `process()` is called **through the proxy from another bean or from `main`**, the advice prints `advice:process`.

### 4.4. Caller Bean With Its Own @PostConstruct

**`StartupCaller.java`**

```java
package com.example.initdemo;

import jakarta.annotation.PostConstruct;

public class StartupCaller {
    private final WorkService workService;

    public StartupCaller(WorkService workService) {
        this.workService = workService;
    }

    @PostConstruct
    public void initializeCaller() {
        System.out.println("callerPostConstruct:begin");
        workService.process("from-other-bean");
        System.out.println("callerPostConstruct:end");
    }
}
```

Here `workService` is a **Spring-injected** dependency, not `new WorkService()`. Because the dependency must be created and initialized before `StartupCaller` can call it, `StartupCaller.initializeCaller()` receives the `WorkService` bean after the normal completion step and can call **through the proxy**.

**Do not turn this into a production rule:** the demo intentionally uses a lightweight cross-bean call to prove the difference. In a real application, `@PostConstruct` is not the place to start requests, long transactions, remote service calls, or heavy task scheduling when the entire context may not be ready yet.

### 4.5. Spring Configuration Creating Beans Explicitly

**`AppConfig.java`**

```java
package com.example.initdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    TraceAspect traceAspect() {
        return new TraceAspect();
    }

    @Bean
    WorkService workService() {
        return new WorkService();
    }

    @Bean
    StartupCaller startupCaller(WorkService workService) {
        return new StartupCaller(workService);
    }
}
```

Spring creates `WorkService`, runs constructor/`@PostConstruct` on the target, and then can put an AOP proxy in place before injecting into `StartupCaller`. The `WorkService` class has no interface, and the configuration requests a class-based proxy to retrieve the bean by concrete type. Both target and aspect are managed by the container via `@Bean` methods; `@ComponentScan` is not needed.

### 4.6. Calling Through the Bean After Context Refresh

**`Main.java`**

```java
package com.example.initdemo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            WorkService workService = context.getBean(WorkService.class);
            System.out.println("isProxy=" + AopUtils.isAopProxy(workService));
            System.out.println(
                "mainResult=" + workService.process("after-refresh")
            );
        }
    }
}
```

### 4.7. Running and Comparing stdout

In the project directory, with Java 17+ and Gradle installed:

```bash
gradle run --quiet
```

If the project has a Gradle Wrapper, use `./gradlew run --quiet` (Linux/macOS) or `gradlew.bat run --quiet` (Windows).

Lines printed by the application code, in order, for the project and configuration above:

```text
constructor:begin
target:from-constructor
constructor:end
postConstruct:begin
target:from-postConstruct
postConstruct:end
callerPostConstruct:begin
advice:process
target:from-other-bean
callerPostConstruct:end
isProxy=true
advice:process
target:after-refresh
mainResult=done:after-refresh
```

This stdout includes only the `System.out.println` statements described; JVM or build-tool startup messages/warnings may appear outside these lines.

**Evidence analysis:**

1. After `constructor:begin` comes `target:from-constructor`, **with no `advice:process`**. This is a call from the object under construction.
2. After `postConstruct:begin` comes `target:from-postConstruct`, **with no `advice:initialize` or `advice:process`**. The callback runs on the raw target; the `process` call inside the callback is self-invocation.
3. After `callerPostConstruct:begin`, `advice:process` **does** appear before `target:from-other-bean`. `StartupCaller` was injected with `WorkService`'s proxy reference. This refutes the overly broad conclusion that no method called inside any `@PostConstruct` can use AOP.
4. `isProxy=true` confirms `WorkService` after context refresh is a Spring AOP proxy.
5. Calling `workService.process("after-refresh")` from `Main` also prints `advice:process` because it goes through the finalized proxy.

There is no `advice:initialize` line because the target's `@PostConstruct` callback is invoked directly during the lifecycle. If a developer manually calls `workService.initialize()` after refresh, that is a **different call** that may be advised because it goes through the proxy; however, it **re-initializes** the target against its contract. Do not use this trick to "verify" the initial callback.

## 5. Why Is @PostConstruct Not the Place to Start Workflows That Need Advice?

`@PostConstruct` fits local steps: validating injected configuration, setting up internal data structures, verifying simple invariants. It **is not an event signaling that the entire ApplicationContext is ready**.

Specific reasons in Spring:

- **The target may still be raw:** the callback runs before the final proxy is published; advice on the target itself is not reliable at this point.
- **Self-invocation:** constructor/init calling `this.method()` does not go through the Spring proxy even if the method is public and the pointcut matches.
- **Other singletons may not be created yet:** arbitrarily accessing other beans from `@PostConstruct` can force Spring to create an entire dependency chain early.
- **Creation lock:** Spring 6.2 emphasizes that init callbacks run under a singleton creation lock; invoking complex bean chains, waiting on threads, or performing long DB/network tasks risks deadlocks.
- **Transaction/cache/security proxy semantics:** if init logic requires `@Transactional`, `@Cacheable`, `@Async`, or method security, internal calls in this phase can bypass the corresponding interception. Do not assume that merely adding business annotations makes transactions/async operate.
- **Testability/observability:** errors occurring during startup can prevent the context from finishing creation; post-refresh hooks usually have a clearer contract for "starting work".

**Example of a flawed assumption:**

```java
@Service
public class ImportService {
    @PostConstruct
    public void onCreate() {
        importBatch(); // self-invocation inside init callback
    }

    @Transactional
    public void importBatch() {
        // Write to multiple tables expecting an enclosing transaction
    }
}
```

This is an **illustrative snippet**, not a full application. Even when `@EnableTransactionManagement` is enabled, calling `importBatch()` directly on the target from `onCreate()` is not guaranteed to go through the transaction interceptor; avoid believing the annotation encloses a transaction in this case. Transaction management also requires an appropriate manager and proper data boundaries.

**Clearer design:** `ImportService.importBatch()` is a method on Spring bean B, while startup coordinator bean A calls **through B's proxy reference** after an appropriate startup point, such as after context refresh. If early import is truly required, you must still evaluate the transaction manager, idempotency, startup ordering, errors/retries, and multi-replica environments.

## 6. Mechanisms to Use Instead When Work Must Run After Initialization

Choose a callback matching the **readiness milestone** actually needed, and have the coordinator bean **inject the target bean through Spring**.

| Need | Suitable Spring mechanism | Guarantees / limits to understand |
| --- | --- | --- |
| Set up properties, validate dependencies of **the bean itself** | `@PostConstruct` | Local initialization only. Do not require advice on the callback itself or self-calls. |
| Wait until **non-lazy singletons** have been created by the container | `SmartInitializingSingleton.afterSingletonsInstantiated()` | Runs at the end of creating non-lazy singletons; does not guarantee all lazy beans or all context events have completed. |
| Run a step after **ApplicationContext refresh** | `@EventListener(ContextRefreshedEvent.class)` / `ApplicationListener<ContextRefreshedEvent>` | Context has refreshed; event can fire again on refresh, and can fire in parent/child contexts. Design idempotently. |
| Start/stop resources requiring lifecycle coordination | `SmartLifecycle` | Has start/stop and phase ordering, usually suitable for background components. |
| Spring Boot: run a task once the context has started and runners are invoked | `ApplicationRunner` or `CommandLineRunner` | Boot hook; code calls services injected via proxies. Can block startup if the task is slow/fails. |
| Spring Boot: react after startup is complete | `@EventListener(ApplicationReadyEvent.class)` | Boot event after runners; **does not prove** downstream external dependencies are healthy or all async tasks finished. |

### 6.1. Spring Framework Example: Coordinating After ContextRefreshedEvent

The following snippet is a **separate illustrative variant**; do not add it to the demo project above if you want to keep the verified stdout unchanged.

```java
package com.example.initdemo;

import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;

public class AfterRefreshCoordinator {
    private final WorkService workService;

    public AfterRefreshCoordinator(WorkService workService) {
        this.workService = workService;
    }

    @EventListener(ContextRefreshedEvent.class)
    public void onRefreshed() {
        workService.process("after-context-refreshed");
    }
}
```

Register from config:

```java
@Bean
AfterRefreshCoordinator afterRefreshCoordinator(WorkService workService) {
    return new AfterRefreshCoordinator(workService);
}
```

When Spring publishes `ContextRefreshedEvent`, `AfterRefreshCoordinator` calls `WorkService.process` through the reference injected by the container, so the method can go through advice if the pointcut matches. In applications with parent/child contexts, multiple refreshes, or multiple nodes, filter by context and ensure idempotency; do not assume the event occurs only once in the system's lifetime.

**Key point:** The "after refresh" milestone helps coordinate work in the right phase, yet **if the event handler is placed right inside `WorkService` and calls `this.process()`, self-invocation still bypasses advice**. Keep the coordinator bean separate from the business bean when calls must go through a proxy.

### 6.2. Spring Boot Example: ApplicationRunner Calling Another Bean

With Spring Boot, an `ApplicationRunner` receiving a `WorkService` dependency is a clear choice for a startup task:

```java
package com.example.initdemo;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class StartupRunner implements ApplicationRunner {
    private final WorkService workService;

    public StartupRunner(WorkService workService) {
        this.workService = workService;
    }

    @Override
    public void run(ApplicationArguments args) {
        workService.process("boot-runner");
    }
}
```

This is an **illustrative snippet for Spring Boot only**; it will not compile in the plain Spring Framework project because Boot dependencies are not declared. Boot can auto-configure AOP when an appropriate starter is present and auto-configuration is not disabled; whether using Boot or Framework, advice still depends on pointcuts and calls going through the proxy.

`ApplicationRunner` runs during Boot application startup, before Boot publishes `ApplicationReadyEvent`. If a runner takes a long time, startup slows down as well; tasks should have timeout, error, and idempotency design. If you need start/stop coordination for a background component, look at `SmartLifecycle`.

### 6.3. Does SmartInitializingSingleton Avoid Self-Invocation?

No. `afterSingletonsInstantiated()` runs at a later milestone than `@PostConstruct`, yet **the callback calling another method on the same object itself** still does not automatically turn into a call through the AOP proxy. If advice is needed, use a **separate coordinator bean** that receives the proxy of the corresponding service.

The startup callback order solves **when work begins**; the Spring AOP proxy determines **what the call goes through**. Both conditions must be satisfied.

## 7. When a Constructor or @PostConstruct Must Call Shared Code

Not every method called from a constructor/init needs Spring AOP. For pure logic such as validating inputs, building a local cache, or normalizing configuration, keeping it as a **private helper** called directly makes sense:

```java
@PostConstruct
public void initialize() {
    validateConfiguration();
    createLocalIndex();
}

private void validateConfiguration() {
    // Only checks injected data; no proxy needed.
}

private void createLocalIndex() {
    // Builds local data structures that are immutable after initialization.
}
```

The snippet above is illustrative, not a standalone runnable file. Those private helpers **intentionally do not need AOP**, and `private` methods are not overridden/intercepted by a Spring subclass proxy. Separate goals cleanly:

- **Local initialization:** direct, does not depend on a proxy.
- **Business use case needing transaction/security/audit/metrics:** placed on an interceptable method of a Spring bean; caller holds the proxy reference.
- **Startup orchestration:** separate bean running after an appropriate milestone and calling through ready service beans.

For work that must hold state or external resources, build an explicit start/stop/retry mechanism; do not put it in a constructor because the constructor can run before dependency injection completes.

## 8. Advanced Cases and Limits of Inference

### 8.1. Do Not Use ObjectProvider or ApplicationContext.getBean in a Constructor to "Get Your Own Proxy"

One may find attempts to fetch the bean from the context, use `ObjectProvider`, self-injection, or `AopContext.currentProxy()` to call one's own method. While a constructor/`@PostConstruct` is running, **the proxy may not be ready yet**, or you may create a circular dependency causing premature initialization. `AopContext.currentProxy()` only exists when `exposeProxy=true` and execution is already inside a Spring AOP proxy call; it does not turn a constructor/init callback into a proxied call.

When a method genuinely must be intercepted, prefer **separating beans** and choosing a later startup milestone.

### 8.2. Early Singleton References and Circular Dependencies

Spring has steps for handling early bean references in circular dependency situations, and the auto-proxy creator can participate via hooks like `getEarlyBeanReference`. That does not mean one can conclude "a proxy already exists inside every `@PostConstruct`". In practice, premature initialization raises the risk of receiving a raw target or an incompletely processed bean. The most stable approach is to **break dependency cycles**, keep constructor/init local, and invoke business logic after the dependency graph is complete.

### 8.3. BeanPostProcessor and Early-Created Beans Themselves

Spring's auto-proxy creator is a type of `BeanPostProcessor`. Another `BeanPostProcessor` and the beans it directly depends on can be created very early, before all BeanPostProcessors are registered. Spring documentation warns that some beans from this phase **are not eligible for full auto-proxying**, often logging something like "not eligible for getting processed by all BeanPostProcessors".

Do not put business logic needing AOP into a `BeanPostProcessor` or a dependency created during the infrastructure phase. For the BPP infrastructure to work properly, `@Bean` methods defining BeanPostProcessors are usually recommended to be declared `static` with minimal dependencies; this is a Spring infrastructure configuration issue, quite distinct from `@PostConstruct` of an ordinary service.

### 8.4. Proxy Configuration and Non-Interceptable Methods

Not every proxy can intercept every method:

- JDK dynamic proxies intercept calls through the proxy's interfaces.
- Class-based proxies (CGLIB) cannot override `private`/`final` methods or subclass a `final` class.
- Self-invocation on the target bypasses the proxy under both mechanisms.
- Constructors **are not Spring AOP method execution join points**; Spring proxies do not provide a way to intercept arbitrary constructor statements.

If you need to intercept constructors/fields/internal call sites at the bytecode level, consider another design approach or dedicated AspectJ weaving; `@EnableAspectJAutoProxy` does not enable weaving by itself.

## 9. Diagnosing When Advice Does Not Appear During Startup

| Symptom | Explanation in Spring | Verification and fix |
| --- | --- | --- |
| Method called in constructor has no advice | Target is under construction; call is `this.method()` | Do not rely on proxies in constructors; do local initialization only. |
| Method called from `@PostConstruct` of the target itself has no advice | Callback runs before final proxy; internal call bypasses proxy | Move the AOP-needing use case to a service boundary; call from a coordinator after startup. |
| `@PostConstruct` itself receives no advice despite matching pointcut | Lifecycle invokes it on the raw bean during initialization | Do not use advice to control init callbacks; use the right lifecycle hook. |
| `@PostConstruct` of bean A calls bean B's method and gets advice | B is already initialized/proxied; A holds the proxy reference | Behavior can be valid; still avoid abusing post-construct for heavy work. |
| Spring context finishes creating, yet method still gets no advice | Aspect is not a bean, missing auto-proxy support, pointcut mismatch, or caller uses raw reference | Check `@Aspect`+`@Component`/`@Bean`, `@EnableAspectJAutoProxy`, runtime proxy, and actual invocation. |
| Self-call still gets no advice after startup | `this` does not go back through the proxy | Move the method to another bean, call via injected proxy. |
| Self-injecting own bean causes circular dependency error | Bean is referenced while under initialization | Remove self-injection, break the cycle, and replace with a coordinator bean. |
| Log shows "not eligible for auto-proxying" | Bean was created too early during BeanPostProcessor bootstrap | Check BPP dependencies, `static @Bean`, and bean creation timing. |
| Startup hangs when `@PostConstruct` accesses many beans or waits on threads | Complex work invoked under singleton creation lock | Move to `SmartInitializingSingleton`/`ContextRefreshedEvent`/Boot runner based on readiness. |
| `@Transactional`/`@Async` has no effect in init | Proxy boundary or annotation's own trigger mechanism is not met | Diagnose proxy/service boundary and pick a post-initialization hook. |

### A Minimal Reliable Measurement

```java
WorkService bean = context.getBean(WorkService.class);
System.out.println(AopUtils.isAopProxy(bean));
bean.process("probe");
```

This is an illustrative snippet placed **after context refresh**, with `AopUtils` imported and an existing context/bean. It checks two things:

1. `AopUtils.isAopProxy(bean)` confirms whether **the current reference** is a Spring AOP proxy.
2. The output/advice of `process("probe")` proves the specific method is actually handled by the advisor.

Checking `isAopProxy=true` alone is not enough: the proxy might carry a different advisor while the pointcut of the aspect under test does not match `process`.

To test lifecycle, place a thread-safe recorder tracking constructor/init/advice/target milestones and assert the order, rather than relying on framework logs mixed with application logs. When running asynchronously, cross-thread order is no longer deterministic; avoid hardcoding a fixed stdout table for that case.

## 10. Rules for Choosing Where to Place Initialization

Answer each question in order:

1. **Does the action only change internal state of the bean itself?** If yes, `@PostConstruct` fits. Do not force it through Spring AOP.
2. **Is the action a business use case needing advice or a Spring interceptor?** Put it on a proxied service method, and call it from another bean via DI.
3. **Does the action need to ensure all normal singletons are created?** Consider `SmartInitializingSingleton`, while still keeping calls going through proxies.
4. **Must the action run after ApplicationContext refresh?** Consider `ContextRefreshedEvent`, noting the possibility of multiple contexts and re-publishing.
5. **Are you in Spring Boot and need a runner/ready event?** Use `ApplicationRunner` or `ApplicationReadyEvent` according to the desired milestone.
6. **Does the task need long-running operation, stop/restart?** Consider `SmartLifecycle`.
7. **Does the task need remote/DB calls or async?** Define timeouts, transactions, retries, idempotency, startup failures, and multi-replica behavior.

Do not treat **`@PostConstruct` + self-call to an AOP-annotated method** as a reliable business invocation pattern, even if a project occasionally appears to print some advice under special configurations.

## 11. Practical QA Checklist

- [ ] Clearly identified **which target** owns the `@PostConstruct` callback and **which target** owns the advised method.
- [ ] On the same target, does constructor/`@PostConstruct` call `this.method()`? If so, do not expect AOP proxy interception.
- [ ] Is the aspect registered as a Spring bean, AOP auto-proxying enabled, and pointcut matching the method?
- [ ] For Spring Framework 6.x, are `jakarta.annotation.PostConstruct` and matching dependencies used?
- [ ] Distinguished a bean still initializing from a completed bean whose proxy is injected into another bean?
- [ ] Used `AopUtils.isAopProxy` **after context refresh** to inspect the reference; called the method through that exact reference?
- [ ] Avoided using `AopContext.currentProxy()` or self-injection in constructor/init to bypass the lifecycle?
- [ ] Avoided placing remote calls, long transactions, heavy schedulers, or operations waiting on other beans inside init callbacks?
- [ ] When startup work is needed, chose `SmartInitializingSingleton`, an event, a lifecycle hook, or a Boot runner/ready event at the right milestone?
- [ ] Tested the proxied call path and internal call path separately, comparing advice output against expectations?
- [ ] Accounted for context hierarchies, circular dependencies, startup failures, and event re-publishing?

**Key takeaway:** With Spring AOP proxies, `@PostConstruct` runs in the lifecycle of the **raw target** and is not a business call through a proxy; calling `this.method()` from it bypasses advice. However, `@PostConstruct` on **another bean** can still call through the proxy of a bean that has already finished initializing. If a requirement truly needs transaction/security/audit/async advice, **choose the right bean boundary and startup milestone**, rather than relying on interception while the bean is still initializing.

## Official Spring Documentation

- [Spring Framework 6.2 — Customizing the Nature of a Bean (lifecycle, raw bean, creation lock)](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html)
- [Spring Framework 6.2 — Container Extension Points (BeanPostProcessor and auto-proxy)](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-extension.html)
- [Spring Framework 6.2 — Using @PostConstruct and @PreDestroy](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/postconstruct-and-predestroy-annotations.html)
- [Spring Framework 6.2 — Proxying Mechanisms (self-invocation)](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Spring Framework 6.2 — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html)

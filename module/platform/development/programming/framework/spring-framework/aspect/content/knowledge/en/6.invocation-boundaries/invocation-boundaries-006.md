# Calls from constructors or initialization callbacks before the Spring AOP proxy is ready

## 1. Why is a method with `@Aspect` advice not intercepted when called during initialization?

In Spring AOP, advice only has a chance to execute when a method call **passes through a Spring AOP proxy** carrying a matching advisor. During the creation of a Spring bean, there is a window where **the target object already exists yet the final proxy has not yet been formed or published for other beans to use**.

Consequently, a method call from a constructor, `@PostConstruct`, `InitializingBean.afterPropertiesSet()`, or a custom init method on **the very bean being initialized** does not automatically pass through that bean's proxy. If that method has `@Before`, `@Around`, `@Transactional`, or `@Cacheable` applied via a Spring proxy, do not expect those mechanisms to activate merely because the method was invoked inside a lifecycle hook.

Example:

```java
public class ReportService {
    public ReportService() {
        generate(); // call on the target under construction
    }

    public void generate() {
        // May match a Spring @Aspect pointcut.
        // Yet the constructor does not call through a Spring proxy.
    }
}
```

This is an illustrative snippet, not a standalone program. Even though Spring can create a proxy for `ReportService` **after initialization**, that does not retroactively affect calls that already occurred earlier.

**Lesson scope:** The boundary between bean lifecycle and proxy-based Spring AOP. We focus on Spring Framework without expanding into constructor weaving or standalone AspectJ compilers. Every issue discussed ties directly to when Spring creates proxies, internal calls, and application startup.

### After this lesson, you will be able to

1. Describe the creation sequence of a Spring bean from constructor to finalized proxy.
2. Explain why calls from `@PostConstruct`, `afterPropertiesSet()`, and `initMethod` do not receive advice on that same bean.
3. Distinguish "a callback run after dependencies have been injected" from "a callback invoked through an AOP proxy".
4. Design startup steps requiring AOP using a coordinator bean calling **another bean through its proxy** after the context is ready.
5. Verify behavior using a Java 17 and Spring Framework 6.1 example with deterministic stdout.
6. Recognize notable exceptions: calling into an already-proxied dependency, premature bean initialization, circular references, and callbacks into an incomplete context.

## 2. Typical creation sequence of a Spring bean with an AOP proxy

For a regular singleton bean created via `ApplicationContext`, you can picture the sequence as:

```text
Spring registers bean definitions and BeanPostProcessors
             |
             v
[1] Instantiation: invoke constructor / @Bean factory method
             |
             v
[2] Dependency injection, *Aware callbacks, and property processing
             |
             v
[3] BeanPostProcessor.postProcessBeforeInitialization(...)
       + process @PostConstruct when the corresponding processor is present
             |
             v
[4] InitializingBean.afterPropertiesSet()
             |
             v
[5] Custom init method: @Bean(initMethod=...), init-method...
             |
             v
[6] BeanPostProcessor.postProcessAfterInitialization(...)
       + Spring AOP auto-proxy creator may wrap the target in a proxy
             |
             v
[7] Container publishes the initialized bean/proxy
             |
             v
[8] Another bean obtains the bean from Spring and calls the method through the proxy
             |
             v
       @Before / @Around / target / @After...
```

This is a **common, simplified path for learning**. Spring has many `BeanPostProcessor`s and special cases such as early proxy references, `FactoryBean`, scoped proxies, circular dependencies, or custom target sources. Those cases may add steps, yet they do not change the core principle: **calling directly on `this` is not calling through a Spring AOP proxy**.

### When callbacks are processed

| Location | Object receiving the call | Gets Spring AOP advice for the bean's own method? | Reason |
| --- | --- | --- | --- |
| Target constructor | Target under construction | **No** | Bean's proxy is not ready yet; proxy-based Spring AOP also does not advise constructor execution. |
| `@PostConstruct` on target | Raw target via lifecycle processor | **No** for direct calls on the same bean | Callback runs in the before-initialization phase, before auto-proxying completes. |
| `InitializingBean.afterPropertiesSet()` | Raw target | **No** | This is an init callback on the target, not a client method call through a proxy. |
| `@Bean(initMethod = "...")` | Raw target | **No** | Spring calls the init method during target initialization. |
| Calling `this.otherMethod()` inside an init callback | Target itself | **No** | Self-invocation goes straight to the target, bypassing the proxy. |
| Calling a method on **another dependency bean** already given a Spring proxy | Dependency's proxy | **Possibly yes** | If the dependency is already proxied and the call matches an advisor, the call passes through the **other bean's** proxy. |
| Coordinator bean calling an injected service after context refresh | Service's proxy | **Possibly yes** | Service proxy has been created, and the call goes through the Spring-provided object matching the pointcut. |

**Key takeaway:** Saying "init callbacks run before the proxy is ready" refers to **the proxy of the bean currently initializing**. It does not mean *no* dependency is proxied yet. If target A already had B injected (a fully formed Spring proxy bean), A can call B through B's proxy inside A's `@PostConstruct`. Even so, performing network/database calls while the context is still initializing can introduce startup-order and resource-readiness risks.

## 3. Constructors: why does advice not run?

### 3.1. Constructors are not method join points intercepted by Spring AOP proxies

Spring AOP supports **method execution join points on Spring-managed beans via proxies**. Declaring:

```java
@Aspect
public class TraceAspect {
    @Before("execution(* com.example.service..*.*(..))")
    public void beforeMethod() {
        System.out.println("advice");
    }
}
```

does not turn a constructor call into a proxied method invocation. Spring must **create the target first** before there is a target to proxy.

CGLIB creates a subclass to act as the proxy and typically uses Objenesis to avoid re-invoking the target constructor when instantiating the proxy. Therefore, do not conclude "CGLIB proxies run constructors through advice" or "every bean always runs its constructor twice". Proxy-based Spring AOP does not perform constructor advice in the sense of AspectJ weaving.

### 3.2. Calling a method from a constructor is also not calling through a proxy

```java
public class InvoiceService {
    public InvoiceService() {
        processInvoice("startup"); // equivalent to this.processInvoice(...)
    }

    public void processInvoice(String source) {
        System.out.println(source);
    }
}
```

Even if `processInvoice` is public, non-final, and matches a `@Before` pointcut, calling it on `this` inside the constructor executes on **an unproxied target**. Only when the bean is later obtained from Spring and a client calls `proxy.processInvoice(...)` does advice have a chance to run.

Beyond AOP, calling overridable methods from a constructor also risks exposing a partially constructed object. In Spring, dependencies injected via `@Autowired`/`@Value` after the constructor runs are not ready at that moment. Constructors should initialize internal state, not trigger business operations needing AOP or injected dependencies.

## 4. `@PostConstruct`: dependencies being injected does not mean having your own proxy

### 4.1. Nature of `@PostConstruct` in Spring

In Spring Framework 6.x, `@PostConstruct` comes from the `jakarta.annotation` package. When the lifecycle annotation processor infrastructure is registered, annotated methods execute **after dependency injection** yet **before initialization finishes**, in the before-initialization phase.

```java
import jakarta.annotation.PostConstruct;

public class OrderService {
    @PostConstruct
    public void initialize() {
        saveOrder("from-init"); // self-invocation on the raw target
    }

    public void saveOrder(String id) {
        // This method may match Spring AOP @Around/@Before.
    }
}
```

This is an illustrative snippet. If advice appears not to run for the `saveOrder` call inside `initialize`, that **matches** Spring proxy semantics. Do not tweak pointcuts, switch from JDK proxy to CGLIB, or raise `@Order` expecting to change that boundary.

### 4.2. What if `@PostConstruct` is on the advised method itself?

Suppose a method carries both a lifecycle annotation and an annotation targeted by a pointcut:

```java
@PostConstruct
public void setup() {
    System.out.println("setup");
}
```

Spring invokes `setup()` through the lifecycle mechanism on the raw bean. Spring does not route that lifecycle call through an AOP proxy merely because the method is public or carries another annotation.

A **later call through the proxy** to the same method (if the API permits it, an advisor matches, and the method is proxiable) is a different situation; it can receive advice. Still, you should not design `@PostConstruct` as a business API for clients to re-invoke. Keeping lifecycle methods separate from business methods is cleaner, and keeping init idempotent where possible is good practice.

### 4.3. Calling another dependency inside `@PostConstruct` is a different case

```java
public final class InitCoordinator {
    private final ReportService reportService;

    public InitCoordinator(ReportService reportService) {
        this.reportService = reportService; // Spring may inject a proxy
    }

    @PostConstruct
    public void initialize() {
        reportService.generate(); // call on a dependency, not this
    }
}
```

This is an illustrative snippet assuming Spring registers `InitCoordinator` and `ReportService`, and the dependency is proxied. The `reportService.generate()` call **can** receive `ReportService`'s advice even while `InitCoordinator` is inside `@PostConstruct`. Crucially, however, **the target bean of the advised call is not the bean currently initializing itself**.

If the logic requires the whole application to be refreshed, transaction infrastructure ready, and services in a settled state, calling into dependencies inside `@PostConstruct` is not ideal. An orchestration step after the context starts up is usually easier to control.

## 5. `InitializingBean` and custom init methods: the same principle

Spring can run multiple initialization mechanisms for a single bean:

1. `@PostConstruct`.
2. `InitializingBean.afterPropertiesSet()`.
3. A custom init method configured via `@Bean(initMethod="...")` or equivalent configuration.

If a bean declares all three mechanisms on **three distinct methods**, the order above is the standard sequence. All of them are **initialization callbacks on the raw target**.

```java
public class CleanupService implements InitializingBean {
    @PostConstruct
    public void postConstruct() {
        process("postConstruct");
    }

    @Override
    public void afterPropertiesSet() {
        process("afterPropertiesSet");
    }

    public void customInit() {
        process("customInit");
    }

    public void process(String phase) {
        System.out.println(phase);
    }
}
```

This illustrative snippet omits imports and bean registration; the complete example is in section 7. All `process(...)` calls on `this` bypass `CleanupService`'s proxy. The fact that `InitializingBean` is a Spring interface does not turn an init callback into an AOP invocation.

**Do not confuse initialization callbacks with post-context-refresh callbacks:** `afterPropertiesSet()` means dependency properties have been set on the bean, not that every bean, advisor, or application-wide resource is ready.

## 6. Calling methods after the proxy is ready: the necessary boundary

### 6.1. Calling through a Spring-managed reference

```text
Inside Service's constructor / @PostConstruct:
    this.perform()
        |
        v
    target.perform()       => no AOP proxy on the call path

After context refresh, another bean has injected Service:
    startupRunner -> serviceProxy.perform()
                       |
                       v
                   @Before/@Around...
                       |
                       v
                   target.perform()  => advice runs if pointcut matches
```

A context refresh event can serve as an **orchestration point** after singleton infrastructure has been initialized. In plain Spring Framework, you can register an `ApplicationListener<ContextRefreshedEvent>` bean that receives the service proxy as a dependency and calls the service through the proxy. In Spring Boot, `ApplicationRunner`/`CommandLineRunner` or `ApplicationReadyEvent` are commonly used for startup work after context refresh, though exact timing and suitability depend on whether callers should wait for runners to finish.

### 6.2. Two errors that look similar

| Symptom | Cause | How to distinguish |
| --- | --- | --- |
| Aspect does not run in service's `@PostConstruct`, yet runs when controller calls service | Internal call before proxy | Test the same method before/after context refresh. |
| Aspect does not run when method A calls `this.methodB()` **after startup finishes** | Self-invocation stays on target, bypassing proxy | Move `methodB` to a collaborator bean and call through Spring dependency. |

The second point matters: **even after the proxy is created, self-invocation still bypasses advice**. Initialization timing makes the issue surface more easily, yet the proxy boundary always governs behavior.

### 6.3. Do not use `AopContext.currentProxy()` inside a constructor to "get the proxy early"

`AopContext.currentProxy()` makes sense only while executing a call **through a proxy configured with `exposeProxy`**, on the corresponding execution thread. A bean's normal constructor or init callback is not inside such an AOP proxy call. Relying on this API can throw `IllegalStateException` or couple code tightly to Spring AOP.

Likewise, never store target's `this` in a static field or leak that reference for "early startup": clients may end up holding **a raw target reference** and permanently bypass the proxy, creating bugs that are very hard to trace.

## 7. Runnable example: constructor → `@PostConstruct` → `afterPropertiesSet` → custom init → `ContextRefreshedEvent`

This example uses **Java 17, Spring Framework 6.1.14, Gradle**. It proves via output that **the exact same method** is advised only when called through the proxy after the bean is fully formed.

A plain Spring Framework project with five Java classes. No Spring Boot, web server, or database needed.

### 7.1. Directory structure

```text
spring-aop-init-boundary/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/lifecycle/
    ├── StartupService.java
    ├── StartupAspect.java
    ├── StartupCaller.java
    ├── AppConfig.java
    └── DemoApplication.java
```

### 7.2. Build configuration

`settings.gradle`:

```groovy
rootProject.name = 'spring-aop-init-boundary'
```

`build.gradle`:

```groovy
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
    implementation 'org.springframework:spring-context:6.1.14'
    implementation 'org.springframework:spring-aop:6.1.14'
    implementation 'org.aspectj:aspectjweaver:1.9.22.1'
    implementation 'jakarta.annotation:jakarta.annotation-api:2.1.1'
}

application {
    mainClass = 'demo.lifecycle.DemoApplication'
}
```

- `spring-context` provides the IoC container, `ApplicationListener`, `ContextRefreshedEvent`, and Java-based configuration.
- `spring-aop` provides AOP proxy infrastructure.
- `aspectjweaver` provides the components Spring needs to parse `@Aspect` pointcut expressions.
- `jakarta.annotation-api` provides `@PostConstruct` on Java 17; the Spring context registers the annotation-processing infrastructure when the dependency is present.

### 7.3. Target making four calls to the same method during initialization

`src/main/java/demo/lifecycle/StartupService.java`:

```java
package demo.lifecycle;

import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.InitializingBean;

public class StartupService implements InitializingBean {

    public StartupService() {
        System.out.println("constructor");
        perform("constructor");
    }

    @PostConstruct
    public void postConstruct() {
        System.out.println("postConstruct");
        perform("postConstruct");
    }

    @Override
    public void afterPropertiesSet() {
        System.out.println("afterPropertiesSet");
        perform("afterPropertiesSet");
    }

    public void customInit() {
        System.out.println("customInit");
        perform("customInit");
    }

    public void perform(String origin) {
        System.out.println("target:" + origin);
    }
}
```

The lifecycle methods call `perform` directly on the target. `perform(String)` is public and non-final, so CGLIB can advise it when clients actually call through the proxy later. The `origin` parameter lets us see which phase originated each call.

### 7.4. Spring `@Aspect` tracking every proxied call to `perform`

`src/main/java/demo/lifecycle/StartupAspect.java`:

```java
package demo.lifecycle;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class StartupAspect {

    @Before("execution(public void demo.lifecycle.StartupService.perform(String))")
    public void beforePerform(JoinPoint joinPoint) {
        String origin = (String) joinPoint.getArgs()[0];
        System.out.println("advice:" + origin);
    }
}
```

`StartupAspect` is processed by Spring because the class has `@Aspect` and will be registered as a bean in `AppConfig`. `@Aspect` does not automatically register a bean without `@Component`, `@Bean`, or an equivalent mechanism.

The pointcut matches `StartupService.perform(String)`. In all five scenarios, the method actually executes, yet only calls **through the Spring proxy** trigger the advice.

### 7.5. Coordinator bean calling after context refresh

`src/main/java/demo/lifecycle/StartupCaller.java`:

```java
package demo.lifecycle;

import org.springframework.context.ApplicationListener;
import org.springframework.context.event.ContextRefreshedEvent;

public class StartupCaller
        implements ApplicationListener<ContextRefreshedEvent> {

    private final StartupService service;

    public StartupCaller(StartupService service) {
        this.service = service;
    }

    @Override
    public void onApplicationEvent(ContextRefreshedEvent event) {
        System.out.println("contextRefreshed");
        service.perform("contextRefreshed");
    }
}
```

`StartupCaller` does not call `this.perform(...)`: it holds the **Spring-provided `StartupService` dependency**, i.e., the proxy after the service has been completely processed. `ContextRefreshedEvent` is published when context refresh completes. The demo has a single context, so it is unaffected by events propagating to parent contexts.

In real applications, `ContextRefreshedEvent` can be published multiple times upon context refreshes or with multiple contexts. If a task must run only once, ensure idempotency/deduplication and verify the event belongs to the expected context. Do not attach arbitrary startup work to listeners without considering that behavior.

### 7.6. Enabling AOP and registering beans

`src/main/java/demo/lifecycle/AppConfig.java`:

```java
package demo.lifecycle;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean(initMethod = "customInit")
    public StartupService startupService() {
        return new StartupService();
    }

    @Bean
    public StartupAspect startupAspect() {
        return new StartupAspect();
    }

    @Bean
    public StartupCaller startupCaller(StartupService service) {
        return new StartupCaller(service);
    }
}
```

The configuration explicitly forces class-based proxies so we can retrieve the Spring bean as `StartupService`. No proxy is created inside `new StartupService()`; Spring processes the bean through the rest of its lifecycle and applies the auto-proxy creator at the appropriate point.

`@Bean(initMethod = "customInit")` tells Spring to invoke `customInit` after `afterPropertiesSet`. `StartupCaller` is injected with the service by the container, so it receives the Spring-managed reference rather than a manually `new`-ed object.

### 7.7. Launching and observing

`src/main/java/demo/lifecycle/DemoApplication.java`:

```java
package demo.lifecycle;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApplication {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            StartupService service = context.getBean(StartupService.class);

            System.out.println("proxy=" + AopUtils.isAopProxy(service));
            service.perform("external");
        }
    }
}
```

Place the files at their proper paths, then run from the directory containing `build.gradle`:

```bash
gradle run
```

If the project includes a Gradle Wrapper, run `./gradlew run` (Linux/macOS) or `gradlew.bat run` (Windows).

Lines **printed by the program's code** in exact order (excluding Gradle or environment logs):

```text
constructor
target:constructor
postConstruct
target:postConstruct
afterPropertiesSet
target:afterPropertiesSet
customInit
target:customInit
contextRefreshed
advice:contextRefreshed
target:contextRefreshed
proxy=true
advice:external
target:external
```

#### Reading the output

1. In constructor, `@PostConstruct`, `afterPropertiesSet()`, and `customInit()`, we see `target:...` with **no `advice:...` line**. The `perform` method ran, yet the call path was the raw target / `this`.
2. `contextRefreshed` appears after the four callbacks. Here `StartupCaller` invokes `service.perform` through the Spring-managed reference, producing `advice:contextRefreshed` before `target:contextRefreshed`.
3. `proxy=true` confirms the `StartupService` bean returned by `getBean(...)` is a Spring AOP proxy.
4. Calling `service.perform("external")` after fetching the bean from the container also prints `advice:external`. No pointcut changes are needed between startup and runtime.
5. Total target invocations are **six**: four during lifecycle and two through the proxy. Advice invocations are **two**. This gap demonstrates that interception depends on calling through the proxy.

**Note on reading stdout:** Observing two `advice:...` lines does not mean Spring "failed to see the aspect" during initialization. The aspect was registered; it is simply that the initialization calls on the target did not pass through the proxy. These output lines assume AOP is enabled as in `AppConfig` and dependencies are loaded properly.

## 8. What about `@Transactional`, `@Cacheable`, or `@Async`?

The following annotations also typically operate through Spring proxies:

| Mechanism | Direct call from same bean's init callback | Risk of misinterpretation |
| --- | --- | --- |
| Spring `@Aspect` advice | Does not pass through the bean's own proxy | Logging/audit/validation advice does not run during init call |
| `@Transactional` in proxy mode | Does not pass through the bean's own transaction interceptor | No transaction advice merely from having the annotation on the method |
| `@Cacheable` / `@CacheEvict` in proxy mode | Does not pass through the bean's own cache interceptor | Cache operation does not occur as assumed |
| `@Async` in proxy mode | Does not pass through the bean's own async interceptor | Call runs synchronously on startup thread instead of offloading to executor |

Example of a mistaken expectation:

```java
@PostConstruct
public void init() {
    rebuildCache(); // self-invocation; @Cacheable/@Transactional on
                    // rebuildCache() is not automatically applied via proxy
}
```

That is only an illustrative snippet; there is no `CacheManager` or transaction manager in section 7's runnable example. When startup work genuinely needs transactions or caching, place the business logic in **another Spring-proxied bean** and call it through a dependency at an appropriate time. The corresponding transaction/cache infrastructure must be fully configured; proxies do not invent a `TransactionManager` or `CacheManager`.

**Important distinction:** Opening a transaction with a direct programmatic API like `TransactionTemplate` is a different mechanism from `@Transactional` advice; it can execute if the right dependency/infrastructure is ready, though it does not turn self-invocation into a proxied call.

## 9. Premature initialization: bean ineligible for auto-proxying

Aside from "the bean's own callbacks lack advice", Spring also has the case where **a bean is created before required `BeanPostProcessor`s are fully registered**.

Example to avoid:

```java
@Configuration
class EarlyProcessorConfiguration {

    @Bean
    BeanPostProcessor customProcessor(ExpensiveService service) {
        // Direct dependency on ExpensiveService may cause
        // the service to initialize too early during BPP registration.
        return new CustomBeanPostProcessor(service);
    }
}
```

This snippet illustrates the problem and **is not a standalone Java file** because `ExpensiveService` and `CustomBeanPostProcessor` are undeclared. `BeanPostProcessor`s must be instantiated very early so they can process other beans. If registering them forces a service to be created early, that service may miss processing by all `BeanPostProcessor`s (including the AOP auto-proxy creator). Spring may log a warning like:

```text
Bean 'someService' ... is not eligible for getting processed
by all BeanPostProcessors (for example: not eligible for auto-proxying).
```

This is an **illustrative message format**; exact wording varies by version. Unlike init callbacks on the target, here even **post-startup service calls** may receive no advice because the bean was created prematurely without being properly proxied.

### How to fix

- Avoid making `BeanPostProcessor`s directly depend on business beans that need AOP.
- When using `@Bean` to declare a `BeanPostProcessor`, make the factory method `static` and return the concrete `BeanPostProcessor` type or the `BeanPostProcessor` interface so Spring detects it early and accurately.
- Avoid arbitrary `getBean()` calls on services from `BeanFactoryPostProcessor` or early infrastructure registration code.
- Read `not eligible for auto-proxying` warnings to find which dependency triggered premature initialization.
- Re-check `AopUtils.isAopProxy(bean)` after fixing configuration.

### What about circular dependencies and early proxy references?

Spring can supply an **early reference** in certain circular dependency situations, and the auto-proxy creator has hooks supporting early proxy references under appropriate conditions. Therefore, one cannot state either "every early reference is definitely a raw target" or "enabling circular references guarantees advice works".

The reliable fix is usually **eliminating dependency cycles and avoiding leaking `this` during constructors/init**. If singleton A depends on B and B depends back on A, A's incomplete lifecycle makes AOP, transactions, and `BeanPostProcessor` behavior unpredictable and sometimes causes context startup errors. Never use circular references as a way to get advice inside `@PostConstruct`.

## 10. Options for running startup work after proxies are finalized

### 10.1. A coordinator bean listening for `ContextRefreshedEvent`

This is the pattern shown in section 7's example. The coordinator uses the service proxy rather than having the service call itself in a constructor:

```text
ContextRefreshedEvent
       |
       v
StartupCaller (ApplicationListener)
       |
       v
StartupService proxy
       |
       v
Spring AOP advice
       |
       v
StartupService target
```

Ensure the callback is **idempotent**, verify context identity when parent–child context hierarchies exist, and avoid infinite loops on every event receipt. When running outside Spring Boot, this approach requires no Boot-specific runner.

### 10.2. `SmartInitializingSingleton`

Spring provides the `SmartInitializingSingleton` interface with its `afterSingletonsInstantiated()` callback invoked once regular non-lazy singletons in the `BeanFactory` finish instantiating. This is useful when interacting with already-initialized beans.

However:
- The callback sits on the object Spring identifies as `SmartInitializingSingleton`; if that object itself is wrapped in a JDK interface proxy that does not expose the callback, verify how discovery and callback invocation actually behave. Do not blindly place the callback on a proxied service.
- Not every lazy singleton, prototype, or request-scoped bean has been created yet.
- Calling `this.advisedMethod()` **still bypasses the proxy** even though the callback runs later.

The clean approach is having a coordinator bean that does not need self-advice implement the callback, while obtaining the AOP-enabled service from Spring as a dependency and calling it via the proxy.

### 10.3. Spring Boot: `ApplicationRunner`, `CommandLineRunner`, and `ApplicationReadyEvent`

In a Spring Boot application:
- `ApplicationRunner` and `CommandLineRunner` run after the context refreshes and Boot invokes runners.
- `ApplicationReadyEvent` is published near the end of startup, after runners in the standard Boot lifecycle.
- A dedicated runner or listener can have Spring-managed service proxies injected and invoke advised methods.

These are **Boot mechanisms** and do not exist automatically in plain Spring Framework. Regardless of when the call happens, **calling `this.method()` inside the same target still bypasses the Spring AOP proxy**. When scheduling long or blocking work at startup, consider whether the application is ready to accept requests yet; avoid inadvertently blocking essential lifecycle steps.

### 10.4. Event listeners also need proper bean boundaries

`@EventListener` or `ApplicationListener` are merely how Spring delivers events; they do not promise "every listener method goes through an AOP proxy". If a handler method sits on a JDK-proxied bean, it may need to be exposed on an interface or use compatible proxy settings. If a service's handler calls `this.someAdvisedMethod()`, that is still self-invocation.

For maximum clarity and testability, **separate listeners/runners into coordinator beans** and inject service proxies separately, as with `StartupCaller`.

## 11. Common issues table

| Symptom | Common Spring AOP cause | How to fix/check |
| --- | --- | --- |
| Public method has `@Before` yet calling from constructor prints no advice | Target is still under construction, no call path through proxy | Move business logic to post-startup step through service proxy |
| `@PostConstruct` calls `@Transactional` method yet no transaction interceptor runs | `this.method()` call on raw target | Move transactional method to a collaborator bean and inject/call via Spring proxy |
| `afterPropertiesSet()` calls `@Cacheable` method yet next call still recomputes | Init call bypasses cache proxy | Route cached operation through bean proxy, verify cache manager |
| `@Async` method runs on main/startup thread when called in init | Does not go through async proxy | Use runner/listener calling another bean once infrastructure is ready |
| Advice runs after startup yet not during init | Standard proxy lifecycle behavior | Compare stdout and `isAopProxy`; do not treat as a broken pointcut |
| Advice does not run even after startup; `not eligible for auto-proxying` logged | Bean initialized prematurely during `BeanPostProcessor` phase | Fix post-processor dependencies, avoid eager creation of business beans |
| Calling from bean A's `@PostConstruct` to bean B runs advice | A injects **already-finished proxy B** | Normal; distinguish callback owner from invoked target bean |
| Using `AopContext.currentProxy()` in constructor fails | No active exposed proxy at that point | Do not use as an initialization workaround; design a coordinator bean |
| CGLIB proxy exists yet `this.method()` still has no advice | Self-invocation is a limit of the proxy mechanism | Call via an actual Spring bean dependency/proxy |
| Listener runs repeatedly after refresh | Multiple refreshes, multiple contexts, or event propagation | Filter for the intended context, keep state idempotent |
| Method annotated `@PostConstruct` does not run at all | Missing Jakarta annotation API or lifecycle processor; invalid method/config | Check Jakarta package, dependencies, registration, and lifecycle setup |

## 12. Diagnostic workflow when advice disappears at startup

Instead of changing settings randomly, check in order:

1. **Where does the call happen?** Constructor, `@PostConstruct`, `afterPropertiesSet`, custom init, event listener, or post-startup REST/service invocation?
2. **Which bean is actually being called?** If it is `this` on the initializing target, it is not a Spring AOP proxy. If calling another dependency, check whether that dependency is proxied.
3. **Is the bean Spring-managed?** Objects created manually with `new` outside the context do not undergo AOP post-processing.
4. **Is AOP enabled and is the aspect a Spring bean?** In Spring Framework, register `@EnableAspectJAutoProxy` in the right context; in Boot, check AOP auto-configuration and dependencies.
5. **Was a proxy actually created?** Fetch the bean from the context after startup and check `AopUtils.isAopProxy`; inspect JDK/CGLIB too if needed.
6. **Do the pointcut and method match?** Check package, annotations, method visibility, and `final`/`private` limits. If the same method gets advised when called externally, the issue is the call boundary.
7. **Was the bean created too early?** Inspect `BeanPostProcessor` logs and bean definitions, especially `@Bean` methods declaring custom processors.
8. **Is there a circular dependency or early reference?** Avoid relying on early references to guarantee advice; fix the dependency graph.
9. **If moved to an event/runner, check timing and idempotency.** Can the event fire multiple times? Was the service genuinely injected as a proxy? Is the runner executing in the right context?

## 13. Key takeaways

In proxy-based Spring AOP, there are two independent boundaries:

- **Lifecycle boundary:** The target is instantiated and receives init callbacks **before** the proxy for that bean is finalized.
- **Call boundary:** Only method invocations **through the Spring AOP proxy** can be advised; self-invocation on `this` bypasses advice, even after startup completes.

A bean's constructor, `@PostConstruct`, `InitializingBean.afterPropertiesSet()`, and custom init methods are good places to set up **the bean's internal state**, not the right places to expect AOP advice on that same bean. For startup work requiring logging, transaction, caching, or async advice, use a **coordinator bean** calling a **Spring-managed service proxy** at a lifecycle point that fits the requirement and guards against duplicate runs.

### Official Spring documentation

- [Spring Framework — Customizing the Nature of a Bean](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): initialization callbacks execute on raw bean, order `@PostConstruct` → `afterPropertiesSet` → custom init.
- [Spring Framework — Container Extension Points](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html): `BeanPostProcessor` before/after initialization, auto-proxying, and premature bean initialization.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): Spring AOP proxies, self-invocation, JDK/CGLIB, and Objenesis.
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): registering `@Aspect` and enabling `@EnableAspectJAutoProxy`.
- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): `ContextRefreshedEvent` and `ApplicationListener`.
- [Spring Framework — SmartInitializingSingleton Javadoc](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/beans/factory/SmartInitializingSingleton.html): callback after regular singleton instantiation.
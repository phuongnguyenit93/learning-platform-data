# Early Initialization Limitations When Using AsyncConfigurer in Spring

When asynchronous processing is enabled with `@EnableAsync`, Spring allows customizing the default executor and exception handling for `@Async void` methods via the **`AsyncConfigurer`** interface. This is a useful mechanism, yet it has a lifecycle limitation that is easy to overlook: **configuration classes implementing `AsyncConfigurer` are initialized early by Spring during the `ApplicationContext` bootstrap phase**.

This directly affects dependency injection and proxying. If the `AsyncConfigurer` class forces another service to be created too early, that service may not yet have passed through all `BeanPostProcessor`s, including processors that create proxies for certain annotations. The result can be beans initialized at the wrong time, circular dependencies, missing advice, or unexpected behavior. Spring advises **making those dependencies as lazy as possible**.

This lesson belongs to the **Proxy and Invocation** group of the **Spring Framework – concurrency** module. Its focus is understanding that limitation, distinguishing it from `@Async` failing due to self-invocation, and organizing executor configuration with **the right beans, right lifecycle, and right proxies**.

## 1. What Is `AsyncConfigurer` Used For?

Spring `@EnableAsync` activates processing for methods annotated with `@Async`. For methods invoked **through the proxy** in the default mode, Spring selects an executor to shift execution onto another thread. `AsyncConfigurer` is the configuration-level hook for two concerns:

```java
public interface AsyncConfigurer {
    default Executor getAsyncExecutor() {
        return null;
    }

    default AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return null;
    }
}
```

This is a **simplified API outline for explanation**; do not copy this interface into a project because Spring already provides `org.springframework.scheduling.annotation.AsyncConfigurer`. The actual methods are `default` methods and may return `null` when customization of the respective concern is unnecessary.

- `getAsyncExecutor()`: supplies the **default executor** for `@Async` calls that do not specify an explicit executor.
- `getAsyncUncaughtExceptionHandler()`: handles exceptions that cannot be sent directly back to the caller from `@Async` methods returning `void`.
- If `@Async("reportExecutor")` specifies a named/qualified executor, that named configuration is evaluated for the call; do not assume every `@Async` uses `AsyncConfigurer`'s default executor.
- If using `Future<T>` or `CompletableFuture<T>`, the caller must observe completion/exceptions via the `Future`. The `void` exception handler does not replace the `Future`'s error-reporting path.

To customize:

```java
@Configuration
@EnableAsync
public class AsyncConfig implements AsyncConfigurer {
    @Override
    public Executor getAsyncExecutor() {
        // Return the configured default executor.
    }

    @Override
    public AsyncUncaughtExceptionHandler
            getAsyncUncaughtExceptionHandler() {
        // Return the handler for @Async void when needed.
    }
}
```

This is a **conceptual fragment, not a standalone compilable program**: method bodies and imports are omitted. Later sections include a complete Spring Boot program and full alternative configurations.

## 2. What Does "Early Initialization" Mean?

During `ApplicationContext` creation, Spring must register infrastructure components to detect `@Async`, decide how to apply advice/proxies, and configure the executor/exception handler. Precisely for that reason, **configuration classes implementing `AsyncConfigurer` are initialized early**, rather than being assumed to initialize only at the end of bootstrap.

A simplified timeline:

```text
ApplicationContext startup
       |
       v
Read @Configuration / @EnableAsync
       |
       v
Register async infrastructure and related BeanPostProcessors
       |
       +--> Needs to discover AsyncConfigurer
       |       |
       |       v
       |    AsyncConfigurer may be initialized EARLY
       |       |
       |       +--> If eagerly injecting another service:
       |               that service may be created too early
       |               relative to some post-processors/proxies
       |
       v
Finish registering/applying post-processors for regular beans
       |
       v
Singletons ready / context starts serving
```

The diagram above is **not a fixed ordering of every callback across all Spring versions**. It illustrates the **underlying cause**: when an infrastructure component needs access to `AsyncConfigurer` early, dragged-along dependencies may not yet have gone through the application's normal processing conditions.

### 2.1. Spring's Official Warning

The Javadoc of `@EnableAsync` notes that configuration classes implementing `AsyncConfigurer` **are initialized early during bootstrap**; if they need to depend on other beans, those dependencies should be **declared lazy as much as possible**, so they have the opportunity to pass through other post-processors.

This has two implications:

1. **Do not assume** every dependency injected into `AsyncConfigurer` already has full proxies/advice just as when resolved later at runtime.
2. **Do not create complex dependency chains** inside the configurer merely to pick an executor; prefer simple configuration, clear bean separation, and deferred resolution when needed.

Primary source: Spring Framework 6.2 `EnableAsync` Javadoc (note on `AsyncConfigurer`): https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html

### 2.2. Why Do Post-Processors Matter?

Spring uses `BeanPostProcessor`s and AOP infrastructure to hook into bean creation, potentially wrapping a bean in a proxy before putting it into service. Depending on configuration, proxies/advice can handle `@Async`, `@Transactional`, caching, security, or other cross-cutting concerns.

For example, a service with `@Transactional` must be invoked **through a proxy carrying the transaction interceptor** for the annotation to take effect in standard proxy mode. If the service is instantiated/accessed too early and an incompletely processed reference is retained, you may observe calls lacking the expected behavior.

State this carefully:

- **Injecting a service into `AsyncConfigurer` does not guarantee its proxy is lost.** Impact depends on actual timing and initialization order.
- **`@Transactional` or `@Async` does not always break** if a configurer class is created early. This is a **lifecycle-dependent risk** to avoid and verify.
- The core issue is **resolving/initializing dependencies too early**, not that `@Configuration` or the `AsyncConfigurer` interface itself is inherently broken.

## 3. Risky Configuration Example: Eagerly Injecting a Service into AsyncConfigurer

The snippet below illustrates a **pattern to avoid**:

```java
@Configuration
@EnableAsync
public class RiskyAsyncConfig implements AsyncConfigurer {
    private final BillingService billingService;

    public RiskyAsyncConfig(BillingService billingService) {
        this.billingService = billingService; // Eager dependency
    }

    @Override
    public Executor getAsyncExecutor() {
        billingService.auditBootstrap(); // Invoking business logic during configuration!
        return Executors.newFixedThreadPool(4);
    }
}
```

This is a **risk-illustrating fragment**, not a complete program: `BillingService` is application-defined, and imports and shutdown policy are omitted. **Do not use the code above as a production solution.**

Independent issues:

1. `RiskyAsyncConfig`'s constructor requires `BillingService` as soon as the configurer is created. If Spring is in early bootstrap, the dependency can be pulled into bean creation ahead of the right time.
2. If `BillingService` needs an AOP proxy (e.g., `@Transactional` or `@Async`), early resolution can result in unexpected proxy behavior or messages that the bean is not eligible for processing by all post-processors.
3. Calling `billingService.auditBootstrap()` inside `getAsyncExecutor()` mixes **infrastructure initialization** with **business logic**, easily causing side effects, DB access before allowed, or starting tasks before the context is ready.
4. `Executors.newFixedThreadPool(4)` is a newly created JDK executor, not automatically a Spring bean, and is not automatically closed by Spring following bean lifecycle without extra management.
5. If the dependency in turn needs the very executor/`@Async` infrastructure being set up, a dependency cycle can arise: configurer → service → executor/proxy → configurer.

**Possible symptoms** (not guaranteed to appear every time): bean-in-creation errors, `BeanCurrentlyInCreationException`, startup failure, logs stating a bean is "not eligible for getting processed by all BeanPostProcessors", proxies missing at the right moment, or unusual startup side effects.

Do not diagnose the cause from a single log line alone. Inspect the **dependency graph**, resolution timing, and whether the bean is actually proxied.

## 4. Preferred Approach: Skip AsyncConfigurer When You Only Want a Specific Executor

In many projects, the goal is simply "use thread pool A for reports, thread pool B for email." Implementing `AsyncConfigurer` is not necessary. You can:

1. Create a Spring-managed `ThreadPoolTaskExecutor` bean.
2. Enable `@EnableAsync`.
3. Put `@Async("beanName")` on the method needing that pool.
4. Call the method from another Spring bean so it passes through the proxy.

Model:

```text
@Configuration @EnableAsync
          |
          +-- @Bean("reportExecutor") --> ThreadPoolTaskExecutor (managed)
          |
Controller bean --> ReportService proxy --> @Async("reportExecutor")
                                               |
                                               v
                                         Worker threads
```

This reduces reasons to use `AsyncConfigurer`, avoids depending on business services inside infrastructure hooks, and makes it explicit which executor is selected.

### 4.1. Complete Spring Boot Program for Spring Boot 3.x

Uses **Java 17+**, **Spring Boot 3.x / Spring Framework 6.x**, and the `spring-boot-starter-web` dependency. Place the code in **src/main/java/com/example/demo/AsyncStartupApplication.java**. This is a complete Boot application in class structure, meant to be compiled/run in a **Spring Boot project with matching dependencies**; it cannot run via plain `javac` without Spring JARs.

```java
package com.example.demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableAsync
public class AsyncStartupApplication {
    public static void main(String[] args) {
        SpringApplication.run(AsyncStartupApplication.class, args);
    }

    @Bean("reportExecutor")
    ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(20);
        pool.setThreadNamePrefix("report-");
        pool.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return pool;  // Spring manages bean initialization/shutdown
    }
}

@Service
class ReportService {
    @Async("reportExecutor")
    public CompletableFuture<String> build(String reportId) {
        String worker = Thread.currentThread().getName();
        if (!worker.startsWith("report-")) {
            throw new IllegalStateException("Unexpected executor: " + worker);
        }
        return CompletableFuture.completedFuture("built:" + reportId);
    }
}

@RestController
class ReportController {
    private final ReportService reports;

    ReportController(ReportService reports) {
        this.reports = reports;
    }

    @GetMapping("/reports/{id}/build")
    public CompletableFuture<String> build(@PathVariable String id) {
        return reports.build(id);
    }
}
```

In a project with the Gradle wrapper and Spring Boot Gradle plugin, run:

```bash
./gradlew bootRun
curl -s http://localhost:8080/reports/R1/build
```

On Windows, use `gradlew.bat bootRun`. When the request is received and the method succeeds, the response body is:

```text
built:R1
```

Explanation:

- `@EnableAsync` is placed on the application class to enable async infrastructure.
- `@Bean("reportExecutor")` creates a **named executor bean**, without needing `AsyncConfigurer`.
- `ReportController` calls **another bean `ReportService`**, so the call passes through the `@Async` proxy in default mode.
- `@Async("reportExecutor")` selects the bean explicitly; checking that the thread name starts with `report-` is an illustrative verification.
- Spring MVC can handle a `CompletableFuture` response using its async request mechanism; **the HTTP client still waits for the Future to complete to receive the body**, not right upon submission.
- Here `build` only returns a string to demonstrate the execution path, **not generating a real report**. If you need to process a long job and return `202` immediately, design a dedicated job ID/status protocol.

**Bootstrap advantage:** no `AsyncConfigurer` holds references to business services or forces them to initialize while Spring is still configuring async infrastructure.

### 4.2. What If You Need a Default Executor Without Specifying Each @Async?

The `@EnableAsync` Javadoc describes Spring searching for a unique `TaskExecutor` or an `Executor` named `taskExecutor`, when no other custom configuration is provided. Thus you can use a named executor bean and ensure there is no ambiguity. In Spring Boot projects, **auto-configuration and the number of executor beans can affect the actual selection**; do not infer defaults solely from class names.

For clarity, when work must run on a specific pool, `@Async("reportExecutor")` remains the explicit choice. When you want to change the default executor for all unqualified `@Async` calls, `AsyncConfigurer` is an option, provided early initialization is handled properly.

## 5. If You Must Use AsyncConfigurer: Defer Dependencies Intentionally

There are cases where you genuinely need `getAsyncExecutor()` as the default or centralized `getAsyncUncaughtExceptionHandler()` customization. In those cases, **simplify the configurer's dependency graph** and avoid eagerly pulling beans that may need post-processing.

### 5.1. Use @Lazy at the Injection Point

One option is injecting the dependency via a **lazy-resolution proxy** rather than fetching the real target immediately in `AsyncConfigurer`'s constructor.

Example **alternative configuration**—do not use simultaneously with the application class in Section 4 within the same project unless deliberately coordinating async configurations:

```java
package com.example.demo;

import java.util.concurrent.Executor;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class LazyAsyncConfig implements AsyncConfigurer {
    private final Executor defaultExecutor;

    public LazyAsyncConfig(
            @Lazy @Qualifier("reportExecutor") Executor defaultExecutor) {
        this.defaultExecutor = defaultExecutor;
    }

    @Override
    public Executor getAsyncExecutor() {
        return defaultExecutor;
    }
}
```

This is a **complete configuration class**, yet it depends on a separately declared `reportExecutor` bean (such as the bean in Section 4) and standard Spring imports/dependencies. `@Lazy` at the **injection point** tells Spring to supply a proxy that defers resolving the target dependency. Returning that proxy from `getAsyncExecutor()` does not necessarily force the target executor to instantiate when the configurer is created.

**Limitations to understand:**

- `@Lazy` at an injection point **does not make the entire `ApplicationContext` lazy**. If the target bean is eagerly injected by another singleton, it can still be created at startup.
- A lazy proxy defers **the actual access to the target**; if the constructor, `@PostConstruct`, or `getAsyncExecutor()` directly calls a method on the proxy too early, the target can still be resolved prematurely.
- `@Lazy` cannot fix an **actual dependency cycle** or business logic that triggers itself at startup.
- If the bean does not exist, a lazy proxy may still be injected, and the error surfaces only **when actually accessed**. Proper startup validation/tests are needed.
- The goal is reducing the chance of creating dependencies before the post-processor system is ready, not an absolute promise that every configuration is always safe.

### 5.2. ObjectProvider to Defer Resolution

`ObjectProvider<T>` carries a **lookup handle** instead of forcing the container to fetch the target when the constructor runs:

```java
package com.example.demo;

import java.util.concurrent.Executor;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class ProviderAsyncConfig implements AsyncConfigurer {
    private final ObjectProvider<Executor> executors;

    public ProviderAsyncConfig(
            @Qualifier("reportExecutor") ObjectProvider<Executor> executors) {
        this.executors = executors;
    }

    @Override
    public Executor getAsyncExecutor() {
        return executors.getObject();
    }
}
```

This is also an **alternative configuration option** meant only for a project that already declares a `reportExecutor` bean; do not enable multiple `AsyncConfigurer` classes simultaneously without intent. In the configuration above:

- The constructor only accepts the provider; it does not call `getObject()` directly there.
- Only when `getAsyncExecutor()` is invoked does `getObject()` request the real bean; this **defers resolution timing** compared to eager constructor injection.
- **Do not assume `getAsyncExecutor()` always runs "after all post-processors have finished"** across all versions/scenarios. If the framework or other code invokes the hook early, the provider will also resolve early.
- A provider is helpful when you want explicit optional/lazy resolution; however, if you only need to route specific methods, a dedicated executor bean plus `@Async("reportExecutor")` is usually simpler and has less coupling.

**Quick comparison of the options:**

| Approach | When Is the Target Fetched? | What to Watch Out For |
| --- | --- | --- |
| Inject `Executor` directly | Eagerly when creating the configurer unless lazy | Can pull in early initialization |
| `@Lazy` at injection point | Proxy first, target on first use | Using the proxy too early still creates the target early |
| Inject `ObjectProvider<Executor>` | Provider first; target when `getObject()` is called | Do not call `getObject()` in the constructor |
| Dedicated executor bean + `@Async("name")` | Container manages the bean and selects via qualifier | Usually does not require `AsyncConfigurer` |

### 5.3. Why Putting @Lazy Only on the Service Class May Not Be Enough

In Spring, a **lazy bean definition** is normally created only on demand. Yet if a **non-lazy** singleton requires that dependency to satisfy its constructor, Spring must create the dependency to fulfill injection. Thus:

```java
@Lazy
@Service
class ExpensiveService {
    // Not guaranteed to stay deferred if another eager singleton demands it right away.
}
```

Merely placing `@Lazy` on the bean class does not solve every eager dependency chain. Conversely, `@Lazy` on a **constructor parameter** can supply a proxy at the injection point and decouple receiving the reference from creating the target. Still, **using the proxy early will trigger target creation**.

Documentation: https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html

## 6. Runnable Java 17+: Visualizing "Capturing a Reference Too Early" vs. "Late Lookup"

The following plain Java example does not use Spring, yet it accurately models **the hazard of capturing a reference before an object is wrapped/decorated**. It does not reproduce Spring's exact `BeanPostProcessor`; it only isolates how references are obtained.

Save as **EarlyReferenceDemo.java**:

```java
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Supplier;

public class EarlyReferenceDemo {
    interface Worker {
        String work();
    }

    static final class RawWorker implements Worker {
        @Override
        public String work() {
            return "work";
        }
    }

    static Worker addAdvice(Worker target) {
        return () -> "advised(" + target.work() + ")";
    }

    public static void main(String[] args) {
        Worker raw = new RawWorker();

        // Eager: holds the reference before wrapping.
        Worker capturedTooEarly = raw;

        // Step simulating post-processing.
        AtomicReference<Worker> registry =
                new AtomicReference<>(addAdvice(raw));

        // Lazy: looks up only at usage time.
        Supplier<Worker> lazyLookup = registry::get;

        System.out.println("early=" + capturedTooEarly.work());
        System.out.println("lazy=" + lazyLookup.get().work());
    }
}
```

Compile/run:

```bash
javac EarlyReferenceDemo.java
java EarlyReferenceDemo
```

**Deterministic stdout:**

```text
early=work
lazy=advised(work)
```

**Analysis:**

- `capturedTooEarly` holds the exact `RawWorker`; subsequently putting a new wrapper into the registry **does not replace** the old reference.
- `lazyLookup` performs a lookup at usage time, retrieves the wrapper stored in the registry, and observes `advised(...)` behavior.
- `AtomicReference` here serves as the registry holder in the demo; Java provides appropriate visibility guarantees for `set/get`. However, the program runs single-threaded and is not meant to prove a concurrent algorithm.
- This is a **technical analogy**, not equating Spring's `ObjectProvider` with `AtomicReference`, nor claiming Spring will always create a "raw bean" just like the demo. Spring manages more complex lifecycle steps and proxies.
- Practical lesson: **do not let an early configuration class capture a dependency before wrapping/post-processing mechanisms can apply**.

## 7. Distinguishing Three Moments: Creating the Configurer, Fetching the Executor, and Running @Async

In practice, three actions can sit in different phases:

1. **Spring instantiates `AsyncConfigurer`** to read async infrastructure configuration.
2. **The `getAsyncExecutor()` hook supplies the executor** used as the default; actual executor resolution may be deferred depending on configuration.
3. **A caller invokes an `@Async` method through the proxy**, and the interceptor selects the executor and submits a task.

Diagram:

```text
BOOTSTRAP
  @EnableAsync
       |
       +-- Create AsyncConfigurer (can be very early)
       |        |
       |        +-- eager service injection: may pull service creation early
       |        +-- @Lazy/ObjectProvider: reduces coupling to target creation timing
       |
       +-- Set up async proxy infrastructure
       |
RUNTIME
  Bean A --> Bean B proxy --> @Async method --> executor --> worker
```

**Early initialization of `AsyncConfigurer` does not automatically mean `@Async` methods will run synchronously.** Conversely, a method running synchronously despite a properly configured pool may be due to **self-invocation** or bypassing the Spring proxy. These are **two distinct problems**.

## 8. Proxies and Self-Invocation: A Separate Issue Easily Misdiagnosed

With default `@EnableAsync` (proxy mode), only calls **passing through the Spring proxy** are handled by the interceptor. Example:

```java
@Service
public class ExampleService {
    public void outer() {
        inner(); // Internal call on the same instance, does not pass through proxy.
    }

    @Async("reportExecutor")
    public void inner() {
        System.out.println(Thread.currentThread().getName());
    }
}
```

This is a fragment; it requires an executor bean and `@EnableAsync` in the application. If `outer()` is called through the proxy and proceeds to call `inner()` via `this`, the internal call **is not intercepted by `@Async`** in proxy mode. This is **not** sufficient evidence to conclude `AsyncConfigurer` was initialized too early.

### How to Check Them Separately

- Call `@Async` from **another bean**, not `this.method()`.
- Verify the bean being called is a **Spring-managed bean**; do not instantiate `new Service()` and expect a proxy.
- Verify the executor name/qualifier, thread name prefix, and submission behavior.
- If suspecting early initialization, inspect the dependency graph, dependency cycles, bean creation timing, and proxy/advisor list.
- If suspecting self-invocation, extract the method into a dedicated Spring bean or deliberately use another interception strategy; **do not expect `@Lazy` to fix self-invocation by itself**.

The `EnableAsync` Javadoc emphasizes that `AdviceMode.PROXY` only intercepts calls passing through the proxy; `AdviceMode.ASPECTJ` uses a different weaving mechanism and requires separate dependency configuration. Do not switch to AspectJ just to hide dependency-graph issues before understanding the impact.

## 9. Spring-Managed Executors vs. Manually Created Executors Inside getAsyncExecutor

An official `@EnableAsync` example looks like:

```java
@Override
public Executor getAsyncExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("custom-");
    executor.initialize();
    return executor;
}
```

This is an illustrative fragment showing **how to manually create an executor inside the hook**. When you merely `new` and return it from this method **without declaring it as a Spring-managed bean**, the executor **does not automatically get full bean lifecycle management**. Therefore, watch out for:

- Manual `initialize()` when using a Spring-style executor outside the `@Bean` lifecycle.
- Shutdown/resource cleanup becomes application code's responsibility if the executor is not managed as a Spring bean.
- If Spring manages the executor via a normal `@Bean`, the container handles initialization and appropriate lifecycle; manual `initialize()` is unnecessary.
- `EnableAsync` documentation notes that you can annotate `getAsyncExecutor()` itself with `@Bean` to turn the returned executor into a managed bean. This is valid per the Javadoc, though you still need to understand dependencies and configurer initialization timing.
- It can be simpler to declare `@Bean("reportExecutor")` in a configuration class that **does not** implement `AsyncConfigurer` and reference it via `@Async("reportExecutor")`.

### Avoid Accidentally Calling @Bean Methods Like Regular Factories

The following can cause confusion if you do not understand `@Configuration(proxyBeanMethods = false)`:

```java
@Configuration(proxyBeanMethods = false)
class ExecutorConfig {
    @Bean
    ThreadPoolTaskExecutor reportExecutor() {
        return new ThreadPoolTaskExecutor();
    }

    ThreadPoolTaskExecutor anotherReference() {
        return reportExecutor(); // Direct Java call, creates a new instance.
    }
}
```

This is an **explanatory fragment**: with `proxyBeanMethods=false`, calling `reportExecutor()` directly as a normal Java method runs the body and creates a new object, **rather than retrieving the container-managed bean**. If you need the bean, **inject the bean** via constructor/qualifier or an appropriate provider. With full `@Configuration` using inter-bean proxying, behavior differs, yet relying on configuration proxy styles is not worth using as an opaque workaround for early initialization.

Do not return an uninitialized new executor on every hook call or create multiple untracked pools simply because a proper bean-lookup pattern is missing.

## 10. Exception Handlers Should Not Pull Complex Services into Bootstrap

`getAsyncUncaughtExceptionHandler()` handles exceptions from `@Async` methods returning `void`. It is also a hook in `AsyncConfigurer`. If the handler is built by eagerly injecting a complex logging/metrics service straight into the configurer's constructor, you still risk pulling the dependency graph up early.

A simple configuration can return a handler without depending on business beans:

```java
@Override
public AsyncUncaughtExceptionHandler
        getAsyncUncaughtExceptionHandler() {
    return (exception, method, params) -> {
        System.err.println(
                "Async void error in " + method.getName()
                + ": " + exception.getClass().getSimpleName());
    };
}
```

This is a **method fragment** to place inside an `AsyncConfigurer` class, requiring `org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler`. The example uses `System.err` for simplicity; production should use a proper logger/metrics while avoiding sensitive data.

If errors must be forwarded to another observability service, you can:

- Use a provider/lazy reference and resolve it only when **the handler is actually invoked**, not in the constructor.
- Avoid creating a dependency cycle between the exception handler, the executor, and the async infrastructure itself.
- Prefer methods returning `CompletableFuture<T>` when callers need results or exception handling. `AsyncUncaughtExceptionHandler` serves only `void`; it does not replace `Future.get()`/`whenComplete()`.

## 11. Dependency Cycles and Why @Lazy Is Not a Cure-All

A problematic graph can look like this:

```text
AsyncConfigurer
     |
     | eager requires
     v
AuditService (@Async / @Transactional)
     |
     | requires
     v
Executor or another configuration bean
     |
     +--------------------> AsyncConfigurer infrastructure
```

Such a cycle can lead to `BeanCurrentlyInCreationException` or hard-to-reason-about bootstrap state. Adding `@Lazy` sometimes avoids **creating the target right while stuck in the cycle**, yet it does not turn a circular dependency design into a good design.

Order of priority:

1. Separate executor beans from business services and async config infrastructure.
2. Ensure the executor **does not depend back** on services that use it.
3. Use explicit qualifiers when multiple executors exist.
4. Only when reference deferral is truly needed, use `@Lazy` at the injection point or `ObjectProvider`.
5. Avoid calling business services, querying DBs, publishing events, or starting tasks from `AsyncConfigurer`'s constructor.
6. If startup still has a dependency cycle, fix the dependency graph rather than blindly enabling circular references.

**An important consequence:** if an executor serves both requests and background work, do not make the executor constructor fetch an `@Async` service to set up its configuration. The executor is a dependency of services, not the other way around.

## 12. Common Misconceptions About @Lazy

| Claim | True or False? | Explanation |
| --- | --- | --- |
| "Putting `@Lazy` on a bean guarantees it is created only on the first request." | False | Another eager singleton may need it immediately at startup |
| "`@Lazy` at an injection point can create a proxy deferring target lookup." | True | Spring uses a lazy-resolution proxy for that dependency |
| "Calling a method through a lazy proxy in the constructor stays lazy." | False | Actual usage can force immediate resolution |
| "Injecting `ObjectProvider` means the target was already created." | False | The provider can be injected first, while the target resolves on lookup |
| "Calling `provider.getObject()` in the constructor still stays non-eager." | False | Calling `getObject()` is the exact moment the target is requested |
| "`AsyncConfigurer` initializes early, so all `@Async` calls will fail." | False | Problems arise when dependencies/proxies/lifecycles are mishandled |
| "`@Lazy` fixes `this.asyncMethod()` self-invocation." | False | Self-invocation bypasses the proxy in default mode |
| "An executor bean created via `@Bean` has a Spring-managed lifecycle." | Normally true | For a standard container-managed bean, Spring runs lifecycle callbacks |
| "An executor created with `new` inside the hook is automatically closed by the container." | False | It is not a Spring bean if you merely return an unregistered object |

Documentation on `@Lazy` injection points and eager dependency limits: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/annotation/Lazy.html

## 13. How to Diagnose an Application Suspected of Early Initialization

If after adding `AsyncConfigurer`, a service suddenly lacks advice or the context fails to start, analyze in order:

**Step 1 — Sketch a minimal dependency graph.** List beans directly depended on by `AsyncConfigurer`, executors, logging/metrics services, business services, and any reverse dependencies. The goal is finding paths that pull a service up before post-processors are ready.

**Step 2 — Confirm whether the configurer is the source of early creation.** Temporarily extract the executor into an independent `@Bean` and use `@Async("beanName")` on the call path under test. If the failure disappears, that is useful evidence of dependency/lifecycle coupling (though you still must understand the root cause rather than concluding from correlation alone).

**Step 3 — Inspect `BeanPostProcessor` warnings.** If logs mention "not eligible for getting processed by all BeanPostProcessors", check which bean was created early and which infrastructure piece requested it. Do not assume every warning is an AOP failure; treat them as signals to verify.

**Step 4 — Verify proxies on the call path.** Ensure the service is injected by Spring rather than created with `new`; check self-invocation and qualifiers. When needed, use `AopUtils.isAopProxy(bean)` or inspect proxies/advisors in tests, remembering that **not every bean must have an AOP proxy**.

**Step 5 — Test behavior, not just bean classes.** For `@Async("reportExecutor")`, record the thread name prefix from inside the method alongside `Future`/exception callbacks and cross-bean calls. For `@Transactional`, use a test with an explicit transaction boundary and verify commit/rollback rather than merely checking that an annotation exists.

**Step 6 — Distinguish startup errors from runtime errors.** Missing-bean/cycle errors during context refresh differ from workers running on the wrong thread at runtime. `@Lazy` can defer configuration errors until first use, so integration tests must exercise actual usage paths.

**Step 7 — Do not lose lifecycle management in the fix.** When splitting or replacing executors, confirm the pool initializes, shuts down cleanly, and keeps proper core/max/queue/rejection policies and exception handlers.

### A Practical Integration Test Checklist

In a Spring Boot integration test you can include:

- **Startup check:** `ApplicationContext` refreshes cleanly with `@EnableAsync`/executor beans.
- **Proxy check:** invoke `@Async` from another bean and confirm the thread name prefix/`Future` completion signal as expected.
- **Advice check:** if the service involved needs `@Transactional` or cache/security advice, verify through the advice's actual runtime behavior.
- **Lazy check:** ensure a deferred dependency is not invoked from constructors/configurers; instrument constructors or log in a test fixture to check creation count/timing when needed.
- **Failure check:** when the executor rejects tasks, submission exceptions must be handled; when a worker throws errors, `Future`/handlers must report via the expected path.
- **Shutdown check:** context closes and executor beans release resources properly.

Do not write tests that depend on log ordering across multiple workers. Use `CountDownLatch` or `CompletableFuture` to wait for deterministic states.

## 14. Common Mistakes

**Mistake 1 — Injecting a complex AOP service straight into `AsyncConfigurer`'s constructor.** Can force premature creation of the service. Prefer separate executor beans, lazy injection, or providers when genuinely needed.

**Mistake 2 — Putting `@Lazy` only on the service class and assuming all eager resolution is gone.** If an eager singleton needs the target, the container still has to satisfy that dependency; `@Lazy` placement matters.

**Mistake 3 — Calling `ObjectProvider.getObject()` right inside the configurer's constructor.** The provider can no longer defer resolution timing.

**Mistake 4 — Calling a method on a lazy proxy inside `@PostConstruct` during bootstrap.** The target can still be created prematurely on first access.

**Mistake 5 — Using `@Async("executorName")` when no executor bean has that exact name.** Executor-resolution failure differs from early-initialization issues.

**Mistake 6 — Calling `this.asyncMethod()` and blaming `AsyncConfigurer`.** Self-invocation bypasses advice under `AdviceMode.PROXY`.

**Mistake 7 — Defining a manually instantiated executor with `new` without initialize/shutdown.** Easily misses lifecycle callbacks and leaks threads on context close.

**Mistake 8 — Putting business logic or DB queries inside `getAsyncExecutor()`.** Infrastructure configuration hooks are not the place for business side effects.

**Mistake 9 — Making an executor depend on a service that uses that very executor.** Creates circular dependencies or unpredictable startup behavior.

**Mistake 10 — Believing that having an `AsyncConfigurer` guarantees every method uses it.** `@Async("qualifier")` can select a dedicated executor; inspect routing.

**Mistake 11 — Assuming `@Async void` throws exceptions back to an HTTP caller.** For `void`, use handlers/logs/metrics; for `Future`, callers must observe results/exceptions.

**Mistake 12 — Fixing startup by enabling circular references or disabling advice.** Masks symptoms while making the system harder to maintain; fix the graph and verify proxies instead.

**Mistake 13 — Creating multiple competing `AsyncConfigurer`s in one context.** Do not register multiple default-providing configurers without clear coordination; consolidate configuration or select executors by qualifier.

**Mistake 14 — Treating a single BPP warning as sole proof.** Combine stack traces, bean creation timing, and behavioral tests; do not infer that every proxy is broken.

## 15. Design Decisions by Need

| Need | Preferred Design Direction |
| --- | --- |
| One method needs a dedicated pool | `@Bean("specificExecutor")` + `@Async("specificExecutor")` |
| Multiple task groups need isolation | Multiple executor beans with explicit qualifiers |
| Want to choose a default executor for unqualified `@Async` | Bean following resolution rules or `AsyncConfigurer` when needed |
| Need a custom handler for `@Async void` | `AsyncConfigurer#getAsyncUncaughtExceptionHandler()`, avoiding early dependencies |
| Configurer must depend on complex beans | Consider `@Lazy` at injection point or `ObjectProvider`, avoiding early dereferencing |
| Need to use an AOP-proxied service inside configuration | Separate business logic from infrastructure; access only once context is ready |
| Task does not run async on internal calls within a class | Fix self-invocation/proxy boundary, do not just add `@Lazy` |
| Suspect `BeanPostProcessor` missed a chance to process | Check early dependency resolution and proxies/advisors via integration tests |
| Executor needs clean shutdown | Register as a Spring-managed bean; do not just return an unmanaged `new` object |

**Pragmatic rule:** if you do not need to override the default executor or global exception handler, **do not implement `AsyncConfigurer` merely to pick a thread pool for a group of methods**. Use named beans and qualifiers, eliminating most early-initialization configuration risks.

## 16. Self-Check Questions

**Question 1.** Why can a configuration class implementing `AsyncConfigurer` be instantiated before other business singletons?

**Answer:** Spring needs to read async infrastructure configuration during bootstrap. The `@EnableAsync` Javadoc warns that `AsyncConfigurer` configuration classes are initialized early; dependencies eagerly required at this stage may not yet have passed through all post-processors.

**Question 2.** Does injecting a service into `AsyncConfigurer`'s constructor guarantee `@Transactional` stops working?

**Answer:** No. It is a bootstrap-timing risk, not a "100% proxy loss" rule. Verify the dependency graph and bean behavior in the actual context.

**Question 3.** What is the difference between `@Lazy` on a bean class and `@Lazy` on a constructor parameter?

**Answer:** `@Lazy` on a bean definition seeks to defer creating the bean until first requested, yet another eager singleton can force its creation at startup. `@Lazy` at an injection point can supply a lazy-resolution proxy, deferring target retrieval until actual use.

**Question 4.** Does injecting `ObjectProvider<Executor>` and calling `getObject()` right inside the configurer constructor solve the problem?

**Answer:** No. You still request the target to be created at constructor time. The provider's benefit exists only when resolution is genuinely deferred until an appropriate time.

**Question 5.** A `this.runAsync()` call still runs on the caller thread even though the executor is configured properly. Does that prove `AsyncConfigurer` was initialized early and caused the bug?

**Answer:** No. In default `AdviceMode.PROXY`, self-invocation bypasses the proxy so the `@Async` interceptor does not run. That is a call-path issue, not proof of a bootstrap error.

**Question 6.** To make a `generate` method use the `reportExecutor` pool, what is the minimal approach?

**Answer:** Define `@Bean("reportExecutor")` with a `ThreadPoolTaskExecutor`, enable `@EnableAsync`, annotate `@Async("reportExecutor")`, and call the method through a Spring proxy. `AsyncConfigurer` is usually unnecessary.

**Question 7.** If `getAsyncExecutor()` creates `new ThreadPoolTaskExecutor()` and simply returns it, is the pool already a Spring-managed bean?

**Answer:** Not necessarily. If the object is only instantiated inside the hook, it does not automatically become a bean. Per the Javadoc, you can annotate the hook with `@Bean` for lifecycle management, or better yet, declare an explicit named `@Bean` executor separately.

**Question 8.** If the startup error disappears after adding `@Lazy`, is that enough to conclude the application is safe?

**Answer:** Not yet. The error may simply have been deferred until the target is first used. Write integration tests covering the `@Async` path, related proxies/advice, handlers, shutdown, and actual runtime behavior.

## Summary

- `AsyncConfigurer` customizes the default executor and the exception handler for `@Async void`.
- **Classes implementing `AsyncConfigurer` can be initialized very early by Spring**, so eager injection of complex beans can cause lifecycle and post-processing/proxy issues.
- **`@Lazy` at injection points** or **`ObjectProvider`** helps defer target resolution, yet loses effectiveness if the target is accessed right inside constructors/initialization phases.
- For typical needs, **declaring the executor as a Spring-managed bean and selecting it via `@Async("beanName")`** is simpler, clearer, and avoids coupling to early configurers.
- Self-invocation, executor selection, AOP proxy creation, and early initialization are **separate concerns to distinguish**, not lump into one error.
- Verify with integration tests covering **lifecycle + proxies + worker execution + exceptions + shutdown**, rather than merely checking annotations or thread names.

## References

1. Spring Framework 6.2 Javadoc – `@EnableAsync`, early initialization warning for `AsyncConfigurer` and `@Bean` on `getAsyncExecutor()`: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html
2. Spring Framework Javadoc – `AsyncConfigurer`: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/annotation/AsyncConfigurer.html
3. Spring Framework – Task Execution and Scheduling, `TaskExecutor` and `@Async`: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
4. Spring Framework – Lazy-initialized Beans: https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html
5. Spring Framework – `@Lazy` injection points: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/annotation/Lazy.html
6. Spring Framework – AOP proxying mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html

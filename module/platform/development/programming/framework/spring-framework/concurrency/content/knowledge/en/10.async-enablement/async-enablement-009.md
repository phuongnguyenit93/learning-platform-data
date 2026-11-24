# Role of `AsyncAnnotationBeanPostProcessor` in Spring Framework

## Objectives

Writing `@Async` on a method is **not enough** for execution to automatically switch to another thread. Spring must detect the annotation on a managed bean, create or enhance an AOP proxy, and attach logic that routes invocations to an executor. In `@EnableAsync`'s default mode, the key piece of infrastructure at this stage is **`org.springframework.scheduling.annotation.AsyncAnnotationBeanPostProcessor`**.

This lesson explains precisely **when** the processor runs, **what components** it produces, and distinguishes its responsibility from actually **submitting and executing tasks**. After studying it, you can:

1. Trace the path from `@EnableAsync` to registering `AsyncAnnotationBeanPostProcessor`.
2. Explain why the `BeanPostProcessor` attaches `AsyncAnnotationAdvisor` to proxies of beans with `@Async`.
3. Distinguish bean processing at initialization from interception when a method is called.
4. Trace executor selection, `Future`/`CompletableFuture` creation, and `void`/exception handling.
5. Know the limits of proxy mode: self-invocation, objects created with `new`, unproxiable methods, JDK/CGLIB proxy types, and application context scope.
6. Run a Java 17+ example verifying the infrastructure processor is registered, the service is an AOP proxy, and the logic runs on the chosen executor.

**One sentence to remember:** `AsyncAnnotationBeanPostProcessor` **sets up the asynchronous routing path for Spring beans**; it is **not a thread pool** and does not execute individual tasks itself. When the application invokes a method through the proxy, the interceptor/advice is what submits the call to an executor.

## 1. Three Phases That Are Easily Confused

To understand `@Async`, separate three phases:

| Phase | Participating Components | What Happens |
| --- | --- | --- |
| **Configuration declaration** | `@Configuration`, `@EnableAsync`, `AsyncConfigurationSelector`, `ProxyAsyncConfiguration` | Spring imports async infrastructure configuration and registers the bean processor in the target context. |
| **Bean initialization** | `AsyncAnnotationBeanPostProcessor`, `AsyncAnnotationAdvisor`, AOP proxy infrastructure | As Spring beans are processed, the processor attaches the async advisor to an existing proxy or creates a proxy if the bean has eligible annotations. |
| **Method invocation time** | Caller, AOP proxy, async interceptor, `Executor`/`TaskExecutor`, worker | The interceptor receives the call via the proxy, resolves the executor, and submits the work; only then does the worker run the method body and handle results/errors. |

You can visualize it as:

```text
          INITIALIZING APPLICATION CONTEXT
@Configuration + @EnableAsync
       |
       v
AsyncConfigurationSelector (proxy mode)
       |
       v
ProxyAsyncConfiguration registers AsyncAnnotationBeanPostProcessor
       |
       v
Bean created -> BeanPostProcessor inspects @Async
       |
       v
Bean proxy has AsyncAnnotationAdvisor/async advice
       |
       +--------- WAITING FOR ACTUAL CALL ------------+
                                                      |
             AT RUNTIME                               v
Caller -> service proxy -> async interceptor -> select executor
                                        |
                                        v
                                 submit invocation
                                        |
                                        v
                                worker runs method
                                        |
                                        v
                              value / error / completion
```

The processor does not schedule periodic tasks, does not invoke methods immediately at context startup, and does not create one thread per bean by default. Work is dispatched only when an eligible call goes through the proxy.

## 2. How Does `@EnableAsync` Register the Processor?

In the Spring Framework, `@EnableAsync` activates support for annotation-driven asynchronous method execution for **the application context where it is declared**.

Minimal configuration:

```java
@Configuration
@EnableAsync
public class AsyncConfiguration {
}
```

This is a configuration snippet within a Spring project, not a standalone program. In `AdviceMode.PROXY` (the default), `@EnableAsync` imports `AsyncConfigurationSelector`; the selector picks the `ProxyAsyncConfiguration` infrastructure configuration, which in turn registers an `AsyncAnnotationBeanPostProcessor`.

In this setup, the processor has an **internal** bean name used by Spring, corresponding to a constant in `TaskManagementConfigUtils`. The internal name is handy for debugging the container, though business code should not depend on infrastructure bean names when all it needs is `@Async`.

Conditions to keep in mind:

- `@EnableAsync` must be processed via configuration in the **right application context**. If a system has a root context and multiple servlet child contexts, enabling it in one context does not automatically enable the others.
- When using Spring Boot, specific auto-configuration can vary by project; never assume async is enabled merely because `spring-context` is a dependency or annotations exist on a service.
- `@EnableAsync` **creates no business logic** and does not turn every method async. Only beans with eligible annotated methods receive the corresponding advisor.
- `@EnableAsync(mode = AdviceMode.ASPECTJ)` chooses a different processing mode requiring `spring-aspects` and weaving; in that mode, call interception does not rely on AOP proxies built by the proxy-mode bean post-processor. Do not require `AopUtils.isAopProxy` as a mandatory check for AspectJ mode.

Similar names, different responsibilities:

| Component | Role |
| --- | --- |
| `@EnableAsync` | Enables and configures annotation-driven async processing. |
| `AsyncConfigurationSelector` / `ProxyAsyncConfiguration` | Selects and registers infrastructure beans in proxy mode. |
| **`AsyncAnnotationBeanPostProcessor`** | Detects async annotations on Spring beans and attaches the advisor/proxy to the call path. |
| `AsyncAnnotationAdvisor` | Pairs the pointcut identifying which calls to intercept with the advice executing async logic. |
| `AnnotationAsyncExecutionInterceptor` | Advice/interceptor that resolves the executor from the annotation and submits the invocation for execution. |
| `Executor` / `TaskExecutor` | Actually executes or dispatches tasks to workers according to a specific policy. |

Class names and responsibility splits in this table reflect Spring Framework 6.2 infrastructure; this is knowledge for reading execution flow, not a requirement for every application to instantiate infrastructure classes manually.

## 3. What Does the BeanPostProcessor Do When a Bean Is Initialized?

`BeanPostProcessor` is a Spring IoC container extension point allowing beans to be processed while the container creates and configures them. `AsyncAnnotationBeanPostProcessor` extends AOP post-processing infrastructure, so its primary job is **equipping proxies/advisors**, not running business methods.

Given a bean like:

```java
@Service
public class EmailService {
    @Async("mailExecutor")
    public CompletableFuture<String> send(String address) {
        return CompletableFuture.completedFuture("accepted:" + address);
    }
}
```

This is a **single-class example** in an application that already has `@EnableAsync`, `@Service` scanning, and a `mailExecutor` bean; not a standalone runnable Java file.

Before the application ever calls `send`, Spring has typically already:

1. Created the target instance of `EmailService` from its bean definition.
2. Passed the bean through the post-processor chain during container initialization.
3. Let `AsyncAnnotationBeanPostProcessor` build an `AsyncAnnotationAdvisor` matching annotations on the class or methods.
4. Added the advisor to an existing AOP proxy or created a proxy for eligible beans; the object injected by the application is usually the **proxy reference**.
5. Returned the processed bean to injection points or `ApplicationContext.getBean(...)`.

In simple cases where `EmailService` declares no interface, Spring may use a class-based proxy. If it implements an interface and default settings favor JDK proxies, the returned object may expose only the service's interface. Therefore, when debugging, do not assume `getBean(ConcreteClass.class)` always succeeds in applications using JDK dynamic proxies.

Merely **having the annotation in source code** does not guarantee interception. The annotation must be recognized by Spring infrastructure on a genuinely managed bean, with a method eligible for proxying/interception.

### Does the Processor Rewrite the Original Method's Code?

No. In proxy mode, the processor does not rewrite the business method's bytecode. It builds an **intermediary call path**: the client calls the proxy, the advisor/interceptor handles it and delegates the work. The target object still holds the original logic.

Brief model:

```text
Client
  |
  v
Proxy (advisor attached during bean initialization)
  |
  +--- async advice: creates task and submits to executor
                                  |
                                  v
                           Target.method(...)
```

This separation explains why `this.send(...)` inside the same target does not pass back through the proxy.

## 4. `AsyncAnnotationAdvisor` and the Interceptor: The Bridge to Runtime

`AsyncAnnotationAdvisor` combines two AOP elements:

- **Pointcut**: decides which beans/methods match `@Async` or a custom async annotation.
- **Advice**: logic executed when a matching call passes through the proxy, including resolving the executor, creating the task, and dispatching the work.

Spring uses `AnnotationAsyncExecutionInterceptor`, a specialization of `AsyncExecutionInterceptor`, to read `@Async`'s qualifier and determine the right executor.

Example:

```java
@Async("reportExecutor")
public CompletableFuture<Report> renderReport(String id) {
    // Actual processing runs on the selected executor.
}
```

This is an illustrative method declaration, not a standalone Java program; `Report` and the implementation body are supplied by the application.

When a caller invokes the method through the proxy, the execution path typically includes:

1. The interceptor receives `MethodInvocation` instead of immediately calling the target.
2. From the annotation, it selects `reportExecutor` or the configured default executor mechanism.
3. It creates a task wrapping the target invocation.
4. It submits the task to the executor; the caller receives the return handle per the async contract.
5. A worker executes the real method, then completes the result or captures errors for the caller/handler to observe.

**The processor does not directly pick a thread each time**; pool selection can be configured via `AsyncConfigurer`, bean name on `@Async`, or defaults, while the executor itself controls workers, queues, and rejection policies.

If you use a synchronous `Executor` like `Runnable::run`, or `CallerRunsPolicy` when a pool saturates, a call can run on the caller even though it passed through the async proxy. Thus **a proxy having an advisor** and **executing on another thread** are two claims that must be verified separately.

## 5. Runnable Example: Verifying the Processor, Proxy, and Worker

The following example runs with **JDK 17+**, Maven, and **Spring Framework 6.2.12**. It verifies three distinct layers:

1. Spring registered `AsyncAnnotationBeanPostProcessor`.
2. The service bean retrieved from the context is genuinely an AOP proxy.
3. Calling `@Async("lessonExecutor")` runs the method body on a worker of the executor prefixed with `lesson-`, not the caller thread.

Directory structure:

```text
async-bpp-demo/
├── pom.xml
└── src/main/java/demo/AsyncBppDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>async-bpp-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>demo.AsyncBppDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/AsyncBppDemo.java`:

```java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.AsyncAnnotationBeanPostProcessor;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class AsyncBppDemo {

    public record WorkResult(String value, Thread executedBy) {
    }

    // Public non-final class and public non-final method so
    // class-based proxy can intercept invocations through the Spring bean.
    public static class WorkService {
        @Async("lessonExecutor")
        public CompletableFuture<WorkResult> process(String input) {
            return CompletableFuture.completedFuture(
                new WorkResult(
                    "done:" + input,
                    Thread.currentThread()
                )
            );
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class AppConfig {
        @Bean
        public WorkService workService() {
            return new WorkService();
        }

        @Bean("lessonExecutor")
        public ThreadPoolTaskExecutor lessonExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(4);
            executor.setThreadNamePrefix("lesson-");
            return executor;
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            // Proves infrastructure BPP was registered by @EnableAsync.
            boolean processorRegistered =
                context.getBeanNamesForType(
                    AsyncAnnotationBeanPostProcessor.class).length > 0;

            WorkService service = context.getBean(WorkService.class);
            boolean proxied = AopUtils.isAopProxy(service);
            Thread caller = Thread.currentThread();

            CompletableFuture<WorkResult> handle = service.process("A");
            WorkResult result = handle.get(5, TimeUnit.SECONDS);

            System.out.println("processorRegistered=" + processorRegistered);
            System.out.println("serviceProxied=" + proxied);
            System.out.println("differentThread="
                + (result.executedBy() != caller));
            System.out.println("namedExecutorWorker="
                + result.executedBy().getName().startsWith("lesson-"));
            System.out.println("value=" + result.value());
        }
    }
}
```

Run from the `async-bpp-demo` directory with JDK 17+ and Maven:

```bash
mvn -q compile exec:java
```

The five lines **printed by the program** on a normal run are:

```text
processorRegistered=true
serviceProxied=true
differentThread=true
namedExecutorWorker=true
value=done:A
```

### Why Is the Output Predictable?

- `@EnableAsync` sits on `AppConfig`, which is registered in `AnnotationConfigApplicationContext`. Spring registers the async BPP when starting the context.
- The `WorkService` bean is created via `@Bean` and has a public `@Async` method. The BPP infrastructure adds an advisor and creates a proxy (class-based since this service has no interface).
- `AopUtils.isAopProxy(service)` inspects the actual object returned to the caller; it is a proxy.
- The caller invokes `service.process("A")` through the proxy, and the interceptor submits the work to the `lessonExecutor` bean.
- `ThreadPoolTaskExecutor` in the example uses workers prefixed with `lesson-` and does not use `CallerRunsPolicy`; thus the worker runs the method on a thread other than the caller.
- `WorkResult` stores a `Thread` reference solely for verification in this lesson. In real business code, return domain data rather than leaking `Thread` to clients.
- `handle.get(5, SECONDS)` waits if incomplete and returns the result, so the five lines print in a fixed order. This is a **caller timeout when reading the result**, not an execution time limit enforced by the BPP itself.

If the environment fails to resolve dependencies, the executor closes before accepting the task, or the 5-second timeout expires, the program may throw an error instead of printing these exact five lines. The output above describes a successful run, not a scheduler timing guarantee.

### What If `@EnableAsync` Is Removed?

In an application with only self-declared configuration like this example and no other async mechanism, Spring will not register the BPP via `@EnableAsync`; the annotated method is simply an ordinary Java method. The caller can directly execute `process`'s body and receive an already-completed `CompletableFuture.completedFuture` on the caller thread. Merely seeing a `CompletableFuture` return type is not enough to conclude async processing is active.

## 6. Boundaries of Proxy Mode

### A. Self-Invocation: Calling `this.method()` Bypasses the Proxy

Illustrative example:

```java
@Service
class InvoiceService {
    public CompletableFuture<String> generate() {
        // this points to target object, does not go through async proxy.
        return sendAsync();
    }

    @Async("invoiceExecutor")
    public CompletableFuture<String> sendAsync() {
        return CompletableFuture.completedFuture("sent");
    }
}
```

This snippet is an illustrative class in an application with an `invoiceExecutor` bean and `@EnableAsync`, not a standalone program. Calling `generate()` externally through the proxy enters the target, and the target calls `sendAsync()` via `this`; the **internal call** does not go through the interceptor, even though `sendAsync` carries `@Async`.

The usual fix is extracting `sendAsync()` into another Spring bean, injecting that bean, and calling it through the bean reference. Avoid injecting a proxy into itself just to work around self-invocation if you can organize cleaner service boundaries instead.

### B. Objects Created With `new` Bypass the BeanPostProcessor

```java
WorkService direct = new WorkService();
direct.process("A");
```

This snippet assumes the example's `WorkService` class. The `direct` object created with `new` is not processed by `ApplicationContext`, so the BPP attaches no AOP proxy to it. The method runs directly on the caller and `@Async` has no effect on the call. Only retrieving the object via `context.getBean(...)` or proper Spring bean injection gives proxying a chance to apply.

### C. Which Proxy Type and Which Methods Can Be Intercepted?

| Situation | Key Point to Remember |
| --- | --- |
| Bean implements an interface, default interface-based proxy | JDK dynamic proxy exposes the interface; clients should inject/call through the valid interface. |
| Bean has no suitable interface or `proxyTargetClass=true` is forced | A class-based proxy may be used, requiring the class/method to be eligible for subclassing/overriding. |
| `private` method | Cannot be called externally through a proxy in the way annotation AOP expects. |
| `final` method on a class-based proxy | Cannot be overridden to intercept; the annotation does not make it async. |
| `final` class needing a class-based proxy | Cannot be subclassed normally; proxy creation may fail. |
| Constructor, internal calls during lifecycle setup, or `@PostConstruct` methods | Not post-initialization application proxy call sites; do not expect the annotation to switch executors. |
| `@Async` on a method declared inside a `@Configuration` class | Not a Spring-recommended/supported placement. Place async business logic in service beans. |

`@EnableAsync(proxyTargetClass = true)` forces class-based proxies in proxy mode, which can also affect other AOP beans in the same context. Changing proxy mode requires checking injection/interface compatibility, especially when the system already uses `@Transactional`, security, or caching.

### D. Application Context Scope

`@EnableAsync` applies within its respective context. A root context and a servlet child context may have separate bean scopes/proxy infrastructure. Inspect the context actually managing the service rather than merely seeing the annotation declared in another configuration.

### E. Synchronous Execution From a Special Executor

Even when `AopUtils.isAopProxy(service) == true`, running on a worker distinct from the caller still depends on the executor. A direct executor like `Runnable::run` can execute tasks right on the caller. With `CallerRunsPolicy`, a saturated pool can also force the caller to run the task itself. The existence of the BPP/proxy **does not prove** every call achieves real concurrency.

## 7. The Processor Does Not Decide All Async Configuration

### Choosing an Executor per Method or by Default

In business code, `@Async("mailExecutor")` and `@Async("reportExecutor")` make clear which pool serves each workload type. The interceptor uses this qualifier when resolving the matching executor. If the bean name does not exist, errors can arise at invocation time.

`AsyncConfigurer` is a Spring-supported configuration interface for supplying a default executor and `AsyncUncaughtExceptionHandler`. When no qualifier is present, Spring applies executor lookup rules for the current setup: such as a matching `TaskExecutor` bean, an `Executor` bean named `taskExecutor`, or a version/condition-dependent fallback. **Do not rely on thread names or default pools without verifying which bean is selected.**

`AsyncAnnotationBeanPostProcessor` exposes configuration points such as `setExecutor(...)`, `setExceptionHandler(...)`, and `setAsyncAnnotationType(...)`; these are for infrastructure customization. In ordinary applications, using `@EnableAsync`, configuring `AsyncConfigurer`, or declaring explicit executor beans is simpler and easier to control than manually constructing a second processor.

### Does `@EnableAsync` Support Other Annotations?

In Spring configuration, defaults can recognize Spring's `@Async`, Jakarta/EJB async annotations when the corresponding dependencies are present, or a custom annotation type configured via `@EnableAsync`'s `annotation` attribute. Adding a custom annotation only helps when the advisor is explicitly configured to recognize that annotation; it is not an arbitrary mechanism that catches every annotation.

Configuration syntax example:

```java
@EnableAsync(annotation = MyAsync.class)
@Configuration
class CustomAsyncConfig {
}
```

This is **illustrative configuration code**; `@interface MyAsync`, imports, and proper runtime conditions are required. Do not assume a custom annotation automatically behaves identically to `@Async("executorName")` in qualifier resolution.

### Ordering With Other AOP Advices

An async bean may simultaneously carry transaction, cache, authorization, or tracing advice. According to the Javadoc, `AsyncAnnotationBeanPostProcessor` is ordered at the end of the BeanPostProcessor chain by default so it can add the async advisor onto an already-proxied bean; the async advisor is typically placed before existing advisors so work is handed off to the executor early.

That **does not replace checking actual advice order** when multiple proxies or custom configurations exist. In particular, a transaction bound to the caller thread **does not automatically carry over to the worker**. For business logic needing a transaction inside a task, establish transaction boundaries on the execution side, verify proxy/advisor selection, and design proper failure handling; do not just stack `@Transactional` and `@Async` assuming a guaranteed order.

## 8. How Does the Processor Relate to Results and Exceptions?

`AsyncAnnotationBeanPostProcessor` equips advisors/proxies **during bean initialization**; it does not complete work in place of the executor. **When the method is called**, the interceptor resolves the executor, submits the invocation, and handles outcomes according to the return type:

| Outcome Type / Situation | Actual Observation Point |
| --- | --- |
| `CompletableFuture<T>` or `Future<T>` | Handle from proxy; completion/exception observed by caller |
| `@Async void` throws error on worker | `AsyncUncaughtExceptionHandler`, logs/metrics |
| Executor missing or rejects task | Failure on resolution/submission path, possibly before caller receives a Future |
| Caller times out or cancels | Does not automatically guarantee the worker stops or side effects roll back |

Short API example on a service bean: `@Async("lessonExecutor") public CompletableFuture<String> compute()` can return `CompletableFuture.completedFuture("ok")` **on the worker**; the caller receives the handle provided by the proxy. Do not infer the method ran synchronously on the caller just because the target built a completed future. For details on `get/join`, `thenCompose`, cancellation, or error paths, see the return type contracts; the goal here is distinguishing the processor's job from the interceptor and executor.

## 9. Comparison With `ScheduledAnnotationBeanPostProcessor`

The two classes have similar names, yet different activation mechanisms:

| | `AsyncAnnotationBeanPostProcessor` | `ScheduledAnnotationBeanPostProcessor` |
| --- | --- | --- |
| Typical annotation | `@Async` | `@Scheduled` |
| Normal enablement | `@EnableAsync` | `@EnableScheduling` |
| Purpose | Attaches interceptor/proxy to offload **caller-initiated method calls** to an executor. | Detects scheduled methods and **registers scheduled tasks** with a scheduler. |
| When does work start? | When a caller invokes through the advisor-backed proxy. | When fixed rate / fixed delay / cron schedule conditions come due. |
| Runtime arguments from caller? | Yes, callers invoke the method with normal arguments. | Scheduled methods are invoked on a schedule and do not take dynamic arguments from callers that way. |
| Execution component | Selected `Executor`/`TaskExecutor`. | `TaskScheduler` and appropriate scheduling configuration. |

Thus the claim "Spring has a BeanPostProcessor, so it must scan and run all async methods by itself" is false. The async processor builds the **call interception path**, whereas the scheduler actively registers **when work fires**.

## 10. Diagnostic Workflow When `@Async` Doesn't Work

Proceed in order to pinpoint where the fault lies:

1. **Is the bean created by Spring?** Verify `ApplicationContext` holds the bean and the application invokes the reference injected/retrieved from the context; avoid manually `new`-ed objects.
2. **Has that context enabled async?** Check `@EnableAsync` in the active configuration; in proxy mode you can check for the presence of an `AsyncAnnotationBeanPostProcessor` bean.
3. **Is there a proxy/advisor?** Use `AopUtils.isAopProxy(bean)` in proxy mode and check proxy type. If the service uses an interface/JDK proxy, check interface-based injection.
4. **Is the method interceptable?** Check `public`, non-`final` for class proxies, proper annotation on class/method, and no calls via `this`.
5. **Which executor is actually chosen?** Check `@Async("...")`, bean names, `AsyncConfigurer`, `threadNamePrefix`, and executor type. Watch out for a direct executor or `CallerRunsPolicy`.
6. **Did the call truly go through the proxy?** Log caller thread at submission and worker thread inside the method; compare names/IDs. Never rely solely on the method returning `CompletableFuture`.
7. **Did rejection or an in-task error occur?** Check submission exceptions, `Future` completion, `AsyncUncaughtExceptionHandler`, queue depth, and shutdown state.
8. **Is the caller blocking itself after submission?** Calling `get()`/`join()` right away makes external behavior look sequential even if the method actually ran on a worker.
9. **Is it relying on caller context?** `ThreadLocal`, MDC, security context, request scope, and transactions do not follow workers automatically. Use intentional propagation and clean up in `finally`.
10. **Are there multiple contexts or auto-proxy creators?** Inspect AOP ordering, proxy chains, transactions, and bean lifecycles in the actual runtime context.

A good check answers three separate questions: **is the processor registered, is the service proxied, and which executor is running the method**. Only one of the three being true is not enough to conclude all call paths are properly async.

## 11. Common Misconceptions

| Wrong Assumption | Why It's Wrong | How to Fix |
| --- | --- | --- |
| "Adding `@Async` makes the JVM open a thread automatically." | Annotations have no runtime interceptor without matching configuration/beans. | Enable `@EnableAsync` and call a Spring-managed bean through its proxy. |
| "`AsyncAnnotationBeanPostProcessor` is a thread pool." | It attaches AOP advisors/proxies; the executor is what accepts tasks. | Distinguish initialization from invocation. |
| "With `@EnableAsync`, every method becomes asynchronous." | Only calls matching the pointcut and passing through interception are handled. | Check annotations and proxy boundaries. |
| "The processor executes async methods when beans are created." | Bean post-processing only builds infrastructure. | Tasks run when callers invoke through the proxy. |
| "Self-invocation automatically switches to a worker." | `this` calls the target directly, bypassing the proxy in default mode. | Extract method to another bean or design proper AOP boundaries. |
| "A `new`-ed object with `@Async` still runs async." | No Spring post-processing occurred on that object. | Retrieve the bean via context/injection. |
| "Once the BPP is registered, every call runs on another thread." | A direct executor or CallerRuns can run on the caller. | Check delegate, saturation, thread logs, and outcomes. |
| "`CompletableFuture` guarantees it was async." | Could be a `completedFuture` created right on the caller. | Inspect proxy/executor instead of inferring from return type. |
| "`@Async` preserves the request thread's transaction." | Transaction context is usually thread-bound. | Design transactions inside the worker and check advice ordering. |
| "`@Scheduled` and `@Async` share one processor." | Scheduler and async advisor use distinct processors and mechanisms. | Distinguish `ScheduledAnnotationBeanPostProcessor` from the async BPP. |
| "Using `@Async void` throws exceptions at the call line." | Errors occur on the worker; callers have no future. | Configure an uncaught exception handler or return a completion handle. |
| "Adding multiple manual processors makes things faster." | Can duplicate proxies/advisors and make infrastructure hard to control. | Use one standard `@EnableAsync` setup and size executors properly. |

## 12. Self-Check Exercises

**Q1.** In proxy mode, what component is responsible for recognizing `@Async` on beans and attaching the corresponding advice?

**Answer:** `AsyncAnnotationBeanPostProcessor` applies `AsyncAnnotationAdvisor` to proxies of eligible beans. The executor is only used later when a call is handled by the interceptor.

**Q2.** Why does a bean with `@Async` still execute on the caller when instantiated with `new`?

**Answer:** The object was not post-processed by the IoC container and has no AOP proxy, so the annotation has no effect on direct Java calls.

**Q3.** What does `@EnableAsync` do, and does it start running all `@Async` methods at startup?

**Answer:** It registers async infrastructure for the context. The processor prepares proxies/advisors; methods only execute later when called through the interception path.

**Q4.** Does `this.sendAsync()` inside a proxied service pass through async advice?

**Answer:** In default proxy mode, no. That is self-invocation on the target; you must call through the Spring proxy from another bean or use a suitable interception mechanism.

**Q5.** A service is AOP-proxied and annotated `@Async("lessonExecutor")`, yet the task still runs immediately on the caller. Is the BPP definitely broken?

**Answer:** Not necessarily. The delegate executor might execute directly, or a saturation policy like `CallerRunsPolicy` may shift work back to the caller. Inspect the executor and invocation path.

**Q6.** Why can the example yield both `processorRegistered=true` and `serviceProxied=true`?

**Answer:** `@EnableAsync` registers the processor, and then the processor creates/enhances the AOP proxy for `WorkService` with its `@Async` method. The two values check two different stages.

**Q7.** Can an exception thrown from `@Async void` be caught via `Future.get()`?

**Answer:** No, because a `void` method returns no handle. You need `AsyncUncaughtExceptionHandler`, or change the method contract to `CompletableFuture<T>` when callers must track outcomes.

**Q8.** An application chooses `@EnableAsync(mode = AdviceMode.ASPECTJ)`. Is `AopUtils.isAopProxy(service)` returning `false` enough to conclude async isn't enabled?

**Answer:** No. AspectJ weaving does not rely on AOP proxies in the same way proxy mode does; inspect weaving, dependencies, and actual runtime behavior.

**Q9.** Are `@Scheduled` annotations on beans scheduled by `AsyncAnnotationBeanPostProcessor` itself?

**Answer:** No. Scheduling has its own infrastructure, typically `ScheduledAnnotationBeanPostProcessor` and `TaskScheduler`.

### Remember

Trace **configuration → bean post-processing → AOP proxy/advisor → method invocation → executor → completion**. `AsyncAnnotationBeanPostProcessor` belongs to the step of **building the call interception path for Spring beans**; the async interceptor handles invocations and hands work off to the executor. When debugging, verify each link in the chain rather than assuming the annotation alone guarantees parallel execution.

### Official References

- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html): enabling `@EnableAsync`, proxy mode, `@Async`, and executors.
- [Spring Framework — AsyncAnnotationBeanPostProcessor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/AsyncAnnotationBeanPostProcessor.html): processor, advisor, annotations, and exception handlers.
- [Spring Framework — EnableAsync Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html): enablement, context scope, proxy/AspectJ modes, and ordering.
- [Spring Framework — AsyncAnnotationAdvisor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/AsyncAnnotationAdvisor.html): pointcut/advice for async methods.
- [Spring Framework — AnnotationAsyncExecutionInterceptor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/AnnotationAsyncExecutionInterceptor.html): annotation-based executor selection and invocation dispatch.

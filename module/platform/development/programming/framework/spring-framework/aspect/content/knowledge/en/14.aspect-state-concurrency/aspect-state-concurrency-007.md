# Thread Switching, `@Async`, and Thread-Bound Context Limits in Spring AOP

## 1. Why Must a Spring Aspect Care About Thread Switching?

Spring AOP normally intercepts **method calls going through a Spring proxy**. `@Async` also uses proxies in its default mode: when a caller invokes an eligible method, the async interceptor submits the work to a `TaskExecutor`, while the caller immediately receives a `Future` / `CompletableFuture` or completes the `void` call. The method body executes later on a worker thread.

```text
CALLER THREAD                              EXECUTOR / WORKER THREAD
    |                                                |
    |  otherBean.work()                              |
    v                                                |
 Spring AOP proxy                                    |
    |                                                |
 Async advisor --------- submit(task) -------------->|
    |                                                | AOP @Around (target)
    | future returned                                |   -> @Before / target
    |                                                |   -> @AfterReturning
    |                                                | completes future
    +---------------- await/result <-----------------+
```

In typical Spring configurations, `AsyncAnnotationBeanPostProcessor` places the async advisor **before existing advisors** so thread switching occurs as early as possible. Consequently, an `@Around` applied **on the `@Async` method itself** usually runs on the worker; an `@Around` on the **caller method** runs on the caller. If the application uses multiple proxies, alters advisor ordering, or uses `@EnableAsync(mode = AdviceMode.ASPECTJ)`, you need to observe the actual execution path. `@Order` among `@Aspect` beans does not replace determining the async advisor's position.

**Distinguish:** (a) when the proxy submits the task; (b) when the method body runs; (c) when the `Future` completes. These three moments can occur on different threads.

## 2. Conditions for Activating `@Async` and Advice

1. Enable `@EnableAsync`, provide an appropriate executor, and optionally specify `@Async("workerExecutor")`. `@EnableAspectJAutoProxy` is required for your application's `@Aspect`; declaring an aspect alone does not enable `@Async` processing.
2. Beans must be Spring-managed and calls must **go through the proxy**. `this.work()` inside the same bean is a self-invocation, bypassing both the async advisor and proxy advice for that call. Extracting the async method into another bean is the simplest way to guarantee a proxy boundary.
3. Avoid applying proxy advice to `private` or `final` methods; CGLIB proxies cannot override `final` methods, and JDK proxies expose only interface APIs. `@Async` is not directly supported on lifecycle callbacks like `@PostConstruct`.
4. With `@Async`, appropriate return types include `void`, `Future<T>`, and `CompletableFuture<T>`. Methods returning async values can return `CompletableFuture.completedFuture(value)` inside the worker; the proxy provides the future for the caller to track execution.
5. Do not confuse `@Async` with a user-declared aspect: Spring uses `AsyncAnnotationAdvisor` / an interceptor to execute async behavior. In AOP methods, `ProceedingJoinPoint.proceed()` invokes the next step in the current interception chain.

### Advice placement determines what a measurement means

| Interception point | Thread that normally runs | What is actually measured |
| --- | --- | --- |
| `@Around` on the service **calling** the `@Async` method | Caller | Time to submit the task / caller processing |
| `@Around` on the **target** `@Async` method | Worker (outermost async advisor) | Target method execution time |
| `@AfterReturning` on caller receiving `CompletableFuture` | Caller | **Future received**, task not necessarily finished |
| `future.whenComplete(...)` | Thread completing the future or thread attaching callback if already done | Final outcome of the tracked stage |

If end-to-end measurement is needed, capture the start timestamp before submission and finish in `whenComplete`; do not conclude "business work finished" just because `@AfterReturning` ran.

## 3. Runnable Spring AOP Example on Java 17+

This example intentionally stores a request ID in a `ThreadLocal` on the caller. It proves the aspect runs on the worker yet **the request ID does not follow automatically**. Uses Maven and Spring Framework 6.2.x; no Spring Boot required.

Structure:

```text
async-aop-demo/
├── pom.xml
└── src/main/java/example/AsyncAspectDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>async-aop-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.8</version>
    </dependency>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-aop</artifactId>
      <version>6.2.8</version>
    </dependency>
    <dependency>
      <groupId>org.aspectj</groupId>
      <artifactId>aspectjweaver</artifactId>
      <version>1.9.22</version>
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
        <version>3.5.0</version>
      </plugin>
    </plugins>
  </build>
</project>
```

`src/main/java/example/AsyncAspectDemo.java`:

```java
package example;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class AsyncAspectDemo {
    static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

    @Configuration(proxyBeanMethods = false)
    @EnableAsync(proxyTargetClass = true)
    @EnableAspectJAutoProxy(proxyTargetClass = true)
    static class Config {
        @Bean
        ThreadPoolTaskExecutor workerExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(5);
            executor.setThreadNamePrefix("worker-");
            return executor;
        }

        @Bean WorkService workService() {
            return new WorkService();
        }

        @Bean TraceAspect traceAspect() {
            return new TraceAspect();
        }
    }

    static class WorkService {
        @Async("workerExecutor")
        public CompletableFuture<String> work() {
            System.out.println("target: " + Thread.currentThread().getName()
                    + ", request=" + REQUEST_ID.get());
            return CompletableFuture.completedFuture("seen:" + REQUEST_ID.get());
        }
    }

    @Aspect
    static class TraceAspect {
        @Around("execution(* example..*.work(..))")
        public Object around(ProceedingJoinPoint pjp) throws Throwable {
            System.out.println("advice before: "
                    + Thread.currentThread().getName()
                    + ", request=" + REQUEST_ID.get());
            Object result = pjp.proceed();
            System.out.println("advice after: "
                    + Thread.currentThread().getName()
                    + ", request=" + REQUEST_ID.get());
            return result;
        }
    }

    public static void main(String[] args) throws Exception {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            REQUEST_ID.set("REQ-42");
            try {
                System.out.println("caller request=" + REQUEST_ID.get());
                CompletableFuture<String> future =
                        context.getBean(WorkService.class).work();
                System.out.println("result=" + future.get(5, TimeUnit.SECONDS));
            } finally {
                REQUEST_ID.remove();
            }
        }
    }
}
```

Run from the `async-aop-demo` directory:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.AsyncAspectDemo
```

`stdout` with a single-worker executor named `worker-1`, advice on the worker, and no `ThreadLocal` propagation mechanism:

```text
caller request=REQ-42
advice before: worker-1, request=null
target: worker-1, request=null
advice after: worker-1, request=null
result=seen:null
```

`future.get(5, TimeUnit.SECONDS)` waits until the task finishes so the display order in the example is deterministic; no `sleep` is needed. `ThreadLocal` isolates values per thread, so the worker does not automatically receive `REQ-42`. This is **not** a bug in the `@Around` pointcut. If a different proxy/executor configuration is used, extra logs or different worker names may appear: observe the actual thread names.

## 4. Categorizing Context Across Executor Boundaries

| Context | Common mechanism | On a new worker or pooled thread |
| --- | --- | --- |
| Custom `ThreadLocal`, correlation ID, SLF4J MDC | Thread-bound value | Not automatically present; requires transfer and cleanup |
| `RequestContextHolder` (Spring MVC) | Thread-bound `RequestAttributes` | Not present by default; request may end before task runs |
| `LocaleContextHolder` | Thread-bound `Locale` | Not present by default; can pass a captured `Locale` |
| Spring Security's `SecurityContextHolder` | Thread-bound `SecurityContext` (default) | Not present automatically; requires dedicated security propagation |
| Imperative `@Transactional` transaction | Thread-bound `TransactionSynchronizationManager` | **Caller transaction does not follow to worker** |
| Micrometer observation / trace | Context snapshot and accessors | Propagated only when configured to support it |
| `Reactor Context` in WebFlux | Context of the reactive data stream | Not identical to `ThreadLocal`; needs a bridge if mixing models |

Context should not necessarily be copied wholesale. For background tasks outliving an HTTP request, parameters like a correlation ID, `Locale`, or validated business identifier are usually more durable and transparent than keeping `RequestAttributes` alive. Avoid passing request/session references, transaction resources, or overly broad credentials unnecessarily.

### The case of `@Transactional` and `@Async`

With `PlatformTransactionManager`, Spring binds imperative transactions to the **current thread**. When a caller inside `@Transactional` calls another bean with `@Async`, the worker **does not join the same transaction**; rolling back on the caller does not mean rolling back on the worker. If the worker needs a transaction, have a method running inside the worker go through a Spring transactional proxy to open a **separate** transaction. Do not copy internal `TransactionSynchronizationManager` ThreadLocals to the worker via a decorator.

### The case of `RequestContextHolder` and `InheritableThreadLocal`

`RequestContextHolder` has an optional inheritance mode, yet `InheritableThreadLocal` copies values only when **creating a child thread**, and does not reliably transfer them across a thread pool that **reuses** threads. It also easily leaks stale context to another task. Extract the needed immutable data before leaving the request; do not turn on inheritance mode to "fix" missing context in a pool.

## 5. Three Approaches Within Spring Aspect Boundaries

### Approach A: Pass explicit parameters

```java
@Async("workerExecutor")
public CompletableFuture<String> work(String requestId) {
    return CompletableFuture.completedFuture("seen:" + requestId);
}

// Caller on another bean: service.work("REQ-42");
```

This is an illustrative replacement inside the Spring bean above, **not** a standalone program. The parameter is immutable data, independent of schedulers or ThreadLocal. Appropriate when business signatures can be modified.

### Approach B: `TaskDecorator` captures/restores context for AOP

If your advice or logging library **must read a ThreadLocal**, attach a decorator to the **exact executor that `@Async` uses**. In the example's `Config`, replace the `workerExecutor()` bean with:

```java
@Bean
ThreadPoolTaskExecutor workerExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(1);
    executor.setMaxPoolSize(1);
    executor.setQueueCapacity(5);
    executor.setThreadNamePrefix("worker-");

    executor.setTaskDecorator(task -> {
        // Capture when the executor receives the task.
        String captured = REQUEST_ID.get();
        return () -> {
            // Worker may be reused: remember the previous state.
            String previous = REQUEST_ID.get();
            try {
                if (captured == null) REQUEST_ID.remove();
                else REQUEST_ID.set(captured);
                task.run();
            } finally {
                if (previous == null) REQUEST_ID.remove();
                else REQUEST_ID.set(previous);
            }
        };
    });
    return executor;
}
```

When rerun, both the advice and target see `request=REQ-42`, and the future yields `result=seen:REQ-42`. Mandatory rule: **capture at task submission → apply on worker → restore worker state in `finally`**. Never carry task A's state into task B when the pool reuses threads. For MDC, capture `MDC.getCopyOfContextMap()`, apply via `MDC.setContextMap(...)` or `MDC.clear()`, and restore the old MDC in `finally`. If using multiple decorators, compose them intentionally (e.g., `CompositeTaskDecorator`) to avoid overwriting each other.

### Approach C: Use built-in support for the right context type

- **Micrometer / Spring Framework 6.1+:** `org.springframework.core.task.support.ContextPropagatingTaskDecorator` can propagate observations/MDC/contexts that have a registered `ThreadLocalAccessor`. Example on an executor with the right dependencies: `executor.setTaskDecorator(new ContextPropagatingTaskDecorator());`. It **does not automatically understand arbitrary custom `ThreadLocal`s**. Spring Boot offers version-dependent context propagation auto-configuration options; when defining an executor manually, verify the decorator is actually installed.
- **Spring Security:** `org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor` wraps an `AsyncTaskExecutor` and restores `SecurityContext` during task execution. Illustrative example: `new DelegatingSecurityContextAsyncTaskExecutor(rawExecutor)`. Make the wrapper the actual executor used by `@Async` (e.g., bean `securedExecutor` and `@Async("securedExecutor")`); creating the wrapper while still dispatching to `rawExecutor` has no effect.

Both mechanisms above serve their supported context scopes; they **do not propagate caller transactions** and do not guarantee arbitrary custom contexts are copied. Test under high task counts and check capture/restore overhead.

## 6. Exceptions, Callbacks, and Chained Stages

**With `CompletableFuture`:** worker exceptions appear on the future; `get()` throws `ExecutionException` wrapping the cause and `join()` typically throws `CompletionException`. When `@Async` returns `void`, the caller usually cannot use `try/catch` around the call to catch worker errors; use `AsyncUncaughtExceptionHandler` to handle/log them. Submission errors when the executor rejects a task can surface immediately on the proxy call and need separate handling.

**When chaining stages:** `thenApply` can run on the thread completing the future or the thread attaching the callback if the future is already done; `thenApplyAsync` uses a separate executor or the default common pool. Thus the decorator on the `@Async` call **does not guarantee** subsequent stages receive the context. Pass values via parameters, or specify a decorated executor at each boundary where it is truly needed.

**With virtual threads:** using virtual threads does not make the caller's `ThreadLocal` automatically appear inside dispatched tasks. You still need to understand proxies and context propagation paths. Do not apply `InheritableThreadLocal` as a universal rule across executor types.

## 7. Issues to Recognize

| Symptom | Common cause | Check / fix |
| --- | --- | --- |
| `@Async` runs on caller thread | `this.work()`, missing `@EnableAsync`, bean created via `new` | Call through bean proxy, log thread name |
| Aspect sees `ThreadLocal=null` | Caller context was not propagated | Use parameters or `TaskDecorator` |
| `@AfterReturning` runs before result is ready | Only observed returning the future | Measure with `whenComplete` |
| Task B carries task A's trace/user | Forgot to restore context on pooled thread reuse | Always use `finally`, test 2 sequential tasks |
| Request/locale missing or invalid | Context tied to request/thread lifecycle | Extract needed data before submitting |
| Worker transaction doesn't roll back with caller | Imperative transactions are thread-bound | Design independent transactions and handle business consistency |
| Worker throws yet caller misses it | `@Async void` has no future | `CompletableFuture` or `AsyncUncaughtExceptionHandler` |
| `@Order` fails to explain thread location | Async advisor/proxy order differs from assumption | Inspect actual advisors, log caller/advice/target |

A good test: a **single-worker** executor, set `REQUEST_ID` on the caller and submit task A, clear it on the caller and submit task B; with a decorator, task A receives ID A and task B must not receive ID A. Add a case where task A throws an exception to verify `finally` does not leak. Use `CompletableFuture` or `CountDownLatch` synchronization instead of guessing timing with `sleep`.

## 8. Key Takeaways

`@Async` creates an **execution boundary** when invoked through a Spring proxy; advice placement determines whether it runs on the caller or worker. ThreadLocal, MDC, request context, security context, and transactions have different lifecycles; do not assume they cross into thread pools. Prefer immutable parameters; when context must be passed to a Spring Aspect or library, use dedicated executors/decorators, restore state in `finally`, and test under thread reuse. Measure future completion time rather than mistaking it for when the method returned the future.

### Spring Documentation for Reference

- `@Async`, executors, and error handling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring AOP proxies and self-invocation: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Advice ordering: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- Thread-bound imperative transactions: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Async advisor before existing advisors: https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/scheduling/annotation/AsyncAnnotationBeanPostProcessor.html
- `ContextPropagatingTaskDecorator`: https://docs.spring.io/spring-framework/docs/6.1.2/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html
- Spring Security context and concurrency: https://docs.spring.io/spring-security/reference/features/integrations/concurrency.html

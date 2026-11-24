# Call Path from Caller Through Proxy to Asynchronous Task

## 1. The Core Question: Who Actually Executes an @Async Method?

In the Spring Framework, placing `@Async` on a method **does not automatically turn the method body into a new thread**. In the default mode, Spring uses an **AOP proxy** to intercept **calls going through the bean proxy**, selects an executor, wraps the method invocation into a task, and submits the task to the executor for execution.

Therefore, to accurately explain a `service.generateReport()` call, you must distinguish three objects and two execution segments:

1. **Caller**: a controller, service, or another component making the call.
2. **Spring proxy**: the bean object that the caller receives via dependency injection. It has the opportunity to intercept eligible calls and apply `@Async` handling.
3. **Target**: the object containing the actual method logic. On the normal asynchronous path, the target logic is invoked inside the task picked up by the executor.

Two execution segments:

- **On the caller thread**: enters the proxy, identifies an asynchronous call, selects an executor, submits the task, and returns control/a result handle.
- **On the worker thread** (for a thread-pool-based executor): picks up the task, invokes the target method, captures the result or exception, and completes the corresponding handle.

`@Async` changes **how an eligible call is routed**, not by defining new Java syntax. When a call **does not go through the proxy**, the annotation is not triggered by default and the method runs directly like a normal Java call.

## 2. Diagram of the caller → proxy → executor → worker → target Path

```text
Caller thread                            Executor / worker thread
-------------                            ------------------------
Controller / other bean
    |
    | 1. service.calculate(21)
    v
Spring-managed proxy
    |
    | 2. Async interceptor checks @Async
    | 3. Resolves executor (e.g., "asyncPool")
    | 4. Wraps target call into a task
    | 5. submit(task) -----------------------------------+
    |                                                   |
    | 6. Returns Future/CompletableFuture                v
    +----> caller continues                   Worker of asyncPool
                                                         |
                                                         | 7. invoke target
                                                         v
                                                   Target.calculate(21)
                                                         |
                                                         | 8. Computes result
                                                         v
                                                 Completes Future
                                                         |
    | 9. caller calls future.get() / callback <---------+
    v
Receives value / error / final state
```

The diagram is an **illustration of the typical processing flow**, not an assertion that every executor always creates a separate thread: if you intentionally configure a synchronous execution mechanism or replace the executor with an implementation that has a different policy, the threading characteristics will differ. Furthermore, the ordering between "caller continues" and "worker starts running" is a **thread-scheduling race**; the worker can finish very quickly right before the caller receives the handle.

The key takeaway remains: **passing through the proxy is the point that triggers the interceptor**, while the executor determines the actual execution schedule.

## 3. Conditions for a Call to Be Intercepted by the Proxy

An `@Async` call works under the proxy mechanism when the following necessary conditions are all satisfied:

1. **Async support is enabled**: typically by placing `@EnableAsync` on a Spring configuration. Merely adding `@Async` without enabling async processing may not produce the desired behavior.
2. **The target is a Spring-managed bean**: Spring has the opportunity to use bean post-processing to create/configure the proxy. Instantiating `new ReportService()` yourself outside the container will not automatically wrap it with this proxy.
3. **The caller invokes the proxy object**: typically received via constructor injection from the container, not calling a method in the same target via `this`.
4. **The method can be advised** according to the proxy type and application configuration: you should place `@Async` on a `public` business method called from another bean.
5. **The selected executor is valid and accepting tasks**: if the executor bean cannot be found, has been shut down, or is saturated, the call may fail during routing/submission.

Example of the right route:

```java
@Service
public class ApiService {
    private final ReportService reports;

    public ApiService(ReportService reports) {
        this.reports = reports; // Reference injected by Spring: may be a proxy.
    }

    public void handleRequest() {
        reports.generateReport(); // External call going through the proxy.
    }
}
```

This snippet is a **code fragment inside a Spring application**, requiring the beans and imports to be declared. It only illustrates the proxy entry point; see the sections below for a standalone runnable project and observing actual threads.

## 4. What Does the Proxy Create and Do When It Sees @Async?

Spring provides infrastructure for the `@Async` annotation: when `@EnableAsync` is enabled, the framework registers components that recognize eligible calls and attach async advice to suitable beans. In the default proxy mode (`AdviceMode.PROXY`), the advice is triggered when a caller invokes through the proxy.

Step by step on the caller thread:

1. The caller holds a reference to a bean. That reference looks like a normal Java object, but in reality it may be a proxy.
2. The call `service.method(args)` enters the proxy.
3. The async interceptor looks up the `@Async` policy, potentially retrieving the executor name from `@Async("beanName")`.
4. The interceptor wraps the target invocation into a task, instead of immediately invoking the target on the caller thread in the usual way.
5. The task is handed off to the chosen executor (an appropriate `Executor`/`AsyncTaskExecutor`), where it can start running or wait in a queue.
6. The proxy returns to the caller according to what the method's declared return type allows, without making the caller create threads itself.

Step by step on the worker thread:

1. The executor assigns a worker to pick up the task.
2. The task executes the necessary interceptor/target call chain.
3. The actual `@Async` method logic runs in the worker's environment. If it returns a `Future` or `CompletableFuture`, Spring can unwrap the corresponding result to complete the handle that the proxy returned to the caller.
4. The result, exception, or cancellation state is reflected through the handle or Spring's error-reporting mechanism.

**Do not imagine that "the proxy is the worker thread."** The proxy is the mechanism for *intercepting and routing* the call. The executor is the mechanism for *executing the task*. The target is where the *business logic* lives.

## 5. Runnable Spring Framework Example with Java 17+

This example uses plain Spring Framework (no Spring Boot required) and `ThreadPoolTaskExecutor`. It demonstrates obtaining the bean from the context by the caller through the proxy, and then the target method executing on a thread with the configured prefix.

Structure:

```text
async-call-path/
├── pom.xml
└── src/main/java/demo/AsyncProxyDemo.java
```

Contents of `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>async-call-path</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
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

Contents of `src/main/java/demo/AsyncProxyDemo.java`:

```java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncProxyDemo {

    @Bean("asyncPool")
    public ThreadPoolTaskExecutor asyncPool() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(1);
        pool.setMaxPoolSize(2);
        pool.setQueueCapacity(10);
        pool.setThreadNamePrefix("async-worker-");
        return pool;
    }

    @Bean
    public WorkService workService() {
        return new WorkService();
    }

    public record Answer(int value, String workerThread) {}

    public static class WorkService {
        @Async("asyncPool")
        public CompletableFuture<Answer> calculate(int number) {
            Answer result = new Answer(
                    number * 2,
                    Thread.currentThread().getName()
            );
            return CompletableFuture.completedFuture(result);
        }
    }

    public static void main(String[] args) throws Exception {
        try (var context =
                 new AnnotationConfigApplicationContext(AsyncProxyDemo.class)) {
            WorkService service = context.getBean(WorkService.class);
            String callerThread = Thread.currentThread().getName();

            CompletableFuture<Answer> future = service.calculate(21);
            Answer answer = future.get(5, TimeUnit.SECONDS);

            System.out.println("value = " + answer.value());
            System.out.println("worker name matches = "
                    + answer.workerThread().startsWith("async-worker-"));
            System.out.println("different thread = "
                    + !callerThread.equals(answer.workerThread()));
        }
    }
}
```

Run in the project directory with Maven and JDK 17+:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.AsyncProxyDemo
```

Stdout produced by the program:

```text
value = 42
worker name matches = true
different thread = true
```

Why is this output meaningful?

- `@EnableAsync` enables annotation processing in the context.
- `@Bean("asyncPool")` provides an executor with the thread name prefix `async-worker-`.
- `@Bean workService()` returns the target `WorkService`, after which Spring can provide a proxy to the caller. The caller **retrieves the bean from the context**, rather than directly instantiating `new WorkService()` outside.
- `service.calculate(21)` goes through the async advice because the `public` method has `@Async("asyncPool")`.
- The worker computes `21*2` and records its own thread name.
- `future.get(5, TimeUnit.SECONDS)` waits for the result, so the last line does not depend on whether the worker is faster or slower than the caller.
- The thread name check and the caller/worker comparison both evaluate to true: the target logic runs on a worker of the pool.

The example uses a Java 17 `record` and `CompletableFuture.completedFuture` inside the **target**. This does not mean the caller received a synchronously completed result: the Spring interceptor returns an **asynchronous handle** to the caller; `completedFuture` inside only matches the target method signature and delivers the result after the worker finishes computing. Do not use the handle creation time as proof that the target has already finished running.

To make it easy for readers to verify syntax, the example can be used directly with Spring `6.2.9` and JDK 17+. Behavior has been verified with JShell on Spring `6.2.9`: value 42 and both thread checks are `true`. When closing the context, Spring manages the executor's lifecycle; the service does not call `shutdown()` itself on the shared bean.

## 6. Critical Issue: Self-Invocation Bypasses the Proxy

Consider a bean with two methods:

```java
@Service
public class InvoiceService {
    public void createInvoice() {
        this.sendEmailAsync(); // Same-object call, bypasses the async proxy.
    }

    @Async("asyncPool")
    public void sendEmailAsync() {
        // Email sending logic.
    }
}
```

This is an **illustrative code fragment** requiring imports for `@Service`, `@Async`, and executor configuration. When `createInvoice()` is already running **inside the target**, `this.sendEmailAsync()` is a direct call within the same object; it does not pass through the proxy, so `@Async` **is not applied to this call** in the default proxy mode.

Comparison diagram:

```text
RIGHT:    OtherBean --> InvoiceService proxy --> async advice --> executor --> target.sendEmailAsync()

BYPASSED: OtherBean --> InvoiceService proxy --> target.createInvoice()
                                                   |
                                                   +--> this.sendEmailAsync()
                                                        (does not go back through proxy)
```

The clearest design approach is to **extract the asynchronous method into another bean**, then inject that bean into the calling component:

```java
@Service
public class EmailTaskService {
    @Async("asyncPool")
    public void sendEmailAsync() {
        // Email sending logic running on the executor.
    }
}

@Service
public class InvoiceService {
    private final EmailTaskService emailTasks;

    public InvoiceService(EmailTaskService emailTasks) {
        this.emailTasks = emailTasks;
    }

    public void createInvoice() {
        emailTasks.sendEmailAsync(); // Goes through EmailTaskService's bean proxy.
    }
}
```

The two classes above are an **integration fragment**, needing to reside in their respective Java files or be declared appropriately in a Spring application; the `createInvoice` method does not need to know how to create threads itself.

Some techniques such as self-injection through the proxy or fetching the proxy from the context can alter the call path, but they couple the code more tightly to AOP/the container. Splitting responsibilities into two beans is usually easier to understand and test.

## 7. Why Can private/final or Calling new Yourself Prevent @Async from Running?

In `AdviceMode.PROXY` mode, the proxy only intercepts calls **that can pass through it**.

- **`private` methods** are not valid entry points for calling through a Spring proxy. Do not put `@Async` on a `private` method and expect an internal call to become asynchronous.
- **`final` classes** cannot be subclassed by a class-based proxy. **`final` methods** cannot be overridden by a class-based proxy to intercept them; be cautious with CGLIB-based designs.
- **JDK dynamic proxies** intercept calls through the **interface** implemented by the proxy; when the caller depends on an interface, the proxy type and injection style affect the bean type the caller sees.
- **Class-based proxies** (subclass-based) can apply when no suitable interface exists or when explicitly configured. They have limitations with `final` and certain non-overridable methods.
- **Objects created with `new` outside Spring** do not go through the container's proxy creation process.
- **Calls via `this`** still bypass the proxy, even if the method is declared `public` with a valid annotation.

Do not claim that every `final` method can never be intercepted in **every kind of proxy**: the override constraint applies directly to class-based proxies, whereas JDK interface proxies use a different interception model. However, for business code that needs reliable `@Async`, you should use a `public` advisable method and call it through the Spring-managed bean.

You can check this in a test:

```java
import org.springframework.aop.support.AopUtils;

boolean proxied = AopUtils.isAopProxy(context.getBean(WorkService.class));
```

This is a **verification snippet** running within a scope that has the `context` and `WorkService` from the example. It only confirms that the reference you hold is an AOP proxy, **and does not by itself prove that every call along every path goes through the advice**.

## 8. @EnableAsync, Executor Names, and Choosing Where Execution Happens

`@EnableAsync` activates annotation processing in a Spring application context. `@Async` can specify the bean name/qualifier of an executor:

```java
@Async("asyncPool")
public CompletableFuture<Integer> calculate() {
    return CompletableFuture.completedFuture(42);
}
```

This is a **method fragment inside a Spring-managed bean**, not a standalone Java file.

`@Async("asyncPool")` binds the work to the `asyncPool` bean. If no name is specified, Spring selects an executor based on async support configuration (`AsyncConfigurer`, an eligible executor bean, or a fallback mechanism depending on the framework/version). Therefore, when you need to know exactly which pool a task runs on, **explicitly declare and select an executor** rather than guessing by the default thread name.

Some key distinctions:

| Abstraction | Role | Does it create the @Async proxy by itself? |
| --- | --- | --- |
| `@Async` | Marks a method as an async execution candidate | No, unless async support is enabled and the proper call path is used |
| `@EnableAsync` | Activates the annotation-processing infrastructure | Enables the mechanism, while each call still must pass through the interception point |
| `AsyncTaskExecutor` | Contract for submitting asynchronous tasks | No; it is an execution contract |
| `ThreadPoolTaskExecutor` | Thread pool implementation for an executor | No; it manages workers and the queue |
| `AsyncAnnotationBeanPostProcessor`/advisor | Helps apply async advice on eligible beans | Participates in creating/attaching advice to the proxy |
| `Future`/`CompletableFuture` | Handle for status and result | No; they do not decide whether a proxy exists |

`@EnableAsync` defaults to `AdviceMode.PROXY`. The `AdviceMode.ASPECTJ` mode uses weaving when configured with the necessary AspectJ components; it has a different interception model and can handle self-invocation, but it is **not** the default behavior of Spring `@Async`. Do not switch modes just to "fix" self-invocation when separating beans is the simpler design.

## 9. What Happens with void, Future, and CompletableFuture?

A method's return type determines what the caller observes after the proxy submits the task.

### void

```java
@Async("asyncPool")
public void writeAuditLog() {
    // Runs on the executor when the call goes through the proxy.
}
```

This is a **method fragment**. The caller does not receive a `Future`, so it cannot call `get()` to obtain a result or exception. If the worker throws an unhandled exception, Spring provides the `AsyncUncaughtExceptionHandler` mechanism for `void` methods; appropriate logging/monitoring should be configured. A business exception on the worker does not automatically appear in the caller's `try/catch` after a `void` call has been submitted successfully.

### Future<T>

An `@Async` method can declare `Future<T>`; the proxy returns a Future used to obtain the result. The caller can call `get()`, wait with a timeout, or observe cancellation if the implementation supports it.

### CompletableFuture<T>

`CompletableFuture<T>` supports `thenApply`, `thenCompose`, `exceptionally`, `handle`, `whenComplete`, and other composition methods. The target can return `CompletableFuture.completedFuture(value)` after computing on the worker, while the caller receives an asynchronous handle from the proxy. Callbacks without the `Async` suffix may run on the thread that completes the stage, so **do not assume callbacks run on the caller thread**.

Short comparison:

| Declared Type | Caller Receives | Where Worker Errors Are Observed |
| --- | --- | --- |
| `void` | No completion handle | Handler/logs/monitoring in the async infrastructure |
| `Future<T>` | `Future<T>` | `get()` throws `ExecutionException` wrapping the cause |
| `CompletableFuture<T>` | `CompletableFuture<T>` | `get()`, `join()`, `handle`, `exceptionally`, etc. |

`get()` **blocks the thread calling it** if the task has not completed yet. Thus `@Async` does not mean every piece of code using it is non-blocking: if a controller calls `future.get()` immediately, the HTTP request may still have to wait.

## 10. Two Different Kinds of Errors in the Call Path

**Submission-time errors** occur on the caller → proxy → executor branch—for example, the executor cannot be found, has already shut down, or the queue/thread pool rejects the task. Spring's `ThreadPoolTaskExecutor` typically throws `TaskRejectedException` when overloaded. This is a failure **before a valid task execution occurs**, and can surface immediately when invoking the `@Async` method (depending on configuration and timing).

**Task-execution errors** occur after the worker has started invoking the target. For example, a database query fails or business logic throws `IllegalStateException`:

- If the return type is `Future<T>`, read the error via `Future.get()` and `ExecutionException.getCause()`.
- If it is `CompletableFuture<T>`, you can handle it with `exceptionally`/`handle`, or read `CompletionException` from `join()`.
- For `void`, no handle is returned to the caller; use an appropriate handler/log/metric.

Do not put a `try/catch` in the caller and assume it will catch every exception inside an `@Async void` running on a worker:

```java
try {
    bean.sendEmailAsync();
} catch (RuntimeException ex) {
    // May catch errors on the submit branch, not all errors running afterward.
}
```

This is an **illustrative fragment** with a Spring-injected bean. If the caller needs to know whether the task succeeded or failed, design the API to return a `CompletableFuture` or use a mechanism to persist task status.

## 11. Thread-Bound Context Does Not Magically Follow the Proxy

The path from caller to worker crosses a **thread boundary**. This affects:

- **`ThreadLocal` and MDC logging**: values bound to the caller thread are not automatically guaranteed to be present on the worker. With a thread-pool executor, workers are reused; if you propagate context, it must be restored and cleared after each task.
- **Security context**: requires an intentional security context propagation mechanism, such as Spring Security's executor wrappers when using Spring Security.
- **Transaction context**: standard Spring transactions are bound to the executing thread; do not assume the caller's transaction is a shared transaction for the worker. If the task needs a transactional boundary, design the transaction on the worker side and check the appropriate advisor/transaction propagation.
- **Trace context**: requires instrumentation or context propagation compatible with your observability library; avoid assuming that simply adding `@Async` makes the trace ID appear on the worker automatically.

A `TaskDecorator` can wrap an executing `Runnable` to selectively propagate and restore certain contexts. However, a decorator does not replace transaction management and has overhead; be clear about which context is genuinely needed for the business logic.

Do not pass whole objects containing mutable data between caller and worker without ensuring concurrency safety. Actions prior to submission have certain *happens-before* guarantees under the JDK executor contract, but that does not make a shared `HashMap` thread-safe if multiple threads continue modifying it concurrently.

## 12. How Do the Proxy and Worker Affect Return Timing?

You can distinguish the following timeline milestones:

```text
T0 caller invokes proxy
T1 executor accepts task
T2 proxy returns handle to caller
T3 worker starts running target
T4 target finishes
T5 Future completes
T6 caller processes callback/get
```

These are **logical milestones**, not an absolute ordering between T2 and T3: the worker can run before the proxy returns to the caller. For an executor with a queue, the interval from T1 to T3 can be significant; thus the time from when the caller receives the handle until the task completes is affected by both **queue wait** and **execution time**.

When measuring performance, distinguish:

1. **Submit latency**: how long the caller takes to go through the proxy and have the task accepted by the executor.
2. **Queue wait**: how long from submission until the worker starts the target.
3. **Execution time**: how long the actual target runs.
4. **End-to-end completion**: total time from request to final result.

`ThreadPoolTaskExecutor` has parameters `corePoolSize`, `maxPoolSize`, and `queueCapacity`; if the queue still has room, increasing `maxPoolSize` may not increase the number of active workers. The difference between "the proxy has returned" and "the task is actually done" is why you must measure **task completion**, not only the HTTP response when a request returns an accepted status.

## 13. How to Diagnose @Async Not Running on a Different Thread

When a method annotated with `@Async` still prints the same thread name as the caller, check in the following order:

1. **Is `@EnableAsync` present in the right application context?** A different context or missing configuration can prevent beans from being processed as expected.
2. **Is the object the caller invokes a Spring-injected bean?** If instantiated directly with `new`, there is no async proxy.
3. **Is there self-invocation?** `this.asyncMethod()` within the same target typically bypasses the proxy.
4. **Can the method be advised?** Check visibility, `final` with respect to subclass proxies, class-based proxies, and interface injection.
5. **Which executor is selected?** Which bean does `@Async("name")` point to; is the pool configuration actually distinct from the caller thread?
6. **Did you measure inside the target?** Checking the thread only on the caller after calling `@Async` does not prove where the worker ran.
7. **Is `future.get()` called right after submit?** This makes the caller wait, though it does not mean the target ran directly on the caller.
8. **Are there submit/rejection errors?** A task that was not accepted cannot run on a worker; observe queue depth, active workers, and exceptions.

Minimal measurement tip (Spring integration snippet):

```java
String before = Thread.currentThread().getName();
CompletableFuture<Answer> future = service.calculate(21);
Answer answer = future.get(5, TimeUnit.SECONDS);

System.out.println("caller: " + before);
System.out.println("worker: " + answer.workerThread());
```

Both full thread names **depend on the runtime**, so do not use them as fixed stdout in test documentation; the complete example in Section 5 checks the prefix instead of requiring an exact thread name. Besides logging, you can check `AopUtils.isAopProxy(bean)` to verify the reference type, though you still need to test the **actual call path**.

## 14. Misconceptions to Avoid

1. **"Having the `@Async` annotation guarantees running on a different thread."** False: the infrastructure must be enabled, the call must follow the right path through the proxy, and a suitable executor must be used.
2. **"Spring proxies are only for logging."** False: they execute advice, which can alter how calls are handled, including submitting tasks to an executor.
3. **"The `TaskExecutor` recognizes the annotation by itself."** No: the `@Async` infrastructure and proxy attach async behavior to the method; the executor only executes tasks handed to it.
4. **"Calling an `@Async` method from another method in the same bean is still async."** In the default proxy mode, self-invocation bypasses the advice.
5. **"The annotation runs on the worker, while all code in the target runs on the caller."** It is the opposite on the standard path: the interceptor routes the call, and the target runs when the worker executes the task.
6. **"Just because a Future was returned means the work is done."** The Future may still be pending/queued/running.
7. **"`@Async` automatically transfers transaction, MDC, and security context from the caller."** Not by default; context propagation and transactional boundaries must be configured as needed.
8. **"The method throws an exception, so the caller's `try/catch` will catch it."** For async worker errors, you need a Future, callback, or appropriate handler.
9. **"Increasing `maxPoolSize` immediately increases workers."** Not true if the queue still has capacity or tasks are waiting on external dependencies.
10. **"`@Async` is always equivalent to `CompletableFuture.supplyAsync()`."** Both support asynchrony, but `@Async` depends on the Spring proxy, bean lifecycle, and interceptor; `supplyAsync` is a Java API with its own executor selection.
11. **"An `@Async` method on a configuration class is the standard way to launch a job when a bean is created."** You should not apply `@Async` to `@Configuration` methods or expect `@PostConstruct` in the same bean to be intercepted by the proxy. Use an orchestrating component after beans are ready.

## 15. Self-Check

**Question 1.** A controller injects `ReportService` from Spring and calls `calculate()` annotated with `@Async`. Which components does the call pass through?  
**Answer:** Caller → bean proxy → async interceptor → executor/queue → worker → target method; results/errors are reflected through the appropriate handle if the return type allows it.

**Question 2.** Inside the same class, `run()` calls `this.sendAsync()`. Why does it not run asynchronously?  
**Answer:** This is an internal call on the target, which does not pass through the Spring proxy in the default `AdviceMode.PROXY`.

**Question 3.** Does `@Async("asyncPool")` make the method run on a thread named `asyncPool`?  
**Answer:** It selects the executor bean/qualifier named `asyncPool`; the thread name and thread-creation policy are determined by the implementation/configuration.

**Question 4.** Why does returning `CompletableFuture.completedFuture(value)` in the target not negate its async nature?  
**Answer:** `completedFuture` is created **inside the worker** to satisfy the target's signature; the proxy already routed the call to the executor and returned an asynchronous handle to the caller.

**Question 5.** A worker throws an exception in an `@Async void` method. Should you expect a `try/catch` right after the call in the caller to catch it?  
**Answer:** No; you must use a handler/logging/metrics for `void` methods or design the API to return a `Future`/`CompletableFuture` to observe errors.

**Question 6.** Is there any way for self-invocation to be intercepted without splitting beans?  
**Answer:** You can change the design to invoke through the proxy or use `AdviceMode.ASPECTJ` with appropriate weaving, though extracting asynchronous tasks into a separate bean is usually the clearer and more maintainable choice.

**Key takeaway:** an asynchronous call in Spring is the result of **routing through the proxy combined with the executor's policy**. When analyzing bugs or performance, always separate *caller*, *proxy/interceptor*, *executor/queue*, *worker*, and *target*.

### References

- [Spring Framework Reference — Task Execution and Scheduling (@Async, proxy mode, executor qualification)](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — @Async JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/Async.html)
- [Spring Framework — @EnableAsync JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html)
- [Spring Framework — AsyncAnnotationBeanPostProcessor JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/AsyncAnnotationBeanPostProcessor.html)
- [Spring Framework — ThreadPoolTaskExecutor JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)

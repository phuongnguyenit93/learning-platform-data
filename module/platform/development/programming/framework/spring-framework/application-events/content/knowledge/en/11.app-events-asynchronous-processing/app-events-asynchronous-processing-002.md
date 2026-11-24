# `@EnableAsync` and Proxy Methods When Processing Application Events Asynchronously in Spring Framework

## 1. The Problem: Why Adding `@Async` Does Not Always Run on Another Thread

In Spring Framework, `@Async` marks a method as eligible to be executed by an `Executor` on a different thread. `@EnableAsync` activates the infrastructure that detects and applies this mechanism to Spring beans in the `ApplicationContext`. By default, Spring implements this using an **AOP proxy**: the call must **go through the proxy** for `@Async` to be intercepted and submitted to the executor.

Therefore, the following two calls can produce very different results:

```java
// Object provided by Spring, through the proxy:
worker.doWork(); // @Async takes effect if this call goes through the proxy.

// Inside the Worker class itself:
this.doWork();   // self-invocation: bypasses the proxy in default mode.
```

This is an illustrative snippet; `worker` is a bean obtained from Spring and `doWork()` is a method annotated with `@Async`. `@EnableAsync` **does not turn every regular Java call into an asynchronous one**. When called internally via `this`, the code usually runs directly on the current thread, even though the target method is annotated with `@Async`.

In the **Spring Framework Application Events** module, this issue is especially important when combining:

```java
@Async
@EventListener
public void onOrderCreated(OrderCreated event) {
    // Runs off the event-publishing thread if the async interceptor is applied.
}
```

Spring normally invokes a registered `@EventListener` method through the managed bean; if the async proxy is active, the listener can be dispatched to the executor. However, a direct internal call `this.onOrderCreated(event)` still follows proxy rules: the annotation does not spawn a thread by itself.

## 2. Role of Each Component

| Component | Responsibility |
| --- | --- |
| `@EnableAsync` | Activates the infrastructure for detecting `@Async` calls in the current context. |
| `@Async` | Labels a method or bean type so the interceptor dispatches eligible calls to an executor. |
| AOP proxy | Intermediary object that receives calls from external beans and applies async advice. |
| `AsyncAnnotationBeanPostProcessor` | Creates/attaches the async interceptor to eligible Spring beans. |
| `Executor` / `TaskExecutor` | Manages threads and executes submitted tasks. |
| `ApplicationEventPublisher` | Publishes events from the application. |
| `@EventListener` | Registers a method to listen for events; can be combined with `@Async` for background processing. |
| `ApplicationEventMulticaster` | Dispatches events to compatible listeners; synchronous by default unless a shared executor is configured. |

Call flow for a business method with `@Async`:

```text
Client/Publisher thread
        |
        v
Spring bean proxy
        |
        +-- async interceptor -> executor.execute(task)
        |                                 |
        |                                 v
        |                          worker thread runs method
        v
Caller continues
```

Internal call flow:

```text
Client -> proxy -> Worker.selfInvocation()
                     |
                     +-- this.doWork()
                           (bypasses proxy)
                           runs immediately on the same thread
```

**Exact execution timing is not guaranteed:** calling through the proxy submits the task to the executor, but the task may start before or after the caller executes the next line. Do not rely on log line order to assert asynchronicity. Check the thread, latch/future, or actual side effects.

## 3. Runnable Java 17+ Example: Event Listener, Proxy Call, and Self-Invocation

The standalone example below uses Spring Framework 6.2.12 and requires no Spring Boot, database, or web server. It demonstrates:

1. `@EventListener @Async("eventExecutor")` executes on an `event-*` thread.
2. Calling `worker.selfInvocation()` causes `this.doWork("self")` to run on the caller thread because it does not go through the proxy.
3. Calling `worker.doWork("external")` from outside the bean, through the proxy returned by Spring, runs on the executor.

Structure:

```text
async-event-proxy-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/AsyncProxyDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'async-event-proxy-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
}

application {
    mainClass = 'demo.AsyncProxyDemo'
}
```

`src/main/java/demo/AsyncProxyDemo.java`:

```java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class AsyncProxyDemo {

    public record JobQueued(String id) {}

    public static class EventObserver {
        private final CountDownLatch done = new CountDownLatch(1);
        private final AtomicReference<String> runningThread =
                new AtomicReference<>();

        @EventListener
        @Async("eventExecutor")
        public void onJobQueued(JobQueued event) {
            runningThread.set(Thread.currentThread().getName());
            done.countDown();
        }

        public boolean awaitEvent() throws InterruptedException {
            return done.await(5, TimeUnit.SECONDS);
        }

        public String runningThread() {
            return runningThread.get();
        }
    }

    public static class TaskWorker {
        private final AtomicReference<String> selfThread =
                new AtomicReference<>();
        private final AtomicReference<String> externalThread =
                new AtomicReference<>();
        private final CountDownLatch externalDone = new CountDownLatch(1);

        // Method intercepted when called THROUGH the Spring proxy.
        @Async("eventExecutor")
        public void doWork(String origin) {
            if ("self".equals(origin)) {
                selfThread.set(Thread.currentThread().getName());
            } else if ("external".equals(origin)) {
                externalThread.set(Thread.currentThread().getName());
                externalDone.countDown();
            }
        }

        public void selfInvocation() {
            // Internal call via this, bypassing the Spring proxy.
            this.doWork("self");
        }

        public boolean awaitExternal() throws InterruptedException {
            return externalDone.await(5, TimeUnit.SECONDS);
        }

        public String selfThread() {
            return selfThread.get();
        }

        public String externalThread() {
            return externalThread.get();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class AppConfig {
        @Bean("eventExecutor")
        ThreadPoolTaskExecutor eventExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(2);
            executor.setQueueCapacity(20);
            executor.setThreadNamePrefix("event-");
            executor.setWaitForTasksToCompleteOnShutdown(true);
            executor.setAwaitTerminationSeconds(5);
            return executor;
        }

        @Bean
        EventObserver eventObserver() {
            return new EventObserver();
        }

        @Bean
        TaskWorker taskWorker() {
            return new TaskWorker();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            EventObserver observer = context.getBean(EventObserver.class);
            TaskWorker worker = context.getBean(TaskWorker.class);
            String callerThread = Thread.currentThread().getName();

            context.publishEvent(new JobQueued("J-1"));
            if (!observer.awaitEvent()) {
                throw new IllegalStateException("Event listener timed out");
            }

            worker.selfInvocation();
            worker.doWork("external");
            if (!worker.awaitExternal()) {
                throw new IllegalStateException("Async worker timed out");
            }

            System.out.println("event used executor: "
                    + observer.runningThread().startsWith("event-"));
            System.out.println("self call used caller: "
                    + callerThread.equals(worker.selfThread()));
            System.out.println("external call used executor: "
                    + worker.externalThread().startsWith("event-"));
        }
    }
}
```

Run with **JDK 17+** and Gradle pre-installed:

```bash
gradle -q run
```

The three `System.out.println` lines from the program:

```text
event used executor: true
self call used caller: true
external call used executor: true
```

**Explanation of results:**

- `@EnableAsync` registers Spring's async infrastructure. Both `EventObserver` and `TaskWorker` are beans created by the context; public `@Async` methods are eligible for proxying.
- `context.publishEvent(...)` goes through the Spring event infrastructure. The listener method is invoked through the Spring bean and has `@Async("eventExecutor")`, so processing runs in the named executor.
- `selfInvocation()` is an external call through the bean, but inside that method, `this.doWork("self")` invokes the target object directly. There is no async interceptor at the internal call site, so the thread matches the caller's thread.
- `worker.doWork("external")` passes through the proxy; the interceptor submits the task to the executor, so the thread name starts with `event-`.
- `CountDownLatch` is used to **wait for task completion confirmation**, rather than relying on `Thread.sleep()` or fragile log ordering. There is an explicit timeout; if the executor rejects the task or it fails to run in time, the example throws an error instead of hanging indefinitely.
- Getters are used to read bean state rather than accessing fields directly on the proxy object; through a class proxy, wrapper and target state should not be assumed to coincide.

`JobQueued` is a Java record and does not need to extend `ApplicationEvent`. Spring supports publishing payload objects; `@EventListener` listeners still receive the matching payload type.

## 4. How Proxies Work, and How Self-Invocation Loses `@Async`

`@EnableAsync` defaults to `AdviceMode.PROXY`. In this mode, the async interceptor only runs when the call passes through the proxy. Consider a bean:

```java
@Service
public class ReportService {

    public void createReport() {
        sendNotificationAsync(); // Internal call: does not trigger @Async.
    }

    @Async
    public void sendNotificationAsync() {
        // Can still run synchronously if invoked via this.
    }
}
```

This is an **illustrative snippet**; `@EnableAsync`, annotation imports, and executor configuration are required in an application. If `createReport()` is called through the proxy, the body of `createReport()` still executes on the target object; from there, `sendNotificationAsync()` is called via `this`, so it does not hit the async proxy again.

Situations where the proxy commonly does not intervene:

- **Self-invocation:** `this.asyncMethod()` or calling `asyncMethod()` directly from another method on the same instance.
- **Non-Spring-managed objects:** `new ReportService()` is a plain object without a Spring async proxy attached.
- **`private` methods:** proxy mode cannot intercept private method calls from outside like public bean methods.
- **`final` methods or classes when subclass-based proxying is required:** CGLIB proxies cannot override final methods or subclass final classes.
- **During constructor / internal initialization:** the proxy may not be ready yet; do not design async execution by calling an `@Async` method inside a constructor or `@PostConstruct`.
- **Calling through a type/interface not exposed by the proxy:** with JDK dynamic proxies, calls must go through the appropriate interface; do not assume you can cast the proxy to the implementation class.
- **`@EnableAsync` not enabled in the `ApplicationContext` containing the bean:** `@Async` does not activate the infrastructure on its own, and parent/child contexts have separate configuration scopes.

Distinguishing the two proxy strategies:

| Proxy Type | Typical Condition | Notes |
| --- | --- | --- |
| JDK dynamic proxy | Bean has suitable interfaces and proxy is configured to use interfaces | Callers work through the interfaces exposed by the proxy; cannot intercept self-invocation. |
| CGLIB subclass proxy | Bean needs class-based proxying, e.g., class without suitable interfaces | Cannot override final methods or subclass final classes; also does not handle self-invocation in proxy mode. |

`@EnableAsync(proxyTargetClass = true)` requests class-based proxies when using `AdviceMode.PROXY`, but **does not fix self-invocation**. Choosing JDK or CGLIB does not change that rule. The scope of proxy configuration effects may vary depending on how Spring merges auto-proxy settings in your project's version and environment; verify against the actual version.

### Recommended Fix for Self-Invocation: Extract to Another Bean

```java
@Service
public class NotificationWorker {
    @Async("eventExecutor")
    public void sendAsync(String orderId) {
        // Asynchronous processing.
    }
}

@Service
public class OrderService {
    private final NotificationWorker notificationWorker;

    public OrderService(NotificationWorker notificationWorker) {
        this.notificationWorker = notificationWorker;
    }

    public void completeOrder(String orderId) {
        // Business steps...
        notificationWorker.sendAsync(orderId); // Call through an injected Spring bean.
    }
}
```

This is **illustrative code consisting of two Spring-managed beans**; it requires importing `@Service`, `@Async`, enabling `@EnableAsync`, and defining an executor bean named `eventExecutor`. Moving async work to another bean ensures the call traverses the bean proxy and keeps responsibilities clear. In a real system, explicitly define transactions, error handling, and pre/post-commit timing.

Other approaches exist but require careful consideration:

- Injecting the bean's own proxy into itself, or looking up the bean from `ApplicationContext`, can create circular dependencies/confusing structure; use only when truly justified.
- `AopContext.currentProxy()` requires enabling expose-proxy and couples business code to Spring AOP; it is not the default approach.
- `@EnableAsync(mode = AdviceMode.ASPECTJ)` can apply advice even to internal calls if `spring-aspects` and compile-time/load-time weaving are configured. Changing `mode` alone without weaving is insufficient; this is a different mechanism from proxy mode.

## 5. How `@EnableAsync` Selects an Executor

For an `@Async` method without an explicit executor name, Spring uses the executor configured for async support if present (e.g., via `AsyncConfigurer`). If not explicitly configured, Spring searches for a unique `TaskExecutor` bean in the context, or an `Executor` named `taskExecutor`; if none is found, Spring Framework infrastructure may fall back to `SimpleAsyncTaskExecutor`. In Spring Boot, auto-configuration may create a default executor depending on version/configuration; check the actual bean in use.

**Thread policy should not depend accidentally on an auto-configured bean.** In applications needing load control, define an executor and select it explicitly with `@Async("eventExecutor")`:

```java
@Configuration
@EnableAsync
class AsyncConfiguration {

    @Bean("eventExecutor")
    ThreadPoolTaskExecutor eventExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("event-");
        return executor;
    }
}
```

This is a standalone pattern snippet (requiring imports for `Configuration`, `EnableAsync`, `Bean`, `ThreadPoolTaskExecutor`); the full runnable example is in section 3.

Key parameters:

- `corePoolSize`: number of core threads.
- `maxPoolSize`: maximum thread limit; with `ThreadPoolTaskExecutor`, how `maxPoolSize` is utilized depends on queue size/behavior.
- `queueCapacity`: number of tasks that can wait; setting it too high can accumulate latency and memory.
- `threadNamePrefix`: helps distinguish event-processing threads in logs and during debugging.
- Rejection policy, shutdown, and timeout: must be designed for system overload or application shutdown.

`SimpleAsyncTaskExecutor` is not equivalent to a thread pool with a bounded queue and explicit policy. When production load control is required, prefer a managed executor with bounds, metrics, a rejection policy, and error handling.

`@Async("eventExecutor")` specifies the name/qualifier of the executor bean. Multiple executors can be used for different task groups (e.g., email, indexing), but avoid creating unbounded pools or duplicating executors unnecessarily.

## 6. `@Async @EventListener` vs. an Executor on `SimpleApplicationEventMulticaster`

There are **two independent mechanisms** for changing how listeners are invoked:

**Approach A: Per-listener asynchronicity via method proxy**

```java
@EventListener
@Async("eventExecutor")
public void onOrderCreated(OrderCreated event) {
    // Specific listener method handled by the @Async interceptor.
}
```

Requires `@EnableAsync`. Other listeners remain synchronous; only listeners with `@Async` are offloaded to the executor. This is an illustrative snippet; `OrderCreated` is application-defined.

**Approach B: Asynchronicity at the multicaster**

```java
@Bean(name = "applicationEventMulticaster")
ApplicationEventMulticaster applicationEventMulticaster(
        ThreadPoolTaskExecutor eventExecutor) {
    SimpleApplicationEventMulticaster multicaster =
            new SimpleApplicationEventMulticaster();
    multicaster.setTaskExecutor(eventExecutor);
    return multicaster;
}
```

This is an illustrative configuration snippet requiring imports for `Bean`, `ApplicationEventMulticaster`, `SimpleApplicationEventMulticaster`, `ThreadPoolTaskExecutor`. The bean must have the **exact name** `applicationEventMulticaster` so the Spring context uses it instead of the default multicaster. Configuring an executor on the multicaster does not require `@Async` on each method, and it is not controlled by `@EnableAsync`. Since Spring 6.1, `ApplicationListener.supportsAsyncExecution()` allows certain listeners to require running on the publisher thread; hence **not every listener** is moved to the pool.

Avoid mechanically enabling both a multicaster executor and `@Async` on every listener: this can introduce an extra handoff between thread pools, making latency, tracing, and task lifecycle harder to track. Consider choosing one primary mechanism based on the desired scope.

| Criterion | `@Async @EventListener` | Multicaster with `TaskExecutor` |
| --- | --- | --- |
| Scope | Per annotated method where the proxy is applied | Across the multicaster's dispatch mechanism, respecting listener async support |
| Key requirements | `@EnableAsync`, Spring-managed bean, call passes through async proxy | Custom multicaster with executor and listener allowing async dispatch |
| Self-invocation rule | Must watch out; direct calls within the same bean bypass the proxy | Does not depend on `@Async` proxy when the multicaster dispatches the listener to the executor |
| Transaction context | Does not automatically propagate to the worker thread | Does not automatically propagate to the worker thread |
| Error tracking | Via `@Async` mechanism, handler/future | Via executor and multicaster's `ErrorHandler` |

## 7. Transactions and Thread Context: Common Pitfalls in Background Event Processing

Suppose a `@Transactional` service publishes an event right after `repository.save(order)`:

```java
@Transactional
public void placeOrder(Order order) {
    repository.save(order);
    publisher.publishEvent(new OrderPlaced(order.getId()));
}
```

If the listener is `@Async @EventListener`, it may begin processing **before the publisher's transaction commits**. Because it runs on a different thread:

- The JDBC/JPA transaction bound to the publisher's thread does not automatically carry over to the event-handling thread.
- Queries on a different connection may not see uncommitted records; depending on isolation, stale data may be seen.
- An exception thrown by an async listener does not automatically roll back the publisher's transaction; the producer may have already committed or not yet committed.
- `SecurityContext`, MDC, `RequestContextHolder`, and other `ThreadLocal` values do not automatically propagate. If needed, use a `TaskDecorator`/controlled context propagation mechanism.
- Do not pass lazy-loading/session-bound JPA entities directly into an async listener assuming it can always access the data.

If the work must only run **after a successful commit**, consider:

```java
@Async("eventExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterOrderCommitted(OrderPlaced event) {
    // Processing will be invoked according to the AFTER_COMMIT phase,
    // after which @Async can offload execution to the executor.
}
```

This is an illustrative snippet inside a Spring-managed bean; it requires `@EnableAsync`, `@Async`, `@TransactionalEventListener`, `TransactionPhase`. For events published inside an imperative transaction, `@TransactionalEventListener` registers a transaction callback; by default, the listener does not run if no transaction is active (unless `fallbackExecution = true` is configured). When DB writes are needed from the async thread, start a separate transaction if business logic requires it—for example by calling another `@Transactional` service—rather than relying on the publisher's committed transaction.

**After commit still does not guarantee delivery:** the event remains in memory; process termination between commit and async execution can lose the task. Business workflows requiring guaranteed delivery need a transactional outbox, durable broker, idempotency, and retries.

## 8. Return Values, Exceptions, and Error Monitoring

General `@Async` methods support `void`, `Future<T>`, or `CompletableFuture<T>` according to Spring's async rules. With `@Async @EventListener`, **`void`** is typically used because the asynchronous event listener mechanism **does not support automatically publishing a follow-up event from a return value** like synchronous listeners do. To publish a follow-up event, inject `ApplicationEventPublisher` and explicitly call `publishEvent(...)` during async processing.

For async methods returning `void`, exceptions do not return directly to the caller that published the event; you can configure an `AsyncUncaughtExceptionHandler`:

```java
@Configuration
@EnableAsync
class AsyncErrorConfiguration implements AsyncConfigurer {

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (error, method, parameters) ->
                System.err.println(
                        "Async failed in " + method.getName() + ": " + error);
    }
}
```

This is an illustrative configuration snippet; it requires imports for `Configuration`, `EnableAsync`, `AsyncConfigurer`, `AsyncUncaughtExceptionHandler`. The example handler prints errors, while production should have structured logging, metrics, alerting, and business handling policies. When an async method returns `Future`/`CompletableFuture`, the caller can observe failures through the corresponding async result. With a `void @EventListener`, the publisher receives no processing result back.

If the `Executor` rejects task submission, an error may appear **immediately at proxy/dispatch invocation time**, unlike errors inside the method running on a worker thread. Both failure modes must be tested separately; `publishEvent()` returning normally is not proof that every task was processed successfully.

`@Order` or listener registration order can only influence the corresponding dispatch/submission order. In a multi-threaded executor, task **completion** order is not guaranteed, and side effects should not rely on that order unless explicit serialization is designed.

## 9. Testing `@EnableAsync` and Proxy Methods Properly

Recommended test scenarios:

1. **Enabling/disabling infrastructure:** with `@EnableAsync` in the context, call the `@Async` method through the bean proxy and verify the task runs on the expected thread; without enablement, do not assume asynchronicity.
2. **External vs. self-invocation:** use the two call paths from the section 3 example to catch `this.asyncMethod()` bugs.
3. **Event listeners:** publish an object via `publishEvent(...)`, wait on the listener's latch/future, and then assert the outcome. Do not use `Thread.sleep(50)` to guess when a task finishes.
4. **Errors in tasks:** have the listener throw an exception and verify the handler/log/future; confirm errors are not accidentally treated as success.
5. **Executor overload:** configure a small queue/pool in a dedicated test, submit multiple tasks that can block in a controlled way, and verify the rejection policy.
6. **Transaction boundaries:** publish an event inside an uncommitted transaction; confirm the async listener does not depend on uncommitted data, and test `AFTER_COMMIT` when using transaction-bound listeners.
7. **Shutdown:** verify in-flight tasks are completed or intentionally canceled within the desired timeout.

Use stable observable conditions such as `CountDownLatch`, `CompletableFuture`, Awaitility, thread values, or DB state. The `"event-"` thread name in the example is only for easy verification, not a general Spring contract.

## 10. Configuration Pitfalls and Quick Fixes

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| Has `@Async` but still runs on caller thread | `@EnableAsync` not enabled, no Spring proxy, or self-invocation | Enable in the right context, obtain bean from Spring, extract async method to a separate bean |
| `@Async` runs when called from controller but not internally | `this.method()` bypasses proxy | Call another bean or choose an intentional interception mechanism |
| Bean not found by implementation class | JDK proxy exposes only interfaces | Inject by interface or configure appropriate class proxying |
| `@Async` on `private`/`final` has no effect | Proxy cannot intercept/override | Move to a public, proxiable method on an appropriate service bean |
| Async listener cannot read newly saved data | Publisher not yet committed; transaction/context not propagated | Use `AFTER_COMMIT`, pass ID, and open a separate transaction when needed |
| Missing logs/trace, security context on new thread | Thread-bound context not propagated | Configure controlled propagation, avoid blindly copying all state |
| Exception does not appear at caller | Error occurred on worker thread | Use `AsyncUncaughtExceptionHandler`, result future, logs/metrics |
| Unstable event ordering | Thread pool executes concurrently | Design for idempotency; if sequential order is needed, use a dedicated queue/partition/order |
| Pool stops accepting tasks | Queue full, executor shut down | Monitor saturation/rejection, plan capacity and shutdown |
| `@Async` on listener does not emit event from return value | Limitation of async event listeners | Call `ApplicationEventPublisher.publishEvent(...)` explicitly |

## 11. Design Selection Guide

Use `@EnableAsync` + `@Async` when only **some** tasks or event listeners need to run in the background and you want individual control over their executors. Use an executor on `ApplicationEventMulticaster` when you want a centralized dispatch strategy, while still respecting listeners that do not support async. Use `@TransactionalEventListener(AFTER_COMMIT)` for post-commit requirements; add `@Async` when execution on another thread is genuinely needed. When durability and delivery guarantees are business requirements, use an outbox/broker instead of relying solely on an in-memory async call.

Checklist for code review: **Who calls the method? Does the call pass through a Spring bean proxy? Which executor runs it? Has the transaction committed? Where are exceptions reported?** Answering these five questions clearly eliminates most bugs caused by misunderstanding `@EnableAsync` and proxies.

Official documentation:

- [Spring Framework — Task Execution and Scheduling, `@Async`, executors, and exceptions](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — ApplicationContext Events, Asynchronous Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — AOP proxying and self-invocation](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — `@EnableAsync` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html)
- [Spring Framework — `@EventListener` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
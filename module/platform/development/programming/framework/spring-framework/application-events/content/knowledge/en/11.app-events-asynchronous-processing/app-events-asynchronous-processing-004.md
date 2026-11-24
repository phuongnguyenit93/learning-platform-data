# Specifying an Executor by Qualifier in Spring Framework Application Events

## 1. Problem Statement and Goals

Suppose an application publishes an `OrderPlaced` event whenever an order is created. Multiple listeners subscribe to this event, each with different load characteristics:

- **Email listener** sends confirmation emails, typically waiting on network I/O and potentially rate-limited by providers.
- **Audit listener** records business audit trails and should have dedicated resources so slow emails do not drag it down.
- **Metrics listener** updates counters, usually a very short task that may need a different handling policy.

Spring supports `@EventListener` to register listeners, `@Async` to execute listeners asynchronously, and `@Async("...")` to select a specific executor by **bean name** or **qualifier**. The goal of this lesson is to learn how to register multiple executors, bind the right executor to each event listener, verify execution threads, and handle overload, errors, and transactions.

An executor is what accepts and runs tasks. With `ThreadPoolTaskExecutor`, tasks run on threads in the pool according to configuration; it is not a durable message queue, nor does it automatically provide retries or exactly-once processing guarantees.

## 2. Distinguishing the Roles

| Component | Purpose | Example |
| --- | --- | --- |
| `ApplicationEventPublisher` | Publishes events to the Spring context | `publisher.publishEvent(new OrderPlaced("O-42"))` |
| `@EventListener` | Marks a method to receive an event type | `@EventListener public void onOrder(OrderPlaced e)` |
| `@EnableAsync` | Enables Spring's `@Async` processing infrastructure | On a `@Configuration` class |
| `@Async` | Requests asynchronous execution of the method | `@Async` or `@Async("mailExecutor")` |
| `Executor` / `TaskExecutor` | Runs tasks on managed threads | `ThreadPoolTaskExecutor` |
| `@Bean("mailExecutor")` | Names the executor bean | Listeners can select `"mailExecutor"` |
| `@Qualifier("auditLane")` | Attaches a qualifier identifier to the bean | Listeners can select `"auditLane"` |
| `ApplicationEventMulticaster` | Selects and dispatches matching listeners | `SimpleApplicationEventMulticaster` |

A common misconception is that **`@Qualifier` turns a method asynchronous by itself**. `@Qualifier` only provides an identifier for Spring to look up a bean. For an event listener, `@Async("auditLane")` is needed to specify which pool the listener must use.

## 3. How to Specify an Executor by Bean Name or Qualifier

### 3.1. Selecting by Bean Name

We register an executor named `mailExecutor`:

```java
@Bean("mailExecutor")
public ThreadPoolTaskExecutor mailExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(50);
    executor.setThreadNamePrefix("mail-");
    return executor;
}
```

The listener selects this bean with:

```java
@Async("mailExecutor")
@EventListener
public void sendOrderEmail(OrderPlaced event) {
    // Runs on mailExecutor.
}
```

Spring resolves the executor using the identifier `mailExecutor`. A Spring-managed bean, rather than an executor instantiated inside the listener, enables unified configuration, reuse, and lifecycle management.

### 3.2. Selecting by a Qualifier Different from the Bean Name

An executor can have a **bean name** and a **qualifier** that differ:

```java
@Bean("auditThreadPool")
@Qualifier("auditLane")
public ThreadPoolTaskExecutor auditThreadPool() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(1);
    executor.setMaxPoolSize(2);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("audit-");
    return executor;
}
```

The listener can be written as:

```java
@Async("auditLane")
@EventListener
public void writeAudit(OrderPlaced event) {
    // Selects the auditThreadPool bean via the auditLane qualifier.
}
```

In Spring, the `value` of `@Async` is used to look up an executor with a matching **bean name** or **qualifier**. In the example above, `@Async("auditThreadPool")` could also select the same executor by bean name. The snippets in this section illustrate individual pieces; a complete runnable program is in section 5.

### 3.3. Do Not Confuse `@Qualifier` Used in Dependency Injection

The following only controls **dependency injection**:

```java
public OrderService(@Qualifier("auditLane") Executor executor) {
    this.executor = executor;
}
```

Having a service with an `executor` field injected from `auditLane` does not automatically cause `@EventListener` methods in that service to run on that pool. If you want Spring to dispatch listener calls to the pool automatically, place `@Async("auditLane")` on the listener method. Submitting tasks manually via `executor.execute(...)` is manual orchestration with a different lifecycle and error handling model.

## 4. Requirements for the Mechanism to Work

- **Enable `@EnableAsync`** in configuration actually loaded into the `ApplicationContext`. Plain Spring does not activate `@Async` merely because the annotation is present.
- **Define executors as Spring beans** and pick the exact name/qualifier. With `ThreadPoolTaskExecutor` declared via `@Bean`, Spring invokes the required lifecycle callbacks to initialize the pool.
- **Register the listener as a Spring bean** and ensure calls pass through Spring's proxy mechanism. In default proxy mode, internal calls like `this.someAsyncMethod()` bypass the proxy.
- **Use proxiable methods**: for example, use non-`final` classes and `public` methods, avoiding constructs that prevent Spring from applying async advice.
- **Do not depend on completion order** across async listeners. Each pool schedules independently; completion order need not match listener registration order.
- **Check for overload**: an executor can reject tasks if it is busy and the queue is full. "Async" does not mean "never fails."

In a typical configuration, the event multicaster still dispatches listeners on the publisher thread. When the adapter invokes an `@Async("mailExecutor")` listener on the Spring proxy, the proxy offloads the work to `mailExecutor`. Therefore, the code calling `publishEvent` usually does not wait for the listener body to finish.

```text
publishEvent(OrderPlaced)
      |
      v
ApplicationEventMulticaster
      |
      +-- @EventListener + @Async("mailExecutor")
      |        |
      |        +--> mailExecutor --> mail-* threads
      |
      +-- @EventListener + @Async("auditLane")
               |
               +--> auditThreadPool --> audit-* threads
```

## 5. Runnable Java 17 + Maven Example

The application below defines two listeners for the same `OrderPlaced` event:

1. `sendEmail` selects its executor by the **bean name** `mailExecutor`.
2. `recordAudit` selects its executor by the **qualifier** `auditLane` on the bean named `auditThreadPool`.

The program uses `CountDownLatch` to wait for both listeners and `ConcurrentHashMap` to collect results from the threads. Output does not depend on the execution order of the two pools.

**Directory structure**

```text
qualified-event-executors/
├── pom.xml
└── src/main/java/example/QualifiedEventExecutorsDemo.java
```

**`pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>qualified-event-executors</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
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
                <configuration>
                    <mainClass>example.QualifiedEventExecutorsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/example/QualifiedEventExecutorsDemo.java`**

```java
package example;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class QualifiedEventExecutorsDemo {

    public record OrderPlaced(String orderId) {}

    public static final class ExecutionEvidence {
        private final CountDownLatch finished = new CountDownLatch(2);
        private final Map<String, String> threads =
                new ConcurrentHashMap<>();

        public void record(String key, String threadName) {
            threads.put(key, threadName);
            finished.countDown();
        }

        public void waitForBoth() throws InterruptedException {
            if (!finished.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Timed out waiting for event listeners");
            }
        }

        public String getThread(String key) {
            return threads.get(key);
        }
    }

    // Do not mark final because this bean is proxied by Spring for @Async.
    public static class OrderListeners {
        private final ExecutionEvidence evidence;

        public OrderListeners(ExecutionEvidence evidence) {
            this.evidence = evidence;
        }

        @Async("mailExecutor")
        @EventListener
        public void sendEmail(OrderPlaced event) {
            evidence.record("mail:" + event.orderId(),
                    Thread.currentThread().getName());
        }

        @Async("auditLane")
        @EventListener
        public void recordAudit(OrderPlaced event) {
            evidence.record("audit:" + event.orderId(),
                    Thread.currentThread().getName());
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class Config {

        @Bean
        public ExecutionEvidence executionEvidence() {
            return new ExecutionEvidence();
        }

        @Bean
        public OrderListeners orderListeners(ExecutionEvidence evidence) {
            return new OrderListeners(evidence);
        }

        @Bean("mailExecutor")
        public ThreadPoolTaskExecutor mailExecutor() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("mail-");
            return executor;
        }

        @Bean("auditThreadPool")
        @Qualifier("auditLane")
        public ThreadPoolTaskExecutor auditThreadPool() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("audit-");
            return executor;
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        String publisherThread = Thread.currentThread().getName();

        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            context.publishEvent(new OrderPlaced("ORD-42"));

            ExecutionEvidence evidence =
                    context.getBean(ExecutionEvidence.class);
            evidence.waitForBoth();

            String mailThread = evidence.getThread("mail:ORD-42");
            String auditThread = evidence.getThread("audit:ORD-42");

            System.out.println("mail selected right pool: "
                    + (mailThread != null
                            && mailThread.startsWith("mail-")));
            System.out.println("audit selected by qualifier: "
                    + (auditThread != null
                            && auditThread.startsWith("audit-")));
            System.out.println("both differ from publisher thread: "
                    + (!publisherThread.equals(mailThread)
                            && !publisherThread.equals(auditThread)));
        }
    }
}
```

Run in the directory containing `pom.xml`, with JDK 17+ and Maven:

```bash
mvn -q compile exec:java
```

**Three standard lines printed by the application**, excluding any tool logs:

```text
mail selected right pool: true
audit selected by qualifier: true
both differ from publisher thread: true
```

Verification: `mailThread` starts with `mail-`, `auditThread` starts with `audit-`, and both differ from `publisherThread`. This verifies runtime execution on actual threads rather than merely relying on source annotations.

`CountDownLatch` has a 10-second timeout. If a listener fails to finish, the program throws a timeout error instead of printing the three success lines. `ConcurrentHashMap` is thread-safe when both tasks record results simultaneously, and the latch ensures `main` waits for both `record` calls. `ThreadPoolTaskExecutor` is managed by Spring and shut down when the context closes.

The payload `OrderPlaced` is a Java `record` and does not extend `ApplicationEvent`. Spring supports `publishEvent(Object)` and can wrap the payload in `PayloadApplicationEvent`; the `@EventListener` method still receives `OrderPlaced` directly.

## 6. When Multiple Executors Exist, How Does Spring Choose?

### 6.1. `@Async("...")` Selects an Explicit Target

When you write `@Async("mailExecutor")`, Spring looks up the executor by the corresponding bean name or qualifier; this takes precedence over async support's default executor selection. Consequently, an application with multiple pools can bind the exact pool to each listener.

If you rename the `mailExecutor` bean to `emailPool`, you must update the corresponding annotation or provide a consistent qualifier/alias; do not assume Spring automatically picks a pool with a "similar" name.

### 6.2. `@Async` Without a Name Uses the Default Mechanism

When no value is specified:

```java
@Async
@EventListener
public void handleEvent(OrderPlaced event) {
    // Uses the default executor of Spring's async mechanism.
}
```

Spring uses its default executor resolution rules (which can be supplied via `AsyncConfigurer`; otherwise the framework's executor bean lookup rules apply). In an application with multiple pools, do not rely on guesswork about which pool is selected; declare a clear default executor or attach an explicit qualifier to the listener.

This is an **illustrative configuration pattern** when a default is needed; do not paste it verbatim into section 5's example without providing a `generalExecutor` bean:

```java
@Configuration
@EnableAsync
class AsyncDefaults implements AsyncConfigurer {
    private final Executor defaultExecutor;

    AsyncDefaults(@Qualifier("generalExecutor") Executor executor) {
        this.defaultExecutor = executor;
    }

    @Override
    public Executor getAsyncExecutor() {
        return defaultExecutor;
    }
}
```

This snippet requires importing `java.util.concurrent.Executor`, `AsyncConfigurer`, Spring annotations, and having the corresponding executor bean. A listener with `@Async("auditLane")` still selects by its own qualifier rather than using the `AsyncConfigurer` default.

### 6.3. Specifying `@Async` at the Class Level

`@Async("mailExecutor")` can be placed on a class to apply to methods within Spring's supported scope; an `@Async("auditLane")` annotation placed on an individual method can override the class-level choice. For event listeners serving multiple tasks, per-method declarations usually make it clearer to readers which pool each workflow uses.

### 6.4. Comparison with Multicaster-Level Executors

`SimpleApplicationEventMulticaster#setTaskExecutor(...)` configures how the multicaster sends eligible listener invocations to an executor. This is an **event-dispatch-level** setting, unlike `@Async("...")` which selects per method.

| Configuration Style | Scope | Needs `@EnableAsync`? |
| --- | --- | --- |
| `@Async("mailExecutor")` on an event listener | One listener method | Yes, in plain Spring configuration |
| `@Async` without a value | One listener method, using default | Yes |
| `SimpleApplicationEventMulticaster#setTaskExecutor(executor)` | Listeners permitted by the multicaster to run asynchronously | Does not depend on `@EnableAsync` to use the multicaster's executor |

Configuring both an executor on the multicaster and `@Async` on listeners simultaneously can create two layers of dispatch; do so only with a clear reason and understanding of each layer's responsibilities. Since Spring 6.1, transaction-bound listeners may require executing callback registration on the publisher thread; the multicaster must respect `supportsAsyncExecution()` when choosing listeners to run asynchronously.

## 7. Sizing Pools by Business Workload

`ThreadPoolTaskExecutor` commonly uses three parameters:

- `corePoolSize`: number of core threads.
- `maxPoolSize`: maximum number of threads when expansion is needed.
- `queueCapacity`: number of tasks waiting in the queue. While core threads are busy, work can queue before additional threads beyond core are created.

For example, configuring `corePoolSize = 2`, `maxPoolSize = 8`, `queueCapacity = 100` does not mean eight tasks immediately run in parallel. A large queue can hold many waiting tasks before the pool scales up to maximum; you must measure real load and wait times.

| Workload Type | Considerations | Suggested Policy |
| --- | --- | --- |
| Email, HTTP, I/O | Timeouts, external service limits | Dedicated pool, bounded threads and queue |
| CPU computation | Processing resource contention | Pool sized to CPU capacity |
| Critical audit | No data loss on application shutdown | Durable persistence/outbox; executor only for execution |
| Short tasks | Low latency and context-switch overhead | Moderate pool, monitor queue and active tasks |

An overloaded pool can reject task submissions; in that case, Spring may throw `TaskRejectedException` at submission time. Separate **submission errors** from errors **inside the listener**. Do not solve overload by increasing the queue indefinitely without understanding the impact on memory and latency.

Setting a clear `threadNamePrefix` helps observability: `mail-*` stands out from `audit-*` in logs and thread dumps. In production, also monitor active threads, queue size, task rejections, and execution duration.

## 8. Exceptions in Asynchronous Listeners

For a listener method returning `void` with `@Async`:

- If code inside the listener throws an exception once running on the executor, the exception **does not automatically propagate back** to the method that called `publishEvent`.
- Spring provides `AsyncUncaughtExceptionHandler` to handle exceptions from `void` `@Async` methods; by default, errors are typically logged.
- If the executor cannot accept the task, a **rejection** error may appear on the dispatch path before the listener body begins; do not confuse these two cases.
- You cannot rely on the return value of an async `@EventListener` to automatically publish a follow-up event. If a new event is needed, inject `ApplicationEventPublisher` and call `publishEvent(...)` explicitly.

The snippet below illustrates configuring an error handler in an `AsyncConfigurer` class:

```java
@Override
public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
    return (error, method, args) ->
            System.err.println("Async listener failed: "
                    + method.getName() + ": " + error.getMessage());
}
```

To use this in a real application, you need a complete configuration class, proper imports, and appropriate logging/monitoring; this is not a standalone program. For critical tasks, maintain an event identifier, a retry/idempotency policy, and a place to record failures. Simply logging errors does not cause the task to retry on its own.

## 9. Transactions, Ordering, and Thread Data

### 9.1. Async Listeners Can Run Before Commit

If a `@Transactional` service publishes `OrderPlaced` inside a transaction, an `@EventListener @Async("mailExecutor")` listener can begin executing on the mail thread **before the transaction commits**. If the transaction subsequently rolls back, the email may still have been sent.

For work that must wait for commit, consider:

```java
// Illustrative snippet integrated inside a Spring bean.
// Requires @EnableAsync and an active transaction manager.
@Async("mailExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void sendEmailAfterCommit(OrderPlaced event) {
    // Only starts after the event-publishing transaction commits successfully.
}
```

The code above requires importing `@Async`, `@TransactionalEventListener`, and `TransactionPhase`, and is not a standalone compilable example. `@TransactionalEventListener` defaults to `AFTER_COMMIT` and `fallbackExecution = false`, so if published outside a transaction, the listener **does not run**. Phase callback registration still binds to the transaction on the publisher thread; the async work itself does not carry that transaction across to a new thread.

### 9.2. Executors Do Not Make Tasks Durable

A task sitting in `ThreadPoolTaskExecutor`'s memory can be lost if the process terminates abruptly. `AFTER_COMMIT` chooses the timing of execution, not reliable delivery. For emails/invoices that must not be lost, apply a **transactional outbox** with workers/brokers, retries, and idempotency.

### 9.3. Do Not Expect Context to Propagate Automatically

Executor threads do not by default carry the same transaction `ThreadLocal`, security context, or MDC as the publishing thread. Include `orderId`/`eventId` in the payload; if thread context must be transferred, use an explicitly designed propagation/`TaskDecorator` solution. Even a listener routed to the right executor can lack data if code implicitly depends on `ThreadLocal`.

### 9.4. Do Not Rely on Listener Completion Order

Two listeners for the same event dispatched to two pools can finish in any order. `@Order` can influence listener invocation order during dispatch, but does not guarantee async **completion** timing. When task B must run after task A, use a workflow/service with explicit dependencies or an appropriate queue.

## 10. Testing and Diagnostics

Result matrix for the section 5 example:

| Listener | `@Async` value | Selected Bean | Expected Thread Name |
| --- | --- | --- | --- |
| `sendEmail` | `mailExecutor` | `mailExecutor` | Starts with `mail-` |
| `recordAudit` | `auditLane` | `auditThreadPool` with `@Qualifier("auditLane")` | Starts with `audit-` |

A sound test should verify that **both listeners receive the event**, both complete before assertions run, and each runs on the correct pool. `CountDownLatch` with a timeout is a suitable approach; arbitrary `Thread.sleep` calls can produce flaky tests.

Additional scenarios worth testing:

1. Change the qualifier to a non-existent name: verify configuration or dispatch fails loudly.
2. Remove `@EnableAsync` in a separate fixture: prove behavior differs from executor-backed execution.
3. Set a small `queueCapacity` and submit many tasks: verify rejection/backpressure per policy.
4. Have a listener throw an exception: verify the handler/logs capture the failure and it is not treated as a successful completion.
5. Publish events in committed and rolled-back transactions: distinguish `@EventListener` from `@TransactionalEventListener`.
6. Shut down the context while tasks are incomplete: verify shutdown wait policy or persistence of unfinished work per system requirements.

### Common Errors and Fixes

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Listener runs on publisher thread | Forgot `@EnableAsync`, call bypassed proxy, bean not managed by Spring | Check configuration, proxy, and call path |
| Executor not found | `@Async("...")` value has wrong name/qualifier or bean is wrong type | Verify bean name, `@Qualifier`, and `Executor` type |
| Listener does not run | `@EventListener` not registered, wrong event type, or condition not met | Check context and listener declaration |
| Task rejected | Pool overloaded, queue full, executor already shut down | Review pool limits, rejection policy, and retry strategy |
| Error logged in executor but publisher sees no exception | Exception from `void` async listener body | Use `AsyncUncaughtExceptionHandler` and observability |
| Behavior differs across environments | Default executor config changed, bean name/qualifier changed | Specify executor explicitly and verify startup config |
| Email sent even though transaction rolled back | Async `@EventListener` ran before commit | Consider `@TransactionalEventListener(AFTER_COMMIT)` and outbox |
| Logs missing correlation ID | `ThreadLocal`-based context not propagated | Carry ID in the event and configure propagation when needed |

## 11. Adoption Checklist

- Identify load, latency, criticality, and isolation needs for each listener group.
- Declare pools as Spring beans with clear names/qualifiers.
- Enable `@EnableAsync` and use listener beans that Spring can proxy.
- Specify `@Async("beanNameOrQualifier")` on listeners needing a dedicated executor.
- Set thread name prefixes to prove and monitor which pool is used.
- Test normal execution, overload, callback errors, and shutdown.
- Review transaction boundaries, retries, idempotency, and work durability for critical side effects.

**Key takeaway:** `@Qualifier` is an identifier used to locate an executor bean; `@Async("qualifier")` is the mechanism for an event listener method to select that executor. Using separate pools isolates workloads, while asynchronous processing reliability still depends on error handling, transactions, task admission capacity, and durable storage.

## Official Documentation

- [Spring Framework — Task Execution and Scheduling: Executor Qualification with @Async](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — ApplicationContext Events: Asynchronous Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Javadoc — @Async in Spring 6.2](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/scheduling/annotation/Async.html)
- [Javadoc — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
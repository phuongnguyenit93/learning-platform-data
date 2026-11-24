# Default Executor and Custom Executors in Spring Async

## 1. Objectives

When a method is annotated with `@Async`, Spring does not create an arbitrary thread for each method on its own. Spring submits the work to an `Executor` configured in the `ApplicationContext`. The executor determines which thread the task runs on, whether it is queued, the maximum concurrency level, and how overload is handled.

If an application has only a small group of tasks, a single default executor may suffice. When a system has multiple kinds of work, such as sending emails, processing images, calling external services, or CPU-intensive computations, different workloads may need separate pools to avoid starving one another of resources.

This lesson focuses on:
- How `TaskExecutor` and `Executor` differ.
- The order in which Spring Framework selects a default executor for `@Async`.
- When `SimpleAsyncTaskExecutor` is used and why it is not a thread pool.
- How to declare a bounded `ThreadPoolTaskExecutor` with thread naming.
- How to specify a dedicated executor using `@Async("beanName")`.
- How to use `AsyncConfigurer` to customize the default executor and exception handling.
- How to choose queue capacity, pool size, rejection policy, and shutdown behavior.
- The differences between Spring Framework's default executor and Spring Boot's auto-configuration.

After this lesson, you will be able to predict which executor an `@Async` method runs on, separate workloads into appropriate pools, and spot configurations prone to unbounded queue growth or forcing the caller to run tasks synchronously.

## 2. Executor and TaskExecutor

In Java, `java.util.concurrent.Executor` is an abstraction that accepts a `Runnable` and decides how to execute the task. An `Executor` can use a thread pool, a single thread, or even execute immediately on the calling thread. The name `Executor` does not guarantee that the implementation is always a pool.

Spring provides `org.springframework.core.task.TaskExecutor` with the `execute(Runnable)` contract. `TaskExecutor` is compatible with `java.util.concurrent.Executor` and gives Spring components a shared task execution abstraction.

Common implementations:

| Implementation | Behavior | When Appropriate |
|---|---|---|
| `SyncTaskExecutor` | Runs the task immediately on the calling thread | Simple tests or when synchronous execution is required |
| `SimpleAsyncTaskExecutor` | Creates a new thread for every task, does not reuse threads | Small workloads or cases with an explicit concurrency limit |
| `ThreadPoolTaskExecutor` | Manages a `ThreadPoolExecutor` with a pool and queue | Common choice for background processing in applications |
| `ConcurrentTaskExecutor` | Adapter for an existing `java.util.concurrent.Executor` | When integrating an external executor with Spring's abstraction |

With `@Async`, the executor is used to run the method after the async interceptor receives the call through the proxy. Executor configuration directly impacts system load capacity and latency.

## 3. How Does Spring Select the Default Executor?

In Spring Framework 6.2, if no `AsyncConfigurer` provides a default executor, Spring searches for an executor in this order:

1. Look for a unique `TaskExecutor` bean in the `ApplicationContext`.
2. If a unique `TaskExecutor` cannot be resolved, look for a bean named `taskExecutor` whose type is compatible with `Executor`.
3. If no suitable executor is found, Spring uses `SimpleAsyncTaskExecutor` as a fallback.

If a configuration class implements `AsyncConfigurer`, the `getAsyncExecutor()` method provides the default executor for `@Async` methods without a qualifier. If you only want to customize the exception handler or keep the default executor, `getAsyncExecutor()` can return `null`.

You can visualize this as:

~~~text
@Async method without qualifier
          |
          v
Is there an AsyncConfigurer returning an Executor?
       /             \
     Yes              No
     |                 |
     v                 v
Use configurer's    Is there exactly one TaskExecutor?
Executor               /             \
                     Yes              No
                     |                 |
                     v                 v
               Use that bean    Is there a bean named taskExecutor?
                                    /          \
                                  Yes           No
                                  |              |
                                  v              v
                           Use taskExecutor  SimpleAsyncTaskExecutor
~~~

A method with a qualifier selects the executor matching that qualifier, independent of the default executor:

~~~java
@Async("mailExecutor")
public void sendMail(String address) {
    // Runs on the executor with bean name or qualifier mailExecutor.
}
~~~

The value in `@Async` can be the name of an `Executor` bean or a qualifier attached to an `Executor` bean, for example via `@Qualifier`.

Do not assume any bean named `applicationTaskExecutor` will automatically serve as the default executor in plain Spring Framework. The default name Spring Framework looks up in its fallback step is `taskExecutor`. `applicationTaskExecutor` typically appears in Spring Boot conventions and auto-configuration.

## 4. SimpleAsyncTaskExecutor Is Not a Thread Pool

If Spring Framework cannot find a suitable executor, the `SimpleAsyncTaskExecutor` fallback can create a new thread for each execution. It does not reuse completed threads like `ThreadPoolTaskExecutor`.

`SimpleAsyncTaskExecutor` can limit the number of concurrent tasks. Once the limit is reached, subsequent submissions may have to wait until a slot becomes free. However, a concurrency limit does not turn it into a pool that reuses threads.

This matters as workload increases:
- A high rate of `@Async` calls can cause many threads to be created.
- New threads consume stack memory and operating system resources.
- There is no queue/pool reuse like in `ThreadPoolTaskExecutor`.
- Concurrency limits still need to be explicitly configured and monitored.

Therefore, for production workloads requiring control over thread count, queuing, and rejection, declare an explicit executor. Do not treat the fallback as a properly sized thread pool for your application.

## 5. Declaring a Default ThreadPoolTaskExecutor

`ThreadPoolTaskExecutor` is Spring's widely used `TaskExecutor` implementation. It wraps a `ThreadPoolExecutor` and allows configuration via bean properties.

Example:

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration {

    @Bean(name = "taskExecutor")
    public ThreadPoolTaskExecutor taskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(50);
        executor.setThreadNamePrefix("app-async-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(20);
        return executor;
    }
}
~~~

Because the executor is declared as a Spring bean, Spring manages its lifecycle and calls the necessary initialize/shutdown steps. There is no need to call `initialize()` manually inside a standard `@Bean` method.

Key properties:

| Property | Meaning |
|---|---|
| `corePoolSize` | Number of core worker threads in the pool |
| `maxPoolSize` | Maximum number of worker threads when the queue is full |
| `queueCapacity` | Number of tasks that can wait in the queue |
| `keepAliveSeconds` | Time excess threads beyond core can remain idle before being reclaimed |
| `threadNamePrefix` | Prefix to identify the executor in logs and thread dumps |
| `waitForTasksToCompleteOnShutdown` | Instructs the executor to wait for accepted tasks when the context shuts down |
| `awaitTerminationSeconds` | Maximum wait time for the executor to terminate on shutdown |

Giving each pool a distinct thread name prefix helps identify which executor a task is running on. For instance, `app-async-1` is a thread from the default pool in the configuration above.

## 6. How Queue Capacity and Pool Size Interact

`ThreadPoolTaskExecutor` follows the rules of `ThreadPoolExecutor`. When a new task is submitted, the executor processes it in order:

1. If fewer than `corePoolSize` workers are running, create a new worker to run the task.
2. If `corePoolSize` is reached, attempt to place the task into the queue if space remains.
3. If the queue is full, create additional workers up to `maxPoolSize`.
4. If the queue is full and the pool has reached `maxPoolSize`, the task is rejected according to the rejection policy.

Example with `corePoolSize=2`, `maxPoolSize=4`, `queueCapacity=50`:

- The first two tasks can run on the two core workers.
- While both workers are busy, subsequent tasks are placed in the queue.
- Only when the queue is full does the executor increase workers beyond core to a third or fourth worker.
- When both the queue and pool are full, new tasks are rejected.

This is why queue capacity directly determines whether the pool ever expands to `maxPoolSize`. An unbounded queue typically causes the executor to keep enqueuing tasks without creating workers beyond core. In that case, `maxPoolSize` has virtually no effect.

There is no single set of parameters suited for every application. Measure processing time, submission rate, concurrency, and resources consumed by tasks to choose core size, max size, and queue capacity.

## 7. Unbounded Queues and Overload Risks

An unbounded queue capacity might seem to prevent task rejections, but it can accumulate work faster than it can be processed.

When producers continuously submit tasks and workers cannot keep up:
- The queue grows steadily.
- Wait time before a task starts increases.
- Tasks retain data and object references in memory longer.
- The application can exhaust heap space and hit `OutOfMemoryError`.
- `maxPoolSize` may go unused because the executor prioritizes the queue first.

A bounded queue establishes a load control point. When the queue fills up, the executor must scale workers or apply the rejection policy. This acts as a signal for the application to apply backpressure, rate-limit submissions, or offload work to a durable queuing system.

Do not pick an overly large queue just to avoid `TaskRejectedException`. A huge queue can mask slow processing and inflate wait times without improving throughput.

## 8. Rejection Policies When the Executor Is Overloaded

When the queue is full and the pool reaches `maxPoolSize`, `ThreadPoolExecutor` needs a policy for new tasks. Spring's `ThreadPoolTaskExecutor` defaults to `AbortPolicy`; the task is rejected and Spring surfaces the error as `TaskRejectedException`.

Common options:

| Policy | Behavior | Notes |
|---|---|---|
| `AbortPolicy` | Throws an error when unable to accept the task | Suitable when the caller needs to know the task was not accepted |
| `CallerRunsPolicy` | The submitting thread runs the task itself | Creates backpressure, but the call can execute synchronously |
| `DiscardPolicy` | Drops the new task | Use only when tasks may be dropped by design |
| `DiscardOldestPolicy` | Drops the oldest queued task and retries submitting the new task | Can lose previously queued work |

Example configuring `CallerRunsPolicy`:

~~~java
executor.setRejectedExecutionHandler(
    new ThreadPoolExecutor.CallerRunsPolicy()
);
~~~

`CallerRunsPolicy` can slow down the producer because the submitting thread must execute the task itself. However, it also alters `@Async` expectations: under overload, the caller may end up running the work on its own thread.

For critical business tasks, never silently discard them. Clearly define which tasks may be dropped, which must fail loudly, which need retries, and which must be persisted durably in a message broker or database outbox.

## 9. Defining Multiple Executors and Selecting per Method

An application can declare multiple executor beans. For example, a default pool handles general background work while `mailExecutor` is dedicated to sending emails.

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration {

    @Bean(name = "taskExecutor")
    public ThreadPoolTaskExecutor taskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(50);
        executor.setThreadNamePrefix("general-async-");
        return executor;
    }

    @Bean(name = "mailExecutor")
    public ThreadPoolTaskExecutor mailExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("mail-async-");
        return executor;
    }
}
~~~

Using the default executor:

~~~java
@Async
public CompletableFuture<String> rebuildSearchIndex() {
    return CompletableFuture.completedFuture("index rebuilt");
}
~~~

Using a dedicated executor:

~~~java
@Async("mailExecutor")
public CompletableFuture<String> sendReceipt(String orderId) {
    return CompletableFuture.completedFuture("receipt sent: " + orderId);
}
~~~

Without an `AsyncConfigurer`, Spring sees multiple `TaskExecutor` beans and cannot pick a unique bean. The bean named `taskExecutor` serves as the fallback choice per Spring Framework's convention. The `sendReceipt` method specifies `mailExecutor`, so it is routed to that pool.

Splitting pools makes workloads more independent. For instance, if the email service slows down, `mailExecutor`'s queue grows while the index processing pool retains its own resources. Still, all pools share CPU, heap, database connections, and network bandwidth; creating more pools does not increase the machine's total resources.

## 10. Choosing Executors by Workload Type

Pool separation should reflect the resources the work consumes.

**I/O-bound:** HTTP calls, sending emails, reading files, or waiting on database responses spend significant time waiting. You may need more concurrent tasks than CPU cores, yet still stay bounded by connection pools and external service limits.

**CPU-bound:** image compression, encryption, or heavy computation continuously consumes CPU. Excess threads can increase context switching and CPU contention. Pools are usually sized close to CPU capacity and workload characteristics.

**Low-priority tasks:** reporting, background sync, or index rebuilding can use a dedicated pool so they do not crowd out critical request-handling threads.

When designing multiple pools, answer:
- Which tasks can run concurrently?
- Which tasks must preserve ordering?
- How many tasks may wait in the queue?
- What concurrency or rate limits do downstream dependencies have?
- Under overload, may tasks be rejected, run on the caller, or must they be persisted?
- On application shutdown, how long do in-flight tasks have to finish?

Do not split pools solely by module name if those modules still contend for the same limited resource. Split according to isolation goals and execution characteristics.

## 11. AsyncConfigurer for Customizing the Default Executor

If you want to supply the default executor programmatically rather than relying on bean lookup, a configuration class can implement `AsyncConfigurer`.

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration implements AsyncConfigurer {

    @Bean
    @Override
    public Executor getAsyncExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(3);
        executor.setMaxPoolSize(6);
        executor.setQueueCapacity(80);
        executor.setThreadNamePrefix("configured-async-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(20);
        return executor;
    }

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (exception, method, params) -> {
            System.err.println(
                "Async method failed: " + method.getName()
                + ", error=" + exception.getMessage()
            );
        };
    }
}
~~~

In this example, `getAsyncExecutor()` is declared as `@Bean`. Therefore, `ThreadPoolTaskExecutor` has its lifecycle managed by Spring and initializes/shuts down automatically; there is no need to call `initialize()` manually.

`AsyncConfigurer` also lets you supply an `AsyncUncaughtExceptionHandler` for `@Async` methods returning `void`. If a method returns `Future` or `CompletableFuture`, the caller can observe errors via the future. With `void`, exceptions cannot propagate directly back to the caller, and by default Spring only logs them if no custom handler is configured.

`AsyncConfigurer` configuration classes are initialized early during `ApplicationContext` bootstrap. If you need to inject other beans into this configuration, avoid pulling in unnecessary early-initialized dependencies; prefer simple configuration and consider lazy dependencies when appropriate.

If you only need a single default executor, a `taskExecutor` bean can be used instead of `AsyncConfigurer`. `AsyncConfigurer` is useful when you want to control both the default executor and the uncaught exception handler together.

## 12. TaskDecorator and Thread Context

An executor thread is not the request thread that called `@Async`. Data bound to `ThreadLocal` such as the MDC logging context is not automatically copied to the worker thread.

`TaskDecorator` allows wrapping the `Runnable` before the executor runs the task. A decorator can:
1. Capture the needed context from the submitting thread.
2. Apply that context on the executing thread.
3. Run the task.
4. Restore or clear the context in `finally` to prevent leaking data to the next task reusing that thread.

Configuration example:

~~~java
executor.setTaskDecorator(task -> {
    Map<String, String> context = MDC.getCopyOfContextMap();

    return () -> {
        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            if (context == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(context);
            }
            task.run();
        } finally {
            if (previous == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(previous);
            }
        }
    };
});
~~~

This example illustrates MDC propagation; an appropriate logging dependency supporting MDC is required. For security context, request context, or transaction context, use the supported integration mechanism for that context type. Do not copy every `ThreadLocal` indiscriminately, as doing so can leak sensitive data or retain stale references.

`TaskDecorator` is useful for tracing and logging. It does not turn the executor thread into the caller's thread and does not make the caller's imperative transaction participate in the async task.

## 13. Shutdown and Executor Lifecycle

Because `ThreadPoolTaskExecutor` is a Spring-managed bean, it participates in shutdown lifecycle when `ApplicationContext` closes. If the application needs to wait for running tasks to complete, you can configure:

~~~java
executor.setWaitForTasksToCompleteOnShutdown(true);
executor.setAwaitTerminationSeconds(30);
~~~

Keep these distinctions in mind:
- Accepted tasks can continue executing during shutdown depending on configuration.
- Wait time is bounded; long-running tasks may still not finish before the process exits.
- New tasks can be rejected once the executor has begun shutting down.
- There is no guarantee that accepted tasks will be recovered if the process is killed abruptly.

If tasks must not be lost, must retry after restarts, or must be distributed across multiple instances, an in-memory executor is not a durable queue. Consider a message broker, persistent job store, or transactional outbox.

## 14. Spring Framework and Spring Boot Have Different Defaults

This is an easily confused difference.

In plain Spring Framework, if there is no `AsyncConfigurer`, no unique `TaskExecutor`, and no `Executor` bean named `taskExecutor`, the fallback is `SimpleAsyncTaskExecutor`. This implementation does not reuse threads like a thread pool.

Spring Boot has its own auto-configuration for task execution. When no custom `Executor` bean exists, Boot can supply a default `AsyncTaskExecutor`; standard configuration uses `ThreadPoolTaskExecutor`, while virtual threads configuration may use `SimpleAsyncTaskExecutor` with Java 21+. Exact rules and beans depend on the Boot version and application configuration.

Therefore:
- The example in this article uses plain Spring Framework 6.2.0 and declares `taskExecutor` explicitly.
- Do not infer Spring Boot's defaults from Spring Framework's defaults.
- When using Boot, consult the documentation for your specific Boot version and inspect `AsyncConfigurer`, `taskExecutor`, `applicationTaskExecutor`, and active auto-configurations.
- If multiple integrations such as MVC, WebFlux, GraphQL, and `@Async` share executors, verify bean names and qualifiers per Boot conventions.

## 15. Runnable Example with Java 17+ and Spring Framework 6.2.0

This example creates two executors:
- `taskExecutor` as the default executor for `@Async` methods without a qualifier.
- `mailExecutor` solely handling methods annotated with `@Async("mailExecutor")`.

The program calls both methods through the bean proxy provided by `ApplicationContext`. The returned strings include the thread name so you can observe the actual executor used.

### 15.1. Project Structure

~~~text
spring-async-executors/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── async/
                        └── AsyncExecutorDemo.java
~~~

### 15.2. Maven Configuration

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>spring-async-executors</artifactId>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 15.3. Demonstration Program

`src/main/java/com/example/async/AsyncExecutorDemo.java`:

~~~java
package com.example.async;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncExecutorDemo {

    public static class AsyncJobService {

        @Async
        public CompletableFuture<String> runDefault(String jobName) {
            String result = "default " + jobName
                    + " on " + Thread.currentThread().getName();

            return CompletableFuture.completedFuture(result);
        }

        @Async("mailExecutor")
        public CompletableFuture<String> sendMail(String recipient) {
            String result = "mail " + recipient
                    + " on " + Thread.currentThread().getName();

            return CompletableFuture.completedFuture(result);
        }
    }

    @Bean(name = "taskExecutor")
    public ThreadPoolTaskExecutor taskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("default-async-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }

    @Bean(name = "mailExecutor")
    public ThreadPoolTaskExecutor mailExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(30);
        executor.setThreadNamePrefix("mail-async-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }

    @Bean
    public AsyncJobService asyncJobService() {
        return new AsyncJobService();
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             AsyncExecutorDemo.class)) {

            AsyncJobService service =
                    context.getBean(AsyncJobService.class);

            System.out.println(
                    "caller thread=" + Thread.currentThread().getName());

            String defaultResult =
                    service.runDefault("rebuild-index").join();

            System.out.println("default result=" + defaultResult);

            String mailResult =
                    service.sendMail("customer@example.test").join();

            System.out.println("mail result=" + mailResult);
        }
    }
}
~~~

Both `ThreadPoolTaskExecutor` beans have their lifecycles managed by Spring. Because the context has multiple `TaskExecutor` beans, Spring cannot select a unique `TaskExecutor` bean; the bean named `taskExecutor` becomes the default executor per Spring Framework rules. The `sendMail` method specifies `mailExecutor`, so it uses its own pool.

Both methods return `CompletableFuture`. Calling `join()` in `main` is solely so the program waits for results and prints stdout in an easily observable order; in a real application, compose futures along the appropriate processing flow instead of blocking the caller immediately after submission.

### 15.4. Running the Program

From the directory containing `pom.xml`:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=com.example.async.AsyncExecutorDemo
~~~

Expected stdout:

~~~text
caller thread=main
default result=default rebuild-index on default-async-1
mail result=mail customer@example.test on mail-async-1
~~~

The output confirms:
- `runDefault` uses the default executor `taskExecutor`.
- `sendMail` uses `mailExecutor` via its qualifier.
- Both executors have distinct thread name prefixes.
- The caller receives a `CompletableFuture` and obtains the result once the task finishes.

The example runs only one task per pool, so the thread suffix is `1`. Under real workload, multiple tasks may run on different workers and completion order is not guaranteed.

## 16. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Desired executor not found | Multiple `TaskExecutor` beans and no matching `taskExecutor` bean | Declare an explicit default executor or `AsyncConfigurer` |
| Method always runs on default executor | `@Async` missing qualifier or wrong qualifier | Use the exact `@Async("beanName")` |
| Assuming `applicationTaskExecutor` is always default | Confusing Spring Boot conventions with Spring Framework | Check the exact framework and Boot version |
| Fallback spawns many threads | Spring falls back to `SimpleAsyncTaskExecutor` | Declare a bounded `ThreadPoolTaskExecutor` |
| Raising `maxPoolSize` does not scale pool | Unbounded or overly large queue | Use a bounded queue and measure load |
| Queue grows continuously | Producer faster than consumer | Throttle submissions, scale throughput cleanly, or use a broker |
| Tasks get rejected | Both queue and `maxPoolSize` are full | Choose rejection policy and handle `TaskRejectedException` |
| Caller unexpectedly runs the task | Using `CallerRunsPolicy` | Understand backpressure and impact on caller latency |
| Tasks lost on abrupt shutdown | Executor only holds tasks in memory | Use a message broker or persistent job mechanism |
| Thread context lost | `ThreadLocal` does not cross executor boundary | Use `TaskDecorator` or proper integration |
| Executor fails to shut down cleanly | Bean lifecycle or wait policy misconfigured | Let Spring manage the bean and configure shutdown explicitly |
| Async exceptions go unobserved | `void` method has no `Future` | Use `AsyncUncaughtExceptionHandler` and logging/metrics |

## 17. Implementation Checklist

- [ ] Identify the default executor according to plain Spring Framework vs. Spring Boot.
- [ ] If using `AsyncConfigurer`, verify which default `getAsyncExecutor()` selects.
- [ ] If not using `AsyncConfigurer`, ensure a unique `TaskExecutor` or an explicit `taskExecutor` bean exists.
- [ ] Each `@Async` qualifier points to the right `Executor` bean.
- [ ] `ThreadPoolTaskExecutor` has suitable core size, max size, and queue capacity.
- [ ] Queue is bounded when workload requires memory control.
- [ ] Rejection policy matches task criticality.
- [ ] Thread name prefixes differ across pools.
- [ ] Exceptions are observed via `Future` or `AsyncUncaughtExceptionHandler`.
- [ ] `ThreadLocal` context is propagated and cleaned up intentionally.
- [ ] Shutdown policy matches task completion windows.
- [ ] Work requiring durability is stored in a broker or persistent store, not solely in executor memory.

## 18. Summary

In Spring Framework 6.2, `@Async` uses the executor configured when async processing is enabled. If an `AsyncConfigurer` is present, `getAsyncExecutor()` supplies the default. Otherwise, Spring searches for a unique `TaskExecutor`, then an `Executor` bean named `taskExecutor`; if neither exists, it falls back to `SimpleAsyncTaskExecutor`. A method can select a different executor with `@Async("beanName")`.

`ThreadPoolTaskExecutor` is suited when worker and queue bounds are needed. The executor fills core threads first, then the queue, and only then scales workers beyond core up to max; if both the queue and pool are full, tasks are rejected. An unbounded queue can grow memory usage and prevent `maxPoolSize` from taking effect.

Partition pools by workload characteristics, configure rejection and shutdown explicitly, and monitor exceptions and thread context. Spring Boot has its own executor auto-configuration, so always verify the exact version and bean conventions in use.

## 19. References

- Spring Framework 6.2 — EnableAsync Javadoc:
  https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html
- Spring Framework 6.2 — AsyncConfigurer Javadoc:
  https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/AsyncConfigurer.html
- Spring Framework 6.2 — Task Execution and Scheduling:
  https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html
- Spring Framework 6.2 — ThreadPoolTaskExecutor Javadoc:
  https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Boot — Task Execution and Scheduling:
  https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html
# AsyncUncaughtExceptionHandler in Spring Framework Application Events

## 1. The Problem: When an Asynchronous Listener Fails, Who Receives the Exception?

Spring lets an event-handling method run asynchronously by combining `@EventListener` and `@Async`. With `@EnableAsync` enabled and the method invoked via Spring's proxy mechanism, the event publication call can finish after handing the work off to an executor, while the listener method is still processing on another thread.

Suppose a listener sends notifications:

~~~java
@Async
@EventListener
public void notifyCustomer(OrderPlaced event) {
    throw new IllegalStateException("Notification service temporarily unavailable");
}
~~~

*This is an illustrative snippet inside a Spring bean; `OrderPlaced` is an application-defined event type.*

Two important facts follow here:

- The `notifyCustomer(...)` method returns `void`, so the publisher does not receive a `Future` to inspect the result or exception.
- An exception thrown **on the asynchronous execution thread** is not normally thrown back to `ApplicationEventPublisher.publishEvent(...)`, which has already handed the work to the executor.

**`AsyncUncaughtExceptionHandler` is Spring's interface for handling uncaught exceptions from `@Async` methods with a `void` return type.** It lets the application log errors, include method/parameter details, emit metrics, or send alerts when background work fails.

The name "uncaught" means exceptions **not caught and handled by the async method itself**, not every exception anywhere in the JVM.

~~~text
Publisher                       Executor / background thread
    |                                        |
    | publishEvent(OrderPlaced)              |
    |       |                                |
    |       +--- @EventListener @Async ------> listener(event)
    |                                        |    |
    | publishEvent(...) returns              |    X throw IllegalStateException
    |                                        |    |
    |                                        +--> AsyncUncaughtExceptionHandler
    |                                                |
    |                                                +--> log / metric / alert
    |                                                     (does not auto-retry)
~~~

In this example, the application can still continue processing the initial request even if sending the notification fails. That is precisely why you must **observe and decide how to handle errors** on the asynchronous side, rather than treating a normal return from the publisher as a sign that every listener succeeded.

## 2. The AsyncUncaughtExceptionHandler Contract

The interface resides in package `org.springframework.aop.interceptor`:

~~~java
public interface AsyncUncaughtExceptionHandler {
    void handleUncaughtException(
            Throwable ex,
            java.lang.reflect.Method method,
            Object... params);
}
~~~

This is an **abbreviated API signature for explanation**, not code redefining the interface yourself.

| Parameter | Meaning | Useful Usage |
| --- | --- | --- |
| `Throwable ex` | The error escaping the `void` `@Async` method. | Inspect exception type, message, stack trace, and root cause. |
| `Method method` | The asynchronous method that failed. | Log method name or handler location for tracing. |
| `Object... params` | The arguments passed to that method. | Extract event ID, order ID, or correlation ID when appropriate. |

The handler returns `void`. Its execution cannot become a return value of `publishEvent(...)` and does not establish a reverse error-reporting channel back to the publisher.

Example custom handler used in Spring configuration:

~~~java
public final class LoggingAsyncExceptionHandler
        implements AsyncUncaughtExceptionHandler {

    @Override
    public void handleUncaughtException(
            Throwable ex, Method method, Object... params) {
        System.err.println("Async failed in " + method.getName()
                + ": " + ex.getMessage());
    }
}
~~~

*This illustrative snippet requires importing `java.lang.reflect.Method` and `org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler`.*

It can be implemented as a dedicated class or a lambda since it is a functional interface. In practice, use a logger with stack traces, task identifiers, and metrics; avoid logging the entirety of `params` if they contain passwords, tokens, or personal data.

## 3. When Is the Handler Called, and When Is It Not?

Distinguish by where processing runs and the **return type of the `@Async` method**:

| Scenario | Where the Error Is Received/Observed |
| --- | --- |
| `@Async public void doWork(...)` throws an uncaught exception | The `AsyncUncaughtExceptionHandler` configured for `@Async`. |
| `@Async @EventListener public void onEvent(...)` throws an uncaught exception | The `@Async` mechanism's `AsyncUncaughtExceptionHandler`. |
| `@Async` method returns `Future<T>` | `Future.get()` reports failure, typically as `ExecutionException`. |
| `@Async` method returns `CompletableFuture<T>` | The Future completes in a failed state; handleable via `whenComplete`, `handle`, `exceptionally`, or `join`. |
| Standard synchronous listener throws an exception | The error can propagate through the multicaster back to `publishEvent(...)` if uncaught. |
| Error is caught and fully handled inside the listener | No uncaught exception remains for `AsyncUncaughtExceptionHandler` to receive. |
| Task is rejected by the executor upon submission | This is a **task-submission** error; it can surface on the calling thread, not from the running method body. |

With Spring `@Async`'s defaults, exceptions from `void` methods are logged by the default handler. **The default handler does not replace task persistence or automatic retries.**

Condition to remember: placing `@Async` on a method is not enough if that method is self-invoked via `this.someMethod()` within the same bean; direct calls on the target object instead of the proxy can bypass asynchronous execution in default proxy mode. `@EventListener` must be on a Spring-managed bean and `@EnableAsync` must be enabled.

## 4. Complete Java 17+ Example: Failing Listener and Invoked Custom Handler

This example uses Spring Framework 6.2.9, Java 17+, and Maven. The program creates an `@Async @EventListener` that intentionally throws `IllegalStateException`, configures a handler via `AsyncConfigurer`, and verifies that the publisher continues while the handler processes the error on another thread.

Structure:

~~~text
async-exception-demo/
├── pom.xml
└── src/main/java/AsyncUncaughtExceptionDemo.java
~~~

Contents of `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>async-exception-demo</artifactId>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Contents of `src/main/java/AsyncUncaughtExceptionDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class AsyncUncaughtExceptionDemo {

    private static final CountDownLatch RELEASE = new CountDownLatch(1);
    private static final CountDownLatch HANDLED = new CountDownLatch(1);

    public record OrderPlaced(String orderId) {}

    public static void main(String[] args) throws InterruptedException {
        try (var context =
                     new AnnotationConfigApplicationContext(DemoConfig.class)) {

            System.out.println("Publisher: before publishEvent");
            context.publishEvent(new OrderPlaced("OD-7"));
            System.out.println("Publisher: after publishEvent");

            // Only to guarantee deterministic stdout ordering for demonstration.
            RELEASE.countDown();

            if (!HANDLED.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Handler did not run in time");
            }
            System.out.println("Publisher: handler has run");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class DemoConfig implements AsyncConfigurer {

        @Bean
        public OrderListener orderListener() {
            return new OrderListener();
        }

        @Bean(name = "taskExecutor")
        public ThreadPoolTaskExecutor taskExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("event-");
            return executor; // Spring initializes and shuts down the executor as a bean.
        }

        @Override
        public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
            return (ex, method, params) -> {
                OrderPlaced event = (OrderPlaced) params[0];
                System.out.println("Handler: " + method.getName()
                        + "(" + event.orderId() + "): " + ex.getMessage());
                HANDLED.countDown();
            };
        }
    }

    public static class OrderListener {

        @Async
        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            try {
                RELEASE.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("Thread was interrupted", ex);
            }

            System.out.println("Listener: received " + event.orderId());
            throw new IllegalStateException(
                    "processing failed " + event.orderId());
        }
    }
}
~~~

From the directory containing `pom.xml`, run with Java 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=AsyncUncaughtExceptionDemo
~~~

Lines printed by the program itself to stdout, excluding any Maven or framework logs:

~~~text
Publisher: before publishEvent
Publisher: after publishEvent
Listener: received OD-7
Handler: onOrderPlaced(OD-7): processing failed OD-7
Publisher: handler has run
~~~

### Result Explanation

1. `@EnableAsync` activates `@Async` processing infrastructure. The `taskExecutor` bean is the executor discovered by `@Async` infrastructure by naming convention; task threads carry the `event-` prefix.
2. `@EventListener` registers `onOrderPlaced` to receive `OrderPlaced`. `OrderPlaced` does not have to extend `ApplicationEvent`; Spring supports payload-based events.
3. When the publisher calls `publishEvent(...)`, Spring hands off execution of the `@Async` method to the executor. Thus the publisher can print "after publishEvent" without waiting for the listener body to finish.
4. `RELEASE` is a synchronization gate **solely for the example**: it forces the listener to wait until the publisher prints the second line. That makes stdout ordering deterministic regardless of OS thread scheduling speed.
5. The listener prints the received event line, then throws `IllegalStateException`. Because the method returns `void`, the error is routed to `getAsyncUncaughtExceptionHandler()`, along with the `Method` and the actual arguments passed to it.
6. The handler prints the error and calls `HANDLED.countDown()`. `main` waits for that signal so the program terminates after the handler completes.

In production code, **do not use a `RELEASE` latch to force async tasks to wait for the publisher**. This latch only makes the example output deterministic and avoids misleading readers into thinking async execution always completes in stdout order.

## 5. Practical Handler Configuration with AsyncConfigurer

A clean way to supply a shared handler for Spring-managed `@Async` methods is to implement `AsyncConfigurer` in a `@Configuration` class:

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration implements AsyncConfigurer {

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (ex, method, params) -> {
            // Log with stack trace, method name, and task identifier.
            // Emit metrics or trigger alerts as needed.
        };
    }
}
~~~

*This is a conceptually standalone configuration snippet; proper Spring imports are required. It cannot run as a complete program unless placed inside a Spring application.*

`getAsyncUncaughtExceptionHandler()` configures the exception path for `@Async`. To customize the executor as well, configure `getAsyncExecutor()` on `AsyncConfigurer` or declare executor beans using names/qualifiers supported by Spring.

When task groups require different error rules, place a `try/catch` directly inside the listener and call a dedicated error-handling service, or organize separate executors and services. A shared `AsyncUncaughtExceptionHandler` is generally suitable for unexpected errors needing logs, metrics, and alerts, but does not replace business compensation logic.

## 6. AsyncUncaughtExceptionHandler vs. Event Multicaster's ErrorHandler

Spring has **two distinct extension points** that are easily confused because both "handle event errors":

| Criterion | `AsyncUncaughtExceptionHandler` | `SimpleApplicationEventMulticaster.setErrorHandler(...)` |
| --- | --- | --- |
| Layer | Spring's `@Async` method invocation infrastructure. | Multicaster infrastructure invoking `ApplicationListener`. |
| Typical use | Exceptions from `void` `@Async` methods, including `@Async @EventListener`. | Exceptions thrown directly while the multicaster invokes a listener. |
| Configuration | `AsyncConfigurer`, or equivalent `@Async` configuration. | `applicationEventMulticaster` bean configured with `setErrorHandler`. |
| Received arguments | `Throwable`, `Method`, and method arguments. | `Throwable` from the listener invocation. |
| Impact on publisher | Exceptions occurring after task handoff do not automatically propagate to the publisher. | For synchronous listeners, the handler may absorb or rethrow the error, affecting the publish call. |

**Important example:** The default multicaster invokes an `@EventListener` adapter synchronously, while the target method has `@Async`. The adapter/proxy submits the work and returns before the method body runs. If the method body later throws an error, `AsyncUncaughtExceptionHandler` handles it; the multicaster's `ErrorHandler` typically never sees that exception.

If you replace the multicaster itself with a `SimpleApplicationEventMulticaster` configured with `setTaskExecutor(...)`, listener invocation moves to another thread at the multicaster layer, and `setErrorHandler(...)` becomes the error-handling point for that listener invocation. Do not assume both configuration styles trigger the same handler or follow the same exception path.

## 7. Contrast with Future and CompletableFuture Exceptions

`@Async` does not require every method to return `void`. A service method can return `Future<T>` or `CompletableFuture<T>` so the caller knows whether the task succeeded or failed.

Illustrative snippet in a Spring service bean:

~~~java
@Async
public java.util.concurrent.CompletableFuture<String> rebuildIndex(String id) {
    if (id.isBlank()) {
        throw new IllegalArgumentException("Empty ID");
    }
    return java.util.concurrent.CompletableFuture.completedFuture(
            "indexed:" + id);
}
~~~

*This is an illustrative method, not a runnable standalone program.*

When `id` is blank, the async result completes with an exception. The `CompletableFuture` receiver can handle it as follows:

~~~java
future.whenComplete((value, error) -> {
    if (error != null) {
        // Record the failure or apply a recovery policy.
    }
});
~~~

`AsyncUncaughtExceptionHandler` is **not** the primary place to handle exceptions from `@Async` methods returning `Future` or `CompletableFuture`; errors are reflected in the Future result. `get()` typically throws `ExecutionException` wrapping the cause, while `join()` throws `CompletionException`.

In the Spring Application Events model, `publishEvent(...)` does not return an aggregated `CompletableFuture` for `@EventListener` methods. Therefore, you cannot assume the publisher can call `join()` to know when all listeners have finished. If business logic requires a result, consider directly calling a Future-returning service or designing a dedicated task-tracking mechanism.

## 8. Impact on Transactions, Data, and Reliability

Because an `@Async` listener executes on a different thread:

- An exception in an async listener normally **does not cause the publisher method to fail** once the task has been successfully submitted.
- The `@Transactional` transaction and `ThreadLocal` context on the publisher thread **are not automatically carried over** to the listener thread. A listener may read data before the publisher's transaction commits, depending on timing and isolation level.
- The handler is invoked when an error occurs, but **does not automatically roll back the publisher's transaction** or undo side effects that have already happened.
- The handler does not automatically provide retries, durable message persistence, or cross-host event delivery; if the JVM stops or the executor loses tasks, in-memory events have no built-in replay mechanism.
- `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` can help if processing should only occur after a transaction succeeds; when combined with `@Async`, you still need dedicated error monitoring and execution guarantees.

For auxiliary tasks like statistics, logging, or best-effort notifications, a handler can log and alert. For mandatory work such as charging payments, deducting inventory, or cross-system synchronization, consider direct calls, bounded retries, durable queues, or a transactional outbox so work is not silently lost.

## 9. Implementation and Error-Observability Principles

1. **Log the root cause.** Log the exception with its stack trace and method name. Printing only `ex.getMessage()` as in the example is insufficient for real operations.
2. **Attach correlation IDs.** Extract event/order IDs or correlation IDs from `params`. Avoid logging entire payloads if they contain sensitive information.
3. **Count and alert.** Increment failure metrics by listener name and error type, and set alert thresholds.
4. **Separate business errors from system errors.** For example, invalid data may require recording for manual intervention; transient timeouts may suit retries with backoff.
5. **Never retry indefinitely inside the handler.** The handler does not inherently know which tasks are safe to re-execute; retries must consider idempotency, attempt limits, and data state.
6. **Monitor the executor.** Full queues or rejected tasks happen before the listener runs, so monitor executor metrics and task submission failures too.
7. **Verify the proxy mechanism.** `@EnableAsync` must be enabled; the listener must be a Spring bean; methods must be proxiable; internal calls via `this` do not trigger `@Async` in standard proxy mode.

Do not rely on default logging as a recovery mechanism. An exception may be logged while the task still failed and was never retried.

## 10. Self-Check Questions

**1.** A `void` `@Async @EventListener` throws `IllegalStateException` after the publisher has called `publishEvent(...)`. Does the publisher receive that exception directly?

**Answer:** Usually no. The exception occurs on the `@Async` task thread; `AsyncUncaughtExceptionHandler` is the handling point designed for `void` methods.

**2.** If the listener catches the exception with `try/catch` and handles it completely, does the handler receive that error?

**Answer:** No. No uncaught error escapes the method to reach the handler.

**3.** If `@Async` returns `CompletableFuture<String>`, where should exceptions be retrieved from?

**Answer:** From the Future result using `get()`, `join()`, or callbacks like `whenComplete(...)`. `AsyncUncaughtExceptionHandler` does not handle Future-returning methods the way it handles `void` methods.

**4.** Is configuring `SimpleApplicationEventMulticaster.setErrorHandler(...)` equivalent to configuring `AsyncConfigurer.getAsyncUncaughtExceptionHandler()`?

**Answer:** No. The two handlers sit at different layers: one at the multicaster's listener invocation layer, and one at the `@Async` method execution layer.

**5.** Does the handler receiving an exception mean the event was retried or the publisher's transaction was rolled back?

**Answer:** No. The handler is solely an exception hook; retries, transaction compensation, and delivery guarantees must be designed separately.

## References

- [Spring Framework Reference — Exception Management with @Async](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): how `@Async` handles exceptions for `void` and `Future`.
- [Spring Framework Reference — Asynchronous Event Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): limitations of `@Async @EventListener` and relation to `publishEvent(...)`.
- [Javadoc — AsyncUncaughtExceptionHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/interceptor/AsyncUncaughtExceptionHandler.html): the `handleUncaughtException(Throwable, Method, Object...)` contract.
- [Javadoc — AsyncConfigurer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/AsyncConfigurer.html): configuring executors and handlers for `@Async`.
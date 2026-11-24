# Exceptions in Spring Framework Async Listeners

## Objectives

When an `@EventListener` method is also annotated with `@Async`, Spring offloads event processing to a `TaskExecutor`. The publisher emits the event and continues its work; the listener runs on a worker thread. Because the listener no longer runs on the thread that called `publishEvent`, exceptions thrown during asynchronous processing do not propagate back to the publisher.

For async listeners with a `void` return type, Spring provides `AsyncUncaughtExceptionHandler` to receive exceptions that have no `Future` handle. If no custom handler is configured, Spring uses a default handler to log them. This mechanism helps observe errors, but does not automatically retry, roll back the publisher's transaction, or persist work to run again after a process restart.

This lesson helps you:

- Distinguish exceptions in synchronous listeners from those in async listeners.
- Understand `@Async` exception flow for `void` and `Future` return types.
- Configure `AsyncUncaughtExceptionHandler` via `AsyncConfigurer`.
- Log sufficient context without exposing sensitive data.
- Catch errors inside a listener, publish failure events, and design controlled retries.
- Distinguish task submission errors from errors occurring on the worker thread.
- Write a runnable Java 17 / Spring Framework 6.2 example and test it using latches.

## 1. Why Don't Exceptions Return to the Publisher?

With a synchronous event listener, `publishEvent` invokes the listener on the current thread. If the listener throws a runtime exception and it is not handled, the error can propagate back to the `publishEvent` call site.

When `@Async` is added, Spring uses a proxy to submit the method call to an executor. The publisher only performs dispatch and submission; a worker thread executes the listener body afterward.

Execution flow:

```text
Publisher thread
    |
    | publishEvent(event)
    v
Spring event dispatcher
    |
    | call async proxy / submit task
    v
TaskExecutor queue
    |
    | worker thread executes
    v
@Async @EventListener method
    |
    +---- completes normally
    |
    +---- throws exception
             |
             v
       Async exception handling
```

When a listener runs asynchronously:

- `publishEvent(...)` does not wait for the listener body to finish.
- Exceptions thrown on the worker thread are not thrown back to the thread that published the event.
- A `try/catch` around `publishEvent` will not catch exceptions thrown later inside the listener.
- The publisher does not know whether the listener succeeded or failed unless the application builds an explicit feedback channel.
- The publisher's transaction, `ThreadLocal`, and logging context do not automatically transfer to the worker thread.

This is a property of asynchronous processing, not a bug in the event publisher. If business logic needs to know the outcome, design an explicit feedback mechanism such as job status, failure events, callbacks, or message results.

## 2. Two Ways Exceptions Are Handled by @Async Return Type

Spring differentiates `@Async` methods returning `void` from methods returning a `Future` type.

| Return type | How is the exception handled? | Who can observe it? |
|---|---|---|
| `void` | No `Future` to hold the exception; forwarded to `AsyncUncaughtExceptionHandler` | Configured handler; Spring logs by default |
| `Future<T>` | Exception is stored in the `Future` and surfaces when caller invokes `get()` | Caller holding the `Future` handle |
| `CompletableFuture<T>` | `Future` completes exceptionally; can be handled with `whenComplete`, `handle`, or `exceptionally` | Caller holding the `CompletableFuture` handle |

### Async Methods Returning void

Example:

```java
@Async("eventExecutor")
@EventListener
public void onPaymentRequested(PaymentRequested event) {
    paymentProcessor.process(event); // May throw an exception.
}
```

Because the method returns `void`, there is no `Future` for a caller to read. Spring calls `AsyncUncaughtExceptionHandler.handleUncaughtException(...)` when an exception escapes the method.

If no handler is configured, Spring uses the default `SimpleAsyncUncaughtExceptionHandler` to log the exception. Production applications should normally configure a custom handler to include method name, event type, event ID, or correlation ID in logs/metrics.

### Async Methods Returning Future

With a service method called directly through a Spring proxy:

```java
@Async("eventExecutor")
public CompletableFuture<PaymentResult> processAsync(
        PaymentRequested event) {
    PaymentResult result = processor.process(event);
    return CompletableFuture.completedFuture(result);
}
```

The caller can hold the handle:

```java
CompletableFuture<PaymentResult> future =
        paymentService.processAsync(event);

future.whenComplete((result, error) -> {
    if (error != null) {
        logger.error("Payment processing failed", error);
    }
});
```

If the method throws an exception, the `Future` completes exceptionally. The caller can observe the error via callbacks or `get()`.

However, when a method is invoked as an async event listener, the publisher does not receive the listener's `Future` from `publishEvent`. Do not design event listeners assuming the publisher can call `get()` or `whenComplete` on the listener's return value. If a `Future` handle is needed, move the work into an async service method and invoke that method directly from the component tracking the result.

## 3. What Is AsyncUncaughtExceptionHandler?

`AsyncUncaughtExceptionHandler` is Spring's interface for handling exceptions that escape `@Async` methods with a `void` return type.

The interface has one method:

```java
void handleUncaughtException(
        Throwable ex,
        Method method,
        Object... params
);
```

The handler receives three pieces of information:

- `ex`: the exception or throwable that escaped the async method.
- `method`: the method that executed and threw the error.
- `params`: the arguments passed to the method, typically containing the event object as the first argument for single-parameter listeners.

This handler is suited for logging, metrics, tracing, and alerting. Do not put all business recovery logic inside the handler, because it is a global error hook for `void` async methods, not exclusive to event listeners.

### Configuring via AsyncConfigurer

A custom handler can be supplied via `AsyncConfigurer` when `@EnableAsync` is enabled:

```java
@Configuration
@EnableAsync
class AsyncConfiguration implements AsyncConfigurer {

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (ex, method, params) -> {
            logger.error(
                    "Async method {} failed",
                    method.toGenericString(),
                    ex
            );
        };
    }
}
```

`AsyncConfigurer` also lets you provide a default executor via `getAsyncExecutor()`. If a listener needs a dedicated executor, you can name a bean and specify `@Async("eventExecutor")`.

If you have multiple task groups with different policies, separate executors by purpose: e.g., `eventExecutor`, `emailExecutor`, or `reportExecutor`. The handler can remain a shared policy; if specific business recovery is needed, catch the exception inside the listener and invoke the corresponding recovery component.

## 4. Configuring a Handler with Event Context

A useful handler logs the method name, error type, and event identifier. Avoid logging the entire payload, as events may contain personal data, tokens, or sensitive business fields.

Example:

```java
@Bean
AsyncConfigurer asyncConfigurer() {
    return new AsyncConfigurer() {

        @Override
        public AsyncUncaughtExceptionHandler
                getAsyncUncaughtExceptionHandler() {

            return (ex, method, params) -> {
                Object firstArgument =
                        params.length > 0 ? params[0] : null;

                logger.error(
                        "Async listener failed: method={}, argumentType={}",
                        method.getName(),
                        firstArgument == null
                                ? "none"
                                : firstArgument.getClass().getSimpleName(),
                        ex
                );
            };
        }
    };
}
```

For an event class with an ID, you can safely extract the ID after checking its specific type:

```java
if (firstArgument instanceof PaymentRequested event) {
    logger.error(
            "Payment listener failed: paymentId={}",
            event.paymentId(),
            ex
    );
}
```

Do not blindly cast every parameter to a fixed event class if the handler is shared across multiple async methods. Check the type first, or log the method signature and argument type instead of making assumptions.

Recommended log fields:

- Method name and related bean/component.
- Event type and event ID if available.
- Safely propagated correlation ID or trace ID.
- Exception class, message, and stack trace.
- Executor/thread name when investigating overload.

Avoid logging passwords, access tokens, payment card data, or full payloads.

## 5. Runnable Example: Async Listener Throws an Exception and Handler Catches It

The example below uses Java 17 and Spring Framework 6.2.8 without Spring Boot. A `void` listener runs on a dedicated executor and intentionally throws `IllegalStateException`. A custom `AsyncUncaughtExceptionHandler` captures the exception and wakes the main thread via a latch so the example produces deterministic output.

Project structure:

```text
async-listener-exception-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── AsyncListenerExceptionDemo.java
```

**pom.xml**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>async-listener-exception-demo</artifactId>
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
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.AsyncListenerExceptionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**src/main/java/demo/AsyncListenerExceptionDemo.java**

```java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executor;
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

public class AsyncListenerExceptionDemo {

    public static void main(String[] args) throws InterruptedException {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            CompletionGate gate = context.getBean(CompletionGate.class);

            System.out.println(
                    "publisher thread: " + Thread.currentThread().getName()
            );

            context.publishEvent(new PaymentRequested(501L));

            if (!gate.awaitStarted(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Listener did not start");
            }

            System.out.println(
                    "publishEvent returned while listener is still running"
            );

            gate.release();

            if (!gate.awaitHandled(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Async exception handler was not called"
                );
            }
        }
    }

    @Configuration
    @EnableAsync
    static class AppConfig {

        @Bean(name = "eventExecutor")
        ThreadPoolTaskExecutor eventExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("event-");
            executor.setWaitForTasksToCompleteOnShutdown(true);
            executor.setAwaitTerminationSeconds(5);
            return executor;
        }

        @Bean
        CompletionGate completionGate() {
            return new CompletionGate();
        }

        @Bean
        AsyncConfigurer asyncConfigurer(
                CompletionGate gate,
                ThreadPoolTaskExecutor eventExecutor) {

            return new AsyncConfigurer() {

                @Override
                public Executor getAsyncExecutor() {
                    return eventExecutor;
                }

                @Override
                public AsyncUncaughtExceptionHandler
                        getAsyncUncaughtExceptionHandler() {

                    return (ex, method, params) -> {
                        PaymentRequested event =
                                (PaymentRequested) params[0];

                        System.out.printf(
                                "async exception in %s: %s; paymentId=%d%n",
                                method.getName(),
                                ex.getMessage(),
                                event.paymentId()
                        );

                        gate.markHandled();
                    };
                }
            };
        }

        @Bean
        PaymentListener paymentListener(CompletionGate gate) {
            return new PaymentListener(gate);
        }
    }

    record PaymentRequested(long paymentId) {
    }

    static class CompletionGate {
        private final CountDownLatch started = new CountDownLatch(1);
        private final CountDownLatch release = new CountDownLatch(1);
        private final CountDownLatch handled = new CountDownLatch(1);

        void markStarted() {
            started.countDown();
        }

        boolean awaitStarted(long timeout, TimeUnit unit)
                throws InterruptedException {
            return started.await(timeout, unit);
        }

        void waitForRelease() {
            try {
                if (!release.await(30, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Release timed out");
                }
            }
            catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                        "Listener interrupted",
                        ex
                );
            }
        }

        void release() {
            release.countDown();
        }

        void markHandled() {
            handled.countDown();
        }

        boolean awaitHandled(long timeout, TimeUnit unit)
                throws InterruptedException {
            return handled.await(timeout, unit);
        }
    }

    static class PaymentListener {
        private final CompletionGate gate;

        PaymentListener(CompletionGate gate) {
            this.gate = gate;
        }

        @Async("eventExecutor")
        @EventListener
        public void onPaymentRequested(PaymentRequested event) {
            System.out.println(
                    "listener started: payment=" + event.paymentId()
                            + " on " + Thread.currentThread().getName()
            );

            gate.markStarted();
            gate.waitForRelease();

            throw new IllegalStateException("simulated failure");
        }
    }
}
```

Run from the directory containing `pom.xml`:

```bash
mvn -q compile exec:java
```

Stdout:

```text
publisher thread: main
listener started: payment=501 on event-1
publishEvent returned while listener is still running
async exception in onPaymentRequested: simulated failure; paymentId=501
```

Explanation:

1. `@EnableAsync` enables `@Async` method processing via Spring proxies.
2. `eventExecutor` is an executor with one worker thread whose name starts with `event-`.
3. The `onPaymentRequested` listener returns `void`, runs asynchronously, and waits on a latch before throwing an exception.
4. `publishEvent` only submits processing; the main thread does not wait for the listener body to finish.
5. When the listener throws `IllegalStateException`, Spring forwards the exception to the custom `AsyncUncaughtExceptionHandler`.
6. The handler receives the method and event parameter, prints the payment ID, and counts down the latch so the main thread exits cleanly.

The `started` and `release` latches only highlight when the publisher and listener run. In real applications, do not use latches for business coordination; use appropriate synchronization or job state tracking.

## 6. Catching Errors Inside the Listener for Business Reactions

`AsyncUncaughtExceptionHandler` is a general error handler. If each event type has its own recovery behavior, the listener can catch exceptions directly inside the method.

Example of a listener publishing a failure event:

```java
@Component
class InvoiceListener {

    private final ApplicationEventPublisher publisher;
    private final InvoiceProcessor processor;

    InvoiceListener(
            ApplicationEventPublisher publisher,
            InvoiceProcessor processor) {
        this.publisher = publisher;
        this.processor = processor;
    }

    @Async("eventExecutor")
    @EventListener
    public void onInvoiceRequested(InvoiceRequested event) {
        try {
            processor.process(event);
        }
        catch (RuntimeException ex) {
            publisher.publishEvent(
                    new InvoiceProcessingFailed(
                            event.invoiceId(),
                            ex.getClass().getSimpleName()
                    )
            );
            throw ex;
        }
    }
}
```

Here, the listener both publishes `InvoiceProcessingFailed` so other components can react and rethrows the exception so the global handler records the error. If you do not want the global handler to process an error already handled locally, you can omit the rethrow; in that case, the listener must ensure logs/metrics and failure state are recorded.

A failure event should contain minimal information such as event ID, business ID, error type, and timestamp. Avoid putting full stack traces or sensitive payloads into business events.

A failure event can also be consumed by another listener. Avoid letting a failure listener re-emit the same event type in an infinite loop; define an explicit retry policy and maximum attempt count.

## 7. Retries, Idempotency, and Persisting Failure State

An exception handler only observes errors. It does not automatically rerun the listener. If retries are needed, define an explicit policy:

- **Attempt limit:** cap the number of retries per event.
- **Backoff:** increase delay between attempts to avoid hammering a failing dependency.
- **Error classification:** separate transient errors like timeouts from invalid-data errors that cannot self-heal.
- **Idempotency:** ensure reprocessing the same event does not create duplicate side effects.
- **State tracking:** record attempt count, last attempt timestamp, and final status.
- **Dead-letter/manual recovery:** retain unprocessable events for investigation or intervention.

For critical tasks that must survive restarts, an in-memory executor is insufficient. Persist work durably with a transactional outbox or a message broker with proper acknowledgments, retries, and dead-letter queues. Consumers still need idempotency because messages may be delivered more than once.

Do not implement retries by recursively calling the listener inside the exception handler. That easily creates tight loops without backoff and makes load hard to control.

## 8. Distinguishing Execution Errors from Task Submission Errors

There are two distinct failure points:

1. **Submission errors:** the executor refuses to accept the task, for instance because the queue is full or the executor has shut down. With Spring's `ThreadPoolTaskExecutor`, executor rejections are typically wrapped as `TaskRejectedException`; this error can appear directly on the dispatch thread when Spring tries to submit the listener.
2. **Execution errors:** the task was accepted, and later the listener throws an exception on the worker thread. For `void @Async` listeners, errors go through `AsyncUncaughtExceptionHandler`.

Both failure types must be monitored separately. `SimpleApplicationEventMulticaster`'s error handler processes errors raised while the multicaster invokes listeners on the dispatch thread; it does not replace `AsyncUncaughtExceptionHandler` for exceptions occurring later on the worker thread.

To reduce submission errors:

- Use an executor with bounded threads and queue capacity.
- Set a rejection policy aligned with system requirements.
- Monitor queue depth, active threads, task rejections, and wait times.
- Do not use an unbounded queue to hide a slow consumer.
- Add backpressure or a durable queue if producers can emit faster than consumers can process.

If the executor uses `CallerRunsPolicy`, a rejected task can run on the submitting thread. This changes publisher latency and can force the publishing thread to execute the listener directly under overload; use it only when that behavior is intentionally accepted.

## 9. Transactions, ThreadLocal, and Logging Context

Async listeners run on worker threads, so they do not automatically inherit the publisher thread's transaction. If a publisher emits an event inside a database transaction, an async listener may begin executing before that transaction commits.

If the listener requires committed data:

- Use `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` to bind when the event is received.
- If data must be written in an independent transaction after commit, call a service using `Propagation.REQUIRES_NEW`.
- If work must never be lost after the transaction commits, consider a transactional outbox rather than relying solely on in-memory event callbacks.

`ThreadLocal`, MDC, and security context also do not propagate automatically to worker threads. You can pass correlation IDs in the event or configure a `TaskDecorator`/context propagation on the executor. Propagate only what is necessary and ensure context is cleared after the task finishes to prevent leaks across tasks sharing threads.

## 10. Common Pitfalls

| Mistake | Cause | Resolution |
|---|---|---|
| Wrapping `publishEvent` in try/catch to catch listener exceptions | Exception occurs later on the worker thread | Use `AsyncUncaughtExceptionHandler` or callbacks |
| Not configuring a handler for async `void` listeners | Exception has no `Future` for the caller to observe | Configure `AsyncConfigurer` and a handler |
| Assuming the handler retries automatically | Handler only receives the exception and metadata | Build bounded retries, backoff, and state tracking |
| Returning a `Future` from an async listener for the publisher to read | Event publisher does not return listener handles | Call an async service directly if a `Future` is needed |
| Using a return value to publish a follow-up event | Return-value publishing is unsupported for async listeners | Inject `ApplicationEventPublisher` and publish explicitly |
| Confusing the multicaster's `ErrorHandler` with the async handler | The two handlers catch errors at different stages | Use the right handler for dispatch errors vs. worker errors |
| Logging the full event payload | May expose sensitive data | Log only event IDs and safe metadata |
| Calling an `@Async` method via self-invocation | Internal calls bypass the proxy | Call through a Spring bean proxy |
| Not monitoring executor rejections | Full queue or shut-down executor prevents task acceptance | Monitor pool/queue and design backpressure |
| Assuming transactions/MDC propagate automatically | Worker uses a different thread | Propagate context intentionally or use `TaskDecorator` |
| Swallowing exceptions without saving state | System loses track of failed work | Record status, metrics, and have a recovery workflow |

## 11. Implementation Checklist

- [ ] `@EnableAsync` is enabled and the listener is managed by Spring.
- [ ] `@EventListener` method is invoked through a proxy, not via self-invocation.
- [ ] Appropriate executor and pool/queue bounds are selected.
- [ ] For `void`-returning listeners, `AsyncUncaughtExceptionHandler` is configured.
- [ ] Handler safely logs method, event ID/type, and exception.
- [ ] `try/catch` around `publishEvent` is not expected to catch worker errors.
- [ ] Task submission errors and listener execution errors are distinguished.
- [ ] When business reactions are needed, the listener catches errors and emits an explicit failure event.
- [ ] Retries are bounded with backoff and idempotency.
- [ ] Async return values are not used to publish follow-up events.
- [ ] Transactions, `ThreadLocal`, MDC, and security context are propagated intentionally.
- [ ] An outbox/broker is used if work must not be lost on process termination.

## Conclusion

Exceptions in async listeners do not propagate back to the publisher because the listener runs on an executor after event dispatch. For `void` `@Async` methods, Spring forwards errors to `AsyncUncaughtExceptionHandler`; for directly called async service methods returning a `Future`, the caller observes errors via the `Future`. Handlers help record failures but do not automatically retry, roll back the main transaction, or persist work durably. Choose bounded executors, separate submission errors from execution errors, publish failure events when business reactions are needed, and use retries, outboxes, and idempotency for critical tasks.

## References

- [Spring Framework 6.2 — Asynchronous Event Listeners](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — Exception Management with @Async](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [AsyncUncaughtExceptionHandler — Spring Framework 6.2.8 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/aop/interceptor/AsyncUncaughtExceptionHandler.html)
- [AsyncConfigurer — Spring Framework 6.2.8 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/scheduling/annotation/AsyncConfigurer.html)
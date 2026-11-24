# Async Listeners Returning Future in Spring Application Events

## 1. Objectives and Context

In Spring Framework, an event-handling method can use `@EventListener` to receive events and `@Async` to run work on an executor. Since Java provides `Future<T>` and `CompletableFuture<T>`, a natural question arises: **if an async listener returns a Future, does the caller of `publishEvent(...)` receive that Future to wait for the result?**

**No.** `ApplicationEventPublisher.publishEvent(...)` has a `void` return type. The event publisher has no API to return a list of listener `Future` instances. Even if a listener method declares a `Future<T>` or `CompletableFuture<T>` return type, that value does not automatically become the return value of `publishEvent`.

However, `@Async` **does support methods returning `Future` or `CompletableFuture`** when those methods are called directly through a Spring proxy. Thus, it is important to distinguish three roles:

1. **Event publisher:** publishes events via `ApplicationEventPublisher`, and does not receive a `Future` from that call.
2. **Event listener:** reacts to events; when annotated with `@Async`, its body runs on another thread. The listener method can declare `CompletableFuture<Void>`, but the publisher cannot directly obtain that handle.
3. **Async service:** a bean with an `@Async` method called directly by a caller; the caller receives `Future<T>` from the proxy to track the value, error, or completion time.

This lesson focuses on `Future` semantics in **Spring Application Events**, how to receive results safely, and key limitations of async listeners.

## 2. What Do `Future` and `CompletableFuture` Mean?

`Future<T>` in `java.util.concurrent` represents a result that may become available in the future.

- `isDone()`: indicates the task has completed per the Future contract (including cancellation or failure); it does not prove the task succeeded.
- `get()`: blocks until a result is available, which can block the thread indefinitely if the work never finishes.
- `get(timeout, unit)`: waits with a time bound; can throw `TimeoutException`, `ExecutionException`, or `InterruptedException`.
- `cancel(...)`: requests cancellation on a best-effort basis depending on the implementation; does not guarantee rolling back side effects such as database writes or external API calls.

`CompletableFuture<T>` implements `Future<T>` and also supports `CompletionStage<T>`. It provides `thenApply`, `thenCompose`, `thenAccept`, `whenComplete`, `exceptionally`, and `handle` to chain processing steps and react to results and errors without forcing the caller to block immediately.

In Spring, `@Async` allows a method to return `void`, `Future<T>`, or `CompletableFuture<T>`. You cannot arbitrarily declare `String` and expect `@Async` to wrap it into a Future automatically. Notably, code **inside the target method** typically returns an already-completed Future, such as `CompletableFuture.completedFuture(value)`; when the caller invokes it **through the proxy**, Spring provides a Future representing the overall work executed on the executor.

~~~java
// Illustrative snippet: method on a Spring bean, called through a Spring proxy.
@Async("lessonExecutor")
public CompletableFuture<String> calculate(String id) {
    String result = "done:" + id;
    return CompletableFuture.completedFuture(result);
}
~~~

Returning `completedFuture` inside the method body does not mean the caller runs synchronously: the body still executes on the executor if the call passes through the `@Async` proxy.

## 3. Combining `@EventListener` and `@Async`: Who Receives the Future?

Consider a listener declared as:

~~~java
// Illustrative snippet, not a standalone application.
@Async("lessonExecutor")
@EventListener
public CompletableFuture<Void> onOrderPlaced(OrderPlaced event) {
    process(event);
    return CompletableFuture.completedFuture(null);
}
~~~

As a method declaration, `CompletableFuture<Void>` is valid for `@Async`. When Spring invokes the method through the proxy, its body runs asynchronously. The key point, however, is that **the publisher's entry point is still `publishEvent(event)` with a `void` return type**, for example:

~~~java
publisher.publishEvent(new OrderPlaced("A-1"));
// This call does not produce a Future for the publisher.
~~~

You cannot write:

~~~java
// INVALID: does not compile, because publishEvent returns void.
CompletableFuture<Void> future = publisher.publishEvent(new OrderPlaced("A-1"));
~~~

`@EventListener` also has its own rule: a non-`void` return value from a **synchronous listener** can be used by Spring to publish a follow-up event. Spring documentation notes not to rely on the return value of an **asynchronous listener** to publish follow-up events; if needed, inject `ApplicationEventPublisher` and explicitly call `publishEvent(new FollowUpEvent(...))`. Do not treat a `Future<T>` from a listener as an implicit request/response protocol between publisher and listener.

**Choosing an approach by goal:**

| Need | Appropriate Approach |
| --- | --- |
| Fire-and-forget; listener logs or sends notifications independently | `@Async @EventListener void handle(Event e)` with logging, retries, and monitoring |
| Caller explicitly wants to retrieve an async result | Directly call an `@Async` service returning `CompletableFuture<T>` |
| Still want events, yet caller needs an in-process result | Design an explicit reply channel (e.g., `CompletableFuture<T>` attached to the event or a correlation-ID map); only suitable within the same process with clear completion/error conventions |
| Ordered work, retries, and durability across processes | Orchestrating workflow/service, durable queue, or broker with correlation and acknowledgment |

## 4. Complete Java 17+ Example: Listener Future vs. Service Future

The example below uses Spring Framework 6.2.12, Java 17+, and Maven. There are two paths:

- **Event:** the publisher creates `CompletableFuture<String> reply` and attaches it to a `WorkRequested` event. The `@Async` listener declares `CompletableFuture<Void>` as its return signature and completes the event's `reply` with the business result. This is an **application-defined reply channel**, not a Future returned by `publishEvent`.
- **Direct bean call:** the caller obtains the `AsyncService` bean from the Spring context, invokes an `@Async` method, and **directly receives** `CompletableFuture<String>` via the proxy.

Create the structure:

~~~text
async-listener-future/
├── pom.xml
└── src/main/java/demo/AsyncFutureEventsDemo.java
~~~

### `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>async-listener-future</artifactId>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### `src/main/java/demo/AsyncFutureEventsDemo.java`

~~~java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class AsyncFutureEventsDemo {

    // Event carrying an explicit reply handle, intended for in-process example use.
    public record WorkRequested(
            String jobId,
            CompletableFuture<String> reply) {
    }

    @Configuration
    @EnableAsync
    public static class Config {

        @Bean("lessonExecutor")
        public ThreadPoolTaskExecutor lessonExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(2);
            executor.setQueueCapacity(8);
            executor.setThreadNamePrefix("lesson-");
            return executor;
        }

        @Bean
        public AsyncEventListener asyncEventListener() {
            return new AsyncEventListener();
        }

        @Bean
        public AsyncService asyncService() {
            return new AsyncService();
        }
    }

    public static class AsyncEventListener {

        @Async("lessonExecutor")
        @EventListener
        public CompletableFuture<Void> onWorkRequested(WorkRequested event) {
            try {
                if (event.jobId().isBlank()) {
                    throw new IllegalArgumentException("jobId is blank");
                }

                String result = "event:" + event.jobId();
                // Important: complete the Future placed in the event by the application.
                event.reply().complete(result);

                // The Future returned by the listener is not handed to the caller by publishEvent.
                return CompletableFuture.completedFuture(null);
            } catch (RuntimeException failure) {
                // If the task fails, the caller awaiting reply also observes the error.
                event.reply().completeExceptionally(failure);
                throw failure;
            }
        }
    }

    public static class AsyncService {

        @Async("lessonExecutor")
        public CompletableFuture<String> execute(String id) {
            // Temporary value inside the target method handled by the proxy.
            return CompletableFuture.completedFuture("service:" + id);
        }
    }

    public static void main(String[] args) throws Exception {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {

            // Approach 1: publish event, receive reply via handle attached to the event.
            CompletableFuture<String> reply = new CompletableFuture<>();
            context.publishEvent(new WorkRequested("A-1", reply));
            String eventResult = reply.get(5, TimeUnit.SECONDS);
            System.out.println("Event reply: " + eventResult);

            // Approach 2: call @Async service through Spring proxy and receive Future.
            CompletableFuture<String> directFuture =
                    context.getBean(AsyncService.class).execute("B-2");
            String serviceResult = directFuture.get(5, TimeUnit.SECONDS);
            System.out.println("Direct Future: " + serviceResult);
        }
    }
}
~~~

Run in the `async-listener-future` directory (requires JDK 17+ and Maven):

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.AsyncFutureEventsDemo
~~~

The two lines printed by the program (`stdout`) in order:

~~~text
Event reply: event:A-1
Direct Future: service:B-2
~~~

**Why does the example have deterministic output order?** In `main`, `reply.get(5, SECONDS)` waits for the listener to complete the reply before printing the first line. Only then does `main` call the async service, wait on `directFuture.get(...)`, and print the second line. This only controls those two operations in the example; it does not mean other asynchronous listeners in an application will always run in event-publication order.

**Meaning of the two Futures:**

- `onWorkRequested` has a signature returning `CompletableFuture<Void>`, satisfying the return types supported by `@Async`. However, the publisher **cannot hold** the Future processed by Spring when invoking the listener.
- `reply` is a Future **created by the application before publishing**. The listener completes it; the publisher can wait on it or attach callbacks. This is an application-level convention requiring clear rules for exceptional completion, timeouts, and reply ownership.
- `directFuture` is the Future that the caller **receives from calling `AsyncService` through the Spring proxy**. This is the standard path when the caller directly requires an async result.

In the code, `reply` is completed before the listener returns; that is a specific choice for this example. If logic has multiple steps, only call `complete` after the necessary effects have finished and data is consistent.

## 5. When Should a Listener Declare `Future<T>` Directly?

In terms of `@Async` return types, `Future<T>` and `CompletableFuture<T>` are valid. For a listener, the real question is **who consumes the result**.

**Side-effect-only cases** such as sending email, writing audits, or refreshing caches: a `void` listener is usually clearer because no caller consumes a return value. In that case, a dedicated error-reporting/monitoring policy is needed.

~~~java
// Illustrative snippet on a Spring bean with @EnableAsync and a valid executor.
@Async("lessonExecutor")
@EventListener
public void sendNotification(OrderPlaced event) {
    notificationService.send(event.orderId());
}
~~~

**Cases where a listener declares a Future:** `CompletableFuture<Void>` expresses the `@Async` contract at the method level without promising a business reply value. Declaring `CompletableFuture<Result>` expecting the publisher to receive `Result` is misleading; `publishEvent` itself never hands that handle to the caller. Furthermore, `@EventListener`'s return-value handling has specific semantics tied to follow-up events, so do not use return values to build an undocumented reply protocol.

**Cases where returning a value to the caller is mandatory:** prefer an **async service** returning `CompletableFuture<Result>` called directly; or if architectural reasons require keeping an event, use an explicitly designed reply channel like the example above. A Future attached to an event only works within the same JVM; it is not a durable message and cannot be serialized intact over Kafka/RabbitMQ or between two services.

## 6. Handling Errors, Timeouts, and Completion Properly

### 6.1. `get` vs. `join`

- `future.get(timeout, TimeUnit.SECONDS)`: blocks the thread with a time bound; failures are typically wrapped in `ExecutionException`.
- `future.join()`: blocks when needed without a timeout argument; failures are wrapped in `CompletionException`. Avoid unbounded `join()` on request threads if the listener could hang.
- `future.whenComplete((value, error) -> ...)`: registers a callback to observe both success and failure. Avoid throwing exceptions inside the callback without a downstream handler.
- `future.exceptionally(error -> fallback)`: produces a fallback value or handles errors; never silently turn critical business failures into fake successes.
- `future.thenCompose(nextAsyncStep)`: chains asynchronous steps with data dependencies without blocking between steps.

Example consuming the reply without blocking the publisher:

~~~java
// Illustrative: reply has been attached to the event.
reply.orTimeout(5, TimeUnit.SECONDS)
     .whenComplete((value, failure) -> {
         if (failure != null) {
             logFailure(failure);
         } else {
             consume(value);
         }
     });
~~~

The snippet above uses `logFailure` and `consume` as illustrative business helper names; both must be defined in the application. `orTimeout` (Java 9+) completes the Future exceptionally on expiration **but does not stop the work already submitted to the executor**. If the listener arrives late, `complete` may return `false` because the Future has already terminated.

### 6.2. What If There Is No Listener or the Executor Rejects the Task?

With nobody completing `reply`, the Future could wait forever. Likewise, if the executor has shut down, the pool is full, or tasks are rejected, the work may never enter the queue; handle errors at the event publication boundary, enforce timeouts, and provide fallback paths. Never treat `publishEvent` returning as proof that every listener ran successfully.

If using a map like `Map<CorrelationId, CompletableFuture<Result>>` for multiple requests, remove entries on success, failure, and timeout branches to avoid memory leaks; consider a unique ID per request and a single owner responsible for completing the reply.

### 6.3. Who Owns the Exception?

For a directly invoked `@Async` method returning `Future<T>`, the caller can observe failures via the Future. For an async listener invoked by the event system, the publisher has no such Future to call `get()` on; errors do not automatically propagate back to the thread calling `publishEvent`. For `@Async void`, Spring provides `AsyncUncaughtExceptionHandler` to handle uncaught exceptions. In all cases, ensure proper logging, metrics, correlation IDs, and retry policies.

In the example, the listener proactively calls `event.reply().completeExceptionally(failure)` before rethrowing. Consequently, the caller awaiting `reply.get(...)` receives an `ExecutionException` wrapping the cause. Without this step, `reply` might never complete even though the listener failed.

## 7. Other Limitations of Async Listeners

### 7.1. Spring Proxies and `@EnableAsync`

`@EnableAsync` enables `@Async` detection; listeners and services must be **Spring-managed beans** with methods interceptable by a proxy. A `this.asyncMethod()` call within the same object (self-invocation) normally bypasses the proxy in proxy mode, resulting in unexpected synchronous execution. Do not place `@Async` directly on methods inside `@Configuration`. Choose and name executors explicitly; ensure pools have sufficient resources, bounded queues, and appropriate rejection policies.

### 7.2. Transactions and Thread Context

Work on another thread does not automatically inherit the publisher's Spring transaction, request-bound `ThreadLocal`, MDC, or security context unless context propagation is configured. If a listener must run after transaction commit, consider `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` with a solid understanding of the transaction lifecycle; this annotation **does not turn a listener's Future into a publisher return value**. If data must survive a crash between commit and async execution, consider a transactional outbox or durable queue.

### 7.3. Ordering, Multiple Listeners, and Reliability

If multiple listeners receive an event, each listener can finish at a different time; `@Order` does not guarantee the completion order of async tasks. A single reply Future does not automatically solve cases where multiple listeners must converge results: you must define reply ownership or use `CompletableFuture.allOf` across Futures **that the caller actually holds**. Do not assume one successful reply means all side effects from every listener succeeded.

When guaranteed results, retries, auditing, and cross-process execution are required, a pure in-memory event solution with a Future is insufficient. Upgrade the model to jobs with IDs, durably persisted state, and query APIs or an appropriate broker/workflow.

## 8. Common Mistakes

| Mistake | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| Assigning `publishEvent` result to a `Future` | Method returns `void` | Call an async service directly or create an explicit reply channel |
| Using `@Async public String handle(...)` | Return type violates the `@Async` contract | Use `void`, `Future<T>`, or `CompletableFuture<T>` |
| Returning `CompletableFuture<String>` from a listener expecting the publisher to receive it | Event dispatch is not request/response | Use a dedicated reply Future or a service with an explicit API |
| Calling `future.get()` without timeout on a request thread | Can hang if listener fails/hangs/is rejected | Set a timeout and handle errors/retries |
| Omitting `completeExceptionally` on failure | Waiter on reply may time out even though listener already failed | Complete the reply on both branches |
| Calling `@Async` via `this` | May bypass the Spring proxy | Call through another bean/proxy |
| Assuming `@Order` guarantees async listener completion order | Multi-threaded executors run concurrently | Coordinate or serialize workflows when required |
| Sending `CompletableFuture` in an event across a broker | A Future is an in-process memory handle | Use correlation IDs and distributed state/reply channels |

## 9. Practical Adoption Checklist

1. Identify who needs the **result**: the publisher, a directly calling service, or a downstream consumer.
2. If the publisher only needs to announce an event, use an independent async listener and monitor errors out-of-band.
3. If the publisher must wait and read a result, prefer an `@Async` service returning `CompletableFuture<T>`; if still using events, define an explicit reply channel.
4. For a reply channel, specify timeout, `complete`/`completeExceptionally`, request ID, listener ownership count, late-reply handling, and cleanup.
5. Choose an appropriate executor, measure queue/rejection behavior, apply context propagation, and manage transactions.
6. Test scenarios with no listeners, listeners throwing exceptions, timeouts, concurrent events, and shutdown.
7. If correctness depends on durable execution or multiple instances, move to a model with persisted state and acknowledgments.

**Remember:** `Future` on an `@Async` method is a tool for callers **invoking the method through a proxy** to track execution. When that method is also an `@EventListener`, the event publisher still only sees `publishEvent(...)` returning `void`. To receive results, design an explicit reply interface; do not infer a Future-returning publisher interface from a listener declaring a Future.

## References

- Spring Framework 6.2 — ApplicationContext, `@EventListener`, Asynchronous Listeners, and return-value limitations: https://docs.spring.io/spring/reference/6.2/core/beans/context-introduction.html
- Spring Framework — `@Async`, `Future`, `CompletableFuture`, `@EnableAsync`, and executors: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework — `@Async` annotation API: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/annotation/Async.html
- Spring Framework — `@EventListener` annotation API: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/EventListener.html
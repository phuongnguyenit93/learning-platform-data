# AsyncUncaughtExceptionHandler for @Async Methods Returning void

> **Module:** Spring Framework – concurrency  
> **Parent topic:** Exception Handling  
> **Goal:** Understand why an exception thrown in an `@Async` method returning `void` does not return to the caller in the usual way; know how to configure `AsyncUncaughtExceptionHandler`, inspect `Throwable`/`Method`/`params` information, distinguish it from `Future`/`CompletableFuture` and handle task submission errors, and design reliable logging/metrics.

## 1. The fundamental problem: @Async void has no Future to return errors

Consider a Spring service:

~~~java
@Service
public class NotificationService {
    @Async
    public void sendNotification(String orderId) {
        throw new IllegalStateException("notification service unavailable");
    }
}
~~~

This is a **Spring integration snippet**, requiring imports for `@Service` and `@Async`, async processing enabled, and calls going through the Spring proxy; it is not yet a standalone program. When the call actually passes through `@Async` advice and the task is accepted by the executor, the caller thread typically regains control **before** the method body finishes. If the method body throws `IllegalStateException` in the worker, the caller cannot write a `try/catch` right around `sendNotification(...)` to catch that exception as if it were a synchronous call.

No `Future` is returned from a `void` method; therefore the caller **has no result handle** on which to call `get()`, `join()`, or check the task's error status. Spring provides `org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler` to handle **uncaught exceptions from the body of an `@Async void` method**.

Core idea:

- **Caller:** requests execution of an async method, receiving no return value via the `void` signature.
- **Executor:** accepts and runs the work afterward, on a thread matching the scheduling policy.
- **Worker:** when the work throws an unhandled `Throwable`, the async interceptor routes the error to `AsyncUncaughtExceptionHandler`.
- **Handler:** receives the error, method, and arguments; records, alerts, or emits observability signals. The handler **does not turn `void` into `Future`** and does not send the exception back to the caller.

This mechanism applies only to calls that are actually intercepted. If `@Async` is bypassed (for example self-invocation in default proxy mode), the method may run synchronously and exceptions follow the normal call stack.

## 2. Execution flow and two points where failure can occur

~~~text
Caller thread
   |
   | calls notificationService.sendNotification("ref-42")
   v
Spring @Async proxy / interceptor
   |
   +-- error submitting task / executor shut down or rejected?
   |       |
   |       +--> caller may receive TaskRejectedException right at the call
   |
   +-- executor ACCEPTS
           |
           +--> caller's void call returns (typically without result yet)
           |
           v
       Task execution thread
           |
           +-- sendNotification succeeds --> completes
           |
           +-- sendNotification throws uncaught exception
                    |
                    v
             AsyncUncaughtExceptionHandler
               handleUncaughtException(error, method, params)
                    |
                    +--> log / metric / alert / controlled error reporting
                    +--> DOES NOT propagate Throwable back to caller
~~~

**Two error paths must be distinguished:**

1. **Task submission error:** Spring's `TaskRejectedException` (or the appropriate rejection exception for the executor) occurs **when the proxy attempts to submit** to a closed/saturated executor. This is a scheduling-stage error, observable immediately on the caller. It is **not** an exception thrown by the async method body and is not guaranteed to go through `AsyncUncaughtExceptionHandler`.
2. **Error after task starts running:** an exception thrown by the `@Async void` method body during execution. Spring uses the handler to process it because there is no `Future` for the caller to observe.

If the executor uses a special policy such as `CallerRunsPolicy` under overload, the task may execute on the caller thread; do not infer thread placement solely from the `@Async` annotation name. However, the proxy's exception-handling path for `void` methods should still be understood according to the handler contract.

## 3. What interface is AsyncUncaughtExceptionHandler?

The interface resides in package:

~~~java
org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler
~~~

Key signature (abbreviated for study, not a standalone Java class):

~~~java
void handleUncaughtException(
    Throwable exception,
    java.lang.reflect.Method method,
    Object... params);
~~~

Meaning of the parameters:

| Parameter | Represents | Notes |
| --- | --- | --- |
| `Throwable exception` | Unhandled error from the `@Async void` method | May be a `RuntimeException`, or an `Error`; not wrapped into `ExecutionException` by default |
| `Method method` | Reflection metadata about the invoked async method | Can inspect `getName()`, `getDeclaringClass()`; do not assume `Method` always belongs to a specific proxy class |
| `Object... params` | Arguments of the original call, passed in by the Spring interceptor | May contain sensitive data, mutable objects, large collections, or dangerous `toString()` implementations |

A handler typically needs to answer three questions: **which method failed? what was the error? how should it be alerted/recorded?** That does not equate to “retry immediately” or “undo all side effects that already occurred”.

Concise handler example:

~~~java
AsyncUncaughtExceptionHandler handler = (error, method, args) -> {
    logger.error("Async void method {} failed", method.getName(), error);
    failedTasksCounter.increment();
};
~~~

This is an **integration snippet**, requiring the application to already have `logger` and `failedTasksCounter`. It does not print all of `args`, because arguments may contain tokens, emails, personal data, transaction details, or objects capable of generating huge log entries.

## 4. What is the default handler if none is configured?

When processing an `@Async` method returning `void` without an application-supplied custom exception handler, Spring Framework defaults to `SimpleAsyncUncaughtExceptionHandler`. The default handler **logs the error** from the async method; it does not automatically retry, does not return an error to an HTTP caller, and does not place the result into a future.

This has an important production consequence: **having an error log does not mean the system handled the business failure**. If the job sends an email, creates an invoice, or syncs another system, logging alone cannot indicate whether the task needs retrying, what side effects occurred, or whether an operational alert is required.

If log aggregation does not capture the right logger/severity, `@Async void` errors can be missed in operations. Therefore a dedicated handler should emit metrics and safe correlation IDs, paired with a runbook for handling failed tasks.

## 5. Configuring the handler via AsyncConfigurer

The idiomatic approach with annotation-based async in Spring is to provide `org.springframework.scheduling.annotation.AsyncConfigurer` in a configuration with `@EnableAsync`, and override `getAsyncUncaughtExceptionHandler()`.

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration implements AsyncConfigurer {
    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (error, method, args) -> {
            // Record the @Async void error here.
        };
    }
}
~~~

This is **illustrative integration code**; you must import the types and let Spring load the configuration. One `AsyncConfigurer` suffices to configure the default exception handler for `@Async` processing in the corresponding context. Avoid registering multiple competing `AsyncConfigurer` beans in the same context; keep a single deterministic default configuration.

`AsyncConfigurer` has two members to distinguish:

- `getAsyncExecutor()`: **optional** default executor provider for `@Async`; when omitted, Spring resolves an executor by type/name and corresponding fallback.
- `getAsyncUncaughtExceptionHandler()`: **optional** handler provider for uncaught exceptions in `@Async` methods returning `void`.

You do not necessarily have to override both. The complete example in section 8 **overrides only the handler** while still declaring a `ThreadPoolTaskExecutor` bean for Spring to select.

**Lifecycle note:** a class implementing `AsyncConfigurer` is initialized relatively early during async configuration. If the handler requires complex dependencies, avoid triggering incomplete beans too early; use clear configuration or lazy lookup where appropriate. Merely declaring an arbitrary bean of type `AsyncUncaughtExceptionHandler` does not mean every interceptor will automatically use it; the configuration path covered here is `AsyncConfigurer`.

## 6. When is the handler invoked, and when is it not?

| Scenario | Is AsyncUncaughtExceptionHandler the main handling path? | Why |
| --- | --- | --- |
| `@Async public void run()` throws an uncaught exception during execution | **Yes** | The caller has no Future to retrieve the error |
| `@Async public void run()` uses `try/catch` itself and does not rethrow | **No** | There is no unhandled exception left |
| `@Async public Future<T> run()` fails while the task runs | **No** | The error is represented via the result Future |
| `@Async public CompletableFuture<T> run()` fails while the task runs | **No** | The error is represented via the result `CompletableFuture` |
| `@Async public CompletableFuture<Void> run()` throws an exception | **No** | Even without a useful value, the method still returns a Future to observe |
| `@Async void` is rejected at submission time | **Not guaranteed** | The error may be thrown by the proxy right at the caller's call |
| `@Async` is bypassed by self-invocation | **No** | Does not pass through the interceptor to reach the handler |
| `@Async void` starts its own future, which fails later | **Not by default** | The error occurs in a detached job; the void method may already have finished normally |
| Code runs directly via `executor.execute(() -> ...)`, without `@Async` | **Not by default** | It does not go through Spring's `@Async` interceptor |

This table also explains why writing **`@Async void` for a task the caller needs to track provides insufficient information**. If the caller needs to know whether the task finished, succeeded, or failed, consider returning `CompletableFuture<Void>` instead of `void`.

## 7. Comparison: @Async void vs. @Async CompletableFuture<Void>

Example of two APIs performing the same work without a return value:

~~~java
@Async
public void sendFireAndForget(String id) {
    sendToExternalService(id);
}

@Async
public CompletableFuture<Void> sendTracked(String id) {
    sendToExternalService(id);
    return CompletableFuture.completedFuture(null);
}
~~~

This is a **Spring integration snippet** where `sendToExternalService` is a hypothetical business function; it is not a standalone Java file.

- With `sendFireAndForget`, an uncaught exception in the worker goes to `AsyncUncaughtExceptionHandler`. The caller cannot await it via the declared API.
- With `sendTracked`, Spring returns a `CompletableFuture<Void>` to the caller. The caller can call `whenComplete`/`exceptionally` or `get()`/`join()` to observe the outcome. If an exception occurs in the task, the caller sees an exceptional completion; the void handler **is not used** for this error.
- `CompletableFuture<Void>` carries no business payload, yet it still has a **completion state**. Do not confuse the `Void` generic type with the `void` return type.
- If an `@Async` method calls another async API internally and returns an already-completed `CompletableFuture` before the child API finishes, the caller may receive a premature success signal. The contract must accurately represent the full lifecycle of the work you want to track.

A common mistake is changing a method from `void` to `CompletableFuture<Void>` without updating callers to observe the future. When that happens, exceptions can still be missed—merely shifting from the handler to an unobserved future.

## 8. Runnable Spring Framework 6.2.9 + Java 17 example

This exercise creates an `@Async void` service that throws `IllegalStateException`; an `AsyncConfigurer` routes the error to a custom handler. `CountDownLatch` lets the CLI wait for the handler to finish, making **stdout order deterministic** without guessing thread timing.

Project structure:

~~~text
spring-void-handler-demo/
├── pom.xml
└── src/main/java/demo/VoidAsyncHandlerDemo.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-void-handler-demo</artifactId>
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

**src/main/java/demo/VoidAsyncHandlerDemo.java**:

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class VoidAsyncHandlerDemo implements AsyncConfigurer {
    private static final CountDownLatch HANDLED = new CountDownLatch(1);

    @Bean("taskExecutor")
    public ThreadPoolTaskExecutor taskExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(1);
        pool.setMaxPoolSize(2);
        pool.setQueueCapacity(4);
        pool.setThreadNamePrefix("demo-async-");
        return pool;
    }

    @Bean
    public NoticeService noticeService() {
        return new NoticeService();
    }

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (error, method, args) -> {
            try {
                System.out.println("Method: " + method.getName());
                System.out.println("Error: " + error.getClass().getSimpleName()
                    + ": " + error.getMessage());
                System.out.println("Arguments: " + args.length);
            } finally {
                HANDLED.countDown();
            }
        };
    }

    public static class NoticeService {
        @Async
        public void sendNotice(String reference) {
            throw new IllegalStateException("delivery failed");
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(VoidAsyncHandlerDemo.class)) {
            context.getBean(NoticeService.class).sendNotice("ref-42");
            if (!HANDLED.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Handler was not called");
            }
            System.out.println("Caller: no task exception propagated");
        }
    }
}
~~~

Run from the `spring-void-handler-demo` directory (JDK 17+, Maven):

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.VoidAsyncHandlerDemo
~~~

**Program stdout lines**:

~~~text
Method: sendNotice
Error: IllegalStateException: delivery failed
Arguments: 1
Caller: no task exception propagated
~~~

The task is scheduled by Spring on the executor named `taskExecutor`; it throws an exception and the handler receives `Method`, `Throwable`, and a one-argument array. `HANDLED.countDown()` runs inside the handler's `finally` block, ensuring `main` prints the final line only after the handler has printed the previous three lines. This demo produces deterministic output provided the executor accepts the task and the handler runs within five seconds; if it takes too long, the program actively reports a timeout.

The example was **compiled targeting Java 17 and executed successfully** on a newer JDK; actual stdout matched the four lines above. The Maven command may still print other environment messages from dependencies/plugins, but those are not the four `System.out.println` lines of the program.

**Why didn't the lesson override `getAsyncExecutor()`?** `AsyncConfigurer` allows providing only the handler. Spring still resolves the default executor from the single `ThreadPoolTaskExecutor` bean (also named `taskExecutor`). This is precisely how to configure error handling separately without creating another executor.

**Limitations:** the example intentionally throws an error; there is no real notification delivery or DB state persistence. `CountDownLatch` is only for testing/CLI waiting illustration, not a delivery-guarantee strategy for a production HTTP API.

## 9. How to implement a handler for production

A handler is not the place to re-run heavy business processing. It must be **fast, safe, and free of secondary failures**, because it typically executes on the task execution thread or the executor's completion path.

A production-ready handler should:

1. **Log in a structured way:** class/method name, exception type, controlled message, and non-sensitive correlation ID/operation ID. Use the logger with a stack trace when logging policy permits.
2. **Increment error metrics:** for example `async_void_failure_total` tagged with bounded-cardinality tags for method name and error type; avoid using raw order IDs as metric tags.
3. **Never dump the raw params array:** arguments may be access tokens, emails, user data, `MultipartFile`, or huge object graphs. `toString()` could also throw errors or trigger unexpected work.
4. **Distinguish error categories:** validation, network, timeout, logic bug, rejection, shutdown; do not auto-retry every exception.
5. **Record business state via a reliable mechanism:** if the work is critical, the handler can emit a failure event with an idempotency key or request a job record update, while accounting for transactions and write-channel reliability.
6. **Do not perform long blocking I/O in the handler:** if the handler blocks, the worker is not released; the pool can lose throughput or worsen overload.
7. **Guard against secondary failures:** use minimal operations and appropriate catches around logging/notification. Do not let the handler throw unexpected exceptions assuming Spring will fix everything.
8. **Monitor the submission path as well:** use a separate `TaskRejectedException` metric because a rejected task may never reach the handler.

Minimal pseudo-logging template illustrating the principle:

~~~java
@Override
public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
    return (error, method, args) -> {
        try {
            metrics.incrementAsyncFailure(
                method.getDeclaringClass().getSimpleName(),
                method.getName(),
                error.getClass().getSimpleName());
            log.error("Unhandled @Async void failure in {}",
                method.getName(), error);
        } catch (RuntimeException loggingFailure) {
            // Minimal fallback per system policy.
        }
    };
}
~~~

This is an **integration snippet**, assuming `metrics` and `log` dependencies exist, not a standalone compilable program. In production, do not silently swallow `loggingFailure` without a fallback error-reporting channel; choose a channel that operates safely and avoid having it flood logs or stall the executor.

## 10. The handler is not an automatic retry mechanism

`AsyncUncaughtExceptionHandler` is invoked after an `@Async void` task has already failed. It **does not durably persist a command**, does not guarantee once-only execution, has no `Future` indicating where the caller went, and does not undo side effects performed before the exception.

Do not do the following:

~~~java
return (error, method, args) -> {
    method.invoke(targetBean, args);  // Dangerous: immediate retry via reflection
};
~~~

This is an **anti-example**, not standalone because `targetBean` is undeclared. It can:

- Invoke the wrong instance/proxy, bypassing advice or causing recursion;
- Duplicate side effects when the task already wrote to a DB/sent a request before failing;
- Retry immediately while the dependency is still overloaded;
- Cause reflection, security, transaction, context, or duplication errors.

If retries are required, design them **from the business task level**: operation ID, idempotency key, durable input data, error classification, `maxAttempts`, backoff + jitter, deadline, queue/job store, and explicit terminal states. A handler can be where incidents are **detected** or a failure-handling workflow is **triggered**, not a delivery-guaranteed job scheduler by itself.

## 11. Unhandled exceptions vs. already-caught errors

Compare two implementations:

~~~java
@Async
public void sendA(String id) {
    remoteService.send(id); // Throws IllegalStateException -> can reach handler
}

@Async
public void sendB(String id) {
    try {
        remoteService.send(id);
    } catch (IllegalStateException ex) {
        logger.warn("sendB failed");
        // Not rethrown -> handler does not receive this exception
    }
}
~~~

This is an **illustrative integration snippet** with `remoteService`/`logger` and annotations configured. If business logic intentionally handles the error inside `catch`, the handler should not be invoked; however, if it merely logs and moves on, the system loses centralized failure signaling.

Case where an `@Async void` task internally only launches another `CompletableFuture`:

~~~java
@Async
public void detach(String id) {
    asyncClient.send(id);  // Returns CompletableFuture, but it is ignored
}
~~~

If `asyncClient.send(id)` returns an incomplete future, `detach` may return normally before the inner future fails. A stage failure **after the void method has ended** is not an uncaught exception from the body of `detach`; `AsyncUncaughtExceptionHandler` does not automatically track abandoned stages. For operations requiring end-to-end completion, return `CompletableFuture<Void>` and chain/observe stages properly, or design durable job status.

## 12. TaskRejectedException and overload must be monitored separately

A `ThreadPoolTaskExecutor` with bounded workers and queue can reject tasks under overload. Rejection happens at **submission**, so sometimes the caller receives `TaskRejectedException` before a worker ever starts running the `@Async void` method.

Illustrative caller snippet:

~~~java
try {
    notificationService.sendNotification(orderId);
} catch (TaskRejectedException rejected) {
    // Handle overload on caller: respond/backpressure or persist durable job.
}
~~~

This is a **snippet woven into an application**; `notificationService` is a Spring proxy bean, `orderId` is input, and `TaskRejectedException` is in `org.springframework.core.task`. This `try/catch` **can catch submission errors**, but **does not catch** `IllegalStateException` thrown later from the `@Async void` body in a worker.

Do not spin in a `while(true)` loop retrying immediately upon rejection: it worsens overload. Instead, separate rejectable requests from mandatory durable jobs, return appropriate `429`/`503` responses, use backoff/jitter with retry limits, or use a durable queue.

Another difference: `CallerRunsPolicy` can execute the task on the caller thread while the pool is running and saturated. If you want predictable request latency, test this policy; do not assume every `@Async` call always returns instantaneously.

## 13. Spring proxy, context, and transaction boundaries

**Proxy:** With `@EnableAsync` in default proxy mode, calling `this.sendNotification()` inside the same bean typically bypasses the interceptor. Nor does the handler intervene in a synchronous call that bypassed the proxy. Tests should call from another bean/caller through the Spring-managed proxy.

**Unsuitable methods:** Avoid relying on `@Async` on private/final methods in class-based proxies because they cannot be intercepted as expected. Classes/methods must be validly proxied by Spring. The annotation does not make calls on a Java object created manually with `new` asynchronous.

**Thread context:** Workers do not automatically and safely inherit all of the caller's `ThreadLocal`, MDC, security principal, or request attributes. `params` in the handler is not a general context-propagation solution. Pass correlation IDs safely through application-designed command/context mechanisms; use `TaskDecorator` or an appropriate adapter when needed.

**Transactions:** Imperative transactions are typically thread-bound. An error in a worker does not automatically roll back a transaction already committed on the request thread; meanwhile, the handler invoked **after the method fails** does not automatically open a new transaction to record status. To persist failure status, use a transaction in the handling service or a clearly scoped `TransactionTemplate`.

**Singleton beans:** Multiple async tasks can run concurrently on a singleton service. The handler can also be invoked concurrently; shared counters, caches, and state must be thread-safe. If using existing loggers and meter clients, verify thread safety of those dependencies.

## 14. Monitoring and testing: do not assert only on logs

A dedicated test suite for `AsyncUncaughtExceptionHandler` should verify:

1. **Call goes through the proxy:** create an `ApplicationContext`, retrieve the bean from Spring, and invoke a public `@Async void` method.
2. **Method exception:** the method throws `IllegalStateException` with a known message; the handler receives the exact type and message.
3. **Method metadata:** `method.getName()`, `params.length`, and permitted inspection data match; do not dump raw tokens or PII.
4. **Threaded execution:** use `CountDownLatch` to wait for the handler, not fixed `Thread.sleep` or assuming the exception happens before the caller's next statement.
5. **Succeeding void method:** the handler is not invoked when the task completes normally; use a latch/clock to bound test time.
6. **Caught exception:** if the method handles the error itself without rethrowing, the handler is not invoked.
7. **Future return:** when an `@Async CompletableFuture<Void>` method fails, the returned future completes exceptionally; the void handler is not its error channel.
8. **Submission rejection:** create a bounded pool and fill the queue using a latch, assert the caller receives rejection per policy; do not wait on the handler to detect it.
9. **Handler robustness:** simulate logger/metric client failures; verify fallback behavior and no infinite retries or recursive business invocations.
10. **Idempotency / restart:** for jobs requiring guaranteed delivery, test lost responses, process restarts, duplicate commands, and durable job state stored outside memory.

Using `CountDownLatch` in tests is not meant to make every API blocking, but to give **tests a deterministic synchronization point**. The example in section 8 checks both the exception and method argument count, then verifies the caller did not receive the task exception via a normal `try/catch`.

Useful metrics: `async_void_failure_total`, `async_submit_rejected_total`, queue depth, active workers, task duration, failure-by-method, and total unhandled failed jobs. Do not put high-cardinality object IDs as metric labels; attach them to controlled logs/tracing if truly needed.

## 15. Common misconceptions

| Misconception | Why it is wrong | How to fix it |
| --- | --- | --- |
| “`try/catch` around `@Async void` will catch worker exceptions.” | Caller and worker have different execution paths | Use the handler; choose `CompletableFuture` if caller needs results |
| “Simply declaring an `AsyncUncaughtExceptionHandler` bean means Spring will always use it.” | The handler must be wired into the async interceptor via configuration | Use `AsyncConfigurer.getAsyncUncaughtExceptionHandler()` |
| “If `@Async void` fails, the caller will definitely know.” | The void signature carries no Future | Record metrics/logs/events; return a Future when status is needed |
| “The handler also receives errors from `CompletableFuture`.” | Futures already have their own error channel | `whenComplete`, `exceptionally`, `get()`/`join()` |
| “The handler will receive errors from every `executor.execute`.” | Raw executor APIs do not necessarily go through the `@Async` proxy | Design a separate error handler for the executor/task |
| “`TaskRejectedException` is an error inside the method body.” | It can occur during submission before running | Catch at the caller and monitor rejection metrics |
| “The default handler retries automatically.” | `SimpleAsyncUncaughtExceptionHandler` mainly logs | Retry with policy, job store, deadline, and idempotency |
| “Logging all of `params` is convenient and harmless.” | Can leak secrets/PII or cause log explosions | Sanitize, store only method/type/correlation ID |
| “The handler always runs on a dedicated separate thread.” | It is usually called on the task execution path; executor policies may vary | Keep the handler short, non-blocking, and test under overload |
| “`@Async void` guarantees work survives a JVM restart.” | Thread-pool tasks live only in memory | Use a durable queue/job store if delivery guarantees are needed |
| “Catching/logging then rethrowing in the method is unrelated.” | If rethrown, the handler can still receive the exception | Clarify logging ownership to avoid duplicate logs and duplicate alerts |

## 16. Production checklist

- `@EnableAsync` is enabled in the right `ApplicationContext`, and calls go through the Spring proxy.
- The method needing the handler actually has return type `void`, not `CompletableFuture<Void>`.
- The handler is configured via `AsyncConfigurer` and verified with an integration test.
- I know which exceptions are caught inside the method body and which are rethrown to the handler.
- The handler records errors safely without dumping raw `params` or user secrets.
- The handler is thread-safe, does not block for long, and performs no unbounded operations.
- The caller handles `TaskRejectedException` separately at submission time.
- I intentionally chose between fire-and-forget `void` and an API returning `CompletableFuture<Void>`.
- I do not use the handler for immediate reflection retries or to create extra overload.
- Critical jobs have idempotency keys, durable state, retry policies, timeouts, and reconciliation mechanisms.
- Transactions, security context, logging context, and worker lifecycle all have clear owners.
- Metrics/logs/alerts can distinguish **tasks that ran and failed** from **tasks rejected before running**.

**Conclusion:** `AsyncUncaughtExceptionHandler` is the channel for handling **uncaught exceptions from `@Async` methods returning `void`** after the task actually runs through the Spring interceptor. It receives information about the error, method, and arguments, but does not propagate errors back to the caller, does not perform automatic retries, and does not replace `Future` or job tracking. For work requiring results/acknowledgement, prefer an API returning a future or a durable job mechanism; for fire-and-forget, ensure you have a handler, logging, metrics, and a clear failure-handling policy.

## Official references

- Spring Framework — [AsyncUncaughtExceptionHandler Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/interceptor/AsyncUncaughtExceptionHandler.html): signature `handleUncaughtException(Throwable, Method, Object...)`.
- Spring Framework — [SimpleAsyncUncaughtExceptionHandler Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/interceptor/SimpleAsyncUncaughtExceptionHandler.html): logs exceptions by default.
- Spring Framework — [AsyncConfigurer Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/AsyncConfigurer.html): configures the default executor and uncaught exception handler.
- Spring Framework — [@EnableAsync Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html): enables async, proxy mode, defaults, and handler configuration.
- Spring Framework — [@Async Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/Async.html): supports `void`, `Future`, and `CompletableFuture` return types.
- Spring Framework — [Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): exception management for async methods and executor integration.
- Spring Framework — [TaskRejectedException Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/TaskRejectedException.html): handling rejection at task submission.

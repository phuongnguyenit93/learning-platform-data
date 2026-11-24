# Configuring the Exception Handler with AsyncConfigurer

## 1. The problem: @Async void fails, yet the caller has no Future to inspect

In Spring Framework, `@Async` allows executing a method using an executor selected by Spring. When the method returns `void`, the caller has no return value or completion handle to receive exceptions from the task running later on the worker. Example:

```java
import org.springframework.scheduling.annotation.Async;

@Async("backgroundExecutor")
public void notifyUser(String eventId) {
    throw new IllegalStateException("Failed to send notification");
}
```

This is a **method snippet inside a Spring-managed bean**, not a standalone program. If the call actually passes through the Spring async proxy and the executor runs the task on a worker, the exception arises after the caller has already left the call. A `try/catch` around `notifyUser(...)` on the caller usually cannot catch this error.

Spring provides `AsyncUncaughtExceptionHandler` to receive errors **that cannot be propagated back through the return type** from `@Async` methods returning `void`. To replace the default handler in Java Configuration, a `@Configuration` class implements `AsyncConfigurer` and overrides:

```java
@Override
public AsyncUncaughtExceptionHandler
        getAsyncUncaughtExceptionHandler() {
    return (exception, method, params) -> {
        // Record the exception from @Async void.
    };
}
```

Point to remember: **the handler is not a tool for catching every exception from every task**. `@Async` methods returning `Future<T>` or `CompletableFuture<T>` propagate errors through the result; submission errors (such as executor rejection) also differ from errors inside the task body.

This lesson focuses on how to declare `AsyncConfigurer`, the contract of `AsyncUncaughtExceptionHandler`, a runnable Spring example, distinguishing the two error channels, initialization risks, and practical error-handling design.

## 2. Where does AsyncConfigurer sit in the @Async flow?

Submission-time errors and errors occurring after the worker starts were distinguished in the opening lesson of this chapter. When configuring Spring, it is even more important to know **which errors `AsyncConfigurer` is responsible for**.

| Boundary | Configuration or observation responsibility |
| --- | --- |
| Proxy selects executor and submits work | Bean lookup failure, pool shutdown, or rejection can go directly to the caller; the handler for `@Async void` is not guaranteed to receive rejections. |
| `@Async void` method runs on a worker and throws an uncaught exception | The async interceptor forwards the exception to the `AsyncUncaughtExceptionHandler` provided by `AsyncConfigurer`. |
| `@Async Future` or `CompletableFuture` method fails | The caller observes the Future's exceptional completion; the void handler is not where the result goes. |

Therefore, you must **invoke beans through the Spring proxy** in tests and choose clearly named executors. Configuring the handler properly does not replace handling submission rejections, and does not guarantee the job has been durably persisted.

## 3. What configuration point is AsyncConfigurer?

The `org.springframework.scheduling.annotation.AsyncConfigurer` interface lets you configure two separate components:

| Method | Purpose | Must both be overridden? |
|---|---|---|
| `getAsyncExecutor()` | Selects the default `Executor` for `@Async` methods that do not specify an executor | No |
| `getAsyncUncaughtExceptionHandler()` | Selects the handler for errors from `@Async void` that cannot propagate to the caller | No |

As of Spring 6.x versions, these methods are default methods. To replace only the handler, you can override just `getAsyncUncaughtExceptionHandler()`, leaving executor selection by bean name, qualifier, or default rules to be configured separately.

Abbreviated API contract:

```java
public interface AsyncConfigurer {
    Executor getAsyncExecutor();
    AsyncUncaughtExceptionHandler
            getAsyncUncaughtExceptionHandler();
}
```

This is an **abbreviated signature outline**, not the full source code: the real API has default implementations and nullability annotations depending on the version. In real configuration, import the interface from Spring and declare `@EnableAsync`.

**Do not extend `AsyncConfigurerSupport` in new Spring applications.** That support class has been deprecated since Spring Framework 6.0; implementing `AsyncConfigurer` directly is clearer.

According to Spring's Javadoc, `AsyncConfigurer` is typically implemented by a `@Configuration @EnableAsync` class. It may be **initialized early during ApplicationContext bootstrap**, so be careful when injecting beans that have proxies, transactions, or complex dependencies.

## 4. Error data that AsyncConfigurer should pass to the handler

`AsyncUncaughtExceptionHandler` has the signature `handleUncaughtException(Throwable error, Method method, Object... params)`. The previous lesson explained its contract and when the handler runs; here the focus is **designing a safe handler when registering it with Spring**.

- Use method/class names and exception categories to record bounded-cardinality metrics; pass the full `Throwable` to the logger at the responsible boundary to preserve cause and stack trace.
- Select only permitted job/correlation IDs from `params`. Do not log all arguments: they may contain tokens, personal data, or mutable objects.
- The handler may run on a worker concurrently with other handlers; dependencies and counters must be thread-safe. If the recorder performs I/O, define timeouts, fallbacks, and do not block the worker indefinitely.
- An exception after a remote request does not prove side effects were rolled back. Retries, recording a `FAILED` status, or reconciliation require separate contracts and transactions.

These decisions will be verified in the `@Configuration` example and Spring context tests in the following sections.

## 5. Minimal configuration via @Configuration and @EnableAsync

**File `AsyncErrorConfig.java` — Spring configuration class, without a standalone main:**

```java
import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncErrorConfig implements AsyncConfigurer {

    @Bean("backgroundExecutor")
    public ThreadPoolTaskExecutor backgroundExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("background-");
        return executor;
    }

    @Override
    public AsyncUncaughtExceptionHandler
            getAsyncUncaughtExceptionHandler() {
        return (error, method, params) -> {
            System.err.println("Async error in "
                    + method.getName()
                    + ": " + error.getMessage());
        };
    }
}
```

Here:

1. `@EnableAsync` enables the `@Async` mechanism in the corresponding `ApplicationContext`.
2. Bean `backgroundExecutor` is a `ThreadPoolTaskExecutor` whose lifecycle is managed by Spring, so there is no need to call `initialize()` inside the `@Bean` method.
3. `getAsyncUncaughtExceptionHandler()` supplies the handler used by the Spring async interceptor for unhandled exceptions from `@Async void` methods.
4. The class does not override `getAsyncExecutor()`. Since methods can select a bean via `@Async("backgroundExecutor")`, there is no need to configure a default right in the example.
5. Worker and queue counts of 2/4/16 are purely illustrative. Production must size based on load, wait time, and memory, not shared constants.

A service using the configuration:

```java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {

    @Async("backgroundExecutor")
    public void send(String jobId) {
        throw new IllegalStateException(
                "Failed to send job " + jobId);
    }
}
```

Calls to `NotificationService.send(...)` must come **from another bean through the Spring proxy**. When they do, the handler receives the exact `Method send`, argument `jobId`, and `IllegalStateException`. For reuse, you can return `new ConsoleAsyncErrorHandler()` from `getAsyncUncaughtExceptionHandler()` instead of using a lambda.

## 6. Full Java 17 + Spring demo: handler for void, Future for methods with results

The following example has **two methods that both throw exceptions**, yet only one exception is routed to `AsyncUncaughtExceptionHandler`. The program uses `CountDownLatch` to print output in a verifiable order without relying on `Thread.sleep(...)`.

Requirements: JDK 17 or higher, Maven, Spring Framework 6.2.7 per the pom. This is a small standalone Maven project requiring no HTTP server.

### 6.1. Structure

```text
async-handler-demo/
├── pom.xml
└── src/main/java/lesson/AsyncHandlerDemo.java
```

### 6.2. File pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>lesson</groupId>
    <artifactId>async-handler-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.7</version>
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

### 6.3. File src/main/java/lesson/AsyncHandlerDemo.java

```java
package lesson;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
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

public class AsyncHandlerDemo {

    public static void main(String[] args)
            throws InterruptedException {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(Config.class)) {

            Tasks tasks = context.getBean(Tasks.class);

            tasks.failVoid("job-42");
            if (!Config.HANDLED.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Did not receive handler signal");
            }
            System.out.println("Caller confirmed handler ran");

            CompletableFuture<String> result = tasks.failFuture();
            try {
                result.join();
            } catch (CompletionException error) {
                System.out.println("Future error: "
                        + error.getCause().getMessage());
            }
        }
    }

    @Configuration
    @EnableAsync
    public static class Config implements AsyncConfigurer {
        static final CountDownLatch HANDLED = new CountDownLatch(1);

        @Bean("lessonExecutor")
        public ThreadPoolTaskExecutor lessonExecutor() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(4);
            executor.setThreadNamePrefix("lesson-");
            return executor;
        }

        @Bean
        public Tasks tasks() {
            return new Tasks();
        }

        @Override
        public AsyncUncaughtExceptionHandler
                getAsyncUncaughtExceptionHandler() {
            return (ex, method, params) -> {
                String jobId = String.valueOf(params[0]);
                System.out.println("Handler: " + method.getName()
                        + "(" + jobId + "): " + ex.getMessage());
                HANDLED.countDown();
            };
        }
    }

    public static class Tasks {
        @Async("lessonExecutor")
        public void failVoid(String id) {
            throw new IllegalStateException("void error");
        }

        @Async("lessonExecutor")
        public CompletableFuture<String> failFuture() {
            throw new IllegalArgumentException("Future error");
        }
    }
}
```

### 6.4. Running

In the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=lesson.AsyncHandlerDemo
```

Three lines printed by **the program itself** under normal execution conditions:

```text
Handler: failVoid(job-42): void error
Caller confirmed handler ran
Future error: Future error
```

If the runtime fails to schedule the task within 5 seconds, the program actively throws a timeout error instead of waiting forever. In a normal runtime environment, the output order is guaranteed:

- `tasks.failVoid("job-42")` goes through the `@Async` proxy; the method returns `void`, so the worker exception goes to the handler.
- The handler prints first and only then calls `HANDLED.countDown()`; `main` waits on the latch before printing the second line.
- `tasks.failFuture()` has return type `CompletableFuture<String>`. The error lives in the Future, `join()` throws `CompletionException`; the caller reads `getCause().getMessage()` and prints the last line.
- The `void` handler **does not** receive an extra error event just because `failFuture()` threw an exception.
- The context is closed by `try-with-resources`; do not call `shutdown()` arbitrarily inside services using a shared executor bean.

This code verifies **exception routing**, not durability or retries. `CountDownLatch` is strictly a testing tool: it is not an object `@Async void` automatically returns.

## 7. How does the default handler work?

If no custom handler is specified, Spring handles uncaught exceptions from `@Async void` by logging them through the default handler, typically `SimpleAsyncUncaughtExceptionHandler`. According to the official Spring documentation, exceptions from void methods cannot be propagated back to the caller, so by default they are only logged.

Easy points to misunderstand:

- **Having a log does not mean the task recovered**: the handler does not re-invoke business logic on its own.
- **No exception on the caller does not mean the task succeeded**: the worker may fail after the request has already returned.
- **Using a custom handler that only prints one line `error.getMessage()`** typically loses the stack trace, method name, or correlation ID needed for investigation.
- **Not logging** in a custom handler can make errors completely invisible if there are no metrics, tracing, or other status stores.

A production handler typically combines structured logging, metric counters with appropriate error-category labels, and threshold-based alerts. For critical tasks, include a job ID and a mechanism to persist failure state rather than relying on a single log line.

## 8. Which errors does the handler not handle?

### 8.1. Errors from Future or CompletableFuture

`@Async` returning `CompletableFuture<T>` sends errors back to the caller through the Future:

```java
@Async("backgroundExecutor")
public CompletableFuture<Integer> calculate(int x) {
    if (x < 0) {
        throw new IllegalArgumentException("x must be non-negative");
    }
    return CompletableFuture.completedFuture(x * 2);
}
```

Caller:

```java
service.calculate(-1).whenComplete((value, error) -> {
    if (error != null) {
        System.err.println("Future failed: " + error);
    }
});
```

The two snippets above are **Spring method/caller fragments**, not standalone runnable programs. With basic `Future`, `get()` reports errors via `ExecutionException`; with `CompletableFuture.join()`, typically via `CompletionException`. Do not block with `get()/join()` right on the HTTP request thread if the goal is a non-blocking response.

If the business operation needs to return no data yet the caller needs to know whether the task finished/failed, use `CompletableFuture<Void>` instead of `void`:

```java
@Async("backgroundExecutor")
public CompletableFuture<Void> saveAudit(String id) {
    auditRepository.save(id);
    return CompletableFuture.completedFuture(null);
}
```

Then the caller has a handle to observe the outcome; `AsyncUncaughtExceptionHandler` is no longer the primary error channel for this method. `auditRepository` is a hypothetical component provided by the application.

### 8.2. Submission errors or misconfigured executors

A pool can reject new tasks when full or shut down. With `ThreadPoolTaskExecutor` under normal rejection settings, the caller may see `TaskRejectedException` from the proxy call. The task has not run, so you cannot assume the `void` handler will receive this error.

```java
try {
    notificationService.send("job-9");
} catch (TaskRejectedException rejected) {
    // Return an overload error or apply a safe retry policy.
    throw rejected;
}
```

This snippet assumes `org.springframework.core.task.TaskRejectedException` is imported and the `notificationService` bean exists. Handle this at the admission boundary; if an API returns HTTP 202 when the executor actually rejected the task, that is a contract violation.

Selecting a non-existent executor bean via `@Async("missingExecutor")`, `ApplicationContext` initialization failures, or declaring an unsupported return type on a method are also wiring/contract issues, not normal exceptions thrown by a running `void` method.

### 8.3. Exceptions caught inside the task

```java
@Async("backgroundExecutor")
public void work(String id) {
    try {
        process(id);
    } catch (ExpectedBusinessException known) {
        recordResult(id, known);
    }
}
```

This snippet assumes application-specific `ExpectedBusinessException`, `process`, and `recordResult`. Because the exception was caught and not rethrown, the global handler **does not** receive it. That may be intentional if the task already has business handling; however, never silently swallow every error and record success.

## 9. Early initialization of AsyncConfigurer and dependency risks

Spring Javadoc emphasizes that configurations implementing `AsyncConfigurer` may be initialized early during bootstrap. If the configurer field-injects a proxied bean or too many dependencies, that bean may be instantiated without going through all expected `BeanPostProcessor`s.

Example to watch out for:

```java
@Configuration
@EnableAsync
public class FragileConfiguration implements AsyncConfigurer {
    @Autowired
    private ErrorRecorder recorder;

    @Override
    public AsyncUncaughtExceptionHandler
            getAsyncUncaughtExceptionHandler() {
        return (ex, method, params) ->
                recorder.record(method.getName(), ex);
    }
}
```

This is a **risky configuration snippet**, not standalone because `ErrorRecorder` is an application component. When `recorder` needs `@Transactional`, `@Async`, proxies, or has circular dependencies, overly early injection easily causes unpredictable behavior.

One option to defer dependency lookup is `ObjectProvider<ErrorRecorder>`:

```java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
public class LazyAsyncConfiguration implements AsyncConfigurer {

    private final ObjectProvider<ErrorRecorder> recorderProvider;

    public LazyAsyncConfiguration(
            ObjectProvider<ErrorRecorder> recorderProvider) {
        this.recorderProvider = recorderProvider;
    }

    @Override
    public AsyncUncaughtExceptionHandler
            getAsyncUncaughtExceptionHandler() {
        return (error, method, args) -> {
            recorderProvider.getObject().record(
                    method.getName(), error);
        };
    }
}
```

This example requires `ErrorRecorder` to be declared in the project; it is not a standalone runnable Java class. Key point: **do not call `recorderProvider.getObject()` eagerly inside `getAsyncUncaughtExceptionHandler()`** if the goal is to defer initialization. Resolve the bean only when the handler actually handles an error, while still guarding against secondary failures/re-entrant cycles.

If only logging is needed, a stateless handler with no complex bean dependencies is easier to test and operate.

## 10. Customizing the default executor and the handler are two separate concerns

The same class can override both:

```java
@Override
public Executor getAsyncExecutor() {
    return defaultExecutor;
}

@Override
public AsyncUncaughtExceptionHandler
        getAsyncUncaughtExceptionHandler() {
    return customHandler;
}
```

These are **two illustrative method fragments**, assuming `defaultExecutor` and `customHandler` are properly configured and managed within the application lifecycle.

`getAsyncExecutor()` specifies the **default pool** for `@Async` methods that do not pick an executor. `@Async("backgroundExecutor")` can select a specific executor bean by name/qualifier even when the default executor differs. The handler from `getAsyncUncaughtExceptionHandler()` still serves errors from `@Async void` processed by the infrastructure in the same context, rather than “only catching errors from the default pool”.

If no default executor is configured, Spring searches according to `TaskExecutor` bean / `taskExecutor` bean rules; if none is found, it may fall back to `SimpleAsyncTaskExecutor`. In environments with multiple executors, define routing explicitly and do not rely on implicit selection.

**Do not create a dedicated pool inside the handler just for logging.** The handler executes in the error-handling context of a task; if telemetry must be pushed elsewhere, enforce resource limits, timeouts, and fallbacks. Recursively submitting error-logging tasks back onto the same overloaded pool can make matters worse.

## 11. Proxies and @EnableAsync: why doesn't the handler run?

### 11.1. Calling within the same bean (self-invocation)

```java
public void outer() {
    this.failAsync();  // Bypasses proxy in default mode.
}

@Async("backgroundExecutor")
public void failAsync() {
    throw new IllegalStateException("Error");
}
```

This is an anti-example inside one class. With proxy-based `@Async`, the call `this.failAsync()` does not pass through the interceptor, so Java executes the method directly. The caller/`outer()` may see the exception as a synchronous error. The `@Async` handler never gets a chance to receive it.

Common fix: move the async method to another bean, inject that bean, and call it through the Spring-managed proxy. Do not call private/final methods expecting a CGLIB proxy to intercept every situation.

### 11.2. Instantiating the object manually with new

```java
new NotificationService().send("job-42");
```

If the object is not Spring-managed, `@Async` is just a source-code annotation; calls do not automatically dispatch to an executor. Retrieve the Spring-managed bean from the context and ensure `@EnableAsync` is active in the right context.

### 11.3. Multiple ApplicationContexts

In applications with a root context and a servlet context, enabling `@EnableAsync` in one context does not automatically proxy every bean in another context. Place the configuration where the business beans reside and verify with an integration test.

### 11.4. @Async method returning an unsupported type

Standard Spring `@Async` supports `void` or `Future` types such as `CompletableFuture`. The signature `@Async public String load()` is invalid for the async interceptor and cannot turn a synchronous `String` into an immediately returned result. Return-type errors are not runtime exceptions from an `@Async void` body for the handler to process.

## 12. Handling secondary handler failures

The handler is invoked when a task has already encountered a failure. If the handler in turn calls an unavailable database, network, or telemetry backend, the handler itself can fail.

Spring has a mechanism to log a warning when `AsyncUncaughtExceptionHandler` throws an unexpected error itself; however, the `@Async void` caller still has no Future to receive this error, so **it must not be treated as a reliable recovery path**.

A practical handler should:

1. Record exception type, message, stack trace, and method/operation sufficient for investigation.
2. Log only permitted arguments, avoiding passwords/tokens/full payloads.
3. Never loop retries indefinitely or blindly re-submit the same work.
4. Have minimal fallback logging/metrics if the state store cannot be written.
5. Perform no unbounded waits or hold shared locks during I/O calls.
6. Distinguish expected business errors from infrastructure failures to prevent alert fatigue.
7. If persisting `FAILED` job status is needed, design transactions, write reliability, and idempotency separately.

A handler pattern with fallback (method snippet in a class with `logger` and `errorStore`):

```java
@Override
public void handleUncaughtException(
        Throwable error, Method method, Object... args) {
    String operation = method.getName();
    try {
        errorStore.markFailed(operation, error);
    } catch (RuntimeException reportingFailure) {
        logger.error("Async task failed: " + operation, error);
        logger.warn("Failed to record failure status",
                reportingFailure);
    }
}
```

`errorStore` and `logger` here are application components, not built-in Java APIs. Do not treat this snippet as a standalone class; the principle is **never let secondary error-recording hide the root error**.

## 13. Logging, metrics, and data protection

An error event may include these fields:

| Field | Why needed | Notes |
|---|---|---|
| `operation`/`method` | Identify which business operation failed | Names have bounded cardinality |
| `exceptionType` | Classify connection/logic/timeout failures | Do not print only the message |
| `jobId`/`correlationId` | Correlate execution attempts | Check logging permissions |
| `executorName` | Isolate resource pools | Do not always infer from thread name |
| `attempt` | Track attempt number when retrying | Prevent double counting |
| `elapsed` | Distinguish instant failures from long waits | Measure queue wait separately |
| `status` | Submitted/accepted/started/failed | Do not equate accepted with succeeded |

Log sample **illustrating format**, not Spring's default output:

```text
level=ERROR operation=sendNotification
jobId=J-102 exception=IllegalStateException
executor=backgroundExecutor message="Provider unavailable"
```

When using Micrometer/Prometheus, a counter can carry operation and exception type labels. **Do not put `jobId` as a metric tag**, because each new ID creates a new time series, causing high cardinality. Job IDs belong in logs/traces governed by appropriate data policies.

A handler merely logging does not mean job tracking exists. If clients need to query `FAILED/SUCCEEDED` by job ID, the application must design a state store and query interface; it cannot be inferred from `AsyncConfigurer`.

## 14. Transactions, security, and context do not propagate automatically

`@Async` typically moves the method body onto a worker thread. A Spring transaction bound to the caller does not automatically become the same transaction on the worker. If the worker calls the database and fails, the handler does not automatically roll back the caller's earlier transaction.

```text
Request thread:
  @Transactional starts TX-A
  submits @Async void job
  TX-A commits or rolls back per caller policy

Worker thread:
  runs independently in time
  if transaction needed, design TX-B on worker
  unhandled error -> AsyncUncaughtExceptionHandler
```

If a background task reads data the caller has not yet committed, it may see stale state or miss the record depending on transaction isolation. For requirements that must run **only after commit**, consider transaction events/outbox or mechanisms guaranteeing submission timing.

`SecurityContextHolder`, MDC, custom `ThreadLocal`, and request context are not automatically and completely propagated to the worker when using an arbitrary executor. If the handler needs a correlation ID, pass it in task parameters or use tested context propagation, and do not retain request objects past their lifecycle.

**The handler does not roll back external systems.** An already-sent email or a partially executed payment action may require business-level reconciliation and compensation.

## 15. Differences from ExecutorService, @Scheduled, and web exception handlers

`AsyncUncaughtExceptionHandler` belongs to **Spring `@Async`** infrastructure, not a global JVM exception handler.

| Mechanism | Typical error channel |
|---|---|
| `@Async void` through Spring proxy | `AsyncUncaughtExceptionHandler` |
| `@Async Future<T>`/`CompletableFuture<T>` | Caller's Future/callback |
| `ExecutorService.submit(...)` | Future returned by `submit` |
| Plain Java `ThreadPoolExecutor.execute(Runnable)` | Worker's `UncaughtExceptionHandler` or task wrapper |
| `@Scheduled` | Corresponding scheduling `ErrorHandler`/scheduler policy |
| Synchronous Spring MVC handler | Web exception resolvers/`@ControllerAdvice` per configuration |
| Rejection when submitting to pool | Caller/submission boundary, not void-handler by default |

For instance, `@Scheduled` can be configured with Spring scheduling's `ErrorHandler`; do not wire `AsyncConfigurer` and assume every `@Scheduled` task uses the same handler. An application may use both `@Async` and `@Scheduled`, but the two annotations represent different execution paths.

If a task returns a result that the caller fails to observe via the Future, that is **missing error handling on the caller**; Spring does not automatically route that exception to the void handler just because the Future was ignored.

## 16. How to test the handler properly without relying on sleep

An integration test should build a Spring context with `@EnableAsync`, a bounded executor bean, and `AsyncConfigurer`. Invoke the service through the proxy and use `CountDownLatch` or a callback to observe the handler.

A JUnit test fragment (not standalone, requires test context and assertions):

```java
CountDownLatch handled = new CountDownLatch(1);
AtomicReference<Throwable> observed = new AtomicReference<>();
AtomicReference<String> methodName = new AtomicReference<>();

AsyncUncaughtExceptionHandler testHandler = (error, method, args) -> {
    observed.set(error);
    methodName.set(method.getName());
    handled.countDown();
};

// Register testHandler via AsyncConfigurer in the test context
// then invoke the Spring-managed service:
service.failVoid("test-1");

assertTrue(handled.await(5, TimeUnit.SECONDS));
assertEquals("failVoid", methodName.get());
assertInstanceOf(IllegalStateException.class, observed.get());
```

You must **actually register** `testHandler` in `AsyncConfigurer` when building the context; merely creating a handler variable in the test does not make Spring use it. `AtomicReference`, `TimeUnit`, and assertion methods need corresponding imports. For a complete standalone example, use `AsyncHandlerDemo` in section 6.

Important scenarios:

1. `@Async void` throws an exception: handler receives the expected `Throwable`, `Method`, and `args`.
2. `@Async void` succeeds: handler is not invoked.
3. `@Async CompletableFuture` fails: Future reports failure; handler receives no extra invocation for this error.
4. Executor rejects: caller observes rejection per policy.
5. Self-invocation: prove why the handler does not receive the error because advice does not run.
6. Handler itself fails: fallback still records the root error at an appropriate level.
7. Arguments contain sensitive data: not logged in full.
8. Application shutting down / queue full: do not claim the task succeeded when it was only accepted.

`Thread.sleep(100)` does not prove the worker or handler finished: in CI/production, timing fluctuates. A completion signal with a timeout is far better evidence.

## 17. Common misconceptions

| Misconception | Reality |
|---|---|
| `AsyncConfigurer` automatically handles all async errors | It only configures the default executor and handler for void methods whose errors cannot return to the caller |
| Once the handler is configured, Future errors need no handling | Future-typed methods still require caller observation |
| `try/catch` around the caller catches all worker exceptions | With an async pool, errors usually occur after the caller has returned |
| `@Async void` cannot cause exceptions because it returns `void` | Runtime exceptions can still be thrown inside the method body |
| The handler is called even when the executor did not accept the task | Rejection is on the submission path, usually belonging to the caller |
| `@EnableAsync` automatically creates a production-ready thread pool sized for load | You must define/select an executor and bound resources |
| `this.asyncMethod()` triggers the Spring proxy | Self-invocation bypasses advice in default proxy mode |
| When a `Future` throws, the void handler also receives it | The exception stays in the Future and must be observed |
| Handler logging means business logic retried | Logging does not perform retries or rollbacks |
| The handler can log all data in `params` | Must protect/mask sensitive data and avoid large payloads |
| `AsyncConfigurerSupport` is the latest approach | Deprecated since Spring 6.0; implement the interface directly |
| A handler writing errors to DB automatically uses the caller's transaction | Worker/context have different boundaries; use a separate transaction if needed |
| An accepted task means it will survive a JVM crash | An in-memory pool is not a durable queue |

## 18. Practice exercises

### Exercise 1 — Configure a simple handler

Create a `@Configuration @EnableAsync implements AsyncConfigurer` class returning an `AsyncUncaughtExceptionHandler`. The handler logs the method name, exception class, and permitted job ID. Create a bean with `@Async("backgroundExecutor") void fail(String id)` throwing `IllegalStateException`.

**Hint:** Call from another bean through the Spring proxy and use a latch to confirm the handler ran. Do not use `Thread.sleep` to guess.

### Exercise 2 — void vs. Future

Two methods `void push()` and `CompletableFuture<String> load()` both throw errors. Which error does `AsyncConfigurer`'s handler receive? What must the caller do with the other error?

**Hint:** The handler receives the `void` error. The Future holds `load()`'s error; use `whenComplete`, `handle`, or `join/get` at a boundary where blocking is acceptable.

### Exercise 3 — Submission failure

The executor is full and `@Async void` is rejected on submit. Is it guaranteed that the handler will record it? What is wrong if the API returns HTTP 202 while the job was rejected?

**Hint:** The handler does not automatically catch rejections; the caller must respond with overload per contract. HTTP 202 must not be used to claim work was accepted if it was actually rejected.

### Exercise 4 — Lazy dependency

An `AsyncConfigurer` injects `ErrorRecorder` which has `@Transactional` and requires a proxy. Why shouldn't that bean be resolved eagerly during bootstrap? How do you use `ObjectProvider`?

**Hint:** The configurer is initialized early; defer `getObject()` until the handler actually runs, while ensuring no circular dependencies are created.

### Exercise 5 — Security and metrics

The handler receives arguments including a job ID and an API token. Which fields would you log, and why shouldn't you attach the job ID as a metric label?

**Hint:** Log method, exception type, permitted job ID, and correlation ID; mask the token. Metrics should use bounded-cardinality labels such as operation and error type.

### Exercise 6 — Handler fails itself

The handler writes `FAILED` status to a database, but the database is down. Does the caller receive the secondary error? Design a fallback that does not hide the original error.

**Hint:** The caller of void async has no handle and cannot rely on exception propagation back; use fallback logging and separate job status observability.

### Exercise 7 — Run the demo

Run `AsyncHandlerDemo` with the Maven command in section 6. Explain why both methods throw errors yet only one `Handler: ...` line appears.

**Hint:** `failVoid` routes its error to the handler. `failFuture` routes its error through the Future observed by the caller's `join()`.

## 19. Deployment checklist

Before taking an `@Async` handler to production:

1. `@EnableAsync` is active in the context containing the beans; callers invoke through the Spring proxy.
2. The configuration class implements `AsyncConfigurer` and properly overrides `getAsyncUncaughtExceptionHandler()`.
3. The handler logs exception type/stack trace and method; it does not log secrets or full payloads.
4. Exceptions from `void` methods are not confused with Future-typed methods or submission rejections.
5. The executor has bounded workers/queue and an explicit rejection policy.
6. Entire request objects or sensitive thread-locals are not passed to tasks/handlers without a propagation mechanism.
7. If the handler uses other beans, account for early `AsyncConfigurer` initialization and prefer lazy dependencies when needed.
8. The handler has fallbacks, performs no unbounded retries, and does not block workers for too long.
9. Correlation IDs/job IDs exist, distinguishing accepted/started/succeeded/failed.
10. If business requirements demand survival across restarts, use durable storage/queues.
11. Integration tests verify the real handler and Future errors, not just the presence of annotations.
12. It is understood that the handler does not roll back the caller's transaction or external system side effects.

## 20. Key takeaways

- **`AsyncConfigurer.getAsyncUncaughtExceptionHandler()`** is the standard API for configuring a handler for uncaught exceptions from **`@Async void`** methods that cannot propagate back to the caller.
- The handler receives **`Throwable`, `Method`, and `Object... params`**, and must process and log safely without exposing sensitive data.
- **Future and CompletableFuture have their own error channels**; do not expect the void handler to receive every asynchronous error.
- **Executor rejection, bean misconfiguration, and self-invocation** follow different paths from runtime exceptions inside an already-running method body.
- **`@EnableAsync`, Spring-managed beans, and proxy-based invocation** are the core prerequisites for the handler to be used properly in proxy mode.
- **The configurer may initialize early**; avoid complex dependencies or resolving proxied beans eagerly during bootstrap.
- **The handler is not a durable retry/job-queue system.** Status observability, idempotency, timeouts, and compensation must be designed according to business requirements.

### Official references

- [Spring Framework Javadoc — AsyncConfigurer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/AsyncConfigurer.html)
- [Spring Framework Javadoc — EnableAsync](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html)
- [Spring Framework Javadoc — AsyncUncaughtExceptionHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/interceptor/AsyncUncaughtExceptionHandler.html)
- [Spring Framework Javadoc — SimpleAsyncUncaughtExceptionHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/interceptor/SimpleAsyncUncaughtExceptionHandler.html)
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Java SE 17 Javadoc — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)

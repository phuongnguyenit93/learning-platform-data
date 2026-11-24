# Capture Context on the Sender and Restore Prior State Using `try-finally`

**Module:** Spring Framework - concurrency  
**Group:** Execution Context  
**Topic:** Capturing context on the sender and restoring prior state using `try-finally`.

## 1. The Problem: A Request Crosses Multiple Threads, but Context Does Not Automatically Follow

In a Spring application, an incoming HTTP request typically carries metadata for processing and observability: `traceId`, `requestId`, tenant name, locale, or a security context. Several libraries store this information in `ThreadLocal` or MDC (Mapped Diagnostic Context) so you do not have to pass it manually to every logging method.

For example, a request has `traceId=REQ-A` and then calls an `@Async` method:

```text
Servlet thread: http-nio-8080-exec-1
   MDC.traceId = REQ-A
           |
           | executor.execute(task)
           v
Thread pool worker: business-1
   MDC.traceId = ?     <- does not automatically match sender thread
```

**`ThreadLocal` binds data to a thread, not to a logical request or a Runnable.** When a `Runnable` moves from the request-handling thread to a pool thread, the sender thread's `ThreadLocal` values are not automatically copied to the worker thread. An executor may reuse the same worker across thousands of different tasks.

If a worker previously handled request A and left `traceId=A` behind, a subsequent task B running on that worker may:

- Log with A's `traceId` even though B comes from a different request.
- Use the wrong tenant/user context if code relies on ThreadLocal.
- Distort error observability, auditing, and request statistics.
- Leak sensitive data between logical requests.

Two requirements must be solved **at the same time**:

1. **Propagate the exact snapshot of the sender thread** at the time the task is submitted.
2. **Accurately restore the worker thread's existing state** after the task finishes — **even if the task throws an exception**.

The solution is **capture → install → run → restore** with `try-finally`, rather than merely setting a value and hoping the pool clears it automatically.

## 2. Four Moments and One Invariant That Must Never Be Violated

Suppose the sender thread has `requestId=A`, and the worker has `requestId=WORKER-BASELINE` temporarily set by outer wrapping code. The flow:

```text
T0: SUBMITTER                         T1: WORKER
    requestId = A                        requestId = WORKER-BASELINE
         |
    capture snapshot = A
         |
    executor.execute(wrappedTask) ----------->
                                              previous = WORKER-BASELINE
                                              try {
                                                  install(A)
                                                  delegate.run()
                                              } finally {
                                                  restore(WORKER-BASELINE)
                                              }
                                          -> requestId = WORKER-BASELINE
```

**Key invariant:** once the callback completes (whether succeeding or failing), the executing thread's context must return to **the exact state before the callback began**, not to a constant or to a snapshot from a prior request.

| Moment | Executing Thread | Action |
| --- | --- | --- |
| T0 — create wrapper / submit task | **Sending** thread | Read/copy values to propagate; do not wait until the worker |
| T1 — start of `run()` | **Executing** thread | Read the worker's current state and save it to `previous` |
| T2 — before calling business work | Executing thread | Install snapshot from sender; if the snapshot has no value, **clear** the old value |
| T3 — inside `finally` | Executing thread | Restore `previous` — even if business work fails, has a `return`, or has nested decorators |

### Why Must You Snapshot **Before Enqueuing**?

A task may wait in the queue for seconds before a worker picks it up. During that time, the HTTP thread may:

- Change `traceId` to process another step.
- Clear MDC upon completing the request.
- Be reused by the servlet container for the next request.

If a wrapper captures the value **inside `run()`**, it reads **the worker's context at run time**, not the request's context at submit time. You must capture inside `execute(...)`, `decorate(...)`, or at the callsite on the **sending thread**.

## 3. Minimal Java Pattern, in the Right Order

A basic wrapper for `ThreadLocal<String>`:

```java
private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

static void setOrRemove(String value) {
    if (value == null) {
        REQUEST_ID.remove();
    } else {
        REQUEST_ID.set(value);
    }
}

static Runnable wrapWithCurrentContext(Runnable delegate) {
    String captured = REQUEST_ID.get(); // Sending thread: CAPTURE NOW.
    return () -> {
        String previous = REQUEST_ID.get(); // Running thread: SAVE OLD CONTEXT.
        try {
            setOrRemove(captured);       // Install snapshot, even if null.
            delegate.run();             // Run business work.
        } finally {
            setOrRemove(previous);       // Restore accurately.
        }
    };
}
```

This is an **illustrative member snippet** and needs to be placed inside a class with appropriate imports. If used as:

```java
executor.execute(wrapWithCurrentContext(() -> process()));
```

`process()` and `executor` must be defined by the application. **Key point:** `wrapWithCurrentContext()` is called on the submitter thread before `executor.execute`, and `delegate.run()` is called only **once** inside the wrapper.

`ThreadLocal.remove()` is better than `ThreadLocal.set(null)` when you want to remove the binding completely. If `previous == null`, we **remove** in `finally`; if the worker previously had a non-null value, we must **restore that value**, rather than calling `remove()` unconditionally.

Some libraries allow a snapshot to hold multiple fields, yet the principle stays identical: an immutable snapshot or defensive copy at submission time; saving **all state needing restoration** at run time; cleaning/restoring via `finally`.

## 4. Why Calling Only `remove()` in `finally` Can Be Wrong

A commonly seen pattern:

```java
Runnable wrapped = () -> {
    REQUEST_ID.set(capturedId);
    try {
        businessWork();
    } finally {
        REQUEST_ID.remove();
    }
};
```

This is an illustrative snippet where `capturedId` and `businessWork()` are provided by the application. This pattern might suffice in **a** system where workers always start empty and there are no nested wrappers, yet it **does not properly restore the prior state**.

For example:

1. An outer task sets `requestId=A`.
2. A component inside the outer task invokes an executor running **directly on the same thread** (`Runnable::run`) or via `CallerRunsPolicy`, creating an inner task with `requestId=B`.
3. The inner task finishes and calls `remove()`.
4. The outer task resumes execution, but `requestId=A` has been **wiped out**.

```text
Outer:  previous=null -> set A
    Inner: previous=A -> set B -> finally restore A   [correct]
Outer:  still sees A -> finally restore null
```

Use `try-finally` to **restore previous**, rather than just clearing to "empty", so that it composes with nested decorators and executors that can run inline. For a completely blank worker, `previous=null`, so the end result is still `remove()`, yet the more general rule avoids breaking outer code's context.

### `CallerRunsPolicy` Makes This Problem Practical

When the pool is full, `ThreadPoolExecutor.CallerRunsPolicy` can run the task **directly on the submitting thread**, if the executor has not been shut down. `try-finally` must restore **that thread's** context, even though it was originally a servlet/request thread rather than a dedicated worker. Never write a decorator assuming every task always runs on a fresh thread with an empty `ThreadLocal`.

## 5. Why Must a Snapshot Be Copied, Not Just Held by Reference?

For an immutable value such as `String requestId`, keeping a reference to the `String` is enough. However, a `ThreadLocal<Map<String,String>>` holding a **mutable object** can be modified by the sending thread after submission:

```java
Map<String, String> captured = currentMap; // Only copies the reference!
executor.execute(() -> use(captured));
currentMap.put("tenant", "another-tenant");
```

This is an illustrative snippet (`currentMap`, `executor`, `use` must exist). The worker may observe late-mutated data, or even encounter races when multiple threads read/write an unsafe `HashMap`.

When snapshotting is needed:

```java
Map<String, String> captured =
        currentMap == null ? Map.of() : Map.copyOf(currentMap);
```

This is a Java 17 illustrative snippet; `Map.copyOf` produces a map that cannot be modified via map APIs, yet it **only performs a shallow copy**: if values are mutable objects, those values still share references. `Map.copyOf` also rejects null keys/values. For nested structures, you must perform deep copies where required or convert into a validated immutable DTO.

**Do not snapshot an entire HTTP request, session, JDBC connection, entity manager, transaction, or sensitive credentials** out of convenience. Pass **minimal values** instead, such as `correlationId`, verified tenant ID, and required business parameters.

### Snapshot vs. "Always-Up-to-Date Context"

Context propagation uses **the value at submission time**; if the sending thread changes `traceId` afterward, the queued task still uses the old snapshot. That is the desired property so logs belong to the right originating request.

## 6. Standalone Runnable Java 17: Capture at Submit, Test Errors, and Restore Both Worker/Caller

The program below requires no Spring and lets you verify the **exact** semantics of `try-finally`. It uses a single-thread executor to prove thread reuse. `CountDownLatch` holds the worker while the sending thread modifies context, so the test does not rely on `Thread.sleep` or guessing scheduling.

Goals:

- Capture `request-A` **before the task runs**, even if the caller changes to `changed-after-submit`.
- Request B's task sees `request-B`, not A.
- If the sending thread **has no context**, the task must see `null`, even though the worker already has `worker-baseline`.
- A task throwing an error still returns the worker to its initial context.
- An executor running inline (`Runnable::run`) must also restore the **caller's** context after the callback mutates ThreadLocal.
- `FutureTask` retains the exception for `Future.get`, while the wrapper's `finally` still runs.

Save everything into **`ContextSnapshotDemo.java`**:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;

public class ContextSnapshotDemo {

    private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

    static void setOrRemove(String value) {
        if (value == null) {
            REQUEST_ID.remove();
        } else {
            REQUEST_ID.set(value);
        }
    }

    static final class SnapshotExecutor implements Executor {
        private final Executor delegate;

        SnapshotExecutor(Executor delegate) {
            this.delegate = delegate;
        }

        @Override
        public void execute(Runnable task) {
            // CAPTURE on submitter thread, before putting task in queue.
            String captured = REQUEST_ID.get();

            delegate.execute(() -> {
                // SAVE on the thread actually running the task.
                String previous = REQUEST_ID.get();
                try {
                    setOrRemove(captured);
                    task.run();
                } finally {
                    setOrRemove(previous);
                }
            });
        }
    }

    static <T> Future<T> submit(Executor executor, Callable<T> work) {
        FutureTask<T> future = new FutureTask<>(work);
        executor.execute(future);
        return future;
    }

    public static void main(String[] args) throws Exception {
        ExecutorService raw = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            // Set old context on worker thread to verify restoration.
            raw.submit(() -> setOrRemove("worker-baseline")).get();

            SnapshotExecutor propagated = new SnapshotExecutor(raw);

            // Keep worker busy so task A is guaranteed to stay in queue.
            raw.execute(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker not started");
            }

            setOrRemove("request-A");
            Future<String> first = submit(propagated, REQUEST_ID::get);

            // Change context AFTER submit but BEFORE task A runs.
            setOrRemove("changed-after-submit");
            release.countDown();

            System.out.println("snapshotAtSubmit=" + first.get());

            setOrRemove("request-B");
            System.out.println("secondRequest=" +
                    submit(propagated, REQUEST_ID::get).get());

            // Null snapshot must temporarily clear the worker's context.
            setOrRemove(null);
            System.out.println("missingSnapshot=" +
                    submit(propagated, () ->
                            REQUEST_ID.get() == null
                                    ? "<none>" : REQUEST_ID.get()).get());

            setOrRemove("request-error");
            Future<String> failure = submit(propagated, () -> {
                throw new IllegalStateException("boom");
            });
            try {
                failure.get();
            } catch (ExecutionException ex) {
                System.out.println("failure=" +
                        ex.getCause().getClass().getSimpleName());
            }

            // Test the same decorator pattern when running directly on caller.
            setOrRemove("caller-before-inline");
            SnapshotExecutor direct =
                    new SnapshotExecutor(Runnable::run);
            direct.execute(() -> setOrRemove("temporary-in-task"));

            System.out.println("callerAfterInline=" + REQUEST_ID.get());
            setOrRemove(null);

            // Read directly from raw executor to confirm worker restoration.
            String restoredWorker = raw.submit(
                    (Callable<String>) REQUEST_ID::get).get();
            System.out.println("workerAfterAll=" + restoredWorker);
        } finally {
            release.countDown();
            setOrRemove(null);
            raw.shutdown();
            if (!raw.awaitTermination(5, TimeUnit.SECONDS)) {
                raw.shutdownNow();
            }
        }
    }
}
```

Run in the directory containing the file with Java 17+:

```bash
javac ContextSnapshotDemo.java
java ContextSnapshotDemo
```

**Program stdout on normal completion:**

```text
snapshotAtSubmit=request-A
secondRequest=request-B
missingSnapshot=<none>
failure=IllegalStateException
callerAfterInline=caller-before-inline
workerAfterAll=worker-baseline
```

Explanation:

1. `snapshotAtSubmit=request-A` even though `REQUEST_ID` on the sender changed before the worker was released. The wrapper captures inside `execute`, not when running.
2. `secondRequest=request-B`: task B does not inherit A or the baseline from the worker's prior use.
3. `missingSnapshot=<none>`: the wrapper handles a null snapshot with `remove`, avoiding reading the stale `worker-baseline` value already on the worker.
4. `failure=IllegalStateException`: `FutureTask` records the exception, while the wrapper still runs `finally`.
5. `callerAfterInline=caller-before-inline`: executor `Runnable::run` runs the callback directly on the caller; restoring `previous` protects the request context even when the callback assigns another value.
6. `workerAfterAll=worker-baseline`: after A, B, the empty task, and the failing task, the worker still has the exact context it had before the wrappers started. No A/B leak into subsequent uses.

**Limitation:** the demo deliberately puts a `ThreadLocal` on the worker to verify the mechanism. In production, the worker should be left in an appropriate state after each task, typically **empty**. Storing `worker-baseline` in a pool here is not a design recommendation for real applications.

## 7. `TaskDecorator` in Spring: Capture in `decorate`, Restore in `run`

Spring provides `org.springframework.core.task.TaskDecorator` to wrap a callback before the executor runs the task. Writing it is similar to the JDK wrapper:

```java
import org.springframework.core.task.TaskDecorator;

public final class RequestIdTaskDecorator implements TaskDecorator {

    private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

    @Override
    public Runnable decorate(Runnable callback) {
        String captured = REQUEST_ID.get(); // SENDING thread.
        return () -> {
            String previous = REQUEST_ID.get(); // RUNNING thread.
            try {
                if (captured == null) {
                    REQUEST_ID.remove();
                } else {
                    REQUEST_ID.set(captured);
                }
                callback.run();
            } finally {
                if (previous == null) {
                    REQUEST_ID.remove();
                } else {
                    REQUEST_ID.set(previous);
                }
            }
        };
    }
}
```

This is a **structurally complete Java class**, but an application wishing to use the same `REQUEST_ID` must expose an API to set/get on the sending thread; this simple example keeps the field `private` to focus on the algorithm. The next section uses MDC, a ready-made API for Spring Boot applications.

Wiring it into a Spring executor:

```java
@Bean("businessExecutor")
public ThreadPoolTaskExecutor businessExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(64);
    executor.setThreadNamePrefix("business-");
    executor.setTaskDecorator(new RequestIdTaskDecorator());
    return executor;
}
```

This is an **illustrative configuration method snippet**, requiring `@Bean`, `ThreadPoolTaskExecutor` imports and placement in a configuration class. Do not call `initialize()` manually if `ThreadPoolTaskExecutor` is actually registered as a Spring bean; Spring manages the normal lifecycle.

**Two misconceptions to avoid:**

- `decorate()` runs at the **task submission boundary**; only the value read inside `decorate` is the snapshot from the sending thread. If `decorate` merely returns a lambda and the lambda itself calls `ThreadLocal.get()` to "capture", you are already too late.
- `TaskDecorator` may wrap an **internal execution callback** like `FutureTask`, not necessarily the original `Runnable`/`Callable`. With `submit`, exceptions may be held by `FutureTask` rather than escaping `callback.run()`. Thus `try-finally` is definitely useful for cleanup, yet `catch` in a decorator **is not** a catch-all mechanism for business errors. You must observe `Future.get`, `CompletableFuture.whenComplete`, or an appropriate error handler.

## 8. Copying and Restoring the Entire MDC Instead of Just One Key

In applications using SLF4J/Logback, MDC attaches `traceId`, `requestId`, and `tenant` pairs to the thread's logs. When propagating MDC to an executor, you can copy the entire map at submit time and **restore the worker's entire prior map**.

A proper `TaskDecorator`:

```java
import java.util.Map;

import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

public final class MdcSnapshotTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable callback) {
        // T0: snapshot immediately on the sending thread.
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            // T1: save the current map of the thread about to run the callback.
            Map<String, String> previous = MDC.getCopyOfContextMap();

            try {
                // T2: install snapshot, even when the submitter has no MDC.
                restore(captured);
                callback.run();
            } finally {
                // T3: restore exact state prior to the callback.
                restore(previous);
            }
        };
    }

    private static void restore(Map<String, String> map) {
        if (map == null || map.isEmpty()) {
            MDC.clear();
        } else {
            MDC.setContextMap(map);
        }
    }
}
```

Points to note:

- `MDC.getCopyOfContextMap()` provides a **copy** of the context map when the MDC backend supports it. Never store `MDC` as a shared mutable singleton map across threads.
- When the snapshot is `null` or empty, call `MDC.clear()` on the worker **before** running the callback; otherwise, logs may carry traces from a previous task.
- `previous` is retrieved **after the worker starts**, right before installing the snapshot, and restored in `finally`; this supports nested wrappers or direct same-thread execution.
- `MDC.setContextMap` replaces the current context map according to the supported backend. Do not merely call `MDC.put("traceId", captured)` and leave leftover `tenant`/`user` keys intact on the worker.
- Do not log or automatically propagate sensitive values such as access tokens, passwords, or session cookies. Put into MDC only fields permitted by security policy.
- If the application uses a logging backend without true MDC support, verify actual support. The Spring Boot example below uses Logback via starter so MDC works.

### Why Restore **the Prior Map** Instead of Calling `MDC.clear()` at the End?

Suppose task A is running with map `{traceId=A, spanId=1}`, and invokes callback B directly on **the same thread** with `{traceId=B, spanId=2}`. If B ends with `MDC.clear()`, A loses all its info. If B saves `previous={traceId=A,spanId=1}` and calls `MDC.setContextMap(previous)` in `finally`, A continues with its original map.

This is especially critical when an executor uses `CallerRunsPolicy`, tests use `Runnable::run`, or a library runs nested callbacks on the completion thread.

## 9. Runnable Spring Boot Example: MDC Across `@Async` With a Reused Thread Pool

**Java 17+**, **Spring Boot 3.5.7** (Spring Framework 6.2.x), Maven example. The program does not open an HTTP server; it simulates three distinct requests on the main thread, calls a Spring `@Async` service through a proxy, and checks MDC results on the worker:

1. Request A submits with `traceId=req-A`, then the caller switches to `req-B`.
2. Request B submits with `traceId=req-B`.
3. Caller clears MDC; the third task must see `<none>`, neither A nor B.
4. An `@Async` method throws an error; the caller observes an exceptional Future. The decorator still restores MDC despite the error.

### 9.1. Project Structure

```text
mdc-async-demo/
├── pom.xml
└── src/main/java/com/example/mdcdemo/
    ├── MdcAsyncApplication.java
    ├── AsyncConfiguration.java
    ├── MdcTaskDecorator.java
    └── ContextService.java
```

### 9.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>mdc-async-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

This Spring Boot starter pulls in AOP, Spring Context, and the default logging backend needed for the `MDC` example. No `@WebMvcTest` or servlet container configuration is needed to practice `@Async`.

### 9.3. `src/main/java/com/example/mdcdemo/MdcTaskDecorator.java`

```java
package com.example.mdcdemo;

import java.util.Map;

import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

public final class MdcTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable callback) {
        final Map<String, String> snapshot = MDC.getCopyOfContextMap();

        return () -> {
            final Map<String, String> previous = MDC.getCopyOfContextMap();

            try {
                restore(snapshot);
                callback.run();
            } finally {
                restore(previous);
            }
        };
    }

    private static void restore(Map<String, String> context) {
        if (context == null || context.isEmpty()) {
            MDC.clear();
        } else {
            MDC.setContextMap(context);
        }
    }
}
```

### 9.4. `src/main/java/com/example/mdcdemo/AsyncConfiguration.java`

```java
package com.example.mdcdemo;

import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncConfiguration {

    @Bean("contextExecutor")
    public ThreadPoolTaskExecutor contextExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(8);
        executor.setThreadNamePrefix("context-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.setTaskDecorator(new MdcTaskDecorator());
        return executor;
    }
}
```

A single worker is used to easily demonstrate **thread reuse**. In production, size core/max/queue based on real load and deadlines; do not take the example's `1/1/8` values as defaults.

### 9.5. `src/main/java/com/example/mdcdemo/ContextService.java`

```java
package com.example.mdcdemo;

import java.util.concurrent.CompletableFuture;

import org.slf4j.MDC;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ContextService {

    @Async("contextExecutor")
    public CompletableFuture<String> readTrace() {
        String traceId = MDC.get("traceId");
        return CompletableFuture.completedFuture(
                traceId == null ? "<none>" : traceId);
    }

    @Async("contextExecutor")
    public CompletableFuture<String> fail() {
        throw new IllegalStateException("demo failure");
    }
}
```

`readTrace()` executes on the worker chosen by the Spring proxy. Inside the body, `CompletableFuture.completedFuture(...)` **does not** spawn a second async task. With Spring, the Future returned from the proxy to the caller may differ from the temporary Future object created by the target method. `fail()` throws an exception on the worker, and the caller-side Future completes exceptionally; the error handler for `@Async void` is not where this error is handled.

### 9.6. `src/main/java/com/example/mdcdemo/MdcAsyncApplication.java`

```java
package com.example.mdcdemo;

import java.util.Map;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;

import org.slf4j.MDC;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class MdcAsyncApplication {

    public static void main(String[] args) throws Exception {
        SpringApplication app = new SpringApplication(MdcAsyncApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);
        app.setDefaultProperties(Map.of("logging.level.root", "OFF"));

        try (ConfigurableApplicationContext context = app.run(args)) {
            ContextService service = context.getBean(ContextService.class);

            MDC.put("traceId", "req-A");
            var first = service.readTrace();

            // After submitting A, caller changes MDC; worker still uses snapshot A.
            MDC.put("traceId", "req-B");
            System.out.println("first=" +
                    first.get(5, TimeUnit.SECONDS));
            System.out.println("second=" +
                    service.readTrace().get(5, TimeUnit.SECONDS));

            MDC.clear();
            System.out.println("empty=" +
                    service.readTrace().get(5, TimeUnit.SECONDS));

            try {
                service.fail().get(5, TimeUnit.SECONDS);
            } catch (ExecutionException ex) {
                System.out.println("futureError=" +
                        ex.getCause().getClass().getSimpleName());
            }
        } finally {
            MDC.clear();
        }
    }
}
```

In the directory containing `pom.xml`:

```bash
mvn -q spring-boot:run
```

**Four lines explicitly printed by `System.out` on normal completion:**

```text
first=req-A
second=req-B
empty=<none>
futureError=IllegalStateException
```

The build tool or environment may print its own extra info. The example disables banner/root logging to focus on output, yet does not depend on thread names to decide business logic.

Mechanism explanation:

- `first=req-A`: `TaskDecorator.decorate()` captures MDC before Spring puts the task in the queue, so the caller switching to `req-B` does not alter A's snapshot.
- `second=req-B`: the second task is submitted after the caller sets B, so the worker receives B even though the same thread processed A.
- `empty=<none>`: when the submitter has no MDC, the decorator **temporarily clears MDC on the worker** rather than leaving the trace from the prior task.
- `futureError=IllegalStateException`: the task fails and the Future reflects the error. The decorator runs `finally` to restore the worker's MDC, even when the executing callback does not let the exception escape because of a Future wrapper.

You cannot infer "durable jobs proven" from this example: all tasks still live in JVM memory. For jobs to survive restarts, you need a DB/queue/broker and dedicated recovery design.

## 10. Spring 6.1+'s `ContextPropagatingTaskDecorator`: When to Use It Instead of a Custom Wrapper?

Spring Framework 6.1+ includes `org.springframework.core.task.support.ContextPropagatingTaskDecorator`. It integrates the **Micrometer Context Propagation** mechanism to capture/reinstall registered contexts, especially helpful for logging/observation contexts.

Guiding example:

```java
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
```

This is an **illustrative snippet**; pool configuration and lifecycle are still needed. In Spring Boot production apps, the executor is usually registered as a bean; Micrometer/context-propagation dependencies and `ThreadLocalAccessor`/context accessors must be configured for the contexts you actually intend to propagate.

**Do not mistakenly believe** that adding a `ContextPropagatingTaskDecorator` automatically copies **every** custom `ThreadLocal` or every request object. Only contexts with a matching mechanism/accessor are captured and restored. You must test in practice with the trace/MDC of your current stack; depending on the backend and integration, extra dependencies or configuration may be needed.

A custom decorator like `MdcTaskDecorator` can make sense for a **specific, simple**, well-tested need. For rich observability stacks, prefer official integrations with context snapshots/accessors over duplicating each context type in scattered code.

Performance note: capturing/restoring context allocates objects/copies maps. Especially with millions of tiny tasks, measure overhead and decide whether full propagation or just a few minimal fields is needed.

## 11. Spring Security: Do Not Copy `SecurityContext` Like a Plain Map

Under common configuration, `SecurityContextHolder` relies on `ThreadLocal`. An `@Async` task does not naturally share the same authentication as the request thread, and losing context can break downstream authorization or auditing.

Spring Security provides dedicated wrappers:

- `DelegatingSecurityContextRunnable` and `DelegatingSecurityContextCallable`.
- `DelegatingSecurityContextExecutor`.
- `DelegatingSecurityContextTaskExecutor`.
- `DelegatingSecurityContextAsyncTaskExecutor`.

These classes manage attaching/cleaning up `SecurityContext` around tasks and integrate with Spring `TaskExecutor`. They are better than manually calling `SecurityContextHolder.setContext(...)` and forgetting to restore/clear.

**Security limits:**

1. Propagate only the authentication needed after authentication/authorization; **do not** "elevate privileges" for a worker simply because the caller holds a certain role.
2. `SecurityContext` and authentication can contain mutable objects/references. Never assume propagating context yields a **deep immutable snapshot**. If an immutable snapshot is needed, convert to a minimal claims DTO or use an appropriate framework mechanism.
3. A task running long after the request may hold stale privilege info. For sensitive tasks, define authorization checks at **execution time** along with expiration/revocation policies.
4. Do not put access tokens, session secrets, or sensitive personal data into MDC/logs merely for propagation convenience.
5. When calling external systems, pass identity/authorization per contract; copying `ThreadLocal` does not replace downstream authentication or authorization.

**Illustrative** example given an existing `AsyncTaskExecutor delegate` bean:

```java
import org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor;

var secured =
        new DelegatingSecurityContextAsyncTaskExecutor(delegate);
```

This snippet requires the Spring Security dependency and a `delegate` of the right type in context; it is not a standalone program. Clarify which wrapper owns snapshot/cleanup, and avoid combining multiple custom decorators that easily overwrite each other's context.

## 12. What **Not** to Propagate: Transactions and Request Resources

### Transactions Are Not a Map to Copy

Spring transactions are typically tied to threads and real resources (JDBC connections, transaction managers, entity managers). An open `@Transactional` on the request-handling thread **does not automatically extend** to a worker just because we copy trace IDs. Attempting to transfer `TransactionSynchronizationManager` or the same JDBC connection/EntityManager to another thread can break correctness, lifecycle, and thread safety.

**The right way:** pass the required data/IDs and let the worker establish **its own transaction boundary** when it needs DB operations. If the worker must run after the caller's transaction commits, design the enqueue timing properly, such as after-commit publication or transactional outbox; do not fake transactions by copying ThreadLocals.

### `RequestContextHolder` and Servlet Requests

`RequestAttributes` or `HttpServletRequest` is data tied to the request and container lifecycle. A background task may run **after the response ends**, when the request object is already invalid or released/reused. Do not carry the entire request scope into a thread pool assuming it remains usable forever.

Instead:

- Capture the required **primitive values or immutable DTOs** while the request is still valid.
- Authenticate/authorize upon receiving the request; redesign permission checks at worker execution time if needed.
- Do not hold sessions/resources/streams still tied to an HTTP response inside long-running jobs.
- Have TTLs and context cleanup mechanisms when bridging into a durable job system.

### `InheritableThreadLocal` Does Not Solve the Thread Pool Problem

`InheritableThreadLocal` lets a newly spawned child thread inherit values at thread creation time; it **does not** provide a fresh snapshot per task on an **already created and reused** worker. A thread pool reusing workers can retain values from when the worker was initialized, leading to stale/wrong context. Do not use it as a substitute for per-task capture/restore.

## 13. Multiple Thread Hops: Is the Decorator Applied at Every Stage?

A pipeline of `@Async` and `CompletableFuture` can traverse multiple executors:

```text
HTTP thread (MDC A)
      |
      | @Async("contextExecutor")
      v
Spring contextExecutor worker (MDC A)
      |
      | thenApplyAsync(...) WITHOUT passing an executor
      v
ForkJoinPool.commonPool worker (MDC ???)
```

A `TaskDecorator` attached to **a specific `ThreadPoolTaskExecutor`** only wraps tasks **submitted through that exact executor**. If a continuation uses `thenApplyAsync` without passing an executor, the JDK typically uses the common pool; the Spring executor's decorator **does not automatically run** on the common pool.

To intentionally preserve context at a specific boundary:

```java
CompletableFuture<Dto> dtoFuture =
        source.thenApplyAsync(this::mapToDto, contextExecutor);
```

This illustrative snippet requires `source`, `mapToDto`, and `contextExecutor` to exist. If `contextExecutor` is configured with `MdcTaskDecorator`, submitting the continuation through it captures the context **of the thread actually scheduling the callback** at submission time. However, do **not** assume the thread scheduling the callback is always the original HTTP thread. If the `source` dependency completes from a thread without MDC, the snapshot may be null. Therefore, when you need logical request context across **the entire graph**, consider framework-supported `ContextSnapshot`/propagation mechanisms and design each stage's creation point carefully.

Methods without the `Async` suffix such as `thenApply` or `whenComplete` may run on the thread completing `source` or the thread registering the callback; there is no guarantee which worker runs them. Do not rely on MDC as a mandatory source of business data if a stage can execute from different threads; explicit parameter passing is much safer.

### Prefer Passing Business Data via Parameters

```java
record WorkContext(String requestId, String tenantId) {}

CompletableFuture<Result> process(WorkContext context, Input input) {
    return service.computeAsync(context, input);
}
```

This is an **illustrative snippet** requiring `Result`, `Input`, and `service` to be defined. An immutable `record` with Strings is well-suited to explicitly carry logical context across multiple stages. ThreadLocal/MDC primarily serves logging/observability integrations and certain framework APIs; it does not replace explicitly passed business data.

## 14. Exceptions and `FutureTask`: Why `try-finally` Is Still Right Even If `catch` Misses the Error

With executor `submit(Callable<T>)`, the actual task `TaskDecorator` sees may be a `FutureTask`. When `Callable` throws an exception, `FutureTask.run()` typically **catches and stores** the exception so `Future.get()` throws `ExecutionException`. A wrapper like:

```java
return () -> {
    Map<String, String> previous = MDC.getCopyOfContextMap();
    try {
        restore(captured);
        callback.run();
    } catch (Exception ex) {
        logFailure(ex); // Not guaranteed to catch Callable's error.
    } finally {
        restore(previous);
    }
};
```

This is only an **illustrative** snippet; `captured`, `callback`, `logFailure`, and `restore` belong to the application. If the callback is a `FutureTask`, the `Callable`'s error may not escape `callback.run()`, so `catch` is never triggered. Nevertheless, `finally` still runs **when `callback.run()` returns normally**, so restoration **still works**.

With `CompletableFuture`, business errors are normally represented as exceptional completion. The caller needs:

```java
future.whenComplete((value, failure) -> {
    if (failure != null) {
        metrics.recordFailure(failure);
    }
});
```

This is an illustrative snippet with application-defined `future` and `metrics`. For `@Async void` methods, use `AsyncUncaughtExceptionHandler` or your application's observation mechanism. **Restoring context** and **detecting business errors** are two separate responsibilities; do not make cleanup logic depend on `catch`.

If an error occurs **before the delegate task is accepted** (executor rejects or is shut down), the wrapper never runs and thus never sets context on a worker; caller code must handle rejection (`TaskRejectedException`/`RejectedExecutionException`) per contract. Never promise a job was accepted when the executor rejected it.

## 15. Multiple Decorators, Ordering, and Ownership

In a real application, a task may need MDC, trace/observation, and SecurityContext propagated. A sound approach is usually:

1. **Identify which contexts are genuinely needed** for each task type; do not copy everything blindly.
2. **Prefer framework-provided wrappers/TaskDecorators** (Micrometer/Spring Security) for context types that already have contracts.
3. If using multiple decorators, use `CompositeTaskDecorator` or build one combined decorator with explicit ordering; verify capture/restore behavior under nested wrappers.
4. Let only one layer own resetting each context type, avoiding two decorators overwriting the same map without knowing ordering.
5. With a custom JDK `Executor`, apply an adapter/wrapper at the **executor boundary** instead of scattering `set/clear` code across every business method.
6. Observe `TaskRejectedException`, timeouts, and cancellation at the submission boundary; a decorator is not a durable queue or retry mechanism.

Specifically: if you use `CallerRunsPolicy` or a direct executor in tests, the wrapper can run **right on the submitter thread**. Thus `restore previous` in `finally` must work accurately in both separate-worker and same-thread models.

## 16. How to Test Properly Without `sleep`

To test context propagation, **do not** rely on workers accidentally finishing in a certain order. Use `CountDownLatch` and `Future.get(timeout)` to control execution deterministically:

| Test Case | Setup | Passing Condition |
| --- | --- | --- |
| Timely capture | Hold worker with latch, submit snapshot A, switch caller to B, release worker | Task still sees A |
| Thread reuse | 1-worker pool; task A completes then task B | B sees only snapshot B |
| Null snapshot | Caller has no context, worker already has baseline | Task sees null, not baseline |
| Restoration | Capture worker baseline before task, read again via raw executor after task | Baseline is preserved |
| Failing task | Task throws exception via FutureTask | Caller sees error, worker is still restored |
| Nested / inline | Use `Runnable::run`, callback modifies ThreadLocal | Caller retains pre-callback value |
| CallerRuns | Pool full, policy runs callback on caller | Caller context is restored after callback |
| Multiple MDC keys | A has `{traceId,tenant}`, B lacks `tenant` | B does not carry A's `tenant` |
| Mutable structure | Sending thread mutates map after submit | Snapshot is not unexpectedly altered |
| Async graph | `@Async` then `thenApplyAsync` via another executor | Every needed boundary has propagation or explicit params |

With JUnit 5, you can write a deterministic test for the wrapper:

```java
@Test
void inlineExecutionRestoresCaller() {
    ThreadLocal<String> current = new ThreadLocal<>();
    current.set("caller");

    Executor wrapped = task -> {
        String snapshot = current.get();
        Runnable delegated = () -> {
            String previous = current.get();
            try {
                current.set(snapshot);
                task.run();
            } finally {
                if (previous == null) {
                    current.remove();
                } else {
                    current.set(previous);
                }
            }
        };
        delegated.run(); // Direct execution.
    };

    wrapped.execute(() -> current.set("inner"));
    assertEquals("caller", current.get());
    current.remove();
}
```

This is an **illustrative test snippet**, requiring imports for `org.junit.jupiter.api.Test`, `org.junit.jupiter.api.Assertions.assertEquals`, and `java.util.concurrent.Executor`, plus the JUnit 5 dependency. For a real shared application `ThreadLocal`, write an `afterEach` cleanup fixture/extension so tests do not leak context across other tests.

When testing Spring `@Async`, **you must call through the Spring proxy from another bean/test context**. Calling `this.asyncMethod()` from the same bean bypasses async advice in default proxy mode, making the test "pass" on the same thread without actually verifying propagation.

## 17. Anti-Patterns to Recognize

| Anti-pattern | What Is Wrong? | How to Fix |
| --- | --- | --- |
| Calling `ThreadLocal.get()` **inside `run()`** | Reads the worker's value, not the sending thread's | Capture before `executor.execute`/inside `decorate` |
| `ThreadLocal.set(snapshot); task.run();` without `finally` | A failing task leaves stale data on the worker | `try-finally` always restores previous |
| Always calling `remove()` at task end | Breaks context of nested wrappers / caller-runs | Save `previous` first, restore exact prior value |
| Only `put`ting new keys without clearing old MDC keys | Keys from prior requests persist | Restore the **entire map** or clear when snapshot is empty |
| Using a mutable `HashMap` reference as snapshot | Sending thread mutates map, worker sees changed data | Defensive copy/immutable DTO |
| Automatically propagating every ThreadLocal | Carries tokens/sessions/transactions that should not move | Allowlist contexts, check security/lifecycle |
| Using `InheritableThreadLocal` for pooled workers | Snapshots at **thread creation**, not per task | Per-task decorator or explicit parameters |
| Assuming `@Async` propagates MDC automatically | Worker is a different thread; MDC may be null/wrong | Attach TaskDecorator or propagation integration |
| Using `supplyAsync()` without an executor after decorated `@Async` | Callback enters common pool, losing propagated context | Explicitly specify executor or context snapshot for the stage |
| Calling `MDC.clear()` in business method without restoring | Breaks caller/nested stage context | Capture/restore wrapper in `finally` |
| Copying `TransactionSynchronizationManager` to worker | Wrong transaction and resource boundary | Worker opens its own transaction; pass required data |
| Capturing `HttpServletRequest` for a long-running job | Resource outlives request lifecycle | Snapshot immutable DTO/ID |
| Relying on `TaskDecorator`'s catch to catch all Future errors | `FutureTask` keeps exception inside | Observe Future and use error handlers |
| Using an unbounded thread pool and copying large contexts | Wastes memory, causes backlog and latency | Bounded queue, minimal snapshot, metrics |
| Passing the same mutable SecurityContext to multiple tasks | Races/inconsistent permissions | Spring Security wrapper, minimal identity snapshot |
| Forgetting cleanup in integration tests | Next test inherits MDC/request ID | Teardown/fixture with `finally` or `afterEach` |

## 18. Production and Operations Checklist

Before deploying a propagation mechanism:

- **Scope:** which contexts are permitted to propagate? `traceId`, `requestId`, locale, tenant, authentication? Which must go via explicit parameters?
- **Timing:** is the snapshot created on the **submit thread**, not the worker?
- **Copying:** is the snapshot isolated from mutable data after submission?
- **Installation:** are old keys on the worker cleared when the snapshot is empty?
- **Restoration:** is `previous` saved **on the executing thread**, and does `finally` run for success/error/cancellation/inline?
- **Nested execution:** does direct execution or `CallerRunsPolicy` preserve outer code's context?
- **All boundaries:** do `@Async`, `Executor.submit`, `CompletableFuture.supplyAsync/thenApplyAsync`, scheduled tasks, and event listeners pass through the decorator in the right places?
- **Security:** avoid copying tokens, request objects, transactions, and unnecessary personal data; re-authenticate when needed.
- **Resources:** is the snapshot small with a sensible TTL? Does the executor have a bounded queue? What is the memory risk under prolonged task backlogs?
- **Errors:** are `Future` completions/errors observed separately rather than relying on the decorator's `catch`; is rejection handled at submit?
- **Observability:** log trace IDs at submit and on worker, rate of tasks missing expected trace, cross-tenant context mismatches, queue wait, executor active/queue/rejection metrics.
- **Testing:** thread reuse, submitter changing context before worker runs, null snapshot, exceptions, nested calls, async graphs, shutdown, and overload.

An application with standard tracing should prefer built-in propagation mechanisms, yet you must still understand the capture/install/restore algorithm. When encountering a bug where "user A's trace appears in user B's task", the root cause is usually **failing to clear on empty snapshot, missing restore in finally, or wrapping the wrong executor boundary**.

## 19. Self-Check Questions

**1.** Why must `MDC.getCopyOfContextMap()` be called in `decorate()` rather than inside `run()`?  
**Answer:** `decorate()` happens when submitting the task from the sending thread. `run()` executes on the worker, potentially seconds later and with a different MDC. Capturing inside `run()` loses the link to the original request.

**2.** Why must you save the worker's `previous` state before installing the snapshot?  
**Answer:** So that after the task, the executing thread returns to the exact context it had previously, including nested wrappers or executors running on the caller; merely clearing can break outer code's context.

**3.** The caller has no trace, while the worker still has `traceId=A` from an earlier task. What should the worker see during the new task?  
**Answer:** No trace (`null`/`<none>`); an empty snapshot must **temporarily clear** the old MDC. At the end of the callback, `previous` is restored per the wrapper contract; in a healthy app, a worker should not hold stray trace data outside tasks.

**4.** A task throws an exception on the worker. Does `finally` run?  
**Answer:** Yes, when control exits `try` normally via exception, provided the JVM is not abnormally terminated. Therefore restoration belongs in `finally`, not only on the success branch.

**5.** `FutureTask` stores the `Callable`'s exception. Does `catch` inside the decorator always catch that error?  
**Answer:** No. `FutureTask.run()` may not let the error escape outward; the caller must observe `Future.get()`. `finally` still executes around `run()`.

**6.** A `ThreadLocal<Map>` points to a `HashMap`; is keeping that reference in the snapshot enough?  
**Answer:** No, if the map is mutated after submission. A defensive copy is needed (and consider deep copy/immutable values).

**7.** An `@Async` method calls `CompletableFuture.supplyAsync()` without passing an executor. Does the Spring pool's decorator automatically wrap this supplier?  
**Answer:** No. The supplier may run on the JDK common pool, outside the Spring bean's decorator. You must configure each boundary or pass context via an appropriate mechanism.

**8.** Should you copy `@Transactional` context from the HTTP thread to the worker?  
**Answer:** No. Transactions and resources have thread-bound lifecycles; the worker should have its own transaction and receive explicit data/IDs.

**9.** `CallerRunsPolicy` causes a task to run directly on the sending thread. Why is restoration still necessary?  
**Answer:** The task can alter the `ThreadLocal` of **the HTTP thread itself**; `finally` must return the original context after the callback.

**10.** Does `ContextPropagatingTaskDecorator` automatically propagate every application-created `ThreadLocal`?  
**Answer:** No. A matching mechanism/accessor is needed for the context you want to propagate; test against your actual stack rather than assuming one decorator understands every value.

## 20. Key Takeaway and Official Documentation

**Fundamental formula of context propagation on an executor:**

```text
SUBMITTER: snapshot = captureCurrentContext()  // capture before enqueuing
WORKER:    previous = captureCurrentContext()  // save current state
           try {
               install(snapshot)               // even for empty snapshot
               runOriginalTask()
           } finally {
               restore(previous)               // no leaks, no breaking outer context
           }
```

A proper wrapper must withstand **pool reuse, failing tasks, null snapshots, inline execution, nested contexts**, and multiple `CompletableFuture` boundaries. When wrapping specialized contexts such as SecurityContext/observability, use the official Spring/Spring Security/Micrometer integrations and verify actual behavior with tests.

**References:**

- [Java SE 17 — `ThreadLocal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): thread-scoped data, `get`, `set`, `remove`.
- [Java SE 17 — `Executor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html): task submission contract, inline execution possibility.
- [Spring Framework — `TaskDecorator` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/task/TaskDecorator.html): callback wrapper and exception-catching limits with Future.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): configuring `ThreadPoolTaskExecutor.setTaskDecorator` and `@Async`.
- [Spring Framework — `ContextPropagatingTaskDecorator` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html): Micrometer context capture/restore.
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html): combining task execution and context propagation.
- [Spring Security — Concurrency Support](https://docs.spring.io/spring-security/reference/6.5/features/integrations/concurrency.html): wrappers protecting `SecurityContext`.
- [SLF4J — MDC API](https://www.slf4j.org/apidocs/org/slf4j/MDC.html): `getCopyOfContextMap`, `setContextMap`, `clear`.
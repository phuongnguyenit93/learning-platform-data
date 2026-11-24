# Risk of Previous Task Context Data Being Reused

## 1. The Problem: A Request Mistakenly Reads Context from a Previous Request

In Spring Framework, `ThreadPoolTaskExecutor` typically **reuses worker threads**. Task A runs on worker W and binds `tenantId=tenant-A` into a `ThreadLocal` or SLF4J `MDC`. After A finishes, W does not disappear: the pool reuses W to run task B. If A does not clean up its context, B can end up reading `tenant-A` even though B belongs to `tenant-B` or has no tenant at all. This is a **stale execution context** bug, also known as *cross-task context leakage*.

The consequences can be severe:

- B's logs get tagged with A's `requestId`/`traceId`, corrupting incident investigation and observability.
- Services filtering data by `tenantId` or `userId` taken from a stale thread-local risk cross-tenant data exposure or improper authorization.
- `SecurityContextHolder` on the worker retains another task's `Authentication`; authorization logic relies on the wrong current user.
- Locale, timezone, feature flags, request metadata, and audit actor data get reused without validation.
- `ThreadLocal` can hold references to large objects or request-scoped objects until the worker dies; memory retention grows with the number of long-lived workers.
- The bug only surfaces when **hitting the exact worker used previously**, so single-request tests or tests that spawn new threads easily miss it.

**Rule:** a new task does not mean a new thread. You must define the **capture → install/clear → run → restore/remove** boundary for every task, on the actual worker thread. Never use `ThreadLocal` or MDC as the sole source of truth for tenant or security verification.

## 2. Mechanism: ThreadLocal Follows Thread Lifecycle, Not Job Lifecycle

`ThreadLocal<T>` gives each thread its own separate value when code calls `set()/get()`. That value belongs to the **current thread**, not to an HTTP request or unit of work. `ThreadLocal.remove()` clears the value for the calling thread itself; it does not clean up other worker threads.

~~~text
Caller request A        ThreadPoolTaskExecutor       Worker pool-1-thread-1
       |                          |                            |
       +---- task A ------------->|------ run A -------------->|
       |                          |    tenant.set("tenant-A")  |
       |                          |    process(A)              |
       |                          |    // forgot remove()      |
       |                          |<----- task A done ---------|
       |                          |       worker keeps tenant-A|
Caller request B                  |                            |
       +---- task B ------------->|------ run B -------------->|
                                  |    tenant.get() = tenant-A |
                                  |    // wrong context A      |
                                  |<----- task B done ---------|
~~~

If two tasks run **on two different threads**, they do not automatically read the same `ThreadLocal` slot. The bug here occurs because **worker W is reused**. This is different from a race condition on a singleton field shared across multiple workers.

Two situations must also be distinguished:

| Situation | Worker Sees | Meaning |
| --- | --- | --- |
| Caller has `tenant-A`, worker has not received context | `null` | Missing propagation, not stale |
| Caller B has no tenant, worker still holds A's value | `tenant-A` | Stale value, isolation failure |
| Caller has `tenant-B`, wrapper captures B and installs it before running | `tenant-B` | Correct propagation when the value is trustworthy |
| Caller has no context, wrapper **clears** worker before running | `null` | B does not pick up old context |
| After task, wrapper cleans/restores in `finally` | Returns to prior scope's context | Prevents this task's context from leaking to the next task |

A decorator that calls `MDC.setContextMap(snapshot)` **only when snapshot is non-null** is buggy: if a subsequent task **has no MDC**, the wrapper sets nothing, so the worker can retain MDC from the previous task. The null-snapshot branch needs an explicit action such as `MDC.clear()` at the appropriate boundary.

## 3. Which Contexts in Spring Carry Risk?

| Type | Common Mechanism | Risk When Misused |
| --- | --- | --- |
| Application `ThreadLocal` | `ThreadLocal<String>` storing tenant, job ID, batch metadata | Wrong tenant/job, memory retention |
| Logging MDC | `org.slf4j.MDC` storing `requestId`, `traceId` map | Logs tagged with wrong request, info leak, broken tracing |
| Spring Security | `SecurityContextHolder`, usually `MODE_THREADLOCAL` | Reusing `Authentication`/principal from previous task |
| Request context | `RequestContextHolder`, thread-bound request attributes | Using an expired request or wrong request |
| Transaction | `TransactionSynchronizationManager` and resource association | Invalid resource/connection/transaction-bound state |
| Micrometer observation | Tracing/metrics scope/context | Wrong correlation or unclosed scope |
| Custom library context | Locale, timezone, routing, audit | Business behavior diverges from actual payload |

**Not everything propagates automatically.** When crossing from a servlet request thread to a worker thread, `ThreadLocal` usually does not follow along. Conversely, once a worker already **has** an old value, it does not clear itself when the previous task finishes.

`ThreadLocal.remove()` called on the HTTP caller thread does not clean up the worker's variable. `MDC.clear()` likewise only clears the MDC of the **calling thread**; calling it solely in the controller after submitting is not enough to clear the worker's MDC.

## 4. Standalone Java 17 Example: Deterministically Reproducing the Leak

The example uses `Executors.newSingleThreadExecutor` so all tasks run on **the exact same worker**. `Future.get(timeout)` waits for the prior task to finish before running the next step, without relying on `Thread.sleep` or random CPU scheduling.

### 4.1. ThreadLocalLeakDemo.java

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class ThreadLocalLeakDemo {
    private static final ThreadLocal<String> TENANT = new ThreadLocal<>();

    private static <T> T run(
            ExecutorService pool, Callable<T> job) throws Exception {
        return pool.submit(job).get(3, TimeUnit.SECONDS);
    }

    // Capture on caller, install and restore on worker.
    private static <T> Callable<T> withTenantContext(Callable<T> job) {
        String captured = TENANT.get();
        return () -> {
            String previous = TENANT.get();
            try {
                if (captured == null) {
                    TENANT.remove();
                } else {
                    TENANT.set(captured);
                }
                return job.call();
            } finally {
                if (previous == null) {
                    TENANT.remove();
                } else {
                    TENANT.set(previous);
                }
            }
        };
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor(
                runnable -> new Thread(runnable, "context-worker"));
        try {
            System.out.println("FIRST=" + run(pool, () -> {
                TENANT.set("tenant-A");
                return TENANT.get(); // Anti-pattern: forgot cleanup.
            }));

            // Old worker is reused: B without a tenant still sees A.
            System.out.println("LEAKED_IN_SECOND="
                    + run(pool, TENANT::get));

            System.out.println("RESET=" + run(pool, () -> {
                TENANT.remove();
                return TENANT.get();
            }));

            // Correct way if the task owns its own context.
            System.out.println("SAFE_REQUEST=" + run(pool, () -> {
                TENANT.set("tenant-B");
                try {
                    return TENANT.get();
                } finally {
                    TENANT.remove();
                }
            }));
            System.out.println("AFTER_SAFE=" + run(pool, TENANT::get));

            // Caller has tenant-C; worker does not automatically receive tenant-C.
            TENANT.set("tenant-C");
            try {
                System.out.println("NO_AUTO_PROPAGATION="
                        + run(pool, TENANT::get));

                System.out.println("PROPAGATED="
                        + run(pool, withTenantContext(TENANT::get)));

                System.out.println("AFTER_PROPAGATED="
                        + run(pool, TENANT::get));
            } finally {
                TENANT.remove(); // Clean caller.
            }

            // A business error must not skip cleanup either.
            Future<?> failed = pool.submit((Runnable) () -> {
                TENANT.set("tenant-D");
                try {
                    throw new IllegalStateException("boom");
                } finally {
                    TENANT.remove();
                }
            });
            try {
                failed.get(3, TimeUnit.SECONDS);
            } catch (ExecutionException ex) {
                System.out.println("ERROR_CAUSE="
                        + ex.getCause().getClass().getSimpleName());
            }
            System.out.println("AFTER_ERROR="
                    + run(pool, TENANT::get));
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(3, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Save the file with the exact name, using JDK 17+:

~~~bash
javac --release 17 ThreadLocalLeakDemo.java
java ThreadLocalLeakDemo
~~~

Program stdout:

~~~text
FIRST=tenant-A
LEAKED_IN_SECOND=tenant-A
RESET=null
SAFE_REQUEST=tenant-B
AFTER_SAFE=null
NO_AUTO_PROPAGATION=null
PROPAGATED=tenant-C
AFTER_PROPAGATED=null
ERROR_CAUSE=IllegalStateException
AFTER_ERROR=null
~~~

Why the output is deterministic: `newSingleThreadExecutor` has only one worker; the `run` calls wait for the prior task to complete. When A forgets `remove()`, B immediately reads tenant-A on the same worker. After reset, the safe task B is wrapped in `try/finally` so the next call reads `null`. Context on the caller does not propagate automatically into the worker; the `withTenantContext` wrapper snapshots on the caller, installs on the worker, and then restores. When a task throws an error, `finally` still runs, so `AFTER_ERROR=null`.

**Important detail to remember:** `withTenantContext` restores the worker's `previous` value, which is useful for nested scopes. However, if the worker was already dirtied by some other code, restoring may return it to **that exact wrong value**. Therefore, you must ensure the boundary or component owning the worker cleans up at the source, rather than treating "restore previous" as a cure for every pre-existing leak.

## 5. How to Handle It: Always Clean Up and Manage Ownership

### 5.1. If a Task Creates Its Own ThreadLocal, Clean Up in finally

~~~java
// Illustrative snippet inside a worker; Job and perform are defined by the project.
void process(String tenant, Job job) {
    try {
        CURRENT_TENANT.set(tenant);
        perform(job);
    } finally {
        CURRENT_TENANT.remove();
    }
}
~~~

`CURRENT_TENANT` is an application-created `ThreadLocal<String>`; `remove()` runs on the worker itself. Whether `perform` throws an exception or returns early, `finally` still runs. Do not clean up only inside `catch`: on the success path, `catch` never runs and the context remains.

### 5.2. Nested Scopes Must Restore the Previous State

~~~java
// Snippet: the thread may already have a valid parent scope.
String previous = CURRENT_TENANT.get();
try {
    if (newTenant == null) {
        CURRENT_TENANT.remove();
    } else {
        CURRENT_TENANT.set(newTenant);
    }
    perform();
} finally {
    if (previous == null) {
        CURRENT_TENANT.remove();
    } else {
        CURRENT_TENANT.set(previous);
    }
}
~~~

The pattern above only illustrates managing an application-owned `ThreadLocal`. If `T` is a mutable object (such as `Map`, `SecurityContext`, `HttpServletRequest`), snapshotting a **reference** does not make it immutable data. To let a task work with a user/tenant, prefer passing verified scalar IDs or immutable DTOs instead of sharing the entire request object.

### 5.3. Define Who Is Responsible for Cleanup

There are at least three boundaries:

1. **Servlet/security/tracing filter**: creates and cleans up the HTTP request's context. Do not arbitrarily call `MDC.clear()` in a service and wipe out data belonging to a filter or tracing framework.
2. **Task executor/decorator**: captures at submission, installs or clears on the worker, runs the task, and restores or removes in `finally`. Guards between **tasks**.
3. **Business code**: if it creates its own `ThreadLocal` inside a worker, it must clean up that exact scope, including when the task throws an error.

If each layer blindly clears another layer's context, nested scopes can break; if no layer takes responsibility, stale context persists across tasks. Explicitly specify ownership in your design.

## 6. Spring TaskDecorator: Capturing and Restoring MDC for Each Submission

Spring `ThreadPoolTaskExecutor` has `setTaskDecorator(TaskDecorator)` to wrap the execution callback. This is the right place to carry MDC from caller to worker **and prevent MDC from leaking into the next task**. We illustrate with SLF4J `MDC.getCopyOfContextMap()` and a `String → String` snapshot map.

### 6.1. Java 17 + Spring Boot 3.3.5 Maven Project

Structure:

~~~text
spring-context-isolation/
├── pom.xml
└── src/main/java/com/example/context/
    ├── ContextIsolationApplication.java
    ├── MdcSnapshotTaskDecorator.java
    └── ContextProbe.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>spring-context-isolation</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
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
~~~

`spring-boot-starter` includes the standard logging backend supporting SLF4J MDC. The example is a command-line application requiring no DB or web server.

### 6.2. MdcSnapshotTaskDecorator.java

~~~java
package com.example.context;

import java.util.Map;
import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

public final class MdcSnapshotTaskDecorator implements TaskDecorator {
    @Override
    public Runnable decorate(Runnable delegate) {
        // Capture at SUBMIT time on caller, not on worker.
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            // Snapshot existing scope on worker for restoration.
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                if (captured == null) {
                    // Must clear even when context is absent, to avoid picking up stale MDC.
                    MDC.clear();
                } else {
                    MDC.setContextMap(captured);
                }

                delegate.run();
            } finally {
                if (previous == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previous);
                }
            }
        };
    }
}
~~~

Three things to verify in any similar decorator:

- `captured` is read inside `decorate()` when the task is submitted, before running on the worker. Reading `MDC` inside `Runnable.run()` without capturing earlier reads the **worker's MDC**, not the caller's MDC.
- When `captured == null`, the wrapper **clears MDC on the worker before the delegate runs**. If you only set when the snapshot is non-null, a task without context may see the previous task's values.
- Cleanup is placed in `finally`. The `previous` snapshot helps nested scopes restore prior context; however, if that context is leftover residue forgotten by another component, that component itself must also be fixed.

`TaskDecorator` Javadoc notes that the received callback may be an executor wrapper, **not the original Runnable submitted by the user**. Thus, a decorator is suitable for managing context but is not the sole place to catch business errors of a `FutureTask`: exceptions from `submit` can be held inside the Future, so a result-observing handler is still required.

### 6.3. ContextProbe.java

~~~java
package com.example.context;

import java.util.concurrent.CompletableFuture;
import org.slf4j.MDC;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ContextProbe {
    public record Observed(
            String request, String tenant, String worker) { }

    @Async("contextExecutor")
    public CompletableFuture<Observed> read(String request) {
        return CompletableFuture.completedFuture(new Observed(
                request,
                MDC.get("tenant"),
                Thread.currentThread().getName()));
    }
}
~~~

`ContextProbe` is a Spring-managed bean separate from the caller. `@EnableAsync` must be enabled; `worker.read()` must be called through the proxy, not via an internal `this.read()`. The method returns a valid `CompletableFuture` and records `MDC.get("tenant")` right inside the worker.

### 6.4. ContextIsolationApplication.java

~~~java
package com.example.context;

import java.util.concurrent.TimeUnit;
import org.slf4j.MDC;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@SpringBootApplication
@EnableAsync
public class ContextIsolationApplication {
    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                SpringApplication.run(ContextIsolationApplication.class, args)) {
            // Runner finishes, context closes per lifecycle.
        }
    }

    @Bean("contextExecutor")
    ThreadPoolTaskExecutor contextExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(1);
        pool.setMaxPoolSize(1);
        pool.setQueueCapacity(8);
        pool.setThreadNamePrefix("ctx-");
        pool.setTaskDecorator(new MdcSnapshotTaskDecorator());
        pool.setWaitForTasksToCompleteOnShutdown(true);
        return pool;
    }

    @Bean
    ApplicationRunner showIsolation(ContextProbe worker) {
        return args -> {
            ContextProbe.Observed first;
            ContextProbe.Observed second;
            ContextProbe.Observed missing;

            try {
                MDC.put("tenant", "tenant-A");
                first = worker.read("A").get(3, TimeUnit.SECONDS);

                MDC.put("tenant", "tenant-B");
                second = worker.read("B").get(3, TimeUnit.SECONDS);

                MDC.remove("tenant");
                missing = worker.read("C").get(3, TimeUnit.SECONDS);
            } finally {
                MDC.remove("tenant"); // Clean caller.
            }

            System.out.println("A=" + first.tenant());
            System.out.println("B=" + second.tenant());
            System.out.println("C=" + missing.tenant());
            System.out.println("REUSED_SAME_THREAD="
                    + first.worker().equals(second.worker()));
            System.out.println("WORKER_PREFIX="
                    + first.worker().startsWith("ctx-"));
            System.out.println("CALLER_CLEARED="
                    + (MDC.get("tenant") == null));
        };
    }
}
~~~

The pool is managed by Spring and has one `ctx-*` worker. `ApplicationRunner` intentionally waits on each `Future.get(3, SECONDS)` to produce deterministic verification results; this is **not** a pattern for an HTTP controller to block synchronously and call that background processing. In real systems, return a Future or job ID per contract and configure timeouts/backpressure.

### 6.5. Running and Stdout

In the directory containing `pom.xml`, with JDK 17+ and Maven:

~~~bash
mvn spring-boot:run
~~~

Ignoring Spring/Maven startup logs, the six lines printed by the application:

~~~text
A=tenant-A
B=tenant-B
C=null
REUSED_SAME_THREAD=true
WORKER_PREFIX=true
CALLER_CLEARED=true
~~~

A and B use the same worker because the pool has only one thread. Yet the value on the worker changes per MDC snapshot at **each submission**. Task C has no tenant MDC on the caller, so the decorator clears MDC before running and returns `null` instead of keeping `tenant-B`. Tasks run sequentially in the demo for deterministic output; production may have many concurrent workers.

## 7. Why Is a Decorator Without finally Still Wrong?

~~~java
// Anti-pattern: only sets context if non-null, never cleans up.
Map<String, String> captured = MDC.getCopyOfContextMap();
return () -> {
    if (captured != null) {
        MDC.setContextMap(captured);
    }
    delegate.run();
};
~~~

If task A carries `tenant-A`, the worker retains that map after A. Task B **has no** context on the caller, the `if` branch is skipped, so B sees tenant-A. If a task throws an exception, no cleanup runs at all. In nested context scenarios, calling `MDC.clear()` unconditionally at the end can also destroy context owned by a parent scope.

The proper pattern in section 6 **sets the map or clears on entry**, then **restores previous or clears on exit**, always inside `finally`. However, it must not be interpreted as "every context from every library is safe": the decorator only manages the **MDC map**; it does not automatically propagate Spring Security, transactions, request attributes, or arbitrary application `ThreadLocal`s.

You can use `MDC.remove("key")` instead of `MDC.clear()` when a layer owns only a single key; for a decorator wrapping a full MDC snapshot, restoring the map preserves valid outer scopes. Ownership must be designed on both ends.

## 8. ContextPropagatingTaskDecorator from Spring Framework 6.1

Spring Framework 6.1+ includes `org.springframework.core.task.support.ContextPropagatingTaskDecorator` for contexts supported via **Micrometer Context Propagation**. The library can snapshot and restore observation/logging context when the worker runs.

Configuration snippet inside a `@Configuration`, **not a standalone project**:

~~~java
@Bean("observedExecutor")
ThreadPoolTaskExecutor observedExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(32);
    executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
    return executor;
}
~~~

Requires importing `ThreadPoolTaskExecutor`, `ContextPropagatingTaskDecorator`, and `@Bean`; the application needs a compatible `io.micrometer:context-propagation` dependency along with registered `ThreadLocalAccessor`s for the context types to propagate.

**Do not infer that every ThreadLocal is automatically propagated** just from using that class. You must verify the right accessors/registry and test in practice. The library also incurs capture/restore overhead, which is not worth applying blindly to millions of tiny tasks. For simple values, explicit immutable payloads (verified `tenantId`, `jobId`, `correlationId`) are cheaper and more transparent.

You should also avoid installing multiple decorators simultaneously that independently manage the same MDC without understanding install/restore ordering; they can overwrite or restore the wrong scope.

## 9. Spring Security: Avoid Using Authentication from a Previous Task

`SecurityContextHolder` typically uses `ThreadLocal` by default. During a servlet request, the Spring Security filter chain manages setting and clearing the context at the request boundary. However, on a custom thread pool, `@Async` code is not automatically guaranteed to receive the caller's SecurityContext, nor is it safe from reading a stale context if a prior task dirtied the worker.

Anti-pattern (snippet, do not use for authorization decisions):

~~~java
Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();
// A dirty worker may return the previous task's auth.
~~~

Spring Security provides `DelegatingSecurityContextRunnable` and wrappers like `DelegatingSecurityContextAsyncTaskExecutor` to set the context per task and clean up by scope. The snippet below only illustrates configuration:

~~~java
@Bean("securedExecutor")
AsyncTaskExecutor securedExecutor(
        @Qualifier("rawAsyncExecutor") AsyncTaskExecutor raw) {
    return new DelegatingSecurityContextAsyncTaskExecutor(raw);
}
~~~

Requires importing `org.springframework.core.task.AsyncTaskExecutor`, `org.springframework.beans.factory.annotation.Qualifier`, `org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor`, `@Bean`; the `rawAsyncExecutor` bean and Spring Security dependencies must exist. The constructor without a fixed `SecurityContext` uses the context captured per submission; the overload taking a fixed context uses one designated principal for every task, suitable only for intentional service accounts.

Notes:

- `SecurityContext` can contain `Authentication` and mutable objects; capturing a reference does not make it immutable. Do not share and arbitrarily mutate that object across threads.
- A task without user privileges **must not** inherit the previous task's principal; permission checks must be re-verified at the service/DB layer.
- If only a verified `userId` or `tenantId` is needed for background work, passing an immutable DTO is usually safer than passing an entire `HttpServletRequest`/session.
- Security context propagation does not equate to business authorization: the tenant in the payload must still match actual permissions.
- `SecurityContextHolder.clearContext()` clears the calling thread's context; do not assume calling it on the caller cleans the worker.

**Do not use `MODE_INHERITABLETHREADLOCAL` as a fix for thread pools.** `InheritableThreadLocal` receives the parent's value **at thread creation time**, not at each task submission. A long-lived worker can "inherit" data from request A when spawned, then continue serving requests B/C; that is the exact definition of a stale value. Moreover, mutable values can end up sharing references.

## 10. Transaction and RequestContext: Do Not Try to Propagate Manually

### 10.1. @Transactional and Thread-Bound Resources

Spring manages transaction/resource associations per thread (for example, via `TransactionSynchronizationManager`). When a task moves to another worker, the caller's transaction **does not automatically follow**. Do not copy `EntityManager`, `ConnectionHolder`, or JDBC connections from the HTTP thread into the worker: those resources have their own lifecycles and thread-safety constraints.

If a worker needs a transaction, open a `@Transactional` boundary in a service invoked through a Spring proxy **on the worker thread**. When a job is dispatched before commit and needs committed data, use an after-commit hook/outbox or another suitable ordering design. If a custom library manually calls `bindResource` on a worker, it must precisely call `unbindResource`; standard code should let Spring's transaction interceptor manage the lifecycle.

### 10.2. RequestContextHolder

`RequestContextHolder` binds request attributes to the servlet request thread. A worker outliving the request must not retain `ServletRequestAttributes` or `HttpServletRequest` and use them after the request has ended. Needed values should be extracted **before submission** into an explicit payload.

Java 17 snippet:

~~~java
record JobEnvelope(
        String jobId,
        String tenantId,
        String initiatedBy,
        String correlationId) { }
~~~

The IDs in `JobEnvelope` must come from verified sources and exclude unnecessary sensitive data. The record is immutable at the `String` reference level and can be passed across executors or persisted in a job store; an in-JVM ThreadLocal cannot replace durable job state across multi-pod deployments/restarts.

## 11. Frequently Overlooked Exit Paths

| Exit Path | What to Do |
| --- | --- |
| Success | `finally` cleanup, retain or propagate result per contract |
| Exception | `finally` still runs; Future/handler receives the business error |
| Early return | Cleanup must be in `finally`, not just the success branch |
| Caller timeout | `Future.get(timeout)` only stops **waiting**; the worker may keep running and holding context until finished |
| Cancel unstarted task | Wrapper has not entered the worker so context was not set; still clean up job state/handle on caller |
| Cancel running task | Interrupt is only a request, not guaranteed immediate stop; rely on `finally` when the worker exits |
| Submission rejection | Task did not run, may have no Future returned; catch `TaskRejectedException`/`RejectedExecutionException` |
| Shutdown | Queue may still have unrun tasks; handle Future/job ledger separately, thread-local cleanup is not enough |
| Nested async | Each executor needs its own propagation boundary and valid scope |
| Default `CompletableFuture.supplyAsync` | May use `ForkJoinPool.commonPool()`, bypassing decorators on other Spring pools |

A short timeout on the HTTP caller does not automatically clear MDC sitting on the worker. When a task hangs on I/O, both context and resources can remain held until the task actually exits, so timeouts on network/DB calls themselves and real cancellation policies are needed.

## 12. Testing Reuse Bugs and Fail-Closed Principles

### 12.1. Test With at Least Two Tasks on Exactly One Worker

A test submitting only one task does not prove isolation. You should:

1. Create an executor with core=max=1 or `newSingleThreadExecutor`.
2. Submit A with `tenant-A` and let it finish (in the buggy version, omit cleanup).
3. Wait for A via a Future with timeout; submit B **without setting a tenant**.
4. Before the fix, B will read tenant-A. After the fix, B must receive null or be explicitly rejected for missing context.
5. Submit C with `tenant-C` to verify propagation/cleanup. Trigger an exception inside C; submit D to ensure D no longer has C's context.
6. Add nested scope, cancellation, rejection, and shutdown cases to cover all exit paths.

Use `CountDownLatch`/barriers when testing multiple parallel workers instead of relying on `Thread.sleep` and scheduling coincidence. If testing with `SyncTaskExecutor` running inline, many thread-local bugs will not surface because the caller thread runs everything directly; at least one test must use an executor that actually reuses threads.

### 12.2. End-to-End Tests Matching Security Requirements

- Simulate two different principals/tenants and a tenant-less request on the same worker; verify DB queries/authz do not use the old principal/tenant.
- Test logs with different `requestId`s: job B's log lines must carry B or null per contract, never A.
- If a bean has `@Async`, call it from **another bean via proxy**; `this.asyncMethod()` can bypass the proxy, causing the test to run inline instead of on the pool.
- Audit all real executors used in the application, including `@Async`, `@Scheduled`, async event listeners, and CompletableFuture with specified executors.
- With multiple workers, run high-load tests to catch reuse under races/rejection; with one worker, deterministically test leak paths.

### 12.3. Is Checking Only tenant != null Enough?

No. If worker B holds a **stale tenant-A**, the condition `tenant != null` still evaluates to true. Query/authorization decisions must rely on the **verified tenant bound to job B**, not an unverified thread-local value.

~~~java
// Illustrative snippet; tenantContext, repository are application components.
String actualTenant = tenantContext.currentTenant();
if (!job.verifiedTenantId().equals(actualTenant)) {
    throw new SecurityException("Unexpected tenant execution context");
}
repository.findByTenantIdAndOrderId(job.verifiedTenantId(), job.orderId());
~~~

`job` must be an object containing a verified tenant from a trusted boundary; if no valid context is present, reject (fail closed). Better yet, pass the verified tenant directly into the service/repository to avoid relying on implicit context in security logic.

## 13. Common Bugs and Checklist

| Symptom | Cause | Proper Fix |
| --- | --- | --- |
| Log B carries A's requestId | MDC not cleaned on worker | Capture map at submit, install/clear and restore in `finally` |
| Tenant B confused with A | `ThreadLocal` retains previous task's value | Worker cleanup, verify authenticated tenant |
| User B processed with Authentication A | SecurityContext not cleaned properly | DelegatingSecurityContext wrapper, clear/restore with proper ownership |
| Dev test shows no bug | Worker reuse not forced | Single worker with sequential tasks |
| Task without MDC still sees MDC | Decorator only sets when snapshot is non-null | When snapshot is null, clear worker |
| `@Async` runs but request context is lost | Switched to another thread without propagation | Extract immutable IDs, use proper integration |
| Caller's `@Transactional` absent in worker | Transactions are thread-bound | Create transaction inside worker via Spring service |
| `MDC.clear()` in service wipes parent tracing scope | Cleared context not owned by that component | Snapshot previous and restore at boundary |
| `InheritableThreadLocal` uses wrong user | Value inherited at worker creation, not per task | Propagate per submission |
| Task timed out but context hasn't vanished | Worker still runs after caller times out | I/O timeout and cleanup when worker actually exits |
| Only pool A has decorator | Pool B or commonPool bypasses decorator | Audit all executor/scheduler/callback boundaries |
| Data leak despite correct log context | Log context is not an authorization mechanism | Check permissions and tenant in business/DB logic |

**Pre-merge checklist:** (1) Have all contexts using `ThreadLocal`/MDC/SecurityContext been identified? (2) Who owns cleanup? (3) Are null snapshots handled on the worker? (4) Is there a `finally` for both success and failure? (5) Are mutable security/request/session objects being passed? (6) Are transactions/EntityManagers being passed across threads? (7) Were multiple tasks tested on a single worker, including tasks without context? (8) Were exceptions, timeouts, cancellations, and overload tested? (9) Do all executors needing propagation use the same strategy? (10) Is there a fail-closed check for invalid tenants/users?

## 14. Self-Check Questions

1. Why is `ThreadLocal` not "one variable per HTTP request"?
2. Task B sets no tenant yet sees tenant-A: is that a propagation bug or stale reuse?
3. Does calling `MDC.clear()` in the controller clear the MDC of a `ThreadPoolTaskExecutor` worker?
4. Why must a decorator **clear when captured is null**, rather than only setting when a value exists?
5. If task A throws an exception after setting context, why is `finally` critical?
6. Does an MDC TaskDecorator automatically propagate Spring SecurityContext and transactions?
7. Does `MODE_INHERITABLETHREADLOCAL` update context every time a pool receives a new task?
8. If `CompletableFuture.supplyAsync` uses commonPool, is a decorator attached to `contextExecutor` invoked?
9. Why doesn't a timeout from `get(3, SECONDS)` prove the worker has cleaned up its context?
10. There is a stale tenant-A, yet `tenant != null` is true: how should authorization be checked and designed?

**Conclusion:** worker threads typically outlive individual tasks. To prevent reusing stale context, you must **capture per submission, install or clear before running, restore/remove in finally on the worker**, and test two sequential tasks on the same thread. Propagation serves execution context consistency; authorization must rely on verified data, never an unverified thread-local value.

## Official References

- [Java SE 17 — ThreadLocal, set/get/remove](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html)
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Spring Framework 6.2 — TaskDecorator](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/core/task/TaskDecorator.html)
- [Spring Framework 6.2 — ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html)
- [Spring Framework — Observability and context propagation](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Spring Security — Concurrency Support](https://docs.spring.io/spring-security/reference/features/integrations/concurrency.html)

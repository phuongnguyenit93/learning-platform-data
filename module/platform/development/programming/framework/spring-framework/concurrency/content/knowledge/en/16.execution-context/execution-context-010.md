# Do Not Use InheritableThreadLocal as a General Solution for Reusable Thread Pools

## 1. The Problem: Child Threads Inherit at Creation Time, Not Every Time a Task Runs

In Java and Spring applications, a request may need to carry a bit of **execution context** into asynchronous work: a request ID, tenant ID, correlation ID for logging, or framework-managed security info. Because these contexts are normally bound to the current thread, developers easily assume that replacing `ThreadLocal<T>` with `InheritableThreadLocal<T>` will make async tasks "automatically have" the request's data.

**That assumption is wrong when using a thread pool that reuses workers.** `InheritableThreadLocal` transfers **initial values from parent thread to child thread at the moment the child thread is created**. A pool may spawn workers at startup or upon receiving an initial task, and then reuse **the same worker** to execute tasks from many different requests. Request B submitting a task to a worker created during request A **does not make Java re-inherit** B's context.

The consequence can be **reading stale context**, reading an unexpected `null`, or mixing data across requests/tenants. This is not merely a logging bug: if code accidentally uses an old tenant/user ID to decide data access, the issue can become an **authorization and data isolation incident**.

### Lesson Objectives

After this lesson, you will:

- Understand when `InheritableThreadLocal` copies values and how `childValue(parentValue)` works, distinguishing it from **per-task** context propagation.
- Explain why `ExecutorService`, `ThreadPoolExecutor`, `ThreadPoolTaskExecutor`, and `@Async` can reuse workers, leaving inherited data un-updated with the caller.
- Reproduce the bug with a **Java 17+ program having deterministic stdout**, then fix it with a wrapper that captures/restores context at **submit** time.
- Know when to pass data via explicit parameters, when to use Spring's `TaskDecorator`, context propagation tools, or Spring Security wrappers.
- Handle `ThreadLocal.remove()` and restoring the prior value in `finally`, avoiding retaining request state on threads serving multiple requests.
- Distinguish between when a new thread is actually created versus when a worker already exists; understand the risk of mutable values shared by reference.
- Test context correctness using **the same reused worker** and multiple requests, without relying on thread counts or chance.

**Example versions:** Java 17+, Spring Framework 6.1.3 (pure Spring Maven example). `InheritableThreadLocal`'s inheritance rules are part of the Java contract; Spring does not alter that contract simply because `@EnableAsync` is used.

## 2. How Exactly Does InheritableThreadLocal Work?

### 2.1. Plain ThreadLocal vs. InheritableThreadLocal

`ThreadLocal<T>` provides a **per-thread** storage slot. If two threads both call `REQUEST_ID.get()` on a `ThreadLocal` key, each thread reads its own value and does not implicitly see the other thread's value.

`InheritableThreadLocal<T>` extends `ThreadLocal<T>`, adding a step that **initializes data for a child thread when the child thread is created**. Per Java 17 Javadoc:

- When creating a child thread, the child can receive initial values from the parent thread for `InheritableThreadLocal` variables that currently hold values.
- The `childValue(parentValue)` method computes the child's initial value; that computation happens **on the parent thread before the child is started**.
- By default `childValue` simply **returns the `parentValue` object itself**. If the value is a mutable object, parent and child can hold **the exact same reference**, not a deep copy.
- Java permits some forms of thread creation **not to inherit** inheritable thread-locals. Therefore, inheritance must not be treated as a universal mechanism across all executors and runtimes.

Comparison table:

| Characteristic | `ThreadLocal<T>` | `InheritableThreadLocal<T>` |
| --- | --- | --- |
| Values isolated per thread | Yes | Yes |
| Child thread automatically receives initial value from parent by default | No | Yes, when the **child thread is created** |
| Automatically updates value each time executor receives a new task | No | **No** |
| Thread pool worker automatically switches to request B's context | No | **No** |
| `remove()` on caller automatically clears value on existing workers | No | **No** |
| Suitable for request context in reusable pools without a wrapper | Unsuitable | **Unsuitable** |
| Usable when spawning a true child thread with parent-bound lifecycle | Must pass manually | Can be suitable if scope and shared objects are clearly understood |

**Rule:** `ThreadLocal` manages data per **thread**; a request/task is a logical scope **distinct from a thread**. Setting data on a thread does not establish a cleanup boundary after each task.

### 2.2. Timeline Causing the Bug

Suppose a thread pool has only one worker:

~~~text
Request A (caller): TENANT.set("tenant-A")
    |
    +-- submit task A
          |
          +-- pool needs new worker: creates worker-1
                |
                +-- worker-1 inherits value "tenant-A"
                +-- runs task A, reads tenant-A
                +-- task A finishes, worker-1 is NOT destroyed

Request B (caller): TENANT.set("tenant-B")
    |
    +-- submit task B
          |
          +-- pool REUSES worker-1
                |
                +-- Does NOT spawn a new thread
                +-- Does NOT re-invoke childValue for request B
                +-- task B still reads tenant-A from worker-1
~~~

**Core misconception:** developers think `submit(task B)` creates a new **parent/child** relationship between request B and worker-1. In reality, submitting merely hands a `Runnable`/`Callable` to the executor; worker-1 **was already created earlier**.

There is no guarantee every pool fails in the exact same way. If workers are created at startup, inherited data may be **empty**; if the pool scales up under load, new workers may receive different contexts; when a thread dies and is replaced, behavior can shift. This dependence on worker creation timing makes the approach **unstable**.

## 3. Standalone Runnable Java 17+: Reproducing Stale Request Context

This example deliberately misuses `InheritableThreadLocal` to observe the bug. `Executors.newSingleThreadExecutor()` uses one worker and reuses it for subsequent tasks under normal conditions. We call `Future.get()` after each task to ensure task A completes before submitting B.

Save as `InheritablePoolPitfallDemo.java`:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public final class InheritablePoolPitfallDemo {

    private static final InheritableThreadLocal<String> TENANT =
            new InheritableThreadLocal<>();

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            TENANT.set("tenant-A");

            // Worker is created on receiving the first task and inherits A.
            System.out.println("first="
                    + pool.submit(TENANT::get).get());

            // Caller changes context; old worker does not update automatically.
            TENANT.set("tenant-B");
            System.out.println("caller=" + TENANT.get());

            // B still runs on the pre-existing worker.
            System.out.println("second="
                    + pool.submit(TENANT::get).get());

        } finally {
            // Only clears value on MAIN; does not modify worker context.
            TENANT.remove();

            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Run:

~~~bash
javac InheritablePoolPitfallDemo.java
java InheritablePoolPitfallDemo
~~~

**Stdout on typical JDK 17+ in this single-worker example:**

~~~text
first=tenant-A
caller=tenant-B
second=tenant-A
~~~

### Why Is This Result Reliable?

1. `TENANT.set("tenant-A")` happens before the first task submission, so the worker spawned to run task A inherits value A upon creation.
2. `pool.submit(TENANT::get).get()` waits for task A to finish. The task only reads the value; it throws no exception that would replace the worker.
3. The caller switches `TENANT` to B without affecting the value inside **the other worker**.
4. The single-worker executor reuses that worker, so task B reads value **A**.
5. `TENANT.remove()` in `main` affects only the **main thread**. Worker cleanup does not happen automatically just because the caller cleared its context.
6. The program shuts down the executor in `finally`, leaving no worker running after the demo exits.

If real production code uses long-lived workers serving many requests, seeing tenant A during request B is an **unacceptable outcome**. Never copy this counter-example's propagation style into systems handling user data.

**Experiment limitation:** with multi-worker executors, workers may be spawned at different times or replaced, changing the observed data. That does not make the technique safe—it shows it is even more unpredictable.

## 4. Not Just Wrong Timing: Also the Risk of Sharing Mutable Objects

By default, `InheritableThreadLocal.childValue(parentValue)` returns **the exact input reference**. For example, if the parent thread puts a `Map<String, String>` or `List<String>`, the child thread can see and mutate **the same object**. Two threads have two slots in their thread-local maps, yet the values in those slots can point to **the exact same instance**.

Short illustrative Java snippet (fragment, needs imports and enclosing method):

~~~java
InheritableThreadLocal<java.util.List<String>> tags =
        new InheritableThreadLocal<>();

java.util.List<String> list = new java.util.ArrayList<>();
tags.set(list);

Thread child = new Thread(() -> tags.get().add("child"));
child.start();
child.join();

System.out.println(list); // [child]
tags.remove();
~~~

Here `join()` ensures the child finished mutating before main reads `list`; there is no concurrent update to `ArrayList` in the fragment. If parent and child mutate `ArrayList` concurrently, a **data race** is added because `ArrayList` is not thread-safe.

You can override `childValue` to create a copy when a child thread is created:

~~~java
// Illustrative fragment showing one way to copy a list at child thread creation.
InheritableThreadLocal<java.util.List<String>> tags =
        new InheritableThreadLocal<>() {
            @Override
            protected java.util.List<String> childValue(
                    java.util.List<String> parent) {
                return parent == null
                        ? null
                        : new java.util.ArrayList<>(parent);
            }
        };
~~~

However, **this does not fix the thread pool bug**: `childValue` is still invoked **only when creating the worker**, not when each task is submitted. Copying at thread creation decouples references, **not keeping data fresh per request**.

**Never attach a JPA entity, connection, transaction object, mutable security context, or heavy request object** to an inheritable thread-local to pass to a task. Those objects are typically bound to specific lifecycles, sessions, or threads and may not be thread-safe.

## 5. Situations Making the Bug Appear Sporadically

### 5.1. Workers Pre-Started Before Requests Arrive

`ThreadPoolExecutor` can be initialized with **pre-started** core workers via `prestartCoreThread()` or `prestartAllCoreThreads()`. Spring `ThreadPoolTaskExecutor` also has `setPrestartAllCoreThreads(true)`.

~~~java
// JDK fragment, not a standalone class.
ThreadPoolExecutor pool = new ThreadPoolExecutor(
        1, 1, 60, TimeUnit.SECONDS,
        new LinkedBlockingQueue<>());
pool.prestartAllCoreThreads();
~~~

If workers are spawned on a startup thread **lacking tenant/request context**, those workers do not automatically inherit context from later task-submitting callers. You may observe `null`, even when the request thread set `InheritableThreadLocal`.

### 5.2. Workers Created Lazily on the First Request

By default, many pools spawn workers on demand when tasks arrive. If request A triggers worker creation, that thread can inherit context A. As B/C/D reuse the worker, context A lingers. The risk of leaking data across requests is more severe than an easily spotted `null`.

### 5.3. Pool Scales Workers When the Queue Fills

With `ThreadPoolExecutor`, worker creation depends on `corePoolSize`, `maximumPoolSize`, and queue state. New workers may be created at different times and from different submitting threads. Consequently, the same pool can simultaneously contain a worker holding context A, a worker holding context B, and an empty-context worker. Results then depend on which worker happens to pick up a task.

Do not write tests assuming "submit three tasks and they will use workers A/B/C in order". Use a single-worker executor to deterministically demonstrate the flaw, or test systematically with latches, bounded workers, queues, and per-task context assertions.

### 5.4. Workers Replaced or Pool Resized

Workers can terminate, be replaced, or some pools have configurable idle timeouts. When a replacement worker is created, a different inheritable value may appear. Thus the bug can "vanish" after a restart or shift under high load; that does not mean the code is right.

### 5.5. Parent Thread Is Itself a Worker of Another Pool

In pipelines with multiple executor layers, a task running on a worker from the first pool may trigger worker creation in a second pool. `InheritableThreadLocal` values are inherited from **the thread creating the worker**, not necessarily the original request. With complex pool topologies, thread lineage does not reflect request lineage.

## 6. Distinguishing Scopes: Thread, Task, Request, and Transaction

~~~text
Request scope:      [ Request A ]  [ Request B ]  [ Request C ]
Task scope:           [ Task A ]     [ Task B ]     [ Task C ]
Worker scope:       [------------ worker-1 reused -------------]
                           ^
                           |
                  InheritableThreadLocal
                  inherits once at
                  creation, NOT at submit
~~~

For task B to know context B, the right approach is **capturing context when B is submitted**, installing that context **only for the execution scope of B**, and then cleaning up/restoring.

In particular, the following data types have their own mechanisms:

| Data | Appropriate Solution |
| --- | --- |
| Simple `tenantId`/`requestId` | **Pass immutable parameters** or snapshot at submit point |
| MDC/correlation logging | Controlled MDC map copy or configured context propagation facility |
| Spring Security `SecurityContext` | Use **Spring Security** wrappers/async integrations, verify scope and cleanup |
| Spring transactions | Establish a **separate transaction boundary** where execution runs; do not pass caller transaction via ThreadLocal |
| Servlet request attributes | Avoid retaining request objects past response; pass needed data or use facilities with clear lifecycles |
| Micrometer observation/tracing | Context propagation with properly registered accessors and instrumentation |
| Database session/JPA EntityManager | Do not share thread/session-bound resources; go through services/repositories on the worker with proper transactions |

**Security:** Passing a user ID as a String does not automatically become an authorization mechanism. Permission decisions must rely on an authenticated principal/context per security contracts, never trusting an arbitrary ThreadLocal as the sole source of sensitive identity.

## 7. Preferred Choice: Passing Context via Parameters

If a task only needs `tenantId`, `documentId`, a correlation ID, or a few **immutable** business values, the clearest approach is passing them directly to the task:

~~~java
// Fragment; tenantId is a value already verified at the boundary.
String tenantId = currentTenantId();

CompletableFuture<String> result =
        CompletableFuture.supplyAsync(
                () -> documentService.loadForTenant(tenantId),
                documentExecutor
        );
~~~

This is a **non-standalone fragment**, requiring application variables, methods, and executor. There is no `InheritableThreadLocal`; the task holds the `tenantId` snapshot in its closure. When the same worker runs tasks from different requests, each closure carries its own value.

Advantages: easy to test, explicit data relationships, zero cross-worker context leaks, and no guessing which framework interceptors apply. In return, APIs must accept explicit parameters; for multiple framework-specific contexts, an official propagation mechanism may fit better.

**Beware mutable objects:** If a closure holds an object the caller can mutate after `submit`, races still occur. Snapshot/immutable-copy needed values or build immutable DTOs instead of passing raw requests/entities subject to concurrent mutation.

## 8. Standalone Runnable Java 17+: Capture/Restore Context Per Task

When interacting with an API that uses `ThreadLocal`, you can write a wrapper that **captures the value on the submitting thread** and **sets that value on the worker strictly during task execution**. Afterward, the wrapper restores the worker's prior context or calls `remove()` if previously empty.

The following example uses a plain `ThreadLocal<String>`, **without InheritableThreadLocal**. That is deliberate: thread-creation inheritance does not solve per-task scoping.

Save as `ExplicitContextDemo.java`:

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class ExplicitContextDemo {

    private static final ThreadLocal<String> TENANT =
            new ThreadLocal<>();

    private static <T> Future<T> submitWithTenant(
            ExecutorService executor,
            Callable<T> task) {

        // Read on caller RIGHT AT SUBMIT, do not wait until worker runs.
        final String captured = TENANT.get();

        return executor.submit(() -> {
            // Worker may currently be serving another scope.
            final String previous = TENANT.get();

            try {
                if (captured == null) {
                    TENANT.remove();
                } else {
                    TENANT.set(captured);
                }

                return task.call();
            } finally {
                // Ensure the new task's context is not left on the worker.
                if (previous == null) {
                    TENANT.remove();
                } else {
                    TENANT.set(previous);
                }
            }
        });
    }

    private static String currentTenant() {
        String tenant = TENANT.get();
        return tenant == null ? "none" : tenant;
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            TENANT.set("tenant-A");
            Future<String> first =
                    submitWithTenant(pool, ExplicitContextDemo::currentTenant);
            System.out.println("first=" + first.get());

            TENANT.set("tenant-B");
            Future<String> second =
                    submitWithTenant(pool, ExplicitContextDemo::currentTenant);
            System.out.println("second=" + second.get());

            TENANT.remove();
            Future<String> empty =
                    submitWithTenant(pool, ExplicitContextDemo::currentTenant);
            System.out.println("empty=" + empty.get());
            System.out.println("caller=" + currentTenant());

        } finally {
            // Clean up context on MAIN and executor lifecycle.
            TENANT.remove();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Run:

~~~bash
javac ExplicitContextDemo.java
java ExplicitContextDemo
~~~

Output:

~~~text
first=tenant-A
second=tenant-B
empty=none
caller=none
~~~

### Why Does the Wrapper Fix the Bug?

1. `captured = TENANT.get()` runs on **the caller submitting the task**. Thus task A captures snapshot A and task B captures snapshot B.
2. When the worker accepts the task, it saves the **worker thread's** `previous`, then installs that task's snapshot.
3. The task reads its own value regardless of when the worker was created.
4. `finally` runs even if `task.call()` throws an exception, ensuring context is cleared/restored per the established scope.
5. If the caller has no value, the wrapper calls `TENANT.remove()` on the worker **before the task**, avoiding seeing stale context.
6. After the task finishes, the worker's context is restored to its prior state. On a clean initial worker, this means leaving neither task A nor B's value for the next task.

**"Restore previous" vs. "always remove":** When a wrapper owns only part of a context inside a nested task stack, restoring the old value is necessary so outer scopes are not broken. For completely dedicated workers with no baseline context, cleaning up with `remove()` after each task is also a valid strategy. However, if `previous` already contained leaked context from other code, restoring does not fix the external bug; you must control executor ownership and all context-setting paths.

**Note:** This is a minimal example for a `ThreadLocal<String>`. Do not take it verbatim and blindly apply it to `SecurityContext`, transactions, MDC, or mutable data without understanding official snapshot/restore APIs. For security data, prefer appropriate framework wrappers.

## 9. In Spring: TaskDecorator Is Where Context Is Set Per Task

`org.springframework.core.task.TaskDecorator` is a functional interface for wrapping a `Runnable` before execution. `ThreadPoolTaskExecutor.setTaskDecorator(...)` applies the decorator to the execution callback. This is the right place to create **per-submission context snapshots** and install/restore them on workers, rather than relying on inheritance at worker birth.

In Spring Framework 6.1.3, `ThreadPoolTaskExecutor` Javadoc notes that a decorator may receive a **task wrapper** (not necessarily the exact Runnable/Callable sent by the caller). Its primary role is setting up execution context or observing execution time; do not rely on a decorator to catch every exception thrown from a `FutureTask`, as the wrapper may keep errors inside the `Future`.

### 9.1. Runnable Spring Framework 6.1.3 Maven Example

Three-Java-file structure:

~~~text
spring-context-demo/
├── pom.xml
└── src/main/java/demo/
    ├── ContextConfig.java
    ├── TenantService.java
    └── SpringContextDemo.java
~~~

**File `pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-context-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.3</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>demo.SpringContextDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**File `src/main/java/demo/ContextConfig.java`:**

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class ContextConfig {

    // A simple value to observe results; do not use as a
    // security authorization source in real applications.
    public static final ThreadLocal<String> TENANT = new ThreadLocal<>();

    @Bean("contextExecutor")
    public ThreadPoolTaskExecutor contextExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(8);
        executor.setThreadNamePrefix("tenant-");

        executor.setTaskDecorator(task -> {
            // This callback is created when the task is submitted to the executor.
            String captured = TENANT.get();

            return () -> {
                String previous = TENANT.get();

                try {
                    if (captured == null) {
                        TENANT.remove();
                    } else {
                        TENANT.set(captured);
                    }
                    task.run();
                } finally {
                    if (previous == null) {
                        TENANT.remove();
                    } else {
                        TENANT.set(previous);
                    }
                }
            };
        });

        return executor;
    }

    @Bean
    public TenantService tenantService() {
        return new TenantService();
    }
}
~~~

`@EnableAsync` activates annotation processing, and `@Bean` creates a named executor selectable via `@Async("contextExecutor")`. `TaskDecorator` captures `TENANT` from **the task-submitting thread**, installs the snapshot on the worker, and cleans up after the task completes.

**File `src/main/java/demo/TenantService.java`:**

~~~java
package demo;

import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;

public class TenantService {

    @Async("contextExecutor")
    public CompletableFuture<String> readTenant() {
        String current = ContextConfig.TENANT.get();
        String result = current == null ? "none" : current;
        return CompletableFuture.completedFuture(result);
    }
}
~~~

The `readTenant()` method sits on a **service bean**, not declared inside the `@Configuration` class. Spring `@Async` Javadoc notes it does not support methods declared directly on `@Configuration`, so separating the two classes is intentional.

**File `src/main/java/demo/SpringContextDemo.java`:**

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public final class SpringContextDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             ContextConfig.class)) {

            TenantService service = context.getBean(TenantService.class);

            try {
                ContextConfig.TENANT.set("tenant-A");
                System.out.println("first=" + service.readTenant().join());

                ContextConfig.TENANT.set("tenant-B");
                System.out.println("second=" + service.readTenant().join());

                ContextConfig.TENANT.remove();
                System.out.println("empty=" + service.readTenant().join());
            } finally {
                ContextConfig.TENANT.remove();
            }
        }
    }
}
~~~

Run:

~~~bash
mvn -q compile exec:java
~~~

Output of the Java program:

~~~text
first=tenant-A
second=tenant-B
empty=none
~~~

### Analyzing the Spring Results

- Spring creates a `ThreadPoolTaskExecutor` using **one worker**. That worker is reused from call A to B and to the context-less call.
- `@Async("contextExecutor")` routes external calls through the Spring proxy, submitting them to the explicitly chosen executor.
- On each submission, `TaskDecorator` captures the value from the caller invoking the service: A, B, then `null`.
- Before running the target method, the worker is given the matching context. After the method and callback finish, `finally` restores the prior value.
- `join()` awaits completion of the `CompletableFuture`; since the program prints only on main, stdout order is deterministic.
- This snippet uses a **plain `ThreadLocal`**, needing no `InheritableThreadLocal`. It controls context **per task**, not by when the worker was born.

**Never copy a `static ThreadLocal` holding tenant IDs verbatim into production and use it to grant access.** This example uses a String to illustrate context propagation; real systems need auditable security boundaries, verified principals, clear ownership, and cleanup at request entry/exit.

**Lifecycle:** `AnnotationConfigApplicationContext` manages the executor bean. When the context closes, Spring shuts down the thread pool per lifecycle. Never instantiate a new `ThreadPoolTaskExecutor` per request.

## 10. Spring's Standard Integration Options

### 10.1. Spring 6.1+ and Micrometer Context Propagation

Spring Framework 6.1 provides `org.springframework.core.task.support.ContextPropagatingTaskDecorator`. It can use the Micrometer Context Propagation mechanism to capture and restore contexts that have registered matching accessors, useful for **tracing, observation, and logging**.

~~~java
// Spring 6.1+ fragment; requires appropriate dependencies/context accessors.
executor.setTaskDecorator(
        new ContextPropagatingTaskDecorator());
~~~

This is **not** a magic spell that automatically propagates **every** arbitrary `ThreadLocal`. Check the `io.micrometer:context-propagation` dependency, registered `ThreadLocalAccessor`s, Spring version, and how active instrumentation captures snapshots. Without an accessor for your app variable, do not claim it is propagated. Capture/restore also has overhead, so measure under high volumes of very short tasks.

For simple contexts holding only business IDs, **explicit parameter passing** usually remains easier to understand with fewer dependencies.

### 10.2. Spring Security: Do Not Use Inheritable Holder Mode as a General Solution

Spring Security typically stores thread-bound `SecurityContext` via `SecurityContextHolder`. Switching to `SecurityContextHolder.MODE_INHERITABLETHREADLOCAL` does not solve stale context bugs on a worker-reusing pool; values can still be inherited at worker creation, not when new tasks are submitted.

Spring Security provides dedicated concurrency wrappers, such as `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextExecutor`, and `DelegatingSecurityContextAsyncTaskExecutor` (depending on the executor API), to set up/clear security context per execution scope. With overloads taking a fixed `SecurityContext`, the wrapper intentionally uses **one shared context for every task**; for submit-time capture mode, pick the constructor/wrapper matching your intent. Do not assume every class dynamically propagates principals in the exact same way.

When handling real access rights, go through official Spring Security mechanisms and test **two requests with two different principals on the same worker**, plus a case with no principal. Do not manually copy mutable `SecurityContext` references and treat them as guaranteed safe snapshots.

### 10.3. MDC Uses Map Snapshots and Cleanup

For logging frameworks supporting MDC, the right approach is:

1. On the task-submitting thread, obtain a **copy of the context map** via the framework's MDC API (not sharing the same mutable map).
2. On the worker, save/restore the current MDC per framework requirements, installing the task's own copy.
3. In `finally`, clear or restore old data so the worker never carries request A's correlation ID into B.
4. Test when the caller has no context, when the task fails, when the future is rejected, and when workers were pre-started.

Not every MDC implementation has identical APIs and structures; do not mix arbitrary `ThreadLocal`s with MDC without checking your logging library's contract.

### 10.4. @Async and CompletableFuture Must Use the Right Executor

`@Async` in Spring usually relies on proxies; **self-invocation** (`this.asyncMethod()` inside the same service) bypasses the proxy in default `AdviceMode.PROXY`. Thus, a `TaskDecorator` on an executor cannot help if the call never reached the executor.

Similarly:

~~~java
// Fragment: businessExecutor is a TaskExecutor/Executor bean.
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(
                () -> loadDocument(), businessExecutor);
~~~

When passing the Spring executor, the decorator applies to tasks sent through that executor. Conversely, `CompletableFuture.supplyAsync(() -> loadDocument())` **without an executor** normally uses `ForkJoinPool.commonPool()`, so Spring's decorator **is not automatically applied**.

Stages like `thenApplyAsync(fn)` or `handleAsync(fn)` also use their own default async facility when no executor is passed. If context matters, pass the required executor to **each async stage needing isolation**, or use an explicitly designed propagation mechanism.

## 11. Which Contexts Should Not Be "Copied" Like a String?

Not every context can be copied naively:

- **Transactions:** Spring transactions are normally bound to the executing thread; never capture and move raw transaction/resource handles to a worker. Create an appropriate transaction inside the worker method via a Spring transaction interceptor/transaction template when needed.
- **Request/response objects:** Servlet requests have limited lifecycles; do not retain raw objects past HTTP response completion just to read headers on a background thread. Pass the immutable values genuinely needed.
- **EntityManager/Session:** session/transaction-bound persistence resources are not thread-safe by default; open resources per worker and manage lifecycles.
- **Mutable security context:** may change while a task waits; use official APIs/wrappers and define snapshots/ownership.
- **ThreadLocals holding large data:** long-lived pool workers can retain large objects, driving unexpected memory usage and retention. Cleanup via `remove()` is the responsibility of code putting context on the worker.

For jobs running over MQ or another process, `ThreadLocal`/`InheritableThreadLocal` is not a cross-process context transport protocol. Put needed metadata into messages/headers per security policy, and reconstruct valid context on the consumer.

## 12. Observing and Testing the Right Scenarios

### Minimum Required Tests

| Test Case | What to Confirm |
| --- | --- |
| One worker, two tasks A/B from caller switching tenants | Each task sees **its own right tenant** |
| After A/B, task C with no tenant | C must see **none/null**, zero leak of A or B |
| Worker `prestart`ed before any tenant existed | Task still gets right context via wrapper, independent of inheritance |
| Task throws exception mid-way | `finally` restores/clears context; next task is uncontaminated |
| Caller changes tenant **after** submitting yet before worker runs | Task uses **submit-time snapshot**, not the new value |
| Pool with multiple workers | Outcome does not depend on which worker the scheduler picks |
| `@Async` via proxy vs. self-invocation | Only assert async on calls traversing the proper interceptor |
| Executor shutdown/rejection | Catch errors at submit and never report "task accepted" when unaccepted |
| Security context across two principals | No identity/authorization mixing across requests |
| MDC/correlation | Logs inside task carry right trace, cleaned up when task ends |

To test races deterministically, use `CountDownLatch` to hold a worker, submit a task, and change caller context before releasing the latch. Once the worker reads, assert the wrapper captured the value **at submit time**. Avoid `Thread.sleep(10)` and guessing when a worker ran.

### Production Metrics to Observe

- Active tasks, queue length, submit → start latency, task duration, and rejection counts.
- Jobs missing tenant/correlation IDs, context mismatch rates, callbacks running on unexpected executors.
- "Wrong principal" security errors, unusual duplicate request IDs, and mismatched trace logs; **never log tokens, session secrets, or sensitive details** for debugging.
- Worker memory retention and `ThreadLocalMap` contents when leaks are suspected.
- Flow of async context across `@Async`, schedulers, `CompletableFuture` stages, retries, and message consumers.

### Code Review Checklist

1. Find all `new InheritableThreadLocal<>()` and places setting `SecurityContextHolder.MODE_INHERITABLETHREADLOCAL`.
2. Determine whether the value is **per-request/per-task** or genuinely valid for a **one-shot child thread**.
3. If tasks run on a worker-reusing pool, **do not rely on inheritance** to obtain request context.
4. Prefer immutable parameters, or wrappers/scopes capturing at submit and restoring/clearing via `finally`.
5. In Spring, configure `ThreadPoolTaskExecutor.setTaskDecorator(...)` or appropriate built-in propagation, checking ordering across multiple decorators/propagators.
6. With Spring Security, use integrated classes/wrappers and test concrete principals; never add custom authorization based on a String ThreadLocal.
7. Ensure `@Async` and `CompletableFuture` stages actually run on the configured executor; avoid accidentally bypassing proxies or falling back to common pool.
8. When passing mutable values, consider defensive snapshot copies and thread-safety; avoid accidental shared state between parent and child.
9. Handle cleanup on task failure, pre-run cancellation, timeout, or worker exception; watch what runs when a task is rejected.
10. Do not declare victory just by renaming threads or enlarging the pool; test multiple turns on the same worker and measure actual behavior.

## 13. Common Misconceptions

**"InheritableThreadLocal re-inherits automatically on every submit."** False: inheritance is tied to **thread creation**, not submission.

**"Once the caller calls `remove()`, the worker loses its old value too."** False: `remove()` affects only **the calling thread**, not other workers.

**"Pools cannot use InheritableThreadLocal because there are never new threads."** Inaccurate. Pools can spawn new workers, yet creation timing **does not align with every request's logical scope**; that is why inheritance is unreliable.

**"Overriding `childValue` to clone context solves per-request propagation."** No. It only changes the initial value at worker creation, not re-running per task.

**"Thread-local values on two threads are always two distinct objects."** False. Two slots can hold **the exact same mutable reference** under default inherited values.

**"Wrapping a task with TaskDecorator makes every Future exception throw out of the decorator."** No. With `submit`/`FutureTask`, errors can be held inside the `Future`; check `get()`/callbacks per API.

**"Enabling `@EnableAsync` is enough for context to propagate automatically."** No. It enables async method processing, not propagation for arbitrary `ThreadLocal`s.

**"Using Spring Security's `MODE_INHERITABLETHREADLOCAL` is safe for reusable pools."** No. It shares the same thread-creation inheritance limit; use proper security wrappers.

**"CompletableFuture without an executor uses Spring's ThreadPoolTaskExecutor."** False. Overloads without an executor normally run on the JDK's common pool.

**"Every task execution calls `set(context)` so `finally` is unnecessary."** False. A worker may later run another task and observe the old value.

**"Propagating an EntityManager/transaction via ThreadLocal makes them usable on another thread."** False. Those resources have their own lifecycle/thread constraints.

**"When a worker thread gets replaced and the bug disappears, the bug is fixed."** False. The change merely reflects new inheritance timing; the bug can recur.

## 14. Self-Check

**Question 1.** When does `InheritableThreadLocal` copy a parent's value to a child?  
**Answer:** When **the child thread is created**, via `childValue(parentValue)`, not automatically repeated when the thread picks up tasks.

**Question 2.** A single-worker pool was created during request A. Request B changes `TENANT` and submits a task; does task B automatically receive context B?  
**Answer:** Not with inheritance alone. The existing worker can keep reading value A; submit-time capture and worker-side install/cleanup are required.

**Question 3.** Does `TENANT.remove()` during request B clear `TENANT` inside the worker?  
**Answer:** No. `remove()` only affects the current thread; the worker is a different thread.

**Question 4.** Why can an `InheritableThreadLocal<List<String>>` cause unintended shared data?  
**Answer:** Default `childValue` returns the same parent reference; a mutable list can be shared, leading to cross-thread mutations and races.

**Question 5.** Why does cloning in `childValue` still fail to guarantee task B receives context B?  
**Answer:** Cloning only occurs when spawning a child thread. The existing worker is not recreated when accepting B.

**Question 6.** What is the simplest solution if a task only needs a verified `tenantId`?  
**Answer:** Pass `tenantId` as an immutable parameter to the task/service instead of implicitly pulling from an inheritable thread-local.

**Question 7.** In Spring, where should `TaskDecorator` capture context and clean up?  
**Answer:** Capture when **the task is submitted**; install the value on the worker before running the callback; restore or remove in `finally` after the callback finishes.

**Question 8.** When `@Async` hits self-invocation, is TaskDecorator guaranteed to run?  
**Answer:** No. In proxy mode, self-invoking the method may bypass the async interceptor/executor, so the decorator may never participate.

**Question 9.** Should you pass a transaction/JPA EntityManager via InheritableThreadLocal to keep the caller's transaction on the worker?  
**Answer:** No. Thread/session/lifecycle-bound resources need separate boundaries on the worker; never copy directly to simulate the same transaction.

**Question 10.** A task on a single-worker pool returns `null` even though the caller just set context; what scenario can cause this?  
**Answer:** The worker was pre-created when no context existed; inheritance happens only at creation time, not at submit time.

## 15. Official References

- [Java SE 17 — InheritableThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/InheritableThreadLocal.html): inheritance timing, `childValue`, and how children can receive the same reference.
- [Java SE 17 — ThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): `get`, `set`, `remove` for the current thread.
- [Java SE 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): worker reuse, on-demand construction, prestart, pool sizing, and queuing.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): `submit`, `Future`, and shutdown.
- [Spring Framework 6.1.3 — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): `setTaskDecorator`, thread pool lifecycle, queue, and decorator behavior with `FutureTask`.
- [Spring Framework 6.1.3 — TaskDecorator](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/core/task/TaskDecorator.html): wrapping task callbacks, setting up execution context.
- [Spring Framework 6.1.2 — ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/6.1.2/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html): Micrometer context propagation, available since Spring 6.1.
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): executors, `@Async`, pool selection, and concurrency handling.
- [Spring Security Reference — Concurrency Support](https://docs.spring.io/spring-security/reference/features/integrations/concurrency.html): `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextExecutor`, and per-task security cleanup.

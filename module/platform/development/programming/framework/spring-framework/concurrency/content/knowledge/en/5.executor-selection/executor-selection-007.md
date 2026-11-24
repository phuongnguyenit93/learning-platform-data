# DefaultManagedTaskExecutor in a Jakarta EE Environment

## 1. Why Does a Spring Application Running in Jakarta EE Need a Container-Managed Executor?

In Java SE, an application can directly use `Executors.newFixedThreadPool(...)` to create and manage background threads. When a Spring application is deployed **inside a Jakarta EE application server**, the situation differs: the server manages application lifecycle, shared resources, security identities, classloaders, naming contexts, and load control. Background tasks should normally run on **application-server-managed threads** rather than a self-created pool that the server cannot monitor or clean up.

Spring provides the class:

```java
org.springframework.scheduling.concurrent.DefaultManagedTaskExecutor
```

This class bridges **Spring's task execution interfaces** with **an executor available in JNDI** in the deployment environment. By default it looks up:

```text
java:comp/DefaultManagedExecutorService
```

This is the standard resource name for `ManagedExecutorService` in Jakarta Concurrency (formerly known via JSR-236). A compliant Jakarta EE server supplies the executor and is responsible for managing worker threads, processing capacity, execution context, and resource lifecycle. Spring retrieves the provisioned executor and delegates `TaskExecutor.execute(...)` or `AsyncTaskExecutor.submit(...)` calls to that executor.

**Model to remember:**

```text
Application call / @Async
          |
          v
TaskExecutor / AsyncTaskExecutor (Spring)
          |
          v
DefaultManagedTaskExecutor
          |
          | JNDI lookup when bean initializes
          v
java:comp/DefaultManagedExecutorService
          |
          v
Jakarta EE server's ManagedExecutorService
          |
          +-- server-managed threads
          +-- server resource allocation and limits
          +-- Jakarta EE contexts per configuration/spec guarantees
          +-- server-owned lifecycle
```

**DefaultManagedTaskExecutor does not create a new thread pool.** It is a **delegator/adapter** enabling a Spring application to submit work to a `java.util.concurrent.Executor` looked up via JNDI; in standard setups, that object is a `jakarta.enterprise.concurrent.ManagedExecutorService`. Detection and adaptation when the delegate is a managed executor live in the superclass `ConcurrentTaskExecutor`.

Lesson goals: accurately understand the contract, Spring configuration, JNDI lookup mechanism, usage with `@Async` or direct `Runnable` submission, result/error management, context-propagation limits, and deployment mistakes to avoid.

## 2. Position in the API Hierarchy

### 2.1. Types and Inheritance Relationships

```text
java.util.concurrent.Executor
  └─ execute(Runnable)

org.springframework.core.task.TaskExecutor
  └─ execute(Runnable)

org.springframework.core.task.AsyncTaskExecutor
  ├─ execute(Runnable)
  └─ submit(Runnable/Callable)

ConcurrentTaskExecutor
  └─ implements AsyncTaskExecutor,
     adapts any java.util.concurrent.Executor
          ^
          |
DefaultManagedTaskExecutor
  ├─ extends ConcurrentTaskExecutor
  ├─ implements InitializingBean
  ├─ performs JNDI lookup in afterPropertiesSet()
  └─ delegates to the discovered Executor

jakarta.enterprise.concurrent.ManagedExecutorService
  └─ extends java.util.concurrent.ExecutorService
     (a Jakarta EE resource, not a Spring executor subclass)
```

Common points of confusion:

- `DefaultManagedTaskExecutor` is a **Spring class**, in package `org.springframework.scheduling.concurrent`.
- `ManagedExecutorService` is a **Jakarta Concurrency interface**, in package `jakarta.enterprise.concurrent` in modern Jakarta releases.
- `Executors` (plural) is the Java SE factory class; it is **not** another name for `DefaultManagedTaskExecutor`.
- `ThreadPoolTaskExecutor` is a Spring bean that manages its own pool per application config; `DefaultManagedTaskExecutor` **uses an executor already under the server's management**.
- `ConcurrentTaskExecutor` is a general adapter for a provided `Executor`; `DefaultManagedTaskExecutor` adds conventional JNDI lookup.

Spring Javadoc has documented this class since Spring Framework 4.0, and it remains present in Spring Framework 6.x/7.x. Older descriptions mention “JSR-236” after the original specification name; when working with modern Jakarta EE, use the current environment's `jakarta.*` packages instead of copying `javax.enterprise.concurrent.*` from legacy Java EE examples.

### 2.2. Why Not Call ManagedExecutorService Directly?

You can use `ManagedExecutorService` directly when writing a Jakarta EE component. However, in a Spring application, depending on `TaskExecutor` or `AsyncTaskExecutor` keeps services unaware of JNDI resource names or server configuration. One runtime profile can select `DefaultManagedTaskExecutor`, while local/test profiles select a different executor.

`DefaultManagedTaskExecutor` is especially useful when you want a common Spring interface for:

1. Direct `TaskExecutor.execute(Runnable)` calls.
2. Spring `@Async("managedTaskExecutor")` methods.
3. Spring components requiring a `TaskExecutor` or `AsyncTaskExecutor` bean.

It is not a mechanism for running durable tasks across restarts, does not replace a message broker, and does not by itself guarantee background operations succeed in all scenarios.

## 3. JNDI and Jakarta EE's Default Resource

### 3.1. What Is JNDI in This Context?

JNDI (Java Naming and Directory Interface) is a Java API for looking up an object bound under a runtime-managed name. Under Jakarta Concurrency, the application server provides by default:

```text
java:comp/DefaultManagedExecutorService
```

This name references a `ManagedExecutorService` created/configured by the server. The lookup does not instantiate a new executor; it obtains a reference to the server-provided object for the application component to use.

Under Jakarta Concurrency, the default service can propagate at least **naming**, **classloader**, and **security** contexts from the submitting component, per the specification's rules. These contexts help tasks execute in the proper Jakarta EE environment; they do not mean arbitrary application `ThreadLocal` values are copied.

### 3.2. Bean Initialization Flow

When `DefaultManagedTaskExecutor` is a Spring bean, it implements `InitializingBean`. After setting properties, Spring invokes `afterPropertiesSet()`. The class performs a JNDI lookup using the configured name (defaulting to the standard name above), requests type `Executor`, and sets that object as the delegate for `ConcurrentTaskExecutor`.

```text
Spring creates bean
   |
   v
new DefaultManagedTaskExecutor()
   |
   +-- setJndiName(...), setResourceRef(...), if configured
   |
   v
afterPropertiesSet()
   |
   +-- JNDI lookup(name, Executor.class)
   |
   +-- success -> setConcurrentExecutor(foundExecutor)
   |
   +-- failure -> lookup/bean-init error; must fix runtime/name/mapping
```

**There is no default fallback to a self-created pool if the JNDI lookup fails.** If running the application in a Java SE environment or an embedded servlet container that does not provide this resource, bean configuration can fail at startup. Choose an executor matching the runtime rather than assuming merely adding the Jakarta Concurrency dependency makes the JNDI resource appear.

### 3.3. Full Names and Relative Names

Notable configuration APIs:

| Method | Purpose | Notes |
|---|---|---|
| `setJndiName(String)` | Overrides the default JNDI name with a server-published executor | The name must exist and the object must be compatible with `Executor` |
| `setResourceRef(boolean)` | Adjusts how relative names are resolved in `java:comp/env/` | Does not automatically create a new resource on the server |
| `setJndiTemplate(JndiTemplate)` | Customizes the object performing JNDI lookups | Mainly for integration/testing or specialized JNDI environments |
| `setJndiEnvironment(Properties)` | Supplies JNDI properties if required by the runtime | Usually unnecessary when container JNDI is already available |

With the **full** name `java:comp/DefaultManagedExecutorService`, you normally do not need to prepend `java:comp/env/`. If using a relative name with `resourceRef=true`, lookup rules can prepend `java:comp/env/`. Do not alter the default name merely because you see “env” in other examples.

## 4. Spring Example: Registering an Executor from JNDI

The following Java Configuration sample is intended for a Spring Framework application running **inside a Jakarta EE server that provides the default JNDI resource**.

**File `ManagedExecutorConfiguration.java`**

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.DefaultManagedTaskExecutor;

@Configuration
@EnableAsync
public class ManagedExecutorConfiguration {

    @Bean("managedTaskExecutor")
    public DefaultManagedTaskExecutor managedTaskExecutor() {
        return new DefaultManagedTaskExecutor();
    }
}
```

This is a **Spring configuration class**, not a standalone Java SE program with `main`. To run, the application needs compatible Spring Framework libraries on the classpath, must be bootstrapped with a Spring ApplicationContext, and must be deployed into a Jakarta EE runtime providing `java:comp/DefaultManagedExecutorService`. This class neither creates nor configures a new pool.

Why use `@EnableAsync`? Because this annotation activates Spring's mechanism for processing `@Async` methods. It is **not required** if the application only injects `TaskExecutor` and calls `execute(...)` manually. However, for `@Async` to work through Spring proxies, async support must be enabled in application configuration.

The name `managedTaskExecutor` is explicitly declared so `@Async` methods can target the right executor. If the application has multiple executors, do not rely on Spring picking a bean by chance.

### 4.1. Choosing Another JNDI Name

If the server administrator creates a dedicated resource and publishes it at `java:comp/env/concurrent/ReportingExecutor`, you can configure:

```java
@Bean("managedTaskExecutor")
public DefaultManagedTaskExecutor managedTaskExecutor() {
    DefaultManagedTaskExecutor executor =
            new DefaultManagedTaskExecutor();

    executor.setJndiName(
            "java:comp/env/concurrent/ReportingExecutor");
    return executor;
}
```

This is an **alternative bean method** replacing the method in `ManagedExecutorConfiguration`, not a second method with the same name in the same class. The server must have the corresponding configuration/mapping. The example name is not a resource automatically guaranteed by Jakarta EE; check your actual application server's documentation and configuration.

Do not call `afterPropertiesSet()` manually in the bean method above. When Spring creates the bean, the container handles the lifecycle and invokes that method after properties are set.

### 4.2. XML Configuration If the Project Uses XML

The same idea can be expressed as an XML bean:

```xml
<bean id="managedTaskExecutor"
      class="org.springframework.scheduling.concurrent.DefaultManagedTaskExecutor" />
```

This is a **Spring XML configuration fragment** requiring full XML namespaces/declarations in its containing file. Spring instantiates the bean and performs the JNDI lookup when the container starts. You can add a `jndiName` property if another resource is needed.

## 5. `@Async` Example Running on a Managed Executor

**File `ReportService.java`**

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @Async("managedTaskExecutor")
    public CompletableFuture<String> buildReport(String reportId) {
        // Simulate computation or external service call.
        String result = "Report " + reportId + " created";
        return CompletableFuture.completedFuture(result);
    }
}
```

**File `ReportControllerOrCaller.java`** — example of another Spring component calling the service:

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.stereotype.Component;

@Component
public class ReportControllerOrCaller {
    private final ReportService reportService;

    public ReportControllerOrCaller(ReportService reportService) {
        this.reportService = reportService;
    }

    public CompletableFuture<String> request(String reportId) {
        return reportService.buildReport(reportId);
    }
}
```

The two snippets above are **Spring component classes**; actually running them requires Spring initialization config, dependencies, and a Jakarta EE server as noted. There is no fixed stdout: execution order and completion timing depend on the managed executor.

Mechanism:

1. `ReportControllerOrCaller` receives `ReportService` via dependency injection. Calls from another bean pass through the Spring proxy.
2. `@Async("managedTaskExecutor")` tells Spring to use the named executor bean.
3. Spring submits the work to the executor; `DefaultManagedTaskExecutor` delegates to the `ManagedExecutorService` obtained from JNDI.
4. A Jakarta EE server-managed worker executes the method body; the result is observed via `CompletableFuture<String>`.
5. The caller can handle completion or exceptions without immediately blocking the request thread.

**Watch out for self-invocation:** if `ReportService` itself calls `this.buildReport(...)` from one of its own methods, the call normally bypasses the Spring proxy in default proxy mode and does not trigger `@Async` behavior. Design one bean to call another, or deliberately use another proxy/AspectJ mechanism depending on the application.

### 5.1. `@Async` Does Not Mean Every Subsequent Step Runs on the Managed Executor

If the caller uses `CompletableFuture` combinators, be clear which executor runs them. Calls like `thenApplyAsync(...)` or `CompletableFuture.supplyAsync(...)` **without passing an executor** may use CompletableFuture's/Java SE's default executor. Never assume every callback keeps running on `ManagedExecutorService` just because the first stage began from `@Async`.

When a specific callback must run on the managed executor, pass that executor to the overload accepting an `Executor`, or use the asynchronous completion facilities provided directly by `ManagedExecutorService` per your Jakarta Concurrency version.

### 5.2. `@Async` Exceptions

For methods returning `CompletableFuture<T>`, the caller should observe errors via `whenComplete(...)`, `handle(...)`, `exceptionally(...)`, or `get()/join()` where blocking is permitted. If `@Async` returns `void`, the caller has no result handle to receive errors; Spring provides `AsyncUncaughtExceptionHandler` to handle those exceptions.

Do not call `join()` right inside the HTTP request thread if the goal is non-blocking request handling. Coordinate results according to the endpoint contract, timeouts, and runtime capabilities.

## 6. Submitting Tasks Directly via TaskExecutor

You do not have to use `@Async`. A service can receive `TaskExecutor` directly via constructor injection and submit a `Runnable`:

**File `AuditDispatchService.java`**

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class AuditDispatchService {
    private final TaskExecutor executor;

    public AuditDispatchService(
            @Qualifier("managedTaskExecutor") TaskExecutor executor) {
        this.executor = executor;
    }

    public void dispatch(String eventId) {
        executor.execute(() -> {
            // Illustrates a task decoupled from the caller.
            System.out.println("Processed event: " + eventId);
        });
    }
}
```

This is a **Spring component**, using the bean configured in section 4. The `execute(...)` method only submits a `Runnable` and returns no `Future` for retrieving values or errors. For tasks requiring business state persistence, design result recording, retries, and idempotency as needed.

If injected as `AsyncTaskExecutor` (which `DefaultManagedTaskExecutor` implements), you can call `submit(Callable<T>)` to obtain a `Future<T>`. However, results and exceptions must still be observed. With Spring Framework 7 and releases with differing APIs, always check the Javadoc for the exact deployed library version; do not copy overloads verbatim from older Spring docs if the API has changed.

## 7. Differences Between the Spring Adapter and the Real ManagedExecutorService

There are two layers of responsibility:

| Aspect | DefaultManagedTaskExecutor | ManagedExecutorService |
|---|---|---|
| Where does it live? | Inside the Spring Framework library | In the Jakarta Concurrency API and server implementation |
| Who creates worker threads? | Creates no pool; delegates | Application server provides server-managed workers |
| Primary function | JNDI lookup, adapts `Executor` to `TaskExecutor` | Accepts tasks, executes with context, enforces server resource config |
| Pool size/queue config | No pool-management setters like `ThreadPoolTaskExecutor` | Configured via server settings/policies, product-specific |
| Executor lifecycle | Spring manages the **adapter bean** lifecycle | Server manages the resource/worker lifecycle |
| Calling `shutdown()` | Not the place to shut down a managed pool | Application must not shut down server-managed pools |
| Goal | Clean integration with `TaskExecutor`, `@Async` | Ensure compliant Jakarta EE behavior |

Note an additional distinction: because `DefaultManagedTaskExecutor` can delegate to **any compatible `Executor` bound in JNDI**, using this Spring class **does not by itself prove** the delegate is a `ManagedExecutorService`. With a compliant Jakarta EE server's default JNDI binding, it is the managed executor resource; if you point `setJndiName` to another resource, verify its actual type and semantics.

## 8. Jakarta EE Context: What Is and Isn't Propagated

### 8.1. Server-Managed Contexts

When a Jakarta EE component submits a task to `ManagedExecutorService`, the server applies Jakarta Concurrency context propagation rules. For the default managed executor, specification-mandated context groups include **naming context**, **classloader context**, and **security information**.

For instance, a task may need the application classloader to load classes or the JNDI context to access corresponding resources. Running workers “outside the application server's management” can break those assumptions.

However, exact details of which security identity is used and which permissions a task receives still depend on the Jakarta EE runtime's security model and policies. Do not assume every user identity or every application context is automatically copied.

### 8.2. Transaction Context Does Not Automatically Follow the Caller

Per Jakarta Concurrency, tasks run **without automatically participating in the submitting component's transaction**. The caller being inside `@Transactional` does not mean the managed task continues in that same transaction. If background work needs a transaction, establish appropriate transaction boundaries **inside the worker** via a Spring proxy-managed service or the application's Jakarta transaction mechanism.

Illustrative principle:

```text
Request thread:
  @Transactional begins TX-A
  submits @Async task
  continues processing and finishes TX-A

Managed worker thread:
  runs later or concurrently
  does not automatically inherit TX-A
  if needed: starts appropriate TX-B inside the worker
```

Consider data consistency as well: an async task can read data before the caller's transaction commits. If work must only start after commit, design post-commit events, an outbox, or an appropriately durable mechanism instead of relying solely on `@Async` submission order.

### 8.3. ThreadLocal, Spring Security, and MDC

Do not assume request `ThreadLocal`s, `RequestContextHolder`, `SecurityContextHolder`, logging MDC, or other libraries' trace contexts are automatically propagated just because you use `DefaultManagedTaskExecutor`. Each context type has its own rules; runtime-managed Jakarta EE contexts differ from application-created thread-local variables.

If a task needs `correlationId`, `tenantId`, or an application principal, pass immutable data explicitly as task arguments or use a verified context-propagation mechanism. For sensitive data, avoid blindly cloning full request objects or short-lived resources to workers.

## 9. Task Patterns and Outcomes: Runnable, Callable, Future

`ManagedExecutorService` extends `ExecutorService`, thus supporting methods like `execute(Runnable)` and `submit(Callable<T>)`; the Spring adapter exposes corresponding submission methods via `TaskExecutor`/`AsyncTaskExecutor`.

```text
Runnable
  └── work returning no direct value

Callable<T>
  └── work returning T, may throw checked exceptions

AsyncTaskExecutor.submit(Callable<T>)
  └── Future<T>
       ├── get()           retrieves value / reports error / may block
       ├── isDone()        can be true even on error/cancellation
       └── cancel(true)    requests cancellation/interruption cooperatively
```

Failure modes to account for:

- JNDI lookup fails at **bean initialization**: configuration/resource error, distinct from a task error.
- Executor rejects new work: may raise `TaskRejectedException` at the Spring layer or a delegate error per contract; handle at the call site.
- Task runs and throws an exception: when submitted via `submit`, `Future.get()` reports it wrapped in `ExecutionException`; inspect `getCause()` for the root cause.
- Waiting too long: `Future.get(timeout, unit)` throws `TimeoutException`; timing out does not automatically cancel the task.
- Task cancelled: `Future` can throw `CancellationException`; do not assume cancellation immediately halts blocking I/O.

**Never call `future.get()` indefinitely inside a worker when the dependent task needs the very same worker/resource to run.** The system can deadlock due to circular dependencies, worker limits, or shared locks. Managed executors are still subject to finite physical resource limits.

## 10. Lifecycle: Never Shut Down the Application Server's Pool

A fundamental difference between Jakarta EE and Java SE:

**In a Java SE program that creates its own `ExecutorService`**, the code owning the pool must shut it down with `shutdown()`/`shutdownNow()` under an appropriate policy.

**In Jakarta EE**, `ManagedExecutorService` is managed by the application server. The application **must not shut down** the shared managed executor. The specification mandates that lifecycle operations on `ManagedExecutorService`—such as `shutdown()`, `shutdownNow()`, `awaitTermination()`, `isShutdown()`, and `isTerminated()`—are rejected with `IllegalStateException`.

Therefore:

- When using `DefaultManagedTaskExecutor`, let Spring manage the **adapter bean**, while letting the application server manage the **actual executor**.
- Never pull out the delegate and call `shutdown()` as if owning a Java SE pool.
- Do not create a pool “per call” just to run background work; in Jakarta EE, use server-provided resources.
- During redeploy/undeploy, the server may stop accepting work, cancel pending tasks, or interrupt running tasks per spec/runtime policy.
- A managed executor runs tasks in-process, not as a durable queue. If work must complete across restarts/crashes, use an appropriate durable processing solution.

On the application side, you still must design timeouts, cancellation support, task error handling, input throttling, and work recovery. “Managed” refers to the server's resource-management responsibility; it does not mean the application avoids handling failures.

## 11. Comparison with ThreadPoolTaskExecutor and ConcurrentTaskExecutor

| Criterion | DefaultManagedTaskExecutor | ThreadPoolTaskExecutor | ConcurrentTaskExecutor |
|---|---|---|---|
| Executor source | JNDI lookup; defaults to Jakarta EE managed executor | Spring creates and configures `ThreadPoolExecutor` | Accepts an existing `Executor` |
| Suitable runtime | Jakarta EE application server with JNDI resource | Self-managed Spring apps, typically standalone Spring Boot | When an `Executor` from a library/other source must be exposed as a Spring executor |
| Configuring `corePoolSize`/`maxPoolSize`/`queueCapacity` | Configured on the application server rather than on this adapter | Direct setters on the bean | Depends on delegate; does not define its own pool |
| Who owns workers? | Application server | Application/Spring bean | Provider of the delegate |
| Default JNDI lookup | Yes | No | No |
| Compatible with `@Async` | Yes, when the bean is targeted and runtime is ready | Yes | Yes |

**Choose DefaultManagedTaskExecutor when:** the Spring application is packaged/deployed to a Jakarta EE runtime supporting Jakarta Concurrency, you want to use the server-managed executor, and you want Spring services to depend only on `TaskExecutor`.

**Choose ThreadPoolTaskExecutor when:** the Spring application runs standalone and actively manages its pool, queue limits, and shutdown; there is no Jakarta EE managed executor resource provided by the runtime.

**Choose ConcurrentTaskExecutor when:** you already have a suitable `Executor` object and just need to adapt it to Spring interfaces without default JNDI lookup conventions.

An embedded servlet container is not automatically equivalent to a full Jakarta EE application server with Jakarta Concurrency. Check your specific runtime's features and JNDI resources rather than judging by the word “Jakarta” in a dependency name.

## 12. Deployment Patterns by Environment

### 12.1. Production Jakarta EE Environment

A typical deployment sequence:

1. The administrator confirms the server is compatible and allows the app to use the default managed executor or a dedicated resource.
2. The Spring application configures a `DefaultManagedTaskExecutor` bean with the exact JNDI name.
3. At startup, Spring performs the lookup; lookup errors must clarify configuration rather than silently falling back to an unmanaged pool.
4. Services inject `TaskExecutor` or specify `@Async("managedTaskExecutor")`.
5. Manage worker counts, resource limits, rejection policies, and monitoring via application server features.
6. Test primarily on the real target runtime: permissions, contexts, timeouts, cancellation, shutdown/redeploy.

### 12.2. Running Locally/in Tests Without a Jakarta EE Server

You cannot assume `new DefaultManagedTaskExecutor()` runs in a plain Java SE unit test because the default JNDI binding is absent. Depending on project structure, you can:

- In unit tests, inject a direct `Runnable::run` `TaskExecutor` or a controlled test executor; verify business logic without depending on specific threads.
- In the application's local profile, use `ThreadPoolTaskExecutor` with explicit worker/queue limits and shutdown.
- In integration tests aiming to prove real JNDI and managed contexts, run on a compatible Jakarta EE runtime or an equivalent test harness with configured resources.

The following **standalone Java 17** example demonstrates that code depending on `Executor` can run on different delegates. **This only simulates the delegation principle**, with no JNDI, Spring, or Jakarta EE managed executor.

**File `ExecutorDelegationDemo.java`**

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ExecutorDelegationDemo {
    static void dispatch(Executor executor,
                         CountDownLatch done) {
        executor.execute(() -> {
            System.out.println(
                    "Worker thread: "
                    + Thread.currentThread().getName());
            done.countDown();
        });
    }

    public static void main(String[] args)
            throws InterruptedException {

        ExecutorService owner = Executors.newSingleThreadExecutor(
                runnable -> new Thread(runnable, "demo-worker"));

        try {
            CountDownLatch done = new CountDownLatch(1);
            dispatch(owner, done);
            done.await();
            System.out.println("Caller received completion signal");
        } finally {
            owner.shutdown();
        }
    }
}
```

Compile/run commands with Java 17+:

```bash
javac ExecutorDelegationDemo.java
java ExecutorDelegationDemo
```

Exact output:

```text
Worker thread: demo-worker
Caller received completion signal
```

Why does this program illustrate the right architecture? The `dispatch` method only knows `Executor`, and neither creates nor manages a pool. `main` creates the executor source for the demo and is responsible for calling `shutdown` on the pool it created. In Jakarta EE, the Spring adapter receives a server-owned executor via JNDI, and **the application must not shut down the delegate managed executor**.

The `CountDownLatch` signal makes the order of the two output lines deterministic; there is no need for `Thread.sleep(...)` to “hope for the best”. In this minimal example, the task always prints before calling `countDown()`. Real applications must add exception handling to ensure the latch cannot hang if the task can fail before counting down.

## 13. Comparing Two Ways to Access the Resource: Direct JNDI vs. Spring Adapter

Jakarta EE allows looking up or injecting `ManagedExecutorService` directly. When writing code depending on Jakarta APIs, in principle you can do:

**Illustrative Java snippet inside a Jakarta EE component (not a standalone program):**

```java
import jakarta.enterprise.concurrent.ManagedExecutorService;
import javax.naming.InitialContext;
import javax.naming.NamingException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;

public String runWithManagedExecutor()
        throws NamingException,
               InterruptedException,
               ExecutionException {

    ManagedExecutorService managed =
            (ManagedExecutorService) new InitialContext().lookup(
                    "java:comp/DefaultManagedExecutorService");

    Future<String> result = managed.submit(
            () -> "managed result");

    return result.get();
}
```

To use this snippet, you need the appropriate Jakarta Concurrency API on the classpath (usually provided by the server) and a component running in a valid JNDI environment. `javax.naming.InitialContext` remains part of Java SE's JNDI API; do not rename it to `jakarta.naming.InitialContext`. `get()` can block, so do not use it this way in code that must respond asynchronously right away.

The Spring approach:

```java
// Placed inside an injected Spring-managed component.
private final TaskExecutor executor;

public void submitJob() {
    executor.execute(() -> System.out.println("Managed job"));
}
```

The snippet above is not a standalone class; it requires injecting the `TaskExecutor` bean from section 4. When using the Spring adapter, the business layer does not need to import `ManagedExecutorService` directly or know JNDI resource names.

**The two approaches do not conflict:** choose the Jakarta API directly when you genuinely need capabilities specific to the managed executor; choose the Spring adapter when the architecture primarily relies on Spring abstractions.

## 14. Do Not Confuse ManagedTaskExecutor with a Scheduler

Jakarta Concurrency has `ManagedScheduledExecutorService` for scheduled/delayed tasks. Spring has a separate class named:

```java
org.springframework.scheduling.concurrent.DefaultManagedTaskScheduler
```

This scheduler class uses the corresponding default JNDI name:

```text
java:comp/DefaultManagedScheduledExecutorService
```

`DefaultManagedTaskExecutor` in this lesson focuses on **task execution**, not turning arbitrary `Runnable` instances into recurring scheduled jobs. An executor belonging to Spring's `SchedulingTaskExecutor` family does not mean it is a `TaskScheduler` for cron or delay schedules.

If the requirement is running every 5 minutes or on a cron expression, study `TaskScheduler`, `@Scheduled`, and dedicated scheduler configuration—do not apply `DefaultManagedTaskExecutor` as an ad-hoc timer.

## 15. Load Management, Stability, and Observability

Because the resource is server-owned, concurrency capacity and queue bounds are usually tuned through **application server configuration**, not `setCorePoolSize(...)` on `DefaultManagedTaskExecutor`. Consult the deployed server's documentation for exact property names and supported capabilities.

Metrics to observe:

- Number of submitted, running, completed, failed, or rejected tasks.
- Delay from submission to execution start; queue depth when exposed by the runtime.
- Execution duration p95/p99 and timeout rates.
- Latency of external systems that tasks depend on.
- Signs of workers blocked on I/O, mutexes, or `Future.get()`.
- Behavior while the application is stopping, restarting, or redeploying.

**Concurrency limits do not replace input throttling.** If requests can flood the system with long tasks or fan-out child tasks, the server may reject tasks. The application must decide whether to return errors, apply backpressure, perform bounded retries, or offload work to a durable queue.

Do not treat “managed” as a way to avoid all race conditions: if multiple tasks mutate shared state on a singleton bean, you still need thread-safety strategies such as immutable data, `AtomicLong`, concurrent collections, or `synchronized` with short critical sections. Server-managed context does not automatically protect Java data.

## 16. Common Deployment Mistakes

| Mistake | Symptom or consequence | How to fix |
|---|---|---|
| Deploying a plain Spring Boot JAR with `DefaultManagedTaskExecutor` enabled | Lookup of `java:comp/DefaultManagedExecutorService` fails as nonexistent | Pick a Spring pool for standalone runtimes or supply a real Jakarta EE resource |
| Thinking `new DefaultManagedTaskExecutor()` creates its own pool | No core/max pool options found and JNDI errors occur | Understand it is an adapter; configure pools on the server |
| Configuring `setJndiName(...)` without mapping the resource on the server | Bean fails to initialize because the name is not found | Check JNDI bindings and the type of the looked-up object |
| Wrongly prepending `java:comp/env/` before the default name | Lookup targets the wrong name | Use the standard full name; only use relative names when `resourceRef` is configured properly |
| Using `@Async` without enabling async support | Method runs synchronously | Configure `@EnableAsync` or equivalent |
| Calling `this.asyncMethod()` inside the same bean | Bypasses the Spring proxy in default mode | Split callers so invocation goes through a Spring-managed bean |
| Having multiple executors without specifying which one a task uses | Runs on an unexpected pool | Use `@Async("managedTaskExecutor")` or `@Qualifier` |
| Assuming all `ThreadLocal`/request contexts follow the task automatically | Missing or wrong context | Pass required data explicitly and verify context propagation tools |
| Assuming an async task inherits the caller's transaction | Uncommitted data or wrong transaction scope | Start an appropriate new transaction in the task or design post-commit execution |
| Calling `shutdown()` on the raw managed executor | Violates Jakarta EE lifecycle; may throw `IllegalStateException` | Let the application server manage lifecycle |
| Ignoring `Future`/`CompletableFuture` or having no error handler | Task failures go unrecorded | Observe completion/errors; implement bounded retries |
| Calling `CompletableFuture.supplyAsync(...)` without passing an executor | May run on the common pool, outside managed expectations | Pass the executor or use the appropriate Jakarta managed-stage API |
| Assuming tasks survive redeploy/crash | Unfinished work is lost | Choose a durable queue if business rules require persistence |

## 17. Checklist for Verifying a Real Deployment

When tasked with deploying a Spring application onto a Jakarta EE server, verify in order:

1. **Runtime:** the server genuinely supports Jakarta Concurrency and provides `java:comp/DefaultManagedExecutorService` or a dedicated configured resource.
2. **Library compatibility:** Spring Framework and Jakarta EE API versions match the runtime's classloader; avoid mixing old `javax.enterprise.concurrent` and new `jakarta.enterprise.concurrent` packages.
3. **Bean:** `DefaultManagedTaskExecutor` is created and initialized by Spring without error; if lookup fails, inspect JNDI names/mappings rather than patching with an unmanaged pool.
4. **Routing:** `@Async` names the bean explicitly or injects `TaskExecutor` with `@Qualifier`, and calls traverse the proxy when using `@Async`.
5. **Context:** verify naming, classloader, and security; do not rely on request `ThreadLocal`s or caller transactions propagating automatically.
6. **Outcomes:** callers have paths to observe success, errors, timeouts, and cancellation; tasks do not swallow exceptions or interrupts.
7. **Load:** the server has clear task/worker limits; load test and verify rejection behavior.
8. **Lifecycle:** the application never calls `shutdown` on the raw managed executor; understand what happens on redeploy.
9. **Durability:** if work must not be lost after a crash, use a durable job store rather than relying solely on in-memory task submission.

In integration tests, you can record submission and execution start timestamps, log correlation IDs clearly, and capture lookup and rejection errors; never treat a specific thread name as the sole proof that a task is running on a managed executor. Better evidence includes a correctly typed JNDI binding, server configuration, and runtime telemetry.

## 18. Self-Check Exercises

**Exercise 1 — Choosing the right runtime.** A Spring Boot app run via `java -jar` has no JNDI bindings. If you add a `DefaultManagedTaskExecutor` bean, what is likely to happen during context initialization? Name two proper options for local development vs. deploying to a Jakarta EE server.

**Guidance:** The default lookup cannot find the resource; configure another executor for local use, and keep the managed executor for the Jakarta EE environment where the real resource exists.

**Exercise 2 — Identifying pool ownership.** An application calls `managedExecutor.shutdown()` inside a `@PreDestroy` method believing it must clean up all resources. What is wrong?

**Guidance:** The managed executor's lifecycle belongs to the server; lifecycle methods on `ManagedExecutorService` are prohibited for application code. Closing the adapter bean does not mean shutting down the server's pool.

**Exercise 3 — Selecting the executor with `@Async`.** An ApplicationContext contains both a `ThreadPoolTaskExecutor` bean and a `DefaultManagedTaskExecutor` bean. How do you ensure a critical method is dispatched to the managed executor?

**Guidance:** Give the bean a stable name and use `@Async("managedTaskExecutor")`; callers must invoke through the Spring proxy.

**Exercise 4 — Analyzing transactions.** A request inside `@Transactional` spawns an `@Async` task that reads a record just modified but not yet committed. Is the task guaranteed to see the new version and share the same transaction?

**Guidance:** No. The task does not automatically join the caller's transaction. You must design transaction boundaries inside the task and coordinate post-commit execution if appropriate.

**Exercise 5 — Checking context.** A task needs `tenantId` stored in a request `ThreadLocal`. Why isn't using a managed executor enough to guarantee `tenantId` is present? Propose a way to pass the data.

**Guidance:** Specification-managed Jakarta EE contexts differ from custom `ThreadLocal`s; pass an immutable tenant ID via arguments, check authorization inside the worker, and never hold request objects past their lifecycle.

**Exercise 6 — Java 17 practice.** Run `ExecutorDelegationDemo`, replace `ExecutorService` with the inline executor `Runnable::run`, and explain why output switches to the `main` thread even though `dispatch` code did not change.

**Guidance:** `Executor` only promises to execute `Runnable`, not to create a new thread. The inline case executes immediately on the calling thread; Spring's adapter delegates according to the runtime, so behavior depends on the real executor.

## 19. Summary of Principles

- **`DefaultManagedTaskExecutor` is Spring's bridge** to an `Executor` via JNDI; by default it looks up `java:comp/DefaultManagedExecutorService`.
- **ManagedExecutorService belongs to Jakarta Concurrency** and is created, configured, worker-allocated, context-propagated, and lifecycle-managed by the application server.
- **There is no automatic fallback pool** if the JNDI resource is missing. Pick the right executor for the right environment.
- **Use Spring's `TaskExecutor` or explicitly named `@Async`** so the business layer does not depend directly on JNDI configuration.
- **Managed context does not mean carrying every `ThreadLocal` or transaction**; data transfer and transactions must be designed explicitly.
- **Never shut down the managed executor resource** from application code; while still handling errors, resource limits, timeouts, cancellation, and job durability.

### Primary References

- [Spring Framework API — DefaultManagedTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/DefaultManagedTaskExecutor.html)
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Jakarta EE Platform API — ManagedExecutorService](https://jakarta.ee/specifications/platform/11/apidocs/jakarta/enterprise/concurrent/managedexecutorservice)
- [Jakarta Concurrency Specification](https://jakarta.ee/specifications/concurrency/3.0/jakarta-concurrency-spec-3.0)

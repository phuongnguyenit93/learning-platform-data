# Closing Resources and Cleaning Up Context Across All Exit Branches in Spring AOP

## 1. Goal: prevent resource or context leaks after method execution

When a Spring service is called through an AOP proxy, a custom `@Aspect` may create **temporary resources** or **per-call context** for tracing, auditing, logging, timing, managing a resource handle, or integrating an external client. These objects must be cleaned up whether the target **returns successfully**, **returns `null`**, **completes `void`**, **throws an exception**, or an inner interceptor returns early.

Examples:

- An aspect places a correlation ID into a `ThreadLocal` before calling `proceed()`. If it forgets to clear/restore it, a thread pool may carry the previous request's ID into the next invocation.
- An aspect opens an `AutoCloseable` lease to track a call. If the target throws an exception, closing only on the success branch will leak the lease.
- An aspect populates temporary MDC logging fields. With nested scopes, calling `clear()` unconditionally can wipe out valid caller context.
- An aspect logs "cleanup complete", yet the cleanup callback itself throws an exception, masking the original exception.
- An aspect assumes a method returning `CompletableFuture` normally means the asynchronous work has finished and closes a still-needed resource too early.

**Practical goal:** design cleanup **around the lifecycle of each Spring AOP invocation**: resources actually owned by the aspect are closed by the aspect; temporary context set by the aspect is restored to its prior state; the target's exception or result is preserved if cleanup is observational only. For transaction, security, or HTTP request contexts owned by Spring infrastructure, never close or clear them arbitrarily.

**Scope:** Spring Framework, Spring-managed `@Aspect`, `@After` (after-finally), `@Around` with Java `try/finally` and `try-with-resources`, proxy boundaries, nested invocations, transaction/async/reactive nuances, and testing. This is not a guide to AspectJ compile-time or load-time weaving.

## 2. What Spring guarantees and what Spring cannot guarantee

Spring Framework describes `@After` as **after (finally) advice**: it is invoked when a **matched method execution** exits, regardless of whether it exits by normal return or by exception. `@AfterReturning` is only for normal returns, and `@AfterThrowing` is for exceptional exits. Spring also supports `@Around` with `ProceedingJoinPoint.proceed()`, allowing the advice itself to use `finally` to guard the scope it creates.

However, the phrase "all exit branches" must be understood with **proper boundaries**:

1. **Was the advice entered at all?** `@After` does not run if the method bypasses the Spring proxy, the pointcut does not match, or an outer interceptor short-circuits **before** reaching its advisor.
2. **A single method execution or completion of an asynchronous task?** When a method returns `Future`/`Mono`/`Flux` normally, a synchronous Spring proxy advice can finish before the underlying data or task completes.
3. **Target returned or transaction committed?** `@After` around a target execution is not implicitly an "after DB commit" callback; transaction advisor position and transaction propagation decide when commit happens.
4. **Is cleanup completely infallible?** `finally` attempts to run cleanup in Java when the thread flows normally through control flow, but it is not a guarantee when the process is killed, the JVM halts abnormally, or an uncontrollable system error occurs. Cleanup itself can also throw exceptions.
5. **Who owns the resource?** Resources managed by `PlatformTransactionManager` or Servlet/Spring Security filters are not for custom aspects to `close()`/`clear()`.
6. **Multiple Spring aspects participating?** Advice precedence can affect cleanup scope: an outer aspect wraps more interceptors than an inner aspect.

Therefore, do not write "`@After` always runs for every method call in the application." The accurate statement is: **when a method call is intercepted by a Spring proxy and has entered the matching `@After` advice, Spring applies after-finally when the join point exits**, subject to the proxy and invocation lifecycle bounds above.

## 3. Choosing the right cleanup mechanism in Spring AOP

| Goal | Preferred mechanism | Reason |
| --- | --- | --- |
| Run cleanup after normal return or exception of a matching method | `@After` | Spring AOP after-finally semantics; no need for `proceed()` control. |
| Aspect **allocates** a resource before invocation and must close that invocation's exact handle | `@Around` + `try/finally` or `try-with-resources` | Resource handle lives in a local variable of that invocation; avoids shared singleton aspect fields. |
| Temporarily set `ThreadLocal`/MDC for the target and restore the pre-invocation value | `@Around` + capture/restore in `finally` | Scope wraps the exact target execution using the context; supports nested calls. |
| Record **normal-return value only** | `@AfterReturning(returning="result")` | Observes the result; **insufficient** for cleanup on exceptional exits. |
| Log/meter specific exception types | `@AfterThrowing(throwing="error")` | Reads the error; **insufficient** for cleanup on success. |
| Clean up resources managed by Spring transaction management | Transaction manager/`TransactionSynchronization` | Resource lifecycle depends on the transaction, which can outlive a single service method. |
| Clear request-level SecurityContext | Spring Security filters/security infrastructure | Custom service aspects must not wipe out the caller's authentication/context. |
| Clean up when a future completes or publisher terminates | Callback APIs/reactive operators matching lifecycle | Synchronous `finally` in AOP only guards the moment the method returns the wrapper. |

**Rule of thumb:** if you only need cleanup at the end of a method without initializing your own context, `@After` is simpler. If the advice creates a context or resource at the **start** of the call and needs handle ownership, `@Around` + `finally` expresses ownership and timing most clearly.

## 4. @After is after-finally, not after-success

Annotation example from `org.aspectj.lang.annotation`:

```java
@Aspect
public class CompletionAuditAspect {
    @After(
        "execution(public * com.example.cleanup.TaskService.*(..))"
    )
    public void afterCompletion(JoinPoint jp) {
        System.out.println("finished:" + jp.getSignature().getName());
    }
}
```

This is an illustrative snippet requiring `Aspect`, `After`, `JoinPoint` imports, an aspect bean, and a target Spring bean to run. When a matching target method **returns normally** or **throws an exception**, the advice records the completion event in both cases.

**Distinction:**

```java
@AfterReturning(
    "execution(public * com.example.cleanup.TaskService.*(..))"
)
public void afterSuccess() {
    // Does not run if the method exits with an exception.
}

@AfterThrowing(
    "execution(public * com.example.cleanup.TaskService.*(..))"
)
public void afterError() {
    // Does not run if the method returns normally.
}

@After(
    "execution(public * com.example.cleanup.TaskService.*(..))"
)
public void afterFinally() {
    // Intended for cleanup steps on both exit types.
}
```

These snippets illustrate **three advice types with different semantics**; do not add them to the main demo project unless you intend to alter stdout. The `@AfterReturning`/`@AfterThrowing` pair is **not** a sufficient substitute for general cleanup when failure modes include another advice throwing an exception or an outer chain short-circuiting before/between layers.

### 4.1. @After does not directly receive return and exception objects

`@After` can accept `JoinPoint` to obtain the method signature and arguments. It **does not share the `returning` syntax of `@AfterReturning` or `throwing` syntax of `@AfterThrowing` to bind both result and exception simultaneously**.

If cleanup only needs to release a resource, observing payloads is unnecessary. If you must know the outcome, combine with appropriate advice or use **one `@Around`** that handles normal/exception branches while keeping cleanup in `finally`.

### 4.2. Beware of exceptions thrown by @After

Dangerous example:

```java
@After("execution(* com.example.cleanup.TaskService.*(..))")
public void close() {
    throw new IllegalStateException("cleanup failed");
}
```

This is an illustrative anti-pattern. If the target is throwing an original error, an additional exception thrown by cleanup can cause the caller to see a different error, depending on the advisor chain. **After-finally means getting a chance to clean up when the join point exits; it does not mean Spring automatically isolates every error thrown during cleanup.**

If cleanup is best-effort, define an explicit logging/suppression policy. If a resource close failure makes the operation fail by contract, propagate the error intentionally and retain cause/suppressed exceptions as needed.

## 5. @Around + try/finally for aspect-owned resources

`@Around` is the natural choice when the resource/context is created **within the same advice**:

```java
@Around("execution(public * com.example.cleanup.TaskService.*(..))")
public Object withResource(ProceedingJoinPoint pjp) throws Throwable {
    final ResourceHandle handle = openMyResource();
    try {
        return pjp.proceed();
    } finally {
        handle.close();
    }
}
```

This illustrative snippet requires `ResourceHandle`, `openMyResource()`, and the corresponding Java/Spring imports. It ensures that along normal Java control-flow paths exiting `proceed()`, `handle.close()` is called.

However:

- If `openMyResource()` **throws before `try`**, the handle was never created to close; any temporary state modified earlier still needs protection by an outer `try/finally`.
- If `handle.close()` throws inside `finally` while `proceed()` is throwing, the cleanup exception can **mask the original exception**.
- If the scope is created per invocation, never store the handle in a mutable field on a singleton aspect where threads would overwrite each other's handles.
- `pjp.proceed()` should run only once unless retry/short-circuiting is explicitly designed; with retries, cleanup must still account for each attempt.
- If the resource handle belongs to the target or transaction infrastructure, do not close it simply because you can obtain a reference to it.

### 5.1. try-with-resources preserves original exceptions better than manual finally close

Java `try-with-resources` applies suppression rules when both the body and `close()` throw:

```java
try (MyResource resource = acquire()) {
    return pjp.proceed();
}
```

If `proceed()` throws error A and `resource.close()` throws error B, with `try-with-resources`, error A generally stays the primary exception and B is recorded in `A.getSuppressed()`; this is a **Java** mechanism very useful for Spring AOP cleanup. If the body returns normally yet close throws, the caller may receive the close failure: that behavior should be documented if resource release is critical.

**Illustrative code**: `MyResource`/`acquire()` are hypothetical. In the runnable project in section 9, `Lease.close()` does not throw exceptions so the contract preserving normal and exception outcomes remains clear.

### 5.2. If acquisition fails halfway through

With multiple resources:

```java
try (ResourceA a = openA();
     ResourceB b = openB()) {
    return pjp.proceed();
}
```

If `openA()` succeeds but `openB()` throws, Java `try-with-resources` still closes `a`. Resources close in reverse opening order. This prevents leaking resource A when acquiring B fails.

This is a standalone snippet illustrating Java syntax; do not assume Spring manages these two hypothetical resource types. For resources managed by Spring/JPA/JDBC, use the framework's lifecycle APIs rather than closing them manually.

## 6. Cleaning up ThreadLocal/context: restore prior state, do not always clear

A custom Spring aspect may temporarily put a **correlation ID, tracing label, or request-scoped marker** into a `ThreadLocal` for downstream services to read on the same thread:

```java
String previous = Context.current();
Context.set("task:" + pjp.getSignature().getName());
try {
    return pjp.proceed();
} finally {
    Context.set(previous);
}
```

This is an illustrative snippet. `Context.set(null)` must invoke `ThreadLocal.remove()` in its implementation to avoid retaining stale references. **Why restore** instead of calling `remove()` unconditionally?

Suppose the caller already set `"request-42"`, and an outer aspect temporarily sets `"service:save"`. When the method finishes, code calling `remove()` unconditionally would **erase the request context owned by the caller**. Capturing `previous` and restoring `previous` is more accurate:

```text
Caller scope: context = request-42
  Aspect enters: previous = request-42
  Aspect sets: context = service:save
    Target reads: service:save
  Aspect finally restores: context = request-42
Caller continues: context = request-42
```

With nested invocations:

```text
Caller context = caller
  Outer Spring advice sets outer
    Collaborator call via second Spring proxy sets inner
    Inner finally restores outer
  Outer finally restores caller
```

Each layer must restore only **the state that layer changed**. If every advice calls a global `clear()`, an inner layer can destroy an outer layer's context.

### 6.1. ThreadLocal and ThreadPool

Thread pools reuse threads. If advice sets a `ThreadLocal` without restoring or removing it in `finally`, a subsequent invocation on the same worker thread may observe the stale marker, causing:

- Incorrect log correlation (carrying over the previous request/tenant);
- Holding large object references longer than necessary;
- Context data leaking across requests/tasks;
- Flaky tests dependent on thread reuse and execution order.

However, **do not wipe ThreadLocals belonging to other frameworks**. An aspect should clean up only ThreadLocals it creates/manages, or scope APIs with clear public ownership.

### 6.2. MDC/SLF4J

When logging integrates SLF4J MDC, a Spring `@Around` often needs to set a temporary marker in `MDC` and restore the previous marker:

```java
String oldValue = MDC.get("operation");
MDC.put("operation", operationName);
try {
    return pjp.proceed();
} finally {
    if (oldValue == null) {
        MDC.remove("operation");
    } else {
        MDC.put("operation", oldValue);
    }
}
```

This is an **illustrative pattern** requiring `org.slf4j.MDC` and an appropriate SLF4J/logger dependency. It is not included in the SLF4J-free demo in section 9. Do not call `MDC.clear()` unconditionally if callers or frameworks already populated a request ID or other trace fields.

If you only want to restore **one key**, preserve that exact previous key. If advice intentionally swaps the entire MDC map, consider snapshotting/restoring the map using the logging integration's API and weigh the cost and context coupling.

### 6.3. Spring Security's SecurityContextHolder is not owned by custom aspects by default

In Servlet applications, Spring Security typically stores authentication state in `SecurityContextHolder` (using `ThreadLocal` by default) and manages its lifecycle via filter infrastructure. A custom Spring service aspect **should not** end every call with:

```java
SecurityContextHolder.clearContext(); // Do not do this blindly on every service exit.
```

This code is an **illustrative anti-pattern** when Spring Security filters or callers still need the authenticated principal. It can wipe the context mid-request, breaking downstream authorization.

Intervene only if a component **actually owns setting a temporary context** under an explicit contract, and restore the previous context properly. For cross-thread task execution, use the appropriate Spring Security `DelegatingSecurityContext...` utilities instead of ad-hoc manual set/clear calls.

## 7. Do not close Spring/JPA/JDBC resources managed by another layer

Spring transaction infrastructure can bind resources to threads, managing connections, `EntityManager`s, and synchronization callbacks. A custom `@Aspect` must not conclude "the method is about to finish, so I can call `Connection.close()`/`EntityManager.close()`."

### 7.1. @Transactional and resource ownership

If a Spring service has:

```java
@Transactional
public void writeOrder(String id) {
    // JPA repository / JdbcTemplate work
}
```

This illustrative snippet is valid only when the application has transaction management enabled and a proper transaction manager/data source. A `@Transactional` service execution may participate in **the caller's transaction**, spanning multiple service methods.

If a custom aspect closes a connection or `EntityManager` in `@After` on a method mid-transaction, Spring may still need that resource for remaining operations. Consequences can include premature closure, rollbacks, lazy-loading failures, or lost context.

**Rule:** use `JdbcTemplate`, Spring Data repositories, transaction-aware resource access, or Spring transaction APIs. Never grab a Spring-bound resource directly and close it on the lifecycle of *a single method advice* when the resource belongs to the transaction lifecycle.

### 7.2. Need cleanup tied to transaction completion?

Use Spring transaction synchronization:

```java
if (TransactionSynchronizationManager.isSynchronizationActive()) {
    TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCompletion(int status) {
                // Release a resource owned by THIS COMPONENT
                // after the corresponding transaction completes.
            }
        }
    );
}
```

This is an **illustrative snippet** requiring imports from `org.springframework.transaction.support` and clear resource ownership. `afterCompletion` receives the commit/rollback/unknown status of transaction synchronization; its semantics differ from `@After` on a target method.

If synchronization is not active, the application must decide its own policy: clean up immediately, skip registration, or report an error per contract. Do not call `registerSynchronization` unconditionally.

When you need a business event **after commit**, you can use `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` if appropriate; it is also **not** a general substitute for local `AutoCloseable` cleanup.

### 7.3. Commit errors can occur after the target returns

The relative order of a custom aspect and the transaction advisor determines whether your `@After`/`finally` runs before or after commit. The target method can return normally while commit fails in an outer interceptor. Do not equate `cleanup-called` with "database committed."

With transaction tests, verify the actual DB state and callback timing against the real transaction boundary; do not infer from log order alone.

## 8. @After and @Around differ in ownership, not just syntax

Compare two patterns:

**Pattern A — `@After` releases state managed by separate infrastructure:**

```java
@After("execution(* com.example.cleanup.TaskService.*(..))")
public void recordEnd(JoinPoint jp) {
    recorder.record(jp.getSignature().getName());
}
```

`@After` can make sense when merely recording a completion event to a thread-safe recorder bean; there is no need to hold a resource handle created at invocation start. `recorder` is an illustrative dependency with no definition in this snippet.

**Pattern B — `@Around` owns per-invocation scope:**

```java
@Around("execution(* com.example.cleanup.TaskService.*(..))")
public Object withScope(ProceedingJoinPoint pjp) throws Throwable {
    String previous = MyContext.current();
    MyContext.set("within");
    try (AutoCloseable resource = myResourceFactory.open()) {
        return pjp.proceed();
    } finally {
        MyContext.restore(previous);
    }
}
```

**Snippet B is design-illustrative only**; `AutoCloseable.close()` may declare `throws Exception`, so the advice's `throws Throwable` signature lets it propagate and Java try-with-resources applies suppression. `MyContext`/`myResourceFactory` require implementations.

Pattern B has **clear scope ownership**: the aspect creates the handle and holds it in a local variable, enclosing the exact target invocation. In a singleton Spring `@Aspect`, never use mutable instance fields such as `currentHandle`/`currentRequestId` to store per-call state because concurrent requests will overwrite each other.

### 8.1. Do not mechanically replace try/finally with @AfterReturning + @AfterThrowing

You can write two separate advice methods, but it easily duplicates cleanup code and risks diverging exception/type bindings. If a resource handle is created in `@Before`, how do `@AfterReturning` and `@AfterThrowing` obtain the exact per-invocation/per-thread handle? Using a singleton field is wrong; passing through a `ThreadLocal` introduces yet another lifecycle to manage.

When the logic is **setup → proceed → cleanup**, a single `@Around` with lexical scope and `finally` is usually cleaner, safer, and easier to test.

## 9. Runnable Java 17+ demo: cleanup on success, void, null, and exception

The demo below actually runs a **Spring Framework AOP proxy** with a Spring-managed `@Aspect`. The aspect creates **a lease (resource handle)** and **sets a `ThreadLocal` marker** isolated per invocation. Across normal return, `void`, `null`, and target exception, the aspect always closes the lease and **restores the caller's marker**.

Environment: Java 17+, Spring Framework **6.2.19**, AspectJ Weaver **1.9.25.1**, Gradle. The resource objects created in the demo are **mock resources that only count invocations**, opening no sockets or JDBC connections; do not use them to extrapolate transaction resource cleanup.

### 9.1. Directory tree

```text
spring-aop-cleanup/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/cleanup/
    ├── AppConfig.java
    ├── CallContext.java
    ├── ProbeResources.java
    ├── CleanupAspect.java
    ├── TaskService.java
    └── Main.java
```

**`settings.gradle`**

```gradle
rootProject.name = 'spring-aop-cleanup'
```

**`build.gradle`**

```gradle
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
    implementation 'org.springframework:spring-aop:6.2.19'
    implementation 'org.aspectj:aspectjweaver:1.9.25.1'
}

application {
    mainClass = 'com.example.cleanup.Main'
}
```

In production Spring Boot, let the Boot BOM manage Spring module and AspectJ versions; do not copy the demo's versions into a different Boot major version without checking compatibility.

### 9.2. A CallContext that accurately restores the previous value

**`CallContext.java`**

```java
package com.example.cleanup;

public final class CallContext {
    private static final ThreadLocal<String> CURRENT = new ThreadLocal<>();

    private CallContext() {}

    public static String current() {
        return CURRENT.get();
    }

    public static void set(String value) {
        if (value == null) {
            CURRENT.remove();
        } else {
            CURRENT.set(value);
        }
    }
}
```

In the demo, `CallContext` acts as an **application/aspect-owned ThreadLocal**, completely independent of `SecurityContextHolder` or the Spring transaction manager. `set(null)` calls `remove()` to release the thread reference when there is no parent value.

`Main` intentionally sets `"caller"` before the service calls; the advice must restore **`"caller"`** rather than calling clear unconditionally because that state belongs to the caller.

### 9.3. Open/close lease resource with invocation counters

**`ProbeResources.java`**

```java
package com.example.cleanup;

import java.util.concurrent.atomic.AtomicInteger;

public class ProbeResources {
    private final AtomicInteger opened = new AtomicInteger();
    private final AtomicInteger closed = new AtomicInteger();

    public Lease open(String name) {
        opened.incrementAndGet();
        System.out.println("resource:open:" + name);
        return new Lease(name);
    }

    public int openedCount() {
        return opened.get();
    }

    public int closedCount() {
        return closed.get();
    }

    public final class Lease implements AutoCloseable {
        private final String name;
        private boolean done;

        private Lease(String name) {
            this.name = name;
        }

        @Override
        public void close() {
            if (!done) {
                done = true;
                closed.incrementAndGet();
                System.out.println("resource:close:" + name);
            }
        }
    }
}
```

Each `open()` creates a **dedicated Lease**; no shared mutable handle is reused across the singleton aspect. `close()` in the demo neither declares nor throws checked exceptions, so it never masks target exceptions.

`AtomicInteger` protects the counters if multiple threads update them; the `done` boolean belongs to each handle and the demo does not pass a handle across threads. If a real resource can be closed concurrently from multiple threads, define an explicit concurrency/idempotency contract.

### 9.4. Spring target with four exit paths

**`TaskService.java`**

```java
package com.example.cleanup;

public class TaskService {
    public String ok(String id) {
        System.out.println("target:ok:context=" + CallContext.current());
        return "ok:" + id;
    }

    public void refresh() {
        System.out.println("target:refresh:context=" + CallContext.current());
    }

    public String missing() {
        System.out.println("target:missing:context=" + CallContext.current());
        return null;
    }

    public String fail() {
        System.out.println("target:fail:context=" + CallContext.current());
        throw new IllegalStateException("boom");
    }
}
```

All methods are public and non-final; the class is non-final. `fail()` represents an exceptional exit; `missing()` represents a **normal return of `null`**; `refresh()` represents normal completion of `void`.

### 9.5. Spring aspect using try-with-resources and finally

**`CleanupAspect.java`**

```java
package com.example.cleanup;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class CleanupAspect {
    private final ProbeResources resources;

    public CleanupAspect(ProbeResources resources) {
        this.resources = resources;
    }

    @Around("execution(public * com.example.cleanup.TaskService.*(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        String method = pjp.getSignature().getName();
        String previous = CallContext.current();
        CallContext.set("scope:" + method);

        try {
            try (ProbeResources.Lease lease = resources.open(method)) {
                System.out.println(
                    "advice:enter:" + method
                    + ":context=" + CallContext.current()
                );
                return pjp.proceed();
            }
        } finally {
            CallContext.set(previous);
            System.out.println(
                "advice:restore:" + method
                + ":context=" + CallContext.current()
            );
        }
    }
}
```

**Exact execution order:**

1. Capture `previous` **before** changing the current marker.
2. Set the temporary marker for the current invocation.
3. `resources.open(method)` creates the Lease.
4. Target is invoked **once** via `pjp.proceed()`.
5. Whether the target returns or throws, Java `try-with-resources` calls `Lease.close()` (in the example, simply incrementing the count and printing).
6. The wrapper `finally` **always restores `previous`** when control exits the try block, even if `open()` or `close()` throws.
7. The advice does not catch and turn errors into `null`; it lets the original exception propagate to the caller per Java propagation rules.
8. If `close()` on a real resource throws, you must consider suppression/masking behavior; `Lease.close()` in the demo is intentionally no-throw so the four outcomes are clearly visible.

**Important design detail:** the cleanup section in `finally` still contains `System.out.println`. In a production app, even logging should be treated as a side effect that can fail depending on the environment; if preserving exceptions/results is a hard contract, design cleanup and error logging with an explicit failure policy. `finally` only guarantees control flow reaches cleanup along normal Java execution paths, not that every side effect is infallible.

### 9.6. Registering Spring beans and enabling AOP support

**`AppConfig.java`**

```java
package com.example.cleanup;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    ProbeResources probeResources() {
        return new ProbeResources();
    }

    @Bean
    CleanupAspect cleanupAspect(ProbeResources resources) {
        return new CleanupAspect(resources);
    }

    @Bean
    TaskService taskService() {
        return new TaskService();
    }
}
```

`@Aspect` is not itself `@Component`; `@Bean` registers the aspect in the Spring container. The target `TaskService` is also a Spring-managed bean. `@EnableAspectJAutoProxy(proxyTargetClass=true)` enables Spring AOP class-based proxies, so `getBean(TaskService.class)` returns a proxy of the concrete class.

`@ComponentScan` is unnecessary since all three beans are declared explicitly. Spring AOP uses AspectJ annotations and pointcut parsing, yet interception remains proxy-based without needing `-javaagent`.

### 9.7. Main running the four cases and checking resource counts

**`Main.java`**

```java
package com.example.cleanup;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            TaskService service = context.getBean(TaskService.class);
            ProbeResources resources = context.getBean(ProbeResources.class);

            CallContext.set("caller");

            System.out.println("proxy=" + AopUtils.isAopProxy(service));
            System.out.println("before=" + CallContext.current());

            System.out.println("result=" + service.ok("A"));
            System.out.println("afterOk=" + CallContext.current());

            service.refresh();
            System.out.println("afterRefresh=" + CallContext.current());

            System.out.println(
                "missingIsNull=" + (service.missing() == null)
            );
            System.out.println("afterMissing=" + CallContext.current());

            try {
                service.fail();
            } catch (IllegalStateException error) {
                System.out.println("caught=" + error.getMessage());
            }
            System.out.println("afterFail=" + CallContext.current());

            System.out.println("opened=" + resources.openedCount());
            System.out.println("closed=" + resources.closedCount());

            CallContext.set(null);
            System.out.println("afterClear=" + CallContext.current());
        }
    }
}
```

At the project root, with Java 17+ and Gradle installed:

```bash
gradle run --quiet
```

With Gradle Wrapper: `./gradlew run --quiet` (Linux/macOS), `gradlew.bat run --quiet` (Windows).

**Stdout printed by the program, in exact order** (excluding external JVM/Gradle/Spring notices):

```text
proxy=true
before=caller
resource:open:ok
advice:enter:ok:context=scope:ok
target:ok:context=scope:ok
resource:close:ok
advice:restore:ok:context=caller
result=ok:A
afterOk=caller
resource:open:refresh
advice:enter:refresh:context=scope:refresh
target:refresh:context=scope:refresh
resource:close:refresh
advice:restore:refresh:context=caller
afterRefresh=caller
resource:open:missing
advice:enter:missing:context=scope:missing
target:missing:context=scope:missing
resource:close:missing
advice:restore:missing:context=caller
missingIsNull=true
afterMissing=caller
resource:open:fail
advice:enter:fail:context=scope:fail
target:fail:context=scope:fail
resource:close:fail
advice:restore:fail:context=caller
caught=boom
afterFail=caller
opened=4
closed=4
afterClear=null
```

### 9.8. Four outcomes, one cleanup invariant

| Method call | Target outcome | Was `Lease.close()` called? | `CallContext` after call | Caller receives |
| --- | --- | --- | --- | --- |
| `ok("A")` | Normal `String` | Yes | `caller` | `ok:A` |
| `refresh()` | Normal `void` | Yes | `caller` | No value |
| `missing()` | Normal `null` | Yes | `caller` | `null` |
| `fail()` | Throws `IllegalStateException` | Yes | `caller` | Exception `boom` |

Two invariants demonstrated by the demo by design:

- **`opened=4` and `closed=4`**: one lease per intercepted external invocation, closed exactly once per handle.
- **`afterOk=afterRefresh=afterMissing=afterFail=caller`**: the nested aspect scope does not erase the caller's context. Finally, the caller itself clears the `CallContext` it set, so `afterClear=null`.

Do not confuse **close count** with transaction commit count. The demo's lease is an application-created resource, not a Spring transaction-managed connection.

## 10. Advanced case: nested Spring bean calls and context scopes

When one service calls **another Spring collaborator bean through its proxy**, multiple nested aspect scopes can exist:

```text
Request scope = req-42
  Proxy A: @Around sets service-A
    Service A calls injected proxy B
      Proxy B: @Around sets service-B
      Service B target sees service-B
      Proxy B finally restores service-A
    Service A target sees service-A again
  Proxy A finally restores req-42
Request scope still req-42
```

For correctness, each around advice keeps its **own `previous` in a local variable** and restores it in `finally`. Never store `previousContext` in a field on a singleton `@Aspect` because concurrent calls would overwrite each other.

If Service A calls `this.someMethod()` internally, that invocation **does not go through the Spring AOP proxy**, so no new advice scope targeting `someMethod` alone is created; this is a Spring proxy limitation, not a `finally` bug.

### 10.1. When the initial context is null

If `CallContext.current()` returns `null` before the advice enters:

```java
String previous = CallContext.current(); // null
CallContext.set("scope:work");
try {
    return pjp.proceed();
} finally {
    CallContext.set(previous); // set(null) invokes ThreadLocal.remove()
}
```

After the call, the `ThreadLocal` is empty again. This is the right behavior for an invocation with no parent context.

## 11. When resource closing fails: preserving the original error and defining failure policy

**Every piece of advice saying "always close in finally" must account for the fact that closing can fail.**

### 11.1. Manual finally close can mask the target exception

```java
try {
    return pjp.proceed();  // Throws ServiceException
} finally {
    resource.close();      // Also throws IOException
}
```

If `close()` throws while unwinding `finally`, Java can make the cleanup exception replace the service exception at the caller. For non-critical audit/metric resources, that behavior is usually undesirable.

### 11.2. try-with-resources manages suppressed exceptions

```java
try (MyResource resource = acquire()) {
    return pjp.proceed();
}
```

If the method body throws A and `close()` throws B, Java `try-with-resources` places B into `A.getSuppressed()` in the standard case. That keeps the primary exception available for the caller to handle.

However, do not turn `try-with-resources` into "cleanup can never fail the target call": if the target returns normally yet close throws an exception, the close failure can still become the error the caller receives.

### 11.3. Controlled suppression of cleanup errors

For **best-effort** cleanup:

```java
Throwable primary = null;
try {
    return pjp.proceed();
} catch (Throwable error) {
    primary = error;
    throw error;
} finally {
    try {
        bestEffortResource.close();
    } catch (Exception cleanupFailure) {
        if (primary != null && primary != cleanupFailure) {
            primary.addSuppressed(cleanupFailure);
        } else {
            // Choose an explicit policy when the target returned normally.
            // For example, record telemetry via a safe non-throwing channel.
        }
    }
}
```

This is an **illustrative snippet** assuming `bestEffortResource` was created in an outer scope. Define a policy for errors from loggers/telemetry and from `Error` during cleanup. Do not abuse `catch(Throwable)` to swallow fatal errors; if releasing the resource is critical, propagate and retain cause/suppressed information.

### 11.4. Whose resource are you closing?

| Resource | Typical owner | Custom aspect action |
| --- | --- | --- |
| Lease/temporary handle created per invocation by the aspect | The aspect itself | Close within the advice's scope. |
| File/InputStream/socket opened by a custom component | The opening component | Close in the proper place, matching lifecycle to the use case. |
| JDBC connection managed by `JdbcTemplate`/transaction manager | Spring JDBC/Transaction infrastructure | **Do not** close manually when a method advice exits. |
| Transaction's JPA EntityManager | Persistence/transaction infrastructure | **Do not** call `close()` arbitrarily inside a custom aspect. |
| SecurityContext in a Servlet request | Spring Security filter/security framework | Do not call `clearContext()` unconditionally in service advice. |
| MDC key temporarily set by the aspect | The aspect | Restore the previous key; do not delete other keys. |
| Reactor Context of a reactive chain | Reactor subscription/context operators | Manage via reactive lifecycle; do not assume a ThreadLocal context spans all signals. |

## 12. Future, @Async, and reactive: cleaning up along the real lifecycle

### 12.1. CompletableFuture

Suppose a service is:

```java
public CompletableFuture<String> loadAsync(String id) {
    return remoteCallAsync(id);
}
```

A synchronous Spring `@Around` will observe `pjp.proceed()` **returning `CompletableFuture` very quickly**. `finally` runs right after the wrapper is returned from the target invocation, **before the asynchronous computation actually completes**.

If the resource is only needed while **creating/scheduling** the future, cleanup in `finally` may be right. If the async task still uses that resource, closing immediately is **too early**.

You can attach a completion callback to the future when the contract permits:

```java
CompletableFuture<String> future = serviceOperation();
future.whenComplete((value, error) -> {
    // Clean up the owned resource once the future completes.
});
```

This is an illustrative snippet. The callback may run on another thread or immediately if already completed; resource ownership needs thread safety, cancellation semantics, and an error policy. With Spring `@Async`, async proxy interceptors may dispatch the target/advice to an executor thread; check advisor ordering and execution threads before deciding context/cleanup scope.

**Do not set a caller's `ThreadLocal` and expect it to appear automatically on the worker thread**. When context must be propagated, use a Spring `TaskDecorator` suited to the specific executor and context; for `SecurityContext`, use Spring Security's context propagation utilities.

### 12.2. Mono / Flux

A method returning a reactive publisher:

```java
public Mono<String> findReactive(String id) {
    return repository.find(id);
}
```

This illustrative snippet requires Reactor/Spring reactive dependencies and a real repository. With lazy publishers, synchronous `@Around` wraps only **the moment the publisher object is returned**, not subscription, cancellation, or terminal signals.

When a resource belongs to the subscription lifecycle, use Reactor `using`/`usingWhen` or `doFinally` with the appropriate `SignalType`; these APIs handle complete/error/cancel branches along the reactive lifecycle. Never use synchronous `try/finally` to close a connection that the publisher only uses **after** subscription.

### 12.3. Difference between synchronous exceptions and async exceptions

If `pjp.proceed()` throws immediately, `@Around`'s `catch/finally` sees a synchronous exception. If it returns a `Future` normally and the future completes exceptionally later, synchronous advice **does not receive that exceptional exit** via `@AfterThrowing` on the wrapper-returning method. To measure async failures, observe future completion or reactive error signals using the appropriate API.

## 13. Spring Boot: configure sufficiently without interfering with framework lifecycles

In Spring Boot with appropriate AOP auto-configuration, you can register:

```java
@Aspect
@Component
public class CleanupAspect {
    @Around("execution(public * com.example.app..*Service.*(..))")
    public Object cleanup(ProceedingJoinPoint pjp) throws Throwable {
        // Capture context, acquire owned lease, proceed, restore in finally.
        return pjp.proceed();
    }
}
```

This is an **illustrative skeleton** without cleanup logic; packages and imports must be added. `@Aspect` does **not automatically** make a class a Spring bean, so `@Component` must be within component scan or the aspect must be returned from a `@Bean` method.

Several Spring-specific notes:

- Spring Framework Java configuration uses `@EnableAspectJAutoProxy`; Boot typically enables AOP automatically when the right starter is present.
- With JDK proxies, advised methods must be exposed via an interface; with CGLIB, `final` classes/methods cannot be overridden. `private` methods are not Spring AOP proxy entry points.
- `this.innerMethod()` from inside a target bypasses the proxy; Spring creates no extra cleanup scope for it.
- Aspect beans are usually singletons; keep invocation state in **locals**, not in shared mutable fields.
- `@Order` relative to transaction/cache/security/async advisors can place your cleanup scope outside or inside those features. Verify the actual proxy/advisor chain.
- Never call `TransactionSynchronizationManager.clear()` or `SecurityContextHolder.clearContext()` as a "universal cleanup" from a custom business aspect.

Dependencies by Spring Boot major version (pick **one** matching your Boot dependency management):

```gradle
// Spring Boot 3.x
implementation 'org.springframework.boot:spring-boot-starter-aop'
```

```gradle
// Spring Boot 4.x
implementation 'org.springframework.boot:spring-boot-starter-aspectj'
```

Do not include both at the same time hoping to increase interception. Spring AOP proxies and Spring transaction/request security lifecycles must still be understood separately.

## 14. Testing Spring AOP cleanup properly

### 14.1. Why unit tests calling the aspect directly are not enough

`new CleanupAspect(resources).around(fakeProceedingJoinPoint)` can test the advice's Java logic, yet **it does not prove Spring registered the `@Aspect` bean, matched the method execution, created a proxy, or wired the interceptor chain**.

Integration tests must retrieve `TaskService` **from `ApplicationContext`**, invoke through the Spring proxy, verify `AopUtils.isAopProxy(service)`, and assert state/resources after each invocation.

### 14.2. Invariants to assert

For the demo:

1. `service.ok("A")` returns `"ok:A"`; lease closes, context restores.
2. `service.refresh()` completes; lease closes, context restores even for `void`.
3. `service.missing()` returns `null`; lease closes, context restores.
4. `service.fail()` still throws `IllegalStateException("boom")`; lease closes, context restores.
5. `openedCount == closedCount == 4` after four external proxy calls.
6. Caller's `"caller"` remains intact after every method call, not mistakenly wiped by `finally`.
7. If the caller initially has `null`, context returns to `null` after an intercepted call.
8. A raw `new TaskService()` does not trigger Spring advice, so the Spring aspect's resource counter does not increment.
9. If a nested collaborator bean/proxy is added, the inner scope restores the outer scope, and then the outer restores the caller.
10. If an outer aspect short-circuits without calling `proceed()`, inner cleanup is not invoked because the inner aspect owns no resource on that invocation.

### 14.3. Example test assertions

```java
try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
    TaskService service = context.getBean(TaskService.class);
    ProbeResources resources = context.getBean(ProbeResources.class);
    CallContext.set("parent");

    if (!"ok:X".equals(service.ok("X"))) {
        throw new AssertionError("Result changed");
    }
    if (!"parent".equals(CallContext.current())) {
        throw new AssertionError("Parent context lost on normal return");
    }

    service.refresh();
    if (service.missing() != null) {
        throw new AssertionError("Null return changed");
    }

    try {
        service.fail();
        throw new AssertionError("Expected IllegalStateException");
    } catch (IllegalStateException expected) {
        if (!"boom".equals(expected.getMessage())) {
            throw new AssertionError("Wrong original exception", expected);
        }
    }

    if (!"parent".equals(CallContext.current())) {
        throw new AssertionError("Parent context lost on exception");
    }
    if (resources.openedCount() != 4 || resources.closedCount() != 4) {
        throw new AssertionError("Resource lease count mismatch");
    }

    CallContext.set(null);
}
```

This is an **illustrative test snippet** using the demo classes, requiring an import for `AnnotationConfigApplicationContext` and placement in a suitable test/main class; it creates its own context—**do not merge it into `Main`** if you want to preserve section 9.7's stdout. With JUnit, you can use `assertThrows`/`assertEquals` alongside `@SpringJUnitConfig` or `@SpringBootTest`.

### 14.4. Failure injections worth testing additionally

- Resource acquisition throws: context still restores in the outer `finally`.
- Resource close throws after normal target return: close exception is handled/propagated per defined policy.
- Resource close throws while target is throwing: `try-with-resources` preserves the original error and marks the close exception as suppressed.
- Logger/metric callback throws: does not silently lose the target exception/outcome if telemetry is best-effort.
- Two concurrent requests: no shared mutable resource handles or current-context fields on the singleton aspect.
- Async task/thread swap: cleanup belongs to the right thread and lifecycle rather than using fake synchronous assertions.
- Transaction participation: never close Spring-managed resources when a method is merely one step in a broader transaction.

## 15. Common mistakes and how to diagnose them

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Cleanup aspect does not run when service method finishes | Target did not go through Spring proxy, pointcut mismatch, aspect not a bean, or outer short-circuit | Check `AopUtils.isAopProxy`, `@EnableAspectJAutoProxy`, bean registry, and caller path. |
| Cleanup runs only on success | Placed in `@AfterReturning` or after `proceed()` without `finally` | Move to `@After` or `@Around` + `finally` with proper ownership. |
| Request context disappears after a nested service call | Inner aspect called `remove()/clear()` unconditionally | Capture previous and restore in `finally`. |
| Thread pool retains previous request's marker | Missing `finally`/`ThreadLocal.remove()` when no parent existed | Scope per invocation; test thread reuse. |
| Resource close skipped when target throws | Close code placed only after `return pjp.proceed()` | Use `try-with-resources`/`finally`. |
| Caller receives cleanup exception instead of original error | `finally close()` threw on the exceptional-exit path | Use a suppression policy; do not throw from best-effort telemetry. |
| DAO/JPA fails after a service call | Aspect closed a connection/EntityManager managed by a Spring transaction | Remove manual close; use Spring transaction-managed APIs. |
| `@After` printed log yet DB has not committed | Advice sits before transaction completion in the advisor chain | Inspect order and use transaction synchronization when afterCompletion is needed. |
| Security principal lost mid-request | Custom aspect cleared `SecurityContextHolder` | Let Spring Security filters manage it; only restore context owned by this component. |
| Future fails after aspect reported success | Aspect saw only the future wrapper's normal return | Observe future completion. |
| Mono/Flux uses an already-closed resource | Synchronous aspect `finally` closed before subscription | Use Reactor resource lifecycle `using/usingWhen/doFinally`. |
| Nested proxy scopes interleave wrongly | Previous context stored in a singleton aspect field | Use local per-invocation state and restore LIFO. |
| Same resource closed twice | Multiple advice claim ownership, or cleanup is not idempotent | Establish single ownership and manage close contract. |
| `@After` does not run when outer `@Around` returns early | Inner advice was never entered | Cleanup must belong to the layer that acquired the resource; do not expect downstream finally to run. |
| `@After` ran yet business exception changed | Cleanup code threw or swallowed in another advice | Inspect primary/suppressed exceptions and contracts. |

## 16. Practical design workflow

**Step 1 — Identify who owns the resource/context.** Did the custom aspect actually open or set it? If the resource is owned by transaction, security, Servlet, or Reactor infrastructure, pick the corresponding lifecycle API rather than closing or clearing manually.

**Step 2 — Choose the right scope.** Every cleanup must bind to a per-invocation handle or local snapshot: `previous ThreadLocal`, `Lease`, span scope, or trace field key.

**Step 3 — Choose the least powerful advice.** `@After` for completion observation; `@Around` when you need lexical scope setup/teardown and to hold a resource handle. Do not use `@Around` merely to print a log after a method if `@After` suffices.

**Step 4 — Prepare before proceed.** Capture previous context then set temporary state; acquire resources inside a protected `try` so acquisition failures also restore any modified state.

**Step 5 — Preserve the contract.** `return pjp.proceed()` inside `try`; do not alter return types/references or swallow exceptions unless the API/policy allows it. Run `proceed()` once unless retry is explicitly designed.

**Step 6 — Reliable cleanup.** For owned resources, `try-with-resources` or `finally`; restore parent context in an outer `finally`. Define a cleanup failure policy and use suppressed exceptions to keep the root cause.

**Step 7 — Verify nested/concurrent calls.** Never use singleton aspect fields for per-call mutable state. For thread pools, clear `ThreadLocal` when previous is null; for nested scopes, restore previous instead of calling a global clear.

**Step 8 — Check the real lifecycle.** `@Async`/future/reactive subscriptions, transaction completion, and HTTP request/security scopes can outlive one method execution. Attach cleanup to the right hook.

**Step 9 — Lock in with integration tests.** Run through a real Spring proxy, testing return/`void`/`null`/exception, resource counts, parent context restoration, cleanup failure injection, self-calls, and worker-thread behavior where relevant.

## 17. Pre-production checklist

- [ ] Does the aspect have `@Aspect` and Spring bean registration, and is the target a Spring-managed bean?
- [ ] Is Spring AOP enabled and do callers go through the proper JDK/CGLIB proxy?
- [ ] Does the pointcut match the intended service methods without assuming `this.method()` is advised?
- [ ] Have `@After` finally, `@AfterReturning` success-only, and `@AfterThrowing` exception-only been distinguished?
- [ ] Is the resource being cleaned up genuinely **owned by the aspect**, not transaction/security infrastructure?
- [ ] If the advice creates a resource, does it use a local handle and `try-with-resources`/`finally`?
- [ ] If modifying `ThreadLocal`/MDC, is previous snapshotted and restored in `finally`?
- [ ] If previous is null, does the code call `remove()` instead of retaining keys or thread references?
- [ ] Do nested invocations restore context LIFO without `clear()`ing parent context?
- [ ] Are per-invocation `Resource`/`previousContext` values kept out of mutable fields on the singleton aspect?
- [ ] Does cleanup failure have an explicit policy so it neither loses the root exception nor turns a normal return into an off-contract failure?
- [ ] If resource close can throw, have `getSuppressed()`/try-with-resources been accounted for?
- [ ] Are Spring-managed JDBC/JPA connections/entity managers left unclosed by custom `@After`?
- [ ] Are `SecurityContextHolder` and global transaction synchronizations never cleared unconditionally?
- [ ] For future/`@Async`/Reactor, is cleanup attached to completion/terminal lifecycles?
- [ ] Are there real Spring-proxy integration tests for success, `void`, `null`, exception, nested calls, and concurrency?
- [ ] Are audit cleanup logs kept distinct from transaction commits or async business success?
- [ ] Have outer aspects/cache/security advisors that could short-circuit been considered when assigning cleanup ownership?

**Remember:** In Spring AOP, **`@After` is after-finally for a matched method execution**, while **`@Around` + Java `try/finally`/`try-with-resources`** is the clearest pattern when the aspect itself opens a resource or sets temporary context. Clean up **only what you own** and **restore caller state**, without deleting or closing resources managed by transactions, security, or other async/reactive lifecycles. Method completion does not necessarily mean transaction completion or asynchronous computation completion.

## References

- [Spring Framework 6.2 — Declaring Advice: After (Finally) Advice and Around Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html)
- [Spring Framework 6.2 — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html)
- [Spring Framework 6.2 — Proxying Mechanisms and self-invocation](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Spring Framework 6.2 — Resource Synchronization with Transactions](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/tx-resource-synchronization.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Security — SecurityContextHolder and Servlet authentication architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Java — try-with-resources and suppressed exceptions](https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html)

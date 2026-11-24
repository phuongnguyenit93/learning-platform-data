# Limits of Propagating `SecurityContext`, MDC, and Transaction Context Across Threads

## 1. Practical scenario and what to distinguish

An HTTP request entering a Spring Boot application may pass through servlet filters, Spring Security, a controller, and a `@Transactional` service, and then dispatch work to `@Async`, `CompletableFuture`, `ExecutorService`, or a Reactor scheduler. On the request-handling thread, the application can read:

- **`SecurityContext`**: the `Authentication` bound to the executing thread, used to identify the user and enforce authorization checks in Spring Security Servlet.
- **MDC (Mapped Diagnostic Context)**: key–value pairs like `requestId`, `traceId`, and `tenantId` included in log lines for correlation.
- **Transaction context**: resources, state, and transaction synchronizations managed by `PlatformTransactionManager`; with JDBC/JPA these are typically thread-bound.

After switching to another thread, these three **do not follow along automatically**. Typical symptoms are `SecurityContextHolder.getContext().getAuthentication()` missing request details, `MDC.get("requestId")` returning `null`, or database operations running outside the caller's transaction.

The core question is not merely “how do I copy context?” You must ask: **which context is allowed to propagate, via what mechanism, how long should it live, and is it even safe to use on another thread?** Security context and MDC can be passed to bounded tasks under explicit policies. An active JDBC/JPA transaction **cannot be safely handed off simply by copying thread-local variables**.

Article scope: Spring Boot 3.3.x, Spring Framework 6.1.x, Spring Security 6.x, Java 17+; distinguishing the Servlet stack from Reactive/WebFlux. Examples are labeled **standalone** or **integration snippet** so illustrative fragments are not mistaken for complete applications.

## 2. Foundational model: physical threads vs. logical context

`ThreadLocal<T>` stores a value per **current thread**. Two threads reading the same `ThreadLocal` variable receive different values:

```text
Request R-42
    |
    v
Thread servlet-1
    SecurityContextHolder = user: alice
    MDC["requestId"]     = R-42
    JDBC transaction     = tx-A / connection-A
    |
    +---- executor.submit(task) ----> Thread pool-3
                                      SecurityContext = NOT auto-propagated
                                      MDC             = NOT auto-propagated
                                      tx-A            = NOT auto-propagated
```

A request is a **logical unit**; a thread is an **execution unit**. In synchronous Servlets, they usually align during primary handling. During asynchronous execution, a job may run on another thread, the original thread is reused for another request, and a reactive pipeline can switch across multiple threads within a single subscription's lifetime.

| Context | Common mechanism in Servlet/imperative | Across threads by default | Appropriate handling |
| --- | --- | --- | --- |
| Security | `SecurityContextHolder` defaults to `MODE_THREADLOCAL` | Unreliable | Spring Security delegating wrappers or passing controlled identity data |
| MDC | Logging frameworks typically keep a per-thread map | Unreliable | Snapshot MDC on submit, set on worker, restore in `finally` |
| JDBC/JPA Transaction | `TransactionSynchronizationManager` binds resources/transaction state to the thread | **Never propagated** | Deliberately open a new transaction on the worker, or keep work synchronous in the original transaction |
| Security in WebFlux | Reactor `Context` via `ReactiveSecurityContextHolder` | Preserved within the same reactive chain/subscription | Stay within the reactive pipeline and `Context`; avoid relying on Servlet `ThreadLocal` |
| Reactive transaction | Reactor `Context` with `ReactiveTransactionManager` | Preserved within the same reactive subscription | Keep reactive chains and transaction operators scoped properly |
| Tracing/observation | Micrometer/observability context + matching bridge | Depends on configuration/instrumentation | Use registered context propagation; do not mistake it for DB transaction handoff |

A common design mistake is lumping all three into a single “request context” and copying everything. Each context has different origins, sensitivity, and lifecycle rules.

## 3. Java 17: deterministic `ThreadLocal` experiment

The following example runs **standalone on JDK 17+**; it demonstrates that request values do not appear automatically on workers, and how to scope/restore a snapshot for one task.

**File `ThreadBoundaryDemo.java`:**

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ThreadBoundaryDemo {
    private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            REQUEST_ID.set("req-42");
            System.out.println("caller: " + REQUEST_ID.get());

            String before = pool.submit(REQUEST_ID::get).get();
            System.out.println("worker before: " + before);

            String captured = REQUEST_ID.get(); // snapshot before submitting
            pool.submit(() -> {
                String previous = REQUEST_ID.get();
                try {
                    REQUEST_ID.set(captured);
                    System.out.println("worker during: " + REQUEST_ID.get());
                } finally {
                    if (previous == null) {
                        REQUEST_ID.remove();
                    } else {
                        REQUEST_ID.set(previous);
                    }
                }
            }).get();

            String after = pool.submit(REQUEST_ID::get).get();
            System.out.println("worker after: " + after);
        } finally {
            REQUEST_ID.remove();
            pool.shutdown();
        }
    }
}
```

Compile and run:

```bash
javac ThreadBoundaryDemo.java
java ThreadBoundaryDemo
```

**Exact stdout:**

```text
caller: req-42
worker before: null
worker during: req-42
worker after: null
```

`newSingleThreadExecutor()` reuses the same worker thread across all three sequential tasks. The first task proves there is no automatic inheritance; the second installs the snapshot only for task execution; the third proves cleanup succeeded. Omitting `finally` lets a pooled thread retain data from a previous request so a later request reads stale values—especially dangerous with user-specific data.

This is only a simulation to show the boundary; in Spring Security applications, **never use a homegrown `ThreadLocal` in place of the security framework**.

## 4. `SecurityContext` in Spring Security Servlet

In the Servlet model, `SecurityContextHolder` provides access to the current context:

```java
Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();
```

`Authentication` can represent an authenticated user, anonymous authentication, or `null`, depending on filter-chain position and configuration. Hence “empty context” does not strictly mean “the request is definitely unauthenticated.” Only make authorization decisions through configured security filters/method security—never infer permissions from MDC or thread names.

### 4.1. What happens with `@Async`/executors?

With the default `MODE_THREADLOCAL` strategy, Spring Security binds the context to the current thread. `new Thread(...)`, `CompletableFuture.supplyAsync(...)`, or an ordinary `Executor` runs tasks on another thread; **you should not expect the Servlet context to transfer intact**.

Avoid this deceptive shortcut:

```java
// Should not be chosen as a general thread-pool solution:
SecurityContextHolder.setStrategyName(
        SecurityContextHolder.MODE_INHERITABLETHREADLOCAL);
```

`MODE_INHERITABLETHREADLOCAL` only inherits values when creating **child threads**; pooled threads are typically created before requests arrive and reused across requests. It provides no per-submission snapshot semantics, risking cross-user context leakage or data outliving requests. `MODE_GLOBAL` is even more dangerous for multi-user web apps because it shares one context across the entire JVM.

### 4.2. Per-task propagation using Spring Security mechanisms

Integration snippet for the Servlet stack, executed where the caller's `SecurityContext` is already populated:

```java
import java.util.concurrent.Executor;

import org.springframework.security.concurrent.DelegatingSecurityContextExecutor;

// delegate is the real Executor, such as an application-managed thread pool.
Executor securityAware = new DelegatingSecurityContextExecutor(delegate);

securityAware.execute(() -> securedService.process());
```

The constructor **that does not take a fixed `SecurityContext`** captures the current context upon each task submission, wraps the task, sets the context on the worker, and clears it after the task finishes. Passing a fixed `SecurityContext` to the other constructor makes every task run under that same identity—only suitable for specialized system jobs, not a general web-user executor.

Spring Security provides matching adapters: `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextCallable`, `DelegatingSecurityContextExecutor`, `DelegatingSecurityContextExecutorService`, `DelegatingSecurityContextAsyncTaskExecutor`, etc. Pick the adapter matching your API and execution path.

**Limits:** The wrapper helps propagate `SecurityContext`; it **does not automatically propagate MDC, JDBC/JPA transactions, request attributes, or other `ThreadLocal`s**. Context captured at submission time can become stale by the time the task runs. Never carry request credentials blindly into long-lived jobs, durable queues, or external services.

### 4.3. `@Async` needs the right executor and proxy invocation

`@Async` works through a Spring proxy (by default). An `@Async` method must be called from **another bean via the proxy** to dispatch onto an executor; calling `this.someAsyncMethod()` inside the same bean normally bypasses interception.

If you declare:

```java
@Async("contextAwareExecutor")
public CompletableFuture<String> fetchAsync() {
    Authentication a =
            SecurityContextHolder.getContext().getAuthentication();
    String username = a == null ? "none" : a.getName();
    return CompletableFuture.completedFuture(username);
}
```

then `contextAwareExecutor` must be an `Executor`/`AsyncTaskExecutor` configured to propagate security context. The method above is an **integration snippet inside a Spring bean**, not standalone code: it requires `@EnableAsync`, Spring Security, and the matching executor bean.

Special note: Spring MVC includes security-context integration for certain Servlet async mechanisms, such as MVC-managed `Callable`s. **Do not generalize that to every `CompletableFuture`, `DeferredResult`, manual thread, or `@Async`**; each execution path has its own contract.

## 5. MDC: copy **logging metadata** and always restore worker state

In Spring Boot Servlet apps using SLF4J with default Logback, `MDC.put("requestId", ...)` usually binds entries to the current thread:

```java
MDC.put("requestId", "req-42");
try {
    // logs on the current thread can read requestId
} finally {
    MDC.remove("requestId");
}
```

When threads switch, the MDC map does not transfer reliably on its own. MDC holds **logging metadata**, not authentication or transaction authority. To propagate it, snapshot `MDC.getCopyOfContextMap()` at **submission time**, apply it on the worker during execution, and restore the prior map inside `finally`.

`TaskDecorator` example for Spring 6.1+:

```java
import java.util.Map;

import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

public final class MdcTaskDecorator implements TaskDecorator {
    @Override
    public Runnable decorate(Runnable task) {
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                restore(captured);
                task.run();
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

This is a **syntactically standalone class**, though it requires `slf4j-api` and `spring-core` on the classpath. `TaskDecorator` only takes effect when registered on the executor actually being used. `getCopyOfContextMap()` creates a copy of the map; never share a single mutable map across concurrent requests. `finally` executes even if the task throws an exception.

If your application integrates Micrometer Context Propagation with matching `ThreadLocalAccessor`s, consider `org.springframework.core.task.support.ContextPropagatingTaskDecorator`. It helps propagate **registered** observability/logging contexts, though you cannot expect it to copy arbitrary `ThreadLocal`s—and it certainly cannot make database transactions transferable.

Never place access tokens, passwords, session secrets, sensitive identifiers, or `Authentication` objects into MDC. Above all, **never use MDC for authorization checks**. If `requestId` comes from an external HTTP header, sanitize and bound its length to prevent log injection and excessive label cardinality.

## 6. Combined MDC and Security pattern for `@Async` in Spring Boot

Goal of this pattern: every task submitted to `contextAwareExecutor` receives the caller's **SecurityContext** and **MDC snapshot**; transactions are not propagated.

**`AsyncContextConfiguration.java`** — integration snippet for a Spring Boot app with `spring-boot-starter-security`:

```java
package com.example.web;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncContextConfiguration {

    @Bean("mdcDelegateExecutor")
    ThreadPoolTaskExecutor mdcDelegateExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("background-");
        executor.setTaskDecorator(new MdcTaskDecorator());
        return executor;
    }

    @Bean("contextAwareExecutor")
    AsyncTaskExecutor contextAwareExecutor(
            @Qualifier("mdcDelegateExecutor") ThreadPoolTaskExecutor delegate) {
        return new DelegatingSecurityContextAsyncTaskExecutor(delegate);
    }
}
```

`ThreadPoolTaskExecutor` is a Spring bean so the container manages initialization and shutdown of the delegate bean; avoid manually managing multiple overlapping executors. Place `MdcTaskDecorator` from the previous section in the same `com.example.web` package. On submission, the Spring Security adapter wraps the task while the delegate applies the MDC decorator. Both preserve cleanup rules after task completion.

**`AsyncAuditService.java`** — another bean called through a Spring proxy:

```java
package com.example.web;

import java.util.concurrent.CompletableFuture;

import org.slf4j.MDC;
import org.springframework.scheduling.annotation.Async;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class AsyncAuditService {

    @Async("contextAwareExecutor")
    public CompletableFuture<String> describeCaller() {
        Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();

        String username = auth == null ? "none" : auth.getName();
        String requestId = MDC.get("requestId");

        return CompletableFuture.completedFuture(
                "user=" + username + ", requestId=" + requestId);
    }
}
```

When **another bean** invokes `asyncAuditService.describeCaller()` inside an authenticated request with MDC populated, the principal and request ID will be available inside the task provided the entire path uses the executor above. Exact output depends on live authentication and MDC; no fixed stdout is assumed for an unspecified request.

This integration snippet requires Spring Boot web/async/security and logging in the project; it **does not preserve the caller's transaction**. Never place `@Transactional` on the configuration just to try copying context.

**When is copying unnecessary?** If the background task only needs immutable `orderId`, stable `userId`, and `correlationId`, it is usually cleaner to pass those three immutable values as explicit parameters. That avoids spreading full request authority into background jobs with longer lifecycles.

## 7. Imperative transaction context: the boundary you MUST NOT cross by copying

Spring Framework uses `TransactionSynchronizationManager` to manage **thread-bound** resources and transaction synchronizations in imperative models like JDBC/Hibernate:

```text
Thread request-1:
@Transactional boundary (PlatformTransactionManager)
    -> Connection / EntityManager bound to thread-1
    -> save(order)
    -> executor.execute(...)
         |
         v
       Thread worker-7:
         Does NOT automatically have Connection / EntityManager / original tx
    -> original transaction commits or rolls back on thread-1
```

`@Transactional` on a request service **does not make the transaction follow** tasks dispatched to another thread. If `worker-7` calls a repository, that operation may run in a **different transaction** (if the repository/worker method starts its own) or without a transaction, depending on APIs. Consequences:

- The worker may miss uncommitted changes under typical isolation levels and see stale state.
- The task may run **before the caller commits** or continue **after the caller rolls back**.
- Failures in the task do not automatically roll back the caller's transaction; caller rollbacks do not undo commits made by the worker.
- `EntityManager`/JPA persistence contexts and JDBC `Connection`s are generally unsafe for concurrent multi-thread access.

**Do not do this:**

```java
// Wrong direction: copying TransactionSynchronizationManager resources/objects
// or passing the request's Connection/EntityManager to a worker.
executor.execute(() -> useSameEntityManagerAcrossThreads());
```

`TransactionSynchronizationManager.bindResource(...)` is infrastructure SPI for transaction/resource managers; manually copying thread-bound resources onto a worker does not create a valid distributed transaction and risks concurrent access bugs, broken commits/rollbacks, and connection leaks. Never use security/MDC propagation to “work around” this.

### 7.1. Need a transaction on the worker? Open a **new transaction on the worker**

Integration snippet using a dedicated service bean; `@Async` and `@Transactional` apply through Spring proxies with an appropriate `PlatformTransactionManager`:

```java
package com.example.web;

import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AsyncDatabaseService {

    private final AuditRepository auditRepository;

    public AsyncDatabaseService(AuditRepository auditRepository) {
        this.auditRepository = auditRepository;
    }

    @Async("contextAwareExecutor")
    @Transactional
    public CompletableFuture<Void> saveAudit(AuditEntry entry) {
        auditRepository.save(entry);
        return CompletableFuture.completedFuture(null);
    }
}
```

**Integration snippet, not a self-contained app**: `AuditRepository`/`AuditEntry` are domain types your application must define. `@EnableAsync` and transaction management must be enabled, and calls must go through proxies. The transaction in `saveAudit(...)` is created **on the thread executing the method**, independent of the caller's transaction rather than “continuing the original transaction” with shared resources/commit. `Propagation.REQUIRED` on the worker can only join a transaction bound to **the worker itself**—it cannot see a transaction active on the caller thread.

For explicit transaction control, run `transactionTemplate.execute(status -> ...)` **inside the worker** using a properly configured `TransactionTemplate` and transaction manager. Never start a transaction on the request thread and hand its connection off to a worker.

### 7.2. When work must run only after commit

Do not trigger external side effects before database changes are durable. Common approaches:

1. **Synchronous:** keep mutations requiring strict atomicity inside one `@Transactional` service on the same thread.
2. **Post-commit, same process:** `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` fires after transaction commit. If async execution is needed, hand off to an executor after this point; worker DB writes may need a **new transaction**. In-memory events are not durable queues: the process could crash after commit before the task finishes.
3. **Reliability across restarts:** transactional outbox—inside the original transaction write both business state and an outbox record; a worker reads committed outbox entries and retries independently. Make consumers idempotent since delivery may be at-least-once.

Do not assume `@TransactionalEventListener(AFTER_COMMIT)` means “every DB operation inside the callback automatically gets a fresh transaction.” Right after commit, transaction resources may still be briefly bound during cleanup; if the callback needs durable DB writes, explicitly start a new transaction—such as via a proxied `@Transactional(propagation = REQUIRES_NEW)` service or on the worker itself.

## 8. WebFlux: Reactor `Context` is not `ThreadLocal`

In WebFlux, a request is not guaranteed to stay on one thread from start to finish. `publishOn(...)` switches the thread for downstream signals; `subscribeOn(...)` affects where subscription/source runs; reactive pipelines can hop schedulers while remaining a single **logical subscription**.

Reactor provides `Context`/`ContextView` attached to the **Subscriber**, not the thread. This underpins Spring Security Reactive and reactive transactions.

### 8.1. Reactor Context demo across `publishOn`

This is a **Java example using reactor-core**; you can place it in `main` of a project with Reactor dependencies (such as `spring-boot-starter-webflux`):

```java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.util.context.Context;

public class ReactorContextDemo {

    public static void main(String[] args) {
        Mono<String> pipeline = Mono.deferContextual(view ->
                        Mono.just(view.getOrDefault("requestId", "missing")))
                .publishOn(Schedulers.parallel())
                .contextWrite(Context.of("requestId", "req-42"));

        System.out.println(pipeline.block());
    }
}
```

**Stdout:**

```text
req-42
```

`contextWrite(...)` attaches data to the subscription for upstream operators; `deferContextual(...)` reads it upon subscription. `publishOn(...)` switches threads, yet Reactor context travels with the pipeline/subscription. Do not infer that `ThreadLocal` values inside `Mono` are automatically restored: that is a separate mechanism.

**Boundary caveat:** manually calling `subscribe()` inside a method to launch an independent subscription, jumping to a plain `ExecutorService`, or leaving the reactive pipeline will not automatically preserve the caller's Reactor Context. Nor does Context automatically turn into HTTP headers or message-broker metadata.

### 8.2. Reactive SecurityContext

In Spring Security WebFlux, access identity via `ReactiveSecurityContextHolder`:

```java
import reactor.core.publisher.Mono;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

Mono<String> currentUsername =
        ReactiveSecurityContextHolder.getContext()
                .flatMap(context ->
                        Mono.justOrEmpty(context.getAuthentication()))
                .map(Authentication::getName)
                .defaultIfEmpty("anonymous");
```

This **integration snippet** must run inside a Spring Security-configured WebFlux request or a subscription populated with security context. `ReactiveSecurityContextHolder` reads from Reactor Context; do not replace it with thread-based `SecurityContextHolder.getContext()` in genuinely reactive code. In tests, populate Authentication on a chain via:

```java
Mono<String> secured = currentUsername.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(authentication));
```

`authentication` is an `Authentication` instance supplied by the test/app, not predefined in the snippet. A reactive subscription's context does not imply a long-lived auth session for unrelated background jobs.

### 8.3. Reactive transactions differ from JDBC/JPA transactions

With `ReactiveTransactionManager` (for example, an R2DBC transaction manager), Spring carries transaction state via **Reactor Context**. Data-access operations joining the same transaction must participate in the same reactive pipeline/subscription; reactive `@Transactional` methods must return reactive types like `Mono`/`Flux`, or use `TransactionalOperator`.

With `PlatformTransactionManager` (JDBC/JPA), state is thread-bound. **You cannot use Reactor Context to make a JDBC transaction reactive**, nor can you use Micrometer's `ThreadLocal` propagation to carry one thread's `Connection`/`EntityManager` over to another thread.

Comparison examples:

| Pattern | Conclusion |
| --- | --- |
| `Mono.defer(...).publishOn(...).contextWrite(...)` | Reactor Context remains visible across scheduler hops within the same subscription |
| Reactive repository inside `TransactionalOperator` | Joins the reactive transaction managed by the operator |
| JDBC/JPA `@Transactional` calling `CompletableFuture.supplyAsync(...)` | Task does not inherit the caller's JDBC/JPA transaction |
| Calling `.block()` on a reactive op and assuming it joins the imperative transaction | No automatic guarantee; introduces subscription and thread boundaries, risking event-loop blocking |
| Calling a new `subscribe()` inside a transactional pipeline | Starts an independent subscription; do not expect it to share the original chain's transaction/context |

In WebFlux, avoid blocking the event loop with JDBC or `.block()` during request handling. When forced to call a blocking API, consider `Schedulers.boundedElastic()` with a **separate, explicitly scoped transaction**; do not confuse changing schedulers with transferring transactions.

## 9. MDC and observability in Reactive/async: bridges have limits

SLF4J MDC is usually thread-bound, whereas Reactor Context is subscription-bound. Therefore:

```text
Reactor Context["requestId"] = req-42
               |
               +--> publishOn(thread B)
                         |
                         +--> MDC.get("requestId") may be null
```

`contextWrite(...)` does not guarantee `MDC.get(...)` sees the value. There are three approaches:

- Inside an operator with context access, **read `ContextView`** and set MDC locally around the exact log statement; use `try/finally` or `MDC.putCloseable` to clean up immediately without polluting event-loop threads.
- With Micrometer Context Propagation: register matching accessors to capture/restore context across supported boundaries; enable Reactor automatic context propagation when needed. It only restores `ThreadLocal`s known to registered accessors under the configured mode.
- Use Micrometer Tracing/Observation and proper instrumentation so trace/span correlation flows across pipelines via supported mechanisms. Verify log patterns and versions rather than assuming MDC keys exist without setup.

Spring Boot 3.3 offers the property:

```properties
# Only use when the project needs it and dependencies support Context Propagation
spring.reactor.context-propagation=auto
```

This property enables automatic Reactor context propagation **when supporting infrastructure is present**; it does not make every arbitrary `ThreadLocal` transferable, nor does it transfer JDBC/JPA transactions. For `@Async` in Spring Boot 3.3, propagating observation/logging context across custom executors still needs a `TaskDecorator`/capture mechanism; do not assume `spring.reactor.context-propagation=auto` handles standard thread pools.

A practical rule: propagate only **essential correlation metadata**. If a background job outlives the request, give the job its own correlation linked by ID to the originating request rather than keeping full MDC and `SecurityContext` around indefinitely.

## 10. Boundary table by execution API

| API/scenario | Switches thread? | Servlet Security | MDC | Imperative transaction |
| --- | --- | --- | --- | --- |
| Controller → sync service in same call stack | Normally no | Retained on current thread/request | Retained on thread | Can join Spring-managed transaction |
| `new Thread(...).start()` | Yes | Not by default | Not by default | No |
| `ExecutorService.submit(...)` | Usually yes | Not by default; needs per-task wrapper | Not by default; needs decorator/snapshot | No |
| `CompletableFuture.supplyAsync(...)` without executor | May run on common pool | Not by default | Not by default | No |
| `@Async` on bean called through proxy | Yes | Configure security-aware executor if needed | Needs matching decorator/propagation | Caller transaction does not follow; async method may start its own |
| `parallelStream()` | Usually uses other workers | Not by default | Not by default | No; avoid thread-bound DB transactions inside parallel streams |
| Spring MVC async `Callable` managed by MVC | Yes | Specific Spring Security integration when configured | Do not assume propagated | Do not assume propagated |
| Spring WebFlux `publishOn` in same subscription | Yes | Use `ReactiveSecurityContextHolder`/Reactor Context | MDC needs bridge | Reactive transaction can continue in chain; JDBC transaction does not follow |
| Message queue/HTTP call to another process | Different process | Cannot pass Java `ThreadLocal`/`SecurityContext` objects | Send correlation/tracing metadata per protocol | Cannot transfer local DB transaction; use messaging/outbox/separate transactions |

This is the **default boundary map and contract limit**. Libraries, filters, `TaskDecorator`s, tracing agents, or app configs may add specific propagation; verify the exact mechanism before relying on it.

## 11. Request–async–database cycle: three classic bugs

Suppose `POST /orders` belongs to user `alice`, has `MDC["requestId"]="R-42"`, and the service saves an order inside transaction `tx-A`.

**Bug 1: losing user identity on the worker**

```text
Controller on servlet thread: alice
    -> @Async worker: Authentication is null / different request
    -> @PreAuthorize(...) on worker may fail
```

Solution: wrap the executor with `SecurityContext` propagation if the task **truly needs the caller's privileges**. For long-running jobs, use an appropriate worker identity/authorization model and pass immutable inputs rather than holding expired session privileges unchecked.

**Bug 2: unlinked or mixed-up logs across requests**

```text
servlet-1: requestId=R-42
pool-3:    requestId=null
pool-3:    requestId=R-10 (if prior task forgot to clear)
```

Solution: snapshot the map per task, install/restore inside `finally`, and verify MDC cleanup after execution including error paths. For queues/outboxes, store correlation IDs as explicit business metadata.

**Bug 3: task reads/writes DB before commit**

```text
tx-A: save(order=123)
      submit(asyncSendOrder123)
pool-3: query(order=123)    <-- may not see the record yet
tx-A: rollback             <-- task may still have sent notification
```

Solution: never launch external side effects just because `save()` ran inside an uncommitted transaction. Choose `AFTER_COMMIT`, a fresh worker transaction when DB access is needed, or an outbox for reliable delivery. **Security/MDC propagation does not solve transaction atomicity.**

## 12. Capture timing, lifecycle, safety, and performance

A sound propagation design must answer:

1. **When to capture?** Typically at task submission time, while the request context is valid. If the task queues for a long time, context/claims may expire before execution.
2. **What to pass?** Pass minimal values (`correlationId`, `actorId`, immutable business data); pass full `SecurityContext` only where the security design explicitly calls for it.
3. **When to restore?** At task start; restore the worker's prior state in `finally`, including on cancellation or exceptions. Cleaning up at request/filter boundaries is equally critical.
4. **What about child tasks?** Task A being wrapped does not mean a subtask B launched by A via `supplyAsync(...)` is wrapped. Every executor/subscription/process boundary must be handled deliberately.
5. **What about retries and pooling?** Pooled workers are reused; prevent leaking MDC or identities across users. Retries minutes later should use explicit inputs, not stale snapshots from an ended request.
6. **Performance impact?** Capturing/copying contexts has cost; avoid heavy decorators on millions of tiny micro-tasks if unnecessary. Keep MDC and trace attribute cardinality reasonable.
7. **What about virtual threads?** Java 21 virtual threads still have their own `ThreadLocal`s; virtual threads do not magically propagate arbitrary caller context across threads. Never tie correctness to thread names or assume requests stay pinned to one thread.

`ThreadLocal`/MDC are neither inter-service communication channels nor long-term business state stores. Use headers/tracing conventions, message metadata, database/outboxes, and explicit data objects as appropriate.

## 13. How to verify in a Spring Boot project

You can log checks on both the **request thread** and the **worker thread** with a small diagnostic helper:

```java
import org.slf4j.MDC;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public final class ContextProbe {
    private ContextProbe() { }

    public static void inspect(String label) {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();
        String username = authentication == null
                ? "<none>" : authentication.getName();

        System.out.printf(
                "%s | thread=%s | user=%s | requestId=%s | tx=%s%n",
                label,
                Thread.currentThread().getName(),
                username,
                MDC.get("requestId"),
                TransactionSynchronizationManager.isActualTransactionActive());
    }
}
```

**Integration snippet** requiring Spring Security, SLF4J, and Spring transaction on the classpath. Use:

```java
ContextProbe.inspect("before-submit");
asyncService.run(...); // via Spring proxy and configured executor
```

and invoke `ContextProbe.inspect("inside-worker")` inside the async method. There is no fixed stdout because values depend on the live request/executor/transaction. `isActualTransactionActive()` reports the transaction status Spring has bound **to the inspected thread**; it does not prove two threads share the same transaction.

A worthwhile testing checklist:

- **Default:** An unwrapped executor must not be assumed to see the caller's principal/requestId; the worker must not see the request thread's imperative transaction.
- **With wrapper:** Send two requests with two different users and two `requestId`s through a reused pool, using controlled synchronization if needed; ensure each task sees only its own user/`requestId`.
- **No leaks:** After each task, the worker retains no `requestId`/user from the prior task; test exception and cancellation paths too.
- **Transactions:** Inside a `@Transactional` request, inspect transaction status; inside the worker inspect separately. Explicitly test the worker opening its own transaction and caller rollback scenarios.
- **Post-commit:** Test commit, rollback, and process restart; if durability is required, test outbox and retry/idempotency.
- **Reactive:** On a single pipeline with `contextWrite`, test `publishOn`/`subscribeOn` and read `deferContextual`; spawn a separate `subscribe()` to observe the boundary; with reactive transactions, verify repository operations execute within the right subscription.

Never use a log showing “the same thread name” as proof context propagated properly; under concurrency, thread names carry no user identity.

## 14. Misconceptions that lead to serious bugs

**“`@Async` copies all contexts automatically.”** False. Async selects an executor and runs the method on another thread. Propagation requires adapters/decorators compatible with each context type.

**“Having `DelegatingSecurityContextAsyncTaskExecutor` covers MDC and transactions too.”** False. The Spring Security adapter handles security context; MDC needs its own propagation, and imperative transactions need their own boundaries.

**“`MODE_INHERITABLETHREADLOCAL` is safe with thread pools.”** False. It only inherits upon thread creation and provides no per-task snapshot/cleanup semantics for existing pooled threads.

**“Copying `TransactionSynchronizationManager` or JDBC Connections transfers transactions.”** Wrong and dangerous: resources have lifecycle, ownership, and thread-safety constraints; transaction managers must create/manage transactions on the owning thread/scope.

**“Putting `@Transactional` outside `CompletableFuture` makes the whole future share the transaction.”** False. Imperative transactions bind to threads and interceptor scopes; futures executing on other threads have separate lifecycles.

**“Reactor Context is a copy of MDC.”** False. Reactor Context attaches to subscribers; MDC is usually thread-bound. Getting MDC into logs requires local bridging or configured context propagation.

**“`publishOn` always drops Reactive SecurityContext/transactions.”** False if staying within the same reactive subscription using Reactor Context. Starting a new `subscribe()` or jumping to blocking APIs/Executors outside the chain is a different boundary.

**“Putting user/token in MDC is a way to authorize.”** False. MDC is for logging; rely on controlled authentication/authorization mechanisms and avoid leaking secrets.

## 15. Self-check questions and how to choose an approach

1. A `@Transactional` service launches `CompletableFuture.supplyAsync(...)` to write to the same database. Why isn't the future guaranteed to see uncommitted data, and why doesn't a failure in the future automatically roll back the original transaction?
2. Between `DelegatingSecurityContextExecutor` and `MdcTaskDecorator`, which tool handles which context? What else is needed if the task also needs a database transaction?
3. If two requests sequentially reuse the same worker thread, why can omitting `finally` stamp the first request's ID onto the second request's logs?
4. In WebFlux, why is `ReactiveSecurityContextHolder.getContext()` preferable to reading `SecurityContextHolder` directly? What changes if you call a fresh `subscribe()`?
5. For sending a notification after an order is successfully placed, when is `@TransactionalEventListener(AFTER_COMMIT)` appropriate and when is a transactional outbox needed?
6. Even with `spring.reactor.context-propagation=auto`, why must you still **not** copy a JDBC transaction onto another scheduler?

Choosing the right solution by goal:

| Need | Preferred solution |
| --- | --- |
| Include request ID in executor logs | MDC snapshot/decorator with cleanup, or configured observability propagation |
| Run `@Async` with the current request's identity (short, controlled task) | `DelegatingSecurityContextAsyncTaskExecutor` + proper proxy call |
| Long-lived job only needing to know who requested it | Pass minimal `actorId`/claims as immutable inputs; authorize per job policy |
| Update DB inside an async worker | `@Transactional`/`TransactionTemplate` opening a separate transaction **inside the worker** |
| Side effect must happen after DB commit succeeds | Post-commit event, or transactional outbox when durability and retries are required |
| WebFlux security/reactive DB | Reactor Context + `ReactiveSecurityContextHolder` + `ReactiveTransactionManager`/`TransactionalOperator` |
| Calling another service/process | Intentional HTTP headers/tracing context or message metadata; never pass Java `ThreadLocal` objects |

**Key takeaway:** switching threads can drop thread-bound state, yet **not every context should be transferred**. For security and MDC, apply scoped capture/cleanup at the right boundary. For imperative transactions, redesign the transaction boundary; for WebFlux, rely on Reactor Context and subscription scope.

### Official documentation

- Spring Security, Concurrency Support (Servlet): https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html
- Spring Security, reactive method security and Reactor Context: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html
- Spring Framework 6.1, `TransactionSynchronizationManager`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html
- Spring Framework, declarative transaction implementation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework 6.1, `ContextPropagatingTaskDecorator`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html
- Spring Boot 3.3, application properties (`spring.reactor.context-propagation`): https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Project Reactor, Context Propagation: https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html
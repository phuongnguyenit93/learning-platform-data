# `@Async`, Executors, and Propagating `SecurityContext` Within Proper Scope

> **Topic:** Spring Security – authorization · **Group:** Proxies and Transactions. This lesson explains how Spring `@Async` changes execution threads, why `SecurityContext` does not automatically follow executor threads, and how to pass identity/permissions to tasks **for the right person, at the right time, in the right scope** without leaking across tasks. Primary scope: Spring Boot Servlet, Spring Security method security, Java 17+.

## 1. What Will You Master?

After this lesson, you will be able to:

1. Explain the relationship among `SecurityContextHolder`, `ThreadLocal`, `@Async`, Spring proxies, and thread pools.
2. Choose `DelegatingSecurityContextAsyncTaskExecutor`, `DelegatingSecurityContextExecutor`, `Runnable`/`Callable` wrappers, or a dedicated system identity according to task type.
3. Use `@Async("...")` to specify a `SecurityContext`-wrapping executor rather than relying on the default executor.
4. Distinguish **propagating security context** from **enforcing permissions**, **propagating transactions**, **propagating HTTP requests**, and **propagating trace/MDC**.
5. Write tests proving the principal is visible in the worker, method security still denies unauthorized callers, and threads are cleared after both success and exceptions.
6. Identify risks of user mix-ups from thread reuse, delayed tasks, revoked tokens, and internal calls bypassing proxies.

## 2. Why Do Errors Occur When Moving Logic to `@Async`?

In a typical Spring Security Servlet application, `SecurityContextHolder` stores `SecurityContext` for **the current thread**, defaulting to the `MODE_THREADLOCAL` strategy. `SecurityContext` holds `Authentication` (principal, authorities, authentication details). When a protected HTTP request arrives, the filter chain establishes the context on the request thread and clears it upon completion.

Suppose a controller invokes a service method protected by `@PreAuthorize("hasAuthority('report:read')")`. On the HTTP request thread, `SecurityContextHolder.getContext().getAuthentication()` may be Alice, holding the `report:read` authority. When moving work to `@Async`, the method may execute on a **different** executor thread; the parent thread's `ThreadLocal` does not automatically appear in the worker. Common consequences:

- `SecurityContextHolder.getContext().getAuthentication() == null` in the worker; code calling `getName()` may throw `NullPointerException`.
- `@PreAuthorize`/`@PostAuthorize` executing in the worker lacks `Authentication`, so the protected method can be denied even though the HTTP caller was authenticated.
- If the application sets the context manually and **forgets to clear it**, thread pool reuse can carry Alice's principal into Bob's task: a severe isolation bug.
- Patching around it by passing `username` as a method parameter does not guarantee proper authorization: an ID string is not a verified `Authentication`; security requires policy verification at the point of use.

### Request Flow Diagram

~~~text
Alice's HTTP request
  |
  v
request thread "http-..."
SecurityContextHolder -> Authentication(alice, report:read)
  |
  | call @Async proxy, submit task
  v
worker thread "report-..."
SecurityContextHolder -> [empty by default]
  |
  +--> call @PreAuthorize -> missing authentication -> DENY

If using an executor wrapping SecurityContext:
request thread: Authentication(alice)
  | submit => capture context at submission point
  v
worker thread: set Alice context
  | call Spring-protected service -> evaluate Alice's permissions
  | finally: clear context
  v
thread returns to pool, does not retain Alice for other tasks
~~~

**Crux:** `@Async` only handles **dispatching the method to an executor**. It is not a feature that automatically propagates all thread-local state. `@EnableMethodSecurity` enables method authorization checks, yet it does not propagate context to workers either.

## 3. What Are the Boundaries of `SecurityContext`?

### 3.1. Thread-Local, Not Global Across All Requests

| Strategy / mechanism | Behavior | Appropriate here? |
| --- | --- | --- |
| `MODE_THREADLOCAL` (common/default) | Context belongs to the current thread | Suits request threads; executors need wrappers to pass context |
| `MODE_INHERITABLETHREADLOCAL` | **Newly created child** threads can inherit context reference at creation time | **Not** a safe general solution for thread-reusing pools |
| `MODE_GLOBAL` | Single shared context for the entire JVM | **Not** suitable for multi-user server applications |
| `DelegatingSecurityContext...` | Wraps each task, sets context during execution, clears afterward | Proper choice for executor work needing caller identity |
| Explicit principal/tenant/scope in job payload | Carries business data across boundaries with re-verification | Suits long-running/durable jobs, queues, or other services |

Do not switch `SecurityContextHolder.setStrategyName(MODE_INHERITABLETHREADLOCAL)` just to "fix" `@Async`. Pools may create threads before a request starts; threads are reused and do not re-inherit context on each submission. Worse, context may leak to child threads **that should not hold those permissions**.

### 3.2. Capturing Context Differs from Granting New Permissions

Transferring context only means **the worker sees the transferred `Authentication`**; it does not mean those permissions remain valid forever or apply to every resource. The worker must still invoke method security or domain policies. When a task waits in a queue for a long time, roles may have changed or the account may be locked; an old snapshot does not refresh itself.

Nor should every task act on behalf of a request user. For instance:
- **Work requiring Alice herself and Alice's current permissions:** propagate Alice's context at submission, and consider re-checking at execution.
- **Periodic system maintenance:** run under a dedicated least-privilege service identity; never copy a random request's context.
- **Jobs spanning restarts/messaging:** persist actor ID/tenant/permission intent in a controlled way; in another worker process, establish and verify a trusted identity—never "copy `ThreadLocal` over Kafka."

## 4. Where Does `@Async` Actually Take Effect?

Enable async processing:

~~~java
@Configuration
@EnableAsync
class AsyncConfiguration {
}
~~~

When an `@Async` method is **called through the Spring proxy**, Spring dispatches the call to a matching `TaskExecutor`; the caller can receive a `CompletableFuture`/`Future` immediately while the method body runs on an executor-chosen thread. You can select an executor by name:

~~~java
// Snippet inside a Spring-managed bean.
@Async("securedWorkerExecutor")
public CompletableFuture<String> calculate() {
    return CompletableFuture.completedFuture("done");
}
~~~

**Do not confuse `@Async` with "always runs asynchronously":**

- `this.calculate()` from the same bean normally **does not go through the proxy**, so `@Async` is not triggered in default proxy mode.
- `@EnableAsync` and `@EnableMethodSecurity` are two separate mechanisms; calling an `@PreAuthorize` method via self-invocation can bypass authorization too.
- `@Async` returning `void` has no future to deliver exceptions to the caller; configure an `AsyncUncaughtExceptionHandler` or appropriate logging/monitoring.
- `CompletableFuture.get()/join()` surfaces worker exceptions to the caller when awaited; do not confuse "submitted" with "succeeded."
- With `@Async`, methods returning results normally return `Future`/`CompletableFuture`; do not return a plain `String` expecting Spring to turn it into a future.
- If you write `CompletableFuture.supplyAsync(...)` inside `@Async` without passing an executor, you create a **second thread boundary** (typically the common pool) and can lose security context again. Inside an already-async method, returning `completedFuture(...)` after synchronous processing on the worker is easier to reason about.

### 4.1. Ordering Between `@Async`, `@PreAuthorize`, and `@Transactional`

Advice/proxy ordering is decided by the framework and configuration. Do not assume two annotations on the same method always execute on the same thread or in your desired order. An easily testable structure is:

- Bean A holds the `@Async("securedWorkerExecutor")` method.
- Bean B holds the `@PreAuthorize` method enforcing policy on the worker.
- Bean C (if needed) manages the DB transaction inside the worker.

When A calls B **through the Spring bean proxy**, the worker already has `SecurityContext` installed by the wrapper before B's method security runs. This structure keeps boundaries clear and avoids relying on advisor ordering between `@Async` and `@PreAuthorize` on the same method.

## 5. Using `DelegatingSecurityContextAsyncTaskExecutor`

Spring Security provides `org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor`, an `AsyncTaskExecutor` that wraps tasks before passing them to the underlying executor. The `Runnable`/`Callable` wrapper sets `SecurityContext` on the worker before running the delegate and clears it in `finally` afterward.

### 5.1. Two Constructors with Different Meanings

**Use the context at submission time (usually right for user-triggered `@Async`):**

~~~java
AsyncTaskExecutor secured = new DelegatingSecurityContextAsyncTaskExecutor(
        rawAsyncTaskExecutor);
~~~

No fixed `SecurityContext` is passed: the wrapper captures the context of the thread **submitting the task** to forward to the worker. If Alice submits and then Bob submits, each task carries its respective context at submission time. Do not misread this as "permanently capturing Alice when the bean is created."

**Use an explicitly supplied context for all tasks:**

~~~java
SecurityContext systemContext = SecurityContextHolder.createEmptyContext();
// Set Authentication of a service identity verified by a trusted mechanism.
AsyncTaskExecutor secured = new DelegatingSecurityContextAsyncTaskExecutor(
        rawAsyncTaskExecutor, systemContext);
~~~

The second form fits only when **every task** intentionally runs under the same identity (such as a subsystem designed for system jobs). Never supply a fixed admin principal just so tasks pass `@PreAuthorize`; that turns a context-propagation bug into a privilege-escalation vulnerability. Never construct fake `Authentication` objects from client data to "pass" checks.

### 5.2. A Security Wrapper Is Not a Transaction, Request, or Trace Wrapper

The security wrapper manages only `SecurityContextHolder`; it **does not automatically transfer**:
- `@Transactional` transactions, JDBC connections, `EntityManager`, or request persistence contexts.
- `RequestContextHolder`/`HttpServletRequest`, or closed sessions.
- SLF4J MDC/correlation IDs, `LocaleContextHolder`, tracing state, or other custom `ThreadLocal`s.
- Identities/tokens to another process.

If MDC/tracing is needed, use dedicated context-propagation mechanisms and establish cleanup order; never stuff unrelated state into `SecurityContext` or use static/global users. Always clear/restore state in `finally`.

### 5.3. Mutable References and Submission Timing

`SecurityContext` is a mutable object. When transferring **the same instance** to tasks, avoid calling `SecurityContextHolder.getContext().setAuthentication(...)` to mutate users repeatedly on a context referenced by queued tasks. When changing identities, create a fresh context:

~~~java
SecurityContext separate = SecurityContextHolder.createEmptyContext();
separate.setAuthentication(trustedAuthentication);
SecurityContextHolder.setContext(separate);
~~~

This guides **working with a valid verified context**, not self-elevating privileges. If a task needs a long-lived reliable snapshot, design explicit authorization/identity data per contract and re-verify at execution time. "Capturing at submission" does not freeze every mutable property, nor prevent permission changes or token expiration.

## 6. Spring Boot Example: Raw Executor vs. `SecurityContext`-Propagating Executor

This example uses a Spring Boot application context without a REST controller to isolate `@Async` and method security. Everything resides in **one Java file** and runs in a Spring Boot project with proper dependencies. A single-threaded `ThreadPoolTaskExecutor` bean serves both call paths:

- `@Async("rawWorkerPool")`: worker receives **no** context from the caller.
- `@Async("securedWorkerExecutor")`: wrapper transfers the caller's context into the worker, then cleans up.
- A **separate bean** uses `@PreAuthorize` to prove permissions are genuinely evaluated inside the worker.

Create `src/main/java/demo/asyncsecurity/AsyncSecurityApplication.java`:

~~~java
package demo.asyncsecurity;

import java.util.concurrent.CompletableFuture;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor;
import org.springframework.stereotype.Service;

@SpringBootApplication
@EnableAsync
@EnableMethodSecurity
public class AsyncSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(AsyncSecurityApplication.class, args);
    }

    @Bean(name = "rawWorkerPool")
    ThreadPoolTaskExecutor rawWorkerPool() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(1);
        pool.setMaxPoolSize(1);
        pool.setQueueCapacity(20);
        pool.setThreadNamePrefix("report-worker-");
        pool.initialize();
        return pool;
    }

    @Bean(name = "securedWorkerExecutor")
    AsyncTaskExecutor securedWorkerExecutor(
            @Qualifier("rawWorkerPool") ThreadPoolTaskExecutor delegate) {
        // Do not pass a fixed SecurityContext:
        // captures the submitting thread's context per task.
        return new DelegatingSecurityContextAsyncTaskExecutor(delegate);
    }
}

@Service
class ProtectedReportReader {
    // This method is called from another bean through the Spring proxy.
    @PreAuthorize("hasAuthority('report:read')")
    public String readUnderCurrentPrincipal() {
        Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();
        return auth.getName();
    }
}

@Service
class AsyncReportReader {
    private final ProtectedReportReader securedReader;

    AsyncReportReader(ProtectedReportReader securedReader) {
        this.securedReader = securedReader;
    }

    @Async("rawWorkerPool")
    public CompletableFuture<String> nameWithoutPropagation() {
        Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();
        return CompletableFuture.completedFuture(
                auth == null ? "anonymous" : auth.getName());
    }

    @Async("securedWorkerExecutor")
    public CompletableFuture<String> nameWithPropagationAndAuthorization() {
        String name = securedReader.readUnderCurrentPrincipal();
        return CompletableFuture.completedFuture(name);
    }
}
~~~

**Gradle dependencies** in a project with Spring Boot plugin, dependency management, and Java 17+ configured:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

You can run the application with the project's wrapper (e.g., `./gradlew bootRun` on Unix or `gradlew.bat bootRun` on Windows). The demo defines no HTTP endpoints and creates no real accounts. For verification proof, run `./gradlew test` with the tests in the next section. For a real API, add Spring Web / an appropriate `SecurityFilterChain` and ensure request callers have an `Authentication` before submitting.

### 6.1. Tracing the Example's Call Paths

~~~text
@WithMockUser(alice, report:read) / authenticated request
  |
  +-- asyncReportReader.nameWithoutPropagation()
  |    |
  |    +-- @Async("rawWorkerPool")
  |         worker thread: auth == null -> "anonymous"
  |
  +-- asyncReportReader.nameWithPropagationAndAuthorization()
       |
       +-- @Async("securedWorkerExecutor")
            wrapper captures Alice's context on submit
            rawWorkerPool runs task with Alice's context
                |
                +-- protectedReportReader.readUnderCurrentPrincipal()
                    Spring proxy @PreAuthorize("hasAuthority('report:read')")
                    => PASS, result "alice"
            finally: clear Alice's context from worker
~~~

A single-thread pool makes thread reuse easy to verify, yet is **not** required for the wrapper to work properly. Production can choose pool size/queue policies per load, backpressure limits, and SLAs. Without queue and rejection controls, async tasks may be rejected under overload; submission failures are not authorization errors.

### 6.2. Why Define a Separate Bean for the Raw Pool?

We keep `rawWorkerPool` under Spring's lifecycle so Spring manages shutdown and supplies it as the delegate to the wrapper. The `securedWorkerExecutor` bean is solely responsible for propagating `SecurityContext`. With `@Async("securedWorkerExecutor")`, the specific method uses the wrapped executor explicitly.

**In production code, avoid letting arbitrary `@Async` methods use the raw pool by default.** You can expose only secured executors for tasks needing a principal, name executors clearly for tasks running under service identities, and prevent methods from accidentally using a non-propagating executor. If `@Async` omits an executor name, Spring picks one via its default resolution rules; never assume that is always `securedWorkerExecutor`.

## 7. Testing Method Security End-to-End in Workers

Place `src/test/java/demo/asyncsecurity/AsyncSecurityApplicationTest.java` in the same package:

~~~java
package demo.asyncsecurity;

import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class AsyncSecurityApplicationTest {
    @Autowired
    AsyncReportReader reader;

    @Test
    @WithMockUser(username = "alice", authorities = "report:read")
    void transfersAliceAndClearsWorkerAfterward() throws Exception {
        assertEquals("anonymous",
                reader.nameWithoutPropagation()
                        .get(3, TimeUnit.SECONDS));

        assertEquals("alice",
                reader.nameWithPropagationAndAuthorization()
                        .get(3, TimeUnit.SECONDS));

        // Raw pool has a single worker, so subsequent calls reuse the same thread.
        assertEquals("anonymous",
                reader.nameWithoutPropagation()
                        .get(3, TimeUnit.SECONDS));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "profile:read")
    void methodSecurityDeniesEvenWithContextTransferred()
            throws Exception {
        ExecutionException failure = assertThrows(
                ExecutionException.class,
                () -> reader.nameWithPropagationAndAuthorization()
                        .get(3, TimeUnit.SECONDS));

        assertInstanceOf(AccessDeniedException.class,
                failure.getCause());

        // Error path must also clear context from worker.
        assertEquals("anonymous",
                reader.nameWithoutPropagation()
                        .get(3, TimeUnit.SECONDS));
    }

    @Test
    @WithMockUser(username = "carol", authorities = "report:read")
    void nextCallerGetsOwnPrincipal() throws Exception {
        assertEquals("carol",
                reader.nameWithPropagationAndAuthorization()
                        .get(3, TimeUnit.SECONDS));

        assertEquals("anonymous",
                reader.nameWithoutPropagation()
                        .get(3, TimeUnit.SECONDS));
    }
}
~~~

### Expectations per Test

| Case | Key signal |
| --- | --- |
| `nameWithoutPropagation` even though request/test is Alice | `anonymous` in worker; `@Async` does not auto-propagate auth |
| `nameWithPropagationAndAuthorization` with Alice having read authority | Worker sees Alice and `@PreAuthorize` allows |
| Bob missing `report:read` | `Future.get()` throws `ExecutionException` wrapping `AccessDeniedException` |
| After successful/failed task, call via raw pool | `anonymous`: no principal retained on reused thread |
| Carol submits after earlier tasks | Result is Carol, not Alice or Bob |

The last piece of evidence relies on the **single worker** configured in the example and should not be used as a multi-threaded production test algorithm. In production, use task barriers and per-task tracking to detect contamination across concurrent users and threads.

**Note:** `@WithMockUser` places authentication into the test thread's security context and does not vanish just because an async task finishes. The goal here is testing that the wrapper transfers context from the test thread to the executor thread, enforces method security in the worker, and cleans up the worker. A test instantiating the service with `new` will **not** test Spring proxies.

## 8. Standalone Java 17: Simulating Per-Task Capture/Restore

This example uses only the JDK, without Spring Security. It simulates `ThreadLocal` and an executor so learners can clearly see the difference between a raw task and a wrapped task. The illustrative mechanism includes **restoring the worker's previous value** in `finally`; Spring Security uses wrappers managing `SecurityContextHolder` directly, and the framework docs describe clearing the context after the task.

Save as `ThreadContextDemo.java`:

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ThreadContextDemo {
    private static final ThreadLocal<String> USER = new ThreadLocal<>();

    static <T> Callable<T> propagate(Callable<T> operation) {
        // Capture when caller submits, not re-read inside worker.
        String captured = USER.get();

        return () -> {
            String previous = USER.get();
            try {
                if (captured == null) {
                    USER.remove();
                } else {
                    USER.set(captured);
                }
                return operation.call();
            } finally {
                if (previous == null) {
                    USER.remove();
                } else {
                    USER.set(previous);
                }
            }
        };
    }

    static String currentName() {
        String user = USER.get();
        return user == null ? "anonymous" : user;
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            USER.set("alice");
            System.out.println("raw=" +
                    pool.submit(ThreadContextDemo::currentName).get());

            System.out.println("alice=" +
                    pool.submit(propagate(ThreadContextDemo::currentName))
                            .get());

            USER.set("bob");
            System.out.println("bob=" +
                    pool.submit(propagate(ThreadContextDemo::currentName))
                            .get());

            System.out.println("after=" +
                    pool.submit(ThreadContextDemo::currentName).get());
        } finally {
            USER.remove();
            pool.shutdownNow();
        }
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 ThreadContextDemo.java
java ThreadContextDemo
~~~

**Exact stdout** (the program calls `get()` to serialize print order):

~~~text
raw=anonymous
alice=alice
bob=bob
after=anonymous
~~~

**Output explanation:** `raw` runs directly on the pool thread and sees none of the caller's `ThreadLocal`. Both `propagate(...)` calls capture Alice and Bob respectively on the submitting thread; the worker installs each value and cleans up. The final raw call confirms the worker does not retain Bob. In Spring apps, use `DelegatingSecurityContext...` instead of writing manual security wrappers when the framework provides them.

## 9. `@Async` and `@Transactional`: Two Boundaries to Manage Separately

`SecurityContext` can be transferred to the worker via a wrapper, yet **transaction context does not follow automatically**. Example:

~~~java
// Business flow sketch, not a standalone program.
@Transactional
public void approveAndNotify(long invoiceId) {
    invoiceRepository.markApproved(invoiceId);
    notificationService.sendAsync(invoiceId); // @Async on another bean
}
~~~

If `sendAsync` runs fast, it may execute **before `approveAndNotify`'s transaction commits**. It may miss the new data or send a notification for a transaction that ultimately rolls back. Propagating `SecurityContext` does not fix that race.

Principles:

1. `@Transactional` opens and closes transactions bound to the executing thread per its transaction manager. Switching threads does not carry the caller's JDBC transaction or persistence context across.
2. If a method running **in the worker** needs its own transaction, invoke a `@Transactional` bean through its Spring proxy inside the worker; test reads/writes and rollback in the worker's transaction.
3. If a task must run only after data commits, consider `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` to dispatch the async command **after commit** (note that event listeners do not make tasks durable). For reliable delivery across restarts or executor failures, use a transactional outbox/queue with idempotent retries.
4. Never pass lazy-loading JPA entities across async threads assuming the session stays open. Pass minimal IDs/DTOs and reload inside a separate transaction if needed.
5. If business logic must check tenant permissions when the worker actually runs, use the verified identity/tenant and re-evaluate policy against current data. Having permission at enqueue time does not guarantee the task is still permitted hours later.

### 9.1. Putting `@Async` and `@Transactional` on the Same Method?

Configuration can let the worker open its own transaction, yet proxy/advice interaction is easy to misunderstand. The transparent design is splitting the async bean and the transactional bean:

~~~java
// Illustrative snippet; bean/method names belong to your application.
@Service
class AsyncCoordinator {
    private final TransactionalWorker worker;

    AsyncCoordinator(TransactionalWorker worker) {
        this.worker = worker;
    }

    @Async("securedWorkerExecutor")
    public CompletableFuture<Void> execute(long id) {
        worker.processOne(id);
        return CompletableFuture.completedFuture(null);
    }
}

@Service
class TransactionalWorker {
    @Transactional
    public void processOne(long id) {
        // Opens a new transaction on the worker thread when called via proxy.
        // Reload state/resource and enforce permissions before writing.
    }
}
~~~

The block above **is not standalone**: imports and persistence logic are omitted. It illustrates intentional boundaries and does not replace full error handling, idempotency, timeouts, or transaction propagation settings. If the transactional service itself is an authorization boundary, add `@PreAuthorize` or matching policies to protect it when jobs/HTTP call through different paths.

## 10. Proper Scope: "Propagating Authentication" Is Different from "Granting Permissions"

### 10.1. Permissions at Enqueue Time vs. Execution Time

There are at least three distinct points in time:
- **t0:** Alice's request is authenticated and wants to schedule a job.
- **t1:** the system places the task in the executor queue; the wrapper captures the submitting thread's context.
- **t2:** the worker runs the task after t0 and t1 have passed.

If Alice's account is locked between t1 and t2, the captured context is not a fresh account-status check. Method security may evaluate authorities stored in the old `Authentication` unless policy actively queries updated state. Choose an explicitly documented contract:

| Contract | Recommended handling |
| --- | --- |
| Short task tightly bound to request | Capture context on submit, check permissions in worker, clear context afterward |
| Long-running, high-risk task where access can be revoked | Persist minimal actor/tenant/scope; re-verify before sensitive actions |
| System background job | Dedicated service identity, least privilege, audit "on behalf of" when applicable |
| Message queue / cross-process task | Never propagate Java `ThreadLocal`; verify identity in worker, protect payload, enforce idempotency |

Distinguish **acting with the requester's permissions** from **acting with the system's current permissions**. Both can be valid depending on business rules, yet tasks must never accidentally run under another user's identity due to pool reuse.

### 10.2. A `SecurityContext` Instance Is Not an Immutable Snapshot

If code shares a mutable `SecurityContext` across multiple threads, mutating `Authentication` inside that context can cause unintended side effects. Never use a static or singleton instance to represent the "current user." When changing authentication on a thread, create a new `SecurityContextHolder.createEmptyContext()`, control its scope, and clean up per lifecycle. For long-lived jobs, pass a **verified identity claim**, then build/verify context via the worker's valid authentication mechanism.

### 10.3. Do Not Propagate Overly Broad Credentials

`Authentication` may hold sensitive details or credentials depending on the provider. Transfer context to tasks only when truly needed and within the same trust boundary. For queues, audit logs, or DB persistence, **never arbitrarily serialize the entire `SecurityContext`**. Use minimal actor ID, tenant ID, correlation ID, and action intent; resolve permissions via policy when needed.

### 10.4. Method Security Remains the Enforcement Layer

If the worker only executes:

~~~java
String username = authentication.getName();
emailGateway.send(...);
~~~

having `username` does not prove that email is allowed to be sent. You must evaluate both authorities and resource permissions, such as `@PreAuthorize("hasAuthority('report:read')")`, ACL policy beans, or service validation. If a user may read report A only, their context does not authorize reading report B. Verify tenant scope and resource ownership, and never trust client-supplied IDs.

## 11. Related Mechanisms That Are Not Equivalent

### 11.1. `DelegatingSecurityContextRunnable` and `Callable`

For an individual task not routed through Spring `@Async`:

~~~java
// On a thread already holding a valid SecurityContext:
Runnable securedTask =
        new DelegatingSecurityContextRunnable(() -> protectedService.run());
executor.execute(securedTask);
~~~

This concise wrapper fits when you control submission manually. If every task on an executor needs the caller's context, wrapping **the executor** once is usually less error-prone than wrapping each `Runnable` by hand. For `Callable` with return values, use `DelegatingSecurityContextCallable`. For standard `ExecutorService`, Spring Security provides `DelegatingSecurityContextExecutorService`.

Remember **where wrapping happens**: the `Runnable`/`Callable` must be wrapped while the caller holds a valid context, or the executor wrapper must wrap at submission time. Never create a task and wrap it for the first time inside the worker after the caller's context is gone.

### 11.2. `TaskDecorator`

Spring's `ThreadPoolTaskExecutor` supports `TaskDecorator` to attach logic around tasks, often used for MDC/observability. Implementing security propagation manually via a decorator requires handling capture, cleanup, wrapper layering, and overwrite edge cases; for `SecurityContext`, prefer the dedicated `DelegatingSecurityContext...` abstractions. Combining multiple decorators/wrappers can capture at the wrong moment or clean up in an unexpected order; write integration tests over real call paths.

### 11.3. Servlet Async, MVC `Callable`, and WebFlux Are Not Like `@Async`

- Servlet `AsyncContext.start(...)` and Spring MVC async return types have dedicated Spring Security integrations that **do not follow automatically** from how service `@Async` works.
- Reactor/WebFlux has `ReactiveSecurityContextHolder` bound to Reactor Context rather than merely a thread-local passed across an executor as in Servlet.
- Java virtual threads differ from traditional pools in thread-creation semantics, yet do not turn `SecurityContext` into global state; propagation still depends on the execution model.
- `CompletableFuture.supplyAsync(...)` uses its own executor; unless you pass a suitable executor, an outer `@Async("securedWorkerExecutor")` cannot protect work dispatched onto the next thread.

## 12. Common Pitfalls and How to Spot Them

### Pitfall 1 — "Enabling `@EnableAsync` and `@EnableMethodSecurity` is enough"

Symptom: request succeeds before async, then throws `AccessDeniedException` or sees `Authentication` as null in async. Cause: security context is thread-local and was not transferred to the worker. Choose a context-wrapping executor and test through the proxy.

### Pitfall 2 — Using `MODE_INHERITABLETHREADLOCAL` for a Thread Pool

It can pass by luck when the pool happens to spawn a thread during Alice's request, then fail when Bob reuses that thread. This is dangerous for multi-user applications. Never use it as the standard mechanism for pools; per-task wrappers bind the user **at submission time**.

### Pitfall 3 — Setting Context in Worker Without Clearing It

~~~java
// Unsafe anti-pattern:
SecurityContextHolder.setContext(aliceContext);
doWork(); // if this throws, the thread may retain Alice indefinitely
~~~

Use Spring Security wrappers; if forced to manage manually, place cleanup/restore in `finally` and test exception, cancellation, and rejection paths. Never use a static `SecurityContext` across tasks.

### Pitfall 4 — An Executor Wrapping a Fixed Admin Context

Every task gets silently elevated to admin privileges, hiding insufficient caller permissions. Only use a fixed context when **deliberately designing a service identity**, provisioned reliably with only necessary permissions, distinguishing system jobs from user tasks.

### Pitfall 5 — `@Async` Nullified by Self-invocation

~~~java
@Service
class WrongAsyncService {
    public void start() {
        doAsync(); // this.doAsync(): bypasses default proxy
    }

    @Async("securedWorkerExecutor")
    public void doAsync() {
        // May execute synchronously on the caller thread.
    }
}
~~~

Fix: extract `doAsync` into another bean and call through the Spring-managed bean, or deliberately pick another interception mechanism. Never rely on the annotation alone to assume a thread switch occurred.

### Pitfall 6 — Misunderstood Post-Check / Transaction Scope

Task reads uncommitted entities, or sends email before the caller's transaction rolls back. Propagating Alice's context does not propagate transactions or rollback. Design after-commit dispatch, worker-scoped transactions, or outbox, and re-check policy at write time.

### Pitfall 7 — Ignored `Future`s and Swallowed Errors

`@Async void` may log exceptions somewhere nobody monitors; returning `CompletableFuture` without observing failures causes silent job failures. Use futures/monitoring, retry policies, idempotency, and correlation-ID logging **without exposing credentials**. Handle authorization errors distinctly: never blindly retry an `AccessDeniedException` as a transient network glitch.

### Pitfall 8 — Thinking Context Propagation Equals Permission Verification

Having an `Authentication` does not mean every action is allowed. Method security and policies must check authorities, tenant, ownership, and resource state; for delayed tasks, consider revoked permissions.

### Pitfall 9 — Async Tasks Spawning Further Async Tasks on the Common Pool

Default `CompletableFuture.supplyAsync` can use `ForkJoinPool.commonPool`; the second thread lacks the context wrapper. Specify the proper executor on **every** submission boundary, or keep work on one configured executor and test all branches.

### Pitfall 10 — Using HTTP Request Credentials for Durable Jobs

The request logs out, the token expires, or the thread ends while the job sits in a queue. The job may hold stale permissions or inappropriate credentials. Separate request-scoped tasks from durable jobs; pass minimal actor/tenant/scope and re-verify from trusted sources at execution time.

## 13. Minimum Test Matrix for Production Applications

| Case | What to prove |
| --- | --- |
| Caller Alice has read permission | Worker receives Alice's `Authentication` accurately |
| Caller Bob has a different permission | Worker denies in method security, never "borrowing" Alice |
| Anonymous / contextless caller | Fails closed; never assigns default permissions |
| Task throws exception | Worker context cleared/restored; future surfaces the failure |
| Single-thread pool with Alice → Bob → Alice | Zero cross-user contamination |
| Multi-thread pool with concurrent tasks | Each task binds identity at submission time |
| Bean calls internal `this.@AsyncMethod` | Test catches unproxied call path |
| Service called from scheduled job / message listener | Clear identity, method authorization still enforced |
| Caller transaction rolls back | Async action is not mistaken for part of caller's transaction |
| User permissions revoked before task runs | Policy re-checks per contract; task does not hold permissions forever |
| Full queue, executor shutdown, task cancellation | No "false success"; proper cleanup and monitoring |
| Nested `CompletableFuture`/executors | Every thread boundary has proper context propagation |

Never verify security merely by printing `Thread.currentThread().getName()`. Assert **exact principal/authorities per task, zero leakage afterward, and right authorization decisions in the service**. If HTTP endpoints exist, add `MockMvc` tests to verify the request filter chain; `@WithMockUser` in service-only tests does not verify the real HTTP path.

## 14. Practical Decision Rules

1. **Short task triggered by an authenticated user needing method security?** Use `@Async("securedWorkerExecutor")` with `DelegatingSecurityContextAsyncTaskExecutor` without a fixed context; test auth and cleanup.
2. **Task does not need a user identity?** Do not force context propagation; use a service/job contract with explicit least-privilege identity.
3. **Slow / long-queued work items?** Design re-authorization or service identity at execution time; never trust stale authority snapshots indefinitely.
4. **Tasks mutating the DB?** Open appropriate transactions in the worker, protect state at write time, and decouple from caller commit timing.
5. **Data from other tenants or via queues/processes?** Never blindly forward raw context/credentials; validate identity and resource scope at the processing boundary.
6. **Multiple executors / nested futures?** Check which executor actually runs each stage; never assume an outer wrapper protects every thread.

### Self-Practice Questions

**Question 1:** Alice has `report:read`, calls `@Async` on a raw executor, and the worker calls a `@PreAuthorize("hasAuthority('report:read')")` bean. Why can it be denied?

**Answer:** `@Async` switches threads; `SecurityContextHolder` is thread-local by default, so the worker lacks Alice's authentication. Use a context-wrapping executor at submission and keep checking permissions in the worker.

**Question 2:** Does enabling `MODE_INHERITABLETHREADLOCAL` fully solve thread pools?

**Answer:** No. Pools reuse pre-existing threads; inheritance happens only when child threads are created and risks retaining wrong identities across tasks.

**Question 3:** Once the wrapper transfers `Authentication`, are `@PreAuthorize`/ACL checks in the worker still needed?

**Answer:** Yes. Propagation only provides identity data; enforcement decides what the task may do to which resources.

**Question 4:** Update an invoice in a request transaction, submit an async email right away, then the transaction rolls back. Does context propagation solve this?

**Answer:** No. Security context is distinct from transactions. Synchronize with commit (`AFTER_COMMIT`/outbox), manage worker transactions separately, and enforce idempotency.

**Question 5:** Is `CompletableFuture.supplyAsync` inside an `@Async` using a secured executor automatically safe?

**Answer:** You cannot assume so. It may run on another executor; pass the appropriate executor on the subsequent submission too.

## Reference Materials

- [Spring Security – Concurrency Support](https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html): thread-bound `SecurityContextHolder`; `DelegatingSecurityContextRunnable` and `DelegatingSecurityContextExecutor`, capture/cleanup semantics.
- [DelegatingSecurityContextAsyncTaskExecutor Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/task/DelegatingSecurityContextAsyncTaskExecutor.html): two constructors, `Runnable`/`Callable` wrappers, `AsyncTaskExecutor` interface.
- [Spring Framework – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@EnableAsync`, `@Async`, executor selection, proxy/self-invocation, and exception handling.
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, method interception.
- [Spring Framework – Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): proxy boundaries and transaction semantics.

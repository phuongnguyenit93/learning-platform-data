# Propagating Tenant Context Through Background Tasks and Cleaning Up After Execution in Spring Security

## 1. Goal: the right tenant in every thread, even outside HTTP requests

In a multi-tenant SaaS application, HTTP requests are typically authenticated by Spring Security and the application resolves an `AuthorizedTenantScope`: who is calling, which tenant they belong to, and what permissions they hold. However, processing often continues on another thread: `@Async`, `CompletableFuture`, `ExecutorService`, schedulers, Spring Batch, queue consumers, report-export jobs, or email workers.

Across these handoffs, two distinct hazards arise:

1. **Context loss:** the worker does not know the verified tenant; developers fall back to a default tenant, drop the filter, or trust a tenant from an unverified payload.
2. **Context leakage:** a thread pool reuses a worker; tenant `alpha` lingers in `ThreadLocal`, `SecurityContextHolder`, MDC, or the database session, causing tenant `beta`'s job to execute as tenant `alpha`.

The second bug is insidious because no attacker needs to craft a special URL. Simply running two jobs from two different tenants sequentially on the same worker with an uncleaned error path is enough.

This article explains **propagating authorized tenant information** rather than arbitrary tenant strings, **re-checking permissions when work actually runs**, and **clearing/restoring every context in `finally`**. Topics cover standalone Java 17, Spring `TaskDecorator`/`@Async`, Spring Security `DelegatingSecurityContext...`, queues, schedulers, Reactor, RLS, auditing, and tests.

### Invariant to uphold

```text
Before task runs:
    worker tenant context = EMPTY

While task runs:
    worker tenant context = authorized tenant
    DB query/update targets only that tenant

After task succeeds / fails / is interrupted:
    worker tenant context = EMPTY
    or restore prior context per contract

Next task:
    cannot observe the previous task's tenant
```

**Note:** cleanup preserves isolation between tasks, yet it does not turn a client-supplied tenant ID into a trusted tenant. **Authorization must happen before granting tenant scope**, and delayed jobs must re-verify at execution time per your revocation policy.

## 2. Four kinds of information never to conflate

| Information | Example | Why are they not equivalent? |
| --- | --- | --- |
| Requested tenant | Header `X-Tenant-Id: alpha` | Caller chose it; proves zero permission |
| Authenticated identity | `Authentication`, validated JWT `iss/sub` | Identifies caller, not whether alpha is allowed |
| Authorized tenant scope | `subject=alice, tenant=alpha, action=EXPORT` | Policy outcome from identity + membership + action |
| Execution context | `ThreadLocal`, MDC, Reactor `Context`, DB session | Only a state carrier, never proof of authorization |

An application may use `TenantContext` so Hibernate or repositories know the active tenant. Nevertheless:

- `TenantContext.set("alpha")` **is not an authorization grant**.
- `SecurityContextHolder.getContext().getAuthentication()` may contain a user yet **lack the application's tenant scope**.
- `MDC.put("tenant", "alpha")` only attaches a log label; it does nothing to protect SQL.
- A `Connection` currently pointed at schema alpha does not prove the caller has rights in alpha.
- A job DTO carrying `tenantId=alpha` must be evaluated under the producer/consumer trust model.

**Preferred design:** pass an immutable `AuthorizedTenantScope` or `JobCommand` carrying normalized identity and tenant, and invoke server-side policy at each security boundary. Use `ThreadLocal` only to support frameworks requiring implicit context; whenever possible, passing scope explicitly as a service/repository parameter is easier to verify.

## 3. End-to-end flow: request → enqueue → worker

```text
HTTP / API
  |
  v
Authentication: verified JWT/session/mTLS
  |
  v
TenantResolver:
    requested tenant -> verify membership/authority
  |
  v
AuthorizedTenantScope(subject, tenant, permissions)
  |
  +------ synchronous request ------------------+
  |                                             |
  v                                             v
Service read/write                         Submit background job
  |                                      /          \
  v                                     /            \
Repository WITH tenant predicate    In-process async  Durable queue
                                        |                 |
                                        v                 v
                                   Capture scope      Persist command
                                   at submit         do not send raw token
                                        |                 |
                                        v                 v
                                   Worker thread     Consumer identity
                                   holds temp scope  + reauthorization
                                        |                 |
                                        +--------+--------+
                                                 |
                                                 v
                                       Tenant-scoped repository
                                                 |
                                                 v
                                       finally cleanup context
                                                 |
                                                 v
                                       Thread/cursor/connection
                                       safe reuse
```

These two paths have **different trust models**:

- **In-process async, very short-lived:** may pass an immutable snapshot authorized at submission, though especially sensitive actions should re-check.
- **Durable queue/job running minutes/hours later or in another service:** a request-time snapshot is insufficient. The consumer must authenticate the job origin, resolve appropriate identity/capabilities, check live membership/policy, and only then construct the runtime scope.

Never persist a user's bearer token into a queue just so workers can “borrow” the old token. Tokens expire, can leak, and carry the wrong audience; use service identities and explicit authorization contracts for durable work.

## 4. Why are ThreadLocal and thread pools dangerous?

Java `ThreadLocal<T>` binds a value to **the currently executing thread**. `Executors.newFixedThreadPool(...)` or `ThreadPoolTaskExecutor` retains threads to serve multiple tasks. If task A calls `CURRENT_TENANT.set("alpha")` and omits `remove()`:

```text
Worker-1:
  09:00 task A        CURRENT_TENANT = alpha
  09:01 task A finishes but forgets remove()
  09:02 task B        CURRENT_TENANT is still alpha
  09:03 task B queries -> accesses wrong tenant
```

Dangerous code:

```java
static final ThreadLocal<String> CURRENT_TENANT = new ThreadLocal<>();

void process(String tenant, Runnable action) {
    CURRENT_TENANT.set(tenant); // Wrong: is tenant even authorized?
    action.run();               // If this throws, context remains.
}
```

Even when `action.run()` succeeds, the worker keeps the old tenant. Never use `ThreadLocal` to hold long-lived request state, and never treat `InheritableThreadLocal` as a fix for pools.

### InheritableThreadLocal does not solve thread reuse

`InheritableThreadLocal` copies values when **a new child thread is created**. Pooled workers may already exist before the current request and thus never receive the new value—or they may capture a prior request's value at creation time and hold onto it indefinitely. That causes cross-tenant mix-ups, hard-to-debug races, and leaks. Spring Security likewise notes that choosing `SecurityContextHolder.MODE_INHERITABLETHREADLOCAL` requires careful understanding; it does not make an independent application tenant context safe for task queues.

**Rule:** context must be **installed close to task execution from a verified scope**, and **cleaned up in `finally`**. Never rely on pooled-thread inheritance.

## 5. Safe pattern: immutable scope and lexical boundaries

A Java 17 record:

```java
public record AuthorizedTenantScope(
        String subjectId,
        String tenantId) {

    public AuthorizedTenantScope {
        if (subjectId == null || subjectId.isBlank()
                || tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Missing tenant identity");
        }
    }
}
```

A record is shallowly immutable; if it contains a `Set` or `List`, copy via `Set.copyOf(...)`/`List.copyOf(...)` so callers cannot mutate it after submission. **Validating nonblank values in a record constructor does not prove the subject/tenant has permissions.** Only the designated policy service may construct authorized scopes used across security boundaries.

Wrapper pattern:

```java
final class TenantContext {

    private static final ThreadLocal<AuthorizedTenantScope> CURRENT =
            new ThreadLocal<>();

    static AuthorizedTenantScope require() {
        AuthorizedTenantScope scope = CURRENT.get();
        if (scope == null) {
            throw new IllegalStateException("Missing authorized tenant context");
        }
        return scope;
    }

    static <T> T callWith(
            AuthorizedTenantScope scope,
            java.util.concurrent.Callable<T> task) throws Exception {

        if (scope == null || task == null) {
            throw new IllegalArgumentException("Missing scope or task");
        }

        if (CURRENT.get() != null) {
            throw new IllegalStateException("Nested tenant context prohibited");
        }

        CURRENT.set(scope);
        try {
            return task.call();
        } finally {
            CURRENT.remove();
        }
    }
}
```

This is an **integration snippet**, not a standalone file because it uses the record above. Its benefits:

- If no resolved tenant is present, `require()` fails instead of returning “all tenants.”
- Whether a task succeeds or throws, `finally` clears the context.
- Prohibits nested contexts under this contract to prevent silently swapping tenants mid-transaction.
- Never calls `set` from a controller based solely on headers.
- Prevents tasks from mutating the scope object when designed cleanly as immutable.

**Restore-previous pattern:** some projects legitimately allow same-tenant nested calls; they can snapshot `previous = CURRENT.get()`, install scope, and in `finally` call `remove()` if `previous` was null or `set(previous)` otherwise. If **cross-tenant** nesting is ever permitted, enforce explicit cross-tenant authorization—never treat “restore” as an implicit right to switch tenants.

### Why does `finally` matter?

`finally` runs when a task returns normally or throws a synchronous exception. It also runs when `InterruptedException` unwinds the stack cleanly. However, on a process crash, hard kill, infinite uninterruptible loop, or JVM termination, `finally` is not guaranteed to run. Workers need timeouts, cooperative cancellation, and proper isolation/monitoring.

## 6. Runnable Java 17: a single pooled thread running multiple tenants

This standalone example serves three goals:

1. Construct scopes only after policy cross-checks actor/tenant against memberships and resource tenants.
2. Use **a single worker thread** so missing cleanup is immediately exposed.
3. Prove the context is empty after success, after an exception, and after permission revocation.

File `TenantBackgroundLab.java`:

```java
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class TenantBackgroundLab {

    record Job(String actor, String requestedTenant, long documentId) {}

    record AuthorizedScope(String actor, String tenant) {}

    static final class TenantContext {
        private static final ThreadLocal<AuthorizedScope> CURRENT =
                new ThreadLocal<>();

        static AuthorizedScope current() {
            return CURRENT.get();
        }

        static <T> T callWith(
                AuthorizedScope scope, Callable<T> task) throws Exception {
            if (scope == null || task == null || CURRENT.get() != null) {
                throw new IllegalStateException("Invalid tenant boundary");
            }
            CURRENT.set(scope);
            try {
                return task.call();
            } finally {
                CURRENT.remove();
            }
        }
    }

    static final class Policy {
        private final Map<String, Set<String>> activeMemberships =
                new ConcurrentHashMap<>();

        private final Map<Long, String> resourceTenants =
                Map.of(11L, "alpha", 12L, "alpha", 21L, "beta");

        Policy() {
            activeMemberships.put("alice", Set.of("alpha"));
            activeMemberships.put("bob", Set.of("alpha", "beta"));
        }

        AuthorizedScope authorize(Job job) {
            if (job == null || job.actor() == null
                    || job.requestedTenant() == null
                    || !job.requestedTenant().matches("[a-z][a-z0-9-]*")
                    || !activeMemberships.getOrDefault(
                            job.actor(), Set.of()).contains(job.requestedTenant())
                    || !job.requestedTenant().equals(
                            resourceTenants.get(job.documentId()))) {
                throw new SecurityException("Denied");
            }
            return new AuthorizedScope(
                    job.actor(), job.requestedTenant());
        }

        void revoke(String actor, String tenant) {
            activeMemberships.computeIfPresent(actor, (key, before) -> {
                Set<String> next = new HashSet<>(before);
                next.remove(tenant);
                return Set.copyOf(next);
            });
        }
    }

    private static String workerState(ExecutorService pool)
            throws Exception {
        Future<String> state = pool.submit(() ->
                TenantContext.current() == null ? "EMPTY" : "LEAK");
        return state.get();
    }

    private static String runJob(
            ExecutorService pool,
            Policy policy,
            Job job,
            boolean failInside) throws Exception {

        Future<String> future = pool.submit(() -> {
            // Re-resolve when worker RUNS; never trust Job.requestedTenant.
            AuthorizedScope checked = policy.authorize(job);

            return TenantContext.callWith(checked, () -> {
                if (failInside) {
                    throw new IllegalStateException("Simulated failure");
                }
                return checked.tenant() + "/" + job.documentId();
            });
        });

        try {
            return future.get();
        } catch (ExecutionException ex) {
            Throwable cause = ex.getCause();
            if (cause instanceof SecurityException) {
                return "DENIED";
            }
            if (cause instanceof IllegalStateException) {
                return "FAILED";
            }
            throw ex;
        }
    }

    public static void main(String[] args) throws Exception {
        Policy policy = new Policy();

        try (var ignored = new java.io.Closeable() {
            @Override
            public void close() {
                // Do not use this pattern to close executors in Java 17.
            }
        }) {
            ExecutorService pool = Executors.newSingleThreadExecutor();
            try {
                System.out.println("before=" + workerState(pool));

                System.out.println("alice-alpha=" + runJob(
                        pool, policy, new Job("alice", "alpha", 11L), false));
                System.out.println("after-alpha=" + workerState(pool));

                System.out.println("bob-beta=" + runJob(
                        pool, policy, new Job("bob", "beta", 21L), false));
                System.out.println("after-beta=" + workerState(pool));

                System.out.println("failed=" + runJob(
                        pool, policy, new Job("alice", "alpha", 12L), true));
                System.out.println("after-failure=" + workerState(pool));

                policy.revoke("bob", "beta");
                System.out.println("after-revocation=" + runJob(
                        pool, policy, new Job("bob", "beta", 21L), false));
                System.out.println("after-denied=" + workerState(pool));

                System.out.println("wrong-resource=" + runJob(
                        pool, policy, new Job("alice", "alpha", 21L), false));
                System.out.println("after-wrong-resource=" + workerState(pool));

                System.out.println("main-thread="
                        + (TenantContext.current() == null ? "EMPTY" : "LEAK"));
            } finally {
                pool.shutdown();
                if (!pool.awaitTermination(
                        5, java.util.concurrent.TimeUnit.SECONDS)) {
                    pool.shutdownNow();
                }
            }
        }
    }
}
```

**Structure explanation:** `Policy.authorize` uses server memberships and resource-tenant mappings; `Job.requestedTenant` is strictly input data. Only when policy permits does the worker place `AuthorizedScope` into `ThreadLocal`. After each job, `main` submits an observer task inspecting `ThreadLocal` on **the exact reused worker thread**. This catches leakage far better than checking `ThreadLocal` on the main thread alone.

Command to run on Java 17+:

```bash
javac TenantBackgroundLab.java
java TenantBackgroundLab
```

Stdout from the code:

```text
before=EMPTY
alice-alpha=alpha/11
after-alpha=EMPTY
bob-beta=beta/21
after-beta=EMPTY
failed=FAILED
after-failure=EMPTY
after-revocation=DENIED
after-denied=EMPTY
wrong-resource=DENIED
after-wrong-resource=EMPTY
main-thread=EMPTY
```

What this proves:

- Alice runs document 11 in alpha; Bob runs document 21 in beta while holding membership.
- Alice's task deliberately throws an exception **after setting context**. `finally` still calls `remove()`, leaving the worker empty for the next task.
- Bob/beta membership is revoked **before a new job runs**; policy re-checks and returns `DENIED`.
- Alice cannot use tenant alpha to operate on beta's document 21.
- The main thread context stays empty; workers do not share `ThreadLocal` with `main`.

**Demo scope:** no JWT, Spring, Kafka, or real database; `actor` in `Job` is illustrative data. Production must bind actors to trusted origins (producer identity, signed capabilities, authenticated users, or service policies) rather than letting clients submit `"bob"` and trusting it. The example deliberately uses `newSingleThreadExecutor()` to prove cleanup, not as a recommendation to run all work single-threaded.

### Production code is even simpler

In real code, drop the no-op `try (var ignored = ...)`; just write:

```java
ExecutorService pool = Executors.newFixedThreadPool(4);
try {
    // Submit and await controlled tasks.
} finally {
    pool.shutdown();
}
```

This is a snippet, not a standalone program. In Java 17, `ExecutorService` does **not yet** implement `AutoCloseable` as in newer JDKs, so avoid `try (pool)` when targeting Java 17. The demo used a no-op wrapper solely to keep resource management via `finally` clear.

## 7. Three distinct moments: capture, execute, and cleanup

### Capture-time: when enqueueing/submitting

Once a request is authorized, the app can create an immutable `AuthorizedTenantScope`. Never capture raw `HttpServletRequest`, mutable principal objects, live transactions, or JDBC Connections to hand off to workers.

```text
t0: Alice's request authenticates, alpha membership is ACTIVE
t1: Scope(alice, alpha) is created
t2: Job is submitted
```

### Execute-time: when the worker actually runs

```text
t3: Alice's membership is revoked
t4: Worker runs job
```

If business rules require immediate revocation, the worker at `t4` must **re-authorize**, rather than trusting the `t1` snapshot alone. For ultra-short immediate tasks where policy tolerates brief lag, a scoped snapshot may be used with explicit SLAs and auditing.

### Cleanup-time: regardless of outcome

```text
try:
    set verified scope
    run operation
finally:
    clear / restore context
```

Cleanup must cover:

- Tenant `ThreadLocal`.
- `SecurityContextHolder` if worker code sets it manually (Spring wrappers manage their own lifecycle).
- Logging `MDC`/trace context if the app populates it.
- Database connection/schema/RLS tenant settings when using connection-bound state.
- Request-scoped metrics/diagnostics stored in application thread-locals.

A Java `finally` block **does not automatically reset every kind of state**. Check the cleanup contract of each context API you use.

## 8. SecurityContextHolder and tenant context are separate concerns

Servlet Spring Security typically stores `SecurityContext` in `SecurityContextHolder` per thread (default strategy). When hopping to a new thread, context may disappear. Spring Security provides:

- `DelegatingSecurityContextRunnable`.
- `DelegatingSecurityContextCallable`.
- `DelegatingSecurityContextExecutor`.
- `DelegatingSecurityContextExecutorService`.
- `DelegatingSecurityContextAsyncTaskExecutor`.
- `DelegatingSecurityContextTaskScheduler` and related classes.

Official docs state that `DelegatingSecurityContextRunnable` installs the caller's `SecurityContext` on the worker and calls `SecurityContextHolder.clearContext()` in `finally`. Yet it **handles only SecurityContext**—it does not automatically propagate a custom application `TenantContext`.

```text
Spring Security wrapper:
  Capture Authentication/SecurityContext
  |
  v
Run task with SecurityContext
  |
  v
Clear SecurityContextHolder

Application tenant wrapper:
  Capture authorized tenant scope
  |
  v
Run task with TenantContext
  |
  v
Remove/restore tenant context
```

### Be careful when capturing Authentication

`Authentication`/`SecurityContext` can contain authorities, credentials, details, or mutable data. Never persist this raw object for long-running durable jobs. Never assume “authorized at enqueue” implies “authorized at execution.” If a wrapper is constructed with **a fixed SecurityContext**, every task runs under that same principal; that is valid only when intentionally using a fixed service identity with strictly bounded operations.

## 9. Spring @Async: configuring a TaskDecorator for tenant scope

Spring Framework's `TaskDecorator` wraps a `Runnable` at the moment the executor accepts a task; this is the right hook to **capture scope on the submitting thread** and install it in the worker around `run()`.

Assuming the app has `TenantContext.require()` and `TenantContext.callWith(...)` as in section 5, plus an `AuthorizedTenantScope` record created by policy:

```java
import java.util.concurrent.Callable;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
class AsyncTenantConfiguration {

    @Bean("tenantWorkerExecutor")
    ThreadPoolTaskExecutor tenantWorkerExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(50);
        executor.setThreadNamePrefix("tenant-worker-");

        TaskDecorator tenantDecorator = task -> {
            // decorate runs on the SUBMITTING thread.
            AuthorizedTenantScope captured = TenantContext.require();

            return () -> {
                try {
                    TenantContext.callWith(captured, () -> {
                        task.run();
                        return null;
                    });
                } catch (RuntimeException ex) {
                    throw ex;
                } catch (Exception checked) {
                    throw new IllegalStateException(
                            "Tenant task failed", checked);
                }
            };
        };

        executor.setTaskDecorator(tenantDecorator);
        return executor;
    }
}
```

**This is an integration snippet**, not a standalone Maven project. Given `callWith` accepting `Callable<T>` and prohibiting nested scopes, the code ensures cleanup when `task.run()` throws a runtime exception.

Understand these details carefully:

- `TaskDecorator.decorate` runs at submission time. Therefore, `TenantContext.require()` must already hold a valid scope **before calling `@Async`**.
- Never capture from `ThreadLocal` **inside the worker**; by the time the worker runs, it is a different thread.
- Never read tenant directly from a header inside the decorator; the decorator only copies an already-authorized result.
- If scope is missing at submit time, fail closed; schedulers/queue consumers outside HTTP requests need their own path to construct scopes.
- Queue-full rejections can occur on submit; define retry/backpressure policies. Never swallow rejection errors and report “job queued” when it was not queued.
- `TaskDecorator` may wrap an internal `Runnable` backing a `Future`. Spring docs note that exceptions from Future-based tasks may not propagate from `run()` as expected; monitor `Future.get()`/`CompletableFuture`, metrics, and error handlers rather than relying solely on the outer decorator.

### Where should @Async be invoked?

```java
@Service
class ExportFacade {

    private final TenantResolver resolver;
    private final AsyncExportService worker;

    ExportFacade(TenantResolver resolver, AsyncExportService worker) {
        this.resolver = resolver;
        this.worker = worker;
    }

    void requestExport(Authentication auth, String requestedTenant, long docId) {
        AuthorizedTenantScope scope =
                resolver.require(auth, requestedTenant, "EXPORT");

        TenantContext.callWith(scope, () -> {
            worker.export(docId); // Call through @Async bean proxy.
            return null;
        });
    }
}

@Service
class AsyncExportService {

    @Async("tenantWorkerExecutor")
    public CompletableFuture<Void> export(long documentId) {
        AuthorizedTenantScope scope = TenantContext.require();
        // Revalidate membership/permission here if needed.
        // Query resource by (scope.tenantId(), documentId).
        return CompletableFuture.completedFuture(null);
    }
}
```

This pattern is a **wiring snippet**, incomplete because `TenantResolver`, repositories, re-authorization rules, exception handling, and persistence belong to your app. Because `callWith` throws checked `Exception`, callers must either declare `throws Exception` or handle it properly; never copy a method ignoring checked exceptions into production assuming it compiles.

Self-invoking `this.export(...)` inside the same bean bypasses Spring AOP `@Async`. Use a separate bean, call through its proxy, and write an integration test confirming the worker thread differs from the request thread.

## 10. Combining DelegatingSecurityContextAsyncTaskExecutor when identity is also needed

If an in-process task genuinely needs the caller's `SecurityContext` to invoke method security, wrap the tenant-decorated `ThreadPoolTaskExecutor` in `DelegatingSecurityContextAsyncTaskExecutor`.

```java
@Bean("securityAndTenantExecutor")
AsyncTaskExecutor securityAndTenantExecutor(
        @Qualifier("tenantWorkerExecutor")
        ThreadPoolTaskExecutor tenantExecutor) {

    return new DelegatingSecurityContextAsyncTaskExecutor(tenantExecutor);
}
```

Imports:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor;
```

When using the single-argument constructor taking the delegate executor, the Spring Security wrapper captures the submitting thread's `SecurityContext` automatically. The tenant `TaskDecorator` captures `AuthorizedTenantScope` separately; each wrapper cleans up its own context.

**Two reminders:**

1. If an `@Async` method names `"securityAndTenantExecutor"`, verify that exact bean is selected rather than a fallback default executor. Test both `SecurityContext` and `TenantContext` **inside the worker**.
2. `SecurityContext` propagation does not replace **re-evaluating authorization**. For jobs queued for hours, do not reuse an old user `SecurityContext`; use service identity/capabilities and live membership lookup in the consumer.

### Never set SecurityContextHolder recklessly

`SecurityContextHolder.setContext(...)` can be valid inside a custom wrapper with `try/finally`, though Spring Security's built-in wrappers are preferred. If you fabricate a fake context with `ROLE_ADMIN` just to make a job run, you open a privilege escalation path whenever job payloads are insufficiently constrained and audited.

## 11. MDC and tracing: logs need the right tenant, never as a permission source

SLF4J/Logback MDC is commonly used:

```java
MDC.put("tenantId", scope.tenantId());
MDC.put("subjectId", scope.subjectId());
```

MDC can be `ThreadLocal`-backed and also needs cleanup. Calling `MDC.clear()` blindly can wipe an outer wrapper's trace ID. With nested contexts, snapshot and restore the previous map:

```java
Map<String, String> previous = MDC.getCopyOfContextMap();

try {
    MDC.put("tenantId", scope.tenantId());
    MDC.put("subjectId", scope.subjectId());
    task.run();
} finally {
    if (previous == null) {
        MDC.clear();
    } else {
        MDC.setContextMap(previous);
    }
}
```

This is an **integration snippet** requiring SLF4J `MDC`, `Map`, and `task`. Log only the resolved tenant in MDC—never log a raw client-supplied header as a trusted audit value. Never log JWTs, bearer tokens, cookies, or sensitive contents. If using Spring's `ContextPropagatingTaskDecorator` built on Micrometer context propagation, register a `ThreadLocalAccessor` for any **custom** context you want propagated automatically, and still guard the tenant boundary. The default decorator handles propagation of registered contexts; **it does not understand business tenant verification**.

## 12. Async tasks must never switch tenants mid-flight

Each task should be bound to **one** explicit tenant scope. When multiple tenants must be processed:

```text
For each authorized tenant:
  establish scope(tenant)
  process tenant-specific batch
  finally cleanup
Move to next tenant
```

Avoid:

```java
TenantContext.set("alpha");
processAlpha();
TenantContext.set("beta");
processBeta();
```

That leaks alpha if `processAlpha()` throws or a nested call uses the stale context. Use two separate lexical scopes, with tenant transitions explicitly permitted by service/job policy.

When processing documents in tenant `alpha`, repositories must query with tenant scope:

```sql
SELECT id, body
FROM documents
WHERE tenant_id = :authorized_tenant
  AND id = :document_id;
```

Never let a worker fetch a document by ID alone and decide “if tenant differs, don't return it,” because side effects, logs, joins, or lazy loading may already touch unauthorized data. For updates, use conditional SQL or transactions + re-checks:

```sql
UPDATE documents
SET status = 'EXPORTED'
WHERE id = :document_id
  AND tenant_id = :authorized_tenant
  AND status = 'PENDING';
```

After `UPDATE`, inspect affected rows so zero rows is never treated as success. Wrap DB updates + outbox/events in a transaction as needed; emitting an “exported” event before commit causes inconsistencies.

## 13. Durable queues: tenantId in a message is only a selector

Example message:

```json
{
  "jobId": "job-123",
  "tenantId": "alpha",
  "requestedBy": "alice",
  "documentId": 42,
  "action": "EXPORT",
  "policyVersion": 7
}
```

Nothing in this JSON proves user Alice is authorized to EXPORT. Producers can be compromised, clients might publish directly to queues, or messages can be replayed. Consumers must:

1. Authenticate producer/service identity and topic/queue write permissions.
2. Validate schema, type/action allowlist, canonical tenant ID, and payload size.
3. Enforce idempotency by `(tenantId, jobId, action)` or an equivalent key.
4. Verify the source of truth for `requestedBy` (a DB job record written after authorization, a signed capability, or a trusted producer contract).
5. Look up live memberships/grants/permissions or a policy-approved snapshot/capability.
6. Match `documentId` against the resource tenant in the database.
7. Install `AuthorizedTenantScope` before invoking domain services.
8. Clear context in `finally` even if the handler throws.
9. Handle retries/DLQs without leaking data; log `jobId`, verified tenant, and reason codes, never tokens.

### Example consumer logic (pseudocode)

```text
onMessage(message):
    trustedOrigin = verifyProducer(message)
    job = jobRepository.findById(message.jobId)

    require trustedOrigin authorized to deliver job
    require message.tenantId equals job.tenantId
    require job.status is PENDING
    require actor/job capability still permitted for action
    require document.tenantId equals job.tenantId

    scope = authorizedScope(job.actor, job.tenantId, job.action)

    try:
        install scope
        execute idempotent business operation
        mark job COMPLETE atomically with outbox/event
    finally:
        clear scope, SecurityContext if manually set, MDC and DB state
```

This is intentionally pseudocode. The crucial point is that **the consumer never takes `tenantId` from the message and hits the DB directly**. A job queued while membership was ACTIVE may run after membership was REVOKED; policy must decide whether to cancel the job or honor the submission-time authorization snapshot with explicit TTLs and auditing.

### Retries and dead-letter queues

A retried message may run on a different worker or the same thread. Never rely on context from a prior attempt. Re-authorize on **every attempt**; there is no need to ship raw `SecurityContext` over queues. If a job committed yet ACK failed, consumers must be idempotent so retries do not send duplicate emails, double-update, or produce duplicate tenant outputs.

## 14. Schedulers and Spring Batch: no request principal

`@Scheduled`/cron jobs do not run inside an authenticated user HTTP request. When a scheduler generates reports for tenants, it needs a **service identity** and an authorized tenant list fetched from a trusted server source:

```java
@Scheduled(cron = "0 0 * * * *")
public void hourlyReports() {
    for (String tenantId : tenantRegistry.authorizedForReporting()) {
        AuthorizedTenantScope scope =
                reportPolicy.resolveServiceScope(tenantId);

        // Each tenant has its own boundary; clean up when finished.
        tenantRunner.run(scope,
                () -> reportService.generateForTenant(scope.tenantId()));
    }
}
```

This integration snippet assumes `TenantRegistry`, `ReportPolicy`, `TenantRunner`, and `ReportService` are provided. Service accounts should not hold a blanket global bypass; if a workflow requires global admin rights, make them explicit, audited, and tightly bounded.

**Spring Batch:** a tenant ID can be passed as `JobParameters` so restarts target the right tenant, yet job parameters remain **data**, not authorization. Steps/workers must validate service identity, tenant entitlement, and reader/writer predicates; partitioned steps or multi-threaded chunks must install isolated scopes and clean up per step/task. Never store a mutable singleton `"currentTenant"` field inside an `ItemReader` shared across partitions.

### Fixed tasks running for a single tenant

A tenant ID may come from managed scheduler configuration instead of user input. Even then, verify the tenant remains ACTIVE, the service account remains authorized, and DB/queries stay within that tenant. “Trusted config file” does not mean policies never change.

## 15. CompletableFuture, ExecutorService, and lost context

With `CompletableFuture.supplyAsync(...)` **omitting an executor**, work runs on the common ForkJoin pool, which does not automatically carry `SecurityContextHolder` or custom `TenantContext` under your contract.

```java
// Counterexample: inside supplier, tenant may be missing.
CompletableFuture.supplyAsync(() -> repository.loadCurrentTenant());
```

Use an executor configured for propagation and/or pass immutable scope explicitly:

```java
AuthorizedTenantScope checked = tenantResolver.require(...);

CompletableFuture<Result> future =
        CompletableFuture.supplyAsync(
                () -> service.loadForTenant(
                        checked.tenantId(),
                        checked.subjectId()),
                tenantAwareExecutor);
```

This is an **integration snippet**; `Result`, resolver, service, and executor are application-defined. **Important:** if `service.loadForTenant` blindly trusts its arguments without re-checking resources/permissions, vulnerabilities remain. Proper scope passing does not replace policy enforcement.

### Capture at submission, not in the worker

If writing a decorator to propagate `ThreadLocal`:

```java
Runnable wrapAtSubmission(Runnable original) {
    AuthorizedTenantScope captured = TenantContext.require();
    return () -> TenantContext.runWith(captured, original);
}
```

This is integration Java pseudocode; `TenantContext.runWith` should be built atop `callWith` and always clean up. `wrapAtSubmission` must run **before** handing the `Runnable` to the executor, whereas the returned lambda runs on the worker. Capturing scope inside the worker lambda by reading `ThreadLocal` there finds it null or stale.

### Cancellation and timeouts

When `Future.cancel(true)` interrupts a worker, tasks must honor interruption. `finally` runs only when the task exits its executing method; blocking libraries ignoring interrupts can hold tenant context longer. Never work around that by forcibly reusing a busy thread. On submission rejection before execution starts, worker context was never installed, yet producers must recognize the task was never enqueued.

## 16. Reactive: Reactor Context is not ThreadLocal

In Spring WebFlux/reactive pipelines, execution hops threads continuously. Using `ThreadLocal` as in servlet requests breaks the model. Reactor provides `Context` bound to **each subscription**, and Spring Security Reactive provides `ReactiveSecurityContextHolder`.

Example **integration snippet**:

```java
static final String TENANT_SCOPE_KEY = "authorizedTenantScope";

Mono<String> operation(AuthorizedTenantScope verifiedScope) {
    return Mono.deferContextual(context -> {
        AuthorizedTenantScope scope =
                context.get(TENANT_SCOPE_KEY);
        return repository.findTitle(scope.tenantId())
                .map(title -> scope.tenantId() + ":" + title);
    }).contextWrite(context ->
            context.put(TENANT_SCOPE_KEY, verifiedScope));
}
```

Assumes `repository.findTitle` returns `Mono<String>` and `verifiedScope` was authorized earlier. **Putting a raw tenant string into Reactor Context does not make it authorized.** Reactor Context differs from `ThreadLocal`: values flow per subscription, so pure Reactor Contexts need no manual `ThreadLocal.remove()` when a subscription finishes. However, when bridging into blocking JDBC code using `ThreadLocal`, establish an explicit boundary with its own cleanup.

Never store a `ContextView` or subscriber context in singleton state shared across requests. When using `publishOn`/`subscribeOn`, rely on version-appropriate Reactor context propagation APIs rather than copying `ThreadLocal` manually.

### SecurityContext in reactive flows

`ReactiveSecurityContextHolder.getContext()` is the reactive API for `SecurityContext`, not synchronous `SecurityContextHolder.getContext()`. Reactive context stays inside the pipeline; when crossing onto external queues, apply the payload/trust/re-authorization rules from section 13.

## 17. Database connections, schemas, and RLS also require proper cleanup

Multi-tenant systems may use:

1. **Shared schema with `tenant_id` column**: every SELECT/UPDATE/DELETE/COUNT/GROUP BY constrains tenant.
2. **Schema per tenant**: connections switch `search_path`/current schema.
3. **Database per tenant**: DataSource selected by authorized tenant.
4. **PostgreSQL RLS**: DB enforces policies from the transaction's tenant context.

Connection pooling reuses physical connections across tenants. Changing schema or session state without resetting lets a later request/job run under the prior tenant **even if Java ThreadLocal was removed**.

### Shared-table query

```sql
SELECT id, title
FROM documents
WHERE tenant_id = :authorized_tenant
  AND id = :document_id;
```

### PostgreSQL RLS with transaction-local setting

```sql
BEGIN;

SELECT set_config('app.tenant_id', :authorized_tenant, true);

SELECT id, title
FROM documents
WHERE id = :document_id;

COMMIT;
```

In PostgreSQL, passing `true` to `set_config(name,value,is_local)` scopes the setting to the transaction, reducing session-state leaks across pooled connections. Even so, DB roles and RLS policies must prevent bypasses, and users must not execute arbitrary SQL under the same role to overwrite `app.tenant_id`.

Async tasks normally run in **their own transactions**; a request's transaction **never propagates automatically to workers**. Workers must open their own transactions, configure DB tenant state for the scope, execute queries/updates, finish the transaction, and return clean connections to the pool.

### Never feed raw tenants into schema/database routing

```text
raw X-Tenant-Id -> "schema_" + value -> SET search_path
```

is unsafe without authorization, validation, and registry mapping. When using `AbstractRoutingDataSource` or Hibernate multi-tenancy, routing keys must be canonical authorized tenants—never fall back to a “default datasource” when context is missing, as that can expose global data.

## 18. MDC, transactions, caches, and observability must align

When generating a CSV report for tenant alpha, SQL filtering alone is insufficient if:

- Object storage file keys omit tenant and get overwritten by another tenant.
- Cache keys use `report:{jobId}` where `jobId` is unique only per tenant.
- Audit logs record the raw header tenant instead of the resolved scope.
- Trace contexts bleed across two tasks, misleading monitoring tools about the tenant.
- Metric labels include unbounded raw tenant strings, causing cardinality explosions.

Rule:

```text
authorization scope = sole tenant source

DB predicate / routing  -> scope.tenantId
cache key               -> tenantId + subject/entitlement + operation
object storage path     -> validated tenantId + jobId
idempotency key         -> tenantId + jobId/action
audit tenant            -> scope.tenantId
MDC tenant              -> scope.tenantId (for logging only)
```

Having tenant in a key never replaces authorization when reading caches or object storage. Verify the caller/job is allowed to access the object, and ensure storage IAM does not expose buckets/paths improperly.

With OpenTelemetry/Micrometer, context propagation may be automatic or manual depending on stack/version. Never confuse “trace ID propagated” with “tenant scope verified.” When changing async engines, regression tests must prove tenant context **is neither lost nor leaked** on the actual executor in use.

## 19. Avoid turning a TaskDecorator into a vulnerability

A `TaskDecorator` propagates context, **not an authorization gateway**. Common anti-patterns:

**A. Capturing raw headers at submission.**

```java
String tenant = request.getHeader("X-Tenant-Id");
executor.execute(() -> TenantContext.set(tenant));
```

Result: clients pick any tenant with zero policy check.

**B. Using a fallback tenant.**

```java
String tenant = TenantContext.getOrDefault("public");
```

If context is lost across a thread hop, the task silently runs under the wrong tenant. Sensitive operations must fail closed when scope is missing.

**C. Decorator sets without removing.**

```java
return () -> {
    TenantContext.set(captured);
    task.run();
};
```

Whether the task throws or completes normally, the worker retains the old tenant. Always clean up in `try/finally`.

**D. Using a SecurityContext wrapper and assuming tenant came along.**

Spring Security propagates `SecurityContext` only, not arbitrary application `ThreadLocal`s. Test `TenantContext` independently.

**E. Running all jobs under a fixed global SecurityContext ROLE_ADMIN.**

An untrusted job payload can abuse the admin role to read across tenants. Bind service identities to controlled operation/tenant scopes rather than global bypasses.

**F. Capturing inside the wrapper before authorization.**

If `TenantContext` holds no scope at capture time, the wrapper should throw and refuse to enqueue rather than guessing a tenant from the request.

**G. Reusing a mutable scope object across tasks.**

Job A mutates `scope.tenantId`, causing job B to see the wrong value. Use records or immutable classes with defensively copied collections.

**H. Passing user tokens through queues.**

Tokens can leak, be replayed, expire, or carry wrong audiences. Use job identities, service auth, and consumer-side policies.

**I. Caching authorization indefinitely.**

Memberships get revoked while workers keep using stale snapshots; enforce TTLs/invalidation or execution-time checks per SLA.

**J. Forgetting DB context.**

Java `ThreadLocal` gets cleared while the pooled connection still holds schema alpha. Use transaction-scoped DB settings and resets.

## 20. Testing thread-reuse risks properly

Cleanup tests must not merely assert `TenantContext.current()==null` on the test thread. They must run at least two tasks on **the exact same worker thread**.

### Unit/integration matrix

| Case | Setup | What to assert |
| --- | --- | --- |
| Alpha job succeeds | Pool size 1, alpha scope | Sees alpha inside |
| Subsequent beta job | Same worker, beta scope | Sees beta inside, never alpha |
| Missing scope | Submit to context-requiring executor | Fails closed, no default tenant |
| Exception inside task | Task throws after setting scope | Job fails; next task sees EMPTY |
| Interrupted/cancelled | Task handles interrupt cooperatively | Once finished, context is clean |
| Rejection/queue full | Executor rejects task | Never reports queued; producer handles it |
| Revoked membership | Enqueue before revoke, run after | Denied per execution-time policy |
| Wrong resource tenant | URL/job picks alpha, resource in beta | Denied |
| Revoked role | Actor stays member, lacks action | Operation denied |
| Nested different tenant | Alpha task tries opening beta | Denied or passes explicit cross-tenant policy |
| Multi-worker pool | Stress with 2–8 threads | Zero cross-task tenant leaks |
| Single-tenant scheduler | Service identity scoped to alpha | Queries alpha only |
| Multi-tenant scheduler | Loop with cleanup | Each tenant isolated |
| Queue replay | Duplicate jobId/tenant | Idempotent, never executes twice |
| Pooled DB connections | Pool size 1, alternate alpha/beta | No leftover schema/RLS state |
| Cache | Two tenants share local jobId | Outputs never swapped |
| MDC | Task succeeds/fails | Tenant label restored/removed |
| Reactive | Two differently scoped subscribers | No mixing across Scheduler hops |
| Propagated SecurityContext | Spring executor wrapper | Right Authentication, independent tenant cleanup |

### Testing exception paths

```java
ExecutorService pool = Executors.newSingleThreadExecutor();
try {
    Future<?> failed = pool.submit(() -> {
        TenantContext.runWith(alphaScope, () -> {
            throw new IllegalStateException("boom");
        });
    });

    assertThrows(ExecutionException.class, failed::get);

    Future<Boolean> clean = pool.submit(
            () -> TenantContext.currentOrNull() == null);

    assertTrue(clean.get());
} finally {
    pool.shutdownNow();
}
```

This is a **test snippet**, assuming `TenantContext.runWith`, `currentOrNull`, and `alphaScope` exist. It shows the right worker-pool testing strategy, though it is not a standalone JUnit class. The Java 17 lab in section 6 implements the same verification without JUnit.

### Never test only two successful jobs

An implementation forgetting `remove()` can still pass an “alpha then beta” test if the decorator **always overwrites** tenant before each job. Only submitting an **observer task asserting empty context between jobs**—or intentionally running an unscoped task—catches context leaks. Section 6 uses that exact technique.

## 21. Integration tests with Spring Boot @Async

Integration tests need:

- Real `@EnableAsync` and `ThreadPoolTaskExecutor`.
- Real scope resolver and tenant decorator.
- A service annotated `@Async("tenantWorkerExecutor")` invoked via **another bean/proxy**.
- `CompletableFuture<T>` to await completion rather than using `Thread.sleep` as primary synchronization.
- An inspector task checking worker context after success and failure.
- `@WithMockUser`/`jwt()` when authentication is needed, remembering mock security does not verify real JWT signatures.
- Active membership changed between submit and execute, coordinated deterministically with `CountDownLatch`.
- Assertions on DB row IDs/counts and zero cross-tenant side effects, not merely context strings.

Structural example (pseudocode):

```text
given:
  alice active in alpha
  doc 11 belongs to alpha
  doc 21 belongs to beta

when:
  submit export(11) with AuthorizedTenantScope(alpha)
  worker waits at latch
  revoke Alice from alpha
  release latch

then:
  worker re-authorizes at execution time
  export denied
  no report/object storage output
  worker context cleaned even after denial
```

If a job starts before permissions are revoked, the result depends on your consistency contract; tests must explicitly define the linearization point or policy snapshot instead of assuming ambiguous wall-clock timing.

### Spring MVC async requests differ from background queues

Spring MVC supports async request processing, and Spring Security integrates with several async constructs. That does not mean every `@Async`, custom `Executor`, `CompletableFuture`, scheduled task, Kafka listener, or custom `ThreadLocal` tenant is **propagated automatically**. Test the exact executor/concurrency model you run.

## 22. Failure paths, timeouts, and retries

Beyond happy paths:

- Task finishes, yet queue ACK fails → duplicate delivery.
- Task throws after installing tenant context.
- Task is interrupted by shutdown/cancellation.
- Worker process restarts before updating job status.
- Pool saturates and rejects work.
- Database times out while setting local tenant config.
- Membership service is temporarily unavailable.
- Task attempts to open a new transaction after the request transaction closed.

Handling principles:

1. **Idempotency** keyed on tenant + job identity.
2. Worker-bounded DB transactions, never reusing the request thread's entity manager/connection.
3. Re-authorization on every execution attempt when policy requires it.
4. Fail closed whenever tenant is missing or permissions cannot be verified.
5. Sensible timeouts; ensure tasks respect interruption.
6. Context cleanup always in `finally` of an effective wrapper.
7. Never log or return raw tokens, credentials, or cross-tenant data in errors.
8. Protect dead-letter-queue payloads and strictly control replays.

**Important:** membership-service outages should not blindly masquerade as “403”; they may be operational errors (retry/503), yet must **never be treated as granted**. Denials due to expired/revoked rights differ from transient DB-unavailable failures; emit accurate reason codes so retries never spin in infinite loops.

## 23. Comparing tenant propagation mechanisms

| Approach | Best suited for | Limitations / warnings |
| --- | --- | --- |
| `AuthorizedTenantScope` parameter | Service → repository, explicit | Must pass through APIs; unsafe if callers fabricate it |
| `ThreadLocal` + lexical wrapper | Legacy ORM/servlet, thread-bound code | Must capture properly, clean up, does not auto-propagate |
| Spring `TaskDecorator` | `ThreadPoolTaskExecutor`/`@Async` | Propagates only explicitly coded contexts; does not authorize |
| Spring `DelegatingSecurityContext...` | Passing `SecurityContext` across threads | Does not carry custom tenant `ThreadLocal`s |
| MDC | Logs/diagnostics | Never use as an authorization source |
| Reactor `Context` | WebFlux/reactive | Per-subscription, not global, does not auto-bridge blocking APIs |
| Durable job command | Kafka/RabbitMQ/DB outbox | Payload not trusted on its own; needs re-auth/identity/idempotency |
| Tenant-scoped service identity | Cron/schedulers/automation | Must bound permissions and audit |
| DB RLS/session-local | Persistence defense-in-depth | Requires proper DB roles/transactions/pooling |
| `InheritableThreadLocal` | Simple one-off child threads | Unreliable for thread pools/reuse, prone to stale data |

**Preferred choices:** immutable scope parameters at domain boundaries; context wrappers only when framework integration requires them; durable queues using job commands plus consumer re-authorization. Every boundary needs cleanup and tests.

## 24. Adoption checklist

- [ ] Authenticated principal is verified before resolving tenant.
- [ ] Tenant in headers/paths/messages is treated as a selector, not proof of permission.
- [ ] `AuthorizedTenantScope` is constructed only after membership/role/resource-policy checks.
- [ ] In-process tasks capture scope on the **submitting thread**, never on pooled workers.
- [ ] Durable tasks re-authorize at execution time rather than holding long-lived raw bearer tokens.
- [ ] Tenant context is installed close to execution and removed/restored in `finally`.
- [ ] `SecurityContextHolder` and custom `TenantContext` are propagated and cleaned up **separately**.
- [ ] MDC/trace contexts are restored; credentials are never logged.
- [ ] `InheritableThreadLocal` is never used as the default for thread pools.
- [ ] No shared mutable static “currentTenant” is used across requests.
- [ ] `@Async` is invoked via Spring proxies on the right executor.
- [ ] Missing scope never falls back to a default tenant; fails closed.
- [ ] Worker queries/updates carry tenant predicates; authoritative resource tenant is verified.
- [ ] Connection schema/RLS settings are configured and reset per transaction/connection.
- [ ] Caches, object storage, idempotency keys, and report paths isolate tenants.
- [ ] Schedulers/batches use dedicated service identities and per-tenant scopes.
- [ ] Queue consumers authenticate origin, validate payloads, re-authorize, and clean up.
- [ ] Tested two tenants sequentially **on the same thread**.
- [ ] Tested success, exception, interruption, rejection, revocation, and retries.
- [ ] Tested multiple workers, MDC, DB connection pools, and caches for zero leaks.
- [ ] Auditing and revocation SLAs are defined for background jobs.

**Conclusion:** `ThreadLocal`, Reactor `Context`, `SecurityContext`, and DB sessions are **state carriers**, not authorization sources. Tenant context must originate from **verified identity and policy**, be propagated deliberately to workers, be **re-verified when jobs run** where required, and be **cleaned up in `finally`** or an equivalent lifecycle hook. When a single worker serves thousands of tenants, the most important test is proving **no task ever inherits the previous task's context**.

## Official references

- [Spring Security — Concurrency Support](https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — TaskDecorator JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/task/TaskDecorator.html)
- [Spring Framework — ContextPropagatingTaskDecorator JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html)
- [Project Reactor — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [Spring Security — Reactive Security Context](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [PostgreSQL — Runtime Configuration Functions](https://www.postgresql.org/docs/current/functions-admin.html)

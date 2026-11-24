# ThreadLocal and the Context Cleanup Requirement to Prevent Identity Leakage

> **Core point:** In a **Servlet**-based Spring Security application, `SecurityContextHolder` stores `SecurityContext` in a `ThreadLocal` by default. This allows code on the **same request-processing thread** to read the current `Authentication` without passing it as a parameter through every method. However, **servlet container threads and thread pool threads are reused**. If code manually places an identity into `SecurityContextHolder` and **fails to clear it in `finally`**, the next request or task reusing that thread can observe the previous user's identity or authorities — a **security context leak that can cause privilege escalation and cross-user data exposure**. The standard Spring Security filter chain manages and clears the context at the end of a request; manually spawned threads, custom filters, custom authentication, and background executors must follow the corresponding lifecycle.

This lesson belongs to the **Security Context** topic in the **Spring Security – fundamentals** module. Examples use **Java 17+, Spring Boot 3.5.16, and Spring Security 6.5.x, Spring MVC/Servlet**. With **Spring WebFlux**, context is propagated via **Reactor Context** and `ReactiveSecurityContextHolder`, so Servlet ThreadLocal does not apply by default. Examples that manually construct authentication in unit tests are strictly for demonstrating how context is held and cleared, **not how real users log in**.

## 1. Learning objectives

By the end of this lesson, you can:

1. Explain Java `ThreadLocal` and why a variable "bound to a thread" is not a variable "bound to a request" or "bound to a user".
2. Distinguish `SecurityContextHolder`, `SecurityContext`, `Authentication`, `SecurityContextRepository`, and `HttpSession`.
3. Describe the filter that loads context at the start of a request and the cleanup mechanism at the end of a request, even when a handler throws an exception.
4. Point out the severe bug when a single-thread `ExecutorService` runs Alice's task then Bob's task and `ThreadLocal` data from Alice remains behind.
5. Write a `try/finally` pattern to clear context reliably regardless of whether execution succeeds or fails.
6. Explain why `SecurityContextHolder.clearContext()` differs from deleting a session or logging out.
7. Use `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextExecutor`, and corresponding wrappers to **propagate context per task** and **restore/clear** when the task finishes.
8. Identify the limitations of `MODE_INHERITABLETHREADLOCAL`, `MODE_GLOBAL`, `@Async`, and `CompletableFuture` without a security-configured executor.
9. Write tests verifying consecutive requests with different identities, thread-pool cleanup, exception paths, and no automatic identity propagation to background tasks.
10. Apply a review checklist for custom filters, custom login, thread pools, scheduled tasks, auditing, and reactive code.

## 2. How does Java's ThreadLocal work?

`ThreadLocal<T>` provides access to a **per-thread value**, not "per-user memory". Two different threads can read two different values through the same `ThreadLocal` variable. When a thread is reused, its value persists unless replaced or removed.

### 2.1. Standalone Java example, without Spring

Create `ThreadLocalDemo.java`:

```java
public class ThreadLocalDemo {
    private static final ThreadLocal<String> CURRENT =
        new ThreadLocal<>();

    public static void main(String[] args) throws Exception {
        Thread worker = new Thread(() -> {
            try {
                CURRENT.set("alice");
                System.out.println("worker=" + CURRENT.get());
            } finally {
                CURRENT.remove();
            }
            System.out.println("worker-after=" + CURRENT.get());
        }, "demo-worker");

        worker.start();
        worker.join();

        System.out.println("main=" + CURRENT.get());
    }
}
```

Compile and run with JDK 17+:

```bash
javac ThreadLocalDemo.java
java ThreadLocalDemo
```

**Expected exact stdout:**

```text
worker=alice
worker-after=null
main=null
```

Explanation:

- `CURRENT.set("alice")` only sets the value on the **worker thread**.
- `CURRENT.get()` on main remains null; ThreadLocal is not a shared global variable.
- `CURRENT.remove()` deletes the worker's mapping; it does not automatically destroy any "user session".
- `finally` guarantees cleanup is still invoked if code inside `try` throws an exception.
- This example creates a new thread that terminates, whereas in a **thread pool** a thread lives long and runs many tasks, making removal even more critical.

### 2.2. Risk when a thread pool reuses threads

```text
ExecutorService with a single worker thread named pool-1-thread-1

Task #1 (Alice)
  CURRENT.set("alice")
  processing
  NO remove()    <-- BUG
  return

Task #2 (Bob/anonymous) on the SAME thread
  CURRENT.get() -> "alice"    <-- IDENTITY LEAK

Task #3 (Charlie)
  may even inherit wrong data if not initialized/cleared
```

This is the core mechanism to understand, not necessarily a bug in Spring Security itself: **custom code outside the filter lifecycle** can leave stale values on a worker thread. A single thread object can serve countless requests in a servlet container; never treat a thread ID as a session ID or user ID.

### 2.3. Two distinct kinds of failures

- **Failing to propagate context:** Alice submits a background task to an executor on another thread, and the task sees `Authentication` as null and denies access or loses the actor. This is usually a functional bug and can mask authorization bugs.
- **Propagating or creating context and failing to clear it:** Alice's task leaves an authenticated principal behind when the thread is reused for Bob. This can be a **cross-task identity leakage vulnerability**, more severe than missing propagation.

The solution is **not** turning on a JVM-wide shared context, but **intentionally propagating identity for the right task and clearing/restoring after the task**.

## 3. Who is SecurityContextHolder in Spring Security?

### 3.1. Three related objects

```text
SecurityContextHolder
    |
    |  uses SecurityContextHolderStrategy (default ThreadLocal)
    v
SecurityContext
    |
    +-- Authentication
           |
           +-- principal      (trusted identity)
           +-- authorities    (roles/permissions)
           +-- credentials    (usually erased after auth)
           +-- details        (metadata if any)
```

`SecurityContextHolder` is the static API to access the context per strategy. `SecurityContext` holds an `Authentication`. `Authentication` represents either unauthenticated input or a trusted authentication result depending on where it is used; in a controller after filters, you normally work with an authenticated result or an anonymous token.

Commonly used APIs:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

SecurityContext context = SecurityContextHolder.getContext();
Authentication current = context.getAuthentication();

SecurityContext newContext = SecurityContextHolder.createEmptyContext();
newContext.setAuthentication(verifiedAuthentication);
SecurityContextHolder.setContext(newContext);

// When manually managing a scope:
SecurityContextHolder.clearContext();
```

This is a **snippet**; `verifiedAuthentication` must be created by a trusted authentication mechanism. Never read username/roles from a JSON request and call the `authenticated(...)` factory to self-mint a user before authorization.

### 3.2. Is getContext() null when anonymous?

Normally **no**. `SecurityContextHolder.getContext()` can return an empty context instead of null, while `context.getAuthentication()` may be null when no principal exists yet. In a standard Spring Security filter chain, `AnonymousAuthenticationFilter` may also set an `AnonymousAuthenticationToken`. The anonymous token can return `isAuthenticated()==true` at the interface level, yet **does not represent a logged-in user**.

Therefore:

```java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();

if (auth != null && auth.isAuthenticated()) {
    // NOT ENOUGH to conclude login used real credentials.
}
```

The snippet above is an anti-pattern for learning. At the HTTP boundary, use Spring Security rules `authenticated()`, `fullyAuthenticated()`, `hasRole(...)`, `hasAuthority(...)`; if code must distinguish anonymous, use `AuthenticationTrustResolver` or an equivalent policy check. Never use "token has flag true" as proof of an authorized actor.

### 3.3. getName() on the current thread is not yet permission on data

A request authenticated as Alice can read `auth.getName()=="alice"`. That only establishes identity. When Alice requests `GET /accounts/bob/invoices`, the service must still check owner/tenant, status, and resource permissions. **Properly clearing ThreadLocal does not replace object-level authorization**.

## 4. Why does SecurityContextHolder use ThreadLocal by default?

In classic Servlet applications, a request enters a container thread and flows through filters/controller/service. Using ThreadLocal lets deep layers obtain the principal without passing `Authentication` through every method signature.

```text
Thread A (servlet worker)
  |
  +-- Security filter: load/initialize SecurityContext(Alice)
  |     |
  |     +-- AuthorizationFilter: reads Alice
  |     +-- Controller: reads Alice
  |     +-- Service: reads Alice if needed
  |     |
  |     +-- finally: clear Thread A's context
  |
  +-- can serve another request afterward

Thread B (another servlet worker)
  |
  +-- Security filter: load/initialize SecurityContext(Bob)
  |     |
  |     +-- Controller: reads Bob
  |     |
  |     +-- finally: clear Thread B's context
```

The benefit is a uniform API for reading identity during a request. The trade-off is a lifecycle bound to the thread, while threads are routinely reused.

**Important:** "thread holds context" does not mean "all request processing runs on one thread". Servlet asynchronous processing, `@Async`, `CompletableFuture`, scheduled jobs, messaging listeners, and reactive streams can switch execution contexts. You must understand each specific integration instead of expecting ThreadLocal to follow the logical request automatically.

### 4.1. SecurityContextHolder strategies

| Strategy | Meaning | Notes |
| --- | --- | --- |
| `MODE_THREADLOCAL` | Each thread has its own SecurityContext; common default | Must be cleared at scope end; context does not move to other threads automatically |
| `MODE_INHERITABLETHREADLOCAL` | Newly created child threads can receive context reference at creation time | Very error-prone with thread pools, lifecycles, and mutable data; **do not use as default fix for @Async** |
| `MODE_GLOBAL` | Shared context across the JVM | **Unsafe for multi-user servers**; meant for special non-multi-user-web cases |
| Custom `SecurityContextHolderStrategy` | Custom storage/retrieval per architecture | Requires dedicated design and testing; never use just to avoid writing cleanup |

Do not call `SecurityContextHolder.setStrategyName(...)` while the server is serving requests. This setting has JVM-wide impact; changing strategy at runtime can trigger unexpected leaks/errors and break tests in other modules. Normally keep the default `MODE_THREADLOCAL`.

## 5. Where does Spring Security clear context in an HTTP request?

### 5.1. Servlet lifecycle

With Spring Security 6.x, a key filter is `SecurityContextHolderFilter`. It loads/defers loading `SecurityContext` via `SecurityContextRepository`, makes the context available in `SecurityContextHolder` for the scope of request processing, and **clears the context from the holder on exit**. Spring Security also has the historical `SecurityContextPersistenceFilter` model, though both must never be installed together.

```text
HTTP request
    |
    v
DelegatingFilterProxy(springSecurityFilterChain)
    |
    v
FilterChainProxy
    |
    v
SecurityContextHolderFilter
    |
    +-- SecurityContextRepository.load/deferred context
    +-- provides SecurityContext for current thread
    |
    v
Authentication Filters -> Authorization -> Controller
    |
    +-- normal return
    |      or
    +-- exception/redirect/error
    |
    v
finally in filter lifecycle
    |
    +-- SecurityContextHolder.clearContext()
    |
    v
HTTP response / thread returns to container pool
```

Do not misread this diagram as the exact order of **every filter** in every `SecurityFilterChain`; filter order depends on configuration. The security point is that **the thread's scope must be cleared even when downstream fails**.

Spring Security documentation also emphasizes that `FilterChainProxy` guarantees `SecurityContext` cleanup in standard web flows. When leftover context is spotted in a **custom pool outside the filter chain**, do not immediately blame Spring Security.

### 5.2. Post-request cleanup vs persistence for next request

Comparison table:

| Action | API/Component | Purpose |
| --- | --- | --- |
| Set identity in current request | `SecurityContextHolder.setContext(context)` | Code in scope can read it |
| Clear identity from current thread | `SecurityContextHolder.clearContext()` | Prevent leakage to next scope on same thread |
| Save for another HTTP request to restore | `SecurityContextRepository.saveContext(...)` | Session or other storage per policy |
| Reload context when new request arrives | `SecurityContextHolderFilter` and repository | Identify current user of new request |
| End session/logout | `LogoutFilter`, logout handlers, repository/session | Authenticated session no longer exists |
| Delete user or change password in database | Domain account service | Updates credentials/account; needs separate revocation when appropriate |

**Example:** When Alice logs in via form login, the security context can be stored in the HTTP session. At the end of the request, the framework **still clears ThreadLocal**. A subsequent request carrying the session cookie **reloads** the saved context. There is no contradiction: clearing the thread does not delete the session, and keeping the session does not mean ThreadLocal lives forever.

### 5.3. Spring Security 6 and explicit save

In Spring Security 6, `SecurityContextHolderFilter` normally only **loads** the context rather than auto-saving every mutation. If you **write a custom login controller/filter** and want authentication to persist across requests, in addition to setting the holder you must call `SecurityContextRepository.saveContext(context, request, response)` at the appropriate time before the response commits.

This is **separate** from cleanup responsibility:

- `saveContext` handles **persistence**.
- `clearContext` prevents **identity leakage across thread reuses**.
- Calling `saveContext` does not replace `clearContext`.
- Calling `clearContext` does not erase authentication saved in the session.

For standard form login/OAuth2 filters, Spring Security already handles saving and context lifecycle accordingly. There is no need to insert `clearContext()` mid-controller during a normal request just to feel "more secure"; doing so can wipe out current authentication prematurely.

### 5.4. Exceptions and redirects

`finally` must run whether the handler:

- Returns status `200` or `403`.
- Throws an exception that the framework routes to an exception handler.
- Sends the browser a `302` redirect after login.
- Is halted by an authentication/authorization filter.
- Encounters timeout/cancellation in the flow executed by the wrapper.

If custom code does:

```java
SecurityContextHolder.setContext(context);
doBusinessWork();                      // throws exception
SecurityContextHolder.clearContext();  // NOT CALLED
```

then cleanup can be skipped. Correct pattern when **you own the scope**:

```java
SecurityContextHolder.setContext(context);
try {
    doBusinessWork();
} finally {
    SecurityContextHolder.clearContext();
}
```

This is a principle snippet, not a complete custom login endpoint. When running inside a Servlet request whose context is already managed by filters, **do not** arbitrarily set/replace context and clear it mid-request. Use Spring Security APIs and enforce permissions along the right lifecycle.

## 6. How can identity leakage happen?

### 6.1. Thread reuse + stale SecurityContext

Suppose an application creates a custom worker pool to handle document imports:

```text
Pool worker P (reused)

10:00  Alice's task
       create/set SecurityContext(Alice)
       process file A
       FORGET clearContext()

10:01  Bob's task
       skips creating new context assuming one already exists
       reads SecurityContextHolder
       sees Authentication(Alice)  <-- identity leak
       writes wrong actor in audit / misreads Alice's data

10:02  Anonymous task
       may continue seeing Authentication(Alice)
```

Severity depends on how much business code trusts the context. It can cause incorrect audit records, cross-tenant data access, operations executed with authorities not belonging to the requester, or PII exposure. Never rely on "seeing username in logs" as the sole evidence: inspect actual authorization and all data regions that could be read/written.

### 6.2. Custom filter in the wrong position

A `Filter` outside the Spring Security filter chain, or running under a different dispatcher/async path, can set context and forget to clear it. Specifically check:

- Does the filter run **before** `DelegatingFilterProxy` and set context early?
- Does the custom authentication filter use `SecurityContextHolderStrategy`/`SecurityContextRepository` properly?
- Does it wrap `chain.doFilter(...)` in `try/finally` when **it itself** sets context outside framework-managed scope?
- Is it guaranteed not to run twice and overwrite/clear context wrongly during nested dispatches?
- Does it skip certain requests/URLs, leaving stale worker-thread data behind?
- Does it handle ERROR/ASYNC dispatcher threads differently?

Do not "fix" this by removing all filters or enabling `permitAll()`; locate the exact owner of the context lifecycle.

### 6.3. Broken custom login

A controller manually calls `AuthenticationManager.authenticate(...)` and sets authentication in the holder, yet:

- Omits `SecurityContextRepository.saveContext(...)` when session login is needed.
- Fails to handle session fixation/CSRF/exceptions/success/failure properly.
- Fails to clear context in code running outside filters, or clears it prematurely while downstream filters still need auth.

Depending on the bug, users may lose login on the very next request or leak identity across unmanaged scopes. For learning, prefer Spring Security's standard login filters first; only write custom ones with clear justification and thorough tests.

### 6.4. Static/singleton variable holding current Authentication

```java
// DANGEROUS ANTI-PATTERN — DO NOT USE.
class CurrentActorCache {
    static Authentication currentUser;
}
```

A static field or mutable field on a singleton `@Service` is **not thread-local**. Another concurrent request can overwrite it, causing all threads to observe the last user's identity. Even a static ThreadLocal requires remove; using a plain static field is usually worse because it is shared across the entire JVM.

### 6.5. InheritableThreadLocal and thread pools

`MODE_INHERITABLETHREADLOCAL` copies the value from parent thread to **child thread at the moment the child is created**; it does not create an "identity sync pipe" for future tasks.

```text
Alice request -> creates worker thread for the first time
                 worker inherits Alice's context
                 |
Bob request   -> submits to that worker (no new child thread created)
                 worker can still hold Alice's context
```

`SecurityContext` is also mutable; inheriting/sharing references can lead to unintended mutations. Enabling InheritableThreadLocal web-wide to "fix @Async" can leak permissions. Use a **task-submission-time** wrapper instead of changing the JVM-wide strategy.

### 6.6. MODE_GLOBAL is even more dangerous

`MODE_GLOBAL` shares a single context across JVM threads; on a multi-user server, users can trample over each other. It only suits non-multi-user-server models in very special cases. Never switch a Servlet app to MODE_GLOBAL so "everywhere can read Authentication".

### 6.7. Data independent of SecurityContext can still leak

Clearing `SecurityContextHolder` **does not clear** other custom ThreadLocals such as `TenantContext`, `MDC`, hand-rolled request-scoped caches, or datasource routing keys. Each context has its own lifecycle. When propagating identity through an executor, also address trace/correlation/tenant, not just authentication. Clearing `SecurityContext` while leaving `TenantContext=tenantA` can still cause queries against the wrong tenant.

## 7. Propagating context to another thread: when and how?

### 7.1. No automatic propagation for arbitrary thread pools

With default `MODE_THREADLOCAL`:

```java
Authentication current =
    SecurityContextHolder.getContext().getAuthentication();

CompletableFuture.supplyAsync(() -> {
    Authentication background =
        SecurityContextHolder.getContext().getAuthentication();
    return background == null ? "none" : background.getName();
});
```

This is an illustrative snippet: `CompletableFuture.supplyAsync` by default typically runs on a different pool. It is **not guaranteed** to have the caller's `SecurityContext`. If code needs the actor, decide whether identity should be propagated, and if so use a security-aware executor or pass a verified actor ID as data and **reauthorize** when the task runs later.

### 7.2. DelegatingSecurityContextRunnable

Spring Security provides `DelegatingSecurityContextRunnable`. It wraps a `Runnable`, sets the desired context on the holder before the delegate runs, and **clears/restores** when the task finishes per its implementation/version.

```java
SecurityContext submittedContext =
    SecurityContextHolder.getContext();

Runnable work = () -> {
    Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();
    // Only perform operations authorized after policy check.
};

Runnable secured =
    new DelegatingSecurityContextRunnable(work, submittedContext);

executor.execute(secured);
```

This is a snippet; `executor` is an `Executor` configured by your application, not a fake documentation instance. With the constructor that omits context, the wrapper captures context from the holder at creation time. **Remember:** capture context right at submit time; never use a hard-coded admin context to run all tasks.

### 7.3. DelegatingSecurityContextExecutor

When you want every `executor.execute(...)` call wrapped consistently:

```java
ExecutorService rawPool = Executors.newFixedThreadPool(4);

Executor safeExecutor =
    new DelegatingSecurityContextExecutor(rawPool);

// Called inside Alice's request:
safeExecutor.execute(() -> {
    Authentication current =
        SecurityContextHolder.getContext().getAuthentication();
    // Task sees context captured at submit time.
});
```

This is also a snippet. The constructor taking only a delegate `Executor` (without a fixed context) captures the caller's `SecurityContext` on **each submission** and wraps the task. The wrapper manages setting and clearing the thread scope. You must shut down `rawPool` when the application stops, handle cancellations/exceptions, and avoid passing full context into queues that run hours later without an authorization expiration policy.

### 7.4. Difference between the two key constructors

| How executor is constructed | Context used | Warning |
| --- | --- | --- |
| `new DelegatingSecurityContextExecutor(rawExecutor)` | Context captured from `SecurityContextHolder` at **each task submission** | Useful when tasks must execute under the current identity |
| `new DelegatingSecurityContextExecutor(rawExecutor, fixedContext)` | **Same fixed context** for every task | Use only with a tightly controlled system identity; very dangerous if fixing a high-privilege user |

Never use a fixed admin context for all work and consider it "safe because the wrapper has a finally block". Cleanup prevents context from lingering **after** the task; it does not verify that the task was authorized to run with those privileges.

### 7.5. @Async and CompletableFuture

- `@Async` may run on `ThreadPoolTaskExecutor` or a Spring Boot-configured executor; the request's ThreadLocal does **not automatically** follow every task.
- One integration approach is `DelegatingSecurityContextAsyncTaskExecutor` wrapping an `AsyncTaskExecutor`; then route `@Async("securityAwareExecutor")` via the wrapped bean.
- `CompletableFuture.supplyAsync(supplier)` by default does not use your wrapped executor. Explicitly pass `supplyAsync(supplier, securityAwareExecutor)` when there is a valid security reason for propagation.
- `TaskDecorator` can help pass certain contexts like MDC, yet must not be treated as a replacement for Spring Security wrappers unless designed and tested.
- `ExecutorService.submit(Callable)` on a raw executor is likewise unprotected by `DelegatingSecurityContextExecutor` if you bypass the wrapper.
- `@Scheduled`/long-running job queues should prefer a **service identity or immutable actor ID + rechecking permissions**; do not carry an old authentication token into a job running the next day.

A Spring `@Async` integration sketch (requires appropriate imports/classes):

```java
@Configuration
@EnableAsync
class AsyncSecurityConfiguration {

    @Bean
    ThreadPoolTaskExecutor taskPool() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.initialize();
        return executor;
    }

    @Bean("securityAwareAsyncExecutor")
    AsyncTaskExecutor securityAwareAsyncExecutor(
            ThreadPoolTaskExecutor taskPool) {
        return new DelegatingSecurityContextAsyncTaskExecutor(taskPool);
    }
}

// In another bean, call via Spring proxy:
@Async("securityAwareAsyncExecutor")
public CompletableFuture<String> process() {
    return CompletableFuture.completedFuture(
        SecurityContextHolder.getContext().getAuthentication().getName());
}
```

This is a **directional snippet**: it needs an enclosing class/bean, imports, scope, and null/authz handling; it is not a standalone application. `@Async` uses proxies (self-invocation is typically not intercepted), context can be propagated at submit time, and the wrapper cleans up after the task. Only use this when business policy permits the task to act under caller identity.

### 7.6. When NOT to carry the entire SecurityContext into a background job

If a queue has latency or a task continues running after logout/account lock, the context captured at submit time may no longer reflect current permissions. Instead of keeping the full `Authentication` and raw claims, put **actor ID**, **tenant ID**, **action**, **resource ID**, **trace ID**, and **request timestamp** into a signed/controlled data contract, then recheck permissions and status when the worker actually runs. For system automation, create a dedicated service principal/authorization rather than borrowing an admin session.

**Do not assume logout automatically cancels already-submitted tasks holding a reference to SecurityContext**. You need explicit cancellation/revocation/reauthorization per business rules.

## 8. Complete Demo: Spring Boot MVC observing ThreadLocal in request and worker pool

This small app does three things:

1. HTTP Basic authenticates Alice and admin against a BCrypt-hashed user store.
2. `GET /me` reads `Authentication` from the current servlet thread.
3. `GET /thread/plain` uses a plain `ExecutorService`: background thread **does not automatically see Alice**.
4. `GET /thread/delegated` uses `DelegatingSecurityContextExecutor`: background thread sees Alice **only inside the wrapped task**.
5. Subsequent requests and subsequent raw tasks **must not inherit** Alice's context.

Note: The demo deliberately awaits `Future.get` inside an MVC controller for simple illustration. In loaded production systems, do not block HTTP threads waiting on background jobs; use asynchronous request handling/queues and appropriate policies.

### 8.1. Versions and structure

- JDK **17+**.
- Spring Boot **3.5.16**, Spring Security **6.5.x** via Boot BOM.
- Maven 3.9+ (or equivalent Maven wrapper).
- Spring MVC/Servlet, no WebFlux in this app.

```text
security-context-threadlocal-demo/
├── pom.xml
└── src/
    ├── main/java/demo/context/
    │   └── SecurityContextThreadLocalApplication.java
    └── test/java/demo/context/
        ├── ContextWebTests.java
        └── ContextWorkerTests.java
```

Spring Boot 3.5.16 was released in 2026 and is the final OSS release of the 3.5.x line. For new production projects, choose a supported Boot/Security release and review migration guides. This lesson uses 3.5.x to reproduce exact Spring Security 6.5 APIs; Java 17 is an appropriate baseline.

### 8.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>security-context-threadlocal-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
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

### 8.3. Application Java code

Create `src/main/java/demo/context/SecurityContextThreadLocalApplication.java`:

```java
package demo.context;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import jakarta.servlet.DispatcherType;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.concurrent.DelegatingSecurityContextExecutor;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

@SpringBootApplication
public class SecurityContextThreadLocalApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityContextThreadLocalApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class ContextSecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-pass"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-pass"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/me",
                    "/thread/plain", "/thread/delegated", "/boom")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(Customizer.withDefaults())
            .build();
    }

    @Bean(name = "plainProbeExecutor", destroyMethod = "shutdownNow")
    ExecutorService plainProbeExecutor() {
        return Executors.newSingleThreadExecutor(r -> {
            Thread thread = new Thread(r, "context-probe-worker");
            thread.setDaemon(true);
            return thread;
        });
    }

    @Bean(name = "securityAwareProbeExecutor")
    Executor securityAwareProbeExecutor(
            @Qualifier("plainProbeExecutor") ExecutorService pool) {
        // Do not pass a fixed SecurityContext: capture identity on EACH submit.
        return new DelegatingSecurityContextExecutor(pool);
    }
}

@Service
class ContextProbeService {
    private final ExecutorService rawPool;
    private final Executor securityAwareExecutor;

    ContextProbeService(
            @Qualifier("plainProbeExecutor") ExecutorService rawPool,
            @Qualifier("securityAwareProbeExecutor") Executor secureExecutor) {
        this.rawPool = rawPool;
        this.securityAwareExecutor = secureExecutor;
    }

    static String currentName() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();
        return authentication == null
            ? "none"
            : authentication.getName();
    }

    String fromPlainExecutor()
            throws InterruptedException, ExecutionException,
                   TimeoutException {
        // Raw worker thread differs from servlet request thread:
        // by default does NOT automatically have the caller's authentication.
        return rawPool.submit(ContextProbeService::currentName)
            .get(3, TimeUnit.SECONDS);
    }

    String fromDelegatingExecutor()
            throws InterruptedException, ExecutionException,
                   TimeoutException {

        CompletableFuture<String> answer = new CompletableFuture<>();

        securityAwareExecutor.execute(() -> {
            try {
                answer.complete(currentName());
            } catch (Throwable failure) {
                answer.completeExceptionally(failure);
            }
        });

        // Wrapper will clear worker context after delegate finishes.
        return answer.get(3, TimeUnit.SECONDS);
    }
}

@RestController
class ContextController {
    private final ContextProbeService probe;

    ContextController(ContextProbeService probe) {
        this.probe = probe;
    }

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/me")
    String current(Authentication authentication) {
        return "me:" + authentication.getName();
    }

    @GetMapping("/thread/plain")
    String plain(Authentication authentication) throws Exception {
        return "request:" + authentication.getName()
            + ";worker:" + probe.fromPlainExecutor();
    }

    @GetMapping("/thread/delegated")
    String delegated(Authentication authentication) throws Exception {
        return "request:" + authentication.getName()
            + ";worker:" + probe.fromDelegatingExecutor();
    }

    @GetMapping("/admin")
    String admin() {
        return "admin";
    }

    @GetMapping("/boom")
    String fail() {
        throw new ResponseStatusException(
            HttpStatus.INTERNAL_SERVER_ERROR, "lab error");
    }
}
```

### 8.4. Key things to understand in the code

1. `ContextSecurityConfiguration.securityFilterChain` uses HTTP Basic and `SessionCreationPolicy.STATELESS`: new requests must send fresh credentials; no server session is used to restore Alice.
2. Users `alice` and `admin` are created in RAM with BCrypt hashes; password `demo-pass` is for local learning only.
3. `GET /me` receives the filter-verified `Authentication`, not a global field stored by the controller.
4. `plainProbeExecutor` is a **single-thread** `ExecutorService` so tasks deterministically reuse the exact same worker in the demo.
5. `securityAwareProbeExecutor` wraps **that exact pool**, capturing the submitting thread's context **per submission** (constructor does not pass a fixed context).
6. `GET /thread/plain` shows the request thread sees Alice while the plain worker reads `none`.
7. `GET /thread/delegated` shows the request thread sees Alice and the worker sees Alice **inside the task** where the wrapper installed context.
8. When the wrapped task finishes, the wrapper performs cleanup; thus a subsequent task on the raw worker cannot see Alice again.
9. `/boom` produces an error response from the controller to test the exception path; the filter still clears ThreadLocal when the request finishes.
10. `@Bean(destroyMethod="shutdownNow")` shuts down the worker pool on application context shutdown. This is essential for long-lived pools.
11. Never call `SecurityContextHolder.setStrategyName(MODE_GLOBAL)`, never use InheritableThreadLocal, and never copy context via static variables.

**Boundary:** The `/thread/*` endpoints are for demonstration and use blocking waits. Do not ship this endpoint style into production task-processing systems, and never expose raw security principals/claims as JSON for "debugging".

### 8.5. Integration tests: multiple requests, multiple identities, task wrapper, and exception

Create `src/test/java/demo/context/ContextWebTests.java`:

```java
package demo.context;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ContextWebTests {

    @Autowired
    MockMvc mvc;

    @AfterEach
    void cleanTestThread() {
        // Test isolation; does not replace Spring Security filter cleanup.
        SecurityContextHolder.clearContext();
    }

    @Test
    void sameTestThreadDoesNotKeepPreviousRequestIdentity()
            throws Exception {

        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));

        mvc.perform(get("/me")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("me:alice"));

        // Filter ended: test thread no longer holds Alice.
        assertNull(SecurityContextHolder.getContext()
            .getAuthentication());

        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("me:admin"));

        // Drop credentials, must not inherit admin.
        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void rawPoolDoesNotInheritCurrentCallerAndWrapperDoes()
            throws Exception {

        mvc.perform(get("/thread/plain")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string(
                "request:alice;worker:none"));

        mvc.perform(get("/thread/delegated")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string(
                "request:alice;worker:alice"));

        // Same pool worker, yet context from previous task was cleared.
        mvc.perform(get("/thread/plain")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string(
                "request:admin;worker:none"));

        mvc.perform(get("/thread/delegated")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string(
                "request:admin;worker:admin"));

        mvc.perform(get("/thread/plain")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string(
                "request:alice;worker:none"));
    }

    @Test
    void failuresAndDeniedRequestsDoNotLeaveIdentity()
            throws Exception {

        mvc.perform(get("/me")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/admin")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));

        mvc.perform(get("/boom")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isInternalServerError());

        assertNull(SecurityContextHolder.getContext()
            .getAuthentication());

        // Request right after error must still authenticate from scratch.
        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());
    }
}
```

**Test significance:**

- `@SpringBootTest` loads real beans and `@AutoConfigureMockMvc` runs requests through the real Spring Security filter chain.
- `httpBasic("alice", "demo-pass")` sends credentials to the provider, unlike `@WithMockUser` which mocks a principal without verifying passwords.
- Tests intentionally execute consecutive requests in one method to easily observe that no stale context remains on MockMvc's request thread.
- `GET /thread/plain` and `GET /thread/delegated` contrast **non-propagation** and **proper propagation** on the same worker pool.
- After Alice's delegated task, admin's plain task still reads `none` on the worker — proving the wrapper cleared the background scope.
- `GET /boom` produces HTTP `500`, and the subsequent anonymous request still gets `401`. This demonstrates cleanup does not happen only on the "happy path".
- `@AfterEach` clears the test thread for test isolation; in standard Servlet requests, lifecycle responsibility belongs to the Spring Security filter chain.
- Assertions describe demo behavior under default `MODE_THREADLOCAL`; if a system changed the JVM-wide strategy or uses non-standard custom filters, verify again.

### 8.6. Unit tests: reproducing pool leakage and verifying cleanup

Create `src/test/java/demo/context/ContextWorkerTests.java`:

```java
package demo.context;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.concurrent.DelegatingSecurityContextExecutor;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ContextWorkerTests {

    @AfterEach
    void clearMainTestThread() {
        SecurityContextHolder.clearContext();
    }

    private static String currentName() {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();
        return auth == null ? "none" : auth.getName();
    }

    private static void installTestIdentity(String name) {
        // Create test Authentication only; does not verify credentials.
        SecurityContext context =
            SecurityContextHolder.createEmptyContext();

        context.setAuthentication(
            new TestingAuthenticationToken(name, "not-a-password",
                "ROLE_USER"));

        SecurityContextHolder.setContext(context);
    }

    @Test
    void unsafeWorkerLeaksIdentityIntoNextTaskIfNeverCleared()
            throws Exception {

        ExecutorService worker = Executors.newSingleThreadExecutor();

        try {
            String first = worker.submit(() -> {
                installTestIdentity("alice");
                // INTENTIONALLY OMIT clearContext: anti-pattern.
                return currentName();
            }).get(3, TimeUnit.SECONDS);

            assertEquals("alice", first);

            String leaked = worker.submit(ContextWorkerTests::currentName)
                .get(3, TimeUnit.SECONDS);

            // THIS IS THE BUG TO PREVENT IN REAL APPS.
            assertEquals("alice", leaked);

            // Clean up immediately so this test does not retain a leak.
            String afterCleanup = worker.submit(() -> {
                SecurityContextHolder.clearContext();
                return currentName();
            }).get(3, TimeUnit.SECONDS);

            assertEquals("none", afterCleanup);
        } finally {
            worker.shutdownNow();
        }
    }

    @Test
    void finallyRemovesIdentityEvenWhenWorkThrows()
            throws Exception {

        ExecutorService worker = Executors.newSingleThreadExecutor();

        try {
            assertThrows(ExecutionException.class, () ->
                worker.submit((Runnable) () -> {
                    installTestIdentity("alice");
                    try {
                        throw new IllegalStateException("demo failure");
                    } finally {
                        SecurityContextHolder.clearContext();
                    }
                }).get(3, TimeUnit.SECONDS));

            assertEquals("none", worker.submit(
                ContextWorkerTests::currentName)
                .get(3, TimeUnit.SECONDS));
        } finally {
            worker.shutdownNow();
        }
    }

    @Test
    void delegatingExecutorCapturesCallerAndCleansWorker()
            throws Exception {

        ExecutorService worker = Executors.newSingleThreadExecutor();

        try {
            installTestIdentity("alice");

            DelegatingSecurityContextExecutor secured =
                new DelegatingSecurityContextExecutor(worker);

            CompletableFuture<String> result = new CompletableFuture<>();

            // Test thread's context is captured AT submit time.
            secured.execute(() -> result.complete(currentName()));

            assertEquals("alice", result.get(3, TimeUnit.SECONDS));

            // Clear test thread, verify raw worker no longer has Alice.
            SecurityContextHolder.clearContext();

            assertEquals("none", worker.submit(
                ContextWorkerTests::currentName)
                .get(3, TimeUnit.SECONDS));

            // A new task only receives identity when caller has a new identity.
            installTestIdentity("bob");
            CompletableFuture<String> second = new CompletableFuture<>();
            secured.execute(() -> second.complete(currentName()));

            assertEquals("bob", second.get(3, TimeUnit.SECONDS));
            SecurityContextHolder.clearContext();

            assertEquals("none", worker.submit(
                ContextWorkerTests::currentName)
                .get(3, TimeUnit.SECONDS));
        } finally {
            worker.shutdownNow();
        }
    }

    @Test
    void rawWorkerDoesNotAutomaticallySeeCallerAuthentication()
            throws Exception {

        ExecutorService worker = Executors.newSingleThreadExecutor();

        try {
            installTestIdentity("alice");

            // MODE_THREADLOCAL: another worker does not automatically see caller.
            String onWorker = worker.submit(
                ContextWorkerTests::currentName)
                .get(3, TimeUnit.SECONDS);

            assertEquals("none", onWorker);
            assertEquals("alice", currentName());
        } finally {
            SecurityContextHolder.clearContext();
            worker.shutdownNow();
        }
    }
}
```

**Distinguishing value of the tests:**

- `unsafeWorkerLeaksIdentityIntoNextTaskIfNeverCleared` **intentionally constructs the buggy scenario** on a single thread and asserts the leaked value. This is a test to understand the vulnerability, not a production pattern. The test cleans up immediately after verifying.
- `finallyRemovesIdentityEvenWhenWorkThrows` causes the task to throw an exception, yet `finally` still clears the context before the next task.
- `delegatingExecutorCapturesCallerAndCleansWorker` verifies the wrapper captures identity at submit time: Alice, Bob, and checks that the raw worker is empty after each task.
- `rawWorkerDoesNotAutomaticallySeeCallerAuthentication` highlights that default ThreadLocal does not auto-propagate to a raw executor.
- Each test creates its **own pool**, shuts it down in `finally`, and clears the test thread to avoid corrupting state for other tests.
- `TestingAuthenticationToken` in unit tests is only a mock object, **not** proof that a password was verified. Never place it in a production authentication path.

**Warning on nested context cleanup:** If a task library is already managing a prior valid context, calling `clearContext` unconditionally can wipe out the caller's context. When building nested scope wrappers, use lifecycle-aware framework wrappers or intentionally save/restore the previous context. The primary goal is that **after Alice's task finishes, the thread no longer carries Alice when accepting unrelated tasks**.

### 8.7. How to run

In the directory containing `pom.xml`:

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

**Expected outcomes** when the app and dependencies work:

- `mvn test` runs `ContextWebTests` and `ContextWorkerTests`; assertions are designed to pass, including the test that intentionally reproduces a leak and then cleans up.
- `GET /me` anonymous → `401`, Alice with valid password → `200 me:alice`.
- `GET /thread/plain` with Alice → `200 request:alice;worker:none`.
- `GET /thread/delegated` with Alice → `200 request:alice;worker:alice`.
- `GET /thread/plain` with admin right after delegated → `200 request:admin;worker:none`.
- `GET /admin` with Alice → `403`; with admin → `200`.
- `GET /boom` authenticated → `500`; next request without credentials → `401`.

These are **expectations from code/tests**, not output collected from a Maven run in the authoring environment.

In a second terminal (localhost only):

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u alice http://localhost:8080/me
curl -i -u alice http://localhost:8080/thread/plain
curl -i -u alice http://localhost:8080/thread/delegated
curl -i -u admin http://localhost:8080/thread/plain
curl -i -u alice http://localhost:8080/admin
curl -i -u admin http://localhost:8080/admin
```

Curl will prompt for a password when using `-u alice` or `-u admin`; enter `demo-pass` **on the lab machine only**. Do not embed passwords in command history; never use HTTP Basic over real networks without TLS. In older PowerShell you may need `curl.exe`.

**Do not expose the demo's thread/context diagnostic endpoints publicly**. They display usernames from the principal for clarity; real products only return data vetted by DTOs/authorization policies and never print security context into responses.

## 9. Error control in custom code

### 9.1. Safe scope pattern outside HTTP filters

If you truly own an independent task's lifecycle and must set context:

```java
void runUnderVerifiedIdentity(
        Authentication verified, Runnable work) {

    SecurityContext scope =
        SecurityContextHolder.createEmptyContext();
    scope.setAuthentication(verified);

    SecurityContextHolder.setContext(scope);
    try {
        work.run();
    } finally {
        SecurityContextHolder.clearContext();
    }
}
```

This is a **snippet** with a crucial precondition: `verified` must come from a trusted source/authentication mechanism, not a self-assigned role token from an HTTP request. If code involves nested scopes, use Spring Security wrappers or a proper previous-context restoration strategy so you do not accidentally clear the caller's scope.

### 9.2. Saving and restoring context across nested scopes

In some libraries, code temporarily swaps context to invoke an operation, then restores the caller's context on the same thread:

```java
SecurityContext previous = SecurityContextHolder.getContext();

try {
    SecurityContext temporary =
        SecurityContextHolder.createEmptyContext();
    temporary.setAuthentication(systemIdentity);
    SecurityContextHolder.setContext(temporary);

    performScopedOperation();
} finally {
    SecurityContextHolder.setContext(previous);
}
```

**This is a special-case snippet**, not advice to manually elevate privileges temporarily. `systemIdentity` must be a policy-approved principal, and the previous context must belong to the same trusted scope. If the thread already had leaked data from a prior task, restoring previous could **restore the wrong context**; that is why wrappers must sit at the right boundary and new workers must start clean.

### 9.3. Do not arbitrarily call clearContext in a controller

```java
@GetMapping("/profile")
String profile() {
    SecurityContextHolder.clearContext(); // ANTI-PATTERN
    return loadProfile();
}
```

Clearing context mid-request can strip current authentication from downstream filters/handlers/services, leading to unexpected behavior. When requests are managed by Spring Security, **the framework handles cleanup at the boundary**. You only actively clear when:
- Managing a scope **outside** the filter chain.
- Running a logout/invalidation flow with the proper repository/session.
- Writing a library wrapper that intentionally sets context with a clearly bounded scope.
- Isolating tests after a test completes.

Avoid "arbitrarily clearing somewhere to be safe", which breaks business logic or corrupts auditing.

### 9.4. If a custom filter sets context itself

A common approach is implementing a filter extending `OncePerRequestFilter` for custom authentication. Instead of calling `setContext` ad hoc, integrate with `AuthenticationManager`/`SecurityContextHolderStrategy`/`SecurityContextRepository` and the corresponding Spring Security hooks. If a filter sits outside the lifecycle managed by `SecurityContextHolderFilter`, ensure cleanup in `finally`, and for Servlet ASYNC/ERROR dispatches examine the specific scope/dispatcher.

**Do not assert only a single 200 request.** Test request sequences on the same thread/pool, failing requests, wrong credentials, anonymous, other users, async paths, and session restoration.

## 10. ThreadLocal, MDC, RequestAttributes, and TenantContext

In real systems, a request can simultaneously hold:

```text
SecurityContextHolder  -> Authentication: alice
MDC                    -> traceId: request-123, actorId: alice
TenantContext          -> tenantId: company-A
RequestContextHolder   -> Servlet request attributes
Custom ThreadLocal     -> custom area
```

These contexts **do not share a single unified lifecycle automatically**. Spring Security clears `SecurityContextHolder`; logging frameworks may use `MDC.clear()` or `MDC.remove("key")`; a custom `TenantContext` needs removal; `RequestContextHolder` is managed by Spring Web per dispatch. If spawning a custom worker:

```java
TenantContext.set(tenantId);
MDC.put("traceId", traceId);
try {
    process();
} finally {
    MDC.remove("traceId");
    TenantContext.clear();
    SecurityContextHolder.clearContext(); // when the task itself owns the scope
}
```

This snippet is not standalone because `TenantContext`, `MDC`, and `process` are application APIs/data; it illustrates that **each kind must be cleaned up properly**. With an executor already wrapped by Spring Security, avoid nesting redundant `clearContext` calls at the wrong time; design controlled task decorators/context propagation to clean all layers.

### 10.1. Why is tenant context leakage especially dangerous?

If repository queries use `TenantContext.get()` to select tenant/schema/database, a tenant leak even when `SecurityContextHolder` is clean can expose cross-tenant data. Thus "no identity leak" tests must extend to **no tenant leak**, not just current username.

### 10.2. Logging must avoid credential exposure

Even with proper cleanup, careless logging can leak usernames, access tokens, refresh tokens, session IDs, or raw Basic headers. When auditing is required, record minimal verified actor ID, tenant ID, action, outcome, and correlation ID; never log the entire `Authentication` object or request headers. Never rely on ThreadLocal values as the sole audit source for a delayed job: verify the actor from the job's trusted metadata.

## 11. WebFlux and Reactor Context: do not copy Servlet ThreadLocal into reactive

Spring WebFlux uses a reactive execution model where a single pipeline can hop across different threads and threads are shared across subscriptions. Reactive Spring Security relies on `ReactiveSecurityContextHolder` inside **Reactor Context**, not Servlet ThreadLocal `SecurityContextHolder` as its standard mechanism.

```java
// Reactive snippet in a WebFlux service:
Mono<String> currentName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .defaultIfEmpty("anonymous");
}
```

This snippet requires importing `Mono`, `ReactiveSecurityContextHolder`, `SecurityContext`, and `Authentication`. It is a **snippet**, not to be copied into the Servlet demo app in section 8. With WebFlux, use `SecurityWebFilterChain` and `ServerHttpSecurity`, plus reactive method security where applicable. Never call `SecurityContextHolder.getContext()` inside any reactive operator assuming the user is right just because the request started on that thread.

### 11.1. Technical differences

| Topic | Servlet | WebFlux |
| --- | --- | --- |
| Context normally read via | `SecurityContextHolder` | `ReactiveSecurityContextHolder` |
| Execution mechanism | Servlet thread-bound filter lifecycle | Reactor Context bound to reactive subscription |
| Web security | `SecurityFilterChain`/`HttpSecurity` | `SecurityWebFilterChain`/`ServerHttpSecurity` |
| Tasks switching threads | Requires intentional wrappers/integration | Uses Reactor operators and proper Context propagation |
| HTTP testing | `MockMvc` | `WebTestClient` |
| Leak risks | Worker thread reuse/custom ThreadLocal | Wrong Reactor context scope/custom ThreadLocal/cross-subscriber data |
| Clearing ThreadLocal at end of Servlet request | Plays a direct role | Does not fully explain Reactor Context cleanup |

Never fix WebFlux issues with `MODE_INHERITABLETHREADLOCAL` or by forcing every publisher onto a single thread. Reactive context is a different mechanism requiring proper reactive APIs and tests.

## 12. Pitfalls with async and transactions

### 12.1. @Async changes threads, not policies

A method annotated with `@PreAuthorize` running inside a background task may see no authentication if context is not propagated. Yet "fixing" propagation does not mean the user is still allowed to perform every action when the task executes: permissions may have been revoked. Verify actor, action, resource, and timing when the task actually executes.

### 12.2. CompletableFuture uses the common pool

Never assume `CompletableFuture.supplyAsync(...)` shares the servlet thread's identity. Pass a security-aware executor to the `Executor`-accepting overload, or pass a verified user ID and resolve authorization inside the worker. In all cases, the task must clean up its thread's context.

### 12.3. Transactions are also usually thread-bound

Declarative Spring transactions are normally bound to the executing thread. When offloading work to another worker, the request's transaction does not automatically transfer to the worker, just like SecurityContext. **Do not equate transaction propagation with security context propagation**. A task needs its own transaction if performing DB operations, and must verify permissions/domain invariants at the right moment.

### 12.4. Error/ASYNC dispatch is not the same as an arbitrary task pool

Spring Security integrates with Servlet async processing and Spring MVC async in supported cases. Do not conclude "every Callable from MVC loses context" merely because raw `ExecutorService.submit` does not auto-propagate. However, custom tasks via `@Async`/`CompletableFuture`/queues may use different executors. Identify the **exact invocation mechanism**, then test.

### 12.5. Java 21+ Virtual threads

Virtual threads are still threads with ThreadLocal semantics, though scheduler lifecycles/characteristics differ from traditional thread pools. `SecurityContextHolder` with `MODE_THREADLOCAL` still requires clear scoping; never assume virtual threads automatically eliminate identity leakage or handle auto-propagation. When using virtual-thread executors, consult the compatible Spring Boot/Security release guidance and test async/cancellation/cleanup; Java 17 examples in this lesson do not rely on virtual threads.

## 13. Common mistakes and fixes

| Mistake | Consequence | Fix direction |
| --- | --- | --- |
| `SecurityContextHolder.setContext` then return without finally | Thread pool can carry stale context | Scope owner needs `try/finally`, or official wrapper |
| Catching exception and skipping cleanup | Identity remains on worker | Cleanup in `finally`, not after throw-prone code |
| Enabling `MODE_GLOBAL` for a web app | All users share context | Keep `MODE_THREADLOCAL` |
| Enabling `MODE_INHERITABLETHREADLOCAL` to fix @Async | Thread pool can retain creation-time identity | `DelegatingSecurityContextAsyncTaskExecutor` |
| Using raw `CompletableFuture.supplyAsync` expecting auth | Task misses caller identity | Pass security executor or actor ID with reauthorize |
| Using a fixed admin context for all tasks | Ordinary user tasks can run as admin | Capture per submission or use controlled service identity |
| Storing Authentication in static singleton field | JVM-wide identity race/leak | Never use global mutable current user |
| Clearing ThreadLocal in controller before business method | Business code loses auth mid-request | Let security filter manage HTTP scope |
| Thinking clearContext = logout | Session/token remains valid | Logout handlers + repository/session/token revoke |
| Thinking saveContext = clearContext | Worker still holds stale context | Clear scope via finally/filter |
| Clearing SecurityContext without clearing TenantContext | Can query the wrong tenant | Independent cleanup for tenant/MDC |
| Testing only successful requests | 401/403/500/cancel bugs go undetected | Test failures and consecutive requests |
| Using `@WithMockUser` to conclude Basic login works | Mock bypasses credential provider | Add real `httpBasic`/form login tests |
| Checking only `isAuthenticated()==true` | Anonymous token can also be true | Spring authorization/trust resolver |
| Keeping user session in multi-hour queues | Roles can be stale/revoked | Actor ID + reauthorize/expiry/cancel |
| Creating a ThreadLocal for current tenant without removing | Cross-tenant access risk | Use try/finally/wrapper and test |
| WebFlux calling ThreadLocal `SecurityContextHolder` | Wrong identity across thread switches | `ReactiveSecurityContextHolder`/Reactor Context |

## 14. Recommended testing matrix

| Scenario | What to verify |
| --- | --- |
| `GET /public` anonymous | 200 response; no authenticated user created |
| `GET /me` anonymous | 401 from HTTP Basic entry point |
| `GET /me` Alice valid password | 200, me:alice |
| `GET /me` wrong password | 401 |
| Alice then anonymous on same test thread | Anonymous still gets 401, does not "remember Alice" |
| Admin then anonymous | Does not "remember admin" |
| Alice hits `/admin` | 403, role check enforced |
| Admin hits `/admin` | 200 |
| Authenticated request throws error | Subsequent request without credentials still gets 401 |
| Raw worker executor submitted from Alice's request | Worker does not automatically see Alice |
| Delegating executor from Alice's request | Worker sees Alice only inside the task |
| Delegating executor from Bob's request | Worker sees Bob, does not see Alice |
| Raw worker after delegated task | Worker returns to `none` |
| Manual worker sets context and forgets cleanup | Test intentionally reproduces stale Alice |
| Manual worker with finally | Context cleared even when throwing |
| Misconfigured profile with MODE_GLOBAL | Config test/guard catches it |
| Servlet async/background API | Context propagation tested per integration |
| Job after logout/role revoke | Reauthorization does not use stale grant |
| MDC/TenantContext on same thread | No trace/tenant leakage |
| WebFlux reactive test | Uses Reactor Context/`WebTestClient`, not Servlet ThreadLocal |
| Session-based login next request | Repository restores valid context; thread still cleared after each request |

This is a matrix for **security lifecycle**, not just an "endpoint returns 200" checklist. You must test **A → B** sequences on the same worker or request pipeline to catch identity leakage. However, if code tries to force thread ordering with sleep, tests become flaky; use a `newSingleThreadExecutor` and `Future.get(timeout)` like the demo to deterministically verify worker reuse.

## 15. Self-check questions

**Q1.** Why must `ThreadLocal` be cleared when a thread pool reuses threads?

**A:** ThreadLocal binds values to the **thread**, not to the task/user. A thread processing Alice then Bob can carry Alice's value if `remove`/`clearContext` is omitted.

**Q2.** Is `SecurityContextHolder.getContext() == null` the standard way to check for anonymous?

**A:** No. The holder usually returns an empty context; authentication may be null or an anonymous token. Use proper authorization rules and trust resolvers.

**Q3.** What does Spring Security 6 `SecurityContextHolderFilter` do?

**A:** Loads/defers loading context via `SecurityContextRepository` for the request and clears the holder after the scope; it does not auto-save every change from a custom authentication flow.

**Q4.** After form login, does clearing ThreadLocal at the end of the request log the user out?

**A:** No, if context was properly saved in session/repository. The next request reloads context from the session; the old ThreadLocal is still cleared so it never leaks to others.

**Q5.** Why does a raw `ExecutorService` task not see the current user from a servlet request?

**A:** The default strategy is `MODE_THREADLOCAL`. A worker on another thread does not automatically receive context. Use a propagation wrapper or pass actor ID and check permissions.

**Q6.** How does `DelegatingSecurityContextExecutor(rawExecutor)` differ from `DelegatingSecurityContextExecutor(rawExecutor, fixedContext)`?

**A:** The single-arg version captures the caller's context on each submission; the two-arg version uses the same fixed context for every task. A fixed admin context easily causes privilege escalation if misused.

**Q7.** If a custom worker called `setContext`, is placing `clearContext` at the end of the method after `work.run()` sufficient?

**A:** Not when `work.run()` throws an exception. You need `try/finally`.

**Q8.** Does `SecurityContextHolder.clearContext()` log out all sessions/refresh tokens?

**A:** No. It clears the current thread. Logout/revocation also requires session/repository/token lifecycle handling per policy.

**Q9.** Does enabling `MODE_INHERITABLETHREADLOCAL` guarantee Bob's task in a pool receives Bob?

**A:** No. Inheritance relates to thread creation time, whereas pools reuse threads and can retain stale contexts. Use per-task wrappers.

**Q10.** Does seeing `none` in a background task prove cleanup is working?

**A:** Not enough. The task might never have received identity at all. You need both a test where the delegated task sees **Alice properly** and a subsequent task sees **none/Bob properly**.

**Q11.** Why must you not copy `SecurityContextHolder.getContext()` into WebFlux?

**A:** Reactive pipelines can run across multiple threads; standard security context is propagated through Reactor Context via `ReactiveSecurityContextHolder`.

**Q12.** When Alice's permissions change or she logs out, is a queued job that already captured Alice's SecurityContext automatically revoked?

**A:** Not necessarily. Jobs need expiry/revocation/reauthorization policies at execution time; never hold a long-lived authority snapshot and assume it remains valid.

## 16. Code review checklist

- [ ] Is the app Servlet or WebFlux? Is the matching context mechanism used?
- [ ] Does `SecurityContextHolder` use default `MODE_THREADLOCAL` when running multi-user web apps?
- [ ] Is there no unjustified code enabling `MODE_GLOBAL` or `MODE_INHERITABLETHREADLOCAL`?
- [ ] Do all HTTP requests pass through the security filter chain with right matchers/dispatchers?
- [ ] Where do custom filters/authentication set context, and who owns the lifecycle?
- [ ] For self-managed context scopes: is cleanup in `finally` even on exception/cancel?
- [ ] For standard Servlet filters: is there no arbitrary context clearing inside controllers?
- [ ] Does custom login distinguish `SecurityContextRepository.saveContext` from `clearContext`?
- [ ] Is current Authentication never stored in static/singleton mutable fields?
- [ ] Do `@Async`/`CompletableFuture`/thread pools propagate per-task properly if needed?
- [ ] Is no fixed privileged context used for all users' tasks?
- [ ] Do executor pools have clear shutdown/lifecycles and worker-reuse tests?
- [ ] Do delayed tasks recheck actor/tenant/permissions when needed?
- [ ] Are custom ThreadLocals such as MDC/TenantContext/trace also cleaned up?
- [ ] Are passwords, Basic headers, access tokens, session cookies, and raw Authentication kept out of logs?
- [ ] Are sequences tested as Alice → anonymous/Bob, including errors and exceptions?
- [ ] Is absence of cross-tenant reads/writes verified after context errors?
- [ ] Do tests exercise real credentials on at least one integration path rather than mocks only?
- [ ] For session/SSO/JWT, are logout/revocation implemented separately without mistaking cleanup for logout?
- [ ] For WebFlux, is Reactor Context tested without assuming ThreadLocal auto-propagates?

## 17. Key takeaways

1. **ThreadLocal stores per thread, not per request/user.** When threads are reused, missing cleanup can carry old identities into new tasks.
2. **SecurityContextHolder** uses a strategy, defaulting to `MODE_THREADLOCAL` in Servlet; `SecurityContext` holds the current `Authentication`.
3. **The standard Spring Security filter chain clears context at the end of a request**. If code manually sets context outside the filter lifecycle, it must use `try/finally` or a framework wrapper.
4. **Clearing context does not delete sessions**, and saving via `SecurityContextRepository` does not replace clearing the thread. These are two separate goals.
5. **@Async and ExecutorService do not automatically keep the right identity** just because the parent thread was authenticated. Use `DelegatingSecurityContextExecutor`/matching wrappers or pass actor ID and reauthorize.
6. **Never use MODE_GLOBAL or INHERITABLETHREADLOCAL as a blanket fix** for thread-pool propagation; it risks privilege leaks.
7. **Test sequentially and across thread reuse**: Alice then anonymous/Bob, propagated task then raw task, exception then new request.
8. **WebFlux uses Reactor Context**; Servlet ThreadLocal assumptions do not transfer verbatim to reactive.
9. **Do not clean only SecurityContext**: MDC, tenant context, and custom ThreadLocals can also leak sensitive data.

## Official documentation

- [Spring Security 6.5 — Servlet Authentication Architecture: SecurityContextHolder and cleanup](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 — Concurrency Support: DelegatingSecurityContextRunnable/Executor](https://docs.spring.io/spring-security/reference/6.5/features/integrations/concurrency.html)
- [Spring Security 6.5 — Persisting Authentication, SecurityContextHolderFilter](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html)
- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — SecurityContextHolder Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/context/SecurityContextHolder.html)
- [Spring Security 6.5 — DelegatingSecurityContextExecutor Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/concurrent/DelegatingSecurityContextExecutor.html)
- [Spring Security 6.5 — WebFlux Reactive Method Security and Reactor Context](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [Spring Security 6.5 — MockMvc HTTP Basic Test](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html)
- [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Boot 3.5 — Web Security Auto-Configuration](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html)
- [Java 17 — ThreadLocal API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html)
- [Java 17 — ExecutorService API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)

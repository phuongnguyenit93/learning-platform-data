# SecurityContextHolderStrategy and the Limits of Storage Strategies

In a Spring Security Servlet application, you often see the following code:

```java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
```

It reads the newly authenticated user inside a synchronous controller or service. Yet why does similar code running inside `CompletableFuture.supplyAsync(...)` see `null`? Why does switching to `MODE_INHERITABLETHREADLOCAL` appear to "fix" the issue when creating `new Thread(...)`, yet create risk with thread pools? And why can switching to `MODE_GLOBAL` cause two requests from two users to see each other's identity?

The answer lies in **SecurityContextHolderStrategy**: a *contract managing where `SecurityContext` is stored within the current execution*, not an account store, not a session repository, and not an authentication mechanism itself. Choosing the wrong strategy or failing to clear the context at request/task boundaries can cause **cross-user identity leakage**, wrong authorization decisions, or lost authentication when switching threads.

This lesson belongs to the **Servlet Context** section under *Spring Security - authentication*. The primary scope is Spring Security Servlet 6.x on Java 17+. The runnable Gradle/Spring Security Core 6.5.x example covers `MODE_THREADLOCAL` and controlled context propagation; the Spring Boot 3.x, Spring MVC async, and `SecurityContextRepository` sections explain request/session boundaries. **Do not apply ThreadLocal verbatim to WebFlux/Reactor.**

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the differences among `SecurityContext`, `Authentication`, `SecurityContextHolder`, `SecurityContextHolderStrategy`, `SecurityContextRepository`, and request-lifecycle management filters.
2. State the behavior and limits of `MODE_THREADLOCAL`, `MODE_INHERITABLETHREADLOCAL`, and `MODE_GLOBAL`; identify the right mode for a multi-user servlet server.
3. Understand the `getContext`, `createEmptyContext`, `setContext`, `clearContext`, `getDeferredContext`, and `setDeferredContext` APIs and the implications of custom strategies.
4. Explain when context is lost or can leak across thread pools, `@Async`, `CompletableFuture`, schedulers, and callbacks.
5. Use `DelegatingSecurityContextRunnable`/`DelegatingSecurityContextExecutor` to pass context at the right time, clean up on the receiving thread, and check boundaries.
6. Distinguish **per-thread storage within a single execution** from **persistence across multiple HTTP requests** via session/cookie/`SecurityContextRepository`.
7. Avoid setting an authenticated `Authentication` before verifying credentials, avoid retaining raw passwords, and avoid passing high-privilege contexts to unrelated tasks.
8. Run the code yourself and use the test matrix to prove contexts are never mixed between two users/requests.

## 2. Six Similarly Named Components with Different Responsibilities

| Component | Responsibility | Does Not Provide on Its Own |
| --- | --- | --- |
| `Authentication` | Represents an authentication request or result, containing principal, credentials, authorities, and authenticated status. | Does not guarantee the account status is still fresh in the DB. |
| `SecurityContext` | Container holding the `Authentication` for the current security processing flow. | Does not save sessions or verify passwords. |
| `SecurityContextHolder` | Static façade for accessing `SecurityContext` from running code. | Not a database or HTTP session. |
| **`SecurityContextHolderStrategy`** | Defines **how the context is stored/retrieved/cleared for execution**. | Does not create valid authentication or persist to the next request. |
| `SecurityContextRepository` | Loads/saves `SecurityContext` across request boundaries via session, request attribute, or another store. | Does not define who is authenticated; does not replace the strategy. |
| `SecurityContextHolderFilter` / `SecurityContextPersistenceFilter` | Sets up/restores/ensures cleanup along the filter flow depending on version/configuration. | Does not grant access to unauthenticated clients by default. |

Keep three questions separated:

- **Who has been authenticated?** → `Authentication` created by a trusted filter/provider/mechanism.
- **How does running code see that context?** → `SecurityContextHolder`/`SecurityContextHolderStrategy`.
- **Can a new request recover the previous request's authentication?** → `SecurityContextRepository` + cookie/session/token/filter configuration.

A `MODE_THREADLOCAL` strategy can be completely valid for the current request whether the system uses `HttpSession`, stateless JWTs, or opaque tokens. **The holder mode does not decide whether a session is created.**

### 2.1 Two Lifecycles Diagram

```text
REQUEST LIFECYCLE (Servlet)
  HTTP request
    |
    v
  SecurityContextRepository.loadDeferredContext(...)
    |
    v
  SecurityContextHolderFilter loads context into HolderStrategy
    |
    v
  Authentication filter/provider if needed
    |
    v
  Controller/Service reads HolderStrategy.getContext()
    |
    v
  If persistence is needed: saveContext(...) per appropriate mechanism
    |
    v
  Request ends / clear context from thread

THREAD/TASK LIFECYCLE
  Request worker thread A
    -> MODE_THREADLOCAL: context A resides on A
    -> dispatches task to thread B
         B does not automatically receive context A
         if wrapped: pass snapshot/context in a controlled way
         run task B
         finally: clear B's context
```

In Spring Security 6, `SecurityContextHolderFilter` is typically responsible for **loading** the context, and custom authentication mechanisms that want persistence must **explicitly save to `SecurityContextRepository`**. `SecurityContextPersistenceFilter` from older configurations includes automatic saving where appropriate; do not register both for the same flow by default. See Section 8 for the distinction.

## 3. What Is SecurityContextHolderStrategy?

`SecurityContextHolderStrategy` is an interface in the `org.springframework.security.core.context` package. It defines the operations for a component to get, set, or clear `SecurityContext`. Spring Security components can access the strategy via `SecurityContextHolder.getContextHolderStrategy()` or be configured with the corresponding strategy.

Core API contract, annotated for learning:

```java
public interface SecurityContextHolderStrategy {
    void clearContext();
    SecurityContext getContext();
    void setContext(SecurityContext context);
    SecurityContext createEmptyContext();

    // Default methods added in Spring Security 5.8+:
    Supplier<SecurityContext> getDeferredContext();
    void setDeferredContext(Supplier<SecurityContext> deferredContext);
}
```

**This is an illustrative signature reference, not a file to redefine.** The library's actual interface is the authoritative place to check exact behavior and default methods per version.

### 3.1 Important Operations

- `getContext()`: retrieves the context bound to the current execution; by contract, it must return a non-`null` object. **Does not guarantee `getAuthentication()` is non-`null`**.
- `createEmptyContext()`: creates a **new** empty context per the strategy; should be used before setting a new authentication to avoid mutating a shared context instance.
- `setContext(context)`: associates the context with execution per the active strategy; does not automatically save to `HttpSession`.
- `clearContext()`: removes the association on the current execution per the strategy. With ThreadLocal, clearing after a request/task is mandatory to prevent the next thread use from seeing an old identity.
- `getDeferredContext()`: obtains a `Supplier<SecurityContext>` for deferred context access per the strategy; not a portable token to send between processes.
- `setDeferredContext(supplier)`: sets the context supplier, meaningful for deferred loading; strategies may override the default for optimization.
- `SecurityContextHolder.getContextHolderStrategy()`: retrieves the strategy currently used by the façade; useful when custom components must stay consistent with the filter chain.

### 3.2 An Empty Context Is Not Anonymous Authentication

`getContext()` normally returns a context even when no user is present; `getContext().getAuthentication()` may then be `null`. In a request passing through Spring Security, `AnonymousAuthenticationFilter` may place an `AnonymousAuthenticationToken` so downstream layers see an authentication representing anonymous. This **does not mean anonymous counts as authenticated enough to access protected endpoints**; `AuthenticationTrustResolver` and authorization rules distinguish anonymous.

Do not write:

```java
// Wrong: having a context object does not mean logged in.
boolean loggedIn =
        SecurityContextHolder.getContext() != null;
```

When you need to know the principal handling the request, use the `Authentication` provided by the framework and let authorization rules decide access; do not infer login status merely from the container's existence.

## 4. Three Built-In Strategies

Spring Security defines three modes in `SecurityContextHolder`:

| Mode | Context Storage Scope | Best Suited For | Risks and Limitations |
| --- | --- | --- | --- |
| **`MODE_THREADLOCAL`** | Each thread has its own association via ThreadLocal. This is the default. | **Multi-user Servlet servers**, synchronous request processing. | Context does not follow tasks running on other threads; thread must be cleared after use. |
| **`MODE_INHERITABLETHREADLOCAL`** | Newly created threads can inherit the ThreadLocal value from the parent at thread creation time. | Some desktop/batch apps where child threads are genuinely created in a controlled manner. | **Not per-task propagation in thread pools**; can unintentionally inherit/share references, retain old principals, or leak data. |
| **`MODE_GLOBAL`** | A single JVM-wide context shared across multiple threads. | Special standalone cases with a single JVM-wide shared identity. | **Unsuitable for multi-user web servers**: requests A and B can overwrite or see each other's identity. |

Spring Security documentation describes `MODE_THREADLOCAL` as the appropriate default for servers. Do not switch to `MODE_GLOBAL` to make worker threads "see the user"; that is arguably the worst security mistake of the three options.

### 4.1 MODE_THREADLOCAL: Right Because It Does Not Share by Default

Suppose a servlet container reuses two threads for requests:

```text
Thread T1: Alice's request
   HolderStrategy[T1] -> Context(Alice)

Thread T2: Bob's request
   HolderStrategy[T2] -> Context(Bob)

If Alice dispatches a task to T2:
   Task running on T2 does NOT automatically have Context(Alice).
   Framework/callback must establish the appropriate scope in a controlled manner.
```

ThreadLocal protects against **sharing the same context across all threads by default**, but does not guarantee complete safety if developers omit cleanup or misconfigure scopes. Thread pools keep workers long-lived; if a task calls `setContext` manually and forgets `clearContext` in `finally`, the next task can see the stale principal.

`ThreadLocal` is also not *a distinct context per HTTP request* by Java definition. It is *one value slot per thread*. The Spring Security filter chain must load the right context when a request enters and clean up when it ends. Never treat a thread ID as a user ID.

### 4.2 MODE_INHERITABLETHREADLOCAL: Child Thread vs. Pooled Thread

Java `InheritableThreadLocal` copies the value **when a child thread is created**, not when submitting a task to an already-existing thread. A thread pool may create workers when no context exists or under an arbitrary request's identity. Later, Bob's and Alice's tasks reuse those workers; inheritance does not re-run on each `submit`.

Furthermore, the default `InheritableThreadLocal.childValue` passes the **same reference value** to the child unless custom copying logic exists. With a mutable `SecurityContext`, parent and child can inadvertently observe each other's object mutations. One thread calling `clearContext` does not automatically clear references held by another child.

Dangerous timing example:

```text
09:00 Request thread (Alice) creates Worker-7 when context=Alice
09:01 Worker-7 finishes the task and remains in the pool
09:02 Request thread (Bob) submits a task to Worker-7
09:03 Worker-7 may still hold Alice's inherited/leftover context
=> Inherited thread-local cannot be used as per-task authorization.
```

**Rule:** With `ExecutorService`, `@Async`, `CompletableFuture`, and schedulers, pass security context at the **task submission/execution boundary** using supported wrappers or an explicit identity contract with authorization checks. Never rely on "just turning on inheritable".

### 4.3 MODE_GLOBAL: All Threads Share One Slot

If a Servlet application runs Alice and Bob concurrently:

```text
Alice's request sets global Authentication(Alice).
Bob's request sets global Authentication(Bob).
Alice's request continues and reads global context => may see Bob.
```

This is the pattern of **cross-user leakage / cross-request identity confusion**. `MODE_GLOBAL` only makes sense in specialized programs with a single JVM-wide security context, not multi-tenant/multi-user web services.

If you encounter "async task cannot see the user", **do not** fix it with `MODE_GLOBAL`. Examine why the task needs identity and use `DelegatingSecurityContextExecutor` or a framework-managed mechanism.

## 5. When to Set the Strategy and Why You Should Not Change It Between Requests

A strategy is chosen **JVM-wide** via `SecurityContextHolder`. It can be set at startup using the documented system property or `SecurityContextHolder.setStrategyName(...)`. There is also `setContextHolderStrategy(customStrategy)` for custom strategies.

Illustrative example of choosing **before the application initializes filters and threads**:

```java
// Use at bootstrap only; never run inside a controller/request.
SecurityContextHolder.setStrategyName(
        SecurityContextHolder.MODE_THREADLOCAL);
```

On a production JVM, the default is already `MODE_THREADLOCAL`, so **this configuration line is usually unnecessary**. If the strategy is changed after the app already has running threads/requests:

- Existing threads may still hold contexts under the previous strategy.
- Some components may have already captured/referenced the old strategy.
- Switching the static strategy changes how all threads view the context.
- `SecurityContextHolder.getInitializeCount()` increments with each re-initialization (useful for diagnostics, **not a login metric**).
- Results under concurrent load can be inconsistent or cause security leaks.

The Javadoc explicitly warns against calling `setStrategyName` multiple times in the same JVM; `setContextHolderStrategy` is also **not thread-safe** and must not be used for switching while requests are executing.

### 5.1 Custom SecurityContextHolderStrategy

When a genuinely special requirement exists, an implementation of `SecurityContextHolderStrategy` can be provided. However, that is a *security infrastructure* change, not the normal way to "add a field to the principal". A custom strategy must:

1. Guarantee `getContext()` is non-null, `createEmptyContext()` creates a proper empty context, and `setContext(null)` is rejected per contract.
2. Clearly define scope, isolation between requests/tasks, and how `clearContext()` removes associations.
3. Properly handle `Supplier<SecurityContext>` and deferred loading if the framework relies on `getDeferredContext()`/`setDeferredContext()`.
4. Account for classloader/application restarts, shared singletons, memory retention, and thread-safety.
5. Ensure filters/repositories/delegating concurrency wrappers use the same strategy, especially when configured individually via `setSecurityContextHolderStrategy(...)`.
6. Test end-to-end across authentication, logout, servlet async, task executors, and error/exception conditions.
7. Never swap the JVM-wide static strategy to apply a tenant to a single request; tenant is authenticated data inside the principal/context, **not a JVM-wide mode**.

Example of **using the configured strategy** without replacing it:

```java
SecurityContextHolderStrategy strategy =
        SecurityContextHolder.getContextHolderStrategy();

SecurityContext fresh = strategy.createEmptyContext();
fresh.setAuthentication(authenticationFromTrustedProvider);
strategy.setContext(fresh);

// When managing a scope manually, clean up after completion.
strategy.clearContext();
```

The snippet above is an **illustrative pattern for internal security code**, not a complete login flow, and **must never construct an authenticated authentication from a client-sent username**. In standard servlets, the filter chain manages scope, and controllers should not alter global context themselves.

## 6. Setting Authentication in Context Properly Without Data Leakage

When a trusted authentication component has just verified credentials, code typically creates **a new context** and attaches the result:

```java
// authentication is the REAL result of AuthenticationManager.authenticate(...),
// not an object self-marked authenticated from unverified input.
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
```

Why not write the shorter form:

```java
SecurityContextHolder.getContext().setAuthentication(authentication);
```

In some architectures, the context instance may be held/shared by a repository, session, or another thread. Mutating a reused context can create race conditions across multiple executions. Creating a new context clarifies scope and ownership, though it **does not replace saving properly to the repository if login must persist across future requests**.

### 6.1 Cleaning Up with finally When Managing Scope Manually

If you set context manually in a task not managed by Spring Security's `FilterChainProxy`:

```java
SecurityContext previous = SecurityContextHolder.getContext();
try {
    SecurityContext scoped = SecurityContextHolder.createEmptyContext();
    scoped.setAuthentication(trustedAuthentication);
    SecurityContextHolder.setContext(scoped);
    // Run work within the authorized identity scope.
} finally {
    SecurityContextHolder.clearContext();
    // For nested scopes with a genuine restore contract, design restoring
    // previous separately and ensure no out-of-scope reference is retained.
}
```

For pooled workers, default to **clearing the context in finally** so the next task does not receive an old identity. However, if a valid security context already existed on the thread before entering a nested scope, blindly clearing can wipe the caller's context. Use wrappers/mechanisms with a tested cleanup/restore contract or pass identity explicitly; do not write naive "save/restore" helpers without full understanding.

### 6.2 Never Construct an "authenticated" Authentication from Raw Input

```java
// WRONG: a username from the request does not prove identity.
var forged = UsernamePasswordAuthenticationToken.authenticated(
        request.getParameter("username"),
        null,
        AuthorityUtils.createAuthorityList("ROLE_ADMIN"));

SecurityContextHolder.getContext().setAuthentication(forged);
```

This is a critical anti-pattern. `SecurityContextHolderStrategy` simply holds the object you pass in; it **does not call PasswordEncoder**, does not verify token signatures, and does not stop you from marking something authenticated yourself. Always let a trusted `AuthenticationManager`/provider/filter return the authenticated result, then store it properly.

### 6.3 clearContext Does Not Log Out All Devices

`SecurityContextHolder.clearContext()` removes the current execution's association (typically ThreadLocal). It **does not automatically**:

- invalidate the `HttpSession` that stored the context;
- delete browser cookies or sessions on other tabs/devices;
- revoke JWTs, refresh tokens, or remember-me cookies;
- change enabled/locked/account state in the database;
- revoke authorities granted to another currently running request.

Proper logout requires appropriate handlers, session repositories, and token revocation. Never just call `clearContext()` in a controller and return "logged out of all devices".

## 7. Thread Switching: Why Does ThreadLocal Not Propagate Context?

A Java task can run on another thread via `new Thread(...)`, `ExecutorService`, `CompletableFuture`, `@Async`, or a scheduler. With `MODE_THREADLOCAL`, the receiving thread **does not automatically have** the sending thread's context.

```text
HTTP request thread A
  SecurityContextHolder[A] -> Alice
           |
           | pool.submit(work)
           v
Pooled worker thread B
  SecurityContextHolder[B] -> empty (or leftover data if code is buggy)

If A passes Alice to B using a supported wrapper:
  save/capture context on task submission
  set Alice on B for the scope of the task
  work.run()
  finally clear/restore B's context
```

Do not try to fix this by calling `SecurityContextHolder.getContext()` inside the task hoping to get Alice: at that point you are reading **thread B**, not thread A.

### 7.1 DelegatingSecurityContextRunnable

Spring Security provides `org.springframework.security.concurrent.DelegatingSecurityContextRunnable`. It wraps a `Runnable`, sets `SecurityContext` for the executing thread, invokes the delegate, and clears the holder afterward. With the single-`Runnable` constructor, the wrapper captures the caller's context when the wrapper is constructed.

```java
Runnable businessTask = () -> {
    Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();
    System.out.println(auth == null ? "(none)" : auth.getName());
};

Runnable securedTask =
        new DelegatingSecurityContextRunnable(businessTask);

executor.execute(securedTask);
```

**This snippet plugs into an existing execution flow** and does not declare `executor` or build Authentication itself. Only wrap after the request is authenticated, never before the current user has been placed into the context.

### 7.2 DelegatingSecurityContextExecutor and Two Ways of Capturing

`DelegatingSecurityContextExecutor` wraps an `Executor`, avoiding the need to wrap each `Runnable` manually:

```java
Executor delegate = ...;

// This constructor captures the caller's context on each task submission,
// suitable for short tasks running under the current principal.
Executor securityAware =
        new DelegatingSecurityContextExecutor(delegate);

securityAware.execute(() -> doAuthorizedWork());
```

If the constructor receives a **fixed context**:

```java
SecurityContext explicitContext = ...;
Executor securityAware =
        new DelegatingSecurityContextExecutor(
                delegate, explicitContext);
```

then tasks use **that same fixed context**, not necessarily the user submitting the task. This is useful for a special controlled service identity, but dangerous if you accidentally create an executor with `ROLE_ADMIN` and pass it everywhere in the application. Inspect the exact constructor and lifetime; **never share a high-privilege mutable context across independent requests**.

Spring Security also provides `DelegatingSecurityContextCallable`, `DelegatingSecurityContextExecutorService`, `DelegatingSecurityContextAsyncTaskExecutor`, and related scheduler and Spring Task wrappers. Pick the adapter matching the actual abstraction, and do not arbitrarily clear Spring Security's thread-local yourself.

### 7.3 Propagation Passes Identity, Not Live Permission Updates

If a task is submitted at 10:00 with a context containing `ROLE_ADMIN`, and that role is revoked at 10:01, a task running at 10:02 **does not automatically know** the role was revoked just because the wrapper transferred the context. For critical operations, re-check account status, tenant membership, and object-level authorization at execution time.

If a task is queued for a long time, sent to another process, or handled by a message broker, you should not serialize the entire `SecurityContext`, principal, or password verifier for indefinite reuse. Pass verified subject ID/tenant/action, design a bounded and scoped delegation token or service identity, and **reauthorize** in the consumer per policy.

## 8. Runnable Java 17+ Example: Worker Without Context vs. Proper Wrapper Propagation

This example uses `spring-security-core` 6.5.6 and Java 17. It creates a simulated `Authentication` **marked authenticated solely to test holder behavior locally**, not for real HTTP user login. Never use this fake-token technique at boundaries accepting client data.

Project layout:

```text
context-holder-lab/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/ContextHolderLab.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'context-holder-lab'
```

File `build.gradle`:

```groovy
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
    implementation 'org.springframework.security:spring-security-core:6.5.6'
}

application {
    mainClass = 'demo.ContextHolderLab'
}
```

File `src/main/java/demo/ContextHolderLab.java`:

```java
package demo;

import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.concurrent.DelegatingSecurityContextRunnable;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

public final class ContextHolderLab {

    private ContextHolderLab() {
    }

    private static String principalName() {
        Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();
        return auth == null ? "(none)" : auth.getName();
    }

    public static void main(String[] args) throws Exception {
        // Demo once at startup only; DO NOT switch strategy during a request.
        SecurityContextHolder.setStrategyName(
                SecurityContextHolder.MODE_THREADLOCAL);

        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            SecurityContext context =
                    SecurityContextHolder.createEmptyContext();

            // Simulated authenticated token for local testing only.
            context.setAuthentication(
                    UsernamePasswordAuthenticationToken.authenticated(
                            "alice",
                            null,
                            AuthorityUtils.createAuthorityList(
                                    "ROLE_READER")));
            SecurityContextHolder.setContext(context);

            System.out.println("main=" + principalName());

            // Execute in a pooled worker without propagating context.
            String withoutContext = pool.submit(
                    (Callable<String>) ContextHolderLab::principalName)
                    .get();
            System.out.println("worker-plain=" + withoutContext);

            // Wrap the task while still on main thread holding Alice's context.
            Runnable wrapped = new DelegatingSecurityContextRunnable(
                    () -> System.out.println(
                            "worker-wrapped=" + principalName()));

            pool.submit(wrapped).get();

            // Wrapper has cleared the context on the pooled worker.
            String afterWrappedTask = pool.submit(
                    (Callable<String>) ContextHolderLab::principalName)
                    .get();
            System.out.println("worker-after=" + afterWrappedTask);
        } finally {
            SecurityContextHolder.clearContext();
            pool.shutdown();
        }

        System.out.println("main-after-clear=" + principalName());
        SecurityContextHolder.clearContext();
    }
}
```

### 8.1 Running the Program

If the project has a Gradle wrapper:

```bash
./gradlew run --console=plain
```

On Windows PowerShell:

```powershell
.\gradlew.bat run --console=plain
```

If there is no wrapper, you can use `gradle run --console=plain` after installing a compatible Gradle version. `javac ContextHolderLab.java` alone is insufficient because the code imports Spring Security; Gradle resolves the classpath.

Stdout **of the Java program** (excluding Gradle logs):

```text
main=alice
worker-plain=(none)
worker-wrapped=alice
worker-after=(none)
main-after-clear=(none)
```

This output is deterministic with `MODE_THREADLOCAL`, a single worker, and no external interference. It illustrates:

1. The main thread's context holds Alice.
2. Another raw worker does not have Alice's context.
3. The wrapper brings Alice into the exact scope of one task.
4. After the task, the wrapper clears the worker's context.
5. The main thread retains Alice until main itself performs cleanup.

**Do not infer** that because one wrapper worked, every `@Async`/scheduler is protected. Each execution path must use an appropriate abstraction or decorator, especially when tasks are submitted from different threads or when strategies change.

### 8.2 What Else to Test?

- Submit a task with Bob after Alice, confirming the worker no longer sees Alice.
- Submit a task that throws an exception and then run another task, confirming cleanup still executes.
- Submit multiple concurrent tasks to a multi-thread pool, verifying each task sees the right submitting principal.
- Create a wrapper with a fixed context and verify policy does not accidentally grant the same privileges to every caller.
- Switch security strategies between tasks only in an isolated test program to observe failures, **never in a JVM serving requests**.

## 9. Persisting Across HTTP Requests: SecurityContextRepository, Not Holder Strategy

**The most important distinction of this topic:** `SecurityContextHolderStrategy` answers **where the current execution's context is bound**. `SecurityContextRepository` answers **how a new request retrieves a previously saved context**. An application still uses `MODE_THREADLOCAL` even when using HTTP sessions, because a new request may run on a different thread and the filter will load the context from the repository at the proper time.

Typical implementations:

| Repository | Characteristics | When to Use |
| --- | --- | --- |
| `HttpSessionSecurityContextRepository` | Attaches `SecurityContext` to `HttpSession`, allowing subsequent requests with a session cookie to reload the context. | Form login / stateful sessions. |
| `RequestAttributeSecurityContextRepository` | Holds context in an attribute **for a single request only**, supporting dispatches such as error within the same request. | Request lifetime that must be preserved across servlet dispatches. |
| `NullSecurityContextRepository` | Does not save context for subsequent requests. | Stateless authentication where each request is verified independently. |
| `DelegatingSecurityContextRepository` | Delegates to multiple repositories, e.g., request attribute + HTTP session. | Common Servlet configuration in Spring Security 6. |

Changing `SecurityContextHolder.setStrategyName(MODE_INHERITABLETHREADLOCAL)` **does not** make a session survive after a request. Similarly, saving to `HttpSession` **does not** automatically give an `@Async` task context when running on a thread pool without propagation.

### 9.1 SecurityContextHolderFilter and Explicit Save in Spring Security 6

In Spring Security 6 configurations using `SecurityContextHolderFilter`, the filter **loads** the context from `SecurityContextRepository` and sets it on the holder; components performing authentication themselves (custom filters/controllers) that want to persist across requests must call `saveContext(context, request, response)` via the appropriate repository.

Illustrative pattern **after AuthenticationManager has verified credentials**:

```java
Authentication verified =
        authenticationManager.authenticate(authenticationRequest);

SecurityContext context =
        securityContextHolderStrategy.createEmptyContext();
context.setAuthentication(verified);
securityContextHolderStrategy.setContext(context);

securityContextRepository.saveContext(
        context, httpRequest, httpResponse);
```

This is an **integration pattern**, not a standalone Java class. `authenticationManager`, `authenticationRequest`, `httpRequest`, `httpResponse`, and the repository must come from actual configuration/framework objects. Do not call `saveContext` after the response has committed or on the wrong request/response.

`SecurityContextPersistenceFilter` in older configurations saved automatically when appropriate; `setContext` by itself does not guarantee persistence across all versions. Framework form login and built-in filters already handle saving the context via their own mechanisms, so do not arbitrarily stack an extra saving filter onto the chain.

### 9.2 A Single Request Can Have Multiple Dispatches

A Servlet request can have REQUEST, ERROR, FORWARD, and ASYNC dispatches. When an error dispatch occurs after the thread-local has already been cleared, `RequestAttributeSecurityContextRepository` helps preserve context for the same request in certain configurations. That differs from `HttpSessionSecurityContextRepository`, where context persists across **multiple requests** with a cookie/session.

Do not treat request attributes as a solution for keeping a user logged in after closing the browser or opening a new request. Also do not assume `SecurityContextHolderStrategy` understands error/async dispatch lifecycles on its own.

### 9.3 Stateless Does Not Mean No SecurityContext

With a stateless JWT resource server, each request still has an `Authentication`/`SecurityContext` during the current execution after token verification. `NullSecurityContextRepository` may be selected to **avoid persisting across requests**, yet the holder strategy still provides context on that thread. The next request must present the token again and be verified accordingly.

The bearer JWT mechanism does not invoke `UserDetailsService` by default, so the principal may be a `Jwt` rather than `UserDetails`. If a controller casts the principal to `UserDetails` unconditionally, the application can fail even though the holder strategy is working properly.

## 10. Servlet Async: Callable, DeferredResult, @Async, and Thread Pools

Even though all are "asynchronous", Spring Security's automatic integration differs:

| Execution Model | SecurityContext Status | Solution |
| --- | --- | --- |
| Synchronous controller in security filter chain | Context set by filter/repository for the request thread. | Use injected `Authentication` or holder appropriately. |
| Spring MVC controller returning `Callable<T>` | Spring Security MVC integration typically **propagates context automatically** to the thread invoking Callable via `WebAsyncManagerIntegrationFilter`. | Ensure MVC/Security async integration is in the chain; test dispatches. |
| MVC `DeferredResult<T>` with app-managed task | **No automatic propagation integration for arbitrary tasks**. | Use DelegatingSecurityContext wrappers/Executor or explicit principal. |
| `@Async` on a custom Spring executor | Task typically runs on a different thread, does not inherit ThreadLocal. | Appropriate `DelegatingSecurityContextAsyncTaskExecutor`/TaskDecorator and cleanup. |
| Default `CompletableFuture.supplyAsync` | May run on common ForkJoinPool, does not retain caller context. | Pass a security-aware executor or explicit trusted identity; never use global. |
| `ExecutorService.submit` | Workers are reused; context does not follow task automatically. | `DelegatingSecurityContextExecutorService` or wrapped Runnable/Callable. |
| Schedulers/jobs/background messages | May no longer have a valid HTTP request/principal. | Use a service identity or subject ID + execution-time authorization checks. |
| Reactive WebFlux / Reactor | Uses Reactor `Context` and `ReactiveSecurityContextHolder`. | Do not use Servlet ThreadLocal as the primary mechanism. |

**Specifically:** Spring Security provides automatic support for Spring MVC `Callable`, whereas documentation notes it **does not automatically integrate completely with `DeferredResult`** because the task completing it is orchestrated by the application. You cannot conclude "Spring MVC async always carries SecurityContext".

### 10.1 Servlet Callable Example (Controller Snippet)

Inside a `@RestController` that has passed through the filter chain:

```java
@GetMapping("/api/callable-name")
public Callable<String> callableName() {
    return () -> {
        Authentication current =
                SecurityContextHolder.getContext().getAuthentication();

        return current == null
                ? "(none)"
                : current.getName();
    };
}
```

This snippet requires Spring Web MVC and Spring Security Servlet and cannot run standalone with `javac`. With standard MVC async configuration, `WebAsyncManagerIntegrationFilter` binds the existing context to the thread executing `Callable`. Test requests, async dispatches, and error/timeout paths against your actual security chain.

### 10.2 DeferredResult Example with a Wrapped Executor

If the app dispatches work to an executor itself:

```java
private final Executor securityAwareExecutor;

// In the constructor:
// securityAwareExecutor =
//     new DelegatingSecurityContextExecutor(rawExecutor);

@GetMapping("/api/deferred-name")
public DeferredResult<String> deferredName() {
    DeferredResult<String> result = new DeferredResult<>(5000L);

    securityAwareExecutor.execute(() -> {
        Authentication current =
                SecurityContextHolder.getContext().getAuthentication();
        result.setResult(current == null
                ? "(none)"
                : current.getName());
    });

    return result;
}
```

This snippet is **part of a controller**, omitting full imports/beans. `securityAwareExecutor` must be properly configured to capture the caller's context at `execute(...)` time. Handle timeouts/cancellations/errors, executor shutdown, async servlet dispatches, and ensure context is not retained after the task completes.

### 10.3 Is Passing Identity to Background Jobs Always Right?

No. Preserving Alice's full privileges in a job running for hours can cause *stale authority* if Alice's permissions are revoked or her tenant changes. For durable jobs, it is usually better to:

- Record the verified **account ID / tenant ID / action / request ID**, rather than serializing raw `SecurityContext` or passwords.
- Explicitly specify the policy for whether the job runs under the requester's permissions, a service account, or pre-approved privileges.
- Re-check account/membership and resource permissions when the job runs, or use a time-bounded, scoped delegation grant.
- Avoid reusing one mutable `SecurityContext` across multiple parallel tasks.
- Clean up/revoke state when a worker completes, fails, or retries.

Propagation **preserves an execution context**; it does not replace authentication or authorization.

## 11. Spring Boot 3.x: Controller Reading Filter-Provided Principal

The small example below shows a servlet app using the default `MODE_THREADLOCAL` that still authenticates the user on each request. Because it uses HTTP Basic, the code **does not manually set a strategy** or store context globally.

Structure:

```text
context-servlet-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/ServletContextApplication.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'context-servlet-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

File `src/main/java/demo/ServletContextApplication.java`:

```java
package demo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ServletContextApplication {

    public static void main(String[] args) {
        SpringApplication.run(ServletContextApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("local-demo-password"))
                .roles("READER")
                .build();

        UserDetails bob = User.withUsername("bob")
                .password(encoder.encode("different-local-password"))
                .roles("READER")
                .build();

        return new InMemoryUserDetailsManager(alice, bob);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/api/me").authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

@RestController
class ContextController {

    @GetMapping("/api/me")
    Map<String, Object> me(Authentication authentication) {
        Authentication fromHolder =
                SecurityContextHolder.getContext().getAuthentication();

        return Map.of(
                "argumentName", authentication.getName(),
                "holderName", fromHolder.getName(),
                "authorities", authentication.getAuthorities().stream()
                        .map(a -> a.getAuthority())
                        .sorted()
                        .toList());
    }
}
```

This is a standalone runnable app if the two starters are installed; it is not a JDK-only program. It shows that within the same request, Spring MVC injects `Authentication` and the holder reads the same principal under normal configuration. **Do not use this example to conclude that async executors or subsequent requests do not need authentication**.

Run:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Send requests (localhost demo only; real passwords require HTTPS):

```bash
curl -i http://localhost:8080/api/me
curl -i -u alice:local-demo-password http://localhost:8080/api/me
curl -i -u bob:different-local-password http://localhost:8080/api/me
```

Expected results:

| Request | Status | Body / Meaning |
| --- | --- | --- |
| No credentials provided | HTTP 401 | Endpoint requires authenticated. |
| Alice + valid password | HTTP 200 | `argumentName=alice` and `holderName=alice`; `ROLE_READER`. |
| Bob + valid password | HTTP 200 | `argumentName=bob` and `holderName=bob`; `ROLE_READER`. |

Each request passes through the corresponding filter/manager and is placed into its own execution context. When the container reuses the same physical thread, the filter chain must establish and clean up the context properly; **not because ThreadLocal inherently knows about HTTP cookies or user IDs**.

## 12. Context Leakage in Thread Pools: Two Common Mistakes

### 12.1 Forgetting to Clean Up After a Task

```java
// WRONG: illustrates a job managing scope manually without finally.
executor.execute(() -> {
    SecurityContextHolder.setContext(contextOfAlice);
    processSomething();
    // Forgot clearContext; pooled worker may run Bob's task next.
});
```

If the worker is reused, another task reading `SecurityContextHolder` before setting its own context may see Alice. This is a **cross-request/cross-user confusion** bug.

Prefer `DelegatingSecurityContextRunnable`/`Executor`; or when writing a custom adapter for special requirements, enforce a strict save/restore contract and cleanup in `finally`, testing exception paths too.

### 12.2 Capturing Context at the Wrong Time

```text
T0: App startup creates a fixed SecurityContext with service-admin.
T1: Alice submits a task to the Executor using that fixed context.
T2: Bob submits a similar task.
T3: Both Alice and Bob run under service-admin.
```

Use the `DelegatingSecurityContextExecutor(delegate, explicitContext)` constructor only when **intentionally** running under a service identity with dedicated permission design. If each task should use the caller's identity, use `DelegatingSecurityContextExecutor(delegate)` so it captures at task submission.

Avoid passing an `Authentication` containing sensitive credentials/hashes to tasks that do not need them. For long-running background work, holding context long-term causes stale role snapshots, increases secret retention in memory, and makes revocation difficult.

## 13. Deferred Loading, Suppliers, and the Trap of "Keeping a Supplier for Future Use"

Spring Security 5.8+ provides `getDeferredContext()` and `setDeferredContext(Supplier<SecurityContext>)` on the strategy. They support **deferring `SecurityContext` retrieval until needed**, especially when a repository wants to avoid accessing the session if the request needs no authentication.

Conceptual example:

```java
SecurityContextHolderStrategy strategy =
        SecurityContextHolder.getContextHolderStrategy();

Supplier<SecurityContext> deferred =
        strategy.getDeferredContext();

// Only when actually needed within the same valid lifecycle:
SecurityContext current = deferred.get();
```

**Do not mistake the supplier for an immutable identity token.** It may depend on the scope/repository/request/thread at retrieval time and must not be used arbitrarily after the HTTP request has finished. Never serialize a supplier into a queue, keep it in a singleton/cache, or pass the supplier to a worker thread treating it as official propagation.

If you need to capture identity for a task, use a Spring Security-supported wrapper or a controlled snapshot/principal, along with cleanup. If you want to persist login across subsequent requests, use `SecurityContextRepository.saveContext`, not `setDeferredContext` as a "session replacement".

### 13.1 When Customizing Strategy, Respect the Deferred API

An older implementation thinking only of `getContext`/`setContext`/`clearContext` may overlook the performance or semantics of deferred suppliers when Spring Security components already use `getDeferredContext`. Read the exact Javadoc for your version, implement/override defaults properly, and test requests that do not touch authentication, error dispatches, and async boundaries.

Do not assume a `ThreadLocal<SecurityContext>`-based strategy is sufficient if the app uses built-in supplier-based propagation/repositories. Customizing core security requires thorough unit/integration tests, not a quick hack to fix a null principal.

## 14. Limits of Servlet, @Async, and Reactive Stacks

### 14.1 WebFlux Does Not Use ThreadLocal the Servlet Way

Spring WebFlux/Reactor uses an asynchronous model where schedulers can switch threads mid-pipeline. `ReactiveSecurityContextHolder` stores the context in **Reactor Context**; merely calling `SecurityContextHolder.setStrategyName(MODE_INHERITABLETHREADLOCAL)` does not replace reactive context propagation.

Do not copy Servlet controllers into Reactor `Mono/Flux` assuming `SecurityContextHolder.getContext()` will always have the principal. Use `ReactiveSecurityContextHolder`, `ReactiveSecurityContextRepository`, and pipeline-appropriate operators. This lesson does not implement reactive authentication because the focus is Servlet.

### 14.2 Virtual Threads Do Not Make Scope Bugs Disappear

Java 21+ provides virtual threads, while the demo application runs Java 17. Whether using platform threads or virtual threads, you must still define context **lifetime and ownership**, execution transfer points, and cleanup. Never switch to `MODE_GLOBAL` just because an application uses virtual threads.

### 14.3 Multi-Tenancy and Principals

Two users in two different tenants can have the same username. Strategy is not the place to select a tenant. An authenticated principal must carry account/tenant IDs from a trusted source, while authorization and queries must be scoped by tenant and resource. A leaked ThreadLocal can trick a service into treating tenant B's request as tenant A — making cleanup and cross-tenant testing especially critical.

### 14.4 Sessions/JWTs Do Not Auto-Update Authorities

Propagation holds a `SecurityContext`/`Authentication` instance that may be a **snapshot** from login time. If an account is disabled, a role is revoked, or tenant membership changes, threads/tasks holding the context do not automatically reload the new state. Session/token revocation, auth versioning/freshness, or live authorization checks are required per policy; this is a **different** limitation from the thread-storage strategy question.

## 15. Essential Test Matrix

| Scenario | Assertion to Verify |
| --- | --- |
| Default MODE_THREADLOCAL | Two independent threads do not automatically share the same security context. |
| Interleaved Alice and Bob requests on pool | Each request reads the right principal; Alice does not leak to Bob. |
| Synchronous controller | Injected `Authentication` and holder match after authentication filters. |
| Raw Executor task from Alice | Alice is not automatically present on worker without propagation. |
| Wrapped Runnable from Alice | Worker sees Alice **in scope**; subsequent task no longer sees Alice. |
| Wrapped task throws exception | Worker context is cleared even when an exception occurs. |
| Fixed admin-context executor | Used only when intended/authorized; callers Alice/Bob do not accidentally become admin. |
| InheritableThreadLocal + new Thread | Child may see parent at thread creation; parent/child ownership tested. |
| InheritableThreadLocal + pooled Executor | Does not rely on per-submission inheritance; must not leak old user. |
| MODE_GLOBAL on server | Disabled; config tests ensure server uses an appropriate strategy. |
| Custom strategy | `getContext` non-null, `clearContext` truly clears association, deferred API accurate. |
| Form login + HttpSession | Context is saved/reloaded across requests even when physical threads change. |
| Custom authentication without save | Next request does not retain login; repository must be called properly. |
| NullSecurityContextRepository | Does not persist across requests; still has context within authenticated request. |
| ERROR/ASYNC dispatch | Request attribute/repository + async integration preserve context per configuration. |
| MVC Callable | Context can be propagated automatically by integration filter. |
| MVC DeferredResult with manually submitted task | Requires executor/wrapper; not propagated automatically from all sources. |
| @Async / CompletableFuture common pool | Does not read caller user without valid propagation. |
| Logout | clearContext must not be treated as revoking all sessions/tokens. |
| Role revoked while task is queued | Authorization/freshness checked at execution time if policy requires. |
| JWT/OIDC principal | Do not cast every principal to `UserDetails`. |
| WebFlux pipeline | Uses ReactiveSecurityContextHolder, not servlet ThreadLocal. |

For concurrency tests, use `CountDownLatch`/`CyclicBarrier` to force two users to interleave rather than testing sequentially. Also test cleanup on exceptions, timeouts, cancellations, and worker restarts. Testing "no principal leak" is just as important as testing "principal is propagated".

## 16. Common Pitfalls and Debugging Checklist

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| Principal present in controller, null in `CompletableFuture` | Task runs on another thread under MODE_THREADLOCAL. | Use a security-aware executor or pass identity explicitly; never enable GLOBAL. |
| `@Async` occasionally sees another user | Thread pool retains leftover context or inheritance captured at thread creation. | Clean up in finally, use standard delegating executor/TaskDecorator, test interleaved users. |
| Logged in, yet next request is anonymous | Custom authentication only called `setContext` without `saveContext` to repository, or stateless policy. | Check SecurityContextHolderFilter/Repository, session cookie, and explicit save. |
| Old session still works after logout | Only called clearContext on thread or failed to invalidate session/server token. | Use logout handlers/repository/session invalidation and token revocation per policy. |
| MODE_GLOBAL gives user B A's permissions | A single JVM-wide context shared across requests. | Never use GLOBAL in a Servlet server. |
| Inheritable works with new Thread but fails on pool | Inheritance occurs only at thread creation, not per task. | Use DelegatingSecurityContextExecutor/Callable appropriately. |
| Wrapper used, yet task sees old roles | Context captured before role change; snapshot does not auto-refresh. | Perform reauthorization/freshness checks per policy. |
| ThreadLocal doesn't leak in unit tests but leaks in production | Tests don't reuse threads or lack exceptions/timeouts. | Stress test pool, worker reuse, exception cleanup, mixed principals. |
| Calling `getContext().setAuthentication` causes session B to change like A | Mutated a potentially shared context instance. | Create a new context and verify ownership/persistence. |
| Reactive system lacks principal | Attempting to use Servlet ThreadLocal inside Reactor pipeline. | Use ReactiveSecurityContextHolder/Reactor Context. |
| Custom filter chain lacks principal | Different strategy/repository, wrong filter order, auth incomplete. | Check exact filters/manager, getContextHolderStrategy, and save lifecycle. |
| Context exists but `getAuthentication()==null` | Empty context, unauthenticated, or already cleared. | Check where authentication is set, anonymous handling, and pipeline. |
| SecurityContextHolder.getInitializeCount increases unexpectedly | Code changing strategy multiple times. | Remove strategy changes from request/test paths leaking into runtime; configure once at startup. |

### Safe Debugging Order

1. Which `SecurityFilterChain` did the request hit and which provider authenticated it?
2. What is the current `SecurityContextHolderStrategy`? Is anything calling `setStrategyName`/`setContextHolderStrategy` while the app is running?
3. Does `Authentication` exist **on the executing thread**? Do not just inspect another thread in the debugger.
4. If async, which executor/Callable/DeferredResult created the thread? **When** was the context captured?
5. Does the task clean up context in `finally`, including on exceptions/timeouts?
6. If spanning a new request, what type is `SecurityContextRepository`, was `saveContext` called, and is there a real session/token?
7. Did permissions/status change after login? Is the context snapshot still valid under policy?
8. With multiple users/tenants, is identity being mixed via pool, cache, or global mode?
9. Are logs printing raw `Authentication`, credentials, cookies, JWTs, or password hashes? Filter them out.

Never log raw `SecurityContext` or `Authentication` to debug in production. Sufficient details are usually request ID, filter/strategy type, thread ID (not as a substitute for user ID), verified account ID, principal type, and normalized outcome.

## 17. Exercises with Answers

**Question 1.** A controller can read Alice. A `CompletableFuture.supplyAsync(...)` using the common pool reads `SecurityContextHolder` and sees `null` authentication. Why?

**Answer:** Under `MODE_THREADLOCAL`, worker threads have their own context slots and do not automatically inherit from the request thread. Use an executor/wrapper with proper security context propagation or pass a verified subject ID and reauthorize where it runs.

**Question 2.** Why not enable `MODE_GLOBAL` so all threads see the principal?

**Answer:** Global uses a single shared context across the JVM; concurrent users can overwrite or observe each other's identity. This is a cross-user/cross-tenant risk and must not be used for multi-user Servlet servers.

**Question 3.** `MODE_INHERITABLETHREADLOCAL` allowed `new Thread(...)` to read the user. Why does submitting to an `ExecutorService` still fail?

**Answer:** Inheritance happens when a worker thread **is created**, not at `submit` time. Reused workers in a pool may have inherited from an old moment or with no context, breaking scope. Use a delegating executor.

**Question 4.** A task sets Alice's context on a pooled worker and forgets to clear it. What happens to Bob's subsequent request using the same worker?

**Answer:** If no filter or wrapper sets and clears properly, Bob's task can read Alice's identity. Cleanup must be enforced in `finally` and tested for worker reuse.

**Question 5.** Does `SecurityContextHolder.setContext(...)` automatically keep a login alive for the next request?

**Answer:** No. The holder strategy manages execution scope, not persistence across HTTP requests. With Spring Security 6 custom authentication, you must save to `SecurityContextRepository` if policy requires stateful login.

**Question 6.** How do `RequestAttributeSecurityContextRepository` and `HttpSessionSecurityContextRepository` differ?

**Answer:** Request attribute keeps context within a single request across certain dispatches; HttpSession binds context to a session so other requests with the session cookie can reload it. Both are independent of choosing ThreadLocal or InheritableThreadLocal.

**Question 7.** `clearContext()` is called in a controller. Can we say the user has been logged out of all devices?

**Answer:** No. It clears the current execution's association; it does not automatically invalidate other sessions, revoke JWTs/refresh tokens, or clear the session store. Proper logout/revocation mechanisms are required.

**Question 8.** A `DelegatingSecurityContextExecutor` is created with an explicit `ROLE_SUPERADMIN` context at startup. Ordinary users submit tasks. What can happen?

**Answer:** Tasks may run under the same fixed high-privilege context. Only use a fixed context when an authorized service identity is intentionally designed; for per-user tasks, use a wrapper capturing context at submission and reauthorize as needed.

**Question 9.** Do Spring MVC `Callable` and `DeferredResult` have the same level of automatic context propagation?

**Answer:** No. Spring Security provides MVC integration for `Callable`. For `DeferredResult` completed by an app-managed worker, there is no automatic integration covering all tasks; a security-aware executor/wrapper or explicit identity is required.

**Question 10.** A JWT has been verified in a servlet request, and `SecurityContextHolder` returns a `Jwt` principal. Is casting `(UserDetails) authentication.getPrincipal()` guaranteed to work?

**Answer:** No. The principal depends on the authentication mechanism. Use `Authentication.getName()` or type-safe adapters and matching policies; the holder only provides context and does not normalize every principal to UserDetails.

**Question 11.** An admin revokes `ROLE_MANAGER` after a task was already captured with that role. Does the wrapper automatically fetch the new roles?

**Answer:** No. The wrapper propagates the existing context and does not query the store again by default. For sensitive jobs, check current account/membership/authorization at execution time, or use expiration/revocation policies.

**Question 12.** Why should `createEmptyContext()` be used when creating a new authentication?

**Answer:** To obtain a fresh `SecurityContext` with clear ownership, avoiding mutating an instance that might be shared by a session, repository, or another thread. However, you must still save properly to the repository if you want it persisted across requests.

## 18. Production Design Checklist

1. **Keep the default mode:** Multi-user Servlet servers use `MODE_THREADLOCAL` unless there is a thoroughly reviewed reason.
2. **Configure once:** Never change the JVM-wide holder strategy in a controller, filter, or after threads are running.
3. **Clear scopes:** Filters/requests/tasks have proper create, set, clear, and restore lifecycles; clean up on exceptions.
4. **Do not mix responsibilities:** HolderStrategy manages execution association; repository manages persistence; provider manages authentication.
5. **Comprehensive async audit:** Audit `@Async`, `CompletableFuture`, `ExecutorService`, MVC `Callable`, `DeferredResult`, schedulers, and message workers.
6. **Bounded propagation:** Per-user tasks use wrappers/capture at submit time; fixed service-account contexts only when intentional, never granting high roles to every job.
7. **Minimal identity:** Context/principal must not retain raw passwords or serialize secrets; use verified account/tenant IDs.
8. **Prevent staleness:** Propagation does not replace authorization checks; maintain role/account status freshness and token/session revocation policies.
9. **Servlet persistence:** When custom login needs stateful persistence, call `SecurityContextRepository.saveContext` per Spring Security 6 lifecycle.
10. **Explicit statelessness:** Use appropriate repos/chains; every JWT/Basic request still requires authentication—do not assume ThreadLocal preserves login for the next request.
11. **Concurrency testing:** Test interleaved Alice/Bob, thread-pool reuse, exceptions, async dispatches, cancellations, timeouts, and multiple tenants.
12. **Different for Reactive:** WebFlux uses Reactor Context; do not copy ThreadLocal strategies from Servlet.
13. **Monitoring:** Log filtered metadata, detect unexpected strategy re-initializations, missing-principal errors, and signs of cross-user exposure.
14. **Security review:** Whenever adding custom strategies or new context propagation, review thread-safety and per-task/per-resource permissions.

## 19. Official References

- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `SecurityContextHolder`, default ThreadLocal, holder strategies, and filter lifecycle.
- [Spring Security 6.5 — SecurityContextHolder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/context/SecurityContextHolder.html): `MODE_THREADLOCAL`, `MODE_INHERITABLETHREADLOCAL`, `MODE_GLOBAL`, `getInitializeCount`, `setStrategyName`, `getDeferredContext`.
- [Spring Security 6.5 — SecurityContextHolderStrategy API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/context/SecurityContextHolderStrategy.html): `get/set/clear/createEmptyContext` and supplier API.
- [Spring Security 6.5 — Concurrency Support](https://docs.spring.io/spring-security/reference/6.5/features/integrations/concurrency.html): `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextExecutor`, and controlled wrappers.
- [Spring Security 6.5 — Persisting Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html): `SecurityContextRepository`, `HttpSessionSecurityContextRepository`, `RequestAttributeSecurityContextRepository`, `NullSecurityContextRepository`, and holder filter.
- [Spring Security 6.5 — Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): explicit save, `SecurityContextHolderFilter`, and session lifecycle.
- [Spring Security 6.5 — Spring MVC Integration](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/mvc.html): `@AuthenticationPrincipal`, `Callable` propagation, and `DeferredResult` limitations.
- [Spring Security 6.5 — WebAsyncManagerIntegrationFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/request/async/WebAsyncManagerIntegrationFilter.html): integrating SecurityContext with MVC Callable.
- [Spring Security — Reactive SecurityContextHolder](https://docs.spring.io/spring-security/reference/reactive/authentication/architecture.html): differences between Reactor Context and Servlet ThreadLocal.

**Remember:** `SecurityContextHolderStrategy` decides **how a context is attached to the current execution**, not how users are authenticated or how sessions persist across HTTP requests. On a Servlet server, **MODE_THREADLOCAL + filter cleanup** is the safe default; when switching threads, propagate identity per task with supported tools; when spanning requests, use the appropriate `SecurityContextRepository`/session/token. Never use `MODE_GLOBAL` or `MODE_INHERITABLETHREADLOCAL` to "patch" a null principal on a thread pool, because the risk of cross-user privilege leakage is far worse than the original missing-context bug.
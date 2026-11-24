# ThreadLocal Mechanism and Post-Processing Context Cleanup Requirements

> **Module:** Spring Security — authentication. **Topic Group:** Servlet Context. This lesson explains how Spring Security binds an identity to a Servlet request thread via `SecurityContextHolder`, why the context must be cleared once processing completes, and how to propagate context safely when an application uses thread pools or asynchronous execution. The hands-on section includes a standalone runnable Java 17 program on Spring Security 6.5.11.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Distinguish `Authentication`, `SecurityContext`, `SecurityContextHolder`, `SecurityContextHolderStrategy`, and `SecurityContextRepository`.
2. Accurately describe the `ThreadLocal` model: data belongs to the **currently running thread**, does not automatically belong to an HTTP request, and does not automatically propagate to other worker threads.
3. Explain why a reused Servlet worker can retain an old identity if the context is not cleared, even after the previous request has ended.
4. Recognize the cleanup responsibilities of `FilterChainProxy`/`SecurityContextHolderFilter` or `SecurityContextPersistenceFilter` in Spring Security configuration.
5. Use `createEmptyContext`, `setContext`, `getContext`, and `clearContext` at the proper lifecycle boundaries; prefer `try/finally` when managing context manually.
6. Distinguish **clearing a thread**, **persisting context**, **invalidating a session**, **logging out**, and **revoking a JWT**.
7. Propagate context to an `ExecutorService` via `DelegatingSecurityContextExecutorService`, and understand why `@Async` and `CompletableFuture` do not carry context by default.
8. Write tests simulating worker reuse, exception paths, and safe cleanup requirements.
9. Avoid confusing anonymous authentication, mutable contexts, and dangerous storage modes in multi-user web applications.

## 2. Distinguishing Five Concepts Before Writing Code

### 2.1. Authentication — The Subject and Accepted Proof

`Authentication` holds principal, credentials, authorities, and `isAuthenticated()`. A filter can create an **unauthenticated** authentication from a request, call `AuthenticationManager`/`AuthenticationProvider` to verify the proof, and receive an **authenticated** authentication.

`AuthenticationManager.authenticate(...)` returns an object or throws `AuthenticationException`. It **does not automatically store the result in ThreadLocal, a session, or a JWT**. Its filter/caller is responsible for attaching the result to the appropriate context. Never construct an `authenticated(...)` token from a client-supplied username/roles and place it into the holder as if it were verified.

### 2.2. SecurityContext — The Container Holding Authentication

`SecurityContext` is an object typically exposing `getAuthentication()` and `setAuthentication(...)`. It is neither a thread nor a session:

~~~java
SecurityContext context = SecurityContextHolder.getContext();
Authentication current = context.getAuthentication();
~~~

The default holder's `getContext()` returns a context (not `null`), but `getAuthentication()` **may be `null`**. Therefore, `getContext()!=null` is completely insufficient to conclude that "the user is logged in".

### 2.3. SecurityContextHolder — The Gateway to Read/Write the Current Context

Key APIs:

~~~java
SecurityContextHolder.getContext();
SecurityContextHolder.setContext(context);
SecurityContextHolder.createEmptyContext();
SecurityContextHolder.clearContext();
~~~

`SecurityContextHolder` is a static facade to the selected `SecurityContextHolderStrategy`. Do not use it as a global user data store. When used properly, method security, authorization, and components on the same thread can read the authentication of the task currently being processed.

### 2.4. SecurityContextHolderStrategy — Choosing Where the Context Is Bound

The default in Servlet apps is `MODE_THREADLOCAL`. Each thread has its own slot for the context. `MODE_INHERITABLETHREADLOCAL` allows certain child threads to inherit the value at **thread creation time**; `MODE_GLOBAL` has a single shared context across the JVM. The latter two modes require very careful evaluation and are not a quick fix for multi-user web apps.

### 2.5. SecurityContextRepository — Persisting Across Requests

`SecurityContextRepository` is responsible for retrieving/saving the context per request, session, or other policy. It solves **persistence**, not thread cleanup. Spring Security 6 commonly uses `SecurityContextHolderFilter`, which only reads/provides the context and requires an **explicit save** when a caller manually creates an authentication that needs to persist.

One-sentence distinction:
- **Propagate:** pass the context to another thread/task, with a defined lifetime boundary.
- **Persist:** write the context to a repository so future requests can read it back.
- **Clear:** remove the context from the current thread's holder when the scope ends.

These three actions may be related, but **they do not replace one another**.

## 3. What Is ThreadLocal and Why Does Spring Security Use It?

In Java, `ThreadLocal<T>` provides a separate storage slot for each thread:

~~~java
ThreadLocal<String> identity = new ThreadLocal<>();

identity.set("alice"); // Bound only to the thread calling set.
String name = identity.get();
identity.remove();     // Clears the value on that same thread.
~~~

If thread A calls `set("alice")`, thread B normally cannot read A's value. That is why ThreadLocal fits service methods deep in the call stack: developers do not have to pass `Authentication` through every parameter.

However, **ThreadLocal does not follow HTTP requests**. It only follows the thread. A thread that finishes one request can continue serving another request. Without cleanup, old data remains in that thread's slot.

### 3.1. Error-Prone Timeline

~~~text
Thread T-1: processes Alice's request A
             setContext(Alice) -> controller finishes
             BUG: skips clearContext()

Thread T-1: returned to the Servlet thread pool

Thread T-1: processes unauthenticated request B
             code reads SecurityContextHolder.getContext()
             may still contain Authentication(Alice)
~~~

This is the risk model for **code outside/bypassing standard filter boundaries** or custom workers that mismanage context. In a properly configured Spring Security `SecurityFilterChain`, the framework is responsible for clearing the holder; not every web app automatically suffers from this bug.

### 3.2. Two Different Isolation Concepts

| Isolation | What MODE_THREADLOCAL Guarantees | What It Does Not Guarantee |
| --- | --- | --- |
| Concurrent Thread A and Thread B | Each thread has its own holder slot | Does not prevent code from intentionally assigning the same mutable object to both |
| Two tasks running **sequentially on the same Thread A** | The same slot A is reused | Does not automatically clear the slot after Task 1 finishes |
| An HTTP request handing off to another worker | Does not travel automatically with the task | Does not automatically propagate Authentication |
| End of an HTTP request | Unaware that the request has ended | Requires filter/framework or caller cleanup |
| Session spanning multiple requests | ThreadLocal is not a session store | Does not automatically persist/revoke login |

### 3.3. Context Can Still Be Shared Across Different ThreadLocal Slots

`ThreadLocal` stores an **object reference**, without automatically deep-copying. If Thread A and Thread B are both assigned the same mutable `SecurityContext`, each thread has its own slot yet still points to the same instance. When one side calls `setAuthentication(...)`, the other can observe the change, creating a race condition and identity mix-up.

Therefore, when you need to **replace** the authentication in an already-authenticated flow, use `SecurityContextHolder.createEmptyContext()` to create a new object and attach the verified result, instead of mutating a context directly that might be referenced by a session or another worker.

## 4. Standard Lifecycle of a Servlet Request

A Servlet request typically passes through `DelegatingFilterProxy` → `FilterChainProxy` → a `SecurityFilterChain` selected by URL and chain order. Security filters are responsible for loading the context, authenticating, authorizing, and cleaning up.

~~~mermaid
sequenceDiagram
    participant C as HTTP Client
    participant FP as FilterChainProxy
    participant CF as SecurityContextHolderFilter
    participant AF as AuthenticationFilter
    participant AS as Authorization + Controller
    participant SH as SecurityContextHolder
    C->>FP: HTTP request
    FP->>CF: Matching SecurityFilterChain
    CF->>SH: Provide context from repository
    CF->>AF: Proceed down chain
    AF->>AF: If credentials present: authenticate
    opt Authentication succeeds
        AF->>SH: Set valid Authentication
    end
    AF->>AS: Proceed
    AS->>SH: Read context/Authentication
    AS-->>CF: Response or exception
    Note over CF,SH: finally: clearContext() for current thread
    CF-->>C: Complete HTTP response
~~~

This conceptual diagram cannot show every filter, lazy/deferred context, async dispatch, or specific repository. Spring Security documentation states that `FilterChainProxy` guarantees the holder is cleared when a request completes; the filters managing security context take care of that lifecycle.

### 4.1. SecurityContextHolderFilter in Spring Security 6

`SecurityContextHolderFilter` typically obtains a `Supplier<SecurityContext>` from `SecurityContextRepository` and sets a deferred context on the holder. After the downstream chain runs, even if an exception is thrown, the filter clears the holder in a `finally`-style block.

Pseudocode illustrating the principle:

~~~java
try {
    // Set up SecurityContext source from repository / deferred context.
    filterChain.doFilter(request, response);
}
finally {
    securityContextHolderStrategy.clearContext();
}
~~~

The variables in this snippet belong to framework/filter code; this is **not a standalone Java class**. Do not copy it into a controller and call clear while the request still needs Authentication.

### 4.2. Why Clear at the End of the Chain, Not in Every Filter?

If a custom filter calls `clearContext()` immediately after authenticating and then lets the request proceed, `AuthorizationFilter`, method security, or the controller may not see the principal. Proper cleanup must occur **after the entire scope using the context**.

A filter in the middle of the chain **should not** clear arbitrarily if it does not own the lifecycle. With the standard framework, there is usually no need to write an extra cleanup filter. With custom code managing context outside the framework, set the context yourself and use `try/finally` at the proper scope.

### 4.3. Exceptions Must Not Bypass Cleanup

A controller throwing a runtime exception, a password provider throwing `AuthenticationException`, or a request being denied by authorization — all of these are paths where the thread is eventually returned to the pool. If the context owner only clears on the success branch, data can remain on the failure branch.

Proper structure when the **caller manages the context boundary itself**:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verifiedAuthentication);

try {
    SecurityContextHolder.setContext(context);
    executeAuthorizedWork();
}
finally {
    SecurityContextHolder.clearContext();
}
~~~

`verifiedAuthentication` must come from a trusted mechanism. `executeAuthorizedWork()` is application-defined integration logic; this snippet illustrates `try/finally`, not standalone code or instructions for self-granting permissions from client input.

### 4.4. SecurityContextPersistenceFilter in Legacy Configurations

Some older/customized systems use `SecurityContextPersistenceFilter`. It manages loading, saving, and clearing the context, whereas Spring Security 6's `SecurityContextHolderFilter` typically only loads/provides the context and clears it, requiring explicit saves when needed.

Do not configure both filters in the same security chain hoping to be "doubly safe". Identify the actual filter in use, the framework version, and the `requireExplicitSave` configuration.

## 5. Clear, Save, Logout, and Token Revocation Are Four Different Things

| Operation | Goal | Effect |
| --- | --- | --- |
| `SecurityContextHolder.clearContext()` | Clean up the current thread | Detaches context from the thread holder per strategy |
| `securityContextRepository.saveContext(context, request, response)` | Save context per repository | Allows subsequent requests to reload context depending on policy |
| Logout / invalidate `HttpSession` | Terminate stored session | Depends on logout handler, session store, cookie, and configuration |
| JWT / refresh token revocation | Reject issued tokens | Requires expiry, revoke store/denylist/introspection, or dedicated policy |

### 5.1. An Example When Persistence Is Needed

If the application performs authentication manually after verifying real proof and wants to store it in the session:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authenticationReturnedByManager);
SecurityContextHolder.setContext(context);

// Only when the application needs to persist across requests using an appropriate repository:
securityContextRepository.saveContext(context, request, response);
~~~

This is an **integration snippet**; it must use an Authentication verified by a provider and valid `request`, `response`, and `securityContextRepository` objects from the Servlet flow. Saving does not replace cleanup, and cleanup does not replace saving.

### 5.2. Spring Security 6 Explicit Save

According to Spring Security 6 documentation, `SecurityContextHolderFilter` **does not automatically save** every change to `SecurityContext`. When manually establishing a login session that must survive across subsequent requests, the application must call `saveContext` appropriately or use an authentication mechanism that already handles it.

A request using `SessionCreationPolicy.STATELESS` or `NullSecurityContextRepository` still needs its ThreadLocal cleared after processing, even though there is no session to save. Do not confuse "stateless" with "no SecurityContext during the request".

### 5.3. clearContext Does Not Delete the Object Everywhere

`clearContext()` removes the context from the **calling thread's** holder. If that object is still held by `HttpSession`, a local variable, an async task, a cache, or another reference, it does not necessarily vanish from memory. You cannot rely on clearing to revoke a JWT, end a session, or remove a principal from all threads.

### 5.4. Why Not Replace It with setAuthentication(null)?

~~~java
SecurityContextHolder.getContext().setAuthentication(null);
~~~

That mutates the **Authentication inside the object** currently attached to the thread, but may keep the reference to `SecurityContext` and can affect a shared context. Cleanup must use `SecurityContextHolder.clearContext()` — the proper cleanup API of the strategy.

Similarly, `SecurityContextHolder.setContext(SecurityContextHolder.createEmptyContext())` creates a new empty context while still attaching an object to the thread; it does not express the same cleanup semantics as `clearContext()`.

## 6. Main Risk: Thread Pools Retaining the Previous Request's Identity

Example:

~~~text
Task 1 on worker W:
    setContext(Authentication Alice / ROLE_ADMIN)
    finishes processing, forgets clearContext()

Task 2 assigned to the same worker W:
    does not set context
    calls getContext().getAuthentication()
    receives leftover Alice
~~~

This can cause incorrect auditing, overly long principal retention, memory retention, or worse, authorization checks operating on the stale Authentication. The bug can appear intermittently due to task scheduling and thread reuse.

**Boundary to understand:** a properly configured `SecurityFilterChain` includes Spring Security's cleanup guarantee; the risk above specifically applies to **custom workers/executors, code calling setContext manually, filters running outside the security chain, and callbacks/batch tasks** that do not follow the lifecycle. Do not blame ThreadLocal when the actual bug is the code owner omitting cleanup.

## 7. Complete Java 17 Demo: Proving Propagation and Cleanup

The following program runs without a Servlet container, using **real Spring Security Core**. It creates a single-thread executor to ensure the worker thread **is reused**; it tests via `Future.get()` and actively checks output to fail immediately if behavior diverges from expectations.

One section intentionally simulates missing cleanup **for lab purposes only**, after which the program clears the leftover state. Do not use that pattern in production.

### 7.1. Project Structure

~~~text
security-context-lab/
├── settings.gradle
├── build.gradle
└── src/main/java/example/context/
    └── SecurityContextThreadLocalLab.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'security-context-lab'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.context.SecurityContextThreadLocalLab'
}
~~~

A real Spring Boot project should use dependency management/BOM to align framework versions and patches; the Gradle file above is just a standalone demo for Spring Security Core.

### 7.2. Full Java Code

File `src/main/java/example/context/SecurityContextThreadLocalLab.java`:

~~~java
package example.context;

import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.concurrent.DelegatingSecurityContextExecutorService;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

public class SecurityContextThreadLocalLab {

    private static SecurityContext labContext(String username) {
        SecurityContext context = SecurityContextHolder.createEmptyContext();

        // Use a DUMMY Authentication solely for the ThreadLocal experiment.
        // Production must never issue an authenticated token from unverified input.
        Authentication dummy =
                UsernamePasswordAuthenticationToken.authenticated(
                        username,
                        null,
                        List.of(new SimpleGrantedAuthority("ROLE_DEMO")));

        context.setAuthentication(dummy);
        return context;
    }

    private static String currentUser() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        return authentication == null
                ? "<none>"
                : authentication.getName();
    }

    private static void verifyAndPrint(
            String label, String actual, String expected) {
        if (!expected.equals(actual)) {
            throw new IllegalStateException(
                    label + " expected " + expected + " but got " + actual);
        }
        System.out.println(label + "=" + actual);
    }

    public static void main(String[] args) throws Exception {
        SecurityContextHolder.setStrategyName(
                SecurityContextHolder.MODE_THREADLOCAL);

        ExecutorService rawPool = Executors.newSingleThreadExecutor();

        try {
            verifyAndPrint("main-before", currentUser(), "<none>");

            verifyAndPrint(
                    "worker-before",
                    rawPool.submit(SecurityContextThreadLocalLab::currentUser)
                            .get(),
                    "<none>");

            // Simulate a verified request's context.
            SecurityContextHolder.setContext(labContext("alice"));
            try {
                verifyAndPrint("main-in-request", currentUser(), "alice");

                // Worker thread differs from main; does not inherit ThreadLocal.
                verifyAndPrint(
                        "worker-plain",
                        rawPool.submit(
                                SecurityContextThreadLocalLab::currentUser)
                                .get(),
                        "<none>");

                // Wrapper captures context from the submitting thread and
                // ensures cleanup on the worker when the task finishes.
                ExecutorService securePool =
                        new DelegatingSecurityContextExecutorService(rawPool);

                verifyAndPrint(
                        "worker-wrapped",
                        securePool.submit(
                                SecurityContextThreadLocalLab::currentUser)
                                .get(),
                        "alice");

                verifyAndPrint(
                        "worker-after-wrapped",
                        rawPool.submit(
                                SecurityContextThreadLocalLab::currentUser)
                                .get(),
                        "<none>");
            }
            finally {
                SecurityContextHolder.clearContext();
            }

            verifyAndPrint("main-after", currentUser(), "<none>");

            // INTENTIONALLY WRONG: worker sets context without clearing.
            // Demonstrates the bug only, not how real apps should be written.
            rawPool.submit(() -> {
                SecurityContextHolder.setContext(labContext("stale-user"));
            }).get();

            verifyAndPrint(
                    "worker-stale-next-task",
                    rawPool.submit(
                            SecurityContextThreadLocalLab::currentUser)
                            .get(),
                    "stale-user");

            // Clear on the EXACT worker holding the ThreadLocal.
            rawPool.submit(SecurityContextHolder::clearContext).get();

            verifyAndPrint(
                    "worker-after-clear",
                    rawPool.submit(
                            SecurityContextThreadLocalLab::currentUser)
                            .get(),
                    "<none>");
        }
        finally {
            // Best-effort cleanup even if assertions/workers throw exceptions.
            try {
                rawPool.submit(SecurityContextHolder::clearContext).get();
            }
            finally {
                rawPool.shutdownNow();
                SecurityContextHolder.clearContext();
            }
        }
    }
}
~~~

### 7.3. Running with Gradle

From the `security-context-lab` directory, using JDK 17+ and a compatible Gradle:

~~~bash
gradle run --quiet
~~~

If using Gradle Wrapper:

~~~bash
./gradlew run --quiet
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat run --quiet
~~~

**Output produced by `System.out.println`** (excluding Gradle output):

~~~text
main-before=<none>
worker-before=<none>
main-in-request=alice
worker-plain=<none>
worker-wrapped=alice
worker-after-wrapped=<none>
main-after=<none>
worker-stale-next-task=stale-user
worker-after-clear=<none>
~~~

These lines are deterministic because a single worker is reused and `main` awaits each `Future.get()`. The demo intentionally creates a short-lived stale context, then clears it immediately after demonstrating the risk.

### 7.4. Exact Explanation

- `main-before=<none>`: main does not have an Authentication yet.
- `worker-before=<none>`: worker initially has no Authentication.
- `main-in-request=alice`: main is bound to Alice's demo context.
- `worker-plain=<none>`: worker does not automatically see main's `MODE_THREADLOCAL`.
- `worker-wrapped=alice`: `DelegatingSecurityContextExecutorService` adapter uses the context at task submission time.
- `worker-after-wrapped=<none>`: the wrapper cleaned up after the task completed.
- `main-after=<none>`: `clearContext()` in `finally` cleans up main.
- `worker-stale-next-task=stale-user`: the task intentionally omitted clearing, so the next task sees the leftover identity.
- `worker-after-clear=<none>`: cleanup was executed **on the worker**, not via clearing on main.

### 7.5. Limitations of the Demo

The Authentication in `labContext(...)` is **simulated** for studying propagation. It does not check passwords/JWTs and cannot be used as login logic. Real applications must obtain an Authentication verified by a trusted provider/decoder/IdP.

The program demonstrates setting and clearing context across Java threads; it **does not simulate** sessions, CSRF, authorization, servlet dispatch, or every filter chain detail. Those must be tested separately in web integration tests.

## 8. Safe Patterns When the Application Owns the Context

### 8.1. Using try/finally in Custom Workers

~~~java
// verifiedAuthentication comes from a trusted source.
SecurityContext scoped = SecurityContextHolder.createEmptyContext();
scoped.setAuthentication(verifiedAuthentication);

try {
    SecurityContextHolder.setContext(scoped);
    runAuthorizedWork();
}
finally {
    SecurityContextHolder.clearContext();
}
~~~

The snippet above is integration code, not a standalone class. If the thread already had a **valid prior context** that must be restored after running, do not clear arbitrarily; you must have a save/restore policy and scope boundary. Spring Security wrappers are a good choice for tasks needing propagation.

### 8.2. Do Not Use a Fake Context to Bypass Authentication

An anti-pattern:

~~~java
// SERIOUSLY WRONG if username/roles come from an unverified HTTP request:
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(
        UsernamePasswordAuthenticationToken.authenticated(
                requestUsername, null, clientSuppliedAuthorities));
SecurityContextHolder.setContext(context);
~~~

It self-asserts the client's permissions without proof. For applications using username/password, call `AuthenticationManager` and use only a successful result. For JWTs, verify signature, issuer, audience/time, and claims per policy before constructing authentication.

### 8.3. Do Not Call clear Too Early Inside a Filter

~~~java
// Lifecycle ordering bug if downstream controllers need authentication.
SecurityContextHolder.setContext(verifiedContext);
SecurityContextHolder.clearContext();
filterChain.doFilter(request, response);
~~~

This snippet is just an **ordering error** example. The security context owner must clean up after downstream processing; in a standard Spring Security chain, let the filter infrastructure manage it.

### 8.4. Do Not Use clear Instead of Authorization

`clearContext()` is a state hygiene operation, not a 401/403 decision outcome. When a request is unauthorized, the authorization filter or policy must reject it, and the authentication entry point or access denied handler is responsible for rendering the HTTP response. Merely clearing the context and letting the controller proceed by default can break system logic.

## 9. Async Propagation and ThreadLocal Limits

### 9.1. Default ExecutorService

`ExecutorService.submit(...)` does not automatically carry the calling thread's ThreadLocal over to a pooled thread. The worker may have an empty holder, or worse, stale state from another task that failed to clean up.

Spring Security provides `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextCallable`, `DelegatingSecurityContextExecutor`, `DelegatingSecurityContextExecutorService`, `DelegatingSecurityContextAsyncTaskExecutor`, and related adapters to set and clear context per task.

Example (integration snippet):

~~~java
ExecutorService secured =
        new DelegatingSecurityContextExecutorService(rawExecutor);

secured.submit(() -> {
    Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();
    useAuthenticatedIdentity(authentication);
});
~~~

The constructor without an explicit context uses the context at the time **the task is submitted** per the API. `useAuthenticatedIdentity` is application-defined; do not apply it to jobs when the submitter is unauthenticated.

### 9.2. A Fixed Context Is Not Per-User Context

The adapter also has a constructor taking a specific `SecurityContext`:

~~~java
ExecutorService serviceIdentityExecutor =
        new DelegatingSecurityContextExecutorService(
                rawExecutor, serviceSecurityContext);
~~~

This means tasks use a **pre-supplied context** rather than capturing the user at submission time. Use it only when tasks truly need a least-privilege service identity that has been organizationally approved. Never accidentally use a fixed admin context for ordinary user requests.

### 9.3. Capturing a Mutable Reference Is Not an Immutable Snapshot

The propagated context may be a reference to the current `SecurityContext` object; if a task waits in a queue and the context or authorities are modified/revoked, you do not automatically have an immutable snapshot or permission re-check.

For tasks running for many minutes or hours, it may be better to pass only verified subject ID, tenant ID, and request ID, and re-verify permissions and revocation at execution time. Never store raw bearer tokens or raw passwords in a queue so a worker can "log in again".

### 9.4. @Async, CompletableFuture, and Servlet Async

- `@Async` typically runs on a different executor. Default `MODE_THREADLOCAL` does not guarantee the Spring Security principal transfers to the worker. `DelegatingSecurityContextAsyncTaskExecutor` or a valid propagation mechanism for the configured executor is required.
- `CompletableFuture.supplyAsync(...)` without a specified executor may use the common pool. It does not automatically see the Servlet thread's principal.
- Spring Security integrates with **Spring MVC `Callable`** through web async infrastructure, but you should not assume every `DeferredResult`, custom callback, manual `new Thread(...)`, or `CompletableFuture` is automatically propagated.
- Servlet async may use **different dispatches/different threads**. When needed, verify filter dispatch types, async integration, and cleanup at each boundary. Do not retain ThreadLocal after the response.
- Scheduled jobs have no request-bound principal; use a service identity or check permissions at execution time rather than borrowing the last logged-in context.

### 9.5. Does InheritableThreadLocal Solve This?

`MODE_INHERITABLETHREADLOCAL` enables inheritance when **creating a child thread**, not when **submitting a task** to a pre-existing worker. In a pool, a worker can live across many requests and retain a value inherited at an unrelated time.

Therefore, do not switch the entire app to `MODE_INHERITABLETHREADLOCAL` to "fix" `@Async`. That is a stale identity risk, not a per-task propagation solution.

## 10. Three Storage Modes and Use Cases

| Strategy | Characteristics | Apply Cautiously |
| --- | --- | --- |
| `MODE_THREADLOCAL` | Each thread has its own bound context | Suitable default for Servlet; clean up at end of scope |
| `MODE_INHERITABLETHREADLOCAL` | Newly created child threads can inherit parent context | Unsuitable for broad use with multi-user worker pools |
| `MODE_GLOBAL` | Single shared context for the JVM | Never use in multi-user web apps due to identity mix-up risk |

Changing the strategy via `SecurityContextHolder.setStrategyName(...)` is an **application-wide** configuration, not a per-request operation. If needed, decide it at startup; changing it at runtime can leave components holding different strategies.

Java virtual threads have per-thread ThreadLocal semantics, but they do not solve context management or automatically propagate context from the submitting thread. Some execution models have different lifetimes from platform thread pools; you must still ensure identity is not retained past its scope and avoid excessive unnecessary ThreadLocal state.

## 11. Checking Anonymous and Empty Context Cases

In Spring Security, `AnonymousAuthenticationFilter` can place an `AnonymousAuthenticationToken` in the holder to represent an unauthenticated user. Some token classes have `isAuthenticated()==true` by token contract, yet that is **not equivalent to a user who has proven a real identity**.

| Expression | What Can Be Inferred? | What Cannot Be Inferred |
| --- | --- | --- |
| `SecurityContextHolder.getContext()!=null` | Context object exists | User is logged in |
| `getContext().getAuthentication()!=null` | Authentication object exists | Not anonymous |
| `auth.isAuthenticated()==true` | Flag on token is true | Proof the user is verified per endpoint policy |
| `auth.getAuthorities()` | Authorities on the token | Permissions on current resource/tenant are definitely valid |
| `authorizeHttpRequests().authenticated()` | Framework policy evaluates based on trust resolver and context | Automatic revocation of old tokens/sessions when DB changes |

When writing authorization rules, use `authenticated()`, `hasAuthority(...)`, method security, and proper resource/tenant checks. Never use checks like `getContext() != null` as proof of authorized access.

## 12. Notes on Mutable Objects and Sessions

### 12.1. Do Not Mutate Session-Loaded Context Arbitrarily

A context loaded from a repository/session may be referenced by other objects. Code like:

~~~java
SecurityContextHolder.getContext()
        .setAuthentication(newAuthentication);
~~~

can unexpectedly modify a shared object. When replacing Authentication from a verified source, prefer calling `SecurityContextHolder.createEmptyContext()`, attaching it, and persisting per policy instead of mutating a potentially shared object. Also be cautious when multiple requests sharing the same session run concurrently.

### 12.2. ThreadLocal Clearing Is Not Session Deletion

A request uses a context from `HttpSessionSecurityContextRepository`. When it finishes:
- the thread's holder is cleared;
- `HttpSession` may **still keep the context** for subsequent requests;
- that is normal if the user still holds a valid session.

Logout requires dedicated logout flows/handlers and session policies. If an account is locked after the user has logged in, merely evicting the `UserDetails` cache and clearing the thread **does not guarantee** the session/JWT has been revoked.

### 12.3. Do Not Store Authentication in a Singleton Static Field

A singleton service that reads `SecurityContextHolder.getContext().getAuthentication()` in its constructor and saves it in a field can retain the startup/anonymous/another user's principal by mistake. Read from the holder at the **current request time** when needed, or pass minimal verified identity data. Never create a JVM-wide `static Authentication currentUser` variable.

## 13. Characteristic Errors When Cleanup Fails

| Issue | Symptom | Possible Cause |
| --- | --- | --- |
| Worker retains previous task's principal | Task B sees Alice even though no context was set | Worker manually called `setContext` without clearing |
| Controller loses principal after custom filter | `Authentication` is null upon entering controller | Filter cleared too early or filter order is wrong |
| `@Async` does not see user | Principal is null | Different thread; no propagation |
| Enabling InheritableThreadLocal causes intermittent bugs | Worker sees user of an old submitted task | Pool inherited at thread creation time, not per task |
| Subsequent stateless JWT request sees old user | Cross-request identity confusion | A custom path failed to load/clear context properly |
| Logged out but API session still works | Session not destroyed/revoked | Only called thread clear without invalidating session |
| Repeated requests cause memory retention | Principal/details held by worker long-term | ThreadLocal/reference not cleaned up |
| `@WithMockUser` test always passes | Missing cleanup goes undetected | Mock security context does not traverse real worker logic |
| Bug only appears on exceptions | Task throws before cleanup line | Not using `finally` |
| Right principal but stale authorities | Stale session/JWT | Not necessarily ThreadLocal; needs revalidation/revocation policy |

**Diagnosis should not rely on guessing from a single log:** identify which filter chain was selected, which thread ran the code, who set the context, when it was cleared, and whether Authentication could come from a session/ID token or a custom cache.

## 14. Meaningful Testing

### 14.1. Testing Worker Reuse

Run two tasks sequentially on `Executors.newSingleThreadExecutor()`:
1. Task 1 sets context A and completes.
2. Task 2 reads the holder without setting context.
3. If A is observed, cleanup is missing.
4. Add `try/finally` or a wrapper; Task 2 must see empty.
5. Re-run with Task 1 intentionally throwing an exception to ensure cleanup still happens.

This is why the demo uses exactly one worker and awaits `Future.get()`: so luck does not "hit" a different thread and mask the bug.

### 14.2. Testing Exceptions in a Worker

JUnit/integration pseudocode snippet:

~~~java
Future<?> failed = contextualPool.submit(() -> {
    throw new IllegalStateException("simulated failure");
});

assertThrows(ExecutionException.class, failed::get);

// Use RAW underlying pool to verify no context remains from wrapper:
Authentication residual = rawPool.submit(() ->
        SecurityContextHolder.getContext().getAuthentication()
).get();
assertNull(residual);
~~~

The variables `contextualPool`, `rawPool`, `assertThrows`, and `assertNull` must be defined in an appropriate test. This is not a standalone file. The intent is that exception paths **must not** leave a SecurityContext on the worker.

### 14.3. Testing Through Real Servlet/Spring Security

Use `MockMvc` with the security filter chain or end-to-end HTTP:
- Alice's request is authenticated and has ROLE_USER.
- Next request without credentials (under stateless policy) does not see Alice.
- Bob's request authenticates separately and does not see Alice's authorities.
- Requests failing in provider/controller still leave no context behind.
- Async `Callable`/`DeferredResult`/`@Async` behave properly with the real executor.
- Sessions and logout are tested under dedicated policies.

`MockMvc` may use the test thread and test support managing context itself; to accurately verify Servlet thread pool behavior under load, supplement with integration tests on an embedded server and inspect safe metadata. Do not log raw tokens/passwords for testing purposes.

### 14.4. Reviewing Custom Filters

Search for calls to:
- `SecurityContextHolder.setContext(...)`;
- `SecurityContextHolder.getContext().setAuthentication(...)`;
- `SecurityContextHolder.clearContext()`;
- custom `ThreadLocal<User>` or `InheritableThreadLocal`;
- `ExecutorService`, `@Async`, `CompletableFuture`, scheduled tasks;
- custom `SecurityContextRepository`.

For each occurrence, answer: **who created the Authentication? was it verified? who owns the lifecycle? when is it cleared? is there thread hopping? is persistence required?**

## 15. Non-Leaking Logging and Observability

For debugging, you can record:
- safe request ID/correlation ID, route template, HTTP status;
- thread ID/name when investigating worker reuse;
- Authentication/provider type and outcome;
- context installed/propagated/cleared milestones in custom workers;
- count of async tasks rejected or failing context propagation.

**Do not log:** raw `Authorization` headers, cookies/session IDs, passwords, bearer/JWT tokens, full `SecurityContext.toString()` or `Authentication.toString()`, or sensitive full principals/details. Those objects may contain credentials, claims, or PII.

If you observe "occasionally request A gets identity B", check custom context paths and thread reuse; however, also distinguish this from client-sent sessions/cookies or wrongly cached tokens. An identity bug can originate from multiple layers, not only ThreadLocal.

## 16. Anti-Patterns and Fixes

1. **Manually calling setContext without clearing in a background task:** use `try/finally` or a Spring Security adapter.
2. **Calling clear on the main thread to clean a worker:** `MODE_THREADLOCAL` only clears the calling thread.
3. **Clearing in a filter before the controller:** causes downstream to lose the principal. Let the owner manage end-of-scope cleanup.
4. **Cleaning up only on the success path:** exceptions easily leave leftover context. Use `finally`.
5. **Using MODE_GLOBAL in a multi-user Servlet app:** mixes identities across the entire JVM.
6. **Enabling MODE_INHERITABLETHREADLOCAL with thread pools:** can retain stale identity from worker creation time.
7. **Assuming context != null means logged in:** the context can be empty.
8. **Assuming authentication != null always means a real user:** anonymous tokens exist too.
9. **Manually creating an authenticated token from the request:** skips credential verification, leading to bypass.
10. **Reading Authentication in a singleton constructor:** risks holding wrong state long-term.
11. **Mutating a shared mutable context arbitrarily:** risks race conditions.
12. **Treating clearContext as logout:** sessions/tokens have separate lifecycles.
13. **Treating clearContext as saveContext:** cleanup does not persist.
14. **Thinking stateless means no need to clear:** every request context still requires a proper lifecycle.
15. **Using CompletableFuture's default commonPool and expecting a principal:** no automatic propagation exists.
16. **Using a fixed admin context for all tasks:** excessive privileges; use a dedicated, properly scoped service identity.
17. **Capturing Authentication into a long-lived job queue:** can become stale after privileges are revoked.
18. **Creating another ThreadLocal<User> expecting Spring Security to clean it:** custom holders need their own lifecycle.
19. **Not testing exception/reuse paths:** misses leak branches.
20. **Logging raw SecurityContext or Authentication:** can expose credentials/PII.
21. **Configuring both context filters "just to be sure":** architecturally wrong; pick the single right mechanism.
22. **Relying on a thread name to prove a user was verified:** thread names are not proof of identity.

## 17. Self-Check Questions

**1. Does a Servlet thread serving two consecutive requests automatically clear ThreadLocal after the first request?**  
Not by Java ThreadLocal semantics. The Spring Security filter chain must manage cleanup, or a custom owner must use `clearContext()`.

**2. Why does thread A see Alice while thread B sees null Authentication?**  
`MODE_THREADLOCAL` binds context per thread. Without propagation, B does not automatically receive A's context.

**3. Does calling `clearContext()` on A clear B's context?**  
No, under the default ThreadLocal strategy.

**4. Does `SecurityContextHolder.getContext() != null` prove a successful login?**  
No. It can return an empty context; proper Authentication policy checks are required.

**5. Is `Authentication.isAuthenticated()==true` always a verified user?**  
No. Anonymous tokens or custom-forged tokens can have the flag true; verify the origin mechanism and trust resolver/authorization.

**6. Does SecurityContextHolderFilter automatically save context into the session in Spring Security 6?**  
No; an explicit save is required if the caller wants persistence and the filter has no other saving mechanism.

**7. Can `clearContext()` be replaced with `getContext().setAuthentication(null)`?**  
Not equivalent: one mutates the object, while the other clears the thread's holder.

**8. @Async lacks a principal; should MODE_GLOBAL be enabled?**  
No. Use an executor/wrapper that propagates context in a controlled way, or a separate subject/service identity.

**9. Why does InheritableThreadLocal not safely fix thread pools?**  
It inherits at child thread creation time, whereas pool workers are reused for many subsequent tasks.

**10. Does a request throwing an exception need cleanup?**  
Yes, cleanup in `finally` by the owner or framework.

**11. Does clearContext revoke an unexpired signed JWT?**  
No. JWTs have their own expiration and revocation mechanisms.

**12. Why must tests reuse the same worker?**  
If Task 2 runs on a different worker, it may see an empty context even though Task 1 left state on the first worker.

**13. What two things does DelegatingSecurityContextExecutorService do?**  
Sets the appropriate context for the worker task and clears/restores the holder when the task finishes.

**14. A task is dispatched 30 minutes later with a captured context after the user's permissions were revoked: does it update automatically?**  
There is no guarantee. Long-running jobs require revalidation/policy checks at execution time.

**15. Is a singleton holding an Authentication field safe to avoid calling the holder on every request?**  
No. Singleton fields are shared across requests and can retain the wrong identity.

## 18. Implementation Checklist

- [ ] Identify the exact `SecurityFilterChain` and context filter used for the URL.
- [ ] Check `SecurityContextHolderStrategy`; do not switch to GLOBAL/INHERITABLE without strong justification.
- [ ] When setting context manually outside the framework, use `try/finally` and `clearContext()` on the right thread.
- [ ] Do not clear too early before controller/authorization.
- [ ] Clean up on exception paths as well.
- [ ] Never construct an authenticated token from unverified data.
- [ ] When persistence is needed, call `SecurityContextRepository.saveContext(...)` per policy.
- [ ] Do not confuse cleanup with logout/revocation/session invalidation.
- [ ] Audit `@Async`, executors, scheduled tasks, and CompletableFuture for propagation.
- [ ] Use proper wrappers; do not grant broad admin context to every task.
- [ ] Avoid uncontrolled sharing of mutable SecurityContext across threads.
- [ ] Do not hold Authentication in singleton static fields.
- [ ] Include thread reuse and exception tests alongside HTTP integration tests.
- [ ] Treat stale tokens/sessions as a separate concern from ThreadLocal cleanup.
- [ ] Ensure logs contain no tokens, passwords, cookies, or raw context objects.

**Conclusion:** In Servlet applications, `SecurityContextHolder` defaults to **ThreadLocal** so components on the same thread can read `Authentication`. Because threads are reused, **failing to clean up context after the processing scope can corrupt identity and cause leaks**. Spring Security manages this in the security filter chain; code that spawns its own threads/tasks and sets context manually must use appropriate wrappers or `try/finally`. Keep **propagating context to workers**, **saving context for future requests**, and **clearing context on the current thread** clearly separated.

### Official References

- Spring Security 6.5 — Authentication Architecture and SecurityContextHolder: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security 6.5 — Authentication Persistence/Session Management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security 6.5 — Concurrency Support: https://docs.spring.io/spring-security/reference/6.5/features/integrations/concurrency.html
- Spring Security 6.5.11 — DelegatingSecurityContextExecutorService API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/concurrent/DelegatingSecurityContextExecutorService.html
- Spring Security 6.5 — SecurityContextHolder API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/context/SecurityContextHolder.html
- Java SE 17 — ThreadLocal API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html

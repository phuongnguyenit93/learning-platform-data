# Creating a New Context Instead of Mutating an Object Shared Across Requests

**Module:** Spring Security – authentication. **Section:** Servlet Context.

## 1. The Problem: Two Requests Share a Session, Yet Authentication Changes Unexpectedly

In a Servlet application, developers often write:

~~~java
// Prone to shared-object mutation if SecurityContext comes from HttpSession.
SecurityContextHolder.getContext().setAuthentication(verifiedAuthentication);
~~~

The code looks reasonable because `SecurityContextHolder` defaults to `ThreadLocal`: each request usually runs on a separate thread. However, **ThreadLocal only isolates the reference storage slot**; it does not force the referenced object to be an independent copy.

A browser can send two parallel requests with the same `JSESSIONID`. If `HttpSessionSecurityContextRepository` loads **the exact same `SecurityContext` instance** from the session into both threads' holders, request A calling `setAuthentication` **directly on that instance** can cause request B to observe the principal/authorities changing mid-flight.

Spring Security 6.5 directly recommends:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verifiedAuthentication);
SecurityContextHolder.setContext(context);
~~~

This creates a **new context object**, replacing the thread's current reference instead of mutating a context that may be shared. For custom Servlet authentication that needs to preserve login to the next request, Spring Security 6 also requires saving to the right repository via `securityContextRepository.saveContext(context, request, response)`.

**Principle of this lesson:** authenticate properly → create a new `SecurityContext` → attach a trusted `Authentication` → place the new context in the holder → save via repository when a login session is needed. Never use context replacement as a way to self-grant permissions from client input.

## 2. Why Does ThreadLocal Not Prevent Shared Mutable State?

Four distinct conceptual layers:

| Layer | Function | Does Not Guarantee by Itself |
| --- | --- | --- |
| `SecurityContextHolder` | API to access the current scope's context | Does not deep-copy the context |
| `SecurityContextHolderStrategy` | Manages where the holder stores the reference, default `MODE_THREADLOCAL` | Does not make the held object immutable |
| `SecurityContext` | An object holding an `Authentication` | Does not guarantee single-request ownership |
| `Authentication` | Principal, authorities, credentials, details, and authenticated state | Not permanent data; may contain mutable nested objects |
| `SecurityContextRepository` | Loads/saves context per request/session policy | Does not necessarily clone the object on every load |
| `HttpSession` | Stores state by session identifier | One session can be accessed by multiple HTTP requests concurrently |

Illustration of two independent ThreadLocals pointing to the same object:

~~~text
                        HttpSession S
                       (SPRING_SECURITY_CONTEXT)
                                |
                                v
                      SecurityContext X
                    authentication=ROLE_USER
                          ^            ^
                          |            |
                 Thread A holder   Thread B holder
                 (request A)       (request B)
                   own slot          own slot
                          |            |
                          +--> same X <-+
~~~

`ThreadLocal` works properly: slot A and slot B are separate. **Object X is shared.** When A calls `X.setAuthentication(ROLE_ADMIN)`, B can see `ROLE_ADMIN` when reading X afterward, even though B never called `SecurityContextHolder.setContext`.

This is an issue of **object aliasing** (multiple references to the same object) and **mutability**, not proof that ThreadLocal is broken or that requests always share threads.

## 3. Common Scenario Causing Two Requests to Hold the Same Context

A single session is routinely shared by multiple tabs, background requests, AJAX calls, and HTTP/2 multiplexing. Example:

~~~text
09:00:00.000 Session holds X, Authentication=ROLE_USER
09:00:00.010 Request A: POST /step-up, loads X
09:00:00.020 Request B: GET /transfer, loads X
09:00:00.030 Request B: filter determines user=linh, ROLE_USER
09:00:00.040 Request A: step-up is verified
09:00:00.050 Request A: getContext().setAuthentication(newAuth)
09:00:00.060 Request B: service re-reads context -> may see newAuth
~~~

The fact that the new authentication may be valid does not make the behavior above architecturally sound: B started a task with one snapshot, yet mid-logic its identity was mutated indirectly. If B has multiple authorization/check layers, they can observe different states within the same request.

Potential impacts include:

- Inconsistent authorization between web filters and method security.
- Principal/tenant context changing inside an in-flight request.
- Logs/audits recording an identity that does not match the identity used in an earlier step.
- Race conditions very difficult to reproduce because thread and request ordering is non-deterministic.
- An app working properly in a single JVM may change behavior after moving sessions to Redis or scaling to multiple nodes.

**Do not assume every session backend returns the same object.** With session serialization or distributed stores, two requests may receive two copies; even then, **stale update / last-write-wins** remains an issue, despite no object aliasing between threads. Code should be safe in both situations.

## 4. Wrong Snippet and the Replacement

### 4.1. Mutating the Existing Object Directly

~~~java
Authentication verified =
        authenticationManager.authenticate(requestAuthentication);

// Risk: the current context may share a reference with the session.
SecurityContextHolder.getContext().setAuthentication(verified);
~~~

`getContext()` returns the context **currently held by the holder**, which may be the object loaded from the session. `setAuthentication(...)` mutates that object in place.

A subtle side effect: when the session directly holds reference X in one JVM, mutating X also means the content referenced from the session changed **even without calling `saveContext`**. This is **not** a proper persistence mechanism: another session backend may serialize/deep-copy data and never see the mutation until save. Never design code relying on it "saving itself" like that.

### 4.2. Creating a New Context

~~~java
Authentication verified =
        authenticationManager.authenticate(requestAuthentication);

// Do not mutate the context loaded from the session.
SecurityContext fresh = SecurityContextHolder.createEmptyContext();
fresh.setAuthentication(verified);

// Replace only the current holder's context.
SecurityContextHolder.setContext(fresh);
~~~

Three key points:

1. `AuthenticationManager.authenticate(...)` must return a trusted result; never let an HTTP body self-grant `isAuthenticated=true` or choose its own authorities.
2. `createEmptyContext()` provides a different object from the currently held context.
3. `setContext(fresh)` replaces the current holder's reference; another request holding the old object does not have its state changed **directly**.

This isolates **replacing the SecurityContext container**. It does not by itself deep-separate the entire principal/Authentication, persist the session, or resolve ordering when two requests both save.

### 4.3. Creating New and Saving in Session-Based Custom Login

~~~java
Authentication verified =
        authenticationManager.authenticate(requestAuthentication);

SecurityContext fresh = SecurityContextHolder.createEmptyContext();
fresh.setAuthentication(verified);
SecurityContextHolder.setContext(fresh);

securityContextRepository.saveContext(fresh, request, response);
~~~

This is a **Servlet integration snippet**, requiring `AuthenticationManager`, `SecurityContextRepository`, `HttpServletRequest`, `HttpServletResponse`, and a complete flow in a Spring Security app. For custom login, you must also execute session fixation protection/`SessionAuthenticationStrategy`, CSRF, success/failure handlers, and related policies. Do not treat these lines as a complete production authentication endpoint.

## 5. Related Spring Security Servlet Mechanisms

Spring Security has several components to distinguish:

~~~text
HTTP Request
     |
     v
SecurityContextHolderFilter
     |
     v
SecurityContextRepository
     +--> RequestAttributeSecurityContextRepository
     +--> HttpSessionSecurityContextRepository
     |
     v
SecurityContextHolder (default ThreadLocal)
     |
     v
Request Authentication
     |
     v
Controller / Security annotations / Service
     |
     v
When changing Authentication: createEmptyContext -> setContext
     |
     v
When persistence is needed: SecurityContextRepository.saveContext(...)
     |
     v
Response, filter clears holder
~~~

- `SecurityContextHolderFilter` typically loads/defer-loads context into the holder and clears after the request.
- `SecurityContextRepository` defines the save/load mechanism; it is not `AuthenticationManager`.
- `HttpSessionSecurityContextRepository` uses server-side `HttpSession` to support authenticated state across HTTP requests.
- `RequestAttributeSecurityContextRepository` keeps context scoped to the same Servlet request/dispatch.
- `NullSecurityContextRepository` does not persist context to subsequent requests; fits stateless policies when configured accordingly.
- `DelegatingSecurityContextRepository` typically coordinates request attributes and HTTP sessions in Spring Security 6 Servlet.

**Origin of shared objects:** multiple requests belonging to the **same HTTP session** may load from the same server-side context. If threads A and B hold references to it, never mutate that object.

## 6. Spring Security 6 Explicit Save

### 6.1. Legacy Model: Implicit Save

In Spring Security 5 setups using `SecurityContextPersistenceFilter`, the framework could automatically track and implicitly persist context changes when the response completed. Consequently, legacy code calling only `SecurityContextHolder.setContext(...)` sometimes still took effect on the next request.

### 6.2. Spring Security 6 Model: Explicit Save

`SecurityContextHolderFilter` in default Spring Security 6 configurations **reads and clears**, but does not automatically save every change to the holder. When a custom login filter/controller decides to persist identity for the next request, it must perform:

~~~java
securityContextRepository.saveContext(
        newContext, httpServletRequest, httpServletResponse);
~~~

If you create a new context and forget to save, the current request may get an authenticated `Authentication`, yet the next request has no session context and returns 401.

**Important ordering:**

~~~text
authenticate -> session strategy -> createEmptyContext
             -> setAuthentication -> setContext
             -> saveContext -> redirect / commit response
~~~

Save before redirect/response commit because the repository may need to interact with the session and cookies while the response is still uncommitted.

**Do not** add both `SecurityContextPersistenceFilter` and `SecurityContextHolderFilter` to the same chain trying to get both implicit and explicit behavior. When upgrading the framework, use the proper migration strategy.

### 6.3. Standard Form Login Differs from Custom Login

If you use `http.formLogin(...)` with default filters, Spring Security already orchestrates the corresponding context/session lifecycle. Every controller **does not** need to save context manually.

The warnings in this lesson mainly target:

- Custom login controllers/filters.
- Step-up/reauth handling or controlled switch-user flows.
- Code building custom authentication flows.
- Code replacing `Authentication` within a request's scope.
- Tests interacting with the holder directly.

## 7. Runnable Java 17 Example: Proving Shared Reference Across Two Threads

This example uses **Spring Security Core 6.5.11** and `CountDownLatch`. It does **not** run a Servlet container, save a real session, or verify passwords. Two threads are intentionally given the same context to simulate the object-sharing aspect that can arise when one session serves multiple requests.

Part 1 reproduces how **not** to use `getContext().setAuthentication(...)`. Part 2 creates a new context and illustrates replacing the reference in a simulated store.

### 7.1. Structure

~~~text
security-context-copy-demo/
├── build.gradle
└── src/main/java/demo/ContextCopyDemo.java
~~~

**File `build.gradle`:**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'
    implementation 'org.springframework.security:spring-security-crypto:6.5.11'
}

application {
    mainClass = 'demo.ContextCopyDemo'
}
~~~

**File `src/main/java/demo/ContextCopyDemo.java`:**

~~~java
package demo;

import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

public final class ContextCopyDemo {

    private static Authentication trustedForDemo(String authority) {
        // Simulates verified auth only; NEVER use with client data.
        return UsernamePasswordAuthenticationToken.authenticated(
                "linh", null,
                List.of(new SimpleGrantedAuthority(authority)));
    }

    private static SecurityContext contextWith(String role) {
        SecurityContext result = SecurityContextHolder.createEmptyContext();
        result.setAuthentication(trustedForDemo(role));
        return result;
    }

    private static String role(SecurityContext context) {
        return context.getAuthentication().getAuthorities()
                .iterator().next().getAuthority();
    }

    private static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(ex);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        // 1. Two simulated requests holding the same context object.
        SecurityContext shared = contextWith("ROLE_USER");
        CountDownLatch bRead = new CountDownLatch(1);
        CountDownLatch aMutated = new CountDownLatch(1);
        AtomicReference<String> bBefore = new AtomicReference<>();
        AtomicReference<String> bAfter = new AtomicReference<>();

        Thread requestB = new Thread(() -> {
            SecurityContextHolder.setContext(shared);
            try {
                bBefore.set(role(SecurityContextHolder.getContext()));
                bRead.countDown();
                await(aMutated);
                bAfter.set(role(SecurityContextHolder.getContext()));
            } finally {
                SecurityContextHolder.clearContext();
            }
        }, "request-B");

        Thread requestA = new Thread(() -> {
            SecurityContextHolder.setContext(shared);
            try {
                await(bRead);
                // Wrong for production: directly mutates the object B holds.
                SecurityContextHolder.getContext()
                        .setAuthentication(trustedForDemo("ROLE_ADMIN"));
            } finally {
                aMutated.countDown();
                SecurityContextHolder.clearContext();
            }
        }, "request-A");

        requestB.start();
        requestA.start();
        requestB.join();
        requestA.join();

        System.out.println("unsafe.before=" + bBefore.get());
        System.out.println("unsafe.after=" + bAfter.get());

        // 2. SIMULATED session store, not a Servlet HttpSession.
        AtomicReference<SecurityContext> simulatedSession =
                new AtomicReference<>(contextWith("ROLE_USER"));

        SecurityContext aLoaded = simulatedSession.get();
        SecurityContext bLoaded = simulatedSession.get();
        SecurityContextHolder.setContext(aLoaded);

        SecurityContext newContext =
                SecurityContextHolder.createEmptyContext();
        newContext.setAuthentication(trustedForDemo("ROLE_EDITOR"));
        SecurityContextHolder.setContext(newContext);

        System.out.println("safe.isNewObject="
                + (newContext != bLoaded));
        System.out.println("safe.holder=" + role(SecurityContextHolder.getContext()));
        System.out.println("safe.otherBeforeSave=" + role(bLoaded));
        System.out.println("safe.storeBeforeSave="
                + role(simulatedSession.get()));

        // Only SIMULATES the repository replacing the stored context.
        simulatedSession.set(newContext);

        System.out.println("safe.storeAfterSave="
                + role(simulatedSession.get()));
        System.out.println("safe.otherAfterSave=" + role(bLoaded));

        SecurityContextHolder.clearContext();
        System.out.println("safe.holderEmpty="
                + (SecurityContextHolder.getContext()
                        .getAuthentication() == null));
    }
}
~~~

### 7.2. Run Command

Using JDK 17+ and compatible Gradle, from `security-context-copy-demo`:

~~~bash
gradle -q run
~~~

If using Gradle Wrapper: `./gradlew -q run`; Windows: `gradlew.bat -q run`. The first run may need to download dependencies.

**Stdout printed by the program itself** (excluding Gradle/library logs if enabled):

~~~text
unsafe.before=ROLE_USER
unsafe.after=ROLE_ADMIN
safe.isNewObject=true
safe.holder=ROLE_EDITOR
safe.otherBeforeSave=ROLE_USER
safe.storeBeforeSave=ROLE_USER
safe.storeAfterSave=ROLE_EDITOR
safe.otherAfterSave=ROLE_USER
safe.holderEmpty=true
~~~

### 7.3. Exact Output Explanation

- `unsafe.before=ROLE_USER`: request B reads the role first.
- `unsafe.after=ROLE_ADMIN`: thanks to `CountDownLatch`, B reads again after request A mutated **the shared object**. The result is deterministically reproducible, not because B changed its own ThreadLocal.
- `safe.isNewObject=true`: `createEmptyContext()` returns a different object from the context B holds.
- `safe.holder=ROLE_EDITOR`: the current thread's holder now points to the new object.
- `safe.otherBeforeSave=ROLE_USER` and `safe.storeBeforeSave=ROLE_USER`: the old context was not mutated.
- `simulatedSession.set(newContext)` **only simulates** `saveContext`; it does not issue a session cookie or act as a real Servlet repository.
- `safe.storeAfterSave=ROLE_EDITOR`: a new request reading the stored reference after replacement receives the new role.
- `safe.otherAfterSave=ROLE_USER`: B still holds the old snapshot, untouched internally by A.
- `safe.holderEmpty=true`: clearing the current holder does not mean clearing the session store.

**Do not conclude that creating a new context automatically revokes issued sessions.** The demo only tests object aliasing and replacement. Production requires integration tests with real SecurityFilterChain, SessionAuthenticationStrategy, repositories, and session backends.

## 8. The Same Session Can Suffer Two Different Races

### 8.1. Shared-Object Mutation

~~~text
Session S -> SecurityContext X
Request A -> X
Request B -> X
A: X.setAuthentication(AUTH_NEW)
B: observes AUTH_NEW unintentionally
~~~

Main fix: **new context** when replacing Authentication, instead of mutating X.

### 8.2. Last-Write-Wins Even When Both Requests Create New Objects

~~~text
Session S -> X
A creates YA from verified identity
B creates YB from verified identity
A saveContext(YA)
B saveContext(YB)
Session may end up storing YB
~~~

The same object is no longer mutated, yet **concurrent writes** remain. If B is based on an older snapshot, it can overwrite A's update. Additional fixes needed:

- Restrict where identity can be saved/replaced.
- Control session generation/versioning at sensitive operations.
- Use session invalidation/rotation on identity changes when policy demands.
- Check `authVersion`/account status against a trusted source for high-risk actions.
- With distributed session stores, inspect actual CAS/locking/serialization semantics.
- Test two concurrent requests on the same session and in-flight requests during logout/revocation.

**Creating a new context solves alias mutation; it does not automatically bring transaction isolation to every repository.**

## 9. Creating a New Context and Creating a New Authentication Are Two Different Things

The following snippet does not mutate the old context:

~~~java
SecurityContext prior = SecurityContextHolder.getContext();
SecurityContext next = SecurityContextHolder.createEmptyContext();
next.setAuthentication(prior.getAuthentication());
SecurityContextHolder.setContext(next);
~~~

Yet **`Authentication` may still be the exact same object** that both the old and new contexts point to. If the implementation/principal/details are mutable, mutating inside it can still affect the other side.

One way to separate responsibilities:

- **New container:** call `createEmptyContext()` to avoid dirtying a shared context.
- **New Authentication:** obtain the result from `AuthenticationManager`, a verified identity provider, or a trusted reauthentication/step-up flow.
- **Clean principal:** avoid putting large JPA entities or mutable cached `UserDetails` in by habit.
- **Trusted authorities:** always issued by a verified server/IdP, never copied raw from client JSON into an authenticated token.
- **Save in the right scope:** persist only when session policy requires.

**There is no universal deep-copy function for Authentication** that is safe for all subclasses. Reflection-based serialization/deep-copy can expose credentials, corrupt authorities, or break on Hibernate proxies.

## 10. Temporarily Using a Different Context in a Trusted Scope

Occasionally server code must run a short block with a different, **validly issued** `Authentication` (for example, a tightly controlled internal job system). Avoid mutating the prior context:

~~~java
// ILLUSTRATIVE CODE inside a trusted component, not standalone.
SecurityContext previous =
        securityContextHolderStrategy.getContext();

SecurityContext temporary =
        securityContextHolderStrategy.createEmptyContext();
temporary.setAuthentication(trustedAuthenticationForScope);

try {
    securityContextHolderStrategy.setContext(temporary);
    runAuthorizedScopedOperation();
} finally {
    securityContextHolderStrategy.setContext(previous);
}
~~~

This is a **temporary scope**. Do not call `saveContext(temporary, ...)` unless you genuinely intend to change the session identity for an explicitly authorized use case.

Never use this pattern for ad-hoc privilege escalation: `trustedAuthenticationForScope` must be issued by a trusted mechanism, and the operation must be authorized. With async/thread pools, `ThreadLocal` must be propagated/cleared by supported mechanisms; a `try/finally` block on the current thread does not automatically protect other worker threads.

## 11. Step-Up, Account Switching, and Re-Login

There are legitimate use cases for replacing Authentication:

| Use Case | When to Create a New Context? | What Else Is Needed? |
| --- | --- | --- |
| Initial form login | After AuthenticationManager/provider verifies | Session fixation, save to right repo, success/failure handlers |
| Reauthentication | When credentials are re-verified | Determine session and when privileges take effect |
| MFA / step-up | After stronger verification step | Limit step-up lifetime, auditing, and clear policy |
| Controlled switch-user | After actor is authorized | Remember real actor, audit, no tenant/scope mix-up |
| Logout | When clearing authenticated state | Logout handlers, invalidate/save empty context, and token policy |
| Stateless per-request token | When filter validates token | Do not persist session if session policy is STATELESS |

**Never create a new context on every request just to read the username.** Normal reading:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
~~~

is valid when combined with proper authenticated/anonymous checks and authorization. Creating a new context is for **operations that replace identity**, not a requirement for every controller/service reading the principal.

## 12. Logout: Clearing the Holder Is Insufficient, Mutating the Old Object Is Also Wrong

Mistake:

~~~java
SecurityContextHolder.getContext().setAuthentication(null);
~~~

If the context is shared with the session and other requests, this can mutate the shared object. At the same time, it does not guarantee the session was invalidated or that refresh tokens/JWTs expired.

For Spring Security Servlet, prefer `LogoutFilter` and `SecurityContextLogoutHandler`, because logout must also handle:

- The current holder.
- `SecurityContextRepository` / HTTP session.
- Session cookies, CSRF/remember-me, and configured logout integrations.
- Other sessions or tokens per dedicated policy.

A custom logout must understand **saving an empty context / invalidating the session** and response ordering, not just `clearContext`. `SecurityContextHolder.clearContext()` merely cleans the current slot; if the session still holds the old authentication, the next request can restore the identity again.

Stateless JWTs are a separate matter: deleting session context does not revoke signed tokens. TTL, denylist/version/introspection, or refresh token revocation is required per risk policy.

## 13. UserDetails, Caches, and Nested Mutable References

A new `SecurityContext` does not mean **every nested object is independent**:

~~~text
SecurityContext A -> Authentication A -> Principal U
SecurityContext B -> Authentication B -> Principal U
                                            |
                                      shared object
~~~

If `Principal U` is a mutable JPA entity or a cached `UserDetails`, changing its attributes/roles/password hash can affect multiple contexts.

Spring Security's `ProviderManager` also runs `eraseCredentials()` on the authentication result by default. If the principal shares the same `UserDetails` instance with a cache, erasing credentials on the result can wipe the hash in the cache.

Principles:

- Return small, dedicated `UserDetails`/principals for auth, not complex business domain entities.
- Avoid sharing mutable `Authentication`/principal objects across requests whenever possible.
- When caching, separate cached objects from principal objects and design credential erasure properly.
- Never use an unverified username/tenant from a request as a key to load a privileged principal.
- When data/roles change, use services/DB, live permission checks, and session invalidation per policy; never mutate `principal.getAuthorities()` in place expecting all requests to update.

## 14. Async, ThreadLocal, and Context Propagation

By default `SecurityContextHolder` uses `MODE_THREADLOCAL`. A task from `@Async`/`ExecutorService` running on another thread **does not automatically inherit** the calling thread's context. Spring Security provides `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextExecutor`, and other integrations.

When propagating:

- Distinguish **passing a reference to the context** from creating an independent snapshot.
- If a task receives the same mutable context and the origin thread mutates it, similar aliasing can occur.
- Use a fresh context/trusted snapshot or pass a stable userId and reauthorize inside the task depending on the use case.
- Ensure `clearContext()` runs after the task via a reliable wrapper/`finally` mechanism.
- Never use `MODE_GLOBAL` for multi-user web servers.
- `MODE_INHERITABLETHREADLOCAL` does not automatically handle reused thread pools properly.

**Never use a static `Authentication currentUser`** as JVM-wide shared user storage; it mixes identities across customers.

## 15. SessionCreationPolicy and Context Scope

| Policy / Repository | Can Keep Context to Next Request? | Related Note |
| --- | --- | --- |
| `HttpSessionSecurityContextRepository` | Yes if session remains valid and saved properly | May share object in same JVM; use fresh context when replacing auth |
| `RequestAttributeSecurityContextRepository` | Not across a completely new HTTP request | Used within the same Servlet request/dispatch |
| `NullSecurityContextRepository` | No | Stateless auth requires proof per request |
| `DelegatingSecurityContextRepository` | Depends on delegates | Typically combines request attribute and session |
| `SessionCreationPolicy.IF_REQUIRED` | Can create session when needed | Commonly used for web login |
| `SessionCreationPolicy.NEVER` | Not proactively created by Spring Security, yet can use an existing session | Do not confuse with stateless |
| `SessionCreationPolicy.STATELESS` | Does not use `HttpSession` as a security context source | Fits stateless bearer with matching config |

A session cookie can appear due to `RequestCache` or other application code; do not infer that only `SecurityContextRepository` creates sessions.

## 16. Stale Principals and Permissions Do Not Auto-Update

Creating a new context is a technique to avoid **shared-object mutation**. It **does not automatically guarantee**:

- A newly locked user is blocked across all active sessions.
- A role just revoked in the DB immediately disappears from JWTs/sessions.
- Requests already started before the permission change are aborted immediately.
- Two nodes sharing a session store observe the same snapshot instantaneously.
- Cached `UserDetails` objects and new principals reflect the exact same update timestamp.

For example, an admin revokes `ROLE_ADMIN`, yet an old session still has an `Authentication` with that authority. The repository can only reload the snapshot; it is not the source of the latest policy. Additional safeguards: account status revalidation, token/session revocation, `authVersion`, TTL, object-level authorization, and session generation checks as needed.

**Do not try to "update all requests" by mutating a shared SecurityContext object.** That attempts to fix stale roles by introducing another race hazard.

## 17. Why Is synchronizing on the Context Not a General Solution?

Some code attempts:

~~~java
synchronized (SecurityContextHolder.getContext()) {
    SecurityContextHolder.getContext().setAuthentication(newAuthentication);
}
~~~

This should not be treated as a default solution because:

- Other filters/controllers may read without acquiring the same lock.
- Distributed sessions may deserialize into distinct objects, giving each node a different lock.
- Locking does not prevent last-write/stale-read across two separate requests.
- It can cause contention/deadlocks if business code holds locks for long durations.
- It still mutates a shared object without improving data structure or ownership.

Instead of trying to synchronize everywhere using X, **create a new Y**, replace the reference in the proper scope, and persist intentionally. When consistency is critical, add session/DB version policies and concurrency control at the store level.

## 18. Integrating Multiple SecurityFilterChains

An application may have:

~~~text
/web/**   -> form login + HttpSession
/api/**   -> JWT bearer + stateless
/admin/** -> session + step-up/revalidation
~~~

This is an example design, not Spring Security's default matchers. Each chain must define:

- Which filter/`AuthenticationManager` actually verifies credentials.
- Which `SecurityContextRepository` the holder filter and auth filters use.
- Which `SessionCreationPolicy` and `RequestCache` are in effect.
- Whether custom login runs on the right chain.
- Whether session auth can accidentally be accepted by an API intended for bearer tokens only.
- When identity changes, whether the repository saves for the right scope instead of using a different instance.

**Creating a new context properly yet saving to a repository the filter does not use** causes subsequent requests to lose the identity. Test through actual URLs/filter chains, not only by calling a method directly in a unit test.

## 19. Debugging Real-World Failures

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Two tabs see principal/role change mid-request | Shared context mutated in place | Fresh context + setContext |
| Current login succeeds, next request returns 401 | Custom login did not save context | `SecurityContextRepository.saveContext` before redirect |
| Moving to Redis breaks "auto-save" | Previously relied on object aliasing in local session | Explicit save; test session backend |
| Request B overwrites A's session even though both created new contexts | Last-write-wins | Session generation/version/revalidation |
| `@Async` loses identity | ThreadLocal does not auto-propagate | DelegatingSecurityContext executor or userId boundary |
| Async task sees identity change | Passed shared mutable context/auth | Trusted snapshot and proper cleanup |
| Password hash in cache disappears | `eraseCredentials()` affected shared UserDetails object | Separate cached objects from principals |
| Logout calls `clearContext`, yet next request is still authenticated | Session repository still holds context | Logout support / invalidate / save empty |
| DB role removed, yet session still has ADMIN | Old Authentication snapshot | Revalidation/revocation/refresh per policy |
| "New context" yet principal still gets mutated | Same mutable `Authentication`/JPA entity shared | Separate nested objects / trusted authentication |
| Static context used across entire app | Cross-user contamination | Never use global mutable identity |
| Custom filter creates authenticated token from request | Authentication bypass | Authenticate through manager/provider |
| Switching global strategy mid-request | Context holder strategy race | Inject a consistent strategy |
| Saving after `sendRedirect` | Response already committed | Save before response commit |
| Using only request attribute while expecting login persistence | Repo does not survive across new requests | Use session repository if stateful |
| Stateless endpoint accepts old cookie/session auth | Wrong chain/session policy | `STATELESS` and proper token validation |

## 20. Deterministic Concurrency Testing

**Never** run a single login request and conclude there is no race. You should:

1. Seed a session with a valid authenticated context.
2. Issue two **concurrent** requests sharing the same session ID.
3. Place a test barrier/`CountDownLatch` so request B reads the context before A replaces Authentication.
4. Confirm that with the old approach B observes Authentication changing unexpectedly; after refactoring, B keeps its old snapshot for the in-flight request.
5. Once A saves the new context, verify a new request C sees the identity per policy.
6. When both requests save, test ordering and stale updates.
7. Test servlet session fixation, logout, redirects, session cookies, and distributed stores.
8. For `@Async`, test propagation/cleanup so identities never mix across tasks.
9. Check whether any shared mutable principal/authorities remain.
10. When a role is revoked, verify requests are blocked within the security SLO rather than inspecting context objects alone.

### Integration Testing via MockMvc

This is **pseudocode**, not standalone JUnit:

~~~java
// Test runs through real SecurityFilterChain with seeded user and config.
MvcResult login = mvc.perform(
        formLogin().user("linh").password("correct-password"))
        .andExpect(authenticated())
        .andReturn();

MockHttpSession session =
        (MockHttpSession) login.getRequest().getSession(false);

// Two requests use session and latches/barriers in a test service.
// Do not use Thread.sleep hoping to trigger a race by chance.
// Verify B's role is not mutated by A prior to an intentional
// reauthentication step or session update.
~~~

If the session was invalidated, do not keep passing the old object to new requests; simulate cookies and lifecycle accurately. MockMvc alone cannot verify distributed/multi-node stores; use integration tests against a real session backend.

## 21. Code Review Checklist

1. When replacing Authentication in custom Servlet logic, is **`createEmptyContext()`** used?
2. Is **`setContext(newContext)`** used instead of mutating the current holder object?
3. Is the new `Authentication` issued by a **trusted provider/manager**, not from client payload roles?
4. When a session is needed, is **`saveContext(newContext, request, response)`** called before commit?
5. Does custom login implement `SessionAuthenticationStrategy`/session fixation/CSRF/success handling properly?
6. Do the holder and repository share the same `SecurityContextHolderStrategy`/chain?
7. Are mutable `Authentication`/principals separated from cached objects or JPA entities?
8. Are two concurrent requests sharing **the same session** tested?
9. Is **last-write-wins** handled when two requests both save or when roles are revoked?
10. Is proper logout support used rather than mutating context to null?
11. Are authority freshness/account state and token/session revocation policies in place?
12. Is the holder cleaned up after custom filters/async tasks?
13. Is static/global authenticated user state avoided?
14. Are full `SecurityContext`, credentials, and cookies/tokens kept out of logs?
15. Are multiple chains, different session backends, and post-redirect requests tested?

## 22. Self-Check Questions

**Question 1.** Does `ThreadLocal` mean every request has its own separate `SecurityContext` object?  
**Answer:** No. ThreadLocal isolates the reference storage slot; two requests can hold the same object loaded from one session.

**Question 2.** Why is `getContext().setAuthentication(auth)` risky?  
**Answer:** It mutates the current object. If the object is shared, another request can see the principal/roles change mid-flight.

**Question 3.** What is the right pattern to replace Authentication?  
**Answer:** Authenticate through manager/provider → `createEmptyContext()` → `setAuthentication(verified)` → `setContext(newContext)`.

**Question 4.** In Spring Security 6, does custom login setting a new context automatically persist to the next request?  
**Answer:** Not by default with `SecurityContextHolderFilter`. `SecurityContextRepository.saveContext(...)` is required if session persistence is wanted.

**Question 5.** B holds X, while A calls `setContext(Y)` and saves Y. Does B automatically switch to Y?  
**Answer:** No. B can continue holding X during the in-flight request; subsequent requests may load Y.

**Question 6.** If a new context reuses `oldContext.getAuthentication()`, is it deeply independent?  
**Answer:** No. `Authentication` and its principal may still be shared.

**Question 7.** Why can't local `synchronized` around getContext cure the race?  
**Answer:** Other code paths/nodes do not share the same lock, and last-write-wins at the session store is not resolved.

**Question 8.** Is it acceptable to create an authenticated token with roles from an unverified JSON request?  
**Answer:** No. Never bypass `AuthenticationManager`/providers and authorization.

**Question 9.** After changing roles in the DB, can you call a context setter to update all running requests?  
**Answer:** No. Session/token revocation, refresh/revalidation, and dedicated consistency policies are required.

**Question 10.** What is the `CountDownLatch` demo simulating?  
**Answer:** Two ThreadLocals holding the same reference; A mutates the object and B sees the change. With a new context, only the current scope's reference changes.

**Question 11.** When is creating a new context unnecessary?  
**Answer:** When merely reading principal/authorities in a controller/service without replacing Authentication.

**Question 12.** Is calling only `SecurityContextHolder.clearContext()` enough for logout?  
**Answer:** No. The session repository, cookies, and tokens may still exist; use logout support and revocation policies.

## 23. References

- [Spring Security 6.5 – Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): recommendation to use `createEmptyContext` instead of `getContext().setAuthentication` to avoid races; `SecurityContextHolder` and `Authentication`.
- [Spring Security 6.5 – Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): holder strategies, session semantics, custom authentication, and explicit save.
- [Spring Security 6.5 – Persisting Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html): `SecurityContextRepository` implementations.
- [Spring Security 6.5 – Session Management Migration](https://docs.spring.io/spring-security/reference/6.5/migration/servlet/session-management.html): `SecurityContextPersistenceFilter` vs. `SecurityContextHolderFilter`, `requireExplicitSave`.
- [Spring Security 6.5 – SecurityContextHolder Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/context/SecurityContextHolder.html): `createEmptyContext`, `setContext`, `getContext`, `clearContext`.
- [Spring Security 6.5 – SecurityContextRepository Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/SecurityContextRepository.html): `saveContext` and persistence lifecycle.
- [Spring Security 6.5 – SecurityContextHolderStrategy Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/context/SecurityContextHolderStrategy.html): consistent strategy usage.
- [Spring Security 6.5 – Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): `SessionAuthenticationStrategy` and Servlet login flow.
- [Spring Security 6.5 – Concurrency Support](https://docs.spring.io/spring-security/reference/6.5/features/integrations/concurrency.html): propagating context across threads.
- [Spring Security 6.5 – Logout](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html): session cleanup and logout handlers.

**Remember:** `ThreadLocal` does not make an object private. When replacing identity in Servlet apps, use **`SecurityContextHolder.createEmptyContext()` → `setAuthentication(verified)` → `SecurityContextHolder.setContext(fresh)`**, then **`SecurityContextRepository.saveContext(...)`** if a session is needed. This prevents side effects from mutating a shared object; **concurrent session writes, mutable principals, and revocation still must be addressed separately**.

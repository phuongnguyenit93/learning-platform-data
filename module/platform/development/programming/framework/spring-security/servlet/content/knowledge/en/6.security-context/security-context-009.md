# Creating a New SecurityContext to Avoid Object Sharing Across Requests

## 1. The Problem to Solve

In Spring Security on the **Servlet stack**, the current execution flow's security info is typically accessed via `SecurityContextHolder`. The `SecurityContext` object holds the current `Authentication`: identity, authorities, and authentication status. When developers handle login manually, switch identities, or write custom filters, a very easy mistake is grabbing the existing context and mutating it directly:

~~~java
// Error-prone if the current context is shared via repository/session.
SecurityContextHolder.getContext().setAuthentication(authentication);
~~~

This syntax may run normally, yet it **mutates the contents of the existing context object**. In certain configurations—especially when `SecurityContext` is loaded from the same `HttpSession` across concurrent requests—multiple requests can receive **references to the exact same object**. Replacing `Authentication` directly on that object can cause another request to observe its identity/authorities changing mid-flight.

When you genuinely need to set a new `Authentication`, the safer pattern is:

~~~java
SecurityContext freshContext = SecurityContextHolder.createEmptyContext();
freshContext.setAuthentication(authenticated);
SecurityContextHolder.setContext(freshContext);
~~~

If this is a **login that must persist to the next request**, you must also save the context using the appropriate `SecurityContextRepository`. **Creating a new context** and **saving the context** are two distinct steps.

This lesson explains why that pattern reduces object-sharing risks, how to use it in Spring Security 6 / Spring Boot 3, what still needs handling at the session/async layers, and common pitfalls. The focus is **Servlet security context**, not WebFlux's `ReactiveSecurityContextHolder` model.

## 2. Distinguishing SecurityContextHolder, SecurityContext, and Authentication

| Component | Function | Note |
| --- | --- | --- |
| `SecurityContextHolder` | Exposes `getContext()`, `setContext()`, `clearContext()`, and the storage strategy for current code | Access mechanism for the context, not the user identity |
| `SecurityContextHolderStrategy` | Defines how the context binds to execution flow; default is typically `ThreadLocal` | Strategy does not guarantee the placed object is unshared |
| `SecurityContext` | Object holding `Authentication` | Can be mutable; requests may point to the same instance if supplied that way |
| `Authentication` | Represents principal, authorities, credentials, and authentication state | Can hold mutable data/objects; use only results from trusted verification |
| `SecurityContextRepository` | Loads/saves context between request and response per configured policy | May use request attributes, HTTP session, or another repository |
| `SecurityContextHolderFilter` | In Spring Security 6, sets up context lookup for the request and clears the holder afterwards | Never assume every `setContext` is automatically persisted permanently |

Example reading user info in a protected method:

~~~java
Authentication current =
    SecurityContextHolder.getContext().getAuthentication();

if (current != null) {
    String username = current.getName();
    // Read only appropriate info; do not infer sufficient data access permissions.
}
~~~

The snippet above is an **illustrative Java fragment**, not a standalone application. Some requests carry anonymous authentication; thus `getAuthentication() != null` is **not enough** to conclude a real user logged in. When writing endpoint protection rules, prefer `authenticated()`, `hasRole(...)`, `hasAuthority(...)`, and appropriate domain permission checks.

### ThreadLocal Does Not Mean Each Request Has a Distinct Context Object

By default on the Servlet stack, `SecurityContextHolder` uses a `ThreadLocal`-based strategy. That gives code on thread A and thread B **separate reference slots**, yet does not stop both slots from holding **a reference to the exact same object**.

~~~text
Thread handling request A           Thread handling request B
       |                                  |
A's ThreadLocal                    B's ThreadLocal
       |                                  |
       +----------- same reference -------+
                       |
                       v
                SecurityContext X
                       |
                       v
                Current Authentication
~~~

Suppose two requests in one login session obtain context X from a store returning the same reference, or application code passes the same object X to two threads. If request B executes `X.setAuthentication(bob)`, request A may also see `bob` when reading from X afterwards. That is **mutable object sharing**, not Spring Security "merging" two `ThreadLocal` slots into one.

Also avoid an extreme conclusion: **not every request defaults to sharing the exact same `SecurityContext`**. That depends on the repository, login session, load/save mechanics, and reference passing in the application. Distinguish **the possibility of bugs when an object is shared** from guaranteed behavior in every deployment.

## 3. Why Can Mutating the Old Context Directly Cause a Race Condition?

The code:

~~~java
SecurityContext context = SecurityContextHolder.getContext();
context.setAuthentication(newAuthentication);
~~~

does not create a new `SecurityContext`. It mutates the returned instance. If that instance is still in use by another request, you have altered data that another request may read concurrently.

Consequences can include:

1. **Identity shifts mid-processing:** request A starts with `alice`, yet sees `bob` on a later context read.
2. **Skewed permission checks:** one authorization branch or business check reads the old `Authentication` while another reads the new one.
3. **State leakage across same-session requests:** especially during re-login, account switching, privilege elevation, identity replacement, or manual context edits.
4. **Hard to reproduce:** timing-dependent across threads, so the bug may appear only under high concurrency.
5. **Easy to miss in basic code reviews:** seeing `ThreadLocal` creates a false sense of complete isolation, while the aliasing lies in **the stored object**, not the ThreadLocal variable.

A timeline example:

| Time | Request A | Request B |
| --- | --- | --- |
| T1 | Receives reference to context X; authentication is alice | Not yet running |
| T2 | Performing business validation | Also receives context X |
| T3 | Local reference unchanged | Calls `X.setAuthentication(bob)` |
| T4 | Reads `X.getAuthentication()` again and may see bob | Continues processing as bob |

This is a **conditional illustrative model**: the table assumes A and B already hold X. The goal is recognizing object-sharing bugs, not claiming Spring Security always produces this error on its own.

### Do Not "Fix" It by Synchronizing Every Request

Locking on the context can serialize requests in the same session, hurt scalability, and still fail to prevent one request from observing state intentionally written by another. Instead, on an **authentication change**, create **a new context** and place it in the current thread's holder; design session persistence policies separately as needed.

## 4. The Right Pattern: createEmptyContext → setAuthentication → setContext

Once credentials are verified via a trusted mechanism, use:

~~~java
Authentication authenticated = authenticationManager.authenticate(
    UsernamePasswordAuthenticationToken.unauthenticated(
        username, rawPassword
    )
);

// Important: fresh context, do not mutate existing context.
SecurityContext newContext = SecurityContextHolder.createEmptyContext();
newContext.setAuthentication(authenticated);
SecurityContextHolder.setContext(newContext);
~~~

This is an **integration snippet**; `authenticationManager`, `username`, and `rawPassword` must be declared/supplied by a real authentication flow. Spring Security type imports are required. It is **not a complete login endpoint**.

Meaning of each step:

- **`authenticationManager.authenticate(...)`:** verifies input via the appropriate `AuthenticationProvider`. Returns the result on success; typically throws `AuthenticationException` on failure. Never treat a client-supplied name as an authenticated `Authentication`.
- **`SecurityContextHolder.createEmptyContext()`:** creates a new context object via the active `SecurityContextHolderStrategy`, avoiding mutation of an instance loaded from repository/session.
- **`newContext.setAuthentication(authenticated)`:** places the verified authentication result into the new context.
- **`SecurityContextHolder.setContext(newContext)`:** replaces the **context reference** bound to the current execution flow with the new instance.
- **Save context if needed:** subsequent decision by `SecurityContextRepository`/authentication mechanism on whether the new identity must persist across HTTP requests.

This pattern aligns with Spring Security guidance when proactively replacing authentication: create a new context to prevent race conditions among threads sharing a `SecurityContext`.

### Why Not Use new SecurityContextImpl() Everywhere?

`new SecurityContextImpl()` can instantiate the default context directly. However, `SecurityContextHolder.createEmptyContext()` expresses intent better and respects the `SecurityContextHolderStrategy` chosen by the application. If the application changes strategies, code using the holder's factory stays compatible. The core point remains **a fresh instance**.

### Very Dangerous Anti-Pattern: Self-Granting Client Roles

~~~java
// DO NOT use in applications: client self-claims "admin" and is immediately trusted.
Authentication forged = new UsernamePasswordAuthenticationToken(
    "admin", null, List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
);
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(forged);
SecurityContextHolder.setContext(context);
~~~

This is an **anti-pattern example**. The three-argument constructor creates a token already marked authenticated; it is appropriate only for data already verified by the system or deliberate tests. Feeding a request-supplied username/role into this constructor creates an identity-spoofing vulnerability. **A fresh context does not make invalid credentials valid**; authentication must come from a trusted provider/manager.

## 5. Often-Forgotten Step: Saving SecurityContext After Login

**Calling only `SecurityContextHolder.setContext(newContext)`** generally makes the new context visible within the *current execution flow*. It **does not guarantee** the next request will recognize the user as logged in. To maintain authentication via session, let Spring Security's standard login flow manage it or save the context via the appropriate repository.

In Spring Security 6, common configurations use `SecurityContextHolderFilter` and require **explicit save**: if the application **performs authentication manually**, it must call `SecurityContextRepository.saveContext(...)` when persistence is desired. Never rely on merely setting the holder and assuming the framework writes the session for you.

Combined snippet when an application authenticates manually:

~~~java
Authentication authenticated = authenticationManager.authenticate(
    UsernamePasswordAuthenticationToken.unauthenticated(
        username, rawPassword
    )
);

SecurityContext newContext = SecurityContextHolder.createEmptyContext();
newContext.setAuthentication(authenticated);
SecurityContextHolder.setContext(newContext);

// Only when keeping authentication across requests via the configured repository.
securityContextRepository.saveContext(newContext, request, response);
~~~

Variables `securityContextRepository`, `request` (`HttpServletRequest`), and `response` (`HttpServletResponse`) must exist in the Servlet flow. This is an **integration fragment inside a custom authentication flow**, not permission to skip session fixation, CSRF, remember-me, failure handlers, or success handlers. When using `formLogin()` or standard Spring Security mechanisms, prefer letting built-in filters/handlers run the full flow rather than rewriting it by hand.

### Where Can SecurityContextRepository Store Data?

| Repository or source | What it is used for | Consequences to understand |
| --- | --- | --- |
| `RequestAttributeSecurityContextRepository` | Keeps context in a request attribute, useful across certain dispatcher types | Does not create a login session surviving across new HTTP requests |
| `HttpSessionSecurityContextRepository` | Stores context in HTTP session when conditions allow | Same-session requests can read shared state; avoid mutating shared context directly |
| `DelegatingSecurityContextRepository` | Combines multiple repositories per configuration | Understand which delegate reads/saves context and when |
| `NullSecurityContextRepository` | Does not persist authentication across requests | Suitable for certain stateless models; new requests must re-authenticate |

Spring Security 6 may configure `DelegatingSecurityContextRepository` with request-attribute and HTTP-session repositories in typical setups. Actual defaults still depend on the filter chain and framework version. Do not guess the active repository solely from `spring-boot-starter-security` being on the classpath.

### Fresh Context Does Not Mean Fresh Session

Creating a new `SecurityContext` creates a **new Java object**; it does not create a new `HttpSession` or rotate the session ID. Session fixation protection (e.g., rotating the session ID after login) is a **separate** mechanism. When building custom login, account for context persistence, session fixation, CSRF, login errors, and proper logout.

### What Happens When Two Concurrent Requests Modify the Same Session?

Two concurrent requests can create **two distinct contexts**, both calling `saveContext`, resulting in the last write winning in the session. That avoids mutating **a single actively-used instance**, though it does not automatically solve logical conflicts over "which request should win last for session state". Applications supporting account switching, privilege elevation, or multi-device login need explicit session rules and business-level synchronization.

## 6. Runnable Java 17+ Code: Simulating Sharing Bugs and Creating Isolated Contexts

To observe clearly the difference between **two threads with separate ThreadLocals pointing to the same object** and **each thread using a fresh context**, the example below uses `spring-security-core` and standard Java concurrency. It does **not** start an HTTP server or verify real credentials; simulated tokens serve strictly to verify identity in a controlled simulation.

### Project Structure

~~~text
security-context-isolation/
├── pom.xml
└── src/main/java/demo/ContextIsolationDemo.java
~~~

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>security-context-isolation</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-core</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Boot parent here only manages dependency versions and compiler settings; the demo runs as a **Java `main` program** without creating a web application. Because there is no real Servlet request, the code deliberately puts contexts into threads to simulate references supplied from a session or application code.

**`src/main/java/demo/ContextIsolationDemo.java`**

~~~java
package demo;

import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

public class ContextIsolationDemo {

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            sharedObjectCase(executor);
            independentObjectsCase(executor);
        } finally {
            executor.shutdownNow();
        }
    }

    // Simulation only; DO NOT use authenticated constructor
    // with principals/roles not verified by AuthenticationManager.
    private static Authentication testOnlyAuthentication(String name) {
        return new UsernamePasswordAuthenticationToken(
            name,
            null,
            List.of(new SimpleGrantedAuthority("ROLE_USER"))
        );
    }

    private static void sharedObjectCase(ExecutorService executor)
            throws Exception {

        // Both tasks will receive the SAME SecurityContext reference.
        SecurityContext shared = SecurityContextHolder.createEmptyContext();
        shared.setAuthentication(testOnlyAuthentication("alice"));

        CountDownLatch firstBound = new CountDownLatch(1);
        CountDownLatch secondChanged = new CountDownLatch(1);

        Future<String> requestA = executor.submit(() -> {
            SecurityContextHolder.setContext(shared);
            try {
                firstBound.countDown();
                if (!secondChanged.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Request B timed out");
                }
                return SecurityContextHolder.getContext()
                    .getAuthentication().getName();
            } finally {
                SecurityContextHolder.clearContext();
            }
        });

        Future<String> requestB = executor.submit(() -> {
            if (!firstBound.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Request A timed out");
            }
            SecurityContextHolder.setContext(shared);
            try {
                // Mutate in-place the object that request A is also using.
                SecurityContextHolder.getContext().setAuthentication(
                    testOnlyAuthentication("bob")
                );
                secondChanged.countDown();
                return SecurityContextHolder.getContext()
                    .getAuthentication().getName();
            } finally {
                SecurityContextHolder.clearContext();
            }
        });

        String b = requestB.get();
        String a = requestA.get();
        System.out.println("Shared - request A sees: " + a);
        System.out.println("Shared - request B sees: " + b);
    }

    private static void independentObjectsCase(ExecutorService executor)
            throws Exception {

        CountDownLatch bothReady = new CountDownLatch(2);

        Future<String> requestA = executor.submit(() -> {
            SecurityContext fresh = SecurityContextHolder.createEmptyContext();
            fresh.setAuthentication(testOnlyAuthentication("alice"));
            SecurityContextHolder.setContext(fresh);
            try {
                bothReady.countDown();
                if (!bothReady.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Request B timed out");
                }
                return SecurityContextHolder.getContext()
                    .getAuthentication().getName();
            } finally {
                SecurityContextHolder.clearContext();
            }
        });

        Future<String> requestB = executor.submit(() -> {
            SecurityContext fresh = SecurityContextHolder.createEmptyContext();
            fresh.setAuthentication(testOnlyAuthentication("bob"));
            SecurityContextHolder.setContext(fresh);
            try {
                bothReady.countDown();
                if (!bothReady.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Request A timed out");
                }
                return SecurityContextHolder.getContext()
                    .getAuthentication().getName();
            } finally {
                SecurityContextHolder.clearContext();
            }
        });

        System.out.println("Independent - request A sees: " + requestA.get());
        System.out.println("Independent - request B sees: " + requestB.get());
    }
}
~~~

### Running the Program

Requires JDK 17+, Maven, and network access for initial dependency download. From the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ContextIsolationDemo
~~~

**Exact expected output** from this code:

~~~text
Shared - request A sees: bob
Shared - request B sees: bob
Independent - request A sees: alice
Independent - request B sees: bob
~~~

Explanation of each case:

- **Shared:** request A puts `shared` into its own `ThreadLocal`; request B puts **that exact same reference** and mutates `Authentication` to `bob`. The latch forces B to mutate before A reads again, so A sees `bob` even though A never called `setAuthentication(bob)`.
- **Independent:** each request calls `createEmptyContext()` and builds its own authentication. The two threads hold distinct context instances; A continues seeing `alice`, and B sees `bob`.
- **`clearContext()` in `finally`:** since this is a self-managed thread pool, the holder must be cleared on completion so reused threads do not carry stale state.

This is a **simulation illustrating races from object aliasing**, not a claim that every session repository always shares the same context. The code uses latches to fix observation order so stdout does not depend on which request the scheduler runs first (barring timeouts or system failures). Test tokens were constructed in the authenticated state **for simulation only**; never do this with unverified HTTP data.

## 7. Applying the Principle in Real Servlet Applications

In a Servlet application, you normally **do not write context-assignment code in every controller**. Spring Security's `SecurityFilterChain` and standard authentication filters already manage the security context via their built-in mechanics. Proactively creating a fresh context is most useful when you **build a custom authentication flow**, such as a custom authentication filter or a specialized login endpoint.

Responsibility-accurate pseudo-flow:

~~~text
HTTP POST login
  -> Spring Security / custom authentication component receives credentials
  -> AuthenticationManager verifies info
  -> Receives authenticated Authentication from provider
  -> Creates a NEW SecurityContext
  -> Attaches Authentication to the new context
  -> SecurityContextHolder.setContext(new context)
  -> Handles session fixation protection / success / failure per flow
  -> SecurityContextRepository.saveContext if login needs session
  -> Returns response
  -> Spring Security clears request's holder
~~~

Core code to place after successful verification:

~~~java
Authentication result = authenticationManager.authenticate(
    UsernamePasswordAuthenticationToken.unauthenticated(
        username, rawPassword
    )
);

SecurityContext fresh = SecurityContextHolder.createEmptyContext();
fresh.setAuthentication(result);
SecurityContextHolder.setContext(fresh);

// For manual session login, use the configured repository:
securityContextRepository.saveContext(fresh, request, response);
~~~

In this snippet, `username` and `rawPassword` are login input data that must be verified, never used to self-construct an authenticated token. Variables `authenticationManager`, `securityContextRepository`, `request`, and `response` must exist in the Servlet integration class. This is **not a standalone endpoint example**, and does not cover CSRF, session fixation, error handling, rate limiting, or remember-me. Production systems should use standard filters and login flows unless truly specific integration requirements exist.

**Distinguish two important cases:**

1. **Only observing the current user:** read `Authentication` from a controller/service or an appropriate method argument. No need to create a new context.
2. **Replacing the current Authentication:** use a result from a trusted source, **create a new context**, put it in the holder, and save it per policy if cross-request persistence is needed.

Do not overwrite authentication on the old context just to "switch roles" during a request. If business logic supports impersonation/privilege elevation, design dedicated auditing, scope, expiration, initiation permissions, and rollback; a fresh context solves only part of the object-sharing problem.

## 8. Async, Thread Pools, and Context Propagation

`SecurityContextHolder` defaults to binding the context to the thread. When you spawn a `Thread`, use `ExecutorService`, or invoke `@Async`, code on the new thread **does not automatically** see the original request's authentication. Meanwhile, a thread pool can reuse worker threads across multiple tasks.

Opposing risks:

- **Not propagating context:** background tasks lose identity, causing authorization failures or running as anonymous.
- **Passing the exact same instance and mutating it:** two tasks share a mutable `SecurityContext` and trigger races like the section 6 example.
- **Not clearing context on worker threads:** the previous task's identity data lingers when the thread is reused.

Spring Security provides wrappers such as `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextCallable`, and `DelegatingSecurityContextExecutor` to install context during execution and clean it up afterwards. Even when using them, understand **which context is passed**: wrappers do not turn a shared mutable object into an immutable one. Avoid mutating a context passed to multiple tasks, and consider snapshotting/copying required attributes per business policy.

Do not treat `MODE_INHERITABLETHREADLOCAL` as a default solution for thread pools. Inheritable `ThreadLocal` copies at thread creation time, whereas pools continually reuse threads; this can create wrong expectations about identity and lifetime. Choose Spring Security's supported propagation mechanisms, bound scopes, and clean up properly.

For Servlet requests with async dispatches, error dispatches, or forwards, `SecurityContextRepository` and filters affect how context is preserved across dispatches. When debugging, inspect the **dispatcher type**, filter chain, and actual context storage mechanism. Never assume every dispatch is a fresh request or that every dispatch safely receives the same reference.

## 9. Does a Fresh Context Solve Every Concurrency Issue?

**No.** It solves **avoiding direct mutation of a potentially shared context instance**. Other sources of conflict still exist:

- **Shared Authentication object:** even with two separate `SecurityContext` instances, if both hold the same mutable `Authentication` instance (or a principal with mutable fields), mutating inner objects can still race. Prefer immutable snapshots/controlled principal data; never mutate authorities on a shared object.
- **Shared HttpSession:** other attributes in the session remain mutable and concurrently accessible. Creating a fresh security context does not automatically synchronize all session data.
- **Two concurrent requests logging in again or logging out:** they can contend for saving context to the session/repository; define session policies, revocation, and update ordering.
- **Permission changes in database:** the context may hold authorities granted at authentication time. When permissions change, the application may need refresh/re-authentication or service-layer policies, not merely creating fresh contexts arbitrarily.
- **Cross-request caching:** never store the active `SecurityContext` or `Authentication` in singleton fields, static mutable fields, global shared caches, or thread pools without explicit scope design.
- **Session fixation and CSRF:** a fresh context does not automatically rotate the session ID, protect against CSRF, or bind tokens to the right user.
- **Method security and data permissions:** a context holding the right identity does not automatically mean the user can view every order/tenant. Enforce proper authorization at HTTP and business layers.

A helpful rule: **store shareable, immutable info whenever possible; when replacing `Authentication`, create a new `SecurityContext` instead of mutating the old one; where true shared state exists, design synchronization and lifecycle explicitly for that state.**

## 10. Diagnostics and Testing in Real Applications

### Symptoms to Investigate

- Two concurrent requests in the same HTTP session run, and one sees its identity/authorities change unexpectedly.
- A login or switch-user endpoint calls `setAuthentication` on the old context; the bug appears only when multiple tabs act simultaneously.
- After custom login succeeds, the next request is anonymous because the context was set only in the holder without saving via the proper repository.
- `@Async` tasks fail to see the principal, or see a previous task's principal because a thread pool lacked cleanup.
- Endpoints return 401/403 inconsistently with session state; logs reveal a different context repository or filter sequence than expected.

### Inspection Procedure

1. **Locate code changing authentication:** search for `SecurityContextHolder.getContext().setAuthentication(...)`, `setContext(...)`, `saveContext(...)`, and custom authentication filters. Read-only sites do not need changing.
2. **Identify actual repository/strategy:** inspect `SecurityContextRepository`, session policy, filter chain, and `SecurityContextHolderStrategy`. Avoid guessing from dependencies alone.
3. **Verify object identity:** in tests, check `contextA == contextB` and test what happens when one task replaces authentication; do not check only `getName()` at the start.
4. **Test two concurrent requests in the same session:** coordinate timing with `CountDownLatch`/barriers to reproduce races, rather than relying on flaky `Thread.sleep(...)`.
5. **Test persistence:** after custom login, send a new request using the same session cookie and verify authentication remains as designed; if stateless, verify token re-authentication.
6. **Test cleanup and propagation:** when a request ends or a task returns to a pool, the context must be cleared via the right mechanism. Keep tokens/passwords out of debug logs.
7. **Test business permissions:** two distinct principals must never access each other's resources simply via a guessable record ID.

In development, you can enable:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Logs help observe security filter steps, authentication, authorization, and some context decisions per version. Use `TRACE` in a controlled manner only when more detail is needed; do not enable it in production where secrets risk exposure. Never print full session IDs, credentials, or bearer tokens in debug reports.

### Minimum Test Matrix to Confirm Proper Handling

| Scenario | Expectation |
| --- | --- |
| Two tasks hold the same context instance and one mutates authentication | Test reproduces the other task observing the mutation (bug simulation) |
| Two tasks call `createEmptyContext()` independently with separate auth | No cross-reading of identities |
| Custom login needs session, calls only `setContext` without saving | Must not be expected to persist to the next request |
| Custom login creates a fresh context and calls `saveContext` appropriately | Next request with same session receives verified info per policy |
| Background task finishes | Holder is cleared; thread reuse carries no stale context |
| Same session mutates state concurrently | Additional session conflict policy needed beyond separating context objects |

## 11. Common Mistakes

**Mistake 1 — "ThreadLocal completely guarantees context cannot be shared."** ThreadLocal isolates **reference slots**, not the object both slots point to. Check object identity and repositories.

**Mistake 2 — "`getContext().setAuthentication(...)` is always wrong."** It is a valid API, yet **dangerous when the context might be shared**. When proactively changing authentication, prefer `createEmptyContext` then `setContext` to get an isolated instance and avoid races.

**Mistake 3 — "Calling `createEmptyContext()` alone logs the user in."** A new context starts empty with no `Authentication`. You must use an authentication result from a trusted provider/manager, never self-assigning roles from input.

**Mistake 4 — "`setContext()` means the session is saved."** Updating the holder affects the current execution flow. In explicit-save flows, `SecurityContextRepository.saveContext(...)` is required to persist login; session policies may prevent persistence.

**Mistake 5 — "A new context creates a new session."** Two independent mechanisms; creating a new Java object does not rotate the session ID or provide session fixation protection.

**Mistake 6 — "A new context deep-clones `Authentication`."** `setAuthentication(authenticated)` only stores a reference to the passed `Authentication`. Avoid sharing/mutating mutable authentication or principal objects without policy.

**Mistake 7 — "The main request has a context, so every `@Async` task sees it automatically."** New threads/pools do not inherit context reliably by default. Use controlled propagation and cleanup.

**Mistake 8 — "Using InheritableThreadLocal for pools solves everything."** Reused worker threads can retain stale data. Scoped propagation mechanisms and `finally` cleanup are safer.

**Mistake 9 — "Spring Security always shares one context across all requests."** Incorrect; the backing store and configuration determine which reference is returned. Even so, avoiding mutation of the old context remains good defensive practice when changing authentication.

**Mistake 10 — "Separate contexts remove the need for business authorization."** The context states identity and represented authorities; you must still verify who can access specific resources/tenants.

## 12. Self-Check Comprehension

**Question 1:** Why can two threads using separate `ThreadLocal` slots still see the principal change concurrently?

**Answer:** Both `ThreadLocal` slots can hold references to the exact same mutable `SecurityContext`, e.g., from a shared session/repository or application code passing that object around.

**Question 2:** When custom authentication succeeds, what is the three-step sequence to avoid mutating the old context?

**Answer:** `SecurityContextHolder.createEmptyContext()` → `newContext.setAuthentication(authenticated)` → `SecurityContextHolder.setContext(newContext)`.

**Question 3:** Why is `SecurityContextHolder.setContext(newContext)` insufficient for session-based login?

**Answer:** It only sets the context for the current execution flow. When explicit save is required, you must call `SecurityContextRepository.saveContext(newContext, request, response)` and complete a full, secure login workflow.

**Question 4:** Does creating a new `SecurityContext` automatically copy or freeze the attached `Authentication`?

**Answer:** No. `setAuthentication` stores a reference. If the same mutable object is placed into multiple contexts, races can still occur on that inner object.

**Question 5:** Should every controller call `clearContext()` after reading user info?

**Answer:** No. The standard security filter chain manages request lifecycle. `clearContext()` is needed when code manually manages threads/tasks outside the filter lifecycle, usually inside `finally`.

**Question 6:** If two concurrent requests save two distinct new contexts into the same `HttpSession`, are all race conditions eliminated?

**Answer:** Not yet. Distinct objects avoid mutating a shared instance, but logical conflicts over session state and write order can still arise. Proper session policies are still needed.

**Key takeaway:** **`SecurityContextHolder` manages where the context reference is bound; `SecurityContext` is a potentially mutable object. When replacing `Authentication`, create a new `SecurityContext`, place it in the holder, and save via the repository when needed. Never mistake `ThreadLocal` for a guarantee against shared objects, or a fresh context for a fresh session.**
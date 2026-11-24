# Clearing SecurityContext After Requests and Preventing Cross-Thread Identity Leakage

In a **Spring Security application using Servlet**, each HTTP request can carry a different identity and set of permissions. Servlet containers typically reuse threads from a pool; if user A's information remains on a thread after request A completes, a subsequent request from user B or a background task risks reading A's identity by mistake. This is **security context leakage**, which can lead to wrong audit logs, incorrect permission checks, or unauthorized data access.

Spring Security implements a **set up context during request processing and clear context at completion** lifecycle to prevent this bug. This lesson explains exactly which object must be cleared, which component is responsible, why `ThreadLocal` can cause leaks, how to handle asynchronous tasks, and how to test it. Framework examples below follow **Spring Security 6.x Servlet / Spring Boot 3.x / Java 17+**; for other versions, check the exact mechanism and APIs.

## 1. What Does Clearing SecurityContext Mean?

Relationship of the three fundamental components:

~~~text
SecurityContextHolder
    |
    | getContext()
    v
SecurityContext (context bound to current execution)
    |
    | getAuthentication()
    v
Authentication
    |-- principal   : identified subject
    |-- authorities : permissions/roles/scopes
    |-- credentials : authentication evidence (if still present)
    |-- authenticated : state of the authentication token
~~~

- `SecurityContextHolder` is the access point to the context via a `SecurityContextHolderStrategy`. In traditional Servlet apps, the default strategy is `MODE_THREADLOCAL`: the context is bound to the current thread.
- `SecurityContext` is the object holding `Authentication`. It can be mutable; it should not be shared arbitrarily across requests or threads.
- `Authentication` holds principal, authorities, and authentication status. A context may be empty or hold an anonymous authentication; not every request has a logged-in user.

The primary call to clear the **context bound to the currently executing thread** is:

~~~java
import org.springframework.security.core.context.SecurityContextHolder;

SecurityContextHolder.clearContext();
~~~

Under the default strategy, this removes the context reference from the current thread's storage. It is **not** a complete logout operation, does not destroy the HTTP session, does not delete persisted security contexts in repositories, and does not revoke issued access tokens.

**Important boundary:** Normal applications should let Spring Security's security filters manage per-request context cleanup. Code calling `clearContext()` mid-request can erase authentication before authorization or downstream business logic executes. Manual cleanup in `finally` is mainly needed when code **sets the context manually outside the standard filter lifecycle** or establishes an independent execution boundary responsible for context management.

## 2. Why Do Thread Pools Spread Leaks Across Requests?

A Servlet container can serve thousands of requests over time using a small pool of worker threads. Illustration:

~~~text
Time t1: worker-thread-7 handles Alice's GET /account
                 SecurityContextHolder -> Authentication(Alice)
                                  |
                             request finishes

Time t2: worker-thread-7 is reused for Bob's GET /account
                 (if Alice's context was not cleared)
                 SecurityContextHolder -> Authentication(Alice)  [WRONG]

Correct:
   request Alice  -> set/load Alice context -> process -> clear
   request Bob    -> set/load Bob context   -> process -> clear
~~~

`ThreadLocal` isolates data **per thread**, **not per HTTP request**. When a thread is reused, a `ThreadLocal` value survives into the next execution unless code or the framework actively removes or overwrites it. That is why cleanup must sit at the request-processing boundary and typically in a `finally` block: whether a request succeeds, throws an exception, or is rejected early, cleanup must still run.

This bug may appear only intermittently in production because thread scheduling history determines which subsequent request reuses the same worker. A few sequential tests running on fresh threads can easily miss the issue.

### Consequences of Context Leakage

| Symptom | Possible cause | Consequence |
| --- | --- | --- |
| Controller calls `getAuthentication().getName()` and gets previous request's user | Stale context left on worker thread | Displays wrong data, attributes audit to wrong user |
| Custom authorization uses principal from stale holder | Set context manually without cleanup | Wrong permission decisions |
| Executor task sees previous task's user | Worker thread reused `ThreadLocal` | Task may run under wrong identity |
| After logout, a custom thread keeps old principal | Session destroyed, yet stale context retained on another thread | Logs or background logic still treat user as present |
| Isolated tests PASS, production fails sporadically | Pool reuse and scheduling differ from test environment | Hard to reproduce, security-sensitive risk |

Not every unexpected identity stems from `ThreadLocal`: unchanged sessions/cookies, still-valid tokens, business caches, custom thread context propagation, or authentication policies can also be responsible. Pinpoint the exact source of the context and where it was attached.

## 3. Which Spring Security Component Sets Up and Clears the Context?

In Servlet architecture, a request typically traverses:

~~~text
HTTP request
   |
   v
Servlet container filter chain
   |
   v
DelegatingFilterProxy ("springSecurityFilterChain")
   |
   v
FilterChainProxy -> selects first matching SecurityFilterChain
   |
   v
SecurityContextHolderFilter (common Spring Security 6.x config)
   |-- loads/defers context from SecurityContextRepository
   |-- makes context available via SecurityContextHolderStrategy
   |-- invokes chain.doFilter(...)
   |-- finally: clears SecurityContextHolder
   |
   v
Authentication filters -> AuthorizationFilter -> Controller
~~~

The diagram shows responsibilities and a typical order; the exact filter list/order depends on configuration and version. At runtime, `SecurityContextHolderFilter` wraps downstream filters and **clears the context from the holder in a `finally` block** when leaving its execution scope. If a controller throws an exception, cleanup still runs as the stack unwinds to the filter, provided execution runs through the normal filter lifecycle.

### SecurityContextHolderFilter vs. SecurityContextPersistenceFilter

This often causes confusion when reading docs from different Spring Security versions:

| Filter | Role | Persisting context across requests |
| --- | --- | --- |
| `SecurityContextHolderFilter` | Loads or prepares deferred loading from repository, binds to holder, and clears on completion | **Explicit save** design: the filter itself does not auto-save all context changes |
| `SecurityContextPersistenceFilter` | Legacy mechanism to load and save context per its contract while managing the holder | Historically auto-saved context after request processing in matching setups |

In Spring Security 6, many configurations use `SecurityContextHolderFilter` and require appropriate authentication mechanisms to **explicitly call `SecurityContextRepository.saveContext(...)`** if the context must survive to the next request. Standard authentication filters already handle this internally. If writing custom login, understand this contract and do not assume calling `SecurityContextHolder.setContext(...)` wrote to the session.

**Two separate operations:**

1. **Cleanup:** `SecurityContextHolder.clearContext()` prevents the current request's context from lingering in thread storage.
2. **Persistence:** `SecurityContextRepository.saveContext(context, request, response)` saves an authenticated context so other requests can reload it **if the login model and repository allow**.

You can save the context to the session for the next request **while still clearing the current thread's holder**. Clearing the holder at request end is right for both session-based apps and stateless APIs.

### What If No SecurityFilterChain Is Selected?

`FilterChainProxy` applies the filters of the **first matching `SecurityFilterChain`**. If a request falls outside all chains, the context-managing filter of those chains will not run for that request. If a custom Servlet filter outside Spring Security sets the holder manually, that code bears sole responsibility for clearing the context. Do not configure `securityMatcher("/api/**")` covering only APIs and assume other endpoints are still protected by those filters.

## 4. Simulating Leakage and Fix in Plain Java 17

This is a **standalone Java 17 program run via `javac`/`java`**, using standard JDK `ThreadLocal` to simulate the default `SecurityContextHolder` storage scope. It deliberately creates a buggy case and then cleans up properly to illustrate the exact root cause. This is **not a Spring Security implementation**; do not use it as a real authentication mechanism.

Save the file with exact name `ThreadPoolIdentityLeakDemo.java`:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ThreadPoolIdentityLeakDemo {
    private static final ThreadLocal<String> CURRENT_USER = new ThreadLocal<>();

    private static String who() {
        String user = CURRENT_USER.get();
        return user == null ? "<none>" : user;
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Future<String> alice = pool.submit(() -> {
                CURRENT_USER.set("alice");
                // INTENTIONALLY OMIT remove() to illustrate the bug.
                return "task A: " + who();
            });
            System.out.println(alice.get());

            Future<String> next = pool.submit(() -> "task B: " + who());
            System.out.println(next.get());

            Future<String> reset = pool.submit(() -> {
                CURRENT_USER.remove();
                return "cleanup: " + who();
            });
            System.out.println(reset.get());

            Future<String> carol = pool.submit(() -> {
                CURRENT_USER.set("carol");
                try {
                    return "task C: " + who();
                } finally {
                    CURRENT_USER.remove();
                }
            });
            System.out.println(carol.get());

            Future<String> after = pool.submit(() -> "task D: " + who());
            System.out.println(after.get());
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Run with JDK 17+:

~~~bash
javac ThreadPoolIdentityLeakDemo.java
java ThreadPoolIdentityLeakDemo
~~~

Exact stdout:

~~~text
task A: alice
task B: alice
cleanup: <none>
task C: carol
task D: <none>
~~~

**Step-by-step explanation:**

1. The pool has only **one worker thread**, so task A and task B reuse the exact same thread.
2. Task A sets `alice` and omits `remove()`, so task B (with no identity of its own) still sees `alice`. This bug is intentional in the example.
3. The reset task clears the stale value. Task C sets `carol` inside a `try/finally` boundary and always removes it on exit.
4. Task D reads `<none>`, proving proper cleanup prevents the worker from retaining task C's identity.

The program uses `Future.get()` to await each task sequentially, producing deterministic output order. With multi-thread pools, bugs depend on which thread gets reused; a single-thread pool makes the root cause clear without scheduling guesswork.

**General rule:** Any code region that **sets thread-bound state itself** and owns that state's lifecycle must clean up in `finally`, even when exceptions occur. However, within a request already managed by Spring Security, avoid clearing the holder manually mid-request because the framework handles its boundary.

## 5. Cleanup on Success, Failure, and Early Response Termination

It is not only HTTP `200` flows that need cleanup. Multiple exit paths must be considered:

- **Controller succeeds:** After the filter chain finishes, the holder is cleared so the thread can serve another request.
- **Authentication/authorization fails:** A filter may return `401`, `403`, or redirect `302`; cleanup still runs as the stack returns to the context-managing filter.
- **Exception in controller:** When an exception propagates out to filters or is handled by MVC before completing, the holder-managing filter still finishes its scope cleanup.
- **Filter short-circuits the chain:** If a request entered the context-managing filter and a downstream filter skips `chain.doFilter(...)`, the managing filter's `finally` still runs.
- **Client disconnects / I/O error:** Properly structured `try/finally` ensures cleanup as control flow unwinds, even if the response never finishes cleanly.

In Servlet async or error dispatches, which filters run again and which thread continues depend on dispatcher types, filter registration config, and Spring Security integrations. Never assume the entire asynchronous lifecycle executes on one thread or finishes as soon as the controller method returns.

### Why Not Call clearContext in Every Controller?

Wrong example:

~~~java
// Wrong illustrative code: DO NOT use as a pattern.
public String account() {
    String user = SecurityContextHolder.getContext()
            .getAuthentication().getName();

    SecurityContextHolder.clearContext(); // cleared too early

    return service.loadAccount(user); // downstream code may need context
}
~~~

If `service.loadAccount(...)` has method security, audit logic, or code reading the holder, premature clearing causes missing authentication or unexpected authorization failures. Authorization should be enforced by Spring Security at the right layer, and request cleanup left to the filters.

### Cleaning Up at Self-Owned Boundaries

If an independent background routine **explicitly sets the context** for a whole task without a surrounding Spring Security Servlet filter, clean up in `finally`:

~~~java
// Code placed in a Spring Security app; authentication was
// already verified by a trusted mechanism.
SecurityContext taskContext = SecurityContextHolder.createEmptyContext();
taskContext.setAuthentication(verifiedAuthentication);

try {
    SecurityContextHolder.setContext(taskContext);
    task.run();
} finally {
    SecurityContextHolder.clearContext();
}
~~~

This is a **fragment**, not a standalone runnable Java class: `verifiedAuthentication` and `task` are supplied by the application, with Spring Security imports. The `clearContext()` pattern fits when the task **owns the entire context boundary** on an independent executor thread. If this is merely a nested scope on a thread that already holds a valid context, use a **save/restore previous context** pattern instead of wiping out the outer scope's context. In such cases, prefer standard Spring Security wrappers.

## 6. Passing Security Context to Another Thread: What Can Go Wrong?

The `MODE_THREADLOCAL` strategy does not automatically transfer an HTTP request's context to a new thread. Common scenarios:

- Calling `@Async` to process work after the controller returns a response.
- Submitting a `Runnable` or `Callable` to an `ExecutorService` / thread pool.
- Manually creating a new thread with `new Thread(...)`.
- Enqueuing callbacks/tasks in a job system or message consumer.

This creates **two opposing risks**:

1. The task does not receive the needed authentication, so it sees anonymous/`null`.
2. The task sets/copies authentication manually without cleanup; the next task reads the old user by mistake.

**Never solve this by setting `SecurityContextHolder.MODE_GLOBAL`** in a multi-user web application: the global strategy shares context across request boundaries. `MODE_INHERITABLETHREADLOCAL` is likewise unsuitable as a general solution for long-lived executors: threads may be created before requests arrive and reused across many requests; contexts can be inherited at the wrong time or become stale.

### Using Spring Security Wrappers

Spring Security provides abstractions to wrap work needing a security context, such as:

- `DelegatingSecurityContextRunnable`.
- `DelegatingSecurityContextCallable`.
- `DelegatingSecurityContextExecutor`.
- Corresponding variants for executor services or task executors depending on API.

An example fragment inside a Spring Security application:

~~~java
import java.util.concurrent.Executor;
import org.springframework.security.concurrent.DelegatingSecurityContextRunnable;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

// Runs inside an authenticated request:
// Capture an independent context to avoid sharing the mutable object.
Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();

SecurityContext captured = SecurityContextHolder.createEmptyContext();
captured.setAuthentication(auth);

Runnable job = () -> {
    Authentication current =
            SecurityContextHolder.getContext().getAuthentication();
    System.out.println(current == null ? "<none>" : current.getName());
};

Runnable securedJob = new DelegatingSecurityContextRunnable(job, captured);
executor.execute(securedJob);
~~~

`executor` here is an application-managed `Executor`; this is an **illustrative Spring application snippet**, not standalone Java. The wrapper installs the required context on the thread while the job runs and restores/clears the holder per Spring Security's mechanism when the job ends. Using wrappers avoids missing cleanup even when tasks throw exceptions.

Safety notes:

- `captured` is a **fresh context**, yet `Authentication auth` inside may still reference the same object as the original request; never mutate it or hold it indefinitely. If the task needs only a verified user ID or tenant ID, passing those exact business fields is usually simpler and safer.
- Decide **when capture happens**. Capturing context at application startup instead of task submission would make every task run under a fixed wrong identity.
- Never pass client A's authentication into a task processing work for client B. Propagating context grants access to sensitive data and requires a clear business reason.
- Long-running tasks executing after a request finishes may retain stale verification info; implement permission re-checks, token expiration handling, or dedicated service identities if the work requires them.
- Executors need proper lifecycle management; avoid creating a new thread pool per HTTP request.

When many tasks share an executor, one pattern is wrapping the executor with `DelegatingSecurityContextExecutor`. When using constructors that capture context at submission time, verify your version's capture semantics and avoid pinning a user long-term. This does not replace authentication/authorization inside background workflows.

### Servlet Async Differs from Ad-Hoc Background Tasks

Spring MVC provides some security context integration for supported async mechanisms, yet you should not assume every callback or custom `CompletableFuture` automatically receives the context. For Servlet `ASYNC`/`ERROR` dispatches, saving context in request attributes and configuring dispatcher types can affect principal visibility on the next dispatch. Diagnose by testing the exact flow in use and verifying the holder is cleared on participating threads.

## 7. When to Save/Restore Instead of Simply Clearing?

A utility function may be called **nested on the same thread**:

~~~text
Outer context: user=alice
    |
    +--> Temporary scope: technicalPrincipal
             |
             +--> runs work with dedicated privileges
             |
         scope ends
    |
Outer context must return to: user=alice
~~~

In this situation, `clearContext()` after the temporary scope would wipe out visibility of the outer scope's context too. A **save/restore** pattern fits better:

~~~java
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

SecurityContext previous = SecurityContextHolder.getContext();

try {
    SecurityContext temporary = SecurityContextHolder.createEmptyContext();
    temporary.setAuthentication(temporaryAuthentication);
    SecurityContextHolder.setContext(temporary);
    action.run();
} finally {
    SecurityContextHolder.setContext(previous);
}
~~~

This fragment uses `temporaryAuthentication` and `action` provided by the caller in a Spring Security environment. Using a **fresh context** avoids calling `previous.setAuthentication(...)` on the same mutable object and mistaking it for a copy. Save/restore is valid only when **`previous` is genuinely a valid outer-scope context**, not a stale context leaked from another request.

For independent tasks from an executor, inputs must carry explicitly authorized context and the thread must return to a clean state at the end. Never treat restoring an old context of unknown origin as safe; it can preserve an existing leak.

Where a Spring Security wrapper exists for `Runnable`/`Callable`/`Executor`, prefer it because it handles context binding and cleanup/restoration per framework contracts, reducing the risk of missed exception paths.

## 8. Cleanup Is Not Logout, Session Deletion, or Token Revocation

These four operations address **four distinct scopes**:

| Operation | Scope | What NOT to infer |
| --- | --- | --- |
| `SecurityContextHolder.clearContext()` | Current context storage of the holder/strategy | Does not delete sessions, database records, or issued tokens |
| `SecurityContextRepository.saveContext(...)` | Saves context to the configured repository | Does not immediately update other threads |
| Logout handlers like `SecurityContextLogoutHandler` | Handles logout per config: clears authentication, may invalidate session, and runs related cleanup | Does not automatically revoke issued stateless JWTs without dedicated revocation |
| Bearer token expiration/revocation | Token/verification layer for future requests | Does not replace per-request `ThreadLocal` cleanup |

For example, in an app using form login and `HttpSessionSecurityContextRepository`: after the first request, the context is stored in the session for subsequent requests; at the end of **every request**, the worker thread's holder must still be cleared. On logout, the app must invalidate the session and update repository/cookies per design. Calling only `clearContext()` while keeping the session intact lets the next request reload the same old authentication from the session.

For APIs using stateless Bearer/JWT tokens, each request normally rebuilds `Authentication` from the incoming token; the end of the request must clear the holder, yet the client's token remains usable for new requests until expiration or explicit revocation. Never use `clearContext()` as a "JWT logout".

### Why Does Stateless Also Need Cleanup?

"Stateless" in API design primarily means **not relying on sessions to remember logins across HTTP requests**. Within **one** request, Spring Security still needs a temporary context so filters and controllers can access the principal, authorities, or authentication details. When the request ends, that context must still be cleared from the thread, regardless of whether the app uses sessions.

## 9. Mutable Contexts and Identity Stored in Static Variables

Some bugs stem not directly from forgetting `clearContext()`, but from **object sharing**:

~~~java
// WRONG example: a global variable shared across all requests.
static Authentication currentAuthentication;
~~~

If request A writes `currentAuthentication=authAlice` and request B writes `authBob`, code in request A can read `authBob`. This is a race condition / shared-data bug—completely separate from `ThreadLocal` yet equally capable of mixing identities.

Even with `SecurityContextHolder`, exercise caution:

~~~java
// Avoid mutating a context that may be unintentionally shared:
SecurityContextHolder.getContext().setAuthentication(newAuthentication);
~~~

If you genuinely must set the context manually after verifying via a trusted mechanism, create a fresh context:

~~~java
SecurityContext fresh = SecurityContextHolder.createEmptyContext();
fresh.setAuthentication(verifiedAuthentication);
SecurityContextHolder.setContext(fresh);
~~~

This is a fragment inside a Spring Security app; `verifiedAuthentication` must come from a valid authentication flow—**never construct a trusted token solely from client-claimed usernames or roles**. When persisting login across requests, also follow `SecurityContextRepository` persistence and session security practices. Never mutate authentication just to pass `@PreAuthorize` or authorization filters.

Never store request `SecurityContext` or `Authentication` objects in singleton fields, static maps, long-lived callbacks, or app-wide caches without clear lifecycle and data ownership design.

## 10. Custom Filters: Who Has the Right to Clear the Context?

A custom Servlet filter may want to log identity, attach a correlation ID, or measure latency. If it runs **inside** `SecurityFilterChain`, understand its position relative to the context-managing filter and authentication filters.

Example of a filter that only reads the principal:

~~~java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public class IdentityAuditFilter extends OncePerRequestFilter {
    private static final Logger log =
            LoggerFactory.getLogger(IdentityAuditFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();
        String name = authentication == null ? "none" : authentication.getName();

        log.debug("Security principal for {}: {}", request.getRequestURI(), name);
        chain.doFilter(request, response);
    }
}
~~~

This class is for Spring Security 6.x applications with Jakarta Servlet and SLF4J, and does not run directly with `javac` without the classpath. To ensure the filter sees the context/authentication at the desired point, place it at the right spot in the chain—for instance via `HttpSecurity.addFilterAfter(...)` or `addFilterBefore(...)` with a valid anchor class and awareness of actual filter ordering.

You do not need to put `SecurityContextHolder.clearContext()` in `finally` inside every custom filter that reads the context. If Spring Security wraps the request, cleanup is already handled by the dedicated filter; a misplaced custom filter could wipe out the context before downstream code needs it. If a custom filter **sets the context itself** outside the standard chain, it must own cleanup for that scope, including exception paths.

**Double filter registration is a separate bug.** If a class carries `@Component` so Spring Boot auto-registers it with the Servlet container while also being added to `HttpSecurity`, it can run twice or affect unintended requests. Decide clearly between Servlet-filter level and Security-filter-chain level for custom filters; disable container-level registration via `FilterRegistrationBean` when appropriate.

### On Logging and Privacy

Log identity only when genuinely needed for auditing/diagnostics with proper data policies in place. Never log `Authentication.getCredentials()`, bearer tokens, password hashes, cookies, or the full `Authentication.getDetails()`. Be careful with principals containing personal data and with logging a leaked identity: logging the wrong identity can hinder incident investigation.

## 11. Testing That Requests Do Not Misuse Identities

Suppose we have a simple controller:

~~~java
import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {
    @GetMapping("/whoami")
    public String whoAmI(Principal principal) {
        return principal.getName();
    }
}
~~~

And an illustrative chain:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WhoAmISecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/whoami").authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Both classes belong to a Spring Boot 3.x project with `spring-boot-starter-web` and `spring-boot-starter-security`. Below is a MockMvc test additionally requiring `spring-boot-starter-test`, `spring-security-test`, component-scanned controller, and Spring Security filters active in MockMvc:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ContextCleanupTest {
    @Autowired
    MockMvc mockMvc;

    @Test
    void identitiesAreIsolatedAcrossRequests() throws Exception {
        mockMvc.perform(get("/whoami").with(user("alice")))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));

        assertNull(SecurityContextHolder.getContext().getAuthentication());

        mockMvc.perform(get("/whoami").with(user("bob")))
                .andExpect(status().isOk())
                .andExpect(content().string("bob"));

        assertNull(SecurityContextHolder.getContext().getAuthentication());

        mockMvc.perform(get("/whoami"))
                .andExpect(status().isUnauthorized());

        assertNull(SecurityContextHolder.getContext().getAuthentication());
    }
}
~~~

Here `user(...)` is a `spring-security-test` request post-processor and **does not verify real passwords**. With the HTTP Basic entry point and chain in the example, an unauthenticated request typically receives 401; the test also confirms the MockMvc thread's holder is cleared after each request completes.

**Limitations of the test:** `MockMvc` alone does not prove a production system is free of identity leakage across every thread pool, Servlet async dispatch, message consumer, and custom executor. The test above checks only three requests inside MockMvc. To verify pool-reuse bugs, add integration tests/cases with reused worker threads, async tasks, or a real server; send interleaved requests from two identities and also check business outcomes.

Do not use `@WithMockUser` in this test if the goal is verifying the holder is **empty after each request**, because the test execution listener may intentionally populate the context on the test thread before the request and clear it at the end of the test, altering the condition being tested.

## 12. Diagnostic Workflow for Suspected Identity Leakage

If an endpoint suddenly sees the wrong user, check in order:

1. **Identify the actual request:** endpoint, HTTP method, whether session cookie or Authorization header is present, whether reverse proxies and multiple `SecurityFilterChain` beans exist.
2. **Verify the selected chain:** did `FilterChainProxy` choose a chain containing the context-managing filter, and where does any custom filter sit in that chain?
3. **Inspect authentication source:** did it come from an HTTP session repository, bearer token, Basic auth, test principal, or manual context assignment?
4. **Search all calls** to `SecurityContextHolder.setContext(...)`, `getContext().setAuthentication(...)`, and `setStrategyName(...)`. Where code sets it manually, verify cleanup/restore in `finally`.
5. **Inspect tasks/executors:** does code use `@Async`, `new Thread`, `CompletableFuture`, scheduled jobs, thread pools, or context-propagating wrappers?
6. **Check capture time and lifetime:** is a security context retained in a singleton, shared mutable object, or task queue long after the request ends?
7. **Separate persistence from cleanup:** is the session still valid; is reloading context from session expected; is a stateless API resending the bearer token?
8. **Test two identities:** run A then B on the same worker in a controlled test, confirming no stale authentication remains between the two tasks.
9. **Check error/async paths:** test successful requests, authorization denials, exceptions, and async callbacks; look for bypassed `finally` blocks caused by nonstandard manual management.
10. **Verify after fixing:** automated tests should assert behavior, not rely solely on a debug log line claiming "cleared".

In dev/test environments, you can increase Spring Security logging:

~~~properties
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
logging.level.org.springframework.security.core.context=DEBUG
~~~

Logger names and detail levels vary by version and are not guaranteed to print every holder operation. Avoid printing credentials, tokens, or full security contexts. When observing identity for testing, log only safe info with clear justification and delete sensitive logs after investigation.

### When Referencing Docs Across Spring Security Versions

Some older articles assume `SecurityContextPersistenceFilter` always auto-loads, auto-saves, and clears the context. In Spring Security 6.x, depending on configuration, `SecurityContextHolderFilter` and explicit save may behave differently. Always verify your version, actual filter list, and `SecurityContextRepository` before applying code copied from another version.

The consistent rule: **the thread processing a request must never retain the previous request's identity** past the cleanup boundary, even though cross-request persistence via session/token may exist per authentication policy.

## 13. Common Mistakes to Avoid

| Mistake | Why it is wrong | Proper practice |
| --- | --- | --- |
| "ThreadLocal auto-expires when the request ends" | Threads outlive individual requests and get reused | Framework cleanup; manual code must use `finally` |
| Calling `clearContext()` mid-controller | Erases authentication while downstream steps still need it | Let filters manage the request lifecycle |
| Calling `setContext(...)` for a job and forgetting cleanup | Worker pool retains previous task's identity | Wrap tasks with Spring Security delegation or scoped cleanup |
| Enabling `MODE_GLOBAL` on a web server | Context data crosses per-user boundaries | Use thread-local and appropriate context propagation |
| Enabling `MODE_INHERITABLETHREADLOCAL` to fix thread pools | Threads are created/reused independently of requests | Wrappers/executors with explicit capture and cleanup |
| Using `SecurityContextHolder.clearContext()` as logout | Sessions/tokens may still remain valid | Use logout handlers and valid revoke/invalidation mechanisms |
| Putting `newAuthentication` into a shared old context | Mutable context may be referenced by another scope | Create a fresh context from a trusted verification source |
| Keeping `Authentication` in a singleton's static field | Every request reads/writes shared state | Use scoped context and business data with clear lifetimes |
| Treating `setContext(...)` as saving to the session | Holder and repository have different contracts | Check explicit save for your version/configuration |
| Testing only a single request | Cannot observe thread reuse or A→B leakage | Test two identities, exceptions, and thread pools |

## 14. Self-Check Exercises

**Scenario A.** Servlet thread `http-worker-3` just processed Alice, then moves on to Bob. `ThreadLocal` previously held Alice. Why must cleanup still happen after Alice's request?

**Answer:** Servlet threads can be reused. If Alice's context stays in `ThreadLocal` and is not properly cleared or replaced, Bob or code running before new authentication could see Alice's identity. Spring Security's context-managing filter must clear the holder at the request boundary.

**Scenario B.** An application uses session login. After every request, Spring Security clears the holder. Must the user log in again on the next request?

**Answer:** Not necessarily. If the context was properly saved in `SecurityContextRepository` (e.g., session), the next request can reload authentication. Clearing the thread's holder and persisting context across requests are two separate responsibilities.

**Scenario C.** A custom executor uses only one thread. Task A sets Alice's auth without clearing; task B sets no auth. Whom might task B see?

**Answer:** It can see Alice's authentication because the worker thread is reused. Proper propagation/cleanup mechanisms are required. `ThreadPoolIdentityLeakDemo` demonstrates this exact phenomenon using JDK `ThreadLocal`.

**Scenario D.** Inside a service handling user Alice, code temporarily switches context to a technical identity and then calls `clearContext()` before returning to the service. What can go wrong?

**Answer:** Alice's outer-scope context may become unavailable. For nested scopes, save/restore the previous context—ideally using a Spring Security abstraction—and ensure the technical identity is properly authorized.

**Scenario E.** A JWT was issued to a client and is still valid. The server just called `clearContext()` at request end. Is the JWT revoked?

**Answer:** No. Cleanup only clears the current execution context. Token revocation must be enforced by expiration/revocation policies and token verification mechanisms.

**Scenario F.** An app uses `@Async` for business processing. Inside the async task, `SecurityContextHolder.getContext().getAuthentication()` is `null`. Should you enable `MODE_GLOBAL` to fix it?

**Answer:** No. Use a wrapper/context propagation mechanism matching how tasks execute, or pass a verified user ID as business data. The global strategy can cause other requests to read the wrong identity.

## 15. Project Implementation Checklist

- Identify **which `SecurityFilterChain`** manages the request and which filter handles context in your Spring Security version.
- Remember that default Servlet `SecurityContextHolder` typically relies on `ThreadLocal`, while thread pools outlive individual requests.
- Let Spring Security filters **clear the holder after requests**; never wipe authentication arbitrarily while controllers/services still need it.
- For code setting context manually at **independent task boundaries**, always clean up in `finally`; for nested scopes, properly save/restore the prior context.
- Distinguish **holder cleanup**, **saving context in a repository**, **logout**, and **session/token revocation**.
- Use wrappers like `DelegatingSecurityContextRunnable` when transferring identity across executors; never use the global strategy on multi-user servers.
- Avoid shared mutable `SecurityContext` objects, static `Authentication` fields, and principal-holding variables without lifecycles.
- Test Alice's request followed by Bob's, anonymous users, denied requests, exceptions, thread pools, and async paths realistically.
- Log just enough info for diagnostics; never log credentials/tokens or unnecessary principal data.

**Conclusion:** Per-request context security requires **loading/binding the right `SecurityContext` at the start**, **clearing the holder at the end**, and **explicitly managing boundaries when passing info to other threads**. An uncleared `ThreadLocal` can turn the previous user's identity into the next user's identity; timely cleanup and Spring Security's standard wrappers prevent that class of bugs.
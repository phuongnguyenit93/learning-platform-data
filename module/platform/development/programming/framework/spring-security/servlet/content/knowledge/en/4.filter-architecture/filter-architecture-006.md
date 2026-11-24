# SecurityContextHolderFilter and the Lifecycle of a Request's Context

> **Scope:** Spring Security on the **Servlet stack**, in the context of filter architecture. The goal is to understand how `SecurityContextHolderFilter` introduces `SecurityContext` into the processing flow, who saves the context for subsequent requests, when the context is cleared, and special conditions such as exceptions, multiple filter chains, or asynchronous processing. The Spring examples below use common APIs of Spring Security 6.x / Spring Boot 3.x (Java 17+); actual configuration may vary by version and security choices.

## 1. Four concepts that must not be conflated

| Component | Role | Typical lifecycle |
| --- | --- | --- |
| `SecurityContext` | Holds the current `Authentication` (principal, authorities, and related authentication details). | A context instance used during execution; may be reloaded from configured storage. |
| `SecurityContextHolder` | Access point for `SecurityContext` from code running on the current thread. The default strategy on the Servlet stack is `MODE_THREADLOCAL`. | Scoped to the active processing thread; must be cleared when exiting the filter scope. |
| `SecurityContextRepository` | Loads and, when called, saves `SecurityContext` to the configured store (such as request attributes or HTTP session). | Can span a single dispatch or multiple HTTP requests, depending on the repository type. |
| `SecurityContextHolderFilter` | Makes the context loaded from the repository accessible to the rest of the filter chain, then clears the holder. | Scoped to a single execution of the filter chain corresponding to a dispatch/thread. |

**Key distinction:** having a **context in `SecurityContextHolder`** does not automatically mean that context **has been saved** for the next HTTP request. Likewise, calling `clearContext()` when exiting the filter chain does not mean deleting the session, destroying the account, or logging out.

In a Servlet application, `DelegatingFilterProxy` normally connects the container's filter system with Spring Security's `FilterChainProxy`. `FilterChainProxy` selects a `SecurityFilterChain` matching the request; inside the chain, `SecurityContextHolderFilter` runs before authentication/authorization filters that depend on the security context. Filter order and list **depend on configuration** and should not be inferred from class names alone.

## 2. Timeline of a synchronous HTTP request

~~~text
HTTP request -> Servlet container assigns worker thread T1
  -> DelegatingFilterProxy / FilterChainProxy
     -> selects SecurityFilterChain for request
        -> SecurityContextHolderFilter
           (1) creates deferred context from SecurityContextRepository
           (2) binds deferred context to SecurityContextHolder for T1
           -> authentication filters (if needed)
           -> authorization filters
           -> controller/service
           (3) successful authentication may save context via repository
           (4) end of chain, clear holder in finally
  -> T1 returns to pool, may serve another request
~~~

The core mechanism can be understood through the following **abbreviated** pseudocode; this is not Spring Security's complete source implementation:

~~~java
// PSEUDOCODE: illustrates lifecycle, not a standalone runnable class.
var deferred = repository.loadDeferredContext(request);
try {
    securityContextHolderStrategy.setDeferredContext(deferred);
    chain.doFilter(request, response);
} finally {
    securityContextHolderStrategy.clearContext();
}
~~~

Points to keep accurate when reading the diagram:

1. `loadDeferredContext(request)` enables **deferred loading**: the filter sets up a context supplier, and accessing the backing store may only occur when downstream code actually needs the context. It does not mean every request always reads the session immediately upon entering the filter.
2. Calling `SecurityContextHolder.getContext()` downstream causes the application to retrieve the context available for the current thread; if the repository has no saved context, the mechanism can supply an initial empty context.
3. Authentication filters can place a successful `Authentication` into a new context. Authorization filters afterward rely on authentication/context to check permissions.
4. **`SecurityContextHolderFilter` does not automatically call `saveContext(...)` when the request finishes**. Under explicit-save mode, the component performing the change is responsible for saving when authentication needs to persist for future requests.
5. `finally` ensures the holder is cleared when the downstream filter chain completes or throws an exception. Context saved in the repository (if saved) remains according to the repository's policy.

The diagram describes only the **synchronous execution scope**. An HTTP request can continue via an async dispatch or another thread, so a request must not be assumed to remain permanently bound to a single T1.

## 3. What is deferred loading (`DeferredSecurityContext`)?

`SecurityContextRepository` supports `loadDeferredContext(HttpServletRequest)` to obtain a `DeferredSecurityContext` object. It provides on-demand access to the context; Spring Security can use its `Supplier<SecurityContext>` to integrate with `SecurityContextHolderStrategy.setDeferredContext(...)`.

Compare two scenarios:

- **Request requiring no permissions or principal:** the filter still sets up the context supplier, yet does not necessarily load authentication data from the session if nothing accesses it.
- **Request accessing a protected endpoint:** the authorization filter or other code needs `Authentication`; the context is retrieved from the appropriate repository, or created fresh if no saved copy exists.

"Deferred" refers to **when data is accessed**, not cross-thread context propagation and not a login persistence mechanism. Once a context is loaded or created, changes to the context still must be saved under the explicit-save policy if they are meant to outlive the current scope.

If `SecurityContextHolder.getContext().getAuthentication()` returns `null`, authentication may not have occurred yet. If you see an `AnonymousAuthenticationToken`, that is still not a logged-in user. Do not write security logic relying solely on "Authentication is not null"; use Spring Security's authorization rules.

## 4. Distinguishing two related filters: Holder vs. Persistence

| Question | `SecurityContextHolderFilter` | `SecurityContextPersistenceFilter` |
| --- | --- | --- |
| Provides context to the rest of the filter chain? | Yes, via the deferred context and holder mechanism. | Yes, using the legacy filter's context-loading approach. |
| Clears the holder when the chain's work completes? | Yes. | Yes. |
| Automatically saves context when the chain ends? | **No**; requires explicit saving when needed. | Has an auto-save mechanism at the end of request/response in the corresponding configuration model. |
| When is it commonly seen? | Common in modern Spring Security configurations with `requireExplicitSave(true)`. | Some configurations/versions compatible with the auto-save model, such as choosing `requireExplicitSave(false)` where the API still supports it. |

Do not insert both into the chain "just to be safe"; configure based on your version and desired behavior, and inspect the actual filter chain.

**Why explicit-save matters:** the end of a request is not the only reliable moment to decide whether to save context. The response may already be committed, async processing may occur, or unintended context writes may happen. With `SecurityContextHolderFilter`, deciding **when to save** moves to the place handling authentication/context changes. This clarifies ownership and avoids relying on hard-to-observe automatic writes.

## 5. Who is responsible for saving `SecurityContext`?

Distinguish three actions:

1. **Read:** `SecurityContextHolder.getContext()` retrieves the context bound to the thread, which may trigger loading the deferred context.
2. **Set:** `SecurityContextHolder.setContext(context)` replaces the current thread's context.
3. **Persist within repository scope:** `securityContextRepository.saveContext(context, request, response)` causes the repository to update its store according to policy.

Example **code snippet inside a custom authentication filter**, after verifying login credentials via `AuthenticationManager`:

~~~java
Authentication authentication = authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(username, password)
);

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);

// Important: use the security filter chain's exact repository.
securityContextRepository.saveContext(context, request, response);
~~~

This snippet requires Spring Security 6+ with imports for `Authentication`, `AuthenticationManager`, `UsernamePasswordAuthenticationToken`, `SecurityContext`, `SecurityContextHolder`, `SecurityContextRepository`, `request`/`response` objects, and `username`/`password` variables safely extracted from the request. It is **not a standalone Java SE program** or a complete login filter: a real filter must also handle failed authentication, CSRF, session fixation, success/failure handlers, and must never log passwords.

- Creating a context with `createEmptyContext()` and placing `Authentication` into it prevents accidentally mutating a context reused elsewhere.
- Call `saveContext` **before the response is committed** when saving requires a session/cookie. Without saving, authentication may still be available during the current request, yet the next request reverts to unauthenticated.
- Built-in Spring Security authentication mechanisms (e.g., standard configured form login) already integrate proper context saving. Do not scatter manual `saveContext` calls across controllers.
- When security is configured as **stateless**, token/basic authentication contexts are typically recreated or authenticated on each request; it does not mean the application should create an HTTP session to "fix" not saving.

**Principle:** `SecurityContextHolderFilter` manages **access scope and cleanup**; the authentication component is responsible for **setting authentication**, and the repository and authentication mechanism decide **whether to save**.

### Illustrative configuration using Spring Boot 3 / Spring Security 6

In a Spring Boot project with `spring-boot-starter-web` and `spring-boot-starter-security`, create `SecurityConfig.java` in a component-scanned package:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
            .securityContext(c -> c.requireExplicitSave(true))
            .authorizeHttpRequests(a -> a
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
~~~

This snippet is a **configuration class inside a Spring application**, not runnable with `javac` alone without the Spring classpath. `requireExplicitSave(true)` states the policy explicitly, and `formLogin` provided by Spring Security performs the appropriate authentication/context-saving steps. The `/public` path is merely an example; the application needs a corresponding endpoint if you want to access it. When modifying security configuration, verify other chains as well as the actual Spring Security version.

## 6. `SecurityContextRepository` determines how long data persists

| Repository | Data scope | When to consider it |
| --- | --- | --- |
| `HttpSessionSecurityContextRepository` | Can retain context across HTTP requests sharing the same valid session, according to session creation/usage policy. | Stateful applications using sessions, such as form login. |
| `RequestAttributeSecurityContextRepository` | Retains context across dispatches of the **same request** while request attributes remain alive; useful for error dispatches. | When context is needed across multiple dispatches of the same request, not long-term sessions. |
| `NullSecurityContextRepository` | Does not save context for reloading between requests. | Stateless endpoints or per-request authentication models. |
| `DelegatingSecurityContextRepository` | Combines multiple repositories; load/save behavior follows the configured delegates. | Common Servlet setup combining request attributes and session. |

Some Spring Security 6 configurations use `DelegatingSecurityContextRepository` combining request attribute and session; do not assume every application uses this combination. Whether a session exists and what it contains depend on `SessionCreationPolicy`, the actual repository, authentication method, and security setup.

### Three requests to distinguish holder from session

~~~text
Request A (session S)
  filter loads context: no authentication yet
  user logs in successfully: Authentication = alice
  authentication flow saves context via repository
  filter ends: clears context on thread T1

Request B (same session S)
  filter can reload alice's context from repository
  authorization reads Authentication = alice
  filter ends: clears context on the active thread

Request C (different session or stateless without credentials)
  must not inherit Authentication from A or B
  may see empty/anonymous context depending on filter chain
~~~

**Thread-scoped holder lifecycle** and **repository-stored context lifecycle** are two distinct things. `clearContext()` prevents A's data from lingering on a worker thread serving C; it does not erase context intentionally saved in session S. Conversely, if A fails to save while still seeing authentication inside A, B failing to stay logged in is predictable behavior.

## 7. Runnable Java 17 experiment: load, save, and clear

The example below uses Java SE to **simulate** the relationship between a store, a thread-local holder, and cleanup on the same worker thread. This is **not Spring Security's implementation**: the example loads **eagerly**, whereas `SecurityContextHolderFilter` supports deferred loading; the real repository is HTTP/session-aware rather than a `ConcurrentHashMap`.

Create `ContextLifecycleDemo.java`:

~~~java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class ContextLifecycleDemo {
    private static final Map<String, String> STORED = new ConcurrentHashMap<>();
    private static final ThreadLocal<String> HOLDER = new ThreadLocal<>();

    private static void request(String name, String session, Runnable chain) {
        String saved = STORED.get(session);
        if (saved == null) {
            HOLDER.remove();
        } else {
            HOLDER.set(saved);
        }

        try {
            System.out.println(name + " loaded: " + HOLDER.get());
            chain.run();
        } finally {
            HOLDER.remove();
            System.out.println(name + " cleared: " + HOLDER.get());
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService worker = Executors.newSingleThreadExecutor();
        try {
            worker.submit(() -> request("R1", "S1", () -> {
                HOLDER.set("alice");
                STORED.put("S1", HOLDER.get()); // Explicit save.
                System.out.println("R1 saved: " + STORED.get("S1"));
            })).get();

            worker.submit(() -> request("R2", "S1", () ->
                System.out.println("R2 sees: " + HOLDER.get())
            )).get();

            worker.submit(() -> request("R3", "S2", () ->
                System.out.println("R3 sees: " + HOLDER.get())
            )).get();
        } finally {
            worker.shutdown();
        }
    }
}
~~~

Run on JDK 17 or higher:

~~~bash
javac ContextLifecycleDemo.java
java ContextLifecycleDemo
~~~

Exact output:

~~~text
R1 loaded: null
R1 saved: alice
R1 cleared: null
R2 loaded: alice
R2 sees: alice
R2 cleared: null
R3 loaded: null
R3 sees: null
R3 cleared: null
~~~

The three tasks run sequentially on the same worker due to `newSingleThreadExecutor()` and `Future.get()`. R1 sets and **saves** "alice" for S1; R2 shares session S1 so it reloads it; R3 has S2 so it lacks that value. All three call `remove()` in `finally`, ensuring a reused thread does not retain data from a prior request. If you omit `STORED.put(...)`, R2 will also see `null` even though R1 had set "alice" in the holder.

Do not use this example as a way to implement authentication: the string "alice" is not a verified `Authentication` and a shared map cannot replace a session manager. The purpose is to prove that **saving and clearing are two independent actions**.

## 8. Exceptions, error dispatches, and asynchronous processing

### Exceptions in the filter chain

~~~text
SecurityContextHolderFilter -> authentication/authorization/controller
                           -> exception
                           -> unwind filter stack
                           -> finally: clearContext() on the running thread
~~~

When downstream code throws an exception, `SecurityContextHolderFilter`'s `finally` block still clears the security context it bound during execution. The exception may be converted into a response by `ExceptionTranslationFilter` or another exception handler; that does not replace cleanup responsibility. If code creates its own `ThreadLocal` or sets context manually in tasks outside the chain, it must have **its own** cleanup.

### ERROR and ASYNC dispatches

An HTTP request may go through multiple dispatches on different threads. `RequestAttributeSecurityContextRepository` helps keep context request-scoped in cases like ERROR dispatches; however, which dispatches a filter runs on still depends on Servlet dispatcher types, filter registration, and configuration.

In async processing:
- Thread T1 may exit the initial request handling and return to the pool while the response is not yet complete.
- Thread T2 executes `Callable`, `CompletableFuture`, `@Async`, or callbacks; it does **not automatically** see T1's `SecurityContextHolder`.
- Spring Security supports integration with Spring MVC `Callable` via `WebAsyncManagerIntegrationFilter` when the corresponding filter chain applies. Do not assume automatic support for every other executor/task.
- When managing tasks manually, consider passing minimal identifying data via parameters or using `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextExecutor`, `DelegatingSecurityContextExecutorService` (or an appropriate executor wrapper), with context captured/cleared at the proper scope.
- Using `MODE_INHERITABLETHREADLOCAL` does not solve context transfer across tasks in a pre-created thread pool.

**Do not retain context on T1 until async completes:** T1 may have already picked up another user's request. If background work runs for a long time, also consider that identity/permissions may have changed between submission and execution. Copying context does not by itself grant resource access.

## 9. Interaction with authentication, authorization, and logout

A processing chain can include components with distinct roles:

- `SecurityContextHolderFilter`: prepares where to obtain the security context and clears the holder when exiting the chain.
- Authentication filters such as form login or bearer token authentication: **verify credentials/tokens** via their mechanism and set the appropriate `Authentication`.
- `AnonymousAuthenticationFilter`: can set an anonymous authentication if no matching authenticated principal exists yet.
- `AuthorizationFilter` / authorization managers: check resource access rights based on context/authorization policy.
- Logout handlers: can invalidate the session, clear context, and perform repository-related clearing operations as configured.

These duties should not be lumped into a single custom filter merely because `SecurityContextHolder` is available. Clearing thread-local storage at the end of a request **is not** logout, and calling `clearContext()` manually in a controller when wanting to log out **does not guarantee** erasing context saved in the HTTP session. Use Spring Security's logout mechanism.

If there are multiple `SecurityFilterChain`s (for instance, stateless `/api/**` and stateful web), each chain can have different filters/repositories. Check **which chain actually matches the request** before concluding `saveContext` or session behavior is wrong. A request might match no Spring Security chain or match a different chain than the one whose configuration you are reading.

## 10. Common mistakes and how to diagnose them

| Symptom | Possible cause | Check / remedy |
| --- | --- | --- |
| Login succeeds within the same request, yet the next request is anonymous | Custom authentication called `setContext` without `saveContext` in explicit-save mode; session/cookie not persisted; or repository does not save. | Verify login mechanism, repository, and cookies/session; call `saveContext` in the responsible component if using custom auth. |
| User A's data appears in user B's request | Custom thread-local not cleared, manual holder mutation outside standard lifecycle, or improper use of `MODE_GLOBAL`/inheritance. | Check bind/clear in `finally`, thread pools, strategy config; never share context across users. |
| `SecurityContextHolder.getContext()` is empty in `@Async`/`CompletableFuture` | Task runs on another thread without context propagation. | Pass arguments or wrap the executor with an explicit capture and cleanup policy. |
| Authentication unreadable on ERROR dispatch | Dispatch/chain routing or repository only kept context per-thread, missing request-scoped persistence. | Check dispatcher types and `RequestAttributeSecurityContextRepository` if appropriate. |
| Called `clearContext()` yet the next request is still logged in | The session repository intentionally still holds the context. | Distinguish thread cleanup from logout; use proper logout handlers. |
| Repository has a session but does not save as expected | Stateless/`NullSecurityContextRepository` config, response committed too early, missed explicit-save, or using a different repo than the chain. | Verify actual repository, save timing, session policy, and response flow. |
| Filter only runs on some endpoints | `SecurityFilterChain`s have different request matchers and chain order. | Check matcher and order of selected chains; do not inspect only one `SecurityFilterChain`. |
| Single-request tests always pass, yet failures appear under high load | Thread pool reuse and async expose leftover context or missing propagation. | Test multiple users sequentially on the same worker, exception paths, and async paths. |

Do not conclude "`SecurityContextHolderFilter` is broken" just because authentication is empty: the request might be anonymous, the chain may not have run an authentication filter, the token may be invalid, the repo may be stateless, or the task may be on another thread.

## 11. Practical verification workflow

1. **Read chain configuration:** identify matchers, filter order, `securityContext()`, `requireExplicitSave(...)`, `SessionCreationPolicy`, and the actual repository. Especially when web and API have multiple chains.
2. **Trace one login:** at the point authentication succeeds, verify the new context has the right `Authentication`; identify where saving via the repository happens and verify timing before response commit.
3. **Send the next request with the same session:** check that the client sends back the right cookie/session, the context is loaded, and authorization works for the expected principal.
4. **Send a request without that session:** ensure it does not inherit the previous request's principal even if the container reuses the same thread.
5. **Trigger an exception:** verify the holder was cleared at the filter chain boundary; never log passwords, access tokens, or the entire security context.
6. **Test async/error:** test `Callable`, custom task executors, error dispatches, and nested dispatches; evaluate context propagation and per-thread cleanup separately.
7. **Test logout:** distinguish context in the current holder from context saved in the repository/session; confirm post-logout sessions no longer retain old privileges.

During local debugging, you can enable logging at an appropriate level for `FilterChainProxy` and security filters to see the selected chain and filter order. Turn off detailed logging before production, and only log necessary request IDs/authentication types without logging secrets.

### Self-check questions

**1. Why can `SecurityContextHolderFilter` still recover a login after calling `clearContext()`?** Because `clearContext()` clears data bound to the thread; context already saved in `SecurityContextRepository` can be reloaded for the next request.

**2. What happens if you call `setContext(context)` without `saveContext(...)`?** Downstream code in the current execution can see the new context; under explicit-save, the repository is not updated simply because the filter finishes, so subsequent requests may not see that authentication.

**3. Why is deferred loading not context propagation?** Deferred loading decides when the repository is accessed on the current thread; propagation is how context/data is carried across to another thread or task.

**4. Should you manually add `SecurityContextPersistenceFilter` after `SecurityContextHolderFilter` to auto-save?** No. Choose the save model matching your version/configuration; adding filters arbitrarily can cause overlapping lifecycles.

**5. Does stateless mean there is no `SecurityContextHolder`?** No. The current request still needs a security context for authorization; stateless only means not relying on persisting session/authentication across requests per the configured policy.

**Key takeaway:** `SecurityContextHolderFilter` **loads on demand → provides to downstream → clears the holder**. When authentication needs to be present on subsequent requests, you must understand **who saves the context, where it is saved, and when**. This is the core boundary between the lifecycle of a thread, an HTTP request, and a user session.

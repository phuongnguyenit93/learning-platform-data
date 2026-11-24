# Testing Writing, Reading, and Clearing SecurityContext in the Right Execution Model

**`SecurityContext`** holds the `Authentication` and identity/authorities that Spring Security uses within a processing flow. A statement like "the context was set" can refer to three different situations: setting the context on a **Servlet thread's `ThreadLocal`**, persisting the context in a **`SecurityContextRepository`** for the next request, or attaching it to the **Reactor Context** of a WebFlux subscription. Without distinguishing these cases clearly, tests can stay green while production leaks permissions between users, drops logins after redirects, or runs async tasks under the wrong identity.

The goal is to test the **write → read → clear** lifecycle in the exact execution model: Java unit tests, Spring MVC/Servlet filter chains, session persistence, thread pools/async, and WebFlux. Examples use Java 17+, modern Spring Security, and JUnit 5, clearly distinguishing standalone programs from snippets requiring Spring Boot.

**Security invariant:** a request from Alice must never cause an unrelated request or task from Bob to read Alice's `Authentication`. When a component's owned scope ends, it must clear/restore the context properly; if login must persist across requests, rely on a valid repository/token rather than leftover `ThreadLocal` state.

## 1. Concepts to Distinguish

| Component | Role | What tests must assert |
| --- | --- | --- |
| `Authentication` | Principal, authorities, credentials, authentication state | Right user/service, right permissions |
| `SecurityContext` | Container holding `Authentication` | Accurate `Authentication` at the right moment |
| `SecurityContextHolder` | API to access the current context | Reads accurately within the thread/strategy |
| `SecurityContextHolderStrategy` | Mechanism storing the holder's context | Servlet default is typically `ThreadLocal` |
| `SecurityContextRepository` | Saves/loads context across requests/dispatches | Next request carries/lacks session auth as expected |
| `SecurityContextHolderFilter` | Loads context for Servlet requests and clears at thread boundary | Never leaks to another request reusing the thread |
| `TestSecurityContextHolder` | Spring Security Test utility | Proper test fixture setup and cleanup |
| `ReactiveSecurityContextHolder` | Reads/attaches context via Reactor Context | Independent of JUnit/event-loop threads |

An empty `SecurityContext` can exist:

~~~java
SecurityContext context = SecurityContextHolder.getContext();
Authentication authentication = context.getAuthentication();
// authentication may be null even though context != null.
~~~

Therefore, do not write `assertNull(SecurityContextHolder.getContext())` after cleanup. The holder may lazily create a new empty context when `getContext()` is called. Assert `getAuthentication() == null` or assert that an anonymous request cannot access a protected endpoint.

Additionally, `AnonymousAuthenticationFilter` can create an `AnonymousAuthenticationToken` for unauthenticated requests. Having an `Authentication` with `isAuthenticated() == true` **does not necessarily** prove a user logged in interactively. Use the authorization framework or `AuthenticationTrustResolver` when distinguishing anonymous, remember-me, and fully authenticated principals.

## 2. Choosing a Test Strategy by Execution Model

| Environment | Where context lives | Testing tool | When cleared |
| --- | --- | --- | --- |
| Synchronous Java service | `SecurityContextHolder` / `ThreadLocal` | JUnit + `createEmptyContext`/`setContext` | `finally`, `@AfterEach` |
| Spring MVC Servlet request | Thread context managed by filter chain | `MockMvc` + Spring Security filters | End of chain, even on error |
| Spring Security Test fixture | `TestSecurityContextHolder`/test thread | `@WithMockUser` / `@WithSecurityContext` | `TestExecutionListener` |
| Executor/worker | `ThreadLocal` on worker, different from caller | `DelegatingSecurityContextExecutor` / `Runnable` | Wrapper `finally` on worker |
| WebFlux/reactive | Subscription's Reactor Context | `StepVerifier` + `ReactiveSecurityContextHolder` | Subscription completion/cancellation |
| HTTP WebFlux | `SecurityWebFilterChain` | `WebTestClient` + `mockUser` | Per exchange |
| Full HTTP over TCP | Context on server thread, not JUnit thread | Real login/cookie/token | Server lifecycle and session/token |

Do not port `SecurityContextHolder.setContext()` logic verbatim from Servlet to WebFlux. In reactive streams, operators can switch threads and context belongs to the subscription. Conversely, in standard Servlet apps, Reactor Context does not automatically propagate `Authentication` to an executor you create.

## 3. SecurityContext Lifecycle in Servlet

General flow:

~~~text
HTTP request
     |
     v
SecurityFilterChain
     |
     +-- SecurityContextHolderFilter loads context from repository
     +-- Authentication filter verifies credentials, creates Authentication
     +-- Authorization reads Authentication/authorities
     +-- Controller/Service reads principal during request
     |
     v
Filter chain completes or throws an error
     |
     v
Framework clears context from Servlet thread
     |
     v
Thread returns to pool, retaining no old request identity
~~~

**Clearing `ThreadLocal`** and **persisting the session** are two different things. Clearing context at the end of a request prevents Alice → Bob leaks. When Alice logs in with a session, Alice's next request must **reload** from the repository when a valid cookie/session is presented—not via a context surviving across two requests.

In Spring Security 6.x, `SecurityContextHolderFilter` is used by default to load context, yet it does not automatically save modified contexts. When a custom authentication flow wants session persistence, it must call explicit save after verification:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verifiedAuthentication);

SecurityContextHolder.setContext(context);

securityContextRepository.saveContext(
        context, httpServletRequest, httpServletResponse);
~~~

This is a **Servlet snippet**, in which `verifiedAuthentication` is created only after a provider verified credentials; the repository must be the real repository used by the chain. Save before the response redirects or commits. With the older `SecurityContextPersistenceFilter`, auto-save semantics differ; check your exact version and filter chain.

**Do not call `saveContext` on every stateless request.** If an API uses Bearer tokens and `NullSecurityContextRepository`, the system normally re-verifies the token on each request. Tests should expect a subsequent request without a token to be rejected.

## 4. Creating a New Context Instead of Mutating a Shared Context

Reading `Authentication`:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

if (authentication == null) {
    throw new IllegalStateException("No Authentication");
}

String principal = authentication.getName();
~~~

This snippet does not handle anonymous semantics; application code should rely on `SecurityFilterChain` and authorization policies.

When setting a verified `Authentication`, prefer:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
~~~

Avoid mutating an object directly by default when it might be shared:

~~~java
// Easily creates shared mutable state when context comes from repository:
SecurityContextHolder.getContext().setAuthentication(authentication);
~~~

A `SecurityContext` loaded from a session can have multiple references, especially across concurrent requests. Creating a fresh context reduces the risk of one request mutating the `Authentication` another request is reading.

## 5. JUnit 5: Set, Read, Clear on the Same Thread

File **SecurityContextHolderLifecycleTest.java** (Spring Security Core + JUnit 5):

~~~java
package demo.security;

import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.junit.jupiter.api.Assertions.*;

class SecurityContextHolderLifecycleTest {

    @AfterEach
    void cleanup() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void setReadAndClearOnCurrentThread() {
        assertNull(SecurityContextHolder.getContext().getAuthentication());

        Authentication verified = new UsernamePasswordAuthenticationToken(
                "alice", null,
                List.of(new SimpleGrantedAuthority("ROLE_USER")));

        SecurityContext next = SecurityContextHolder.createEmptyContext();
        next.setAuthentication(verified);
        SecurityContextHolder.setContext(next);

        assertSame(verified,
                SecurityContextHolder.getContext().getAuthentication());
        assertEquals("alice",
                SecurityContextHolder.getContext().getAuthentication().getName());

        SecurityContextHolder.clearContext();
        assertNull(SecurityContextHolder.getContext().getAuthentication());
    }

    @Test
    void anotherTestDoesNotInheritAuthentication() {
        assertNull(SecurityContextHolder.getContext().getAuthentication());
    }
}
~~~

This is a Spring Core test **with no HTTP or database**. It proves writing/reading/clearing on the **current thread**, not that Alice's credentials are real or that a session was persisted. The three-argument `UsernamePasswordAuthenticationToken` constructor marks the token authenticated; in tests that is a controlled fixture, **never a production shortcut to mark a client-sent username as authenticated**.

The `@AfterEach` cleanup protects when an assertion throws. However, it clears only the **test thread**; if a test spawns worker threads, you must check and clean up on those workers too.

## 6. Ownership: Clear or Restore the Context?

A component temporarily replacing context on a thread that already has an owner may need to **restore** the previous context:

~~~java
SecurityContext previous = SecurityContextHolder.getContext();
SecurityContext temporary = SecurityContextHolder.createEmptyContext();
temporary.setAuthentication(delegatedAuthentication);

try {
    SecurityContextHolder.setContext(temporary);
    doTemporaryWork();
} finally {
    SecurityContextHolder.setContext(previous);
}
~~~

This is a snippet; `delegatedAuthentication` and `doTemporaryWork()` belong to the application. Use this only once authorization and ownership policies for impersonation/delegation are explicitly defined.

When a test/worker owns the context from start to finish, it typically needs **clear**:

~~~java
try {
    SecurityContextHolder.setContext(contextForThisOperation);
    doWork();
} finally {
    SecurityContextHolder.clearContext();
}
~~~

If `doWork()` throws an exception, `finally` still executes. Never clear only in the success branch.

**Do not call `clearContext()` at the end of every ordinary Servlet service method**: other filters/controllers in the same request may still need the context. When the framework manages the boundary, the framework performs cleanup; code setting context outside the framework must perform cleanup per contract.

## 7. Standalone Java 17: Simulating ThreadLocal in a Thread Pool

File **ThreadLocalSecurityBoundaryDemo.java** runs without Spring; it models the hazard of reusing the same worker thread. This is **not `SecurityContextHolder`**, but a lab on `ThreadLocal` cleanup.

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ThreadLocalSecurityBoundaryDemo {

    private static final ThreadLocal<String> CURRENT = new ThreadLocal<>();

    private static void runAs(String principal) {
        try {
            CURRENT.set(principal);
            System.out.println("Scoped " + principal + " = " + CURRENT.get());
        } finally {
            CURRENT.remove();
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            Future<?> alice = pool.submit(() -> runAs("alice"));
            alice.get();

            String afterAlice = pool.submit(CURRENT::get).get();
            System.out.println("After alice = " + afterAlice);

            Future<?> bob = pool.submit(() -> runAs("bob"));
            bob.get();

            String afterBob = pool.submit(CURRENT::get).get();
            System.out.println("After bob = " + afterBob);

            System.out.println("Main thread = " + CURRENT.get());
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Run:

~~~bash
javac ThreadLocalSecurityBoundaryDemo.java
java ThreadLocalSecurityBoundaryDemo
~~~

Exact stdout:

~~~text
Scoped alice = alice
After alice = null
Scoped bob = bob
After bob = null
Main thread = null
~~~

`newSingleThreadExecutor()` reuses the worker, while `Future.get()` preserves output order. Removing `CURRENT.remove()` would let a subsequent task with no principal read Alice or Bob. In Spring Security, use official holder/wrapper APIs rather than building your own custom `ThreadLocal` for production identity.

## 8. Testing Servlet via MockMvc, Not Just Calling the Controller

To test the real filter chain, use `MockMvc` with Spring Security filters enabled. Example Spring MVC controller:

~~~java
package demo.security;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class IdentityController {
    @GetMapping("/whoami")
    String whoAmI(Authentication authentication) {
        return authentication.getName();
    }
}
~~~

This is a Spring Boot Servlet class requiring a `SecurityFilterChain` protecting `/whoami`. Illustrative configuration:

~~~java
@Bean
SecurityFilterChain chain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/whoami").authenticated()
                    .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
}
~~~

This is a configuration fragment requiring Spring Boot, imports, and an appropriate test user.

File **IdentityControllerSecurityTest.java**:

~~~java
package demo.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class IdentityControllerSecurityTest {

    @Autowired MockMvc mvc;

    @Test
    void authenticatedRequestDoesNotAuthenticateNextAnonymousRequest()
            throws Exception {

        mvc.perform(get("/whoami").with(user("alice").roles("USER")))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));

        mvc.perform(get("/whoami"))
                .andExpect(status().isUnauthorized());
    }
}
~~~

`with(user(...))` attaches a test user to the request **without requiring Alice to exist in the database**. The filter chain must actually run: `@AutoConfigureMockMvc` in Spring Boot normally registers security filters; with `MockMvcBuilders.standaloneSetup(...)`, you must add `apply(springSecurity())` or the configured `FilterChainProxy`.

The test above uses an HTTP Basic entry point, so anonymous requests normally return 401. With `formLogin`, browsers may receive a 302 redirect to the login page. The core invariant is that the second request must never be treated as Alice—not returning one rigid status across all apps.

## 9. @WithMockUser, @WithSecurityContext, and TestSecurityContextHolder

Spring Security Test can seed test context with annotations:

~~~java
@Test
@WithMockUser(username = "alice", roles = "USER")
void methodCanReadMockAuthentication() {
    Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();

    assertEquals("alice", auth.getName());
    assertTrue(auth.getAuthorities().stream()
            .anyMatch(a -> a.getAuthority().equals("ROLE_USER")));
}
~~~

This is a **test snippet** requiring JUnit 5, Spring Security Test, and a test context. `@WithMockUser` does not verify a real password; `roles="USER"` creates authority `ROLE_USER`. If you need a `UserDetails` from your service, use `@WithUserDetails`; if you need a custom principal, use `@WithSecurityContext` and a factory.

When Spring Security's `TestExecutionListener` populates the context before a test, the framework also clears it afterward. **Do not observe that the JUnit test thread's holder still holds Alice between two `MockMvc` calls inside the same annotated test and conclude there is a leak**: that may simply be the fixture managed by the test framework.

For manual setup:

~~~java
SecurityContext ctx = SecurityContextHolder.createEmptyContext();
ctx.setAuthentication(testAuthentication);
TestSecurityContextHolder.setContext(ctx);

// When injecting into a MockMvc request: .with(testSecurityContext())

TestSecurityContextHolder.clearContext();
~~~

This is a code fragment; `testAuthentication` comes from your test fixture, and `testSecurityContext()` is a Spring Security Test helper. Never clear the fixture before the request that needs it.

**Real HTTP over the network:** annotations on the JUnit thread do not cross TCP to a server running in another thread/process. When using `@SpringBootTest(webEnvironment = RANDOM_PORT)` with a real HTTP client, send a Basic/Bearer token, session cookie, or valid login to authenticate requests.

## 10. Testing Persistence Differs from Testing the Holder

Merely doing:

~~~java
SecurityContextHolder.setContext(context);
assertNotNull(SecurityContextHolder.getContext().getAuthentication());
~~~

does not prove the next request is authenticated. With stateful sessions, you need:

~~~text
Request A: Login
    verify credential
    set context in holder
    saveContext via repository
    response Set-Cookie/redirect

Request B: GET /dashboard with the same valid session
    filter loads context from repository
    controller receives the right principal
    filter clears thread after request

Request C: GET /dashboard without session/token
    must not receive A's principal
~~~

Repositories:

| Repository | Semantics | Testing |
| --- | --- | --- |
| `HttpSessionSecurityContextRepository` | Context tied to `HttpSession` | Request B with same session sees `Authentication` |
| `RequestAttributeSecurityContextRepository` | Per-request context across certain dispatches | Creates no long-lived login session |
| `DelegatingSecurityContextRepository` | Combines multiple load/save stores | Proper repository ordering and context |
| `NullSecurityContextRepository` | Does not persist auth across requests | Without token/session, next request is anonymous |

Unit tests for a custom auth filter can mock the repository to verify `saveContext(...)`:

~~~java
verify(repository).saveContext(
        argThat(ctx -> ctx.getAuthentication() != null
                && "alice".equals(ctx.getAuthentication().getName())),
        same(request),
        same(response));
~~~

This is a **Mockito fragment**, not a standalone JUnit class. It checks that the save API was invoked, not that `HttpSession` cookies work. Integration tests must extract the cookie/session from the login response, make another request, and confirm logout/invalid sessions no longer grant access.

If logout only calls `SecurityContextHolder.clearContext()` while `HttpSession` still holds the `Authentication`, the next request may load that context back. Use Spring Security logout handlers/DSL to clear and invalidate the session/repository per policy. For stateless Bearer tokens, clearing `HttpSession` does not automatically revoke the token.

## 11. Thread Pools Differ from Servlet Threads

Servlet request has Alice in `ThreadLocal`:

~~~text
Request thread has Alice
       |
       +---- executor.submit(task)
                         |
                         v
                  Separate worker thread
                  ThreadLocal does not automatically have Alice
~~~

When a task moves to another thread, Spring Security does not automatically propagate `SecurityContextHolder` across arbitrary application-created executors. If a worker was dirtied by a previous task that failed to clean up, a new task can observe an **unrelated** principal.

**Never use `MODE_INHERITABLETHREADLOCAL` to fix thread pools.** Inherited context only applies when a thread is created; pooled threads are long-lived and can retain stale identities. `MODE_GLOBAL` is even less suitable for multi-user web servers.

Spring Security provides:

- `DelegatingSecurityContextRunnable` / `DelegatingSecurityContextCallable`;
- `DelegatingSecurityContextExecutor` / `DelegatingSecurityContextExecutorService`;
- `DelegatingSecurityContextAsyncTaskExecutor` for certain Spring `@Async` setups.

The wrapper sets the right context for the task, then restores/clears it when the task finishes. Crucially, propagation happens at **submission time** or uses a specific context passed at construction, depending on the constructor; know clearly who is authorized to run background tasks.

## 12. JUnit Testing Context Propagation and Cleanup on Workers

This test uses a single backing thread so the subsequent task proves cleanup from the preceding task.

File **DelegatingExecutorSecurityTest.java**:

~~~java
package demo.security;

import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.concurrent.DelegatingSecurityContextExecutor;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.junit.jupiter.api.Assertions.*;

class DelegatingExecutorSecurityTest {

    @AfterEach
    void cleanupCaller() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void propagatesToTaskAndCleansBackingThread() throws Exception {
        ExecutorService backing = Executors.newSingleThreadExecutor();
        try {
            Authentication alice = new UsernamePasswordAuthenticationToken(
                    "alice", null, List.of());
            SecurityContext ctx = SecurityContextHolder.createEmptyContext();
            ctx.setAuthentication(alice);
            SecurityContextHolder.setContext(ctx);

            var wrapped = new DelegatingSecurityContextExecutor(backing);
            var observed = new java.util.concurrent.CompletableFuture<String>();

            wrapped.execute(() -> {
                Authentication inside =
                        SecurityContextHolder.getContext().getAuthentication();
                observed.complete(inside.getName());
            });

            assertEquals("alice", observed.get(3, TimeUnit.SECONDS));

            // Without wrapper: subsequent task must not receive Alice.
            Future<Authentication> next = backing.submit(() ->
                    SecurityContextHolder.getContext().getAuthentication());
            assertNull(next.get(3, TimeUnit.SECONDS));
        } finally {
            backing.shutdownNow();
        }
    }
}
~~~

This is a Spring Security Core/JUnit 5 test. With a single worker, the second task runs only after the first wrapped task completes and cleans up. Using a multi-worker pool without proving both tasks ran on the **same thread** can let a cleanup test pass falsely.

Add a test where the delegate throws an exception: confirm the wrapper still clears context. When catching errors inside tasks, never accidentally swallow failures or ignore `Future.get()` on a failing task.

Never create a new executor per HTTP request in production; manage shared executors and wrappers through Spring's lifecycle.

## 13. @Async, Callable, CompletableFuture: Testing Real Integration Mechanisms

| Execution style | Support level to verify |
| --- | --- |
| Framework-managed Spring MVC `Callable` | Spring Security integrates async; test propagation and dispatch |
| Servlet `AsyncContext.start(Runnable)` via framework | Test context during callback execution and cleanup |
| `@Async` with custom `TaskExecutor` | Configure/decorate executor to carry context per policy |
| `CompletableFuture.supplyAsync` common pool | Does not automatically inherit Servlet `ThreadLocal` |
| Raw `Thread` | Does not automatically carry the right `Authentication` |
| Background queue / scheduled task | Use service/workload identity or controlled delegation, never inherit the latest user |

Never blindly copy an HTTP request's principal onto a long-running job: the user may log out or lose permissions before the job runs. If a job acts on a user's behalf, require explicit delegation policies, expiration, scopes, tenant checks, and re-verification of resources as needed.

An `@Async` test must assert **inside the task** that the principal is right, and afterward verify the pool worker no longer holds the principal. Asserting on the caller thread alone is insufficient.

## 14. Reactor/WebFlux: Reading SecurityContext Inside a Subscription

WebFlux must not use `SecurityContextHolder.getContext()` in a reactive service to determine the user. Reactor Context belongs to the Publisher/subscription chain, not necessarily to a thread.

Code snippet:

~~~java
Mono<String> currentPrincipalName() {
    return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication().getName())
            .defaultIfEmpty("anonymous");
}
~~~

Providing context in a test chain:

~~~java
Authentication alice = new UsernamePasswordAuthenticationToken(
        "alice", null, List.of());

Mono<String> result = currentPrincipalName()
        .contextWrite(ReactiveSecurityContextHolder.withAuthentication(alice));

StepVerifier.create(result)
        .expectNext("alice")
        .verifyComplete();
~~~

This snippet uses Reactor + Spring Security Reactive + reactor-test; imports are required in the test class. Never set `ThreadLocal` on the JUnit thread to fake Reactor identity.

### JUnit test for WebFlux context isolation

File **ReactiveSecurityContextBoundaryTest.java**:

~~~java
package demo.security;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveSecurityContextBoundaryTest {

    private Mono<String> currentName() {
        return ReactiveSecurityContextHolder.getContext()
                .map(ctx -> ctx.getAuthentication().getName())
                .defaultIfEmpty("anonymous");
    }

    @Test
    void contextsAreScopedToReactiveSubscriptions() {
        Authentication alice = new UsernamePasswordAuthenticationToken(
                "alice", null, List.of());
        Authentication bob = new UsernamePasswordAuthenticationToken(
                "bob", null, List.of());

        StepVerifier.create(currentName().contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(alice)))
                .expectNext("alice")
                .verifyComplete();

        StepVerifier.create(currentName().contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(bob)))
                .expectNext("bob")
                .verifyComplete();

        StepVerifier.create(currentName())
                .expectNext("anonymous")
                .verifyComplete();
    }
}
~~~

This is a JUnit test in a project with `spring-security-core`, `reactor-core`, and `reactor-test`. It tests three independent subscriptions, **not** the WebFlux filter chain or token validation.

In Reactor, never call `SecurityContextHolder.clearContext()` at the end of every operator to "clean up" reactive identity: that operates on an unrelated `ThreadLocal`. Context normally tracks subscription lifecycle. For errors/cancellations, test side effects and framework context propagation; never store mutable per-user context in singletons.

Never call `block()` on the WebFlux request event loop to read `Authentication`, as it can block threads or break composition. Keep composing with `Mono`/`Flux`.

## 15. WebTestClient Testing Reactive Requests

With a WebFlux controller protecting `GET /whoami`, setup:

~~~java
WebTestClient client = WebTestClient
        .bindToApplicationContext(context)
        .apply(SecurityMockServerConfigurers.springSecurity())
        .configureClient()
        .build();
~~~

This snippet needs a Spring reactive `ApplicationContext` and `WebTestClient`. Using the test mutator:

~~~java
client.mutateWith(mockUser("alice").roles("USER"))
        .get().uri("/whoami")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("alice");

client.get().uri("/whoami")
        .exchange()
        .expectStatus().isUnauthorized();
~~~

`mockUser` here is WebFlux's `SecurityMockServerConfigurers.mockUser` API, not Servlet's `SecurityMockMvcRequestPostProcessors.user`. Status 401 is expected when `SecurityWebFilterChain` uses HTTP Basic or a 401 entry point; form login may redirect.

This tests **two exchanges**, not `WebSession` persistence. To test user sessions, send the server-issued cookie across exchanges and verify `ServerSecurityContextRepository`/`WebSession` per design.

**Real full HTTP:** placing `@WithMockUser` on the JUnit thread does not prove a network request to the server was authenticated; send real credentials/cookies or test via `WebTestClient` with properly integrated mock security support.

## 16. Async Errors, Cancellation, and Test Isolation

Systems typically have multiple failure boundaries:

- Servlet controller throws `RuntimeException`;
- `AuthenticationProvider` throws `AuthenticationException`;
- Filter returns 401/403 without calling the controller;
- Worker `Future` throws an exception before completion;
- Reactive `Mono`/`Flux` emits an error or the client cancels the subscription;
- `ERROR`/`ASYNC` request dispatches execute at a different time.

Verify no context leaks after **every termination path**. In Servlet chains, framework filters/holder strategies must clean up; in manually set workers, wrappers/`finally` clean up; in Reactor, Context stays scoped to the subscription and resource cleanup follows the framework.

Do not check `getContext() == null` on the JUnit thread and infer that the servlet worker or Netty event loop was cleaned up. Measure at the **actual execution boundary**. For reusable workers, use a single-thread executor or test instrumentation to compare on the same thread.

Also, do not disable all parallel test execution to hide static holder configuration leaks. If a test calls `SecurityContextHolder.setStrategyName()`, isolate the environment and restore the original strategy because that is a JVM-global setting.

## 17. Method Security, Authorities, and Resource Checks

A `@WithMockUser(roles="ADMIN")` test can verify authorization on a Spring-proxied method. However, method security must be enabled and the call must go **through the Spring bean/proxy**, never via `new Service()` or self-invocation bypassing the proxy.

The test suite needs:

1. Users with valid roles are permitted to call.
2. Users lacking permissions are rejected (typically `AccessDeniedException` or web 403).
3. Anonymous callers are never silently treated as logged-in users.
4. Authorities are not mutated by concurrent requests.
5. Context inside async methods comes from the right caller/policy.
6. Reactive method security uses Reactor Context and appropriate Publisher APIs.

A passing `@WithMockUser` test proves only **authorization under a mocked `Authentication`**; it does not prove passwords/OIDC/SAML were actually verified.

## 18. Test Matrix Across the Three Models

| Case | Expected outcome |
| --- | --- |
| Unit sets Alice on holder | Reads Alice on the same thread |
| After `clearContext` | Null `Authentication` in new context |
| Exception before cleanup | `finally`/`@AfterEach` still cleans up |
| `MockMvc` request as Alice | Controller sees Alice |
| Next anonymous `MockMvc` request | Does not see Alice |
| Stateful login + valid session cookie | Subsequent request reloads Alice from repository |
| Stateless API request without token | Must not retain previous request's `Authentication` |
| Custom login filter sets holder without saving | Does not persist automatically to next request |
| Session logout | Old cookie/session no longer grants access |
| Thread pool Alice task then unwrapped task | Subsequent task does not see Alice |
| `DelegatingSecurityContextExecutor` | Task receives context captured at submit time |
| Wrapped task throws exception | Worker is cleaned up |
| Multi-worker thread pool | Do not assume "same thread" without verifying |
| `@WithMockUser` fixture | Test listener cleans up per lifecycle |
| Real HTTP with `@WithMockUser` | Mock user does not cross TCP automatically |
| WebFlux Alice/Bob/anonymous subscriptions | No identity mix-up |
| Reactor error/cancel | Does not leak principal to another subscription |
| Method security with `@PreAuthorize` | Enforces authorities through Spring proxy |
| Concurrent requests sharing session | Avoid mutating shared mutable context |
| Cookie/request after session rotation | Identity matches right account, not stale user |

Never test only "`SecurityContext != null`". Good tests answer **who**, **where**, **when**, **whether it persists across requests**, and **whether it was cleared upon completion**.

## 19. Common Mistakes and How to Fix Them

| Symptom | Cause | Fix |
| --- | --- | --- |
| Isolated test passes, suite fails | Previous test did not clear context | `@AfterEach`, `TestSecurityContextHolder` cleanup |
| Bob sees Alice's `Authentication` | Thread pool missing cleanup | `finally`/wrapper at worker boundary |
| Async worker lacks principal | Missing propagation | `DelegatingSecurityContextExecutor`/`AsyncTaskExecutor` |
| `MODE_INHERITABLETHREADLOCAL` shows wrong user | Pool reuses old threads | Do not use inheritance for pool propagation |
| Login succeeds, next request anonymous | Forgot `saveContext` | Explicit save before response commits |
| Stateless API retains auth on next request | Wrong session/repository policy | Use per-request credentials and appropriate repo |
| Logout yet still logged in | Cleared only `ThreadLocal` | Clear repository/invalidate session or revoke token |
| `MockMvc` fakes auth yet filter chain skipped | Missing `springSecurity()` | Attach `FilterChainProxy` |
| `@WithMockUser` ineffective on real HTTP | Server thread differs from JUnit thread | Send HTTP credentials/cookies |
| Test role `USER` lacks permission | `roles()` prepends `ROLE_USER` | Align `hasRole`/`hasAuthority` |
| `assertNull(getContext())` fails | Holder creates empty context | Assert `Authentication` is null |
| Reactive misses principal | Reads `ThreadLocal` | Use `ReactiveSecurityContextHolder` |
| `block()` stalls WebFlux | Blocks event loop | Compose `Mono`/`Flux` |
| Anonymous token treated as real login | Misunderstood `isAuthenticated` | `TrustResolver`/authorization framework |
| Shared `SecurityContext` cross-mutated | Mutable session object shared | `createEmptyContext` and concurrency control |
| Context leak appears only on errors | Cleanup missing in `finally` | Test exceptions/errors/cancellations |

## 20. Implementation Checklist

1. Did you identify whether code runs on a Servlet thread, executor worker, WebFlux subscription, or real HTTP test?
2. Does `Authentication` come from a real provider, mock fixture, session, or Bearer token?
3. Do you create a new context before writing to the proper holder/Reactor Context?
4. Do tests assert principal and authorities rather than merely checking context non-null?
5. Does cleanup happen at the exact boundary including exceptions/cancellations?
6. When passing to an executor, does the wrapper run at the right point and clean the worker afterward?
7. If sessions are needed, is there an explicit save via `SecurityContextRepository` and a next-request test?
8. If stateless, are requests missing tokens rejected?
9. Do `MockMvc`/`WebTestClient` attach the real security filters/`WebFilterChain`?
10. Are Alice → Bob → anonymous, logout, session rotation, and concurrent access tested?
11. Are credentials kept out of logs, test fixtures, and shared objects?
12. Do the `SecurityContextHolderFilter` version and test setup match your actual dependencies?

**Conclusion:** Testing `SecurityContext` properly is not just `setContext` and `getContext`. In Servlet, context is bound to the request thread and cleared, while repository persistence is separate. In executors, propagation and worker cleanup are required. In WebFlux, context belongs to the Reactor subscription. Separating and testing each boundary individually prevents two opposite bugs: **dropping valid `Authentication`** and **leaking identity across tasks or users**.

### References

- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — Persisting Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html
- Spring Security — Session Management / Require Explicit Save: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — Concurrency Support: https://docs.spring.io/spring-security/reference/features/integrations/concurrency.html
- Spring Security — MockMvc Testing Authentication: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html
- Spring Security — Testing Method Security: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Security — TestSecurityContextHolder API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/TestSecurityContextHolder.html
- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security — WebTestClient Authentication: https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html
- Spring Security — WebTestClient Setup: https://docs.spring.io/spring-security/reference/7.0/reactive/test/web/setup.html

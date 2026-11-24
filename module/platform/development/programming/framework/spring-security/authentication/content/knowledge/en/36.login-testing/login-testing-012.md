# Parallel Testing and Verifying Zero Cross-User Identity Leakage

## 1. Goal and context

A successful login in one request does not prove the system is safe when **multiple users log in or send requests concurrently**. A Java service typically handles hundreds of requests across a thread pool, maintains sessions for multiple browsers, invokes `@Async` tasks, sends messages, or uses Reactor in WebFlux. If user identity is stored in **shared variables**, an uncleaned `ThreadLocal`, a shared `SecurityContext`, or an improperly keyed authorization cache, user A's request can observe user B's `principal`, data, or privileges.

This Knowledge lesson focuses on **parallel login testing and identity isolation** in Spring Security. After this lesson, you can:

1. Express and test the invariant **"each request belonging to an account uses strictly that account's identity/authorities"**.
2. Distinguish leaks across **threads**, **sessions/cookies**, **HTTP caches**, **data authorization**, **async tasks**, and **reactive contexts**.
3. Understand how Spring Security Servlet uses `SecurityContextHolder`, `SecurityContext`, `Authentication`, `SecurityContextRepository`, and context cleanup.
4. Write Java 17 and JUnit 5 parallel tests using `ExecutorService`, `CountDownLatch`, `CyclicBarrier`, and `Future` **without relying on arbitrary sleeps**.
5. Build a Spring Boot 3.x + Spring Security 6.x demo with two/three users, run **truly parallel HTTP requests**, and assert exact principals, authorities, and 401/403 responses.
6. Design session-form-login tests with **separate cookie jars**, CSRF, and session fixation protection; never confuse single-account session limits with two-account isolation.
7. Test `@Async`, `DelegatingSecurityContextCallable`/executors, and Reactive `ReactiveSecurityContextHolder` without copying A's `SecurityContext` to B.
8. Build a regression test matrix for tenant/data ownership, logout, Bearer tokens, role changes, and multi-node systems.

**Scope:** centered on Spring Security 6.5 / Spring Boot 3.x, Java 17+ for Servlet Spring MVC; distinguishes Spring Security 7.x and WebFlux. Component examples are explicitly marked as standalone runnable or snippets to place into a project.

## 2. What does "cross-user identity leakage" include?

**Cross-user identity leakage** occurs when one principal's request or job mistakenly receives identity, permissions, or data belonging to another principal. This may surface only under concurrent load when the server reuses threads, sessions, or objects.

Example:

```text
Time                 Request A / Alice                 Request B / Bob
   t0                Authentication = Alice            Authentication = Bob
   t1                reads /api/me                     reads /api/me
   t2                expects Alice                     expects Bob
   t3                actual Alice                      actual Alice  <-- LEAK
```

Or more subtly:

```text
A (ROLE_USER) -> GET /api/orders/1001 -> A's order
B (ROLE_USER) -> GET /api/orders/2002 -> B's order

B sends GET /api/orders/1001:
- B may still see `principal=bob` accurately;
- Yet the API returns Alice's order due to missing owner check.
```

The second case is **data/object-level authorization leakage (IDOR/BOLA)** rather than necessarily a `SecurityContextHolder` bug. Good tests must detect **both principal leaks and data leaks**.

Other forms:

| Failure mode | Symptom | Common cause |
| --- | --- | --- |
| Principal leak | Bob's `/api/me` returns `alice` | Static field/`currentUser` singleton, shared context |
| Authority leak | Bob receives Alice's `ROLE_ADMIN` | Mutable authorities list/cache not keyed by user |
| Session leak | Browser B sees A's session | Shared cookie jar, wrong session ID, buggy custom repository |
| Async leak | Bob's background job runs under account A | Context propagated from another user or uncleaned thread pool |
| Cross-tenant leak | Bob in tenant B sees tenant A's profile | Cache/repository key missing tenant, unscoped query |
| Object leak | Alice reads Bob's order despite right principal | Missing object-level authorization |
| Response cache leak | A's private response served to B | HTTP/CDN cache lacking proper Vary/private/no-store |
| Audit leak | A's event records actor B | Mutable actor singleton, wrong context in job |
| Resource Server leak | Claims/authorities from JWT A applied to B | Converter cache not keyed by token/subject/issuer |
| Test contamination | Test B pass/fail depends on test A | `SecurityContextHolder`/global strategy/static test fixtures |

**Key takeaway:** you cannot just assert both logins receive 200. Assert **exact identity, authorities, ownership, and independent traces** on every request.

## 3. Invariants that must hold

Let `principal(request)` be the authenticated user for a specific request and `grants(request)` be the server-verified authorities. We require:

1. **Identity correctness:** `principal(A) == Alice`, `principal(B) == Bob`, never swapped even under simultaneous execution.
2. **No unauthenticated inheritance:** requests without valid credentials/sessions **must not** inherit the Authentication of the previous request handled on the same worker thread.
3. **Authority isolation:** A's authorities are never merged into or retained on B's Authentication.
4. **Resource ownership:** object access checks `owner`/tenant or equivalent policy, not just `isAuthenticated()`.
5. **Session boundary:** A's cookie/session cannot become B's session via caching, context storage, or misrouted responses.
6. **Context lifetime:** context lives only for the exact request/task and is cleared/restored afterward.
7. **Async ownership:** if a job must run under its caller's identity, context must be **propagated in a controlled way** from that request and cleared after the job. If the job is a system task, use a dedicated service identity rather than inheriting arbitrarily.
8. **Credential secrecy:** responses/audits never contain raw passwords, access tokens, cookies, OTPs, or another user's secrets.
9. **Failure isolation:** B's wrong password never makes A's request anonymous, never invalidates A's session, and never lets B use A's context.
10. **Revocation semantics:** after logout, user disablement, or role change, new requests obey revocation/TTL policies; never assume old sessions auto-update immediately without explicit implementation.

This invariant must be tested with **different actors**. Two requests from the same user are not enough to verify cross-user identity swapping between A and B.

## 4. Why are Java servers prone to concurrency bugs?

Sources of shared state in Spring Boot:

- `@Service`, `@Component`, `@Controller` are **singleton beans** by default. If a class has a mutable `currentUsername` field, concurrent requests can overwrite it.
- Servlet containers use a **thread pool**. A thread serving Alice now serves Bob or an anonymous request next.
- `SecurityContextHolder` uses **ThreadLocal** by default, yet application code might switch strategies or declare its own ThreadLocal and forget to clear it.
- `HttpSession` binds browsers/clients via session cookies, not IP address or open tabs.
- `SecurityContext` holds an `Authentication` object that could be shared if an app reuses instances across requests.
- Executors/`@Async` run on different threads and **do not automatically inherit** the originating request's context without proper bridging.
- WebFlux continues a single request across threads, so `ThreadLocal` is not the primary place to read Authentication; Spring Security uses **Reactor Context**.
- Application caches may key response/permission data too broadly, e.g., `profile` instead of `tenantId:userId:profile`.

### Anti-pattern: current user in a singleton service

```java
// WRONG: mutable field inside a singleton bean can be overwritten by other requests.
@Service
public class UnsafeIdentityService {
    private String currentUser;

    public void setUser(String username) {
        this.currentUser = username;
    }

    public String currentUser() {
        return currentUser;
    }
}
```

If A calls `setUser("alice")`, B calls `setUser("bob")`, and A then reads `currentUser`, A may see `bob`. `volatile` only ensures visibility; it **does not** turn a shared field into per-request identity storage. `synchronized` also does not fix storing a single shared principal.

**Right:** read `Authentication`/`Principal` from **the current request**, and pass the explicit identifier into services that need it, e.g.:

```java
@GetMapping("/api/me")
public String me(Authentication authentication) {
    return authentication.getName();
}
```

This is a **snippet inside a Spring MVC controller** on an authenticated request. Never accept a client-supplied `username` and treat it as the current user.

## 5. `SecurityContextHolder` in Servlet: ThreadLocal, not a session

Per Spring Security Servlet:

```text
HTTP request A (JSESSIONID=...)
  |
  v
FilterChainProxy / SecurityContextHolderFilter
  |
  +-- Load SecurityContext from SecurityContextRepository
  |     or from the matching auth filter
  |
  +-- Current Authentication = Alice
  |
  +-- Controller/service (request thread)
  |
  v
Clear SecurityContextHolder when request finishes

Worker thread may be reused for HTTP request B:
  |
  +-- Load B's Authentication or anonymous
  +-- Must not inherit Alice from stale ThreadLocal
```

`SecurityContextHolder` stores `SecurityContext` for **the current thread** under the default `MODE_THREADLOCAL` strategy. `SecurityContext` holds `Authentication`: principal, credentials (typically erased after login), and authorities.

Spring Security's `FilterChainProxy` is responsible for clearing the context when the request finishes. This **does not** guarantee that custom ThreadLocals or self-managed executors in your app are also cleared.

**A detail emphasized by Spring Security docs:** when setting Authentication manually, create a **new** `SecurityContext`:

```java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
```

Rather than mutating in place:

```java
// Not recommended when the context could be shared:
SecurityContextHolder.getContext().setAuthentication(authentication);
```

Because an existing `SecurityContext` could be shared, causing races and identity swaps. Never use `SecurityContextHolder.MODE_GLOBAL` in a multi-user web app; `MODE_INHERITABLETHREADLOCAL` is not a general solution for thread pools, because a reused pooled thread is not a fresh child thread spawned per request.

### SecurityContextRepository is not a ThreadLocal itself

`SecurityContextRepository` saves and restores context across requests; e.g., `HttpSessionSecurityContextRepository` uses sessions for browser login, while `RequestAttributeSecurityContextRepository` is request-scoped. In Spring Security 6.x, when **writing a custom login filter/controller** that creates an Authentication, you must save the context via `SecurityContextRepository.saveContext(...)` to persist the session. Calling only `SecurityContextHolder.setContext(...)` in a custom controller does not automatically restore the user on subsequent requests.

Leak bugs rarely lie in one isolated `setContext` line; they appear when the app uses **one shared SecurityContext** across sessions, or saves A's context into B's session/cookie.

## 6. Separating concurrency by layer

"Running in parallel" can mean at least five things:

| Execution pattern | Example | What to assert |
| --- | --- | --- |
| Concurrent requests | A and B GET `/api/me` simultaneously | A remains A, B remains B |
| Sequential reuse of thread | Worker finishes A, then handles B | B does not read A's ThreadLocal |
| Concurrent logins | A and B POST `/login` simultaneously from separate browsers | A's and B's sessions/cookies never swap |
| Concurrent operations in one session | Two tabs of **the same browser** send requests | Session and login/logout semantics hold; never treat two tabs as two sessions |
| Async/background work | A and B submit jobs to an executor | Each job uses the exact identity issued to it |
| Distributed concurrency | A/B across two app nodes, Redis/shared sessions | Keys/caches/sessions isolated across users |
| Reactive interleaving | Two `Mono`s interleaved on an event loop | Each subscription's Reactor Context stays independent |

Tests running two users **sequentially** can miss races on shared mutable fields. Conversely, concurrent tests where requests share the same cookie jar can swap users because **the test itself shared the client/session**, not due to a server bug. Control both the server and the test harness.

## 7. Designing unambiguous test data

Use fixtures with distinct principals, roles, and data, **never real accounts**:

| Account | Authorities | Valid resources | Must be blocked from |
| --- | --- | --- | --- |
| `alice` | `ROLE_USER` | `profile-alice`, `order-A1` | `profile-bob`, `order-B1`, admin |
| `bob` | `ROLE_AUDITOR` | `profile-bob`, `order-B1` | `profile-alice`, `order-A1`, admin |
| `carol` | `ROLE_ADMIN` | `profile-carol`, `/api/admin` | A/B's private data unless admin is explicitly authorized |
| Anonymous | No user roles | Public endpoints | `/api/me`, `/api/admin`, private objects |

**Never assume `ROLE_ADMIN` means permission to view all tenant data.** Admin role and resource ownership are two potentially independent control dimensions.

A test should inspect:
- `Authentication.getName()` on **every request**.
- `Authentication.getAuthorities()` against **the exact authority set**; asserting only `ROLE_USER` present misses a leaked `ROLE_ADMIN`.
- Resource body contains `ownerId` for the right person/tenant, never returning B's private data to A.
- Matching HTTP status/redirects/cookies, including 401/403/404 per policy.
- Separate session/cookie jars per browser actor.
- Audit actor and correlation ID; never log secrets for verification.

In parallel login tests, misbinding a shared `requestId` or `TraceId` can also cause audits to record the wrong identity even when the client response happens to be right.

## 8. Pure JDK Java 17: ThreadLocal isolation demo

This is a **standalone runnable** program requiring no Spring. It runs two concurrent threads synchronized with `CyclicBarrier`, then intentionally reuses the pool to verify the context was cleared.

File `ParallelIdentityIsolationDemo.java`:

```java
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ParallelIdentityIsolationDemo {

    private static final ThreadLocal<String> CURRENT_USER =
        new ThreadLocal<>();

    private static Callable<String> request(
            String user, CyclicBarrier overlap) {
        return () -> {
            try {
                CURRENT_USER.set(user);
                overlap.await(5, TimeUnit.SECONDS);
                return CURRENT_USER.get();
            } finally {
                CURRENT_USER.remove();
            }
        };
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            CyclicBarrier overlap = new CyclicBarrier(2);
            Future<String> a = pool.submit(request("alice", overlap));
            Future<String> b = pool.submit(request("bob", overlap));

            boolean aliceOk = "alice".equals(a.get(10, TimeUnit.SECONDS));
            boolean bobOk = "bob".equals(b.get(10, TimeUnit.SECONDS));

            // Subsequent two tasks must not inherit identity from prior tasks.
            Future<Boolean> cleanA = pool.submit(
                () -> CURRENT_USER.get() == null
            );
            Future<Boolean> cleanB = pool.submit(
                () -> CURRENT_USER.get() == null
            );

            System.out.println("alice-isolated=" + aliceOk);
            System.out.println("bob-isolated=" + bobOk);
            System.out.println(
                "no-stale-context="
                    + (cleanA.get(10, TimeUnit.SECONDS)
                       && cleanB.get(10, TimeUnit.SECONDS))
            );
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Run:

```bash
javac ParallelIdentityIsolationDemo.java
java ParallelIdentityIsolationDemo
```

**stdout when both tasks execute normally:**

```text
alice-isolated=true
bob-isolated=true
no-stale-context=true
```

This is the logically expected output; if the environment stalls past the 5-second wait limit, it throws an exception instead of printing `false`, so use reasonable timeouts in CI.

**Explanation:**
- `ThreadLocal` separates values by thread, **not** by user/session.
- `CyclicBarrier(2)` ensures A and B reach the rendezvous before reading identity; avoids a "parallel" test that actually runs sequentially.
- `try/finally` calls `CURRENT_USER.remove()` so the thread pool does not retain the prior task's identity.
- `Future.get(...)` propagates worker errors back to the test thread instead of swallowing exceptions.
- Subsequent tasks verify the pool **does not reuse old users**.

**Limitation:** this program is not `SecurityContextHolder` and does not verify the servlet filter chain, sessions, cookies, or object permissions. It only demonstrates the nature of thread-local context and coordinated testing.

## 9. JUnit 5: really testing `SecurityContextHolder` across two threads

In a Gradle project using Spring Boot 3.x + Spring Security 6.x:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Create file `src/test/java/example/isolation/SecurityContextIsolationTest.java`:

```java
package example.isolation;

import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SecurityContextIsolationTest {

    private SecurityContext contextFor(String username) {
        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(
            new TestingAuthenticationToken(
                username, "fixture-only", "ROLE_USER"
            )
        );
        return context;
    }

    private Callable<String> task(
            String username,
            CountDownLatch entered,
            CountDownLatch release) {
        return () -> {
            SecurityContextHolder.setContext(contextFor(username));
            try {
                entered.countDown();
                if (!release.await(10, TimeUnit.SECONDS)) {
                    throw new AssertionError("Test did not release tasks");
                }
                return SecurityContextHolder.getContext()
                    .getAuthentication().getName();
            } finally {
                SecurityContextHolder.clearContext();
            }
        };
    }

    @Test
    void parallelWorkersKeepDifferentPrincipals() throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch entered = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<String> a =
                pool.submit(task("alice", entered, release));
            Future<String> b =
                pool.submit(task("bob", entered, release));

            assertTrue(entered.await(10, TimeUnit.SECONDS));
            release.countDown();

            assertEquals("alice", a.get(15, TimeUnit.SECONDS));
            assertEquals("bob", b.get(15, TimeUnit.SECONDS));

            // Reused thread pool: no stale principal remains.
            Future<Boolean> cleared = pool.submit(
                () -> SecurityContextHolder
                    .getContext().getAuthentication() == null
            );
            assertTrue(cleared.get(15, TimeUnit.SECONDS));
        } finally {
            release.countDown();
            pool.shutdownNow();
            SecurityContextHolder.clearContext();
        }
    }

    @Test
    void newContextIsNotTheSameInstanceAsAnotherUsers() {
        SecurityContext alice = contextFor("alice");
        SecurityContext bob = contextFor("bob");

        assertTrue(alice != bob);
        assertEquals("alice", alice.getAuthentication().getName());
        assertEquals("bob", bob.getAuthentication().getName());
    }
}
```

Run:

```bash
./gradlew test --tests example.isolation.SecurityContextIsolationTest
```

**Testing significance:**
- Both tasks intentionally wait on each other, genuinely triggering race/overlap at the test layer.
- Each task builds a **separate** `SecurityContext` without mutating `Authentication` inside another thread's context.
- `clearContext()` runs in `finally` even if an assertion throws.
- Pool-reuse task verifies no old principal remains.
- Never switch `SecurityContextHolder` to `MODE_GLOBAL`/`MODE_INHERITABLETHREADLOCAL` at the JVM level inside tests; such settings can affect other tests running in the same process.

**Scope:** this is a **component-level concurrency test** and does not prove `HttpSessionSecurityContextRepository` binds contexts to the right browser sessions. That is why the HTTP integration test in section 12 is still needed.

### One thing to avoid in assertions

Do not build `Authentication` in tests via:

```java
// WRONG in production: never verifies credentials.
UsernamePasswordAuthenticationToken.authenticated(
    "alice", null, someAuthorities
);
```

This token works as a fixture in pure authorization unit tests, yet is not proof a real login verified passwords/OTPs. Section 9 tests only **holder** isolation, not password verification.

## 10. Asynchronous tasks: prevent A's context from appearing in B

With `SecurityContextHolder.MODE_THREADLOCAL`, a task running on another thread normally **does not automatically have** the originating request's Authentication. If app code requires a task to run under the caller's identity, Spring Security provides:

- `DelegatingSecurityContextRunnable`
- `DelegatingSecurityContextCallable`
- `DelegatingSecurityContextExecutor`
- `DelegatingSecurityContextExecutorService`
- Corresponding wrappers/schedulers in concurrency support

`DelegatingSecurityContextCallable` takes **a specific context** or captures the current context when the wrapper is created, sets the context for the callable, and **restores/clears it afterward**. Thus one pool can serve A's job then B's job without mixing identities, provided each job uses its own proper context.

### JUnit test reusing the same worker thread

Create `src/test/java/example/isolation/DelegatingContextTest.java`:

```java
package example.isolation;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.concurrent.DelegatingSecurityContextCallable;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class DelegatingContextTest {

    private SecurityContext contextFor(String user) {
        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(
            new TestingAuthenticationToken(user, "fixture-only", "ROLE_USER")
        );
        return context;
    }

    @Test
    void onePooledThreadHandlesAliceThenBobWithoutLeak()
            throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            var aliceTask = new DelegatingSecurityContextCallable<>(
                () -> SecurityContextHolder.getContext()
                    .getAuthentication().getName(),
                contextFor("alice")
            );

            var bobTask = new DelegatingSecurityContextCallable<>(
                () -> SecurityContextHolder.getContext()
                    .getAuthentication().getName(),
                contextFor("bob")
            );

            assertEquals("alice",
                pool.submit(aliceTask).get(10, TimeUnit.SECONDS));
            assertEquals("bob",
                pool.submit(bobTask).get(10, TimeUnit.SECONDS));

            Future<Boolean> after = pool.submit(
                () -> SecurityContextHolder
                    .getContext().getAuthentication() == null
            );
            assertEquals(true, after.get(10, TimeUnit.SECONDS));
        } finally {
            pool.shutdownNow();
            SecurityContextHolder.clearContext();
        }
    }
}
```

**Why use a single worker thread?** If there is a context-retention bug, Bob's task and the final check are guaranteed to hit **the exact reused thread**. Using multiple threads where the scheduler happens to pick a different thread can cause a false negative in the test.

### When is `DelegatingSecurityContextExecutorService` appropriate?

Example when real code has a shared `ExecutorService`:

```java
ExecutorService raw = Executors.newFixedThreadPool(4);
ExecutorService secured =
    new DelegatingSecurityContextExecutorService(raw);
```

This is a **snippet** inside the class owning the executor lifecycle. The wrapper captures context cleanly when submitting tasks from a request that has a security context. When finished, shut down the executor per the application-managed lifecycle; never create a new pool per request.

Warning about the constructor overload taking a fixed `SecurityContext`:

```java
// DO NOT use a fixed Alice context for different users.
new DelegatingSecurityContextExecutorService(raw, aliceContext);
```

If the wrapper is configured with a **fixed** context, every task submitted through that wrapper may run under Alice's identity. This is an intentional feature for a **service account** in certain workflows, not a configuration to use for multi-user requests.

If a job is a **system task**, prefer granting a constrained service principal/permission and auditing its trigger source separately, rather than dragging a user's `ROLE_ADMIN` into a multi-hour background job.

## 11. Spring Boot Web MVC demo: endpoint identifying real users

A `SecurityContextHolder` component test only proves the ThreadLocal API. To verify **real login** through Spring Security, build a small REST app with stateless HTTP Basic, three accounts, and endpoints returning principal/authorities. HTTP Basic simplifies the test because **no cookies or CSRF are needed for GET**; the lesson covers form login/sessions separately in section 14.

### 11.1. Dependencies

In `build.gradle` of a Spring Boot 3.x project already having plugin/BOM/JDK 17+:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Never mix Spring Security 6.x and 7.x outside Boot's dependency management. Use JDK 17+.

### 11.2. Main class

File `src/main/java/example/isolation/ParallelAuthApplication.java`:

```java
package example.isolation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ParallelAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(ParallelAuthApplication.class, args);
    }
}
```

### 11.3. Security configuration

File `src/main/java/example/isolation/IsolationSecurityConfig.java`:

```java
package example.isolation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class IsolationSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/me").authenticated()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            );

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        // Low cost ONLY for local test suites.
        return new BCryptPasswordEncoder(4);
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice-test-only"))
                .roles("USER")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("bob-test-only"))
                .roles("AUDITOR")
                .build(),
            User.withUsername("carol")
                .password(encoder.encode("carol-test-only"))
                .roles("ADMIN")
                .build()
        );
    }
}
```

**Explanation:**

- `.httpBasic(...)` uses HTTP Basic to test login with real credentials. Each request verifies the user and builds an `Authentication` for that request.
- `.sessionCreationPolicy(STATELESS)` ensures the demo does not restore Authentication from an HTTP session; every request must carry `Authorization: Basic ...`.
- `/api/me` requires authenticated, `/api/admin` requires `ROLE_ADMIN`; an authenticated user does not automatically hold admin privileges.
- `InMemoryUserDetailsManager` is for demos only; production uses an appropriate DB/LDAP/IdP and clear cache policies.
- `BCryptPasswordEncoder(4)` uses a low cost so tests run fast and is **not** a production setting.
- Only GET routes exist in the demo; Spring Security still keeps default CSRF. When adding form login or POST/PUT/DELETE on cookie-authenticated apps, handle CSRF per policy—**never** copy a line blindly disabling CSRF.
- The demo does not enable `maximumSessions(1)` because that is a policy **limiting sessions per user**, not solving cross-user A/B isolation.

### 11.4. Controller not holding `currentUser` in a field

File `src/main/java/example/isolation/IdentityController.java`:

```java
package example.isolation;

import java.util.List;
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/api/me")
    public Map<String, Object> me(Authentication auth) {
        List<String> authorities = auth.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return Map.of(
            "username", auth.getName(),
            "authorities", authorities
        );
    }

    @GetMapping("/api/admin")
    public String admin() {
        return "admin-ok";
    }
}
```

The controller is managed by Spring as a singleton yet stores no request data in fields. `Authentication` is resolved for the current request. With real business data, do not return unnecessary sensitive attributes; `/api/me` here exists only to **test isolation**, and `/api/admin` to test role boundaries.

Run:

```bash
./gradlew bootRun
```

Illustrative requests on a local machine:

```bash
curl -i -u alice:alice-test-only http://localhost:8080/api/me
curl -i -u bob:bob-test-only http://localhost:8080/api/me
curl -i -u carol:carol-test-only http://localhost:8080/api/admin
```

**Expected result:** Alice receives `username=alice` with authorities `ROLE_USER` only; Bob receives `ROLE_AUDITOR` only; Carol gets `admin-ok` on `/api/admin`. Demo passwords are not production secrets. `curl -u` can expose test info in process lists/shell history, so never use that method for real credentials.

## 12. Spring Boot integration test: many real HTTP requests in parallel

The following test runs a **real HTTP server** on a random port (`RANDOM_PORT`), uses JDK 17's `java.net.http.HttpClient`, dispatches 30 tasks split across Alice/Bob/Carol, and compares principal plus **exact authority set** on every response.

Create `src/test/java/example/isolation/ParallelLoginHttpTest.java`:

```java
package example.isolation;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Base64;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class ParallelLoginHttpTest {

    @LocalServerPort
    int port;

    @Autowired
    ObjectMapper mapper;

    private HttpRequest request(
            String path, String username, String password) {
        String raw = username + ":" + password;
        String basic = Base64.getEncoder().encodeToString(
            raw.getBytes(StandardCharsets.UTF_8)
        );

        return HttpRequest.newBuilder()
            .uri(URI.create("http://localhost:" + port + path))
            .header("Authorization", "Basic " + basic)
            .GET()
            .build();
    }

    @Test
    void parallelAccountsNeverExchangeNamesOrAuthorities()
            throws Exception {
        HttpClient client = HttpClient.newHttpClient();

        int workers = 10;
        int requests = 30;
        ExecutorService pool = Executors.newFixedThreadPool(workers);
        CountDownLatch ready = new CountDownLatch(workers);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<Void>> futures = new ArrayList<>();

        try {
            for (int i = 0; i < requests; i++) {
                int index = i;

                futures.add(pool.submit(() -> {
                    ready.countDown();
                    if (!start.await(10, TimeUnit.SECONDS)) {
                        throw new AssertionError("Start latch timed out");
                    }

                    String user;
                    String password;
                    Set<String> expectedAuthorities;

                    switch (index % 3) {
                        case 0 -> {
                            user = "alice";
                            password = "alice-test-only";
                            expectedAuthorities = Set.of("ROLE_USER");
                        }
                        case 1 -> {
                            user = "bob";
                            password = "bob-test-only";
                            expectedAuthorities = Set.of("ROLE_AUDITOR");
                        }
                        default -> {
                            user = "carol";
                            password = "carol-test-only";
                            expectedAuthorities = Set.of("ROLE_ADMIN");
                        }
                    }

                    HttpResponse<String> me = client.send(
                        request("/api/me", user, password),
                        HttpResponse.BodyHandlers.ofString()
                    );
                    assertEquals(200, me.statusCode());

                    JsonNode json = mapper.readTree(me.body());
                    assertEquals(user, json.path("username").asText());

                    Set<String> actualAuthorities = new HashSet<>();
                    for (JsonNode authority : json.path("authorities")) {
                        actualAuthorities.add(authority.asText());
                    }
                    assertEquals(
                        expectedAuthorities, actualAuthorities
                    );

                    HttpResponse<String> admin = client.send(
                        request("/api/admin", user, password),
                        HttpResponse.BodyHandlers.ofString()
                    );
                    assertEquals(
                        "carol".equals(user) ? 200 : 403,
                        admin.statusCode()
                    );
                    if ("carol".equals(user)) {
                        assertEquals("admin-ok", admin.body());
                    }
                    return null;
                }));
            }

            assertTrue(ready.await(10, TimeUnit.SECONDS));
            start.countDown();

            for (Future<Void> future : futures) {
                future.get(60, TimeUnit.SECONDS);
            }
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }
}
```

Run:

```bash
./gradlew test --tests example.isolation.ParallelLoginHttpTest
```

**Expected per section 11 config:** all 30 tasks read the right `username` and exact authority set; `/api/admin` returns 200 only for Carol, and 403 for Alice and Bob. This is the **expected outcome from the code**, not output captured from running against a real server in this article.

### Why is this test valuable?

1. Spring Boot actually starts an **embedded HTTP server**, rather than calling controller methods directly.
2. `HttpClient` has no shared cookie store configured; the **stateless Basic** model builds separate authentication from each request's header.
3. `CountDownLatch` makes multiple workers start together; each request passes through the real security filter chain.
4. Each response is compared against the account **that sent the request** rather than checking only status 200.
5. Authorities are compared as a **full Set**, catching leaked extra roles.
6. `/api/admin` catches several kinds of role misassignment.
7. `Future.get(...)` propagates assertion failures from workers back to JUnit instead of hiding errors inside the executor.
8. With three users, races can expose singleton controllers, caches, or custom authentication code sharing state.

### What this test has NOT proven yet

- It does not use **form login** or HTTP sessions/`JSESSIONID`, so it does not test session fixation/cookie jars.
- It does not test per-object permissions belonging to an account/tenant.
- It does not test `@Async`/message brokers/WebFlux Reactor Context.
- It does not simulate multi-node distribution; the local app is a single instance.
- Passing once does not prove a race **never** happens; controlled repetition and error-path tests are needed.
- Basic credentials can still be replayed if leaked; production needs HTTPS and appropriate authentication mechanisms rather than treating the demo as a recommended auth architecture.

## 13. Choosing the right pass/fail criteria

A strong test suite does not stop at:

```java
assertEquals(200, response.statusCode());
```

Instead, it must assert the correlation:

```text
For each actor:
  - request uses that actor's credential/session/token
  - response principal == actor
  - response authority set == actor's policy
  - response private resource owner == actor or explicitly authorized grant
  - response contains no attributes/secrets belonging to another actor
  - audit event actor == actor (if auditing is in scope)
  - anonymous/invalid-token never receives stale identity
```

**Never use** a mutable static `expectedUser` overwritten across tasks as a test oracle. Keep the expected user in **each task's local variable**, as in section 12, or a per-request immutable record.

If a test runs two parallel clients and collects responses into a `List` in completion order, never assume `results[0]` belongs to Alice. Attach a test-generated **correlation ID** to the future/result and match against the corresponding actor; network completion order is non-deterministic.

## 14. Form login and HTTP sessions: isolation tests must use two separate browsers

With browser form login, authentication state is normally held in the HTTP session and the browser sends `JSESSIONID` via cookie. Two **tabs in one browser profile** normally share **the same cookie jar**, so opening two windows does not create two independent sessions. Logging in as Bob in tab B can switch tab A in the same browser to Bob — that is **same-session behavior**, not proof of an isolation leak across two independent users.

To test Alice and Bob in **two separate sessions**, use:
- Two separate browser contexts/profiles; or
- Two HTTP clients with separate cookie jars; or
- Two distinct `MockHttpSession` instances when using `MockMvc`.

### 14.1. Real flow to test

```text
Client A / CookieJar A              Client B / CookieJar B
   | GET /login / CSRF                 | GET /login / CSRF
   | POST /login alice                 | POST /login bob
   | <- Set-Cookie JSESSIONID_A        | <- Set-Cookie JSESSIONID_B
   | GET /api/me (cookie A)            | GET /api/me (cookie B)
   | <- alice                          | <- bob
   | GET /api/orders/A1                | GET /api/orders/B1
   | <- alice's data                   | <- bob's data
   | Logout A                          | B stays active
   | GET /api/me -> login/401          | GET /api/me -> bob
```

**Session fixation protection note:** after a successful form login, Spring Security can rotate the session ID. Never assert that the **pre-login** cookie must equal the **post-login** cookie. Instead, use the current cookie of each browser context.

### 14.2. MockMvc snippet for a different FORM LOGIN application

In an application **different from the stateless Basic demo in section 11**, assuming `.formLogin(withDefaults())` is enabled with two test users `alice` and `bob`, controller `/api/me`, and `MockMvc` wired with the Spring Security filter chain:

```java
// Snippet inside @Test of an app using form login and HTTP sessions.
MvcResult aliceLogin = mvc.perform(
        formLogin().user("alice").password("alice-password"))
    .andExpect(authenticated().withUsername("alice"))
    .andReturn();

MvcResult bobLogin = mvc.perform(
        formLogin().user("bob").password("bob-password"))
    .andExpect(authenticated().withUsername("bob"))
    .andReturn();

MockHttpSession sessionAlice =
    (MockHttpSession) aliceLogin.getRequest().getSession(false);
MockHttpSession sessionBob =
    (MockHttpSession) bobLogin.getRequest().getSession(false);

assertNotEquals(sessionAlice.getId(), sessionBob.getId());

mvc.perform(get("/api/me").session(sessionAlice))
   .andExpect(status().isOk())
   .andExpect(jsonPath("$.username").value("alice"));

mvc.perform(get("/api/me").session(sessionBob))
   .andExpect(status().isOk())
   .andExpect(jsonPath("$.username").value("bob"));
```

Imports needed in the test method/class:

```java
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
```

**This is a snippet, not a standalone test:** a session-based project must provide `MockMvc`, a form-login `SecurityFilterChain`, user fixtures/passwords, `/api/me`, CSRF, and the corresponding repository. Spring Security Test's `formLogin()` automatically populates a valid CSRF token per the default contract. Do not run this snippet as-is with the stateless Basic configuration from Section 11, because that application **does not enable** form login/sessions.

### 14.3. Session tests need negative cases

- A logs in successfully, B fails login: B **does not** receive A's authenticated session.
- A logs out: B remains authenticated; do not accidentally delete B's session.
- B changes password: A's principal is not changed automatically; invalidating other sessions must follow policy.
- A tries to use B's session ID: if a cookie/session is stolen, that is **session hijacking**, which requires appropriate controls/re-authentication/token binding; the server cannot be expected to always distinguish who sends a stolen cookie by physical identity.
- One browser profile logs in as Alice and then Bob sequentially: there should be proper session rotation/context clearing; do not let Alice's old authorities mix with Bob.
- When the response returns `Set-Cookie`, the test updates the cookie jar **for the right client**; do not use a single static `CookieManager` for both actors.
- `maximumSessions(1)` does not replace these tests; that limits **how many sessions the same user can have**.

## 15. Authentication session vs user context: when does a race occur?

A common coding mistake:

```java
// WRONG: all requests share a single mutable SecurityContext.
private static final SecurityContext SHARED =
    SecurityContextHolder.createEmptyContext();

public void onAuthenticated(Authentication authentication) {
    SHARED.setAuthentication(authentication);
    SecurityContextHolder.setContext(SHARED);
}
```

When A and B call `onAuthenticated` concurrently, `SHARED` keeps only whichever `Authentication` was written last. Even if each thread has a `ThreadLocal` pointing to `SHARED`, **the same context object** is still overwritten.

How to fix:
- Create a new `SecurityContext` for **each authentication**.
- Do not keep a static/shared reference to a mutable `SecurityContext`.
- Store it properly per **session/request** via the corresponding `SecurityContextRepository`.
- Do not reuse one user's mutable `UsernamePasswordAuthenticationToken` as another user's result.
- When a background task needs identity, capture a snapshot or an appropriate wrapper per task rather than using a global `SecurityContextHolder`.

**Note:** an independent per-thread `SecurityContext` that holds a **shared mutable** principal/authorities object can still leak permissions or mutate data across users. You need to evaluate the **entire object graph**, not just compare context instance identity.

## 16. `@Async`, `CompletableFuture`, and thread pool tasks

Inside a servlet request:

```java
public void submitJob() {
    // Scope illustration only, not a complete job implementation.
    executor.execute(() -> {
        // The thread pool may differ from the request thread.
        // SecurityContextHolder here is not the caller by default.
    });
}
```

If user context is needed inside the job:
- Extract business identity (actor ID/tenant ID) into **server-verified** arguments.
- Use `DelegatingSecurityContextCallable` or `DelegatingSecurityContextExecutorService` if the job truly needs the Spring Security context.
- When the job obtains identity from `SecurityContext`, the wrapper must be created/submitted **while the caller context is still valid**, not after the request has already ended.
- Ensure cleanup/restore on the worker thread inside `finally`, especially when the job throws an exception.
- Do not use `MODE_INHERITABLETHREADLOCAL` as the primary context propagation mechanism for thread pools.
- When using `CompletableFuture.supplyAsync` or a custom scheduler, verify which executor runs the task; the common pool does not automatically carry the right Spring Security identity.
- For multi-hour jobs, avoid holding the entire mutable Authentication/session; pass the allowed actor/tenant IDs and re-check permissions at execution time when business rules require it.
- Test multiple interleaved A/B jobs on **the same executor** and test a job throwing an exception before job B runs.

### `SecurityContext` was propagated correctly, but permissions changed?

For example, Alice had `ROLE_MANAGER` when enqueuing, then it was revoked before the job ran. An old context snapshot does not automatically reflect revocation. Policy must decide:
- Act based on permissions at **submit time** or **execute time**?
- Should the job be cancelled or should account state/permissions be re-checked before sensitive actions?
- What data scope is the job allowed to operate on, and should audit logs clearly record the actor/delegation?
- Is there a risk of A's task mistakenly reading B's tenant/resource through a cache/repository?

That is **authorization freshness**, different from an identity leak bug, but it must be tested in the same workflow because the consequences are similar.

## 17. WebFlux: use Reactor Context, do not assume ThreadLocal

In Spring Security WebFlux, Authentication is placed in the **Reactor Context** via `ReactiveSecurityContextHolder`. A reactive pipeline can switch threads on `publishOn`, `subscribeOn`, `flatMap`; a single request is not pinned to a single thread.

Example reactive controller:

```java
@GetMapping("/api/reactive/me")
public Mono<String> me() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .switchIfEmpty(Mono.error(
            new IllegalStateException("No authenticated user")
        ));
}
```

Imports:

```java
import reactor.core.publisher.Mono;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
```

This is a **snippet inside a WebFlux `@RestController`** with a `SecurityWebFilterChain` protecting the route; it is not a standalone endpoint. If the principal is anonymous or unauthenticated, the security filters must block it per policy before the controller runs; do not use `IllegalStateException` as an HTTP authentication entry point.

### Reactive leak anti-pattern

```java
// WRONG: sharing a single mutable identity across subscriptions.
static volatile String lastUser;

Mono<String> whoAmI() {
    return Mono.just(lastUser);
}
```

A subscription from Bob may read Alice's value or vice versa. `volatile` does not isolate data per subscription.

Also avoid:
- Accessing `SecurityContextHolder.getContext()` as if it automatically represented a reactive request.
- Storing `Authentication` in a singleton controller/service field.
- Calling `.block()` to get the principal on the Netty event loop.
- Keeping a **globally** `.cache()`-d `Mono<String>` whose content depends on the user without scoping by user/subscription.
- Switching from reactive to an external thread pool and manually propagating `ThreadLocal` incorrectly.

### How to test reactive

Use `WebTestClient` and Spring Security Test to check per-request identity/authorities. When testing true isolation, you can run two `WebTestClient` contexts with different credentials, or use `StepVerifier` for two streams with `contextWrite(ReactiveSecurityContextHolder.withAuthentication(...))`.

Unit **snippet** example:

```java
Mono<String> currentName =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());

Mono<String> aliceFlow = currentName.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(aliceAuth)
);
Mono<String> bobFlow = currentName.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(bobAuth)
);
```

`aliceAuth` and `bobAuth` here are two independently created test `Authentication` instances. Use `StepVerifier` or `Mono.zip(aliceFlow, bobFlow)` to assert that the two names do not mix; `currentName` is only subscribed when the right context has been attached. Do not use the same mutable SecurityContext for both flows.

**Reactive HTTP testing** still needs to verify the actual filter chain, session/cookie or Bearer token, and controller, not just unit-test `contextWrite`.

## 18. Not leaking identity is still not enough: per-resource authorization

Suppose `/api/me` always returns the right principal, but the controller allows fetching data by arbitrary ID:

```java
// WRONG: no owner/tenant check.
@GetMapping("/api/orders/{orderId}")
public Order getOrder(@PathVariable long orderId) {
    return repository.findById(orderId)
        .orElseThrow();
}
```

Alice can try Bob's order ID. This is a **Broken Object Level Authorization (BOLA/IDOR)** bug.

A safer pattern:

```java
@GetMapping("/api/orders/{orderId}")
public Order getOrder(
        @PathVariable long orderId,
        Authentication authentication) {
    return repository.findByIdAndOwnerId(
            orderId,
            authentication.getName()
        )
        .orElseThrow(() -> new ResponseStatusException(
            HttpStatus.NOT_FOUND
        ));
}
```

This is a **snippet** requiring `Order`, `repository`, Spring MVC imports, and the appropriate `ResponseStatusException` type. For multi-tenant systems, `ownerId` is often not enough; the query must also include `tenantId` and a server-verified tenant policy:

```text
SELECT ... FROM orders
WHERE id = :orderId
  AND owner_id = :authenticatedUserId
  AND tenant_id = :authenticatedTenantId
```

Do not take `tenantId` from a client-controlled query/header without checking membership/permission. For admins, use separate authorization for cross-user access; do not accidentally bypass the owner check simply for having any `ROLE_ADMIN` in another tenant.

### Negative test matrix for object isolation

| Actor | Request | Expected |
| --- | --- | --- |
| Alice | `GET /api/orders/A1` | 200, owner=Alice |
| Bob | `GET /api/orders/B1` | 200, owner=Bob |
| Alice | `GET /api/orders/B1` | 403 or 404 per policy, **no** Bob data |
| Bob | `GET /api/orders/A1` | 403/404, no Alice data |
| Anonymous | `GET /api/orders/A1` | 401/redirect, no data |
| Alice/Bob | Concurrent requests across different tenants | No data/authority mixing |
| Alice | `POST /api/orders` with body `owner=bob` | Server does not trust owner from body if policy only allows creating one's own order |
| Tenant A admin | `GET /api/orders/B1` in tenant B | Not automatically allowed if cross-tenant access is forbidden |

For denied responses, verify there is **no PII** of another user in the error body/logs/headers. Avoid returning messages like `"Order 123 belongs to bob"` to Alice.

## 19. Concurrent session control: difference from user isolation

Spring Security Servlet provides `sessionManagement(session -> session.maximumSessions(...))` to limit the number of **concurrent sessions for the same principal**. For example:

```java
http.sessionManagement(session -> session
    .maximumSessions(1)
    .maxSessionsPreventsLogin(true)
);
```

This is a **snippet inside `HttpSecurity` of a session-based application**; do not use it directly in the stateless Basic demo from Section 11.

`maximumSessions(1)` answers: “How many sessions can one account be logged into?”. It does **not** answer: “Could Bob's session get mixed up with Alice's principal?”. Two accounts, Alice and Bob, can each have their own separate session even when each account only allows one session.

To test concurrency control:
- Create **two separate clients/sessions with the same username**.
- With `maxSessionsPreventsLogin(true)`, the second login exceeding the limit must be rejected (depending on the flow).
- With a configuration allowing a new login to replace an old session, the previous session will be invalidated according to policy.
- Ensure `SessionRegistry` and session lifecycle events are configured/received properly when using the traditional mechanism.
- In Spring Session/clustered applications, verify a registry/store suited to the distributed model.
- If a custom principal is used as a key in `SessionRegistry`, `equals()`/`hashCode()` must reflect a stable identity; a broken implementation can cause inaccurate session counting.

**One browser with two tabs** typically shares a single session cookie. Do not use two tabs in the same profile to conclude that concurrent session limits are not working.

### Session fixation protection also needs testing

After login, the session ID may be rotated to prevent session fixation. Tests should:
1. Obtain a pre-login session/cookie if the workflow creates a session.
2. Log in with real credentials.
3. Verify that the post-login cookie/session holds the active identity; typically the session ID changes.
4. Not accidentally attach the previous user's `SecurityContext` to the new session when the browser switches accounts.
5. Ensure logout/session rotation revokes per policy and does not affect another account's session.

## 20. JWT/OAuth2 Bearer: concurrent testing by token, issuer, and tenant

A Resource Server with JWT or opaque tokens typically does not use `HttpSession` to verify users, but it still carries risks of sharing mutable state in converters/caches.

At minimum, test:
- JWT A has `sub=alice`, valid issuer/audience, scope `read:a`; JWT B has `sub=bob`, scope `read:b`.
- Both tokens are sent concurrently to the same endpoint: `JwtAuthenticationToken.getName()`/authorities must match the current token.
- JWT A must not inherit `SCOPE_read:b` from B (and vice versa).
- Do not take `sub`/tenant from a JSON body to replace the principal verified by the decoder.
- Invalid signatures, expired tokens, or wrong audiences must be rejected; they must not pick up an Authentication left behind by an earlier request on the thread pool.
- Token A logout/revocation per policy: if a self-contained JWT has not expired and has no revocation, understand that property clearly; do not assume session logout automatically invalidates a JWT.
- If using a `JWT claims → authorities` cache, the cache key must reflect credential/issuer/tenant/policy version, not just the `/api/me` path.
- With opaque token introspection, backend errors and A/B user data must be mapped independently; do not use a single mutable singleton `OAuth2AuthenticatedPrincipal`.
- Test `JwtGrantedAuthoritiesConverter` or custom converters at the unit level, then test HTTP through the corresponding `SecurityWebFilterChain`/`SecurityFilterChain`.

**Do not confuse `@WithMockUser` with real JWT verification:** the `.jwt()` request post-processor in Spring Security Test typically builds a mock Authentication for authorization tests and does not itself prove signature/issuer/audience verification. To test the full security pipeline, use appropriate decoder/issuer tests or real-token integration tests.

## 21. Headers, caching, and gateways: right principal, wrong response

Cross-user data leak bugs can happen **outside Spring Security**:

```text
Alice -> GET /api/account/summary -> CDN caches by URL
Bob   -> GET /api/account/summary -> CDN returns Alice's cached response
```

The server on request B may have authenticated Bob correctly, yet a cache layer used a **non-user-discriminating key** and served Alice's data. Therefore, you should test through the deployment/gateway when production uses caching.

Mitigations:
- For personal/sensitive responses, consider `Cache-Control: private, no-store` or an equivalent caching policy.
- Do not cache responses containing user data under a global key based solely on URL/path.
- If caching is required, use keys containing principal/tenant/permissions/policy version and proper invalidation; do not expose raw tokens as keys in logs/metrics.
- Check reverse proxies and appropriate HTTP `Vary` headers; do not treat `Vary: Authorization` as a universal guarantee across all CDNs.
- Do not return private information before auth/authorization filters; protect streaming/SSE before committing the response.
- Check GraphQL DataLoader/per-request caching: a singleton DataLoader caching by ID without tenant scoping can return B's object to A.
- For WebSocket, the principal is attached at handshake/session; you must verify permissions for subscriptions/topics and when permissions change. Another connection belonging to Bob must not receive events meant for Alice.
- When using a gateway with pre-auth headers, only trust headers from a verified proxy with client spoofing blocked.

This reiterates: testing `SecurityContextHolder` is necessary, **not sufficient**, to prove user data does not leak.

## 22. State changes while requests are in flight

Concurrent testing must account for **the timing of security state changes**:

### Case A: Logout while another request is being processed

```text
t0: Alice opens request A1 (authenticated)
t1: Alice logs out on another request A2
t2: A1 is still running
t3: A new request A3 arrives after logout
```

You cannot always require A1 to be immediately aborted at t1; that depends on session/policy and whether the request was already authorized beforehand. However, A3 must obey logout/revocation and must not allow the old Authentication to “reappear” due to a thread/session write race.

### Case B: Alice and Bob log in at the same time

- Cookie jars must be kept separate.
- Each client's CSRF token and session state must stay paired properly.
- Each new login writes `SecurityContext` only to the matching target's repository/session.
- B's failed login must not delete A's session.
- Audit events must have accurate actor identities and correlation IDs.
- With a custom `SecurityContextRepository`, verify that keys/session IDs are not overwritten.

### Case C: Role change while a request is running

- An already-authorized request may use the permission snapshot from when it started.
- New requests must follow the updated reload/revocation/permission policy.
- Do not implicitly assume that changing a role in the DB immediately updates every `Authentication` stored in sessions or already-issued JWTs.
- If business requirements need immediate effect, design a dedicated **revocation/version check**.

### Case D: Two requests writing data for the same user

This is also a **business concurrency** issue: optimistic locking, unique constraints, idempotency, and transactions may be required. Testing non-leakage of identity does **not** prove against lost updates or double charges. Each requirement needs its own assertions, especially when modifying permissions/credentials or redeeming recovery tokens.

## 23. Comprehensive testing matrix

| Category | Concurrent / sequential scenario | Pass condition |
| --- | --- | --- |
| Context | A and B on two threads simultaneously | Each thread's context holds the right principal |
| Thread reuse | A finishes, B runs on the same pooled thread | Nothing from A remains in B |
| Anonymous | A authenticated, anonymous GET concurrently | Anonymous does not see A |
| Login success | A/B log in validly on two separate clients | Right account and separate authorities |
| Login failure | A valid, B wrong password | B does not inherit A; A does not lose its session |
| Role | A user, C admin concurrently | A lacks `ROLE_ADMIN`; C has it |
| Session | Cookie A vs cookie B | A sees A, B sees B |
| Same-browser tabs | One cookie jar, switching accounts between tabs | Matches single-session semantics, not treated as two sessions |
| Logout | Logout A while B sends requests | B remains valid; A is rejected per policy |
| Password reset | Reset A while B is logging in | B's token/session is not mistakenly bound to A |
| `@Async` | Job A then B on one executor | Job A uses A, Job B uses B, cleanup after each job |
| Job failure | Job A throws exception then job B runs | A's context does not leak into B |
| WebFlux | Alice/Bob `Mono` interleave | Reactor Context does not mix |
| JWT | JWT A/B/invalid interleaved | Claims/authorities match token, invalid is rejected |
| Ownership | A accesses B's object | 403/404; no B data in response |
| Tenant | Two accounts with same ID in different tenants | Query/cache scoped to tenant properly |
| Cache | CDN/app cache receives request A then B | B does not see A's payload |
| Session fixation | Login rotates session ID | Auth context binds properly to new session |
| Concurrent sessions | Same user logs into two browsers | maximumSessions policy is enforced |
| User revoked | Disable/role revoke while requests exist | New requests obey revocation policy |
| Multi-node | A/B across multiple nodes | Session/cache/store do not mix actors |
| Audit | Interleaved A/B log events | Actor, tenant, and request ID are accurate |

### Test data should carry clear markers

Use fake records:

```json
{
  "ownerId": "alice",
  "tenantId": "tenant-a",
  "marker": "ALICE_PRIVATE_TEST_ONLY"
}
```

And Bob's record with a different marker. Test that Bob's body **does not contain** Alice's marker. Do not use real sensitive data to detect leaks; fixtures just need to be distinguishable.

## 24. Avoiding flaky tests and false positives

**Wrong way to test concurrently:**

```java
// No concurrency guarantee, and relies on luck-based sleep.
Thread.sleep(100);
```

Replace with `CountDownLatch`, `CyclicBarrier`, `Phaser`, or controlled mock dependency coordination. Use timeouts so tests do not hang CI indefinitely.

Rules to apply:

1. **Barrier before the work being verified:** at least two workers must hit the rendezvous point. If testing at the controller/business layer, you can attach the barrier to a test-only service instead of injecting a blocking barrier into production code.
2. **Separate expected data:** the expected actor lives inside each request's `Callable`/immutable record.
3. **Catch exceptions:** call `Future.get`, do not just call `pool.execute` without collecting failures.
4. **Cleanup:** `shutdownNow`/`awaitTermination`, `SecurityContextHolder.clearContext`, close test clients/sessions when needed.
5. **Do not change the global SecurityContextHolder strategy between parallel tests** without isolation, because the strategy is JVM-wide.
6. **Do not use a shared `MockHttpSession`** when the goal is two independent browsers.
7. **Do not use the same cookie store** and mistake test-induced session mixing for a server bug.
8. **Do not use `@WithMockUser` instead of real login** if the goal is to verify authentication providers/filters.
9. **Do not equate `Future` completion order with input order**; use actor-request mapping.
10. **Do not assert only 200:** you must assert name, authorities, tenant, resource content, and negative paths.
11. **Limit load:** test concurrently with a controlled request count; do not run an arbitrary load test against production.
12. **Repeat intentionally:** run across multiple seeds/iterations in CI or staging to catch low-probability races; do not rely on a single pass.
13. **Do not hide bugs with retries:** if a retry makes a race vanish, keep the logs/correlation and add a dedicated regression test to fix the root cause.
14. **Distinguish infrastructure failures:** timeouts/429/503 caused by test overload must not be labeled “identity leak”; inspect service capacity and classify failures.
15. **Do not enable broad parallel test execution too early:** JUnit parallel test execution can mutate singleton state, caches, and test context fixtures, causing interference. Isolate fixtures and use resource locks when needed.

### Deterministic time-based testing

Avoid `Thread.sleep` to “wait for login to finish” or “wait for session to expire”. Use an injectable `Clock` for TTL, latches/barriers for races, and event hooks in tests. For real HTTP session expiry, you can test a short TTL configuration in a test profile or use controlled session-management APIs instead of long unstable sleeps.

## 25. Observability and investigation when a leak is suspected

Production symptoms:
- A user refreshing the page sees someone else's name a few times before it disappears.
- The logged actor differs from the `sub` in the verified token.
- An API response has a different `ownerId` from the principal even though the request was authenticated.
- The issue only occurs under high traffic or when background jobs run.
- Requests from different users hit the same shared cache key.
- After a failed job, the next job has the previous user's authorities.
- CDN/browser cache returns another user's profile.
- One user's logout affects an unrelated session.

When investigating:
- Track **requestId**, trace/span, **server-verified** principal internal ID and tenant ID, and a **pseudonymous session ID** if needed.
- Do not log raw cookies, access/refresh tokens, passwords, OTPs, or unnecessary user PII.
- Log events: auth success/failure, session create/rotate/logout/revoke, principal resolution, authorization deny, context propagation, cache hit/miss.
- You can add an alert when `response.ownerId` differs from `authenticated.subject` at business control points, while considering privacy.
- Capture **synthetic test evidence** (fixtures); never send real customer data to third parties.
- Use per-request correlation; do not use a `ThreadLocal` logging context without clearing it at the end of the request.
- For confirmed data-exposure bugs, treat them as a security incident: stop the leak source, investigate scope, notify according to policy/law, and add regression tests.

**Do not fix by “adding synchronized to every endpoint”.** If the root cause is a singleton `currentUser`, synchronization might temporarily reduce races yet still fail to create per-request identity. Fixing state scope/ownership is the right remedy.

## 26. Self-check questions

**Question 1.** Alice and Bob both GET `/api/me` and both receive HTTP 200. Can we conclude there is no identity leak?

**Answer:** No. You must assert that the `username`/authorities in the body (or other returned information) match the respective request, and verify data ownership. Two 200 responses are not enough.

**Question 2.** In Servlet, `SecurityContextHolder` uses `ThreadLocal` by default, so why do leaks still happen?

**Answer:** Because custom code may share a single mutable `SecurityContext`, store the principal in a singleton/static field, propagate context improperly to an executor, or fail to clear a custom ThreadLocal. The Spring filter chain does not fix application anti-patterns.

**Question 3.** How important is `ThreadLocal.remove()` in `finally`?

**Answer:** It prevents a thread pool from retaining the previous task's identity after the task ends, even when an exception occurs. For Spring-managed servlet requests, the framework clears SecurityContextHolder; for self-managed threads/tasks, proper propagation/cleanup must be applied.

**Question 4.** Do two tabs in the same Chrome profile logged into Alice and Bob count as two sessions?

**Answer:** Usually no. Two tabs usually share the same cookie jar, so they can share one session. Use two profiles/contexts or two cookie jars when testing session isolation.

**Question 5.** Does `maximumSessions(1)` guarantee Bob's session cannot see Alice?

**Answer:** No. It limits the number of sessions for the same account per policy. You must still test principal, cookies, SecurityContextRepository, and resource ownership.

**Question 6.** Why is `@WithMockUser("alice")` not enough for testing real concurrent login?

**Answer:** It attaches a mock Authentication for testing; it does not prove the application's HTTP login/credential validation, session cookies, concurrency, or context persistence.

**Question 7.** In WebFlux, should you read `SecurityContextHolder` inside every `flatMap()`?

**Answer:** No. Spring Security WebFlux relies on Reactor Context; use `ReactiveSecurityContextHolder` or appropriate injection. ThreadLocal is not uniquely bound to a single reactive subscription.

**Question 8.** Bob's API returns `principal=bob` but returns Alice's order. Did the identity test pass?

**Answer:** The principal check may pass, but **the data ownership test fails severely** (IDOR/BOLA). Per-object/tenant authorization must be added.

**Question 9.** Should we create a single `DelegatingSecurityContextExecutorService(raw, aliceContext)` and submit every other user's requests through it?

**Answer:** No. The constructor with a fixed `SecurityContext` can run all jobs under Alice. In multi-user systems, pass the right context per task or use a wrapper that captures at submission time appropriately, along with cleanup.

**Question 10.** Does one concurrent run of 30 requests all succeeding prove permanently that there are no races?

**Answer:** No. It is one layer of regression testing. You need request/session/async/object ownership tests under varied conditions, repeated runs across seeds/controlled load, and architectural review of shared state.

## 27. Release checklist and closing notes

Before concluding that login functionality is safe in a multi-user environment, ensure:

- [ ] At least two or three test users exist with different roles, tenants, and private-data markers.
- [ ] Concurrent HTTP tests compare the principal and **the exact set of authorities**, not just HTTP 200.
- [ ] Test A/B across two separate sessions/cookie jars when the application uses form login.
- [ ] Test that anonymous requests do not inherit auth from a previous request on a pooled thread.
- [ ] There is no application-wide singleton/static mutable field holding `currentUser`/`Authentication`.
- [ ] `SecurityContext` is created and stored separately per request/session; no mutable instance is shared across users.
- [ ] Custom login uses `SecurityContextRepository.saveContext(...)` when persisting sessions.
- [ ] Task executors/`@Async` propagate the caller's context properly or run under an explicit service principal, always with cleanup.
- [ ] Reactive code uses Reactor Context rather than relying on ThreadLocal like Servlet.
- [ ] JWT/opaque token mappers/caches do not mix claims/authorities across users/tenants.
- [ ] Per-object and per-tenant permissions are verified; not just `isAuthenticated()`.
- [ ] Logout, account switching, session fixation, and role revocation have dedicated tests.
- [ ] Same-user concurrent-session limits are tested independently from cross-user isolation.
- [ ] Negative tests exist: wrong token, wrong password, access denied, another user's object, cache hits.
- [ ] No private-response cache uses a global key shared across multiple users.
- [ ] `Future.get`/timeouts/cleanup make concurrent tests fail reliably instead of hanging CI.
- [ ] Regression tests run through HTTP/cluster/gateway when the architecture actually includes those layers.
- [ ] Logs and monitoring do not record raw secrets/cookies while providing enough correlation to detect wrong actors.

**Conclusion:** in Spring Security systems, the identity isolation principle is that **each request/job receives its own security context and authorities, with no shared state capable of swapping or escalating permissions between users**. Testing must apply simultaneously at the **thread**, **authentication filter**, **session**, **async/reactive context**, **object-level authorization**, and **cache/gateway infrastructure** levels. The strongest test is a concurrent run with explicit per-actor expectations and a set of negative cases sufficient to prove no path returns another user's data.

## 28. Official references

- Spring Security 6.5 — Servlet Authentication Architecture (`SecurityContextHolder`, createEmptyContext, ThreadLocal): https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security 6.5 — Concurrency Support (`DelegatingSecurityContextRunnable`, Executor): https://docs.spring.io/spring-security/reference/6.5/features/integrations/concurrency.html
- Spring Security 6.5 — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security 6.5 — Session Management / Concurrent Sessions: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security 6.5 — MockMvc Security Setup: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html
- Spring Security — Testing Form Based Authentication: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/form-login.html
- Spring Security 6.5 API — `DelegatingSecurityContextCallable`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/concurrent/DelegatingSecurityContextCallable.html
- Spring Security 6.5 API — `DelegatingSecurityContextExecutorService`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/concurrent/DelegatingSecurityContextExecutorService.html
- Spring Security 6.5 — Reactive Method Security and Reactor Context: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html
- Spring Security 6.5 — Testing Authentication and MockMvc: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html
- OWASP — Authorization Cheat Sheet (per-object access control): https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP — API Security Top 10: https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/

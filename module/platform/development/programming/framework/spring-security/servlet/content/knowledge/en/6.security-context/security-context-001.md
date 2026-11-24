# How SecurityContextHolder, SecurityContext, and Authentication Relate

In **Spring Security for Servlet applications**, the three concepts `SecurityContextHolder`, `SecurityContext`, and `Authentication` work together to answer one question: **during the current execution, what does Spring Security know about the caller?**

- **`Authentication`** represents information about the principal and authentication state: who is being identified, which authorities are assigned, and what related authentication details exist.
- **`SecurityContext`** is the container holding the current `Authentication`, shared by security components within the appropriate execution scope.
- **`SecurityContextHolder`** is the static access point (facade) to `SecurityContext` via a `SecurityContextHolderStrategy`; in a typical Servlet application, the default strategy binds the context to the **current thread**.

These three components form the following relationship:

~~~text
Code running in request / filter / controller
                |
                v
SecurityContextHolder.getContext()
                |
                v
         SecurityContext
                |
                v
       getAuthentication()
                |
                v
          Authentication
          |   |        |
       principal  authorities  authenticated / credentials / details
~~~

This is the model of the **security context currently in use**; it does not mean every request is already logged in or that context data persists forever. This lesson moves from object structure to request lifecycle, thread safety, sessions, practical APIs, and testing.

## 1. Distinguishing Each Component's Responsibility

| Component | What does it represent? | Typical APIs | What NOT to assume |
| --- | --- | --- | --- |
| `SecurityContextHolder` | How application code accesses the security context bound to the current storage strategy | `getContext()`, `setContext(...)`, `clearContext()`, `createEmptyContext()` | It is not by default a global variable shared across all users |
| `SecurityContext` | The object holding the current `Authentication` | `getAuthentication()`, `setAuthentication(...)` | Does not verify passwords or enforce authorization by itself |
| `Authentication` | Principal details along with authorities and authentication status | `getPrincipal()`, `getCredentials()`, `getAuthorities()`, `isAuthenticated()` | An `isAuthenticated()` flag alone is not enough to conclude this is a real, fully authenticated user |
| `SecurityContextRepository` | Reads/writes the context from/to a store between executions if configured | `loadDeferredContext(...)`, `saveContext(...)` | Not synonymous with `SecurityContextHolder`, and not every application stores context in the session |
| `AuthenticationManager` / `AuthenticationProvider` | Verifies authentication evidence and produces a valid authentication result | `authenticate(...)` | Not the object that stores context per thread |

A simple mental picture: `SecurityContextHolder` is **how to find the right current box**; `SecurityContext` is **the box**; `Authentication` is **the information placed inside the box**. Meanwhile, `SecurityContextRepository` can **save and reload** the box across HTTP requests if the application follows a stateful model.

### Accessing via API

In code currently being processed by Spring Security:

~~~java
SecurityContext context = SecurityContextHolder.getContext();
Authentication authentication = context.getAuthentication();
~~~

Required imports:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
~~~

This is an **application snippet with the Spring Security dependency**, not a standalone Java program run with `javac`. `getContext()` typically provides an existing context or an empty one; however, `getAuthentication()` can be `null` when no authentication is present. Do not immediately call `authentication.getName()` before checking for null.

## 2. What Information Does Authentication Hold?

`Authentication` extends Java's `Principal` and adds properties used for security. Key APIs:

| API | Content | Example / note |
| --- | --- | --- |
| `getPrincipal()` | The identified principal or identity-describing object | May be `UserDetails`, `Jwt`, a `String`, or a custom principal type |
| `getName()` | String representation of the principal's name | Often the username; not guaranteed to be a unique system ID |
| `getCredentials()` | Data used to authenticate | May be a password/token and is often erased after authentication; never log it |
| `getAuthorities()` | Collection of `GrantedAuthority` for access decisions | For example `ROLE_USER`, `ROLE_ADMIN`, or a scope/permission |
| `getDetails()` | Additional details provided by the authentication mechanism | May be web request metadata; not every field should be treated as verified |
| `isAuthenticated()` | Authentication state of the object according to the mechanism that created it | Not necessarily equivalent to "a user logged in with full account credentials" |

For example, after logging in with a username/password, a valid `UsernamePasswordAuthenticationToken` may carry a `UserDetails` principal, authority `ROLE_USER`, and `isAuthenticated()=true`. With a JWT Resource Server, the object type and principal can differ; the application should not cast `getPrincipal()` to `UserDetails` for every mechanism.

### Authentication Is Both a Request and Potentially a Result

In an authentication flow, the same `Authentication` abstraction can be used in two stages:

~~~text
Client sends credentials
      |
      v
Unauthenticated Authentication
(e.g., UsernamePasswordAuthenticationToken.unauthenticated)
      |
      v
AuthenticationManager / AuthenticationProvider
      | verifies credentials, account, policy
      v
Authenticated Authentication
(with trusted principal and authorities)
      |
      v
SecurityContext.setAuthentication(...)
      |
      v
SecurityContextHolder.setContext(...)
~~~

Before verification, `Authentication` can carry a username/password for an authentication provider to verify. After successful verification, `AuthenticationManager.authenticate(...)` returns an authenticated `Authentication`; this object typically contains the final authorities.

**Do not construct an authenticated token solely from user-submitted data.** For example, calling `UsernamePasswordAuthenticationToken.authenticated("alice", null, authorities)` with a client-supplied username and placing it into the context will cause the application to trust an unverified identity. A trusted authentication mechanism must be used to verify it first.

### AnonymousAuthenticationToken May Still Return isAuthenticated() = true

Spring Security commonly includes `AnonymousAuthenticationFilter`, which creates an `AnonymousAuthenticationToken` when no valid authentication is present. For a standard anonymous object, `isAuthenticated()` can be `true` because it is a technical property of the token, **not an indication that a real user has logged in**.

Therefore, a check like:

~~~java
if (authentication != null && authentication.isAuthenticated()) {
    // Not sufficient to conclude this is a logged-in account.
}
~~~

is overly simplistic. For authorization, prefer Spring Security's DSL/`AuthorizationManager`, such as `authenticated()`, `fullyAuthenticated()`, or `hasRole(...)`. The framework uses mechanisms such as `AuthenticationTrustResolver` to distinguish anonymous and remember-me tokens. For displaying a username, exclude anonymous tokens or use an appropriate principal-retrieval mechanism.

## 3. What Does SecurityContext Contain, and Why Create a New Context?

The `SecurityContext` interface fundamentally allows **reading/setting `Authentication`**:

~~~java
Authentication authentication = context.getAuthentication();
context.setAuthentication(authentication);
~~~

A typical application does not need to set the authentication manually: Spring Security's filters and providers handle this during the authentication flow. When building a **properly designed custom login mechanism**, after `AuthenticationManager` returns a trusted result, the safe pattern is to create a new empty context and set it in the holder:

~~~java
// Illustrates a step AFTER AuthenticationManager verifies successfully:
Authentication result = authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
                submittedUsername, submittedPassword));

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(result);
SecurityContextHolder.setContext(context);

// For stateful login that needs to persist across requests, the login mechanism
// may need to call securityContextRepository.saveContext(
//         context, request, response) as configured.
~~~

This snippet **is not a complete login endpoint**: the variables `authenticationManager`, `submittedUsername`, `submittedPassword`, `request`, `response`, and `securityContextRepository` are provided by the application; you must add imports for `UsernamePasswordAuthenticationToken` and appropriate error/login handling. Do not copy this snippet into a public method that accepts credentials while skipping validation, session fixation protection, CSRF, or rate limiting.

Creating a new context with `createEmptyContext()` is useful because context objects are mutable. Mutating an accidentally shared context can affect other code or threads holding a reference to the same object. Using a fresh context for a newly created authentication helps prevent shared-state bugs.

Once the context is set, code in the same execution context can read the `Authentication` via the holder. However, setting it in `SecurityContextHolder` **only ensures access within the current storage scope**; it does not automatically persist across subsequent HTTP requests.

## 4. Context Lifecycle in a Servlet Request

Consider a `GET /me` request in a Spring Boot 3.x / Spring Security 6.x application with a standard `SecurityFilterChain`:

~~~text
(1) HTTP request arrives at container
         |
         v
(2) DelegatingFilterProxy -> FilterChainProxy
         |
         v
(3) SecurityContextHolderFilter or equivalent mechanism
         |-- uses SecurityContextRepository to load context
         |-- binds/prepares context for current thread/request
         v
(4) Authentication filters (if authentication data is present)
         |-- verifies and may update SecurityContext
         v
(5) AuthorizationFilter
         |-- reads Authentication / context per security mechanism
         |-- allows or denies
         v
(6) Controller / Service
         |-- reads SecurityContextHolder when needed
         v
(7) End of request
         |-- may save SecurityContext if strategy requires
         |-- clears SecurityContextHolder to prevent cross-request leaks
         v
    Container reuses thread more safely
~~~

Details vary by configuration and version; not every request passes through every kind of authentication filter. In Spring Security 6.x configurations using `SecurityContextHolderFilter`, loading the context can be deferred until needed via `SecurityContextRepository`. **`SecurityContextHolderFilter` does not automatically save all changes back to the repository**; if you build a custom authentication mechanism that requires persistence, you must follow the explicit context-saving contract.

### Why Must the Holder Be Cleared?

Servlet containers commonly use a **thread pool**. A thread that served user A can be reused for user B's request. If the security context is not cleared at the right time, A's `Authentication` data risks leaking into the next execution.

Spring Security filters manage the holder lifecycle and cleanup (typically in a `finally` block). If application code sets the holder manually outside the normal filter chain, it must ensure cleanup using `try/finally` or a Spring Security-provided abstraction.

**Do not call `SecurityContextHolder.clearContext()` mid-request inside a controller** just because you finished reading the user; doing so can prevent downstream components from seeing the authentication. Arbitrary clearing does not replace logout or session/token invalidation.

## 5. Current Context vs. Persisting Context Across Requests

Distinguish three scopes clearly:

1. **Within the processing thread:** `SecurityContextHolder` provides access to the current context; the common strategy is `MODE_THREADLOCAL`.
2. **Within a single HTTP request lifecycle:** security filters set up/restore the context when the request begins and clean it up when it finishes.
3. **Across multiple HTTP requests:** if stateful login state is needed, `SecurityContextRepository` can load/save the context in the session or another chosen store. If the application is stateless, each request is typically authenticated independently.

Common repositories:

| Repository | Characteristics | Typical usage |
| --- | --- | --- |
| `HttpSessionSecurityContextRepository` | Saves/loads the context via `HttpSession` when configured | Session-based login, form login |
| `RequestAttributeSecurityContextRepository` | Stores the context in request attributes, useful for certain dispatches within the same request | Preserving context across related servlet dispatches |
| `DelegatingSecurityContextRepository` | Delegates to multiple repositories, e.g., combining request attributes and session | Configurations supporting multiple scopes |
| `NullSecurityContextRepository` | Does not retain the context to reload from a repository | Appropriate stateless models where requests re-authenticate independently |

Do not assume that calling `SecurityContextHolder.setContext(context)` automatically puts the user into the session. **Storing in the holder and saving to a repository are two separate actions.**

### SecurityContextHolderFilter vs. SecurityContextPersistenceFilter

Two easily confused API names:

- `SecurityContextHolderFilter`: brings the context from `SecurityContextRepository` to the holder (optionally using deferred loading) and clears the holder when the request completes; **explicit `saveContext`** is the responsibility of the authentication mechanism or code designed for that purpose.
- `SecurityContextPersistenceFilter`: the mechanism in older configurations/versions, which handled saving the context at the end of processing under that model.

When upgrading Spring Security, check the exact version and how the security context is saved. Do not assume every authentication is automatically written to the session, nor call `saveContext(...)` indiscriminately in every controller. Built-in Spring Security authentication filters manage saving according to their own workflows.

### Stateful and Stateless Lifecycle Examples

| Scenario | First request | Subsequent request |
| --- | --- | --- |
| Form login with session | Authenticates successfully, saves context according to configuration | Repository can reload context from session without prompting the user for credentials again |
| Stateless HTTP Basic | Each request carries appropriate Authorization header; filter authenticates | Subsequent request must send credentials again |
| Stateless Bearer/JWT | Filter validates token, creates `Authentication` for the request | Subsequent request resends token; no login context needed in session |
| Manually setting context in holder only | Code in current request can read authentication | No guarantee the next request receives the context |

`SessionCreationPolicy.STATELESS` is a common Spring Security configuration option for stateless APIs. When using it, verify the authentication mechanism, repository, and any components that might use a session; stateless does not mean nothing in the Servlet stack can ever create a session for another reason.

## 6. ThreadLocal, Multithreading, and Propagating Context Properly

### 6.1. The Default Holder Is Thread-Bound

In a traditional Servlet application, `SecurityContextHolder` defaults to a `ThreadLocal`-based strategy (`MODE_THREADLOCAL`). Code running on the same thread can read the bound context; however, a new `Thread`, a task in an `ExecutorService`, or an `@Async` method does not automatically receive the parent thread's context properly.

A common but **incorrect** assumption is: "I logged in during the request, so every thread spawned afterwards knows that user."

The standalone Java 17 example below uses plain JDK `ThreadLocal` to **illustrate what thread scope means**. It does not implement the real `SecurityContextHolder`; its sole purpose is to demonstrate why a child thread does not automatically have the parent thread's data.

~~~java
public class ThreadLocalContextDemo {
    private static final ThreadLocal<String> CURRENT_USER = new ThreadLocal<>();

    private static String currentUser() {
        String value = CURRENT_USER.get();
        return value == null ? "<none>" : value;
    }

    public static void main(String[] args) throws InterruptedException {
        CURRENT_USER.set("alice");
        System.out.println("main before = " + currentUser());

        Thread child = new Thread(
                () -> System.out.println("child = " + currentUser()));
        child.start();
        child.join();

        System.out.println("main after = " + currentUser());
        CURRENT_USER.remove();
        System.out.println("main cleared = " + currentUser());
    }
}
~~~

Save as `ThreadLocalContextDemo.java`; using JDK 17+:

~~~bash
javac ThreadLocalContextDemo.java
java ThreadLocalContextDemo
~~~

Exact stdout because `join()` waits for the child thread to finish:

~~~text
main before = alice
child = <none>
main after = alice
main cleared = <none>
~~~

In a real application, thread pools make the risk of **identity leakage between tasks** even greater if you manually copy the context without restoring/clearing it.

### 6.2. Using Spring Security's Task/Executor Wrappers

When you genuinely need to pass the context to work running on another thread, Spring Security provides abstractions such as:

- `DelegatingSecurityContextRunnable`.
- `DelegatingSecurityContextCallable`.
- `DelegatingSecurityContextExecutor` and executor-wrapping variants.

Illustrative **code snippet inside an application with Spring Security**, not a standalone Java program:

~~~java
import org.springframework.security.concurrent.DelegatingSecurityContextRunnable;
import org.springframework.security.core.context.SecurityContextHolder;

Runnable task = () -> {
    var authentication =
            SecurityContextHolder.getContext().getAuthentication();
    System.out.println(authentication == null
            ? "No authentication"
            : authentication.getName());
};

Runnable withContext = new DelegatingSecurityContextRunnable(
        task,
        SecurityContextHolder.getContext());

new Thread(withContext).start();
~~~

This snippet must run where the holder already contains a valid context. The wrapper ensures the context is set while the task executes and cleaned up/restored according to its mechanism. In production, use a managed executor rather than spawning a new thread per request; consider when the **context is captured**, whether propagation is permitted, and authentication expiration.

**Do not enable `MODE_GLOBAL` for a multi-user web application**, as that strategy shares the context process-wide and is unsuitable for isolating requests. `MODE_INHERITABLETHREADLOCAL` is also not a general solution for thread pools: reused threads or threads created at different times can easily carry stale contexts belonging to the wrong user.

### 6.3. Async and Servlet Dispatch

Any asynchronous processing requires checking boundaries: Servlet async requests, Spring MVC `Callable`, `@Async`, and executor tasks are not identical. Some Spring Security/MVC integrations provide context propagation for specific cases, but there is no universal rule that every callback carries the original context.

If you need access to the principal after the request ends, a better design is usually to pass **only the required business data** (e.g., a verified ID) into the task, or use an appropriate security wrapper. Avoid holding a mutable reference to the entire `SecurityContext` indefinitely.

**This lesson's scope is Servlet.** Spring WebFlux uses a reactive model and `ReactiveSecurityContextHolder` with the Reactor context; do not mechanically apply `ThreadLocal` patterns as in Servlet handling.

## 7. Reading Authentication Safely in a Controller

In a Spring Boot 3.x / Spring Security 6.x application with `spring-boot-starter-web` and `spring-boot-starter-security`, you can build an example controller:

~~~java
import java.util.Map;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentUserController {
    @GetMapping("/public")
    public String publicMessage() {
        return "public";
    }

    @GetMapping("/me")
    public Map<String, Object> currentUser() {
        Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();

        if (auth == null || auth instanceof AnonymousAuthenticationToken) {
            return Map.of("status", "anonymous");
        }

        return Map.of(
                "name", auth.getName(),
                "authenticated", auth.isAuthenticated(),
                "authorities", auth.getAuthorities().stream()
                        .map(authority -> authority.getAuthority())
                        .toList());
    }
}
~~~

This is a Java class placed inside a Spring Boot project; it requires the corresponding classpath/dependencies and does not run standalone with a bare `javac` command. For a validly authenticated request, the endpoint may return JSON such as:

~~~json
{
  "name": "alice",
  "authenticated": true,
  "authorities": ["ROLE_USER"]
}
~~~

This is **a conditional example output** when the principal named `alice` has `ROLE_USER`. Actual values depend on the authentication mechanism and user data.

In production, you should not expose all authorities on a public endpoint unnecessarily; the example includes them to illustrate the object. Never return `credentials`, password hashes, session tokens, access tokens, or the full `Authentication.getDetails()` to the client.

### Do You Always Have to Use the Holder in a Controller?

No. Spring Security offers more convenient ways to receive the authenticated principal in the web layer, such as a `Principal` or `Authentication` method parameter, or `@AuthenticationPrincipal` with the appropriate principal type:

~~~java
import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;

// Inside a @RestController:
@GetMapping("/me/name")
public String currentName(Principal principal) {
    return principal.getName();
}
~~~

This pattern works well when the endpoint is configured to require authentication, ensuring `principal` is non-null. If the endpoint is public, handle null or anonymous appropriately. `@AuthenticationPrincipal` is intended to extract the **principal**, not to return the entire `SecurityContext`.

For business logic, avoid letting each service interpret identities and roles differently. Place permission rules in authorization configuration, method security, or a centrally tested policy.

## 8. How Is Authentication Used for Authorization?

Authentication filters help produce `Authentication`; authorization mechanisms such as `AuthorizationFilter` and method security use the authentication info and authorities to make access decisions. For example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class CurrentUserSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/me", "/me/name").authenticated()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

This is the Spring Security 6.x configuration corresponding to the controller above. Cases:

| Request | Current Authentication | Rule | Typical result |
| --- | --- | --- | --- |
| `GET /public` | May be anonymous | `permitAll()` | Controller returns `public` if not blocked by another filter |
| `GET /me` | Anonymous or missing authentication | `authenticated()` | HTTP Basic typically returns 401 |
| `GET /me` | Validly authenticated | `authenticated()` | Proceeds to controller |
| `GET /admin/audit` | Authenticated, missing `ROLE_ADMIN` | `hasRole("ADMIN")` | Typically 403 |
| `GET /admin/audit` | Has `ROLE_ADMIN` | `hasRole("ADMIN")` | Passes authorization; endpoint must still exist to return 200 |

By default, Spring Security interprets `hasRole("ADMIN")` as the authority `ROLE_ADMIN`. `hasAuthority("ADMIN")` checks for the exact authority string `ADMIN` as passed; do not confuse role names with prefixes.

**Having an authentication in the context does not mean access is granted to every endpoint.** That object is input data; `AuthorizationManager` makes the decision based on the active policy. Similarly, having a principal in a controller does not guarantee the request passed the intended rule: verify that the right `SecurityFilterChain` was selected and the authorization rules ran.

## 9. Testing SecurityContext and Authentication

In a Spring Boot project with `spring-boot-starter-test`, `spring-security-test`, `MockMvc`, and the security configuration above, you can verify that the controller sees the expected principal and authorities:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CurrentUserContextTest {
    @Autowired
    MockMvc mockMvc;

    @Test
    void requestWithoutLoginIsRejected() throws Exception {
        mockMvc.perform(get("/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void loggedInRequestReadsContext() throws Exception {
        mockMvc.perform(get("/me"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("alice"))
                .andExpect(jsonPath("$.authenticated").value(true))
                .andExpect(jsonPath("$.authorities[0]").value("ROLE_USER"));
    }
}
~~~

These assertions assume the exact controller and `SecurityFilterChain` from the example, default HTTP Basic, and security filters integrated into MockMvc. `@WithMockUser` sets up authentication for the **test environment** and does not verify passwords through a real `AuthenticationProvider`; this test verifies how the context is used during a request.

To test real authentication mechanisms, add tests sending valid and invalid credentials/tokens along the actual request path. To test authorization, include tests for both unauthorized and authorized users. If you need to test persistence, send **two consecutive requests** with the configured session/token; a single request does not prove the context is persisted across requests.

### Testing Two Requests with the Same Session

For stateful form login, an appropriate test authenticates on the first request, obtains the session/cookie, reuses that session/cookie on the second request, and verifies the endpoint still recognizes the same principal. For a stateless bearer API, each request should resend the bearer token rather than relying on a session to retrieve the user.

Merely inspecting `SecurityContextHolder.getContext().getAuthentication()` within the same request cannot prove that code properly handles persistence or cleanup across multiple requests.

## 10. Common Pitfalls and Root Causes

### Pitfall 1: Authentication Is Null on a Public Endpoint

`permitAll()` only permits access; it does not guarantee a logged-in user. Without authentication, `getAuthentication()` may be `null` or an anonymous token depending on the chain/filters. Calling `getPrincipal()` directly without checking can throw a `NullPointerException`.

### Pitfall 2: isAuthenticated() Is True, Yet the Request Is Not Considered Fully Authenticated

This is typically the case with `AnonymousAuthenticationToken` or remember-me. The authorization DSL distinguishes anonymous, authenticated, and fully authenticated using framework semantics. Do not replace rules with a simple boolean flag check.

### Pitfall 3: A Service Gets the Context, but Another Thread Reads Null

`@Async`, custom executors, or application-spawned threads do not automatically share `MODE_THREADLOCAL`. Choose an appropriate context propagation mechanism, or pass verified user data as a business parameter when sufficient.

### Pitfall 4: User A Appears in User B's Request

Risk of context leakage arises when code manually sets the context without clearing it, uses a thread pool with broken propagation, or enables the global strategy. Identify where the context is set and when it is restored/cleared, and never store a shared static `Authentication`.

### Pitfall 5: Login Succeeds in One Request, but the Next Request Is Anonymous

Storing in `SecurityContextHolder` does not automatically guarantee saving to the session. Check the authentication filter, `SecurityContextRepository`, `saveContext(...)`, session/cookies, and stateless policy. Specifically with `SecurityContextHolderFilter`, understand the **explicit save** requirement for custom login flows.

### Pitfall 6: Casting Principal to UserDetails Causes ClassCastException

Across different mechanisms, the principal can be a `Jwt`, `String`, domain object, or `UserDetails`. If a unified domain type is needed, build an explicit adapter/mapping or check the type before casting.

### Pitfall 7: Manually Setting Authentication to Bypass Authorization

Placing a trusted token into the context without a verification step is a severe vulnerability. Always use `AuthenticationManager`/providers or a vetted trusted mechanism, and restrict where code can construct authenticated tokens.

### Pitfall 8: Assuming the Current Context Equals the Database User

`Authentication` represents the principal/authorities at the time of authentication or the current request. Authorities in the context may not reflect recent updates in the database, old sessions, or existing tokens. Systems need dedicated policies for authority refresh, token expiration, revocation, and dynamic permission checks when required by business rules.

### Pitfall 9: Enabling MODE_INHERITABLETHREADLOCAL to Fix All Async Issues

The inheritable strategy copies the context at **thread creation** time, but pre-created and reused thread pools make its semantics hard to control. For multi-user server applications, prefer Spring Security wrappers or controlled context-passing designs.

### Pitfall 10: Testing Values in One Request and Concluding There Is No Data Leakage

A single-threaded unit test does not verify end-of-request cleanup, propagation to executors, session persistence, or interleaved requests from two users. These scenarios require integration tests and appropriate concurrency testing.

## 11. Self-Check Exercises

**Exercise 1.** A controller calls `SecurityContextHolder.getContext()` and receives a valid context, yet `getAuthentication()` returns `null`. Is this a contradiction?

**Answer:** No. A context can exist in an empty state. Never assume the existence of a context implies an authenticated principal is present.

**Exercise 2.** A user submits credentials and `AuthenticationManager` verifies them successfully. Where should the result be placed so code on the current thread can see it?

**Answer:** Create a `SecurityContext` via `SecurityContextHolder.createEmptyContext()`, set the authenticated `Authentication` using `setAuthentication(...)`, and call `SecurityContextHolder.setContext(...)`. For stateful login, you must also handle context persistence and the session; setting the holder alone does not guarantee subsequent requests receive it.

**Exercise 3.** On a public endpoint, `authentication.isAuthenticated()` is `true`. Is it guaranteed to be a logged-in user?

**Answer:** No. An anonymous token can also return `true`. Use the framework's anonymous/remember-me distinction and corresponding authorization rules.

**Exercise 4.** A request from user A calls `ExecutorService.submit(...)`, and the task runs on a thread pool. Is the task guaranteed to see A's `Authentication`?

**Answer:** No, under the default `ThreadLocal` strategy. Use an appropriate wrapper/data-passing mechanism and cleanup; avoid shared contexts or relying on thread reuse.

**Exercise 5.** A stateless API uses Bearer tokens. When the first request finishes, should its authentication stay on the thread forever for future requests?

**Answer:** No. Each request typically authenticates from the token sent with that request. The holder must be cleared after processing to prevent leaking state to other requests.

**Exercise 6.** A user has `ROLE_USER` and an authenticated `Authentication`. The `/admin/audit` API requires `ROLE_ADMIN`. Why is the user denied even though the holder contains an `Authentication`?

**Answer:** The context only holds identity/authority data; authorization checks permissions against a separate policy. Because the user lacks the required authority, they are typically denied with 403.

## 12. Checklist When Using SecurityContext in Servlet Applications

- Identify **who creates `Authentication`**, who verifies credentials, and who places the result into `SecurityContext`.
- Understand the **holder → context → authentication** relationship and what each API actually returns.
- Handle cases where authentication is `null` or anonymous; do not treat `isAuthenticated()` as sufficient proof of login.
- Avoid logging credentials/tokens and avoid hard-casting the principal to an unguaranteed type.
- Let the framework manage the per-request context; if setting the context manually, ensure a trusted verification source, required persistence, and cleanup.
- Distinguish **in-thread context** from **cross-request persisted context** via repository/session.
- Account for propagation when using executors/`@Async`; do not share a global holder across users.
- Test anonymous access, authenticated access, authorization, subsequent requests, cleanup, and concurrency as needed.

**Key takeaway:** `SecurityContextHolder` locates the **SecurityContext of the current execution flow**; `SecurityContext` holds the **`Authentication`**; `Authentication` describes the identity and permissions presented to Spring Security. Reading, saving, and clearing the context according to the Servlet lifecycle produces consistent authentication and authorization behavior.
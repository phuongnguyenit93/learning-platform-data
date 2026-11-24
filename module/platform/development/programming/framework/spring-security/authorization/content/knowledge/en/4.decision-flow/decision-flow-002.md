# SecurityContext and Retrieving Authentication at Check Time

> **Module:** Spring Security – authorization  
> **Group:** Decision Flow  
> **Scope:** How Spring Security holds the active identity, how authorization mechanisms retrieve `Authentication` when a decision is needed, and execution-flow boundaries that commonly cause identity lookup errors.

## 1. Opening scenario: who is the "current user"?

An API `GET /api/invoices/101` is called by Lan. The system validates the token/session and knows Lan has the `invoice:read` permission. When deciding whether to return invoice 101, the code needs to determine:

1. **Who is making this request?** What is the identity authenticated by Spring Security?
2. **What permissions does the caller hold at check time?** Do they have the `invoice:read`, `ROLE_ACCOUNTANT`, or `SCOPE_invoices.read` authority?
3. **Is invoice 101 within the caller's scope?** Same tenant, valid owner, or properly shared?
4. **Where is the check executing?** Inside a servlet request thread, inside an interceptor-protected method, or inside an asynchronous task?

In Spring Security, **`SecurityContext` holds `Authentication`**, and **`SecurityContextHolder` provides access to the `SecurityContext` bound to the current execution context**. In a standard Servlet application, `SecurityContextHolder` uses `ThreadLocal`. Therefore, "getting the current user" means **getting the active authentication in the current execution context**, rather than reading a single global variable shared across the entire application.

This lesson follows the actual decision flow to clarify: when the context is loaded, when authentication is read, which APIs are appropriate for reading authentication, why `null`/anonymous sometimes occurs, and why offloading work to another thread requires explicit handling.

## 2. Distinguishing four related components

| Component | Role in the flow | Key point |
|---|---|---|
| `SecurityContextHolder` | Access point to the context according to the configured storage strategy | Not a "user singleton"; defaults to the current thread in Servlet apps |
| `SecurityContext` | Holds the active `Authentication` | Can exist while `getAuthentication()` is `null` |
| `Authentication` | Represents the principal or authentication request; holds principal, authorities, details, authenticated state | Concrete type depends on the authentication mechanism: username/password, JWT, OAuth, anonymous… |
| `GrantedAuthority` | Permission attached to `Authentication` for policy matching | E.g., `ROLE_USER`, `invoice:read`, `SCOPE_invoices.read` |

Common relationship:

~~~text
SecurityContextHolder
         |
         v
   SecurityContext
         |
         v
     Authentication
      /     |      \
principal credentials authorities
                    |
                    +--> ROLE_ACCOUNTANT
                    +--> invoice:read
                    +--> SCOPE_invoices.read
~~~

**`SecurityContext` does not authenticate information by itself.** It stores the authentication result/principal representation according to the system's mechanism. `Authentication` must be produced by a trusted mechanism, such as an authentication filter + `AuthenticationManager` or a JWT verified by a Resource Server. Do not trust a `userId`, `role`, or `authorities` string sent by the client and manually insert it into the context to bypass access controls.

### What does an `Authentication` contain?

Key methods of the interface:

- `getName()`: name representing the principal according to the implementation in use.
- `getPrincipal()`: principal object; may be `UserDetails`, `Jwt`, `String`, or another type.
- `getAuthorities()`: collection of granted `GrantedAuthority` instances.
- `isAuthenticated()`: status flag of the authentication token; **does not by itself guarantee the principal is a logged-in user in the business sense** because anonymous authentication can also be marked authenticated.
- `getDetails()`: additional details supplied by the implementation; do not assume tenant/permissions reside here.
- `getCredentials()`: credential data; usually cleared after authentication, never logged or exposed in APIs.

Do not cast principal to `UserDetails` in every flow. A JWT Resource Server application typically has a `Jwt` principal inside `JwtAuthenticationToken`; a form-login application may use `UserDetails`; anonymous authentication has a different principal. Build your identity abstraction around the application's actual mechanism.

## 3. Servlet request lifecycle: where does the context come from?

A typical flow with Spring Security Servlet:

~~~text
HTTP request
     |
     v
Spring Security FilterChainProxy
     |
     +--> SecurityContextHolderFilter / context loading mechanism
     |    - retrieves SecurityContext from SecurityContextRepository if applicable
     |    - prepares SecurityContextHolder for the request
     |
     +--> Authentication filters
     |    - session/form login, HTTP Basic, Bearer JWT, ...
     |    - verifies credentials/token per configuration
     |    - places trusted Authentication into the context
     |
     +--> AuthorizationFilter
     |    - selects rule for the request
     |    - retrieves Authentication WHEN the rule needs it
     |    - invokes AuthorizationManager to decide
     |
     +--> DispatcherServlet / Controller
     |    |
     |    +--> Service method intercepted by method security if configured
     |    +--> Data access and object-level policy
     |
     v
Response
     |
     v
End of processing: thread context must be cleared per lifecycle
~~~

**This is a conceptual diagram**, not the exact order of all filters in every configuration. There may be an anonymous filter, exception translation, CSRF, session management, request cache, or custom filters. Spring Security orders and orchestrates them according to the active filter chain.

In Spring Security 6.x, `SecurityContextHolderFilter` typically handles loading the context; `SecurityContextPersistenceFilter` belongs to the legacy mechanism and should not be configured to run alongside it. With session-based authentication, the repository can restore the context from the session. With a stateless JWT Bearer Resource Server, the token is typically verified and an authentication is created per request; do not assume login/token automatically persists to an HTTP session.

**Important timing point:** a request can start before all authentication steps have completed. Reading `SecurityContextHolder` arbitrarily in a filter running **before** the authentication filter may yield an empty context or lack the expected principal; place permission checks after authentication or use Spring Security's managed authorization infrastructure.

## 4. Reading `Authentication` in Servlet code

### 4.1. Lowest level: `SecurityContextHolder.getContext()`

Inside a service or component executing on a thread protected by Spring Security:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

SecurityContext context = SecurityContextHolder.getContext();
Authentication authentication = context.getAuthentication();

if (authentication != null) {
    String username = authentication.getName();
    // authorities are in authentication.getAuthorities()
}
~~~

This is a **snippet inside a Spring Security application**, not a standalone Java program. `getContext()` typically returns a context (which may be empty); **`getAuthentication()` is the value that must be checked for `null`**. Do not call `getAuthentication().getName()` directly if the code can run before login, on a public endpoint, in a worker thread, or outside a request.

When only an authenticated identity is needed, ensure the route/service is sufficiently protected and read it where used; do not store authentication in a `static` field or an instance field of a singleton service.

### 4.2. Extracting permissions from Authentication

~~~java
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;

Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

Set<String> authorities = authentication == null
        ? Set.of()
        : authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .filter(java.util.Objects::nonNull)
                .collect(Collectors.toUnmodifiableSet());
~~~

The snippet above illustrates collecting **authority strings**, not how to decide every permission manually. To check `ROLE_ADMIN`, `invoice:read`, or `SCOPE_invoices.read`, you must know which mapping source granted the authorities and what policy applies. When a role hierarchy or custom authorization logic exists, a hand-written `Set.contains(...)` check can differ from the configured `AuthorizationManager`'s result.

**Do not expose the authority list in public APIs by default.** Only expose identity/permission details when the feature truly requires it and the data is appropriately scoped.

### 4.3. Using framework interfaces to avoid reading the holder directly in controllers

In Spring MVC, common options include:

| Retrieval method | What you receive | Best suited when |
|---|---|---|
| `SecurityContextHolder.getContext().getAuthentication()` | Current `Authentication` | Synchronous service/utility inside the Servlet security context |
| `@CurrentSecurityContext(expression = "authentication") Authentication auth` | `Authentication` itself | Controller needs both identity and authorities |
| `@AuthenticationPrincipal Object principal` | `Authentication.getPrincipal()` | Only the principal is needed and its type is known |
| `Principal principal` | Request principal (usually provides `getName()`) | Only the identity name is needed, avoiding implementation coupling |
| `HttpServletRequest.getUserPrincipal()` | Servlet request principal | Servlet API integration |
| `@PreAuthorize` with `authentication`, `principal` expressions | Authentication/principal when method is checked | Placing policy at the method boundary |

An illustrative controller can be written as:

~~~java
import java.security.Principal;
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.annotation.CurrentSecurityContext;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class IdentityController {

    @GetMapping("/me")
    public Map<String, String> me(
            @CurrentSecurityContext(expression = "authentication")
            Authentication authentication,
            @AuthenticationPrincipal Object principal,
            Principal servletPrincipal) {

        // This endpoint must be protected by an authenticated rule.
        return Map.of(
                "authenticationName", authentication.getName(),
                "principalType", principal.getClass().getSimpleName(),
                "servletName", servletPrincipal.getName()
        );
    }
}
~~~

**Run requirements:** this is a Spring MVC class in a project with Spring Web and Spring Security; the `/api/me` endpoint must be protected so only authenticated users can reach it. It does not compile with JDK 17 alone. The `principalType` field illustrates that the principal is **not `UserDetails` by default**. On public endpoints, you must handle null authentication/principal, and never use such output to publicly expose sensitive permission/claim details.

Note that in some configurations, the Servlet `Principal` and Security `Authentication` are related but not necessarily the same type; `@CurrentSecurityContext` is the explicit way when you want the **full Authentication**. If you only need a business ID, use a service that converts the authenticated principal into a trusted domain identifier.

## 5. When is "check time" in `authorizeHttpRequests`?

Starting with Spring Security 6, `authorizeHttpRequests` configuration uses `AuthorizationFilter` and `AuthorizationManager`. A key difference is **on-demand authentication retrieval**:

~~~text
AuthorizationFilter
    |
    +--> creates Supplier<Authentication>
    |
    +--> finds matching rule for the request
    |
    +--> invokes AuthorizationManager
              |
              +--> permitAll / denyAll
              |       usually does not need to call supplier.get()
              |
              +--> authenticated / hasRole / hasAuthority /
                    custom policy
                      |
                      +--> when needed, calls supplier.get()
                               |
                               v
                      Authentication in the current context
~~~

Thus, the statement "Spring Security retrieves authentication **at check time**" has a concrete meaning: a rule requiring identity can retrieve `Authentication` from `SecurityContextHolder` during evaluation, rather than unconditionally loading the principal from the session or token for every URL.

Configuration example **illustrating lookup timing**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/invoices/**")
                    .hasAuthority("invoice:read")
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().denyAll()
        );

        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

In this configuration:

- `permitAll()` can allow a request without authorization **needing to read `Authentication`**; this does not mean all authentication filters are skipped.
- `hasAuthority("invoice:read")` requires the active permission from `Authentication`.
- `hasRole("ADMIN")` with the default convention typically requires the `ROLE_ADMIN` authority.
- `denyAll()` denies unconditionally, so no `Authentication` lookup is needed.
- `httpBasic()` illustrates an authentication mechanism; a real application must configure users/credentials, HTTPS, permitted endpoints, and CSRF/session controls per its architecture.

**A common misconception:** seeing that `permitAll` "does not load Authentication" and concluding "the context in the controller must be empty" or "authentication filters do not run". These are two separate stages. A rule may not **require** a lookup, while other filters may still authenticate the request; actual behavior depends on the chain configuration and the incoming request.

## 6. Custom `AuthorizationManager`: receiving the supplier and reading only when needed

When authorization logic depends on both the request and an object, `authorizeHttpRequests` lets you pass an `AuthorizationManager<RequestAuthorizationContext>`. Example illustrating policy integration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class InvoiceHttpAuthorizationConfig {

    @Bean
    SecurityFilterChain invoiceSecurity(
            HttpSecurity http,
            InvoiceAccessPolicy invoiceAccessPolicy) throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(
                        HttpMethod.GET, "/api/invoices/{invoiceId}")
                    .access((authenticationSupplier, context) -> {
                        String invoiceId =
                                context.getVariables().get("invoiceId");

                        boolean permitted = invoiceAccessPolicy.canRead(
                                authenticationSupplier.get(), invoiceId);

                        return new AuthorizationDecision(permitted);
                    })
                .anyRequest().authenticated()
        );

        return http.build();
    }
}
~~~

**This is an application-dependent configuration snippet**, requiring an `InvoiceAccessPolicy` interface/bean implemented by the system; it omits the authentication mechanism and other necessary rules. The `canRead(authentication, invoiceId)` policy must fetch the invoice from a server-side source and verify permissions, tenant, and ownership; knowing `invoiceId` does not grant permission by itself. Do not accept a caller-supplied tenant from a query/header as the sole basis.

Here, `authenticationSupplier.get()` is called **when the policy needs to evaluate the principal**. Never call the supplier during configuration startup and store `Authentication` in a singleton bean: the bean may live for months while the principal changes on every request.

When a policy needs rich context, passing `Authentication` into the policy as an explicit dependency is easier to test than having every layer call `SecurityContextHolder`. You must also choose the right location: checking per-record permissions in the service usually prevents another call path from invoking the service while bypassing the HTTP rule.

## 7. Method security: retrieving Authentication when a method is called

At the method layer, `@PreAuthorize`/`@PostAuthorize` express authorization conditions at the method call boundary. Enable support with `@EnableMethodSecurity`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

In a Spring-managed service, for example:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;

@PreAuthorize("hasAuthority('invoice:read')")
public InvoiceDto readInvoice(long invoiceId) {
    // Read the resource after passing the action permission check.
    return invoiceService.read(invoiceId);
}
~~~

The expression `hasAuthority('invoice:read')` is evaluated when the method invocation passes through the method security interceptor; it uses the authentication belonging to **the current call**. A subsequent invocation with a different authentication must be re-evaluated. Avoid caching "user A is admin" in shared bean state and reusing it for user B.

Besides helpers like `hasAuthority`, security expressions also provide:

- `authentication`: the `Authentication` instance bound to the invocation.
- `principal`: the `Authentication.getPrincipal()` object.
- `#invoiceId`: a method parameter if its name can be resolved by Spring Security.
- `@somePolicy.check(...)`: invoking an application-defined policy bean.

Example combining functional and object permissions:

~~~java
@PreAuthorize(
        "hasAuthority('invoice:read') " +
        "and @invoicePolicy.canRead(authentication, #invoiceId)")
public InvoiceDto readInvoice(long invoiceId) {
    return invoiceService.read(invoiceId);
}
~~~

**Requirements:** there must be an `invoicePolicy` bean, a matching policy method, and the parameter name `invoiceId` must be resolvable by Spring Security (e.g., compiled with `-parameters` or explicitly declared). This snippet illustrates a single method, not a standalone compilable class.

Distinguish between:

- **Authority check:** does the principal have the functional permission to read invoices?
- **Object check:** does the specific invoice belong to the principal's tenant/owner or a shared group?

Both must succeed. If the method is called directly from another method on the same instance and the project uses proxy-based method security, the annotation may not execute due to **self-invocation**. That is an architectural flaw causing the permission check to be skipped, not a `SecurityContextHolder` bug.

### 7.1. `@PreAuthorize` is not always the only check

A single request may pass through HTTP authorization, then method security, then business policies in the service/repository. Multiple guards make decisions at **different moments** within the same request. Do not conclude "passing the HTTP rule means every object is allowed".

With `@PostAuthorize`, the decision can be checked after the method completes and produces a return value; however, this is no substitute for protecting against side effects before execution. Avoid using post-checks to guard dangerous data-mutating operations that should have been blocked beforehand.

## 8. Context can be empty or anonymous: how to check?

On a public endpoint or code running outside the servlet filter chain, this situation can occur:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

// authentication may be null.
~~~

If anonymous authentication is enabled, Spring Security can place an `AnonymousAuthenticationToken` in the context. Therefore:

~~~java
authentication != null && authentication.isAuthenticated()
~~~

**is not always a reliable way to identify a "logged-in user"**. `AnonymousAuthenticationToken` can also return `isAuthenticated() == true`. This is the framework's authentication token state, not a guarantee that a user with a real identity has logged in.

In a service that only accepts authenticated users, you can use an explicit helper class:

~~~java
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

public final class CurrentActor {

    private CurrentActor() {
    }

    public static Authentication requireUser() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            throw new AccessDeniedException(
                    "An authenticated user is required");
        }
        return authentication;
    }
}
~~~

This is a Java class in a **project that already has Spring Security**, not standalone core Java. It illustrates handling `null` and anonymous tokens. In more complex systems, `AuthenticationTrustResolver` can distinguish anonymous/remember-me from policies requiring *fully authenticated*. For HTTP or method security policies, prefer the framework's `authenticated()`/`isAuthenticated()` rules with proper anonymous semantics rather than rewriting all the logic yourself.

Other cases to distinguish:

| Situation | Authentication in holder may be | What to check |
|---|---|---|
| Protected request, login succeeded | Real user/client Authentication | Principal/authorities, domain policy |
| Public unauthenticated request | `null` or anonymous | Do not assume `getName()` represents a logged-in user |
| Invalid Bearer token | Usually rejected by auth filter before controller | Do not treat as a valid user |
| New thread without context propagation | Empty context, `null` authentication | Use propagation or pass verified identity |
| Unit test without security context setup | Usually empty | Set up appropriate mock authentication/test security |
| After logout/clearContext | Previous authentication is no longer "current" | Do not reuse stale references for new permissions |

Whether the output is 401 or 403 depends on the checkpoint and security entry point/handler: unauthenticated requests usually yield `401`; authenticated requests lacking permissions usually yield `403`. An application may adopt a 404 strategy at the resource level to avoid disclosing existence, but must never leak resource contents.

## 9. Why is `ThreadLocal` the default, and what are its consequences?

On the **Servlet stack**, `SecurityContextHolder` defaults to `MODE_THREADLOCAL`. You can visualize it as:

~~~text
Request A -> Thread T1 -> SecurityContext [Lan]
Request B -> Thread T2 -> SecurityContext [Binh]

SecurityContextHolder.getContext() on T1 -> Lan's context
SecurityContextHolder.getContext() on T2 -> Binh's context
~~~

This does not mean a thread belongs to one user forever. Servlet containers use a **thread pool**: thread T1 may serve Lan's request now and Binh's on the next request. The Spring Security filter chain ensures the context lifecycle is cleaned up via its management mechanism, preventing identity carryover from one request to the next.

Three serious mistakes:

1. **Storing authentication in an instance field of a singleton `@Service`:** this field is shared by all requests and can hold the wrong user.
2. **Manually creating/setting a context in a thread and forgetting to clear it:** a reused thread can carry a stale identity.
3. **Accessing the holder from a new thread and expecting the same caller:** `ThreadLocal` does not automatically cross thread boundaries.

`SecurityContextHolder` supports other strategies such as `MODE_INHERITABLETHREADLOCAL` or `MODE_GLOBAL`, but changing the strategy is not a default server solution. In particular, `InheritableThreadLocal` combined with thread pools can propagate contexts at the wrong thread-creation time and risk using stale identities. For typical web applications, keep the default and use Spring Security's supported propagation mechanisms when truly needed.

## 10. Asynchronous tasks: which context is read when accessing the holder?

Consider an API invoking `@Async`, `CompletableFuture`, `ExecutorService`, or spawning a new thread:

~~~text
Servlet thread: Authentication = Lan
              |
              +--> submit work
                       |
                       v
                  Worker thread
                  Authentication = ?
~~~

By default with `MODE_THREADLOCAL`, a worker thread **does not automatically inherit** the servlet thread's context. It may have no authentication. If a worker reuses a stale context set manually and not cleared, that is an even more severe security bug.

Spring Security provides wrappers such as:

- `DelegatingSecurityContextRunnable`
- `DelegatingSecurityContextCallable`
- `DelegatingSecurityContextExecutor`
- Executor/task executor integrations that support `SecurityContext`

These wrappers set up the appropriate context while the delegate runs and clear it afterward. Depending on the wrapper/constructor, the context may be fixed at configuration time or captured at submission time, so you must understand the exact version and initialization behavior. **Never reuse a `SecurityContext` containing user A's identity as a fixed context for an entire executor processing user B's work.**

Conceptual example in an application that manages an executor:

~~~java
import java.util.concurrent.Executor;
import org.springframework.security.concurrent.DelegatingSecurityContextExecutor;

// delegateExecutor is an application-managed executor.
Executor securityAwareExecutor =
        new DelegatingSecurityContextExecutor(delegateExecutor);

securityAwareExecutor.execute(() -> {
    // The task can access the context propagated by the wrapper.
    // Avoid keeping Authentication in static/global state.
});
~~~

This is an **integration snippet**, not a standalone program; it requires a `delegateExecutor` and proper shutdown lifecycle. Deciding whether to **propagate identity** to background work is a business decision: a job sending an email the next day should usually use an explicit service identity/authorization or verified audit data, rather than retaining the full authentication of an earlier request.

**Rule:** if a task only needs the principal ID for auditing, pass a verified ID as job payload data. If the task must execute *with the user's permissions* at runtime, design dedicated policies, permission freshness, and propagation/delegation mechanisms rather than implicitly relying on `ThreadLocal`.

## 11. Lifecycle, permission changes, and the "currency" of Authentication

The word "current" has two distinct meanings:

1. **Current in the execution context**: the authentication that the security infrastructure is supplying for the ongoing invocation/request.
2. **Current according to the latest permission data in the database/IdP**: a role/permission may have just been changed by an administrator.

These two **are not always identical**. For example:

~~~text
10:00 — Lan logs in; Authentication contains invoice:approve.
10:05 — Admin revokes the invoice:approve permission in the database.
10:06 — An old session or unexpired JWT still carries the old authority.
10:07 — The rule reads the authority from the active Authentication.
~~~

If the system lacks a suitable permission refresh or revocation mechanism, the rule at 10:07 may still see the old authority. That **does not mean `SecurityContextHolder` read the wrong thread**; it is accurately reading the active authentication data, which simply has not been refreshed against the business permission source.

When rapid permission revocation is required, consider:

- Checking sensitive permissions against an updated source or a cache with an invalidation policy.
- Shortening access token lifetimes to a product-acceptable window.
- Designing revocation/session invalidation or token introspection when necessary.
- Not trusting long-lived claims for high-risk decisions that demand fresh permission data.
- Checking tenant, owner, and resource state at execution time, rather than relying indefinitely on data from an earlier request.

Do not equate **retrieving authentication at evaluation time** with **reloading roles from the database on every evaluation**. The authorization engine typically reads authorities already placed in `Authentication`; refreshing permissions is a separate architectural responsibility.

## 12. `SecurityContextRepository` and saving context across requests

In Servlet apps, distinguish:

- **Holder:** the context active in the current processing thread.
- **Repository:** where contexts are stored/restored across requests if the application uses persistence.
- **Session-based authentication:** can use a repository storing the context in the HTTP session.
- **Stateless Bearer JWT:** usually verifies the token and builds authentication per request, without maintaining a server session for the user.

In Spring Security 6.x, when a **custom authentication mechanism** authenticates successfully and wants to persist the context to subsequent requests, you usually need to explicitly save to `SecurityContextRepository` (instead of only calling `SecurityContextHolder.setContext`):

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.context.SecurityContextRepository;

// authentication is the verified result.
// request and response are the current HTTP Servlet objects.
// securityContextRepository is configured/provided by the application.
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);

securityContextRepository.saveContext(context, request, response);
~~~

This is an **illustrative snippet inside a custom authentication flow**, not something every controller needs to do manually. A login filter managed by Spring Security can handle context persistence according to its mechanism. Conversely, a stateless Resource Server usually **does not need** to call `saveContext` for every JWT.

Why use `createEmptyContext()` when creating a context manually? Spring Security recommends creating a fresh context before calling `setAuthentication` to reduce race condition risks caused by the same context instance being referenced/shared across multiple places. Never use manual context setting as a shortcut to spoof an identity.

Clear the context with `SecurityContextHolder.clearContext()` when your code **manages the lifecycle itself** (for example, custom thread tests); for normal requests, the Spring Security filter chain is responsible for cleanup.

## 13. Servlet vs. WebFlux: Authentication is not retrieved the same way

This lesson uses the **Servlet stack** as its primary path. In **Spring WebFlux/reactive** applications, the security context is typically based on **Reactor Context**, and you cannot arbitrarily expect `ThreadLocal` from `SecurityContextHolder` to propagate properly across reactive operators and thread switches.

Reactive Spring Security provides `ReactiveSecurityContextHolder`. Example in a reactive component:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;

public Mono<String> currentName() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
}
~~~

This is a **method in a WebFlux project with reactive Spring Security**, not a standalone Java program; when no security context exists, the publisher can be empty, so callers must design appropriate `switchIfEmpty`/authorization handling. Do not copy this method into Servlet code expecting it to replace `SecurityContextHolder.getContext()`.

In WebFlux controllers, you can inject the principal/reactive authentication through supported mechanisms, or use reactive method security when properly enabled. Preserving context propagation through the Reactor chain is critical; **calling `block()` or spawning arbitrary threads** "to read auth easily" is usually the wrong implementation direction.

## 14. Standalone Java 17 example: illustrating read timing and thread boundaries

To see clearly how **reading right at decision time** differs from **keeping an old snapshot**, the following example uses plain Java `ThreadLocal`. **This only simulates thread-bound context storage**, not Spring Security's implementation; core Java does not authenticate users/tokens on its own.

Save as `ContextTimingDemo.java`:

~~~java
import java.util.Set;
import java.util.concurrent.atomic.AtomicReference;

public class ContextTimingDemo {

    record Actor(String name, Set<String> authorities) {
    }

    private static final ThreadLocal<Actor> CURRENT =
            new ThreadLocal<>();

    static String currentName() {
        Actor actor = CURRENT.get();
        return actor == null ? "<none>" : actor.name();
    }

    static boolean canApprove() {
        Actor actor = CURRENT.get();
        return actor != null
                && actor.authorities().contains("invoice:approve");
    }

    public static void main(String[] args)
            throws InterruptedException {

        CURRENT.set(new Actor("lan", Set.of("invoice:read")));
        Actor savedOldActor = CURRENT.get();

        System.out.println("lan can approve: " + canApprove());

        CURRENT.set(new Actor(
                "minh", Set.of("invoice:read", "invoice:approve")));

        System.out.println("minh can approve: " + canApprove());

        AtomicReference<String> workerName =
                new AtomicReference<>();

        Thread worker = new Thread(() ->
                workerName.set(currentName()));
        worker.start();
        worker.join();

        System.out.println(
                "worker thread actor: " + workerName.get());
        System.out.println(
                "saved old actor: " + savedOldActor.name());

        CURRENT.remove();

        System.out.println(
                "after clear actor: " + currentName());
        System.out.println(
                "after clear can approve: " + canApprove());
    }
}
~~~

Compile/run with JDK 17 or higher:

~~~bash
javac ContextTimingDemo.java
java ContextTimingDemo
~~~

Exact output:

~~~text
lan can approve: false
minh can approve: true
worker thread actor: <none>
saved old actor: lan
after clear actor: <none>
after clear can approve: false
~~~

**Result interpretation:**

1. The main thread context is Lan, who lacks `invoice:approve` → denied.
2. After switching the context to Minh, calling `canApprove()` **at the new point in time** sees `invoice:approve` → allowed.
3. The new thread has its own `ThreadLocal`, so it does not automatically see the main thread's actor.
4. `savedOldActor` still holds Lan even though the current actor changed to Minh → an old snapshot **does not represent the current actor**.
5. `CURRENT.remove()` cleans up the main thread's context, preventing stale values in subsequent processing.

This example **does not mean a production application should switch identities mid-request**. It demonstrates why you must use proper per-request context binding infrastructure, why you must not cache authentication for reuse, and why crossing threads requires explicit mechanisms.

## 15. Testing: verifying who is visible when the policy runs

A good test suite should cover **at least two different users** as well as an unauthenticated case. For example, endpoint `GET /api/invoices/{id}` with a read permission rule and an owner/tenant policy:

| Context | When policy retrieves Authentication | Expected outcome |
|---|---|---|
| Lan has `invoice:read`, reads Lan's invoice | Principal is Lan | Allowed |
| Binh has `invoice:read`, reads Lan's invoice | Principal is Binh | Denied by object policy |
| Lan lacks `invoice:read` | Principal is Lan, missing authority | Denied |
| No login/token sent | No real authentication or anonymous | Denied per configuration |
| JWT has read scope but lacks business permission | Has scope; does not automatically have internal permission | Depends on policy, must not infer |
| Worker task does not propagate context | Worker may lack authentication | Must not implicitly run with caller's permissions |
| Thread context cleared at end of request | Next run does not carry old identity | No cross-user leakage |
| Role just revoked but token/session not refreshed | Authentication may still hold old permissions | Must meet freshness/revocation policy |

In Spring Security MVC tests, `@WithMockUser` or the `user(...)` request post-processor helps simulate authentication. However, a mock user **does not prove** that real JWT validation, session persistence, or role/claim mapping works correctly. Those stages must be tested separately when relevant to security requirements.

Example test snippet in a project with Spring Security Test and a protected `GET /api/me` endpoint:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

// mvc is MockMvc configured with Spring Security test setup.
mvc.perform(get("/api/me").with(user("lan")
                .authorities(new SimpleGrantedAuthority("invoice:read"))))
        .andExpect(status().isOk());
~~~

The line-wrapped `import static` statements in this snippet only illustrate **the test class packages**; when placing them in real Java source, write each import on **one valid Java line**. Because it depends on `mvc`, the endpoint, and test dependencies, this is a snippet, not a standalone JDK example. Test goal: the rule is evaluated with the Authentication of **that request**, not a fixed value leftover from a previous test.

You can use method security tests to verify that the policy sees the right `authentication.name` and authorities for each invocation. To test for thread leaks, run two consecutive tasks with different identities on the same executor and verify the second task does not see the first actor after cleanup.

## 16. Common mistakes when retrieving Authentication

| Mistake | Impact | Fix |
|---|---|---|
| Calling `getAuthentication().getName()` on public requests | `NullPointerException` or mistaking anonymous | Protect endpoint or handle `null`/anonymous |
| Using `isAuthenticated()` as definitive proof of a real user | Anonymous token can report `true` | Use framework trust semantics / proper anonymous checks |
| Storing `Authentication` in a singleton field | Identity leakage across requests/threads | Read/pass per invocation; never hold global state |
| Reading `SecurityContextHolder` before auth filters | Context does not yet contain authenticated user | Move check after auth or use authorization infrastructure |
| Keeping a reference to an old request's authentication | Stale permissions or wrong user | Retrieve at check time, manage permission updates |
| Using `ThreadLocal` inside `@Async` expecting the caller | Worker thread has a different context | Controlled propagation or pass trusted ID |
| Calling `setContext` without `clearContext` on custom threads | Thread pool may retain stale identity | `try/finally` and proper cleanup |
| Calling only `setContext` in custom login expecting persistence | Not saved to repository as needed | Use `SecurityContextRepository.saveContext` when session persistence is needed |
| Casting principal to `UserDetails` in a JWT app | `ClassCastException` | Rely on actual authentication type and an identity adapter |
| Checking only `hasRole` without owner/tenant checks | Data leak despite valid authority | Object-level policy and query scoping |
| Seeing `permitAll` and assuming holder is always empty | Misunderstanding delayed lookup | Distinguish rule lookup from authentication filters |
| Trying to use Servlet holder in a reactive pipeline | Wrong context across thread switches | Use `ReactiveSecurityContextHolder`/Reactor Context |
| Logging tokens, passwords, or full principals | Credential/PII exposure | Log only what is needed, mask sensitive data |

## 17. Checklist when writing a new permission check

1. **Where does the principal come from?** Session, username/password, JWT, or another mechanism?
2. **At what moment?** Inside a filter, controller, method interceptor, service, or background task?
3. **Which execution context?** Servlet thread, task executor, or Reactor Context?
4. **What object is read?** Full `Authentication`, `principal`, or only a verified name/ID?
5. **Can it be null/anonymous?** If so, what is the handling policy?
6. **Which authorities are required?** `ROLE_*`, business permission, or mapped `SCOPE_*`?
7. **Is a resource-level policy needed?** Tenant, owner, sharing relationships, state?
8. **Is context reused across calls?** Do not hold users in singletons or global caches.
9. **Must permissions be fresh?** Is a refresh/revocation mechanism needed for recently revoked roles?
10. **Do tests cover different users?** Test allow/deny, anonymous, async, cross-tenant, and expired tokens where relevant.

### Self-assessment questions

**Q1.** `SecurityContextHolder.getContext()` returns a context object, so is `getAuthentication()` guaranteed to be non-`null`?  
**No**. The context can be empty before authentication, outside a request, or in a worker thread.

**Q2.** Why might `authentication.isAuthenticated()` not be sufficient to identify a logged-in user?  
Because `AnonymousAuthenticationToken` can be marked authenticated; use the anonymous/authenticated semantics provided by Spring Security.

**Q3.** Does `AuthorizationFilter` always force reading `Authentication` on every request?  
**No**. Rules like `permitAll` and `denyAll` do not necessarily call `Supplier<Authentication>.get()`.

**Q4.** Does `@PreAuthorize("hasAuthority('invoice:read')")` by itself decide whether the caller can read someone else's invoice?  
**No**. It only checks the authority; permission on an individual invoice requires a resource policy.

**Q5.** Why might `SecurityContextHolder` inside `@Async` not contain the servlet request's user?  
Because by default the context is bound to `ThreadLocal` and the worker is a different thread; explicit propagation is needed when business logic requires it.

**Q6.** Is calling only `SecurityContextHolder.setContext(context)` enough to keep a login for the next request?  
**You should not assume so**. You must consider `SecurityContextRepository` and the authentication flow's context-saving mechanism, especially for custom login in Spring Security 6.

**Q7.** Does reading `Authentication` at 10:07 guarantee that roles reflect a database change made at 10:05?  
**No**. The active `Authentication` may carry old authorities from the session/JWT; a freshness/revocation mechanism is needed when policy requires it.

**Q8.** What is the appropriate way to read `Authentication` in reactive Spring WebFlux?  
Use `ReactiveSecurityContextHolder`/Reactor Context or supported reactive injection mechanisms, rather than relying arbitrarily on Servlet `ThreadLocal`.

## 18. Official reference documentation

- Spring Security – Servlet Authentication Architecture (SecurityContextHolder, SecurityContext, Authentication): https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security – Authorize HTTP Requests (AuthorizationFilter, Supplier Authentication): https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security – Method Security (authentication/principal expressions): https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security – Anonymous Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/anonymous.html
- Spring Security – Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security – Concurrency Support: https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html
- Spring Security – Spring MVC Integration: https://docs.spring.io/spring-security/reference/servlet/integrations/mvc.html

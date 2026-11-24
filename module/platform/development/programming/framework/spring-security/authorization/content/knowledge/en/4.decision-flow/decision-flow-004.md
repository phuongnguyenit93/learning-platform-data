# Supplier<Authentication> and On-Demand Identity Retrieval

## 1. The problem: why does an authorization decision receive a Supplier?

When an HTTP request arrives at a Spring Security application, the system must decide: **allow or deny**. Not every decision needs to know who the sender is. For example, a public status path may be allowed for everyone, while an unregistered URL may be denied to everyone. In those two cases, retrieving the identity only to discard it is unnecessary.

For permission-dependent rules, the system does need to read the current `Authentication` to check identity, authentication state, and `GrantedAuthority`. That is why Spring Security's `AuthorizationManager` API accepts a **`Supplier<Authentication>`** instead of forcing every rule to eagerly receive a pre-fetched `Authentication` object.

A `Supplier<T>` is a standard Java functional interface with a `T get()` method. It represents an operation *that can be executed when needed*. For `Supplier<Authentication>`, the goal is to defer retrieving the authentication object until the rule actually needs it.

```text
HTTP request
    |
    v
Security Filter Chain
    |
    v
AuthorizationFilter
    | creates Supplier<Authentication>
    | does not necessarily retrieve Authentication yet
    v
AuthorizationManager
    |
    +-- permitAll / denyAll
    |       |
    |       +-- decides by rule, no need to call supplier.get()
    |
    +-- authenticated / hasAuthority / user-based rule
            |
            +-- needs identity info, calls supplier.get()
                     |
                     v
                SecurityContext
                     |
                     v
                Authentication
                     |
                     v
              permission decision (grant / deny)
```

**Key point:** "on-demand identity retrieval" here means **deferring reading `Authentication` from the security context**; it does not mean every `get()` call automatically logs the user in, queries an IdP/LDAP, or refreshes tokens. Those authentication or permission-loading steps belong to other mechanisms.

## 2. Recap of components in the decision flow

| Component | Role |
| --- | --- |
| `Authentication` | Represents the principal and authentication result; contains `principal`, `authorities`, and additional details |
| `GrantedAuthority` | Permission/role/scope that rules can inspect, e.g. `document:read` |
| `SecurityContext` | Holds the `Authentication` of the current execution flow |
| `SecurityContextHolder` | How the application accesses `SecurityContext` (usually `ThreadLocal`-based by default in Servlet apps) |
| `Supplier<Authentication>` | Supplies `Authentication` when `get()` is called |
| `AuthorizationManager<T>` | Decides allow/deny on the protected object `T` |
| `AuthorizationFilter` | Puts the Servlet request through authorization checks before continuing processing |
| `RequestAuthorizationContext` | Request context used during HTTP authorization |
| `SecurityFilterChain` | Filter chain where authentication, request protection, and authorization coordinate |

An easy point of confusion: `Authentication` is not a full user profile record in the database; it is an object representing the identity and authorities produced by the authentication mechanism. Just because `authentication.getName()` returns a username **does not mean** all document access conditions have been checked.

### 2.1. Authentication and authorization processes are distinct

**Authentication** decodes/verifies bearer tokens, checks login credentials, restores sessions, or establishes a principal depending on architecture. **Authorization** reads the authentication result and evaluates policy. The supplier in `AuthorizationManager` is a means to access that result, not a replacement for the authentication step.

For instance, with a JWT resource server, the bearer token authentication filter may need to decode and verify the JWT before `AuthorizationFilter` runs. The fact that a `permitAll()` rule does not invoke the supplier **does not automatically guarantee** every upstream filter skips the token or performs no other work.

### 2.2. `SecurityContextHolder` and the current context

In a typical Servlet application, Spring Security stores the context for the thread handling the request, usually via a `ThreadLocal`-based strategy. When a rule needs `Authentication`, the supplier mechanism can read from `SecurityContextHolder`. Depending on how `SecurityContextRepository` and the filters are configured, loading the context from storage may also be deferred.

Do not infer that this is a global cache or an object that lives forever across all requests. Every request must pass through the appropriate security chain, and propagating context to asynchronous threads must be done deliberately.

## 3. `Supplier<T>` in Java: a very simple deferral mechanism

### 3.1. How do eager and lazy differ?

Fetching data eagerly:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

// Already requested reading Authentication before knowing whether the rule needs it.
boolean allowed = publicEndpoint || hasPermission(authentication);
```

On-demand retrieval (code illustrating the idea):

```java
Supplier<Authentication> authentication =
    () -> SecurityContextHolder.getContext().getAuthentication();

// Can decide to allow immediately without calling get().
boolean allowed = publicEndpoint
    || hasPermission(authentication.get());
```

In the second expression, Java uses **short-circuit evaluation** of `||`: if `publicEndpoint` is `true`, the right-hand side does not run and `authentication.get()` is never called. This illustrates the Java mechanism, **not the full internal code of Spring Security**.

A `Supplier` merely describes an operation. **Creating a supplier does not execute the operation**. However, if a rule author calls `get()` at the start of the method before checking the public branch, they lose the deferral benefit.

### 3.2. Lazy does not mean memoization

Consider a supplier:

```java
Supplier<String> supplier = () -> expensiveLookup();
```

Each call to `supplier.get()` **can** re-execute `expensiveLookup()`. The `Supplier` interface does not promise single computation, does not automatically cache the result, and does not guarantee an immutable outcome. Depending on the implementation, it may return an object already sitting in the context or trigger another deferred loading mechanism.

In Spring Security, when `get()` is called multiple times, do not assume a one-to-one correspondence with database queries, session reads, or token checks. Those details depend on the filters, `SecurityContextHolderStrategy`, `SecurityContextRepository`, and the supplier implementation.

### 3.3. Defer reading, never defer the responsibility to check

If a rule needs to check authorities, it must obtain a trusted `Authentication` and compare permissions. Deferring to save work must never turn into "couldn't read it, so let it pass":

```text
If the rule does not depend on identity:
    decide by static policy (permit / deny)

If the rule depends on identity:
    retrieve Authentication from trusted security source
    if missing/invalid -> never implicitly allow
    if present -> evaluate the full policy
```

A custom manager must also clearly define the outcome when no decision is made. In Spring Security 6.3, `AuthorizationManager.check(...)` can return `null` to indicate no decision (*abstain*). Do not use `null` to express an important business denial; return `new AuthorizationDecision(false)` when you actually need to deny.

## 4. Java 17: standalone example to observe `get()`

The following snippet has no Spring Security dependencies. It uses `Supplier<Identity>` to simulate "retrieving identity only when the rule needs it". The output prints how many times `get()` is actually called, helping distinguish **deferral** from **caching**.

Save file `DeferredAuthenticationDemo.java`:

```java
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

public class DeferredAuthenticationDemo {

    enum Rule {
        PUBLIC,
        DENY,
        READ_DOCUMENT
    }

    record Identity(String name, Set<String> authorities) {}

    static boolean allowed(
            Supplier<Identity> identitySupplier,
            Rule rule
    ) {
        if (rule == Rule.PUBLIC) {
            return true; // Does not call supplier.get()
        }
        if (rule == Rule.DENY) {
            return false; // Does not call supplier.get()
        }

        // Only this rule requires identity.
        Identity identity = identitySupplier.get();
        return identity != null
            && identity.authorities() != null
            && identity.authorities().contains("document:read");
    }

    public static void main(String[] args) {
        AtomicInteger lookups = new AtomicInteger();

        Supplier<Identity> currentIdentity = () -> {
            lookups.incrementAndGet();
            return new Identity(
                "An",
                Set.of("document:read")
            );
        };

        System.out.println(
            "public: " + allowed(currentIdentity, Rule.PUBLIC)
        );
        System.out.println(
            "deny: " + allowed(currentIdentity, Rule.DENY)
        );
        System.out.println(
            "lookups after constants: " + lookups.get()
        );

        System.out.println(
            "read document: "
                + allowed(currentIdentity, Rule.READ_DOCUMENT)
        );
        System.out.println(
            "lookups after first read: " + lookups.get()
        );

        System.out.println(
            "read again: "
                + allowed(currentIdentity, Rule.READ_DOCUMENT)
        );
        System.out.println(
            "lookups after second read: " + lookups.get()
        );

        Supplier<Identity> noPermission =
            () -> new Identity("Binh", Set.of());

        System.out.println(
            "missing permission: "
                + allowed(noPermission, Rule.READ_DOCUMENT)
        );
        System.out.println(
            "missing principal: "
                + allowed(() -> null, Rule.READ_DOCUMENT)
        );
    }
}
```

Compile/run with JDK 17 or higher:

```bash
javac DeferredAuthenticationDemo.java
java DeferredAuthenticationDemo
```

Expected output:

```text
public: true
deny: false
lookups after constants: 0
read document: true
lookups after first read: 1
read again: true
lookups after second read: 2
missing permission: false
missing principal: false
```

Analysis:

1. Both the public rule and the deny rule decide without needing identity: the counter stays `0`.
2. The first document read must retrieve identity: the counter becomes `1`.
3. Calling the same supplier again still runs the lambda body: the counter becomes `2`; `Supplier` **does not memoize automatically**.
4. Without the permission or without a principal, reading the document is not allowed.
5. The `false` outcome in this plain Java example is a rule we wrote; it **does not fully model** Spring Security's exceptions and anonymous handling.

All `Identity` objects in the program are dummy data for learning. In a real application, never accept a `Supplier` from an HTTP request or trust a client-supplied `Identity` object; `Authentication` must come from a trusted authentication mechanism.

## 5. Real Spring Security flow during HTTP authorization

This section describes the Servlet flow using `authorizeHttpRequests` and `AuthorizationFilter` in Spring Security 6.x.

### 5.1. Four stages of a decision

**Stage 1 — Authentication filters prepare the context.** Depending on the mechanism (session, form login, bearer token, etc.), Spring Security processes the required evidence to create/restore `SecurityContext`. Not every request has a logged-in user: it could be anonymous, an unauthenticated request, or a context not yet loaded at the start.

**Stage 2 — `AuthorizationFilter` creates the supplier.** This filter creates a `Supplier<Authentication>` that fetches the current identity from the security context and passes both the supplier and the request to the `AuthorizationManager`. Since the supplier is only the capability to fetch data, this step by itself does not force retrieving the principal.

**Stage 3 — `AuthorizationManager` selects and evaluates the rule.** For example, the routing manager matches `requestMatchers(...)` to pick the appropriate rule. A `permitAll()` or `denyAll()` rule can return a decision immediately; `authenticated()`, `hasAuthority(...)`, or principal-based checks need to retrieve `Authentication`.

**Stage 4 — Proceed or block.** If allowed, processing continues toward the application; otherwise, the flow is blocked and the appropriate security error-handling filters take over. In typical API configurations, missing authentication can lead to 401, while missing permissions can lead to 403. The exact code also depends on `AuthenticationEntryPoint`, `AccessDeniedHandler`, and client type.

### 5.2. Why do `permitAll()` and `denyAll()` usually not need to read identity?

Suppose:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/internal/retired").denyAll()
    .requestMatchers("/api/reports/**")
        .hasAuthority("report:read")
    .anyRequest().denyAll()
);
```

- `GET /public/help`: the policy decides to allow access for all principals; the `permitAll` rule does not need to retrieve `Authentication`.
- `GET /internal/retired`: denies all principals; the `denyAll` rule does not need to retrieve `Authentication`.
- `GET /api/reports/7`: needs to check the `report:read` permission, so the manager must access `Authentication`.
- Requests not allowed by any rule: the final `denyAll` rule denies them; do not create an implicit "default permission" for logged-in users.

This reduces unnecessary authentication-reading work at constant decision points. **Do not interpret this as "public access never touches session/JWT"**: the filter chain may still have performed other operations before reaching the authorization filter. Actual impact depends on configuration and request flow.

### 5.3. When is the supplier called?

| Rule or situation | Is `Authentication` needed to decide? | Key point |
| --- | --- | --- |
| `permitAll()` | No | Static allow decision |
| `denyAll()` | No | Static deny decision |
| `hasAuthority("report:read")` | Yes | Needs the current list of `GrantedAuthority` |
| `hasRole("ADMIN")` | Yes | Usually checks `ROLE_ADMIN` |
| `authenticated()` | Yes | Needs to distinguish a truly authenticated user from anonymous |
| Custom manager depending on user/tenant | Yes | Calls `get()` and checks context, scope, and object |
| Custom manager checking only a static feature flag | Possibly no | Do not call `get()` if the outcome truly does not depend on the user |

The table describes **what the rule itself needs**, not a guarantee that the supplier is called exactly once. A custom manager might call it multiple times, and other security components might have already accessed the context earlier.

### 5.4. Anonymous authentication and the `isAuthenticated()` expression

In configurations with `AnonymousAuthenticationFilter`, an unlogged-in user can be represented by `AnonymousAuthenticationToken`. This object can report `isAuthenticated() == true` per the token object contract, yet Spring Security still recognizes it as **anonymous** when using the corresponding `authenticated()` manager/expression.

Therefore, for protective rules requiring real authentication, **do not replace** `authenticated()` with `authentication != null && authentication.isAuthenticated()` and conclude anonymous access is blocked. Use Spring Security's authentication policy or an appropriate `AuthenticationTrustResolver`.

### 5.5. Missing `Authentication` does not mean access is granted

If a filter/manager needs `Authentication` and the context does not contain a valid object, an exception related to missing authentication can occur and be handled by another filter. Exact details depend on the context strategy and authentication configuration. Never write a custom manager like this:

```java
// WRONG: missing context results in allowing access.
Authentication a = authentication.get();
if (a == null) {
    return new AuthorizationDecision(true);
}
```

Instead, deny access or let Spring's standard authentication error flow handle it. If using standalone check logic, `new AuthorizationDecision(false)` explicitly expresses a deny decision.

## 6. Using `Supplier<Authentication>` in a custom AuthorizationManager

### 6.1. Choosing the right API for your version

Spring Security's API has evolved across versions:

- In **Spring Security 6.3**, `AuthorizationManager<T>` has the primary method `check(Supplier<Authentication>, T)` returning `AuthorizationDecision` (or `null` when abstaining).
- Starting with **Spring Security 6.4**, the new `authorize(...)` method/result type was added, and `check(...)` was marked deprecated in later versions. When upgrading, check the exact JavaDoc and signatures in use.
- The following examples intentionally use **`check(...)` as in Spring Security 6.3**, fitting Spring Boot 3.3 / Security 6.3 projects. Do not mix Security 7 signatures with 6.3 code.

Official documentation: [AuthorizationManager 6.3.3 API](https://docs.spring.io/spring-security/site/docs/6.3.3/api/org/springframework/security/authorization/AuthorizationManager.html) and [Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html).

### 6.2. A rule checking an authority

This is **Spring Security 6.3 integration code in a Servlet application**, not a standalone runnable Java file:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

@Configuration
public class DocumentAuthorizationConfig {

    @Bean
    AuthorizationManager<RequestAuthorizationContext> documentReader() {
        return (authenticationSupplier, requestContext) -> {
            // Retrieve Authentication because this rule requires an authority.
            Authentication current = authenticationSupplier.get();

            boolean mayRead = current != null
                && current.getAuthorities().stream()
                    .anyMatch(authority ->
                        "document:read".equals(authority.getAuthority()));

            return new AuthorizationDecision(mayRead);
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/public/ping")
                .permitAll()
            .requestMatchers(HttpMethod.GET, "/api/documents/**")
                .access(documentReader())
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
```

What is happening:

1. `requestMatchers(...)` selects the rule per request; `documentReader()` is invoked while building the configuration to obtain the manager bean, whereas **decision execution** inside the lambda only occurs when a matching request passes through authorization.
2. Because `documentReader` requires an authority, it calls `authenticationSupplier.get()`. This is the on-demand `Authentication` retrieval point.
3. The rule compares the string `document:read` against `GrantedAuthority.getAuthority()`; if absent, it denies.
4. `.access(...)` attaches the custom manager to the path. `permitAll/denyAll` on other routes do not run the identity-reading logic in this manager.
5. The example omits authentication configuration: a real application must configure an appropriate mechanism to create `Authentication`, such as session login or OAuth2 Resource Server.

In practice, if you only want to check a single authority, `.hasAuthority("document:read")` is shorter and preferred. Write a custom manager when you need special logic such as request-dependent constraints, business policies, or a permission service. **Do not rewrite all of the framework's authentication/anonymous features yourself.**

### 6.3. Conditionally deferred custom rule

A manager can decide based on static information first and only call the supplier when needed. Illustrative lambda snippet (not a complete class):

```java
AuthorizationManager<RequestAuthorizationContext> manager =
    (authentication, context) -> {
        String path = context.getRequest().getRequestURI();

        if ("/public/ping".equals(path)) {
            // Do not call authentication.get() in this branch.
            return new AuthorizationDecision(true);
        }

        if ("/admin/disabled".equals(path)) {
            return new AuthorizationDecision(false);
        }

        Authentication principal = authentication.get();
        boolean allowed = principal != null
            && principal.getAuthorities().stream()
                .anyMatch(a -> "document:read".equals(a.getAuthority()));

        return new AuthorizationDecision(allowed);
    };
```

In real deployments, prefer `requestMatchers` to choose policies for different routes; avoid ad-hoc URL checks that easily break due to context paths, route variables, proxies, encoded URLs, delimiters, and HTTP methods. The snippet's purpose is to make **where `get()` is placed** clear.

Note on **resource permission checks**: having `document:read` is not enough for every document. To view `/api/documents/123`, the service/repository must also verify the tenant, owner, sharing, and state of document 123.

### 6.4. Why is the supplier not a replacement for method security?

Request authorization decides passage through the HTTP layer. A service function may be called from a job, a message consumer, or another controller. When an operation carries business significance, checks are still needed at the service entry point or via an appropriate data policy. The supplier provides identity for a decision; it **does not guarantee** every call site for a feature passes through the same manager.

You can use `@PreAuthorize("hasAuthority('document:read')")` and object-level policies in the service when appropriate. When using method security via Spring AOP proxies, understand that self-invocation can bypass the proxy. Never treat URL protection as the sole guarantee for object-level permissions.

## 7. Trust boundaries: the supplier does not create a new identity

This section is critical to avoid flawed reasoning when optimizing the decision flow.

### 7.1. The trusted source is the request's SecurityContext

A properly configured authentication filter is responsible for placing a trusted `Authentication` into the context. The supplier in authorization uses this result. Never write:

```java
// WRONG: caller sends userId and authorities are constructed from it.
Supplier<Authentication> authentication =
    () -> new UsernamePasswordAuthenticationToken(
        request.getHeader("X-User"),
        null,
        List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
    );
```

The snippet above **intentionally illustrates a security vulnerability** and must never be used in an application. A client-controlled `X-User` header does not prove who is logged in. When multiple identity sources are needed, authenticate through a trusted filter/provider chain rather than turning raw request data into a privileged principal.

### 7.2. The supplier does not refresh roles/JWTs when `get()` is called

Suppose a JWT containing the `report:approve` authority has been verified and placed into `SecurityContext`. If the user's permission is revoked in the IdP, calling `authentication.get()` does not automatically query the IdP to re-check current groups. How long the permission remains effective depends on token lifetime, revocation mechanisms, dynamic permission lookups, or session/cache design.

If the application requires near-real-time permission revocation, you need an explicit mechanism such as short-lived tokens, per-request policy lookup with caching and invalidation, or session/token revocation per architecture; **never treat `Supplier` as a revocation mechanism**.

### 7.3. The supplier is not inherently thread-safe across threads

In Servlet apps, `SecurityContextHolder` defaults to a thread-bound strategy. Storing a supplier in a singleton field or passing it to an executor and calling `get()` there can access a different context or find no context after the request finishes.

When running `@Async`, `CompletableFuture`, scheduled tasks, or message consumers, explicitly design the execution identity. If security context must be carried intentionally, consider Spring Security's context-propagation utilities (such as `DelegatingSecurityContextRunnable`/`DelegatingSecurityContextExecutor` for the corresponding task), while verifying timing and permission scope. Do not automatically copy the caller's session, credentials, or permissions into long-lived background tasks.

### 7.4. Never share a supplier across requests

A supplier created to access identity within a single request must live only within the corresponding decision scope. Do not store it in `static` variables, singleton fields, or global caches. If the supplier relies on thread-local state, its result can vary with thread context, causing user misidentification or unintended authorization grants.

If you need to cache business permission decisions, define the cache key by user/tenant/action/resource/policy version, TTL, and invalidation mechanism. **A `Supplier` is not a cache** and does not solve stale permissions.

## 8. Testing deferral and access decisions

A good test should distinguish three things: **whether the right rule is selected**, **whether the rule needs to read `Authentication`**, and **whether the final decision matches business permissions**.

### 8.1. Test matrix

| Case | Rule | Expected decision | Expected `get()` calls |
| --- | --- | --- | --- |
| Public endpoint | `permitAll` | Allow | This rule does not need to call it |
| Always-locked endpoint | `denyAll` | Deny | This rule does not need to call it |
| API with sufficient `document:read` | `hasAuthority` | Allow | Needs `Authentication` |
| API missing authority | `hasAuthority` | Deny | Needs `Authentication` |
| Unauthenticated | `authenticated` | Block from protected API | Needs to evaluate auth state |
| Custom manager checking static config only | Custom | Per policy | Can be 0 |
| Custom manager checking tenant/owner | Custom | Per real policy | Needs principal and object data |
| Manager calls `get()` twice | Custom | Per manager logic | Can be 2; not auto-cached |
| Background task without proper context | Custom using current context | Do not implicitly allow | Depends on context propagation design |

**Note:** the supplier call count in a simulated test only proves that specific manager's logic. Do not use a counter at one point to conclude the number of DB/session/token reads across the entire pipeline.

### 8.2. Unit testing a Spring Security 6.3 manager

Below is an **illustrative body of a JUnit test**; assume you already have the `AuthorizationManager<RequestAuthorizationContext> documentReader` bean, `HttpServletRequest request`, and the required Spring Security and JUnit imports:

```java
AtomicInteger calls = new AtomicInteger();

Authentication reader =
    new UsernamePasswordAuthenticationToken(
        "an",
        null,
        List.of(new SimpleGrantedAuthority("document:read"))
    );

Supplier<Authentication> supplier = () -> {
    calls.incrementAndGet();
    return reader;
};

RequestAuthorizationContext context =
    new RequestAuthorizationContext(request);

AuthorizationDecision result =
    documentReader.check(supplier, context);

assertNotNull(result);
assertTrue(result.isGranted());
assertEquals(1, calls.get());
```

This snippet shows how to verify that the manager calls `get()` when an authority is required; it is **not a standalone Java program**. The corresponding test for a caller lacking permissions should expect `AuthorizationDecision(false)`. For a public rule, creating a supplier that throws `AssertionError` if invoked verifies that identity is not accessed unexpectedly:

```java
Supplier<Authentication> unexpectedLookup = () -> {
    throw new AssertionError("Authentication should stay deferred");
};

// Invoke the actual manager representing permitAll in the test configuration.
// If it calls unexpectedLookup.get(), the test must fail.
```

Remember: in Spring Security 6.4 and later, the API can use `authorize(...)` with the new result type. Do not copy signatures verbatim from another version and assume errors are caused by the supplier.

### 8.3. Integration testing with `MockMvc`

In a Spring MVC app with `spring-security-test`, test public routes, authorized routes, missing permissions, and unauthenticated requests using `MockMvc`. For POST/PATCH/DELETE, if CSRF is enabled, tests should include a valid CSRF token when testing authorization policies; otherwise, a 403 code may come purely from CSRF.

Test helpers such as `user(...)` or `jwt(...)` set up a mock principal and do not prove that password checks, JWT signatures, audiences, or issuers are validated in a real environment. Add dedicated authentication tests when that is required.

### 8.4. Evidence-based performance measurement

To evaluate deferral benefits, you can measure:

- Request volume hitting public/always-denied routes.
- Context access counts and session load counts when configuration permits measuring them.
- Authorization processing time and cache hit ratio, if applicable.
- Cost of bearer token validation, database queries, and upstream filters.

If overall request latency shows no improvement, do not conclude `Supplier` is useless: most of the cost may lie in other filters or business logic. Conversely, never claim "`permitAll` never touches the database" without measuring in your specific architecture.

## 9. Common mistakes when using `Supplier<Authentication>`

| Mistake | Problem | Fix |
| --- | --- | --- |
| Calling `get()` at the start of every manager | Loses deferral benefit on static branches | Select the rule first, read only when needed |
| Assuming `Supplier` is a cache | Calling `get()` multiple times may repeat work | Understand the implementation; if caching is needed, design explicit scope |
| Thinking `get()` re-validates the JWT | Revoked permissions may still appear valid | Separate token validation, refresh, and revocation |
| Thinking `permitAll` skips the entire filter chain | Token/session or other filters may still run | Distinguish the authorization rule from the full pipeline |
| Checking `auth.isAuthenticated()` alone is enough | Anonymous tokens can count as authenticated via internal flag | Use `authenticated()` rules and trust resolver |
| Missing auth sets `allow = true` | Leaves protected API open | Deny by default or let the framework handle errors |
| Using `null` to express denial | Can mean abstain, causing condition misunderstandings | Return `AuthorizationDecision(false)` when denying |
| Reading role from client header and wrapping in supplier | Users can grant themselves privileges | Only take principals/authorities from trusted auth sources |
| Holding supplier in singleton/async job | Thread context is wrong or expired | Keep proper request scope, propagate context deliberately |
| Protecting URLs only, skipping object permissions | IDOR/BOLA: changing ID accesses someone else's data | Enforce at service/repository and by tenant |
| Mixing 6.3 `check` and 6.4+ `authorize` APIs | Version mismatch, errors on upgrade | Check JavaDoc for the exact version |
| Inferring DB read count from `get()` count | Wrong performance assessment | Measure at the context repository and authentication layers |

## 10. Process for applying in a project

1. **Confirm the Spring Security version** in use to choose the right `AuthorizationManager` signature. For Spring Boot 3.3 / Security 6.3, use `check(...)` in custom manager examples.
2. **Trace the request path** through the security chain: authentication filters, context, `AuthorizationFilter`, manager, handler/controller, and service.
3. **Define the URL policy:** public endpoints, always-blocked endpoints, endpoints requiring authorities. Use `anyRequest().denyAll()` to close unhandled cases.
4. **Write a custom manager only when needed** and use the supplier purposefully: static rules do not read, identity-dependent rules call `get()` during evaluation.
5. **Verify data received from `Authentication`:** principal, authorities, role/scope mapping mechanism; never infer tenant/owner from unverified request data.
6. **Protect business logic and data** in the service/repository, including access to the same resource via non-HTTP channels.
7. **Test** public/denied/authorized/unauthorized/anonymous routes, check call counts in unit tests, and verify no data leaks.
8. **Check async behavior and permission revocation** if the system uses queues, background jobs, long-lived tokens, or session caches.
9. **Measure real performance** when optimization is a goal; do not assume every supplier saves the same amount of resources.
10. **Review on upgrades:** JavaDoc and tests must stay aligned with the project's Spring Security version.

## 11. Self-check questions

1. **Why does `AuthorizationManager` accept `Supplier<Authentication>`?** To retrieve identity only when a decision depends on principal/authorities, avoiding unnecessary lookups on static rules.
2. **Does creating a supplier automatically retrieve `Authentication`?** No; the supplier body runs when `get()` is called.
3. **Does `permitAll()` guarantee no filter accesses the session/JWT?** No. You can only state that the static allow rule does not need to read `Authentication` to decide.
4. **Does calling `get()` twice automatically return the same cached result?** There is no such guarantee from the `Supplier` interface; the implementation decides.
5. **Does `get()` re-check groups in the IdP after a user's permission is revoked?** Not automatically; dedicated authentication/refresh/revocation mechanisms are required.
6. **Why is `isAuthenticated()` alone error-prone with anonymous users?** Because an anonymous token can be marked authenticated as an object flag; the `authenticated()` rule distinguishes it properly.
7. **Does having `document:read` allow reading another tenant's documents?** No; resource-level policy must be checked.
8. **Is it safe to store a supplier in a singleton and use it in another thread?** You cannot assume so; context defaults to thread-bound and request-scoped, requiring deliberate context propagation.
9. **Which primary `AuthorizationManager` method does Spring Security 6.3 call?** `check(Supplier<Authentication>, T)`; later versions add `authorize(...)`.
10. **What if a custom manager cannot verify identity on a sensitive operation?** Never implicitly allow; fail closed or let the standard authentication error mechanism handle it.

**Remember:** `Supplier<Authentication>` is a **deferred identity-retrieval point in the decision flow**. It lets static rules avoid accessing identity and lets permission-dependent rules retrieve `Authentication` at the right moment. It **does not replace authentication**, **does not auto-cache**, **does not auto-revoke permissions**, and **does not replace tenant/object checks in the business layer**.
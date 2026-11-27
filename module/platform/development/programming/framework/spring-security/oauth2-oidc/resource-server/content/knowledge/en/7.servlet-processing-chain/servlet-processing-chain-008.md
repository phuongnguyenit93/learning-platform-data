# SecurityContextHolder and Identity Scope Within a Request

In a **Spring Security OAuth 2.0/OIDC Resource Server** running on the **Servlet stack** (Spring MVC, `HttpServletRequest`), each HTTP request passes through a security filter chain before reaching a controller. When the client sends a valid access token, Spring Security validates the token, creates an object representing the authenticated subject (`Authentication`), and places it inside `SecurityContext`. Code executing within that same request can access this information through `SecurityContextHolder`.

The key takeaway: **the "current" identity is execution-scoped**, typically bound to the thread processing the request and cleared from the holder when the processing chain completes. It is not a global variable holding the most recently logged-in user. Nor does it automatically follow across arbitrary threads, asynchronous tasks, subsequent requests, or downstream service calls.

This lesson explains the structure of `SecurityContextHolder`, how Spring Security establishes and clears the context in the Servlet filter chain, how to consume JWT/opaque-token principals in controllers and services, and identity boundaries across sessions, async work, error dispatches, executors, and microservices.

## 1. Three Distinct Components: Holder, Context, and Authentication

### 1.1. SecurityContextHolder: Access Point to Current Security Information

`SecurityContextHolder` is the central API allowing Java code to retrieve `SecurityContext`:

```java
import org.springframework.security.core.context.SecurityContextHolder;

var securityContext = SecurityContextHolder.getContext();
```

In a Servlet application, `SecurityContextHolder` uses a **`ThreadLocal`**-based `SecurityContextHolderStrategy` by default. Thus, once a request has passed through the authentication filters, code running on the same thread can read security information without threading an `Authentication` parameter explicitly through every method.

The methods on `SecurityContextHolder` are static, but that **does not mean every request shares a single JVM-wide `Authentication`**. The static API delegates access to a strategy; the default strategy stores the context per thread.

### 1.2. SecurityContext: A Context That Can Hold an Authentication

`SecurityContext` represents the security context, whose most important member is:

```java
Authentication authentication = securityContext.getAuthentication();
```

Not every context already contains an authenticated principal. For example, when no bearer token is present, before the authentication filter runs, or on a background thread without propagated context, `getAuthentication()` may return `null`.

### 1.3. Authentication: Authenticated Principal and Authorities

`Authentication` can represent either an unauthenticated input credential or a successful authentication result. For an **authentication result** in a Resource Server, common members are:

| API | Meaning | In a Resource Server |
|---|---|---|
| `getPrincipal()` | Represented subject | Typically `Jwt` (JWT) or `OAuth2AuthenticatedPrincipal` (opaque token) |
| `getName()` | Principal name supplied by the authentication converter | For JWTs, defaults to the `sub` claim; customizable |
| `getAuthorities()` | `GrantedAuthority` instances | Scopes typically map to `SCOPE_orders.read`, `SCOPE_orders.write` |
| `isAuthenticated()` | State of the `Authentication` object | Do not use this boolean alone to claim an authenticated end user exists |
| `getCredentials()` | Associated credential | May be erased after authentication; never write to logs |
| `getDetails()` | Authentication-mechanism-specific metadata | Never treat client-sent metadata as proof of identity |

```mermaid
flowchart TB
  H["SecurityContextHolder<br/>API to retrieve current context"] --> C["SecurityContext"]
  C --> A["Authentication"]
  A --> P["principal<br/>Jwt / OAuth2AuthenticatedPrincipal"]
  A --> N["name"]
  A --> G["authorities<br/>SCOPE_..."]
  A --> D["details / credentials"]
```

**Authenticated subject** (`authentication`) and **permission on a specific resource** (`authorization`) are two independent questions. A user with `SCOPE_orders.read` is not automatically allowed to view another user's orders.

## 2. How Does SecurityContext Appear in the Servlet Filter Chain?

An HTTP request travels from the Servlet container through `DelegatingFilterProxy` to `FilterChainProxy`. Spring Security selects the `SecurityFilterChain` matching the request. In a Resource Server configuration, filters handle context, bearer credentials, authentication, and authorization before the request reaches `DispatcherServlet`.

```mermaid
sequenceDiagram
    autonumber
    participant C as HTTP Client
    participant F as Servlet Security Filters
    participant H as SecurityContextHolder
    participant M as AuthenticationManager
    participant MVC as Controller / Service
    C->>F: GET /api/orders + Bearer token
    F->>H: Load or prepare context for request
    F->>M: Authenticate credential extracted from request
    M-->>F: Authenticated Authentication
    F->>H: Store Authentication in context
    F->>MVC: Continue filter chain + authorization
    MVC->>H: Read principal, authorities
    H-->>MVC: Authentication for current scope
    MVC-->>F: HTTP response
    F->>H: Clear SecurityContextHolder
    F-->>C: HTTP response
```

Components to recognize:

| Component | Role |
|---|---|
| `FilterChainProxy` | Selects the matching filter chain and manages filter execution |
| `SecurityContextHolderFilter` | Loads/sets up context via `SecurityContextRepository` for the processing scope; clears it at the end |
| `BearerTokenAuthenticationFilter` | Extracts Bearer token, sends to `AuthenticationManager`, and sets `Authentication` on success |
| `AnonymousAuthenticationFilter` | May create an anonymous `Authentication` if no authenticated caller exists yet |
| `ExceptionTranslationFilter` | Translates authentication/authorization errors into an entry point or appropriate response |
| `AuthorizationFilter` | Evaluates URL protection rules against the current `Authentication` |
| `DispatcherServlet` | Invokes controllers/services after required filter steps |

This table describes roles, not the exact filter order for every version and configuration. Participating filters and their order can vary depending on the application's `SecurityFilterChain`.

### 2.1. When the Token Is a JWT

Example client request:

```http
GET /api/orders/ord-123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

Typical flow:

1. `BearerTokenResolver` reads the bearer credential from `HttpServletRequest`.
2. `BearerTokenAuthenticationFilter` constructs `BearerTokenAuthenticationToken`.
3. `AuthenticationManager` invokes the JWT provider, typically `JwtAuthenticationProvider` with `JwtDecoder`.
4. The decoder checks signature, matching algorithm/key, timestamps, issuer, and audience per the API's configured validators.
5. The successful result is typically `JwtAuthenticationToken`, whose principal is a verified `Jwt`.
6. Spring Security sets the context containing `Authentication`, and HTTP authorization, controllers, and services read the verified data.
7. The context is cleared from the holder after the processing scope ends, preventing leakage across requests.

`SecurityContextHolder` **does not decode or verify JWT signatures**. It only holds the context after the authentication mechanism puts the result there.

### 2.2. When the Token Is Verified via Introspection

With opaque token configuration:

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults()))
```

The provider calls `OpaqueTokenIntrospector` to validate the token. The `Authentication` stored in the context is usually `BearerTokenAuthentication`, with an `OAuth2AuthenticatedPrincipal` carrying verified attributes. This means applications using both modes **should not cast every `authentication.getPrincipal()` to `Jwt`**.

### 2.3. When the Token Is Invalid or Absent

An expired token, invalid signature, wrong issuer, wrong audience (when validated), or inactive introspection status is rejected during authentication; typically HTTP **401** and `WWW-Authenticate: Bearer` guide the client.

If a request has no bearer credential, the filter lets it continue; `permitAll()` routes still run, whereas `authenticated()` routes require a valid authentication mechanism. A public request's context may hold `AnonymousAuthenticationToken`. That is not a user authenticated by an access token.

## 3. Thread Scope and Avoiding Identity Mixing Across Requests

In standard synchronous Servlets, picture it like this:

```text
Servlet Thread A                         Servlet Thread B
  Request from user-842                   Request from user-901
  ThreadLocal context A                   ThreadLocal context B
  Authentication(user-842)                Authentication(user-901)
          |                                       |
  Controller A                              Controller B
  Service A                                 Service B
```

Two requests can execute concurrently. On thread A:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
```

returns the `Authentication` corresponding to the context set for **thread A**. Thread B has its own context. That is why synchronous services can read the current identity without passing it as an argument through every layer.

### 3.1. Why Is Cleanup Mandatory?

Servlet containers normally use a **thread pool**. The same thread handles multiple requests over time:

```text
T1: Thread-17 -> request user-842 -> context user-842
    Request ends -> clear context from Thread-17

T2: Thread-17 -> request user-901 -> context user-901
    Request ends -> clear context from Thread-17
```

If someone puts an `Authentication` into a custom `ThreadLocal` or modifies the context without cleaning up, a later request can **see the identity and permissions of the previous request**. Spring Security manages clearing `SecurityContextHolder` inside its standard filter chain. Avoid inventing your own thread-local principal storage that bypasses that lifecycle.

### 3.2. SecurityContextHolder Strategies

| Strategy | Storage | Assessment in a web server |
|---|---|---|
| `MODE_THREADLOCAL` | Separate context per thread | Appropriate default for the Servlet filter chain |
| `MODE_INHERITABLETHREADLOCAL` | Newly spawned child threads can inherit parent thread context | Should not be enabled broadly to "fix" async; hard to control with thread pools |
| `MODE_GLOBAL` | Single shared context across the JVM | Unsuitable for multiple requests/users |

`MODE_GLOBAL` risks mixing identities across different requests. `MODE_INHERITABLETHREADLOCAL` does not guarantee tasks executed on an executor receive the right principal: thread pools may be created before requests arrive, or live long and be reused. To pass identity across async boundaries, use an explicit mechanism.

### 3.3. "One Request = One Thread" Is Only a Simplified Model

Servlets can process requests across `REQUEST`, `ASYNC`, and `ERROR` dispatches; the executing thread can change. A thread can also run code unrelated to an HTTP request. Therefore, understand:

- **On a thread where context has been set:** code can read the current `Authentication`.
- **On a new/executor thread:** it does not have the same context by default.
- **Across multiple Servlet dispatches:** context may need to be reloaded depending on the repository and applied filters.
- **After the response/request ends:** never assume the prior request's context remains on the thread.

## 4. Reading the Authenticated Authentication in Spring MVC

Spring Security and Spring MVC offer multiple ways to access the principal. Choose the approach with the least unnecessary coupling to token format.

### 4.1. Injecting Authentication Directly in a Controller

```java
import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {

    @GetMapping("/api/me")
    public Map<String, Object> me(Authentication authentication) {
        return Map.of(
            "principal", authentication.getName(),
            "authorities", authentication.getAuthorities().stream()
                .map(authority -> authority.getAuthority())
                .toList()
        );
    }
}
```

This example assumes `/api/me` is protected and has a valid `Authentication`. In real products, return only the identity/authority fields the client truly needs; **never return raw tokens, credentials, or all claims arbitrarily**.

Accepting `Authentication` is useful when the controller only needs the name/authorities, or when the application can accept both JWT and opaque tokens.

### 4.2. Injecting a Verified JWT via @AuthenticationPrincipal

On a route using a JWT Resource Server, `JwtAuthenticationToken`'s principal is normally `Jwt`:

```java
import java.util.List;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/api/orders/mine")
    public List<OrderDto> myOrders(@AuthenticationPrincipal Jwt jwt) {
        String issuer = jwt.getIssuer().toString();
        String subject = jwt.getSubject();
        String tenantId = jwt.getClaimAsString("tenant_id");

        return orderService.findVisibleOrders(issuer, subject, tenantId);
    }
}
```

`OrderService` and `OrderDto` are application-defined business types. The `Jwt` in this example comes from **Spring Security after verification**, not from a controller manually Base64-decoding a payload. When accepting multiple issuers, system-wide identity typically needs the pair `issuer + subject` or a properly linked internal identifier.

Claims such as `tenant_id` must have an agreed meaning between IdP and API. Even after authenticating the token, the application must still match the tenant against the accessed records.

### 4.3. Injecting an Opaque Token Principal

```java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OpaqueIdentityController {

    @GetMapping("/api/opaque/me")
    public String me(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
        return principal.getName();
    }
}
```

This example requires the route to pass through an opaque Resource Server chain whose introspector creates the matching principal. Do not cast to `Jwt` if the app uses `BearerTokenAuthentication`.

### 4.4. Using @CurrentSecurityContext

```java
@GetMapping("/api/identity")
public String identity(
        @CurrentSecurityContext(expression = "authentication")
        Authentication authentication) {
    return authentication.getName();
}
```

The `@CurrentSecurityContext` annotation belongs to `org.springframework.security.core.annotation` and lets Spring MVC extract the context or a specified property. In a controller, you can also accept `Authentication` directly as shown earlier.

### 4.5. Reading the Context in a Service When Truly Necessary

```java
import java.util.Optional;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

@Component
public class CurrentPrincipal {

    public Optional<Authentication> authenticated() {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();

        if (auth == null || auth instanceof AnonymousAuthenticationToken
                || !auth.isAuthenticated()) {
            return Optional.empty();
        }
        return Optional.of(auth);
    }
}
```

`AnonymousAuthenticationToken` can return `isAuthenticated() == true`. Therefore, **checking this boolean alone is not enough to confirm the request has a valid bearer principal**. When using the API directly, distinguish anonymous tokens or use an appropriate `AuthenticationTrustResolver`. At the HTTP/method security layer, prefer `authenticated()` and standard authorization expressions.

Reading the holder deep inside every repository/service creates an implicit dependency on thread state. A more testable and async-friendly approach is converting the authenticated principal into a **small, immutable actor object** and passing it as a business method parameter.

## 5. Identity Scope in the Business Layer: CurrentActor

Suppose a verified bearer JWT contains:

```json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_id": "tenant-a"
}
```

Distinguish:

1. The JWT is valid in signature/issuer/audience/time and carries the authority to **read orders**.
2. Whether the subject has permission to **read the specific order ORD-123**.

Pattern using Java 17+:

```java
public record CurrentActor(
    String issuer,
    String subject,
    String tenantId
) {}
```

```java
@GetMapping("/api/orders/{orderId}")
public OrderDto readOrder(
        @PathVariable String orderId,
        @AuthenticationPrincipal Jwt jwt) {

    CurrentActor actor = new CurrentActor(
        jwt.getIssuer().toString(),
        jwt.getSubject(),
        jwt.getClaimAsString("tenant_id")
    );

    return orderService.readVisibleTo(actor, orderId);
}
```

Example policy check in the service layer:

```java
public OrderDto readVisibleTo(CurrentActor actor, String orderId) {
    Order order = repository.findById(orderId)
        .orElseThrow(OrderNotFoundException::new);

    boolean ownerMatches =
        order.getOwnerIssuer().equals(actor.issuer()) &&
        order.getOwnerSubject().equals(actor.subject());

    boolean tenantMatches =
        order.getTenantId().equals(actor.tenantId());

    if (!ownerMatches || !tenantMatches) {
        throw new AccessDeniedException("Order access denied");
    }
    return mapper.toDto(order);
}
```

Classes such as `Order`, `OrderDto`, `OrderNotFoundException`, and `repository` are project-specific examples. Real policies may allow admin access within a tenant, check order status, and check payment/customer associations. **A scope in `SecurityContext` is an input to authorization, not a license to skip object checks.**

Passing `CurrentActor` is beneficial because:

- The service knows **who is calling** from an explicit parameter rather than reading implicit thread state.
- There is no need to carry the raw bearer token through business logic just to read `sub`.
- Minimal actor data can be passed to async tasks under explicit policy.
- Business unit tests do not need to mock the entire filter chain or `SecurityContextHolder`.

The actor is purely internal data constructed by the controller from a trusted `Authentication`. If an external client sends JSON `{"subject":"user-842"}`, that JSON **never counts as authentication proof**.

## 6. Stateless Resource Server Configuration and SecurityContext

An example Servlet REST API accepting bearer JWTs from headers:

```yaml
# application.yml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          audiences:
            - orders-api
```

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ResourceServerSecurityConfig {

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            // Appropriate only for APIs using Bearer headers,
            // not cookies/sessions as credentials for write operations.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

In this configuration:

- `oauth2ResourceServer().jwt()` enables the filter/provider validating bearer JWTs.
- `issuer-uri` declares the trusted issuer; `audiences` requires the token to be issued for this API when supported by the Boot version.
- JWT scopes map to authorities, usually prefixed with `SCOPE_`.
- `SessionCreationPolicy.STATELESS` instructs Spring Security **not to create or use an `HttpSession` to retrieve `SecurityContext` for requests**.
- `csrf().disable()` is an option for APIs relying strictly on explicit bearer headers; if the app also has cookie-based authentication, keep appropriate CSRF protection.

A Resource Server must configure an appropriate audience validator; configuring an issuer alone does not guarantee automatic audience checks across every version or custom decoder setup.

### 6.1. Every Request Still Needs a Credential in the Stateless Model

```text
Request 1:
  GET /api/orders/123
  Authorization: Bearer TOKEN_USER_842
  -> Authenticates user-842
  -> SecurityContextHolder holds user-842 for the request scope
  -> Ends, context is cleared

Request 2:
  GET /api/orders/124
  No Authorization
  -> Does not inherit Request 1's identity
```

This is expected behavior. Spring Security creates/loads a fresh context on the next request; bearer auth does not require preserving the same `SecurityContext` Java object across multiple HTTP requests.

## 7. SecurityContextHolder, SecurityContextRepository, and HttpSession Differ

Three frequently confused layers:

| Component | Question answered | Scope |
|---|---|---|
| `SecurityContextHolder` | Where does the currently executing thread obtain the context? | Usually the current thread |
| `SecurityContextRepository` | Where is the context loaded from and saved to? | Depends on repository: per request/dispatch or per session |
| `HttpSession` | What HTTP state does the server keep across multiple requests? | Can span multiple requests |

Important repositories:

- `RequestAttributeSecurityContextRepository` stores context in a **request attribute** to handle multiple Servlet dispatches of **the same request**.
- `HttpSessionSecurityContextRepository` can persist context across `HttpSession` when the application uses an appropriate stateful mechanism.
- `NullSecurityContextRepository` does not persist `SecurityContext` to durable cross-request storage.
- `DelegatingSecurityContextRepository` coordinates multiple repositories per configuration.

### 7.1. SecurityContextHolderFilter in Spring Security 6

In Spring Security 6, the default **explicit save** model uses `SecurityContextHolderFilter`. This filter prepares the context from `SecurityContextRepository` for processing and clears it at the end. To persist context in a repository for other requests, authentication mechanisms or management code must **save it explicitly**.

Spring Security 5 previously used `SecurityContextPersistenceFilter` with an auto-save model for modified contexts. Do not extrapolate from the older version and assume every context mutation is automatically saved in Spring Security 6.

`BearerTokenAuthenticationFilter` may use a repository serving the request/dispatch scope depending on configuration. That **does not mean bearer authentication is automatically saved into a long-lived login session**.

### 7.2. Error Dispatches Within the Same HTTP Request

```text
REQUEST dispatch
    |
    +-- Authenticates user-842
    |
    +-- Controller throws an error
    |
ERROR dispatch
    |
    +-- Renders error page/handling for the same request
```

Depending on the Servlet container and filter setup, the context on the initial dispatch thread may already have been cleared before the error dispatch begins. `RequestAttributeSecurityContextRepository` is designed to retrieve the context for **the same request** across eligible dispatches. It is **not** a session sharing identity across multiple HTTP requests.

If an error handler needs the principal, handle null/anonymous `Authentication` cases and limit returned data. Never display full JWTs or sensitive claims on error pages.

### 7.3. Why Not Manually Write the Context to the Session?

Do not create an ad-hoc login session via:

```java
request.getSession().setAttribute(
    "SPRING_SECURITY_CONTEXT",
    SecurityContextHolder.getContext()
);
```

In a stateless bearer API, this unexpectedly alters the "every request authenticates via token" contract and introduces unnecessary state. If a product needs session/cookie login, design an appropriate session authentication mechanism and repository rather than stuffing `SecurityContext` into the session manually.

## 8. Anonymous Authentication and the Question "Is the User Logged In?"

On `permitAll()` routes, Spring Security may populate `AnonymousAuthenticationToken`, or there may be no `Authentication` if the corresponding filter is absent. `AnonymousAuthenticationToken` represents a guest, **not** an authenticated bearer principal.

The following check is insufficient:

```java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();

if (auth != null && auth.isAuthenticated()) {
    // Cannot conclude this is a truly authenticated user yet.
}
```

Because `AnonymousAuthenticationToken` can return `true` for `isAuthenticated()`, rely on Spring Security's rules and trust resolvers:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll())
```

When scope-based authorization is needed:

```java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public OrderDto readOrder(String orderId) {
    // ...
}
```

Enable method security (e.g., `@EnableMethodSecurity`) for `@PreAuthorize` to take effect.

One more point: a Client Credentials access token may represent a **service principal**, not an interactive user. `authentication.getName()` does not default to an email/username and can vary by converter, grant type, and issuer contract. Never infer "logged in with a password" solely from the presence of an `Authentication`.

## 9. Async Boundaries: Other Threads Do Not Inherit Current Context Automatically

`SecurityContextHolder` defaults to `ThreadLocal`. A task submitted to an executor may run on a different thread than the Servlet thread:

```mermaid
sequenceDiagram
    participant R as Servlet Thread
    participant H as SecurityContextHolder
    participant W as Worker Thread
    R->>H: Context(user-842) in request
    R->>W: submit(task)
    Note over W: Separate ThreadLocal
    W->>H: getContext()
    H-->>W: Does not have user-842 by default
    R->>H: Request context is cleared
```

A common pitfall:

```java
@GetMapping("/api/start")
public String start() {
    CompletableFuture.runAsync(() -> {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();
        // Cannot assume auth is the principal of the request calling start().
        performTask(auth);
    });
    return "accepted";
}
```

`CompletableFuture.runAsync` typically runs on a separate executor. Java does not automatically copy the request's `ThreadLocal` to the thread executing the task.

### 9.1. Simple Approach: Pass Verified Actor Data

If the task only needs the verified issuer/subject/tenant, pass `CurrentActor`:

```java
@PostMapping("/api/reports")
public ResponseEntity<Void> createReport(
        @AuthenticationPrincipal Jwt jwt) {

    CurrentActor actor = new CurrentActor(
        jwt.getIssuer().toString(),
        jwt.getSubject(),
        jwt.getClaimAsString("tenant_id")
    );

    reportService.enqueueReport(actor);
    return ResponseEntity.accepted().build();
}
```

`enqueueReport` is an application-defined business API. Later execution should re-evaluate current permissions if business rules require it, since tokens and permissions may change after the HTTP request finishes. A captured actor is not a perpetual authorization grant.

When enqueuing jobs to a queue/message broker, avoid storing user bearer tokens inside long-lived messages. Use minimal actor metadata and a contracted worker credential/delegation model.

### 9.2. When SecurityContext Is Truly Needed on Another Thread

Spring Security provides concurrency wrappers:

- `DelegatingSecurityContextRunnable`
- `DelegatingSecurityContextCallable`
- `DelegatingSecurityContextExecutor`
- `DelegatingSecurityContextAsyncTaskExecutor`

These wrappers propagate the context to the executing thread and restore/clear it around the task lifecycle. Example:

```java
import java.util.concurrent.Executor;
import org.springframework.security.concurrent.DelegatingSecurityContextExecutor;

// delegate is an application-lifecycle-managed Executor.
Executor securedExecutor =
    new DelegatingSecurityContextExecutor(delegate);

// Submit task while the request has a verified Authentication.
securedExecutor.execute(() -> {
    Authentication current =
        SecurityContextHolder.getContext().getAuthentication();
    processInCurrentContext(current);
});
```

`delegate` and `processInCurrentContext` are application-defined. With the single-executor constructor, the wrapper captures the context present when the task is submitted. Variants exist that accept a specific context when you genuinely need to run under a governed system identity.

Even when propagating context, remember:

1. The task may execute after the original token expires or permissions change.
2. `SecurityContext` may reference sensitive credential/token data; never serialize it into queues or logs.
3. Avoid mutating a context shared across multiple tasks due to race conditions.
4. `DelegatingSecurityContext` only manages context **in-process**; it does not issue OAuth tokens for downstream services.

With `@Async`, you can wrap a managed executor using `DelegatingSecurityContextAsyncTaskExecutor` to propagate context at call time. Do not enable `MODE_INHERITABLETHREADLOCAL` globally to work around thread-pool issues.

### 9.3. Spring MVC Callable and DeferredResult Differ

Spring Security integrates with Spring MVC async. When a controller returns `Callable<T>`, the framework can use `WebAsyncManagerIntegrationFilter` to set the appropriate context when running the Callable:

```java
@GetMapping("/api/slow")
public Callable<String> slow() {
    return () -> {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();
        return "processed for " + auth.getName();
    };
}
```

This example assumes a protected route using standard Spring MVC `Callable`. Do not generalize this behavior to all coroutines, `CompletableFuture`s, or manually spawned threads.

With `DeferredResult`, completion is driven by application code/executors; Spring Security **does not automatically propagate `SecurityContext` to every `DeferredResult` task**. If the thread completing the response needs the identity, pass an actor or use concurrency wrappers.

### 9.4. Scheduled Jobs Have No HTTP Principal

A `@Scheduled` job does not pass through a user's Servlet filter chain:

```java
@Scheduled(fixedDelayString = "PT5M")
public void reconcile() {
    Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();
    // No end-user Authentication is present by default.
}
```

Background jobs should typically have their own service identity and permission policy—such as client credentials when calling remote APIs—rather than fabricating an arbitrary user in the holder.

## 10. When an HTTP Request Calls Another Microservice: JVM Context Does Not Transfer

`SecurityContextHolder` exists **inside the current application's Java process**. When Orders API calls Payments API:

```text
Browser
  |
  | Authorization: Bearer token-A (aud=orders-api)
  v
Orders API
  | SecurityContextHolder -> Authentication(user-842)
  |
  | HTTP call
  v
Payments API
    SecurityContextHolder -> separate context from credential sent to Payments API
```

Payments API cannot read the holder inside Orders API's JVM. It must authenticate its own incoming request credential:

| Approach | When appropriate | Identity at target API |
|---|---|---|
| Token relay | Input token is **already issued for the target API** and bilateral policy permits it | Target API re-validates the token and builds its own context |
| Token exchange / on-behalf-of | A new token scoped for the target API's audience is needed, preserving user delegation | Target API validates the new token |
| Client credentials | Calls made under service identity | Service principal `Authentication`, not an end user by default |

Never relay a token with `aud=orders-api` to `payments-api` if Payments API is not a valid audience. Never serialize a Java `SecurityContext` or `Authentication` over HTTP and treat it as a credential. Self-asserted headers like `X-User-Id` do not prove identity either unless the receiver enforces a real trust contract.

## 11. SecurityContextHolder vs. RequestContextHolder, MDC, and Tracing

Different forms of "per-request" data are not interchangeable:

| Component | Purpose | Proves an authenticated principal by default? |
|---|---|---|
| `SecurityContextHolder` | Access `Authentication` set by the framework | Yes, when populated by a trusted authentication mechanism without tampering |
| `HttpServletRequest` attribute | Share data within a request or dispatch | No |
| `RequestContextHolder` | Access request attributes per thread | No |
| MDC logging | Attach request ID/user ID for observability | No |
| Trace/span context | Track distributed call paths | No |
| `HttpSession` | Store session data | Only carries security weight with an explicit session authentication contract |

For instance, MDC may carry `userId` for log correlation, yet that value must never be used to authorize withdrawals or order reads. MDC also has its own thread/lifecycle management; setting values carelessly without cleanup can mix logs across requests.

## 12. When Should You Set SecurityContext Manually?

In a standard Resource Server, Spring Security's filter sets `Authentication` after validating the bearer token. Controllers and services **do not need** to build contexts manually.

In integration tests or genuinely custom authentication mechanisms, code may need to populate a context manually:

```java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authenticationFromTrustedMechanism);
SecurityContextHolder.setContext(context);
```

Crucial requirement: `authenticationFromTrustedMechanism` must come from a genuine authentication mechanism or governed system principal. **Never** turn a client-supplied `X-User-Id` header directly into an "authenticated" `Authentication`.

Spring Security recommends **creating a new context** when changing `Authentication`, rather than mutating an existing object that might be shared:

```java
// Be careful, as this may mutate an already-shared context.
SecurityContextHolder.getContext().setAuthentication(otherAuthentication);
```

If a self-managed scope runs **outside the Servlet filter chain**, clean up afterward:

```java
try {
    SecurityContext context = SecurityContextHolder.createEmptyContext();
    context.setAuthentication(authenticationFromTrustedMechanism);
    SecurityContextHolder.setContext(context);
    performTrustedWork();
} finally {
    SecurityContextHolder.clearContext();
}
```

This pattern is strictly for **self-managed scopes**; do not copy it into a controller handled by Spring Security. If code is called from an existing context, calling `clearContext()` could wipe the caller's `Authentication`. In that case, use scope-managing wrappers or carefully save and restore the prior context.

Never temporarily swap `Authentication` to an "admin" just to pass method security. If a task needs service privileges, design a dedicated service credential/authorization mechanism and audit trail.

## 13. Common Scenarios

### Scenario A: Two Users Calling the Same Endpoint Concurrently

```text
T1 Thread-21:
  Bearer token of user-A
  JwtAuthenticationToken(name=user-A)

T2 Thread-34:
  Bearer token of user-B
  JwtAuthenticationToken(name=user-B)
```

Each request has its own per-thread context. Once finished, the framework clears the context. Storing `Authentication` in a mutable field of a singleton service would break that built-in boundary.

### Scenario B: Same User Making Two Consecutive Requests

```text
GET /api/me + Bearer token-A -> context(user-A) in request 1
GET /api/me + Bearer token-A -> context(user-A) in request 2
```

With a stateless API, request 2 validates its own credential; there is no need to reuse the same `SecurityContext` Java object from request 1.

### Scenario C: Public Endpoint Without a Token

```text
GET /public/health
No Authorization header
```

The endpoint can still be allowed via `permitAll()`. The context may have no `Authentication` or an anonymous principal depending on configuration.

### Scenario D: Valid JWT with Insufficient Permissions

```text
JWT: aud=orders-api; sub=user-A; scope=orders.read
POST /api/orders requires SCOPE_orders.write
```

JWT authentication can succeed and the context holds `JwtAuthenticationToken(user-A)`, yet authorization returns **403** due to the missing authority. Valid authentication does not mean every operation is permitted.

### Scenario E: Async Work on the Default Executor

```text
HTTP Thread: context(user-A) -> submit task -> response 202
Worker Thread: getContext() -> does not automatically have user-A
```

The solution is passing an explicit actor or using controlled `DelegatingSecurityContext` wrappers while evaluating permissions and execution lifetimes.

### Scenario F: Error Dispatch

```text
REQUEST: user-A authenticated -> controller throws error
ERROR dispatch: repository may be needed to reload context for same request
```

A request-attribute repository can support this case. Do not assume the context persists into a separate HTTP request.

## 14. Risky Design Mistakes

| Mistake | Why it is wrong | Proper approach |
|---|---|---|
| Treating holder as a global holding the last user | Default is `ThreadLocal` | Let the filter chain manage context per request |
| Using `MODE_GLOBAL` in a web server | Identities can be shared across requests | Keep the default strategy |
| Using `MODE_INHERITABLETHREADLOCAL` to fix all async | Pools can retain stale or missing context | Pass actors or use concurrency wrappers |
| Storing `Authentication` in a singleton field | Risk of race conditions and mixing users | Accept actor from request parameters |
| Trusting `isAuthenticated()` alone | Anonymous tokens can return `true` | Use authorization rules / trust resolvers |
| Assuming `getName()` is always an end-user email | Service tokens and custom converters exist | Follow the principal contract |
| Skipping owner/tenant checks after JWT auth | Scopes do not replace record permissions | Enforce checks at the business layer |
| Setting `Authentication` from untrusted headers | Enables user/admin spoofing | Validate bearer credentials per contract |
| Manually saving context into session for bearer APIs | Creates unexpected state and behavior | Stay stateless/per-request per design |
| Clearing context inside a controller | Drops identity before downstream handling | Let filters clear context |
| Logging JWT/token values | Leaked credentials can be replayed | Log only minimal metadata |
| Assuming context propagates to another microservice | Context lives inside the JVM | Target API authenticates its own credentials |
| Using `@WithMockUser` and concluding JWT signatures work | Test only mocks a principal | Test authorization separately from JWT validation |

## 15. Observing and Verifying Behavior Without Exposing Tokens

When debugging, separate three questions:

1. **Authentication:** did the decoder/introspector verify the bearer token?
2. **Context:** what `Authentication` type and authorities are in the holder?
3. **Authorization:** do endpoint and business policies permit the action?

An internal endpoint returning only minimal metadata:

```java
@GetMapping("/internal/auth-info")
public Map<String, Object> authInfo(Authentication auth) {
    return Map.of(
        "authenticationType", auth.getClass().getSimpleName(),
        "principalName", auth.getName(),
        "authorities", auth.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .toList()
    );
}
```

`GrantedAuthority` belongs to `org.springframework.security.core.GrantedAuthority`. This diagnostic endpoint must be protected; never return raw tokens/credentials or full user claims.

In Spring Security Test, `@WithMockUser` creates a mock `Authentication` for testing authorization:

```java
@WithMockUser(username = "user-842", authorities = "SCOPE_orders.read")
@Test
void mayReadWithScope() {
    // Tests the authorization branch using a mocked Authentication.
}
```

This style of test **does not prove the JWT decoder verifies signatures, issuers, audiences, or expiration**. Similarly, `SecurityMockMvcRequestPostProcessors.jwt()` is convenient for testing controllers/authorization with a simulated JWT principal, yet may bypass parts of the real Bearer HTTP header extraction and JWT decoder flow.

When inspecting the filter chain, you can enable DEBUG logging in development:

```yaml
logging:
  level:
    org.springframework.security: DEBUG
```

Never print raw `Jwt#getTokenValue()`, `Authorization` headers, or `Authentication` objects containing credentials into production logs. When using multiple `SecurityFilterChain`s, Spring Security picks the first matching chain; requests failing to match the bearer chain may not authenticate as expected even when a header carries a token.

## 16. Frequently Asked Questions

**Can I read the principal in any Java class?** Yes, in code running on a thread where Spring Security has set up the context. Never assume a context exists when called from startup constructors, `@Scheduled` jobs, executor threads, library callbacks, or code running after the HTTP response.

**Is `SecurityContextHolder` a token store?** No. The holder provides the context holding `Authentication`. Some `Authentication` implementations reference a JWT/token, yet the goal is representing current identity and authorities—not storing refresh tokens or caching bearer tokens across requests.

**Should I call `setAuthentication()` manually in a controller?** In a standard Resource Server, no; the filter already does so after validating the credential. Custom authentication mechanisms must integrate properly with filters/providers and lifecycle handling.

**Why is `getAuthentication()` null even though the client sent a token?** Code might be running before the filter, on another thread, outside the `SecurityFilterChain` matcher, after the request ended, or the request was not handled by a bearer filter. Invalid tokens are usually blocked before reaching controllers. Check both where the context is read and the filter chain configuration.

**Can I put `SecurityContext` onto a message queue?** Do not serialize Java `SecurityContext`/`Authentication` as credentials for another process. Pass minimal actor details per contract; the receiver must enforce its own authentication/authorization.

**Does the context survive after a request?** The context in the request thread's holder is cleared. In stateful models, a repository/session can save data to reload on future requests, which is a different mechanism from leaving an `Authentication` on the thread.

## 17. Mental Model to Remember

```text
HTTP request to Resource Server
    |
    v
Bearer token -> JWT verification or introspection
    |
    v
Authenticated Authentication
    |
    v
SecurityContext holds Authentication
    |
    v
SecurityContextHolder lets thread-scoped code read context
    |
    +--> HTTP/method authorization: scopes, authorities
    +--> Business authorization: ownership, tenant, state
    +--> Async: pass actor/context explicitly
    +--> Other microservices: require valid credentials for target API
    |
    v
Processing ends -> clear context from holder
```

**`SecurityContextHolder` answers: "Within the current execution scope, which `Authentication` is Spring Security using?"** It does not validate JWTs itself, does not automatically grant data permissions, and does not guarantee identity propagates across threads, requests, or processes. Understanding this boundary helps Servlet applications avoid mixing users between requests, losing identity in async tasks, and misusing credentials when calling downstream services.

## References

- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): holder, context, authentication, ThreadLocal strategy.
- [Spring Security — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): Bearer filter, JWT, and opaque tokens.
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JwtDecoder, JwtAuthenticationToken, and validators.
- [Spring Security — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection and principals.
- [Spring Security — Authentication Persistence](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html): SecurityContextHolderFilter and SecurityContextRepository.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): explicit save and session policies.
- [Spring Security — Spring MVC Integration](https://docs.spring.io/spring-security/reference/servlet/integrations/mvc.html): AuthenticationPrincipal, CurrentSecurityContext, and MVC Callable/DeferredResult.
- [Spring Security — Concurrency Support](https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html): DelegatingSecurityContext wrappers.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): usage and protection of bearer tokens.

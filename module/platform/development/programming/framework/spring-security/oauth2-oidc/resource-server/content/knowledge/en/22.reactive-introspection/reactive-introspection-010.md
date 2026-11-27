# Non-Blocking Testing and Authentication Context Propagation to Handler Layers

In a **Spring Security OAuth 2.0/OIDC Resource Server running on Spring WebFlux**, opaque access tokens are typically validated by calling the Authorization Server's **OAuth 2.0 Token Introspection Endpoint**. What matters is not only validating the token properly, but also ensuring the entire flow is **truly non-blocking** and the authenticated identity **propagates correctly via the Reactor Context** to controllers, services, repositories, or other reactive handlers.

Code returning `Mono<OAuth2AuthenticatedPrincipal>` **does not automatically prove it is non-blocking**. If internally it calls `RestTemplate`, `Thread.sleep`, synchronous JDBC, or `.block()` on an event-loop thread, the pipeline can still stall. Likewise, successful token verification **does not guarantee** the service receives the right `Authentication` if developers call `subscribe()` manually, break out of the subscriber chain, or rely on Servlet `ThreadLocal` in ways incompatible with WebFlux.

This lesson focuses on two verifiable goals:

1. **Non-blocking introspection:** A Bearer request reaches `ReactiveOpaqueTokenIntrospector.introspect(String)`, performs WebFlux-compatible HTTP I/O, signals success or failure via `Mono`, never blocks Reactor event loops, and never fabricates principals when the AS fails.
2. **Authentication context propagation:** After successful introspection, `Authentication` is placed in the **reactive security context** and services can read or explicitly receive the authenticated actor without losing context across `flatMap`, `publishOn`, async boundaries, or reactive repository layers.

Examples use Java, Spring Boot with **spring-boot-starter-webflux**, **spring-boot-starter-security**, **spring-boot-starter-oauth2-resource-server**, Spring Security Test, Reactor Test, and WebTestClient. Domains, tokens, secrets, and IDs are illustrative.

> **Core message:** Testing opaque introspection requires separating at least **three layers**: (1) the introspector's output and non-blocking behavior, (2) the WebFlux filter chain's creation/propagation of Authentication, and (3) business permissions on specific objects. `mockOpaqueToken()` tests layers (2)/(3) conveniently, yet **skips the real HTTP introspection call**, so it must never be cited as proof for layer (1).

## 1. Where Introspection Sits in a WebFlux Resource Server

A request:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer 8NqVx2pLmZ_some_opaque_token
Accept: application/json
```

provides no self-verifiable claims from the opaque string itself. The Resource Server uses the AS introspection endpoint:

```http
POST /oauth2/introspect HTTP/1.1
Host: login.example.test
Authorization: Basic <RESOURCE_SERVER_INTROSPECTION_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded

token=<OPAQUE_ACCESS_TOKEN>
```

Example active-token response:

```json
{
  "active": true,
  "sub": "user-123",
  "client_id": "shop-web",
  "scope": "orders.read",
  "aud": ["orders-api"],
  "tenant_id": "shop-a",
  "exp": 1900000000
}
```

For an inactive token:

```json
{
  "active": false
}
```

Per RFC 7662, `active` is the central introspection verdict. Other claims may appear depending on the AS and contract. Never assume every AS returns `aud`, `tenant_id`, or `exp` on every response. If the application requires those fields, establish a contract with the AS and add corresponding validation.

### 1.1. Reactive Authentication Flow

```mermaid
flowchart TD
    A["Client sends Bearer token"] --> B["SecurityWebFilterChain"]
    B --> C["Bearer extraction / AuthenticationWebFilter"]
    C --> D["ReactiveOpaqueTokenAuthenticationManager"]
    D --> E["ReactiveOpaqueTokenIntrospector.introspect(token)"]
    E --> F["Async HTTP introspection with AS"]
    F --> G{"active and token contract valid?"}
    G -- "No" --> H["Mono.error → authentication failed"]
    G -- "Yes" --> I["OAuth2AuthenticatedPrincipal"]
    I --> J["BearerTokenAuthentication + GrantedAuthority"]
    J --> K["Reactive SecurityContext in Reactor Context"]
    K --> L["AuthorizationWebFilter / reactive method security"]
    L --> M{"Has endpoint scope/permission?"}
    M -- "No" --> N["Typically 403"]
    M -- "Yes" --> O["Controller → Mono/Flux service"]
    O --> P["Repository and object-level authorization"]
    P --> Q["Response per business permissions"]
    H --> R["Bearer authentication response, typically 401"]
```

This diagram is logical; specific class/filter names and wiring can vary across Spring Security versions. The invariant to uphold is **never having a trusted principal before introspection succeeds**.

### 1.2. Distinguishing from Servlet and JWT

| Topic | Spring MVC Servlet opaque | Spring WebFlux opaque | Spring WebFlux JWT |
|---|---|---|---|
| Token verification interface | `OpaqueTokenIntrospector` | `ReactiveOpaqueTokenIntrospector` | `ReactiveJwtDecoder` |
| Primary result | `OAuth2AuthenticatedPrincipal` | `Mono<OAuth2AuthenticatedPrincipal>` | `Mono<Jwt>` |
| HTTP introspection | Implementation-dependent, usually synchronous | Reactive HTTP per chosen implementation | Typically no per-token introspection needed |
| Security builder | `HttpSecurity` | `ServerHttpSecurity` | `ServerHttpSecurity` |
| Chain type | `SecurityFilterChain` | `SecurityWebFilterChain` | `SecurityWebFilterChain` |
| Security context | Servlet-oriented `SecurityContextHolder` | `ReactiveSecurityContextHolder` / Reactor Context | Same as WebFlux |
| HTTP tests | MockMvc | WebTestClient | WebTestClient |
| Token test support | Servlet `opaqueToken()` | Reactive `mockOpaqueToken()` | Reactive `mockJwt()` |

In this lesson, never use synchronous `OpaqueTokenIntrospector` as the primary WebFlux implementation.

## 2. "Reactive" Does Not Automatically Mean "Non-Blocking"

The interface signature:

```java
public interface ReactiveOpaqueTokenIntrospector {
    Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
}
```

is a **publisher contract**, not an automatic guarantee that everything inside uses non-blocking I/O.

**Incorrect** example:

```java
@Override
public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
    // blockingClient can send the HTTP request right on the calling thread.
    OAuth2AuthenticatedPrincipal principal =
        blockingClient.introspect(token);

    return Mono.just(principal);
}
```

Despite returning `Mono`, the synchronous HTTP call happened **before a publisher even existed to subscribe to**. Running on a WebFlux event loop, it can block the entire event loop.

An equivalent mistake:

```java
@Override
public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
    return Mono.just(
        blockingIntrospector.introspect(token)
    );
}
```

`Mono.just(...)` evaluates its argument eagerly first. The snippet does not become non-blocking just because of the name `Mono`.

### 2.1. Three Properties to Test Separately

| Property | What to prove | Example criterion |
|---|---|---|
| **Lazy/deferred** | No HTTP introspection is sent before subscribing | Counter/stub receives zero requests prior to subscription |
| **Non-blocking** | Never pins the event loop while waiting on the network | Uses async I/O client; no `block()`, no `Thread.sleep` |
| **Correct context** | After auth, subscriber chain reads the right Authentication | Service receives the right subject, tenant, and authority per request |

**Testing laziness with `StepVerifier` is not enough to prove non-blocking.** A publisher can be lazy yet still block upon subscription. This lesson separates those two test types.

### 2.2. Reactor Also Performs CPU Work

Even when introspection uses a non-blocking `WebClient`, JSON parsing, mapping, and authorization checks still consume CPU. Non-blocking mainly avoids pinning threads while waiting on I/O; it does not make work "thread-free" or magically faster.

## 3. Configuring an Opaque Resource Server with Spring Boot

Core Maven dependencies:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
</dependencies>
```

Introspection configuration:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.test/oauth2/introspect
          client-id: orders-api-introspection
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

Here `client-id` and `client-secret` are the **Resource Server's credentials for calling the introspection endpoint**, not the SPA's client ID that requested the bearer token. Production secrets must come from a secret manager or secure configuration—never hardcode them in repositories.

### 3.1. `SecurityWebFilterChain`

```java
@Configuration
@EnableWebFluxSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/public/catalog")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults())
            )
            .build();
    }
}
```

Imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
```

Because this is **WebFlux**, use `ServerHttpSecurity` and `authorizeExchange`, not Servlet `HttpSecurity`/`authorizeHttpRequests`. When opaque token support is configured, Spring Security uses a corresponding `ReactiveOpaqueTokenIntrospector`.

At the authorization layer, Spring Security normally converts scopes from the introspection response into `GrantedAuthority` instances prefixed with `SCOPE_`:

```text
scope = "orders.read orders.write"

GrantedAuthority:
  SCOPE_orders.read
  SCOPE_orders.write
```

**An active token does not equal permission to call an endpoint.** `active=true` only passes authentication; `hasAuthority("SCOPE_orders.read")` and per-order-ID checks can still deny access.

### 3.2. CORS/CSRF Are Separate from Introspection

If the API is called from a browser SPA, configure CORS preflight properly; `OPTIONS` preflight requests typically lack Bearer tokens. If the application uses cookies/sessions alongside Bearer tokens, evaluate CSRF policy separately. Never disable CSRF globally just because "the app uses JWT/opaque tokens" if browser-attached credentials are still active.

## 4. The `SpringReactiveOpaqueTokenIntrospector` Delegate

In modern Spring Security, creating the reactive introspector is illustrated in official docs as:

```java
@Bean
ReactiveOpaqueTokenIntrospector introspector(
        @Value("${app.security.introspection-uri}")
            String introspectionUri,
        @Value("${app.security.introspection-client-id}")
            String clientId,
        @Value("${app.security.introspection-client-secret}")
            String clientSecret) {

    return SpringReactiveOpaqueTokenIntrospector
        .withIntrospectionUri(introspectionUri)
        .clientId(clientId)
        .clientSecret(clientSecret)
        .build();
}
```

Imports:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;
```

The `app.security.*` keys are illustrative custom application properties that must be declared if you use this snippet. When only default configuration is needed, you can usually **let Spring Boot auto-create the introspector** from `spring.security.oauth2.resourceserver.opaquetoken.*` properties instead of declaring a bean manually.

**Version differences:** constructor/builder APIs of the implementation can vary across Spring Security versions; consult the documentation for your actual dependency version. The `ReactiveOpaqueTokenIntrospector` interface remains the primary extension point.

### 4.1. Why Prefer the Standard Reactive Implementation?

An implementation like `SpringReactiveOpaqueTokenIntrospector` aligns with Spring WebFlux and handles introspection over reactive HTTP as designed by the library. It spares you from manually writing:

- HTTP requests to the token introspection endpoint.
- Resource Server authentication to the AS.
- `active` response validation.
- Claim and scope mapping.
- Translating introspection errors into authentication errors.

Writing a custom HTTP client just for opaque tokens easily misses TLS verification, Basic authentication, content types, error handling, response encoding, and network bounds.

### 4.2. Custom Beans Can Replace Auto-Configuration

When you declare your own `ReactiveOpaqueTokenIntrospector` bean, Spring Boot may **back off** from default auto-configuration. Do not assume Boot automatically applies all Boot properties onto your new bean.

When an application has multiple beans or chains, select the introspector explicitly in the DSL:

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(opaque ->
        opaque.introspector(myReactiveIntrospector)
    )
)
```

`myReactiveIntrospector` must be a properly instantiated and injected object. In multi-chain/multi-issuer setups, ensure requests route to the right introspector.

## 5. Non-Blocking Introspector Customization via a Decorator

A common requirement is verifying that, in addition to `active=true`, the token carries audience `orders-api`. The Resource Server can **wrap the delegate** instead of forging an Authentication itself.

Example:

```java
public final class AudienceCheckingReactiveIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;
    private final String expectedAudience;

    public AudienceCheckingReactiveIntrospector(
            ReactiveOpaqueTokenIntrospector delegate,
            String expectedAudience) {
        this.delegate = Objects.requireNonNull(delegate);
        this.expectedAudience = Objects.requireNonNull(expectedAudience);
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        return Mono.defer(() -> delegate.introspect(token))
            .switchIfEmpty(Mono.error(
                new BadOpaqueTokenException("No principal")
            ))
            .flatMap(principal -> {
                Object audience = principal.getAttribute("aud");

                boolean accepted =
                    audience instanceof String text
                        && expectedAudience.equals(text);

                if (audience instanceof Collection<?> values) {
                    accepted = values.stream()
                        .anyMatch(expectedAudience::equals);
                }

                if (!accepted) {
                    return Mono.error(new BadOpaqueTokenException(
                        "Token not intended for orders-api"
                    ));
                }

                return Mono.just(principal);
            });
    }
}
```

Imports:

```java
import java.util.Collection;
import java.util.Objects;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;
```

Key points:

- `Mono.defer(...)` defers invoking the delegate until subscription, preventing introspection from firing outside the pipeline.
- The delegate must still verify token `active` status; the wrapper **never guesses** token state.
- `switchIfEmpty(...)` converts an unexpected absent principal into an authentication error rather than treating empty as success.
- `flatMap(...)` validates audience without blocking.
- `Mono.error(...)` preserves failure propagation via reactive error signals.
- `return Mono.just(principal)` preserves attributes and authorities built by the delegate.
- Never turn network errors into fake principals.

### 5.1. Not Every AS Returns `aud`

RFC 7662 does not mandate audience in every introspection response. If the Orders API requires audience binding, the AS must commit to returning `aud` (or an equivalent trusted mechanism). With this wrapper, missing audience is rejected per *fail closed*.

### 5.2. Validation Is Not Record-Level Authorization

A token with `aud=orders-api` and `scope=orders.read` still does not prove the caller may view order 42 belonging to another tenant. Object-level policy belongs in the service/repository—never inject per-request order IDs into a token-wide validator.

### 5.3. When a Check Must Query a Database

A database check typically belongs to **business authorization** rather than the token contract. If genuinely required inside the introspector, use a **reactive repository/client** with `flatMap`—never blocking JDBC inside `map`. For record ownership, pass the actor down to the service to check per object.

## 6. Two Common Mistakes That Still Block the Reactor Event Loop

**First mistake — calling `block()`:**

```java
@Override
public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
    OAuth2AuthenticatedPrincipal principal =
        reactiveDelegate.introspect(token).block();

    return Mono.just(principal);
}
```

On non-blocking threads this can throw an exception. Elsewhere, it pins a thread waiting on the network and destroys scalability.

**Second mistake — sleeping while waiting:**

```java
@Override
public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
    return Mono.fromCallable(() -> {
        Thread.sleep(1000);
        return blockingDelegate.introspect(token);
    });
}
```

`Mono.fromCallable(...)` defers execution, yet **does not automatically move blocking work onto another scheduler**. Subscribed on an event loop, it blocks the event loop.

### 6.1. If Integrating a Blocking SDK Is Unavoidable

While migrating a legacy SDK, you can isolate the blocking operation:

```java
Mono<OAuth2AuthenticatedPrincipal> result =
    Mono.fromCallable(() ->
        legacyBlockingIntrospector.introspect(token))
    .subscribeOn(Schedulers.boundedElastic());
```

Imports:

```java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
```

This is **blocking isolation**, not genuine non-blocking network I/O. It has thread/queue bounds, requires timeouts and concurrency limits, and must be monitored under load. Whenever an official reactive implementation exists, prefer it.

### 6.2. Never Self-`subscribe()` Inside Authentication

Wrong:

```java
reactiveDelegate.introspect(token)
    .subscribe(principal -> {
        // Creates an Authentication in a callback detached from the request flow.
    });

return Mono.empty();
```

The detached subscription may run after request authorization has already moved on; context and errors are no longer bound properly to the security pipeline.

**Right approach:** Return the composed `Mono` so Spring Security subscribes within the authentication chain.

## 7. Authentication Context in WebFlux: Reactor Context

In Servlet, many developers are used to:

```java
SecurityContextHolder.getContext().getAuthentication();
```

In WebFlux, however, a reactive request is not pinned to a single thread from start to finish. A pipeline can switch threads across I/O, `publishOn`, `subscribeOn`, or complex composition.

Spring Security stores the authentication context in the **Reactor Context**, accessed via **`ReactiveSecurityContextHolder`**:

```java
Mono<Authentication> currentAuthentication =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication);
```

Imports:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;
```

The Authentication created after opaque introspection is typically `BearerTokenAuthentication`, carrying an `OAuth2AuthenticatedPrincipal` and scope-mapped authorities.

### 7.1. Reactor Context Differs from `ThreadLocal`

| Aspect | Servlet ThreadLocal assumption | Reactor Context |
|---|---|---|
| Bound to execution unit | Thread | Subscription / subscriber chain |
| Thread switches | Can lose ThreadLocal unless propagated | Reactor Context generally follows the reactive chain |
| Access | `SecurityContextHolder.getContext()` | `ReactiveSecurityContextHolder.getContext()` |
| Writing context in tests | Configure SecurityContextHolder | `contextWrite(ReactiveSecurityContextHolder.withAuthentication(...))` |
| Detaching pipeline via manual `subscribe()` | Can lose context | Risks losing subscriber context |
| Passing actor to service | Via security context | Via Reactor Context or explicit parameter |

**Never assume every callback, `CompletableFuture`, or third-party library receives Reactor Context automatically.** It is tied to the subscriber chain and compatible operators/propagation hooks.

### 7.2. Context Is Not a Global Mutable Map

Reactor `Context` is a subscription-scoped structure updated via `contextWrite` and propagation rules. It is nothing like a `static Map<String, Authentication>` shared across requests.

Never store `Authentication` in a `static` variable or shared instance field:

```java
// Unsafe: data can overwrite across requests.
private Authentication lastAuthentication;
```

Concurrent requests can overwrite each other's principals, causing severe data leaks.

## 8. Reading the Actor from `ReactiveSecurityContextHolder`

A service may need the verified principal to enforce ownership/tenant policies. You can define an internal adapter:

```java
public record AuthenticatedActor(
    String subject,
    String tenantId
) {}
```

And a provider:

```java
@Component
public class CurrentActorProvider {

    public Mono<AuthenticatedActor> currentActor() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .switchIfEmpty(Mono.error(
                new AccessDeniedException("No authentication")
            ))
            .flatMap(authentication -> {
                Object rawPrincipal = authentication.getPrincipal();

                if (!(rawPrincipal
                        instanceof OAuth2AuthenticatedPrincipal principal)) {
                    return Mono.error(new AccessDeniedException(
                        "Unsupported principal type"
                    ));
                }

                Object rawSubject = principal.getAttribute("sub");
                Object rawTenant = principal.getAttribute("tenant_id");

                if (!(rawSubject instanceof String subject)
                        || subject.isBlank()
                        || !(rawTenant instanceof String tenant)
                        || tenant.isBlank()) {

                    return Mono.error(new AccessDeniedException(
                        "Missing actor identity"
                    ));
                }

                return Mono.just(new AuthenticatedActor(
                    subject, tenant));
            });
    }
}
```

Imports:

```java
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;
```

**Limitations of the example:** `tenant_id` is a custom claim, meaningful only if returned by the AS under a trusted contract; this code intentionally denies when absent. If an API has no tenant concept or uses another opaque principal shape, adapt accordingly.

### 8.1. Do Not Rely Blindly on `getName()` for Identification

In opaque token support, `name` may map from `sub` or another configured attribute. If a system accepts multiple issuers, two issuers could both emit `sub=user-123` for two completely different people.

A safe multi-issuer identity may require **`(issuer, subject)`** or a trusted internal account mapping. Never treat mutable emails/usernames as immutable owner IDs unless guaranteed by contract.

### 8.2. What If Context Lacks an Authentication?

Never synthesize a default admin actor or read tenant from the request path. `Mono.empty()` from context may indicate a request outside the security chain, a public endpoint, a test missing context setup, or a detached publisher. Handle it per policy: deny on protected endpoints, or use a distinct anonymous actor when an operation is genuinely public.

## 9. Passing the Actor Explicitly Down to Services

A cleaner, easier-to-test option with looser coupling is:

1. WebFlux security authenticates the Bearer token.
2. Controller/adapter extracts the principal.
3. Convert it into an internal `AuthenticatedActor`.
4. Pass the actor to the service as a Java parameter.
5. The service has no direct dependency on Spring Security classes.

Controller example:

```java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService service;
    private final ActorMapper actorMapper;

    public OrderController(
            OrderService service,
            ActorMapper actorMapper) {
        this.service = service;
        this.actorMapper = actorMapper;
    }

    @GetMapping("/{orderId}")
    public Mono<OrderDto> readOrder(
            @PathVariable String orderId,
            @AuthenticationPrincipal
                OAuth2AuthenticatedPrincipal principal) {

        AuthenticatedActor actor =
            actorMapper.fromTrustedPrincipal(principal);

        return service.readVisibleOrder(orderId, actor);
    }
}
```

`OrderService`, `ActorMapper`, `AuthenticatedActor`, and `OrderDto` are domain types implemented by the project. `@AuthenticationPrincipal` is resolved by Spring Security after Authentication succeeds; never pull principals from a JSON body or query parameter.

Related imports:

```java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;
```

### 9.1. Advantages of Passing the Actor Explicitly

- Service signatures clearly declare the actor for the use case.
- Easy to unit test policies without setting up Reactor `SecurityContext`.
- Prevents background jobs from accidentally running without an authenticated HTTP context.
- Easy to enforce tenant/owner data filters.
- Easy to pass across reactive abstractions independent of threads.

Ensure the actor is built from a **verified principal**, never from arbitrary caller-supplied input:

```json
{
  "subject": "admin",
  "tenantId": "shop-b"
}
```

If a service accepts an object like that constructed by the client, permission checks are untrustworthy.

### 9.2. When You Prefer Not to Couple Controllers to Spring Security Types

Another option is `ServerWebExchange.getPrincipal()` or an application adapter returning `Mono<AuthenticatedActor>`. Example:

```java
@GetMapping("/{orderId}")
public Mono<OrderDto> readOrder(@PathVariable String orderId) {
    return currentActorProvider.currentActor()
        .flatMap(actor ->
            service.readVisibleOrder(orderId, actor));
}
```

This stays inside the Reactor subscriber chain and never calls `block()` to read the principal.

## 10. Reactive Services Keep Data Permissions Properly Scoped

A service can accept the actor and query a reactive repository:

```java
@Service
public class OrderService {

    private final ReactiveOrderRepository repository;

    public OrderService(ReactiveOrderRepository repository) {
        this.repository = repository;
    }

    public Mono<OrderDto> readVisibleOrder(
            String orderId,
            AuthenticatedActor actor) {

        return repository
            .findOwnedByTenantAndSubject(
                orderId,
                actor.tenantId(),
                actor.subject()
            )
            .switchIfEmpty(
                Mono.error(new OrderNotFoundException())
            )
            .map(OrderDto::from);
    }
}
```

Query concept:

```sql
SELECT *
FROM orders
WHERE id = :orderId
  AND tenant_id = :trustedTenant
  AND owner_subject = :trustedSubject;
```

With Spring Data R2DBC, the repository executes asynchronously via the reactive driver/database. Never wrap a blocking JDBC repository inside `Mono.just(...)` expecting non-blocking execution.

### 10.1. Action Permissions Differ from Object Permissions

An HTTP rule:

```java
.pathMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
```

only states the token has the **read operation class**. The service must still verify:

```text
order.tenant == actor.allowedTenant
AND (
    order.owner == actor.subject
    OR shareACL permits
    OR assignedSupportPolicy permits
)
```

A token with the right `scope` is not permission to read every order.

### 10.2. List, Count, and Export Endpoints Must Also Filter Permissions

Not just `GET /api/orders/{id}`. Endpoints such as:

```text
GET /api/orders
GET /api/orders/search
GET /api/orders/count
GET /api/orders/export
```

can all leak object-level data if queries omit `tenant_id` or owner/share filters. Passing the actor to the service ensures the same permission boundary governs detail, list, search, and report views.

## 11. How Does Context Propagate Across `flatMap`, `map`, and `publishOn`?

In Reactor, `Context` is tied to the subscription. Standard operators within the same chain normally preserve context even when publishers switch schedulers.

Example:

```java
Mono<String> currentSubject =
    ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication())
        .map(Authentication::getName)
        .publishOn(Schedulers.parallel())
        .flatMap(name ->
            ReactiveSecurityContextHolder.getContext()
                .map(ctx -> name + ":" +
                    ctx.getAuthentication().getName())
        );
```

When Authentication is placed in the Reactor Context before subscription, both reads in a properly composed pipeline observe the same principal, even after `publishOn`.

Imports:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
```

**Do not misunderstand:** `publishOn` switches the scheduler for a downstream segment; it does not duplicate requests or re-run authorization. Reactive Context is not `ThreadLocal`, and you do not manually "copy Authentication into ThreadLocal" for each operator.

### 11.1. `contextWrite` Applies at Subscription Time

Reactor Context flows **from subscriber to upstream** along the chain. Hence a test writes:

```java
Mono<String> result =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());

Mono<String> authenticatedResult =
    result.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(authentication)
    );
```

The upstream `result` publisher can read Authentication when `authenticatedResult` is subscribed.

**Never think of `contextWrite` as a global variable assignment.** It is scoped to the associated publisher chain and follows Reactor subscription rules.

### 11.2. `subscribeOn` Does Not Lose Context Either

If code composes a publisher normally:

```java
return serviceCall()
    .subscribeOn(Schedulers.boundedElastic());
```

Reactor Context stays attached to the subscriber chain per Reactor semantics. However, `subscribeOn` **is not a cure-all for unbounded blocking**. It only selects the subscription scheduler, and synchronous I/O still ties up threads.

### 11.3. Avoid Breaking the Chain with Manual `subscribe()`

Unsafe example:

```java
public Mono<OrderDto> readOrder(String id) {
    currentActorProvider.currentActor()
        .subscribe(actor ->
            auditService.record(actor.subject(), id).subscribe()
        );

    return repository.findById(id).map(OrderDto::from);
}
```

At least three issues occur:

1. Auditing runs in a separate subscription that may not be awaited and drops errors.
2. Security context may not propagate into detached subscriptions as expected.
3. The repository query does not use the actor to filter the object.

A composed alternative:

```java
public Mono<OrderDto> readOrder(String id) {
    return currentActorProvider.currentActor()
        .flatMap(actor ->
            service.readVisibleOrder(id, actor)
                .flatMap(order ->
                    auditService.record(actor.subject(), id)
                        .thenReturn(order)
                )
        );
}
```

This pattern fits when the audit event must belong to the request pipeline; for auditing via a message broker, design explicit reliability/idempotency rather than firing detached `subscribe()` calls and ignoring outcomes.

## 12. HTTP Handlers and Reactor Context: Ways to Obtain the Principal

In WebFlux, handlers have several ways to read the principal:

| Approach | Characteristics | When to use |
|---|---|---|
| `@AuthenticationPrincipal OAuth2AuthenticatedPrincipal` | Injected into annotated controllers | Annotation-based WebFlux handlers |
| `ServerWebExchange.getPrincipal()` | `Mono<Principal>` on the exchange | Functional handlers / web filters |
| `ReactiveSecurityContextHolder.getContext()` | Reads Authentication from Reactor Context | Adapters/services inside the same reactive chain |
| Domain actor parameter | No direct Spring Security coupling | Service/repository policies |
| ThreadLocal `SecurityContextHolder.getContext()` | Should not be assumed in reactive chains | Only where explicitly supported with proper propagation |

### 12.1. Using `ServerWebExchange.getPrincipal()`

Example in a functional handler:

```java
public Mono<ServerResponse> handler(ServerRequest request) {
    return request.principal()
        .cast(Authentication.class)
        .flatMap(authentication -> {
            OAuth2AuthenticatedPrincipal principal =
                (OAuth2AuthenticatedPrincipal)
                    authentication.getPrincipal();

            String subject = principal.getAttribute("sub");

            return ServerResponse.ok()
                .bodyValue(Map.of("subject", subject));
        });
}
```

Illustrative imports:

```java
import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import reactor.core.publisher.Mono;
```

This assumes the endpoint is protected by the Resource Server and the principal has the expected type; production code should check types/nulls and avoid exposing `subject` unnecessarily. Public handlers or routes with other authentication types must never cast unconditionally.

### 12.2. When Using Custom Handler Functions or Filters

Never construct a principal from caller-supplied `X-User-Id` or `X-Tenant-Id` headers. If a system uses identity headers from a gateway, enforce a dedicated trust boundary such as mTLS, header stripping, and strict authentication policies.

An opaque Resource Server should extract the actor from the **introspected `Authentication`** and never treat inbound headers as a source of truth.

## 13. Unit Testing a Reactive Introspector with `StepVerifier`

Before running HTTP tests, test `ReactiveOpaqueTokenIntrospector` directly with a fake delegate. This verifies contracts, error signals, and lazy subscription **without needing a real Authorization Server**.

Principal builder helper:

```java
private static OAuth2AuthenticatedPrincipal principal(
        String subject,
        String tenant,
        String authority) {

    return new DefaultOAuth2AuthenticatedPrincipal(
        subject,
        Map.of(
            "sub", subject,
            "tenant_id", tenant,
            "aud", List.of("orders-api")
        ),
        List.of(new SimpleGrantedAuthority(authority))
    );
}
```

Imports:

```java
import java.util.List;
import java.util.Map;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
```

### 13.1. Testing the Success Case

```java
@Test
void acceptsValidAudienceWithoutBlockingTestThread() {
    ReactiveOpaqueTokenIntrospector delegate = token ->
        Mono.just(principal(
            "user-123",
            "shop-a",
            "SCOPE_orders.read"
        ));

    ReactiveOpaqueTokenIntrospector introspector =
        new AudienceCheckingReactiveIntrospector(
            delegate, "orders-api");

    StepVerifier.create(
            introspector.introspect("opaque-test-token"))
        .assertNext(p -> {
            assertEquals("user-123", p.getName());
            assertEquals("shop-a",
                p.getAttribute("tenant_id"));
        })
        .verifyComplete();
}
```

Imports:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
```

**Be accurate about test scope:** This verifies the publisher emits the right principal and completes; it **is not sufficient to prove non-blocking execution**. The `Mono.just(...)` delegate does no HTTP I/O; test names should reflect tested behavior rather than making performance claims.

### 13.2. Testing Wrong Audience

```java
@Test
void rejectsWrongAudience() {
    OAuth2AuthenticatedPrincipal wrongAudience =
        new DefaultOAuth2AuthenticatedPrincipal(
            "user-123",
            Map.of("sub", "user-123",
                   "aud", List.of("payments-api")),
            List.of(new SimpleGrantedAuthority(
                "SCOPE_orders.read"))
        );

    ReactiveOpaqueTokenIntrospector delegate =
        token -> Mono.just(wrongAudience);

    ReactiveOpaqueTokenIntrospector introspector =
        new AudienceCheckingReactiveIntrospector(
            delegate, "orders-api");

    StepVerifier.create(introspector.introspect("test-token"))
        .expectError(BadOpaqueTokenException.class)
        .verify();
}
```

If the AS introspected an active token whose audience belongs to another API, the wrapper must reject it; never rewrite `aud` inside the principal to force acceptance.

### 13.3. Testing Delegate Errors Remain Fail-Closed

```java
@Test
void preservesInactiveTokenFailure() {
    ReactiveOpaqueTokenIntrospector delegate =
        token -> Mono.error(
            new BadOpaqueTokenException("inactive")
        );

    ReactiveOpaqueTokenIntrospector introspector =
        new AudienceCheckingReactiveIntrospector(
            delegate, "orders-api");

    StepVerifier.create(
            introspector.introspect("inactive-token"))
        .expectError(BadOpaqueTokenException.class)
        .verify();
}
```

Never use:

```java
.onErrorResume(error ->
    Mono.just(principal(
        "admin", "all-tenants", "ROLE_ADMIN"))
)
```

just to make tests green. That is *fail open*.

## 14. Testing Lazy Subscription: No Introspection Before Subscribing

A key property of reactive I/O is that work is deferred until subscription time.

```java
@Test
void delegatesOnlyAfterSubscription() {
    AtomicInteger subscriptions = new AtomicInteger();

    ReactiveOpaqueTokenIntrospector delegate =
        token -> Mono.defer(() -> {
            subscriptions.incrementAndGet();
            return Mono.just(principal(
                "user-123",
                "shop-a",
                "SCOPE_orders.read"
            ));
        });

    ReactiveOpaqueTokenIntrospector introspector =
        new AudienceCheckingReactiveIntrospector(
            delegate, "orders-api");

    Mono<OAuth2AuthenticatedPrincipal> result =
        introspector.introspect("test-token");

    assertEquals(0, subscriptions.get());

    StepVerifier.create(result)
        .expectNextCount(1)
        .verifyComplete();

    assertEquals(1, subscriptions.get());
}
```

Import:

```java
import java.util.concurrent.atomic.AtomicInteger;
```

This proves **the test delegate subscription did not run before a subscriber subscribed**. It does not measure I/O blocking, event-loop starvation, or thread allocation.

### 14.1. Why Does `Mono.defer` Make Testing Stronger?

When a delegate is built with:

```java
token -> Mono.defer(() -> realAsyncCall(token))
```

the callback does not run prior to subscription. If the wrapper also writes `Mono.defer(() -> delegate.introspect(token))`, even invoking the delegate method itself is deferred. Yet if `realAsyncCall` blocks upon subscription, the publisher is still blocking. Verify the actual I/O implementation separately.

## 15. Testing Non-Blocking Behavior Differs from Testing Laziness

An application can pass every `StepVerifier` unit test and still block the event loop in production.

Example:

```java
return Mono.defer(() -> {
    blockingHttpClient.callIntrospection(token); // still blocking
    return Mono.just(principal);
});
```

A laziness test passes because the callback did not run prior to subscription. Yet upon subscription, the request thread still blocks.

### 15.1. Signs of Blocking in Code

- `.block()` or `.blockOptional()` inside filters, introspectors, or services.
- `Thread.sleep(...)` or waiting on `Future.get()`.
- `RestTemplate`, `HttpURLConnection`, or synchronous HTTP SDKs called on the event loop.
- JDBC/JPA repositories called directly from reactive handlers.
- Long blocking file I/O or thread-blocking locks.
- `Mono.just(blockingMethod())`.
- `Mono.fromCallable(blockingMethod)` without proper scheduling/isolation.
- Manual `subscribe()` calls to "wait" on authentication callbacks.

### 15.2. BlockHound and Blocking-Detection Tools

In test environments, **BlockHound** can detect certain blocking operations executed on threads marked non-blocking. Conceptual setup:

```java
// Test framework setup, if dependencies/JDK are compatible:
BlockHound.install();
```

Then run the real flow through WebFlux/Reactor Netty or intentional test scheduling. When `Thread.sleep` or a blocking call runs on an event-loop thread, the test fails.

**Limitations:**

- BlockHound cannot catch every kind of blocking I/O or every library.
- Choose a JVM/agent-compatible version and avoid duplicate installation.
- A unit test running on a normal JUnit thread may not trigger event-loop detection.
- Evaluate instrumentation overhead and false positives.
- A "no BlockHound errors" test does not replace latency/load testing.

Never rely solely on checking `Thread.currentThread().getName()` to prove non-blocking; thread names are an observation, not proof that a method does not block.

### 15.3. Integration Testing with a Delayed AS Stub

A high-value test:

1. Run a test HTTP server simulating the introspection endpoint.
2. Have it return `active=true` after an asynchronous delay.
3. Send many concurrent Bearer requests via `WebTestClient` to the WebFlux Resource Server.
4. Verify event-loop threads are not pinned by blocking calls.
5. Confirm all requests receive the right identities and authorization outcomes.
6. Measure latency and throughput under configured limits.

You do not need full-capacity benchmarks inside `StepVerifier` unit tests, but you should run load tests and monitoring on real systems. **One single request returning the right response does not prove safe concurrency behavior.**

## 16. Timeouts and Network Errors: Non-Blocking Must Never Become Fail-Open

HTTP introspection can encounter:

```text
DNS failure
TLS handshake failure
Authorization Server timeout
503 from introspection endpoint
Malformed introspection response
active=false
Invalid introspection credentials
```

`active=false` proves the token is inactive per the AS. A network timeout means the Resource Server **could not verify the token**, not necessarily that it was revoked. Either way, **neither may be treated as authenticated success**.

### 16.1. Publisher Timeout

A decorator can bound the introspection wait time:

```java
public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
    return delegate.introspect(token)
        .timeout(Duration.ofSeconds(2));
}
```

Imports:

```java
import java.time.Duration;
import reactor.core.publisher.Mono;
```

This is a publisher-level timeout; the HTTP client still needs appropriate connect/read/response timeouts and resource bounds. A timeout produces `TimeoutException`, and exception mapping affects the final HTTP response.

If you want to classify timeouts as infrastructure introspection errors:

```java
return delegate.introspect(token)
    .timeout(Duration.ofSeconds(2))
    .onErrorMap(
        TimeoutException.class,
        error -> new OAuth2IntrospectionException(
            "Introspection temporarily unavailable", error)
    );
```

Imports:

```java
import java.util.concurrent.TimeoutException;
import org.springframework.security.oauth2.server.resource.introspection.OAuth2IntrospectionException;
```

Never convert every error into `BadOpaqueTokenException` as "token revoked"; network failures and inactive tokens are distinct events. Even though HTTP status depends on exception handlers, all failure cases must enforce **fail-closed authentication**.

### 16.2. Bounded Retries

A transient network glitch can sometimes be retried, provided:

- Never retry indefinitely.
- Never retry inactive-token or contract-mismatch errors.
- Apply a time budget for the whole request, not just per attempt.
- Bound concurrency, backoff, and jitter to avoid flooding the AS.
- Measure retry/timeout rates.
- Never extend caching of expired tokens merely because the AS is failing.

### 16.3. Never Use `onErrorResume` to Create a "Temporary" Principal

Severe mistake:

```java
return delegate.introspect(token)
    .onErrorResume(ex ->
        Mono.just(defaultAdminPrincipal)
    );
```

This grants successful authentication whenever the AS or network has an outage. An error handler may adjust **error classification or observability**, never grant unverified privileges.

## 17. Testing Timeouts with `StepVerifier` and Virtual Time

When testing publishers with timeouts, Reactor Test provides `StepVerifier.withVirtualTime(...)` so unit tests do not wait in real time (provided schedulers/time operators are instantiated inside the lambda).

Example:

```java
@Test
void timesOutWhenDelegateNeverResponds() {
    ReactiveOpaqueTokenIntrospector delegate =
        token -> Mono.never();

    ReactiveOpaqueTokenIntrospector timed =
        token -> delegate.introspect(token)
            .timeout(Duration.ofSeconds(3));

    StepVerifier.withVirtualTime(
            () -> timed.introspect("test-token"))
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(3))
        .expectError(TimeoutException.class)
        .verify();
}
```

Imports:

```java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
```

This test proves **Reactor timeout logic** under the virtual scheduler. It does not prove the HTTP client uses non-blocking transport, nor does it test TLS, DNS, or server socket timeouts. Those require integration tests and operational verification.

### 17.1. Never Use `Thread.sleep` to Test Timeouts

A test doing:

```java
Thread.sleep(3000);
```

only blocks the test thread, making tests slow and flaky. Virtual time fits Reactor operators backed by schedulers; real HTTP I/O must be tested with a test server and client timeouts.

## 18. Testing Context Propagation with `ReactiveSecurityContextHolder.withAuthentication`

You can unit test a pipeline that reads `Authentication` without starting an HTTP server. Prepare a simulated `Authentication`:

```java
Authentication authentication =
    new TestingAuthenticationToken(
        "user-123",
        "not-a-real-secret",
        "SCOPE_orders.read"
    );
```

Here the goal is Reactor Context propagation, not real opaque-token introspection. `TestingAuthenticationToken` is a test helper—never use it as a production principal to bypass introspection.

### 18.1. Testing the Same Principal Before and After `publishOn`

```java
@Test
void keepsAuthenticationAcrossPublishOn() {
    Authentication authentication =
        new TestingAuthenticationToken(
            "user-123",
            "test-credential",
            "SCOPE_orders.read"
        );

    Mono<String> pipeline =
        ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication().getName())
            .publishOn(Schedulers.parallel())
            .flatMap(name ->
                ReactiveSecurityContextHolder.getContext()
                    .map(ctx ->
                        name + ":" +
                        ctx.getAuthentication().getName()
                    )
            );

    StepVerifier.create(
            pipeline.contextWrite(
                ReactiveSecurityContextHolder
                    .withAuthentication(authentication)
            )
        )
        .expectNext("user-123:user-123")
        .verifyComplete();
}
```

Imports:

```java
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;
```

This evaluates how Reactor Context travels across the used operators. It **does not** prove `BearerTokenAuthentication` was built from real introspection, because the Authentication was test-created.

### 18.2. Testing Absent Context

```java
@Test
void noContextDoesNotCreateAnAdmin() {
    Mono<String> currentName =
        ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication().getName());

    StepVerifier.create(currentName)
        .verifyComplete();
}
```

Normally, with no security context in the subscriber chain, the publisher emits no user name. Protected services should handle that case per policy—usually rejecting with an error—rather than assigning a "default admin."

### 18.3. Testing Misplaced `contextWrite`

Reactor Context applies upstream of `contextWrite` in the subscription chain. If you break out into a separate subscription, the new context will not reach that publisher. In unit tests, test the exact chain that real requests subscribe to instead of calling an isolated method and subscribing outside the pipeline.

## 19. Testing Opaque Authentication at the HTTP Layer with `WebTestClient`

Spring Security Test provides **`mockOpaqueToken()`** for WebFlux. It injects a verified Authentication into test requests so you can verify routes and method security **without an AS introspection endpoint**.

Example:

```java
@SpringBootTest
@AutoConfigureWebTestClient
class OrdersAuthorizationTests {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void readScopeCanAccessVisibleOrder() {
        webTestClient
            .mutateWith(
                mockOpaqueToken()
                    .attributes(attrs -> {
                        attrs.put("sub", "user-123");
                        attrs.put("tenant_id", "shop-a");
                    })
                    .authorities(
                        new SimpleGrantedAuthority(
                            "SCOPE_orders.read")
                    )
            )
            .get()
            .uri("/api/orders/order-1")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void missingReadScopeIsForbidden() {
        webTestClient
            .mutateWith(
                mockOpaqueToken()
                    .authorities(
                        new SimpleGrantedAuthority(
                            "SCOPE_profile")
                    )
            )
            .get()
            .uri("/api/orders/order-1")
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

Imports:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOpaqueToken;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;
```

**Prerequisites:** the controller, repository, and test fixtures must be set up to return 200 for `user-123`'s `order-1`. If the order does not exist or the service applies another policy, the status after HTTP authorization may be 404/403 instead of 200.

### 19.1. What Does `mockOpaqueToken()` Actually Do?

It places a `BearerTokenAuthentication` matching the mocked principal, attributes, and authorities into the WebFlux test security context. It is useful for checking:

- `SCOPE_...` route authorization.
- Whether controllers receive the Authentication/principal.
- Object-level policies using simulated subjects/tenants.
- Whether reactive services preserve context down the request chain.
- HTTP 2xx/403/404 responses for different authorities.

**It does not test:**

- Whether the token has `active=true` from a real AS.
- Whether the introspection HTTP call is non-blocking.
- Whether Basic/mTLS credentials to the AS are valid.
- Whether AS timeouts/revocation are handled.
- Whether a custom `ReactiveOpaqueTokenIntrospector` runs.
- Whether a caller's real Bearer token parses/validates cleanly.

Never treat an HTTP test using `mockOpaqueToken()` as integration proof for the introspection endpoint.

### 19.2. Why Varying Authorities in Tests Matters

In Spring Security opaque support, the `scope` claim from the AS is typically mapped to `SCOPE_...`. When testing with `mockOpaqueToken()`, grant authorities explicitly:

```java
mockOpaqueToken()
    .authorities(
        new SimpleGrantedAuthority("SCOPE_orders.read"))
```

If a route requires `SCOPE_orders.export`, this request must be rejected despite having `orders.read`. Export permission is a separate contract and never implied by read.

### 19.3. Attaching a Custom Principal for Tests

If an object policy expects a principal with specific name/attributes:

```java
OAuth2AuthenticatedPrincipal testPrincipal =
    new DefaultOAuth2AuthenticatedPrincipal(
        "user-123",
        Map.of(
            "sub", "user-123",
            "tenant_id", "shop-a"
        ),
        List.of(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )
    );

webTestClient
    .mutateWith(
        mockOpaqueToken().principal(testPrincipal)
    )
    .get()
    .uri("/api/orders/order-1")
    .exchange();
```

This simulates an identity for authorization testing; it is not an AS-verified token.

## 20. Integration Testing with Real HTTP Introspection

To test **everything from the Bearer header to the HTTP delegate**, do not use `mockOpaqueToken()`. Instead:

1. Boot the WebFlux Resource Server in the test context.
2. Run an HTTP stub server acting as a **fake Authorization Server introspection endpoint**.
3. Point `spring.security.oauth2.resourceserver.opaquetoken.introspection-uri` to the stub.
4. Configure test introspection client credentials.
5. Send a request via `WebTestClient` with `Authorization: Bearer test-opaque-token`.
6. Have the stub assert receipt of the HTTP introspection request and proper auth credentials.
7. Have the stub return `active=true` + scopes/claims.
8. Have `WebTestClient` assert the response, actor propagation, and authorization.
9. Repeat for `active=false`, timeouts, malformed JSON, and 401/500 from the AS.

### 20.1. HTTP Request Test Template

```java
webTestClient.get()
    .uri("/api/orders/order-1")
    .headers(headers ->
        headers.setBearerAuth("test-opaque-token"))
    .exchange()
    .expectStatus().isOk();
```

In this test, **do not attach `mockOpaqueToken()`**, as that can bypass the authentication manager and introspector you intend to test.

### 20.2. Fake Authorization Server Responses

Active case:

```json
{
  "active": true,
  "sub": "user-123",
  "scope": "orders.read",
  "aud": ["orders-api"],
  "tenant_id": "shop-a"
}
```

Inactive case:

```json
{
  "active": false
}
```

Contract-violation case:

```json
{
  "active": true,
  "sub": "user-123",
  "scope": "orders.read",
  "aud": ["payments-api"],
  "tenant_id": "shop-a"
}
```

With an audience wrapper, the final case must be rejected **during authentication**, before the controller runs.

### 20.3. Why Stub the AS Instead of Calling Production AS?

- Tests do not depend on production networking.
- Real client secrets are not needed.
- You can deterministically trigger `active=false` and infrastructure errors.
- You can test delays and timeouts deterministically.
- No unintended tokens are minted or revoked.
- You can count exact introspection calls and retries.

WireMock, MockWebServer, or a reactive test server can all work depending on your stack; the point is that the test **truly traverses HTTP introspection**, not just a mocked principal.

## 21. Testing End-to-End That the Actor Reaches the Service Accurately

An HTTP test can use a test service that records the actor into a thread-safe sink or returns non-sensitive fields to verify principal propagation. Illustrative test-only endpoint:

```java
@GetMapping("/test/whoami")
public Mono<Map<String, String>> whoAmI() {
    return currentActorProvider.currentActor()
        .map(actor -> Map.of(
            "subject", actor.subject(),
            "tenant", actor.tenantId()
        ));
}
```

With the introspection stub returning:

```json
{
  "active": true,
  "sub": "user-123",
  "tenant_id": "shop-a",
  "scope": "orders.read"
}
```

the test expects:

```json
{
  "subject": "user-123",
  "tenant": "shop-a"
}
```

**Never expose a `/test/whoami` endpoint in production** just for debugging. Keep it inside `@TestConfiguration`/test-only controllers, or verify indirectly through service spies/test fixtures.

### 21.1. Testing Two Concurrent Requests

A valuable boundary test:

```text
Request A:
  token-a → sub=user-123, tenant=shop-a

Request B:
  token-b → sub=user-456, tenant=shop-b

Both call the reactive service concurrently.
```

Expectations:

- Response A contains only data belonging to `user-123`/`shop-a`.
- Response B contains only data belonging to `user-456`/`shop-b`.
- Zero subject/tenant bleed across requests.
- No shared mutable field holding "current user."
- No event-loop blocking under the target load.

If tests only use one user, bugs involving a static Authentication or missing tenant filters easily go unnoticed.

### 21.2. Do Not Use `ThreadLocal` as a "Test Oracle"

Reading `SecurityContextHolder.getContext()` from a `ThreadLocal` inside an arbitrary callback and concluding context was lost is invalid for WebFlux. Tests should read `ReactiveSecurityContextHolder.getContext()` inside the pipeline or pass an explicit actor.

## 22. Method Security in Reactive Services

When services must gate by scope, WebFlux supports reactive method security:

```java
@Configuration
@EnableReactiveMethodSecurity
public class MethodSecurityConfiguration {
}
```

Example:

```java
@Service
public class OrderService {

    private final ReactiveOrderRepository repository;

    public OrderService(ReactiveOrderRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public Mono<OrderDto> getVisibleOrder(
            String id,
            AuthenticatedActor actor) {

        return repository.findVisibleOrder(
                id, actor.tenantId(), actor.subject())
            .map(OrderDto::from)
            .switchIfEmpty(
                Mono.error(new OrderNotFoundException())
            );
    }
}
```

Imports:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;
```

`@PreAuthorize` checks scopes when the method-security proxy applies. The repository query enforces resource-level owner/tenant checks. Never conflate the two.

### 22.1. Method Security Also Relies on Reactor Context

Reactive method security reads `Authentication` from the Reactor Context. Calling a service under a subscription detached from the request context or via self-invocation that bypasses the proxy can skip the annotation.

**Test through the real entrypoint/proxy** when proving method security works, and test object policies in the service/repository separately.

### 22.2. Reactive Authorization When Querying a Database

A policy needing database I/O should use a reactive repository and an authorization mechanism supporting `Mono<Boolean>` or `ReactiveAuthorizationManager` per your Spring Security version. Never write `@PreAuthorize` expressions invoking blocking JDBC methods to compute access.

You can adopt this split:

```text
@PreAuthorize: check operational authority (no I/O)
Service: reactive policy/repository checks tenant/owner/ACL
Mutation: conditional update / appropriate transaction
```

That is far easier to reason about.

## 23. Testing Negative Cases: 401, 403, and Business Errors

A matrix:

| Scenario | Authentication | Authorization | Typical HTTP |
|---|---|---|---|
| No Bearer token sent to protected API | Unauthenticated | Access denied | `401` |
| Inactive opaque token | Introspection rejects | Scope not evaluated | `401 invalid_token` |
| AS returns malformed response | Introspection failure | Access not evaluated | Auth/infrastructure error per mapping |
| Active token, wrong audience per contract | Wrapper rejects | Access not evaluated | Typically `401` |
| Active token, `profile` scope | Authenticated | GET Orders needs `orders.read` | `403` |
| Active token, read scope, order outside tenant | Authenticated | Object policy denies | `403` or `404` |
| Active token, sufficient scope, missing order | Authenticated | Resource absent | `404` |
| Active token, sufficient rights, invalid order state | Authenticated | Invalid business state | `409` or domain code |
| AS timeout | Could not authenticate | Blocked from proceeding | Fail closed; status depends on exception flow |

`401` and `403` must not be used interchangeably. An active token lacking a scope may still work on other endpoints; never treat it as revoked.

### 23.1. Never Send Sensitive Error Details to Clients

Never return raw introspection responses, client secrets, bearer tokens, internal network topology, or another user's object principals. Log general error categories and request IDs; keep diagnostics inside access-controlled logs.

### 23.2. CORS on Browser Requests

A cross-origin SPA requires proper CORS headers on both success and 401/403 responses if the frontend reads status codes. Preflights typically carry no Bearer token; if blocked by premature authentication requirements, browsers report CORS errors before sending the real request.

## 24. Trace/Correlation Context Is Not Authentication Context

Applications often use:

- Reactor Context: Authentication/trace metadata.
- MDC/SLF4J: thread-scoped logging key-values.
- OpenTelemetry tracing context.
- `ServerWebExchange` attributes.
- HTTP header `X-Request-Id`.

These mechanisms can integrate, yet **are not automatically identical**.

### 24.1. Thread-Scoped MDC Differs from Reactor Context

A call like:

```java
MDC.put("userId", "user-123");
```

binds data to the current thread per the MDC implementation. When a reactive pipeline switches threads, values can disappear unless explicit context propagation is configured. Conversely, `ReactiveSecurityContextHolder.getContext()` reads the Reactor Context, not MDC.

Never use MDC as the principal source for authorization.

### 24.2. Safe Correlation IDs

A log entry may include:

```text
request_id=req-123
route=GET /api/orders/{id}
token_introspection=SUCCESS
authorization=DENIED
reason=ORDER_NOT_VISIBLE
```

Avoid:

```text
Authorization: Bearer <RAW_ACCESS_TOKEN>
Introspection-Client-Secret: <SECRET>
Cookie: SESSION=<SECRET>
```

If a correlation ID comes from the client, validate/sanitize it before logging. Never treat `X-Request-Id` as identity or proof of a valid token.

## 25. Background Jobs, Messages, and Losing HTTP Context

An HTTP request may schedule a background job:

```http
POST /api/reports/export
Authorization: Bearer <OPAQUE_TOKEN>
```

When the job executes minutes later on another scheduler or service, the **original HTTP request's** Reactor `SecurityContext` does not exist there automatically.

Design for this:

- Record actor ID/issuer/tenant and permitted scope from the verified principal.
- Re-check permissions at execution time when required by business rules.
- Never store raw bearer tokens unnecessarily in job payloads.
- Never let a broad-privilege service account bypass the original actor's object-level limits.
- Establish clear lifecycle, idempotency, and auditing for jobs.
- If downstream delegation is required, use contracted token-exchange or delegated-access mechanisms.

**Never read `ReactiveSecurityContextHolder.getContext()` inside a job and "invent" a default actor when empty.** Jobs need an explicit identity/authorization contract.

## 26. Testing Introspection Caching and Permission Freshness

Opaque introspection is valuable when checking with the AS whether a token is still active. If caching results:

- Latency and HTTP introspection volume drop.
- However, revoked tokens may remain accepted until the cache expires.
- Scope, tenant, or membership updates may lag behind.
- Cache keys must never expose raw bearer credentials.
- TTL must align with expiration and revocation requirements.
- Changes to wrapper policy may require cache invalidation.

### 26.1. Cache Before or After the Wrapper?

```text
Bearer token
    │
    ├── delegate introspection
    │        └── active + claims
    │
    ├── contract wrapper
    │        └── aud/issuer/client/tenant validation
    │
    └── accepted principal
```

Caching **after the wrapper** stores contract-validated results, yet must invalidate when policies change. Caching **before the wrapper** requires running contract checks on every cache hit. Either way, **never store failed authentication results as success**.

### 26.2. How to Test Caching?

Use a fake delegate counting subscriptions:

```java
AtomicInteger calls = new AtomicInteger();

ReactiveOpaqueTokenIntrospector delegate = token ->
    Mono.defer(() -> {
        calls.incrementAndGet();
        return Mono.just(testPrincipal);
    });
```

Then issue multiple calls for the same token to verify cache hits/misses, TTLs, and invalidation. Note that this only tests local caching logic, not production AS revocation behavior.

### 26.3. Principal-Scoped Caching Mistakes

Never cache business responses keyed solely by `orderId` when returned data depends on subject/tenant/scope. A cache hit is not proof of authorization. Enforce object authorization before serving cached data or isolate cache keys appropriately.

## 27. Multi-Tenant and Multi-Issuer Reactive Introspection

A Resource Server may accept tokens from multiple ASs/realms:

```text
AS shop:
  https://login.example.test/realms/shop/introspect

AS partners:
  https://login.example.test/realms/partners/introspect
```

Each issuer may have:

- Different introspection URLs and client credentials.
- Different scope claim/authority naming.
- Different tenant claim semantics.
- Different audience and client ID rules.
- Different subject namespaces.

For multi-issuer support, use an **allowlisted** resolver/mapping of trusted authentication managers/introspectors. Never read URLs from unverified token strings and call arbitrary endpoints—that risks SSRF or accepting principals from an attacker-controlled AS.

### 27.1. Propagating Issuer-Qualified Identities

If two issuers both emit `sub=user-123`, they may represent two distinct people. The actor passed to object authorization often needs **`(issuer, subject)`** or an internal account mapping.

Never merge users solely by principal name or email unless uniqueness is guaranteed by contract.

### 27.2. Testing Multiple Issuers

At minimum:

| Token | AS response | Orders API policy | Outcome |
|---|---|---|---|
| Shop token for Orders | active, right `aud`, shop tenant | Allow | Passes authentication |
| Allowlisted partner token | active, meets partners contract | Conditionally allow | Passes authentication |
| Token from untrusted issuer | URL/realm outside allowlist | Reject | Never introspect arbitrary endpoint |
| Payments AS token | active, `aud=payments` | Reject | Denied at Orders |
| Token missing required tenant | active, missing claim | Reject per contract | Never auto-fill tenant |
| Token from an AS in outage | Unverified | Fail closed | No Authentication created |

## 28. Measuring Performance Without Trading Away Security

Metrics worth tracking:

| Metric | Question |
|---|---|
| Introspection latency p50/p95/p99 | Is the AS responding quickly and stably? |
| Active/inactive token rate | How many invalid tokens are arriving? |
| Timeout/network/TLS errors | Is the AS or network experiencing trouble? |
| In-flight introspection requests | Are too many requests piling up? |
| Event-loop blocking detections | Is blocking code present in the reactive pipeline? |
| WebFlux event-loop utilization | Are I/O threads abnormally pinned? |
| 401 vs. 403 counts | Authentication failures vs. insufficient privileges? |
| Request-to-service identity mismatches | Is there risk of lost/bleeding security context? |
| Cache hit/miss, revoked token window | Is caching keeping stale permissions alive too long? |
| Reactive repository latency | Is object-level policy creating a bottleneck? |

### 28.1. Measuring Under Concurrent Load

A single passing HTTP test is not enough. Test tens or hundreds of concurrent requests appropriate for your test environment against an AS stub with controlled delays. Observe:

- Whether latency scales weirdly with event-loop thread counts.
- Whether `block()`/`ThreadLocal` assumptions trigger sporadic failures.
- Whether user A/B tenants ever bleed together.
- Whether other requests keep succeeding when one introspection fails.
- Whether connection resources are released cleanly on timeouts.

Never run an uncontrolled micro-benchmark and declare "WebFlux is always faster than Servlet." Results depend on AS, TLS, HTTP pooling, CPU, DB, and architecture.

### 28.2. Bounded Concurrency and Backpressure

An API can be attacked with floods of random Bearer tokens forcing the introspection endpoint to handle massive traffic. Enforce:

- Pre-auth rate limiting by source/caller where feasible.
- Connection pool, concurrency caps, and queue limits.
- Appropriate timeouts and circuit breaking.
- Zero retries on invalid tokens.
- Size limits on Authorization headers/tokens.
- Monitoring invalid-token request ratios.
- Never turning an AS outage into fake principals.

## 29. Classification Table of Test Tiers

| Test type | Tools | What it verifies | What it does not prove |
|---|---|---|---|
| Introspector unit | `StepVerifier` + fake delegate | Success/error, contract, lazy subscription | Real HTTP AS / non-blocking networking |
| Reactive time behavior | `StepVerifier` virtual time | Timeout/retry operators | TLS/socket behavior |
| Context test | `ReactiveSecurityContextHolder.withAuthentication` | Reactor context across operators | Real token introspection |
| HTTP authorization | `WebTestClient` + `mockOpaqueToken` | 401/403/role/scope/actor access at web layer | Real AS introspection |
| Integration introspection | `WebTestClient` + HTTP AS stub + real Bearer header | WebFilter → HTTP delegate → principal → service | Production AS availability |
| Non-blocking instrumentation | BlockHound / tracing / under-load tests | Some blocking calls / event-loop starvation | Every possible concurrency/blocking bug |
| Business object policy | Reactive repository/service tests | Tenant/owner/ACL/list/export | Signature/introspection validity |
| Load/performance | Reactive traffic + AS stub/test AS | Throughput, latency, saturation, timeouts | Correct permission rules unless data is tested |

You do not need to cram every assertion into one giant test. Separating test tiers makes pinpointing failing layers straightforward.

## 30. Required End-to-End Behavior Matrix

| Input | Expected introspection | Authentication context | Expected API outcome |
|---|---|---|---|
| No Bearer token | AS not called for this request | No authenticated bearer principal | Protected routes typically return 401 |
| Inactive opaque token | Returns `active=false` | No trusted principal created | Typically 401 |
| Active opaque token, `orders.read` | Success | Actor with right `sub`/tenant | GET visible order succeeds |
| Active token, missing `orders.read` | Success | Actor lacks required scope | GET Orders typically returns 403 |
| Active token, wrong audience | Delegate active, wrapper rejects | No trusted principal | Authentication failure |
| Active token, another user's order | Success | Actor matches caller user | Object policy returns 403/404 |
| Active token, mismatched tenant | Per token contract or service | Cannot access out-of-scope tenant | Deny |
| AS timeout | Publisher error/timeout | No Authentication | Fail closed |
| AS returns malformed JSON | Introspection error | No Authentication | Fail closed |
| Two concurrent users | Two introspection results | Isolated A/B contexts | No cross-user data leakage |
| `publishOn` in service | Introspection success | Reactor Context continues through chain | Subject remains accurate |
| Job detaches subscription from request | No default HTTP context | Never fabricate actor | Use explicit delegated actor/policy |

## 31. Common Mistakes

### Mistake 1 — Using Servlet `OpaqueTokenIntrospector` for WebFlux

Easily introduces synchronous I/O into the reactive path. Use `ReactiveOpaqueTokenIntrospector` and a proper reactive implementation.

### Mistake 2 — Assuming Returning `Mono` Means Non-Blocking

`Mono.just(blockingCall())` still runs blocking code upfront; `Mono.defer(blockingCall)` still blocks upon subscription. Inspect actual transport and threads.

### Mistake 3 — Calling `block()` to Fetch the Principal in a Controller

Stalls the event loop or throws exceptions. Use reactive composition, `@AuthenticationPrincipal`, or an actor adapter.

### Mistake 4 — Calling `subscribe()` Manually to "Kick Off" Authentication

Creates a detached subscription where errors and context fail to propagate. Return the publisher to Spring Security.

### Mistake 5 — Reading ThreadLocal `SecurityContextHolder` Like Servlet

In WebFlux, use Reactor Context; tests must use `ReactiveSecurityContextHolder` or an explicit actor.

### Mistake 6 — Using `mockOpaqueToken()` and Concluding AS Introspection Works

The mock skips HTTP introspection. Add integration tests with real Bearer headers and an AS stub.

### Mistake 7 — Running `StepVerifier` on One Valid Token and Claiming Non-Blocking

`StepVerifier` asserts signals, not blocking I/O. Use instrumentation, load tests, and client implementation review.

### Mistake 8 — Turning AS Errors into `Mono.just(adminPrincipal)`

This is a severe *fail open* vulnerability; never do it.

### Mistake 9 — Confusing `active=true` with Full Permissions

Read/write endpoints still require authorities; records still require owner/tenant policies.

### Mistake 10 — Taking the Actor from Request Body or Headers

Clients can spoof `tenantId` or `sub`. Build actors solely from AS-verified principals or server-side memberships.

### Mistake 11 — Storing `Authentication` in a Static Variable

Concurrent requests scramble principals. Security context must follow the subscriber/request, never shared mutable state.

### Mistake 12 — Losing Context in Jobs or Out-of-Band Callbacks

Never fabricate identities or forward raw tokens unnecessarily. Pass explicit actors/delegation per contract.

### Mistake 13 — Calling Blocking DBs Inside Object Policies

A reactive authentication chain still stalls if the repository blocks. Use reactive data access or isolate legacy operations within strict bounds.

### Mistake 14 — Blocking CORS Preflights for Missing Tokens

Browser preflights normally carry no Bearer token. CORS policy must run before real request authentication.

### Mistake 15 — Caching Introspection Indefinitely

Allows revoked tokens to remain valid. TTLs and invalidation must satisfy revocation requirements.

### Mistake 16 — Logging Raw Opaque Tokens or Client Secrets

Tokens and secrets are credentials. Log request IDs, routes, and error categories—never raw Authorization headers.

### Mistake 17 — Putting All Database Queries Inside the Introspector

The introspector should check token-wide contracts. Per-order-ID and tenant permissions belong in the service/authorization layer.

### Mistake 18 — Confusing 401 and 403 Errors

Authentication failures are typically 401; accepted tokens lacking privileges are typically 403; business object policies may return 403/404. Preserve exact semantics.

### Mistake 19 — Letting Any Issuer Pick the Introspection Endpoint

Selecting URLs from unverified tokens risks SSRF or trusting an attacker's AS. Use a trusted allowlist/mapping.

### Mistake 20 — Not Testing Multiple Tenants and Users

Tests with only one user miss context leaks, missing owner/tenant query filters, and static-principal bugs.

## 32. Roadmap for Building Reliable Verification

**Step 1.** Define the AS opaque-token contract: `active`, `sub`, `scope`, `aud`, tenant fields, response/error semantics, and introspection credentials.

**Step 2.** Configure the WebFlux `SecurityWebFilterChain` and `ReactiveOpaqueTokenIntrospector` properly. Never use Servlet configuration.

**Step 3.** Prefer Spring Security's reactive implementation to call the AS. For custom wrappers, use `Mono.defer`, `flatMap`, `Mono.error`, and fail closed.

**Step 4.** Use `StepVerifier` to test success, inactive, wrong audience, empty results, exception propagation, and timeout behavior.

**Step 5.** Verify laziness with counters/stubs; **never treat that test as proof of non-blocking execution**.

**Step 6.** Use BlockHound/instrumentation and a delayed AS stub to check event-loop blocking, concurrency, and timeouts.

**Step 7.** Use `ReactiveSecurityContextHolder.withAuthentication(...)` to verify context across `map`/`flatMap`/`publishOn`.

**Step 8.** Use `WebTestClient` with `mockOpaqueToken()` to test routes, scopes, 403s, principal injection, and object policies.

**Step 9.** Use `WebTestClient` **without `mockOpaqueToken`**, sending real Bearer headers against an AS stub to test the full introspection path.

**Step 10.** Prepare fixtures with two users, two tenants, and at least one order owned by another user; test cross-tenant denial and list filtering.

**Step 11.** Verify error responses, CORS, unauthenticated requests, AS outages, and zero token/secret leakage.

**Step 12.** Measure under concurrent load, watching p95/p99 latency, timeouts, event-loop saturation, and context isolation.

## 33. References

- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token, Reactive](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html): reactive introspection configuration, authorities, and custom introspectors.
- [Spring Security Reference — Testing OAuth 2.0 in WebFlux](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockOpaqueToken()`, `WebTestClient`, and mocking principals/authorities.
- [Spring Security Reference — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): `@EnableReactiveMethodSecurity`, reactive authorization, and access decisions.
- [Spring Security API — ReactiveSecurityContextHolder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html): `getContext()`, `withAuthentication(...)`, and Reactor Context.
- [Spring Security Reference — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `ServerHttpSecurity` and `SecurityWebFilterChain`.
- [Project Reactor Reference — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): Context propagation, `contextWrite`, and subscription semantics.
- [Project Reactor Reference — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, virtual time, and testing reactive publishers.
- [BlockHound](https://github.com/reactor/BlockHound): tool for detecting certain blocking calls on reactive threads when configured compatibly.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): introspection request/response and the `active` attribute.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer credential presentation, errors, and HTTP authentication semantics.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): default deny, least privilege, and object-level authorization.

**Conclusion:** Testing an opaque-token Resource Server in WebFlux must prove that **tokens are introspected and verified properly**, **publishers genuinely avoid blocking the event loop**, and **Authentication stays bound to the Reactor subscriber context all the way to handler layers**. Use `ReactiveOpaqueTokenIntrospector` with a trusted reactive HTTP implementation; use `StepVerifier` for publishers and timeouts, `ReactiveSecurityContextHolder.withAuthentication` for context, `WebTestClient + mockOpaqueToken()` for authorization, and **`WebTestClient` + an introspection HTTP stub** for the real authentication path. Once a token is active, scopes and owner/tenant permissions must still be enforced across HTTP and service layers. Avoid `block()`, manual `subscribe()`, fake principals on AS outages, shared mutable Authentications, and logging bearer tokens.

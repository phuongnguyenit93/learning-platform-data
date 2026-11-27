# Multi-Tenant Testing and Reactive Authentication Manager Selection

A **multi-tenant Spring Security WebFlux Resource Server** can verify access tokens under multiple rule sets: each tenant may have its own Authorization Server, issuer, signing keys, introspection endpoint, audience, or permission model. The application must solve two tasks: **resolving the tenant** to select the authentication strategy, and **propagating the verified tenant** to authorization and the data layer.

In WebFlux, the primary coordinator is **ReactiveAuthenticationManagerResolver<ServerWebExchange>**. The resolver accepts a ServerWebExchange and returns an appropriate **ReactiveAuthenticationManager** inside a Mono. That manager then verifies the token.

When testing, separate two goals:

- Testing authorization after Authentication is already established: use **WebTestClient** with **mockJwt()**, **mockOpaqueToken()**, or a suitable test Authentication.
- Testing actual manager selection: send **Authorization: Bearer** through SecurityWebFilterChain so the Bearer authentication filter invokes the resolver; use manager test doubles or decoder/introspector stubs.

If you only use mockJwt() or mockOpaqueToken(), tests can verify post-authentication tenant policies but cannot prove the resolver chose the right manager.

## 1. What Does Multi-Tenancy Mean in a Resource Server?

Spring Security treats a Resource Server as multi-tenant when it has **multiple Bearer token verification strategies**, selected based on a tenant identifier.

Example:

| Tenant | Issuer / Authorization Server | Token strategy | Audience |
|---|---|---|---|
| tenant-a | https://id-a.example.com | JWT/JWKS | orders-api-a |
| tenant-b | https://id-b.example.com | JWT/JWKS | orders-api-b |
| partner-c | https://partner.example.com | Opaque/introspection | partner-api |

A system can also have multiple tenants sharing the same issuer while each tenant has a distinct tenant claim, client policy, or audience.

**Multi-tenancy is not merely adding a tenant_id claim to a JWT.** The Resource Server must select the right validator/manager, verify the token against the right trust contract, and ensure the request only accesses data belonging to the authenticated tenant.

### 1.1. Two Phases: Resolve and Propagate

~~~mermaid
flowchart TD
    R[HTTP request + Bearer token] --> T[Resolve tenant / strategy]
    T --> M[Matching ReactiveAuthenticationManager]
    M --> V[Verify token: signature or introspection]
    V -->|Invalid| DENY[Authentication failure]
    V -->|Valid| A[Authenticated Authentication]
    A --> P[Propagate tenant from verified claims/principal]
    P --> Z[Authorization: scope, role, tenant, ownership]
    Z -->|Authorized| DATA[Tenant-scoped repository query]
    Z -->|Denied| FORBID[403 or 404 per policy]
~~~

**Resolving the tenant** picks which manager is called. **Propagating the tenant** ensures the authentication result carries the verified tenant identity so downstream layers use it accurately.

If a resolver picks the `tenant-a` manager while the controller reads the tenant from a client-supplied query parameter, the system still risks cross-tenant access.

### 1.2. What Needs to Be Separated

| Component | Question answered |
|---|---|
| Tenant resolver | Which tenant/strategy does the request belong to? |
| ReactiveAuthenticationManager | Is the token valid under that strategy? |
| ReactiveJwtDecoder | Are the JWT signature and claims valid? |
| ReactiveOpaqueTokenIntrospector | Is the opaque token active and what are its attributes? |
| Authentication principal | Who is calling, and which tenant do they belong to? |
| Authorization | Does the principal have permission for this endpoint/resource? |
| Repository/domain policy | Is returned data restricted to the right tenant/owner? |

Do not treat the resolver returning a manager as proof that the token is valid. The resolver only routes; the manager verifies the credential.

## 2. How Does ReactiveAuthenticationManagerResolver Work?

General interface:

~~~java
public interface ReactiveAuthenticationManagerResolver<C> {
    Mono<ReactiveAuthenticationManager> resolve(C context);
}
~~~

For a WebFlux Resource Server, the context is typically **ServerWebExchange**:

~~~java
ReactiveAuthenticationManagerResolver<ServerWebExchange>
~~~

The resolver returns a ReactiveAuthenticationManager in a Mono. The manager has an `authenticate` method taking an Authentication request and returning `Mono<Authentication>`:

~~~java
public interface ReactiveAuthenticationManager {
    Mono<Authentication> authenticate(Authentication authentication);
}
~~~

For Bearer authentication, the request object built from the HTTP Bearer token is typically **BearerTokenAuthenticationToken**.

Conceptual processing flow:

~~~text
HTTP request
  -> BearerTokenAuthenticationWebFilter
  -> AuthenticationConverter creates BearerTokenAuthenticationToken
  -> ReactiveAuthenticationManagerResolver.resolve(exchange)
  -> Mono<ReactiveAuthenticationManager>
  -> manager.authenticate(authentication)
  -> Mono<Authentication>
  -> SecurityContext
  -> authorization
~~~

### 2.1. Why Does the Resolver Receive ServerWebExchange?

ServerWebExchange provides the request context:

- HTTP method and path.
- Host and request headers.
- Query parameters.
- Server request/response.
- Attributes placed on the exchange by trusted web filters.

The resolver can use routes, hosts, or gateway-verified metadata to select a manager. However, **not everything in a request is trustworthy**. Self-asserted client headers must never become the sole source determining which tenant a caller may access.

### 2.2. Selecting a Manager Does Not Equal Verifying the Token

Example path-based resolver:

~~~text
/t/tenant-a/** -> tenant-a manager
/t/tenant-b/** -> tenant-b manager
~~~

If a request to `/t/tenant-a/orders` carries a `tenant-b` token, the `tenant-a` manager must reject the token or policy must reject the tenant mismatch after verification.

Do not fall back to the `tenant-b` manager to "try whether the token is valid." Falling back across trust domains can accept tokens outside the endpoint's policy.

## 3. Selecting Tenants by Issuer Claim with JwtIssuerReactiveAuthenticationManagerResolver

When each tenant has its own JWT issuer, the direct approach is **JwtIssuerReactiveAuthenticationManagerResolver**.

Example:

~~~java
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerReactiveAuthenticationManagerResolver;

JwtIssuerReactiveAuthenticationManagerResolver resolver =
    JwtIssuerReactiveAuthenticationManagerResolver.fromTrustedIssuers(
        "https://id-a.example.com",
        "https://id-b.example.com"
    );

http
    .authorizeExchange(authorize -> authorize
        .anyExchange().authenticated()
    )
    .oauth2ResourceServer(oauth2 -> oauth2
        .authenticationManagerResolver(resolver)
    );
~~~

The resolver reads the **iss** claim in the Bearer JWT to identify the issuer, then selects the corresponding JWT-based ReactiveAuthenticationManager.

### 3.1. Issuers Must Be in a Trusted List

An unverified JWT can claim anything:

~~~json
{
  "iss": "https://attacker.example.net",
  "sub": "admin",
  "tenant_id": "tenant-a"
}
~~~

An unverified `iss` value can only serve as a **routing hint** to an allowlisted issuer. It does not prove the token was issued by that issuer.

Never read an arbitrary `iss` and dynamically build a ReactiveJwtDecoder/JWKS client for any URL. That opens the trust boundary to an attacker-controlled Authorization Server and introduces SSRF risks.

Use:

~~~java
JwtIssuerReactiveAuthenticationManagerResolver.fromTrustedIssuers(
    "https://id-a.example.com",
    "https://id-b.example.com"
);
~~~

or a system-managed registry.

### 3.2. Managers Are Created Lazily

Spring Security can create the manager for an issuer when the first request carrying that issuer arrives. This lets the application start without requiring all Authorization Servers to be reachable at startup.

In return, the first request may have to wait for discovery/JWKS initialization. Verify:

- Timeouts and network dependencies during initialization.
- Decoder/manager caching.
- Issuer allowlists.
- Behavior when an issuer is unavailable.
- Metrics for first-time resolution/initialization.

### 3.3. Audience Must Still Be Checked Separately

A trusted issuer A does not mean every token from issuer A can be used on every Resource Server.

An example token:

~~~json
{
  "iss": "https://id-a.example.com",
  "aud": ["billing-api"],
  "tenant_id": "tenant-a",
  "scope": "billing.read"
}
~~~

must not be accepted at `orders-api` merely because the issuer matches. The `tenant-a` manager's decoder/validators must verify the appropriate audience, expiry, and token profile.

## 4. Dynamic Tenant Registry

When tenants can be added or removed at runtime, you can maintain a registry:

~~~java
Map<String, ReactiveAuthenticationManager> managers;
~~~

Under concurrent requests, use an appropriate structure such as **ConcurrentHashMap** or an atomically swapped immutable registry.

Spring Security supports constructing **JwtIssuerReactiveAuthenticationManagerResolver** with a strategy resolving an issuer to a manager. Example:

~~~java
import java.util.Map;

import reactor.core.publisher.Mono;

import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.ReactiveAuthenticationManagerResolver;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerReactiveAuthenticationManagerResolver;

Map<String, ReactiveAuthenticationManager> managers = loadTrustedManagers();

ReactiveAuthenticationManagerResolver<String> issuerResolver =
    issuer -> Mono.justOrEmpty(managers.get(issuer));

JwtIssuerReactiveAuthenticationManagerResolver resolver =
    new JwtIssuerReactiveAuthenticationManagerResolver(issuerResolver);
~~~

In this example, map keys are trusted issuers. An issuer absent from the map has no manager.

### 4.1. Creating a Manager for a New Tenant

An administrative workflow can:

1. Verify the tenant is eligible for onboarding.
2. Validate the issuer URL from managed configuration.
3. Load metadata/JWKS or build an introspector per trust policy.
4. Create the ReactiveAuthenticationManager.
5. Register the manager in the registry.
6. Verify health/metrics before opening traffic.
7. Include a procedure to remove the manager and caches when a tenant is disabled.

If the discovery API performs blocking operations, do not run it on the Reactor event loop. Spring Security illustrates creating a ReactiveJwtDecoder from an issuer location inside `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`.

~~~java
Mono<ReactiveAuthenticationManager> createJwtManager(String issuer) {
    return Mono.fromCallable(
            () -> ReactiveJwtDecoders.fromIssuerLocation(issuer)
        )
        .subscribeOn(Schedulers.boundedElastic())
        .map(JwtReactiveAuthenticationManager::new);
}
~~~

Only invoke this function after the issuer has been validated against a trusted tenant registry. Never allow the first incoming request to self-register a new issuer.

### 4.2. Updating the Registry Safely

When adding/removing tenants:

- Use a thread-safe registry.
- Avoid unsynchronized mutable maps shared across requests.
- Do not tear down an in-flight manager in a way that breaks active requests mid-flight.
- Maintain a version/config revision for the tenant registry.
- Prevent disabled tenants from having managers recreated via lazy fallback.
- Audit who modifies issuers, audiences, introspection URIs, or signing keys.

## 5. Selecting Managers by Path, Host, or Trusted Request Metadata

Not every tenant has its own JWT issuer. A system may share a gateway/issuer yet split strategies by route or host.

Example:

~~~text
https://tenant-a.api.example.com/** -> manager A
https://tenant-b.api.example.com/** -> manager B
/api/partners/**                   -> opaque manager
/api/internal/**                   -> JWT manager
~~~

You can implement a custom resolver:

~~~java
import java.util.Map;

import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.ReactiveAuthenticationManagerResolver;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

class TenantPathAuthenticationManagerResolver
        implements ReactiveAuthenticationManagerResolver<ServerWebExchange> {

    private final Map<String, ReactiveAuthenticationManager> managers;

    TenantPathAuthenticationManagerResolver(
            Map<String, ReactiveAuthenticationManager> managers) {
        this.managers = Map.copyOf(managers);
    }

    @Override
    public Mono<ReactiveAuthenticationManager> resolve(
            ServerWebExchange exchange) {

        String path = exchange.getRequest().getPath().value();
        String tenant;

        if (path.startsWith("/t/tenant-a/")) {
            tenant = "tenant-a";
        }
        else if (path.startsWith("/t/tenant-b/")) {
            tenant = "tenant-b";
        }
        else {
            return Mono.error(unknownTenant());
        }

        ReactiveAuthenticationManager manager = this.managers.get(tenant);
        if (manager == null) {
            return Mono.error(unknownTenant());
        }

        return Mono.just(manager);
    }

    private OAuth2AuthenticationException unknownTenant() {
        OAuth2Error error = new OAuth2Error(
            OAuth2ErrorCodes.INVALID_TOKEN,
            "No authentication strategy is configured for this tenant",
            null
        );
        return new OAuth2AuthenticationException(error);
    }
}
~~~

The example above uses path to illustrate routing. In production, the selected manager must still verify that the token belongs to the right tenant, issuer, and audience. A client-selected path does not by itself grant tenant access.

### 5.1. Using Host

If using hostnames to select tenants, verify the host belongs to a registered domain. Consider:

- Client-sent `Host` headers.
- TLS SNI and ingress host routing.
- Whether a reverse proxy rewrites the host.
- Domain aliases and custom domains.
- Host normalization.
- Whether the backend can be reached directly.

Never use an arbitrary host to construct a decoder or introspection URL.

### 5.2. Using Forwarded Headers

If a gateway sends `X-Tenant-ID` or `Forwarded`, trust only values set by a managed gateway after the gateway strips any client-supplied header with the same name.

Never use an untrusted `X-Tenant-ID` header as authorization grounds. After the manager verifies the token, confirm the tenant in the verified principal/claims matches the selected tenant.

### 5.3. ServerWebExchangeDelegatingReactiveAuthenticationManagerResolver

Spring Security provides **ServerWebExchangeDelegatingReactiveAuthenticationManagerResolver** to select managers based on `ServerWebExchange` and request matchers.

It is useful when there are many path/host/header rules and you want matcher-structured resolution. For a few simple routes, a lambda or a class implementing `ReactiveAuthenticationManagerResolver` is often easier to read.

Whether using the builder or a custom resolver, define clear default behavior. Requests matching no tenant must be rejected rather than falling into an overly broad default manager.

## 6. Choosing Between a JWT Manager and an Opaque Manager

One tenant may use JWT; another may use opaque tokens.

| Token strategy | Verification component | Manager |
|---|---|---|
| JWT | ReactiveJwtDecoder | JwtReactiveAuthenticationManager |
| Opaque token | ReactiveOpaqueTokenIntrospector | OpaqueTokenReactiveAuthenticationManager |

Example building both managers:

~~~java
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtReactiveAuthenticationManager;
import org.springframework.security.oauth2.server.resource.authentication.OpaqueTokenReactiveAuthenticationManager;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;

ReactiveAuthenticationManager jwtManager(ReactiveJwtDecoder decoder) {
    return new JwtReactiveAuthenticationManager(decoder);
}

ReactiveAuthenticationManager opaqueManager(
        ReactiveOpaqueTokenIntrospector introspector) {
    return new OpaqueTokenReactiveAuthenticationManager(introspector);
}
~~~

The resolver can pick the manager via route/tenant registry. Do not let both managers try a Bearer token until one succeeds without a clear trust contract.

### 6.1. JWT Manager

`JwtReactiveAuthenticationManager` uses `ReactiveJwtDecoder` to:

- Decode the JWT.
- Verify the signature against configured keys/algorithms.
- Run validators.
- Convert the `Jwt` into an Authentication and authorities.

A tenant-specific decoder must verify issuer, audience, and tenant-related claims.

### 6.2. Opaque Manager

`OpaqueTokenReactiveAuthenticationManager` uses `ReactiveOpaqueTokenIntrospector` to obtain an `OAuth2AuthenticatedPrincipal`.

Each tenant can have its own introspection endpoint and client authentication. Never use an introspection URI or client credentials supplied by the request.

Introspection timeouts, AS 5xx errors, or inactive tokens must result in authentication failure. Never fabricate a default principal for availability.

### 6.3. Do Not Parse JWTs to Decide on the Opaque Strategy

Opaque tokens have no JWT issuer claim for a resolver to inspect reliably. Never rely on dot counts, string length, or formatting heuristics to decide whether a token is JWT or opaque.

If a tenant already specifies the token type via route/configuration, use the corresponding manager. If a tenant supports multiple token formats, use an explicitly managed and tested classification mechanism rather than falling back across trust domains.

## 7. Attaching the Resolver to SecurityWebFilterChain

WebFlux configuration example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManagerResolver;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.server.ServerWebExchange;

@Configuration
class MultiTenantResourceServerConfiguration {

    @Bean
    SecurityWebFilterChain api(
            ServerHttpSecurity http,
            ReactiveAuthenticationManagerResolver<ServerWebExchange> resolver) {

        return http
            .authorizeExchange(authorize -> authorize
                .pathMatchers("/public/**").permitAll()
                .pathMatchers("/t/**/admin/**")
                    .hasAuthority("SCOPE_admin")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationManagerResolver(resolver)
            )
            .build();
    }
}
~~~

This is an illustrative configuration. Define tenant-specific authorization policies and validators on the managers. `permitAll()` for public routes does not mean other protected routes are skipped.

### 7.1. One SecurityWebFilterChain or Multiple Chains?

If tenants share the same filters and differ only in the manager, a single chain with an `AuthenticationManagerResolver` may fit.

If route groups have different CSRF, CORS, session, entry point, or authorization policies, multiple specialized `SecurityWebFilterChain` beans can be easier to control. With multiple chains, test match order so a broad chain does not intercept requests before a tenant-specific chain.

### 7.2. The Resolver Does Not Replace Authorization

Just because the `tenant-a` manager authenticated a token does not mean that token may call every `tenant-a` endpoint.

After authentication, still check:

- Scopes/roles.
- Audience/resource.
- Tenant claim.
- User/client status.
- Ownership.
- HTTP method and domain operation.

## 8. Propagating the Tenant After Authentication Succeeds

The tenant must be derived from **verified** data.

With JWT, there may be a claim:

~~~json
{
  "iss": "https://id-a.example.com",
  "sub": "user-1001",
  "aud": ["orders-api-a"],
  "tenant_id": "tenant-a",
  "scope": "orders.read"
}
~~~

With opaque tokens, the introspection principal may have matching attributes:

~~~json
{
  "active": true,
  "sub": "user-1001",
  "tenant_id": "tenant-a",
  "scope": "orders.read"
}
~~~

After verification, controllers/services can read the tenant from the principal. Never take the tenant from an untrusted query parameter or header.

### 8.1. Reading the Tenant from a JWT Principal

~~~java
@GetMapping("/api/orders")
Mono<OrderPage> orders(@AuthenticationPrincipal Jwt jwt) {
    String tenantId = jwt.getClaimAsString("tenant_id");
    String subject = jwt.getSubject();

    return orderService.findOrders(tenantId, subject);
}
~~~

This example assumes `tenant_id` is a mandatory claim. Production must handle missing/wrong-typed claims and reject per contract.

### 8.2. Reading the Tenant from an Opaque Principal

~~~java
@GetMapping("/api/orders")
Mono<OrderPage> orders(
        @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {

    String tenantId = principal.getAttribute("tenant_id");
    String subject = principal.getAttribute("sub");

    return orderService.findOrders(tenantId, subject);
}
~~~

An opaque token's principal is not a `Jwt`. Do not force every OAuth2 principal into `JwtAuthenticationToken`.

### 8.3. Tenant in the Reactor Context

WebFlux passes `SecurityContext` via the Reactor Context. When retrieving `Authentication` in a reactive service:

~~~java
Mono<String> tenantId =
    ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication())
        .map(authentication ->
            ((OAuth2AuthenticatedPrincipal) authentication.getPrincipal())
                .getAttribute("tenant_id")
        );
~~~

This abbreviated example assumes the principal is an `OAuth2AuthenticatedPrincipal`. In production code, provide an abstraction that handles both `Jwt` and opaque principals.

Never use `ThreadLocal` or static mutable fields to store the current tenant. Reactive requests can switch threads and run concurrently.

### 8.4. Route Tenant and Principal Tenant Claim Must Match

If the route selected `tenant-a`, yet the verified JWT carries `tenant_id=tenant-b`, reject it.

~~~text
resolved tenant = tenant-a
verified token tenant_id = tenant-b

=> reject
~~~

If you only check the tenant from the path and ignore the tenant in the token, a client could present another tenant's token on the chosen route and cause cross-tenant confusion.

## 9. Multi-Tenant Testing: Separating Objectives

No single test proves all multi-tenant behavior. Split tests into layers:

| Test type | Question |
|---|---|
| Resolver unit test | Does the request context select the right manager? |
| Filter-chain routing test | Does Authorization Bearer actually pass through the resolver? |
| JWT integration test | Are issuer, signature, audience, and tenant claims verified? |
| Opaque integration test | Does introspection hit the right tenant endpoint and map attributes? |
| Authorization test | Are scope/role/tenant/owner checked? |
| Concurrency test | Do two tenants ever mix SecurityContext or data? |
| Failure test | Do unknown tenants, manager errors, and timeouts fail closed? |

### 9.1. Attaching Spring Security to WebTestClient

To test the filter chain inside the application context, you can build the client as:

~~~java
WebTestClient webTestClient = WebTestClient
    .bindToApplicationContext(applicationContext)
    .apply(springSecurity())
    .configureClient()
    .build();
~~~

Tests need a `spring-security-test` dependency compatible with the Spring Security runtime. When using a WebFlux slice test, ensure `SecurityWebFilterChain` and the resolver are actually loaded into the test context.

### 9.2. Using mockJwt()/mockOpaqueToken() When Testing Authorization

Spring Security Test provides:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOpaqueToken;
~~~

Example `tenant-a` JWT:

~~~java
webTestClient
    .mutateWith(mockJwt().jwt(jwt -> jwt
        .claim("iss", "https://id-a.example.com")
        .claim("sub", "alice")
        .claim("tenant_id", "tenant-a")
        .claim("aud", List.of("orders-api-a"))
        .claim("scope", "orders.read")
    ))
    .get()
    .uri("/api/orders")
    .exchange()
    .expectStatus().isOk();
~~~

Example `tenant-a` opaque principal:

~~~java
webTestClient
    .mutateWith(mockOpaqueToken()
        .attributes(attributes -> {
            attributes.put("sub", "alice");
            attributes.put("tenant_id", "tenant-a");
            attributes.put("scope", "orders.read");
        })
    )
    .get()
    .uri("/api/orders")
    .exchange()
    .expectStatus().isOk();
~~~

These tests are well-suited for testing controllers, method security, and tenant authorization once Authentication is supplied.

**They do not prove AuthenticationManagerResolver chose the right manager.** Mutators create Authentication inside the test exchange; they do not send a Bearer credential through the resolver like a production request.

### 9.3. Using a Real Bearer Header to Test the Resolver

To verify the resolver is invoked via the Resource Server filter chain, send a normal Authorization header:

~~~java
webTestClient
    .get()
    .uri("/t/tenant-a/orders")
    .headers(headers -> headers.setBearerAuth("test-token-a"))
    .exchange()
    .expectStatus().isOk();
~~~

In this test, `SecurityWebFilterChain` must configure `oauth2ResourceServer` with the resolver. The resolver returns the matching manager, and the manager test double authenticates the token.

Do not use `mockJwt()` or `mockOpaqueToken()` in tests aimed at verifying manager selection.

## 10. Testing the Resolver with ReactiveAuthenticationManager Test Doubles

A straightforward approach is building a fake manager per tenant. Each manager returns an Authentication whose principal name reflects the selected tenant.

~~~java
import java.util.Map;

import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.ReactiveAuthenticationManagerResolver;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthenticationToken;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

Map<String, ReactiveAuthenticationManager> managers = Map.of(
    "tenant-a", managerFor("tenant-a"),
    "tenant-b", managerFor("tenant-b")
);

ReactiveAuthenticationManager managerFor(String tenant) {
    return authentication -> {
        if (!(authentication instanceof BearerTokenAuthenticationToken)) {
            return Mono.error(invalidToken());
        }

        return Mono.just(
            new UsernamePasswordAuthenticationToken(
                tenant,
                null,
                AuthorityUtils.createAuthorityList("SCOPE_orders.read")
            )
        );
    };
}

ReactiveAuthenticationManagerResolver<ServerWebExchange> resolver =
    exchange -> {
        String path = exchange.getRequest().getPath().value();
        String tenant;
        if (path.startsWith("/t/tenant-a/")) {
            tenant = "tenant-a";
        }
        else if (path.startsWith("/t/tenant-b/")) {
            tenant = "tenant-b";
        }
        else {
            return Mono.error(unknownTenant());
        }

        return Mono.justOrEmpty(managers.get(tenant))
            .switchIfEmpty(Mono.error(unknownTenant()));
    };

OAuth2AuthenticationException invalidToken() {
    return new OAuth2AuthenticationException(
        new OAuth2Error(OAuth2ErrorCodes.INVALID_TOKEN, "Invalid test credential", null)
    );
}

OAuth2AuthenticationException unknownTenant() {
    return new OAuth2AuthenticationException(
        new OAuth2Error(OAuth2ErrorCodes.INVALID_TOKEN, "Unknown tenant route", null)
    );
}
~~~

This is a **test double** to prove routing. This manager does not verify JWT signatures, introspection, issuers, or tenant claims. Never use it in production.

In production, managers must verify tokens under tenant-specific trust contracts. If a request has no tenant manager, the resolver must produce a clear authentication failure or fail to resolve a manager per tested behavior; never use a permissive default manager that accepts every token.

### 10.1. Attaching the Resolver to the Test SecurityWebFilterChain

~~~java
@Bean
SecurityWebFilterChain testApi(
        ServerHttpSecurity http,
        ReactiveAuthenticationManagerResolver<ServerWebExchange> resolver) {

    return http
        .authorizeExchange(authorize -> authorize
            .anyExchange().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .authenticationManagerResolver(resolver)
        )
        .build();
}
~~~

A test controller can return the Authentication name:

~~~java
@GetMapping("/whoami")
Mono<String> whoami(Authentication authentication) {
    return Mono.just(authentication.getName());
}
~~~

Send:

~~~java
webTestClient
    .get()
    .uri("/t/tenant-a/whoami")
    .headers(headers -> headers.setBearerAuth("test-token-a"))
    .exchange()
    .expectStatus().isOk()
    .expectBody(String.class).isEqualTo("tenant-a");
~~~

Test `tenant-b` similarly. This proves the Bearer request actually traverses the manager resolver and the chosen manager produces the matching principal.

### 10.2. Testing a tenant-b Token on a tenant-a Route

The manager test double should reject tokens not belonging to its tenant. Example:

~~~java
ReactiveAuthenticationManager managerFor(String tenant) {
    return authentication -> {
        if (!(authentication instanceof BearerTokenAuthenticationToken bearer)) {
            return Mono.error(invalidToken());
        }

        if (!("token-" + tenant).equals(bearer.getToken())) {
            return Mono.error(invalidToken());
        }

        return Mono.just(
            new UsernamePasswordAuthenticationToken(
                tenant,
                null,
                AuthorityUtils.createAuthorityList("SCOPE_orders.read")
            )
        );
    };
}
~~~

Then:

~~~java
webTestClient
    .get()
    .uri("/t/tenant-a/orders")
    .headers(headers -> headers.setBearerAuth("token-tenant-b"))
    .exchange()
    .expectStatus().isUnauthorized();
~~~

This is still a routing/manager-contract test using fake tokens. JWT integration tests must verify real signatures/issuers/audiences/tenant claims with a decoder and test keys.

## 11. Unit Testing the Resolver Independently

The resolver can be tested directly with `MockServerWebExchange` without starting the entire WebFlux application.

Conceptual example:

~~~java
MockServerWebExchange exchange =
    MockServerWebExchange.from(
        MockServerHttpRequest.get("/t/tenant-a/orders").build()
    );

StepVerifier.create(resolver.resolve(exchange))
    .expectNext(tenantAManager)
    .verifyComplete();
~~~

Cases to cover:

- `tenant-a` path returns manager A.
- `tenant-b` path returns manager B.
- Path belonging to no tenant returns an authentication failure.
- Unregistered host is rejected.
- Disabled tenant does not resolve a manager.
- Trusted forwarded tenant metadata is handled per policy.
- Requests cannot cause the resolver to instantiate a manager for an arbitrary tenant key.

This unit test checks resolver logic. It does not prove `BearerTokenAuthenticationWebFilter` invoked the resolver properly; combine it with the filter-chain test above.

## 12. Testing JwtIssuerReactiveAuthenticationManagerResolver

When selecting managers by issuer, include tests for:

1. JWT from issuer A routes to manager A.
2. JWT from issuer B routes to manager B.
3. Issuer not in the trusted list is rejected.
4. Malformed JWT or missing issuer is rejected.
5. Valid issuer with wrong signature is rejected.
6. Valid issuer with wrong audience is rejected.
7. Valid issuer with mismatched tenant claim is rejected.

### 12.1. Testing with Signed JWTs and a Test JWKS Server

An integration test can:

- Generate test RSA/EC key pairs for issuers A and B.
- Host metadata/JWKS endpoints in a test server.
- Configure the resolver with trusted issuer URLs.
- Sign JWTs for each issuer.
- Send Authorization Bearer via WebTestClient.
- Verify the right manager/decoder was used.
- Send JWTs with an unknown issuer or wrong signature and assert 401.

Do not use `mockJwt()` to prove the issuer resolver read the `iss` claim and fetched the right key. `mockJwt()` supplies a mock Authentication instead of running real JWT verification.

### 12.2. Unverified Issuer Claim Is Only Used to Pick a Candidate

The resolver may read `iss` from the Bearer JWT before the decoder verifies the signature. Therefore, an allowlist is mandatory.

After picking a manager, `JwtReactiveAuthenticationManager`/the decoder must verify the signature and issuer. Never let an unverified `iss` determine an arbitrary URL to call.

## 13. Testing Opaque Multi-Tenancy with ReactiveOpaqueTokenIntrospector

With opaque tokens, the tenant is typically chosen from route/host/tenant registry because the token has no JWT claims for the Resource Server to inspect directly.

Each manager can use its own `ReactiveOpaqueTokenIntrospector`:

~~~java
ReactiveAuthenticationManager tenantA =
    new OpaqueTokenReactiveAuthenticationManager(introspectorA);

ReactiveAuthenticationManager tenantB =
    new OpaqueTokenReactiveAuthenticationManager(introspectorB);
~~~

Testing with an introspector stub:

~~~java
ReactiveOpaqueTokenIntrospector introspectorA = token -> {
    if (!"token-a".equals(token)) {
        return Mono.error(new BadOpaqueTokenException("Invalid token"));
    }

    Map<String, Object> attributes = Map.of(
        "sub", "alice",
        "tenant_id", "tenant-a",
        "scope", "orders.read"
    );

    OAuth2AuthenticatedPrincipal principal =
        new DefaultOAuth2AuthenticatedPrincipal(
            "alice",
            attributes,
            AuthorityUtils.createAuthorityList("SCOPE_orders.read")
        );

    return Mono.just(principal);
};
~~~

`introspectorB` has its own contract for `tenant-b`.

### 13.1. Verifying the Right Introspector Was Called

Use a spy/mock or a test introspector with counters to check:

- `tenant-a` route calls introspector A.
- `tenant-b` route calls introspector B.
- A `tenant-b` token sent to `tenant-a` is not rescued by introspector B.
- Unknown tenants call no introspector at all.
- Inactive tokens do not produce Authentication.
- Timeouts/5xx errors do not fail open.

When using `mockOpaqueToken()`, these introspectors are never called. For integration tests, send a real Authorization Bearer header through the filter chain.

### 13.2. Do Not Share Client Credentials Across Tenants

Introspection client credentials are server-side secrets. Never read client ID/secret from headers or request parameters to choose an introspection endpoint.

Each tenant manager must use credentials and TLS policies managed for that tenant. Never log raw tokens or introspection client secrets.

## 14. Testing Tenant Propagation and Cross-Tenant Authorization

Having the resolver choose the right manager is not enough. The principal must carry the right tenant and repositories must filter by tenant.

Policy example:

~~~text
GET /t/tenant-a/orders
  tenant-a token + SCOPE_orders.read -> allow

GET /t/tenant-a/orders
  tenant-b token + SCOPE_orders.read -> deny

GET /t/tenant-a/orders/42
  tenant-a token but not owner -> deny

GET /t/tenant-a/orders/42
  tenant-a token, valid owner -> allow
~~~

### 14.1. Test Matrix

| Request route | Token tenant | Scope | Resource tenant | Outcome |
|---|---|---|---|---|
| tenant-a | tenant-a | orders.read | tenant-a | Allow if owner/policy matches |
| tenant-a | tenant-b | orders.read | tenant-a | Deny |
| tenant-b | tenant-b | orders.read | tenant-b | Allow if owner/policy matches |
| tenant-b | tenant-a | orders.read | tenant-b | Deny |
| tenant-a | tenant-a | orders.write | tenant-a, GET-only | Deny if read required |
| tenant-a | tenant-a | orders.read | tenant-b | Deny |
| tenant-a | unknown issuer | orders.read | tenant-a | Authentication failure |

### 14.2. Scope Does Not Replace Tenant Authorization

A token with `SCOPE_orders.read` must not automatically read all orders across all tenants. Repository queries should scope by tenant and subject:

~~~java
Flux<Order> findByTenantIdAndOwnerSubject(
    String tenantId,
    String subject
);
~~~

Do not load system-wide data and filter in the controller. That can leak data via pagination, logs, metrics, or a code branch that forgets to filter.

### 14.3. Route Tenant Must Match Principal Tenant

If the path is `/t/tenant-a/orders` yet the principal has `tenant_id=tenant-b`, reject. Never silently overwrite the principal's tenant with the path tenant.

One implementation pattern is building a domain identity object after verifying Authentication:

~~~java
record TenantIdentity(
    String tenantId,
    String subject,
    Collection<GrantedAuthority> authorities
) {}
~~~

An adapter converts the JWT/opaque principal into `TenantIdentity` and validates mandatory fields. Services use `TenantIdentity` instead of reading request headers directly.

## 15. Testing Tenant Metadata from a Gateway

If a gateway sends:

~~~http
X-Verified-Tenant: tenant-a
~~~

then tests must verify:

1. The gateway strips any client-supplied header with the same name.
2. Only the trusted gateway can reach the backend, or the backend authenticates the gateway source.
3. The backend uses this header to pick a manager from the registry.
4. The manager verifies the token has the right issuer/audience/tenant claim.
5. The verified principal carries the matching tenant.
6. If the header says `tenant-a` yet the token is `tenant-b`, the request is rejected.

Do not only test that the resolver receives the header and returns a manager. That tests routing logic, not that the header is genuinely trustworthy.

If no gateway trust boundary is established, use configured host/path routing and still check the tenant inside the token after authentication.

## 16. Unknown Tenants and Fail-Closed Behavior

Scenarios that must be defined:

| Scenario | Expected behavior |
|---|---|
| No matching tenant route/host | Reject or 404 per API contract |
| Tenant not onboarded | No manager, do not auto-create |
| Tenant disabled | Reject |
| Untrusted issuer | Authentication failure |
| Manager missing | Authentication failure |
| Invalid JWT signature | 401 |
| Wrong JWT audience/tenant | 401 or policy denial per contract |
| Inactive opaque token | 401 |
| Introspection timeout/5xx | Do not create Authentication |
| Manager registry unavailable | Fail closed on authenticated routes |

**Never use a default manager that accepts any token** when the resolver cannot find a tenant.

If you want to return 404 for unknown tenants to avoid disclosing the tenant registry, that is an API routing policy; authentication must still fail closed.

### 16.1. Do Not Fall Back to Another Tenant

~~~text
Try tenant-a manager
  token invalid
    -> try tenant-b
      token active
        -> authenticated
~~~

Once `tenant-a` has been chosen by route or trusted issuer, verification failure must terminate the request. Fallback can allow a `tenant-b` credential to cross the `tenant-a` boundary.

### 16.2. Timeouts and Cancellation

Resolvers/managers/introspectors return `Mono`. If the downstream AS is slow:

- Configure appropriate timeouts at the HTTP client/introspection layer.
- Never call `block()` inside the resolver or manager.
- Never call `subscribe()` manually to run verification in the background.
- Propagate cancellation when the client aborts the request.
- Bound concurrency/connection pools.
- Do not retry indefinitely.
- Never return a successful Authentication on upstream timeout.

## 17. Reactive Context and Isolation Between Tenants

WebFlux may handle many concurrent requests on the same event-loop threads. Never store the tenant or Authentication in `ThreadLocal` or static mutable fields.

Example:

~~~text
Request A:
  tenant-a
  subject=alice

Request B:
  tenant-b
  subject=bob
~~~

Each request must keep its own `SecurityContext` and tenant identity in the Reactor Context/request pipeline.

### 17.1. Concurrency Testing

An integration test can dispatch multiple concurrent requests:

~~~text
GET /t/tenant-a/whoami + token-a
GET /t/tenant-b/whoami + token-b
GET /t/tenant-a/orders + token-a
GET /t/tenant-b/orders + token-b
~~~

Verify:

- `tenant-a` responses do not contain `tenant-b` subjects/data.
- Manager A is never called with token B.
- Authorities are never shared across requests.
- Tenant caches/registries do not retain the previous request's principal.
- Canceling one request does not affect other requests.

Never use a mutable test principal or singleton variable to store the current tenant.

## 18. Testing Caching and Lifecycle of Tenant Managers

Managers may be cached per issuer/tenant to avoid repeatedly constructing decoders or introspectors.

Verify:

- Managers are created once per registry policy.
- Two simultaneous initial requests do not spawn unintended duplicate managers.
- Disabling a tenant stops its manager from resolving for new requests.
- In-flight managers have a controlled lifecycle.
- Key/JWKS refresh works when an issuer rotates keys.
- Introspection credentials rotate per the secret lifecycle.
- Caches do not retain managers for deleted tenants.
- There are no cache key collisions between issuers/tenants.

If the manager registry updates dynamically, test concurrent updates alongside active requests. Use immutable snapshots/atomic replacement or concurrent maps with well-understood semantics.

## 19. Distinguishing Resolver Tests from mockJwt()/mockOpaqueToken()

| Tool | Best suited for | Tests resolver via Bearer filter? |
|---|---|---|
| mockJwt() | JWT principal/claims and authorization | No |
| mockOpaqueToken() | Opaque principal/attributes and authorization | No |
| mockAuthentication(...) | A custom Authentication | No |
| Direct resolver unit test | Manager selection logic by ServerWebExchange | Tests resolver, not filter chain |
| WebTestClient + Authorization Bearer + test managers | Manager selection through Resource Server filter | Yes |
| WebTestClient + signed JWT + ReactiveJwtDecoder/JWKS | JWT verification and issuer routing | Yes |
| WebTestClient + introspector stub | Opaque manager/introspection selection | Yes |

### 19.1. Why Do Mock Mutators Not Test the Resolver?

`mockJwt()` and `mockOpaqueToken()` inject a test Authentication into the exchange for controllers/authorization to use. They are useful when token cryptography is not the goal of the test.

However, once a mock Authentication is present, the test skips Bearer token extraction and `ReactiveAuthenticationManagerResolver`. Therefore, if the goal is to prove the `tenant-a` route calls manager A, send a normal `Authorization: Bearer` header through the filter chain.

### 19.2. Combining Test Types

A thorough test suite typically includes:

- Unit tests for the tenant registry and resolver.
- `WebTestClient` filter-chain tests with fake managers.
- Authorization tests with `mockJwt()`/`mockOpaqueToken()`.
- JWT integration tests with test keys/JWKS.
- Opaque integration tests with a `ReactiveOpaqueTokenIntrospector` stub or HTTP test server.
- Multi-node/consistency tests if manager/revocation state is distributed.

You do not need a test that spins up a full Authorization Server for every scenario; choose the test level matching what you need to prove.

## 20. Example WebTestClient Tenant Matrix Tests

Assume test managers return the selected tenant as the principal name and grant `SCOPE_orders.read`.

Positive case:

~~~java
@Test
void tenantARequestUsesTenantAManager() {
    webTestClient
        .get()
        .uri("/t/tenant-a/whoami")
        .headers(headers -> headers.setBearerAuth("token-tenant-a"))
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("tenant-a");
}
~~~

Tenant B:

~~~java
@Test
void tenantBRequestUsesTenantBManager() {
    webTestClient
        .get()
        .uri("/t/tenant-b/whoami")
        .headers(headers -> headers.setBearerAuth("token-tenant-b"))
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("tenant-b");
}
~~~

Cross-tenant:

~~~java
@Test
void tenantBTokenIsRejectedOnTenantARoute() {
    webTestClient
        .get()
        .uri("/t/tenant-a/whoami")
        .headers(headers -> headers.setBearerAuth("token-tenant-b"))
        .exchange()
        .expectStatus().isUnauthorized();
}
~~~

Unknown route:

~~~java
@Test
void unknownTenantDoesNotFallBackToDefaultManager() {
    webTestClient
        .get()
        .uri("/t/tenant-unknown/whoami")
        .headers(headers -> headers.setBearerAuth("some-token"))
        .exchange()
        .expectStatus().isUnauthorized();
}
~~~

Exact status codes depend on failure handlers/entry points and route contracts. If unknown tenants are handled at the router before security, the API may choose 404; what matters is never authenticating the request with another tenant's manager.

## 21. Anti-Patterns to Avoid

**Trusting client-supplied tenant headers.** Can select an unauthorized manager or tenant dataset.

**Reading an unverified issuer and building a decoder for any URL.** Opens the trust boundary and creates SSRF risk.

**Selecting a manager by token string shape.** Dot count/length does not prove whether a token is JWT or opaque.

**Falling back to another tenant's manager when authentication fails.** Can cross tenant boundaries.

**Checking only the route without checking the tenant claim.** Another tenant's token could enter the chosen route.

**Checking only the tenant claim without checking audience.** A token meant for another resource could be accepted.

**Using mockJwt() to claim the resolver ran.** The test mutator injects Authentication instead of going through Bearer manager resolution.

**Using mockOpaqueToken() to claim introspection works.** It never invokes `ReactiveOpaqueTokenIntrospector`.

**Using ThreadLocal to store the tenant in WebFlux.** Context can mix across requests.

**Using a broad default manager when tenant resolution fails.** Unknown tenants must never become authenticated.

**Using a single manager/service principal for all tenants without binding audience/tenant.** Can cause cross-tenant privilege confusion.

**Storing the principal in a mutable singleton field.** Concurrent requests can leak identities.

**Blocking the event loop during discovery/introspection.** Reduces throughput and can cause thread starvation.

**Failing open on introspection timeout or registry failure.** Lacks trustworthy verification evidence.

**Testing only success cases.** Must include cross-tenant, unknown issuer, wrong audience, inactive token, and manager failure cases.

## 22. Implementation and Testing Workflow

**Step 1 — Build the tenant registry.** Record tenant ID, trusted issuer, audience, token strategy, JWKS/introspection endpoint, and active status.

**Step 2 — Choose the tenant source.** JWT issuer claim, route/host, or metadata from a trusted gateway. Document which source is routing-only and which is used for authorization.

**Step 3 — Build dedicated ReactiveAuthenticationManagers.** `JwtReactiveAuthenticationManager` or `OpaqueTokenReactiveAuthenticationManager` with tenant-specific decoders/introspectors.

**Step 4 — Write the resolver.** Return `Mono<ReactiveAuthenticationManager>`; unknown tenants/issuers must be rejected.

**Step 5 — Attach to SecurityWebFilterChain.** Use `oauth2ResourceServer().authenticationManagerResolver(...)`.

**Step 6 — Propagate verified tenant.** JWT claims or introspection attributes are preserved in the principal/Authentication; match against route tenant if present.

**Step 7 — Enforce authorization.** Scope, role, audience, tenant, subject, and resource ownership.

**Step 8 — Unit test the resolver in isolation.** `MockServerWebExchange` for path/host/registry mapping.

**Step 9 — Test through the filter chain.** Real `Authorization: Bearer` headers with manager test doubles.

**Step 10 — Integration test real JWT/opaque flows.** Signed JWT/JWKS or `ReactiveOpaqueTokenIntrospector` stub/HTTP test server.

**Step 11 — Test cross-tenant and failure modes.** Tenant B token on route A, unknown issuer, wrong audience, inactive token, timeout, disabled tenant.

**Step 12 — Test concurrency and lifecycle.** Multiple concurrent tenants, registry updates, manager caching, event-loop/context isolation.

## 23. Self-Check Questions

**1. What context type does ReactiveAuthenticationManagerResolver accept in a WebFlux Resource Server?**

Typically `ServerWebExchange`.

**2. What does resolve() return?**

`Mono<ReactiveAuthenticationManager>`.

**3. What does ReactiveAuthenticationManager do?**

Accepts an Authentication request and returns `Mono<Authentication>` after verification.

**4. How does JwtIssuerReactiveAuthenticationManagerResolver choose a manager?**

By the `iss` claim in the Bearer JWT, provided the issuer is in the trusted set.

**5. Can you create a decoder for an arbitrary issuer from an unverified token?**

No. Only use a trusted issuer registry/allowlist.

**6. When should you use a path/host-based resolver?**

When routes or hosts are configured/managed to identify the tenant's strategy, while tokens are still checked by the manager for issuer/audience/tenant.

**7. Does mockJwt() test the manager resolver?**

No. It supplies a test Authentication directly to test authorization.

**8. How do you test the resolver through the filter chain?**

Send a normal `Authorization: Bearer` header via `WebTestClient` and use `ReactiveAuthenticationManager` test doubles.

**9. How does multi-tenant opaque token handling choose a manager?**

Typically via a trusted route/host/tenant registry to select the corresponding `ReactiveOpaqueTokenIntrospector`.

**10. Why compare the tenant claim with the route tenant?**

So tokens belonging to another tenant cannot be used on the current tenant's route.

**11. Should the tenant be stored in ThreadLocal in WebFlux?**

No. Use the principal/Authentication and Reactor Context.

**12. If the tenant-a manager rejects a token, should you try the tenant-b manager?**

No. Authentication failure must terminate according to the selected trust policy.

## Conclusion

In a multi-tenant Spring Security WebFlux Resource Server, **ReactiveAuthenticationManagerResolver<ServerWebExchange>** selects the manager per tenant/request context; **ReactiveAuthenticationManager** verifies the token under the matching trust policy. For multiple JWT issuers, **JwtIssuerReactiveAuthenticationManagerResolver** selects managers by `iss` within a trusted issuer set. For opaque-token tenants or path/host routing, you can build a custom resolver backed by a managed registry.

Testing must clearly separate **manager selection**, **token validation**, and **tenant authorization**. `mockJwt()`/`mockOpaqueToken()` work well for checking principals, scopes, and post-authentication policies; proving the resolver is called requires sending `Authorization: Bearer` through `WebTestClient` with manager test doubles or decoder/introspector integration.

Finally, the tenant must be propagated from verified claims/principals, matched against the route-selected tenant, and enforced in repository/domain authorization. **Unknown tenants, unknown issuers, wrong-audience tokens, or manager failures must fail closed; never fall back to another trust domain.**

### References

- [Spring Security — Reactive OAuth 2.0 Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/multitenancy.html)
- [Spring Security API — ReactiveAuthenticationManagerResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ReactiveAuthenticationManagerResolver.html)
- [Spring Security API — JwtIssuerReactiveAuthenticationManagerResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerReactiveAuthenticationManagerResolver.html)
- [Spring Security API — ServerWebExchangeDelegatingReactiveAuthenticationManagerResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/ServerWebExchangeDelegatingReactiveAuthenticationManagerResolver.html)
- [Spring Security — Reactive OAuth 2.0 Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html)
- [Spring Security — Reactive Authentication Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security API — JwtReactiveAuthenticationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtReactiveAuthenticationManager.html)
- [Spring Security API — OpaqueTokenReactiveAuthenticationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/OpaqueTokenReactiveAuthenticationManager.html)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)

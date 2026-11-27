# Servlet, WebFlux, and Corresponding Components in Spring Security

In an **OAuth 2.0 Resource Server** application, Spring Security receives the access token issued by the Authorization Server, validates it, and decides whether the request may access the resource. Spring Security has two web application security stacks: **Servlet** (commonly used with Spring MVC) and **Reactive** (commonly used with Spring WebFlux). Both achieve the same goal, yet differ in request types, filter chains, configuration APIs, and how the security context is stored.

This lesson compares the components involved in JWT and opaque tokens, processing flows, Java/Spring Boot configurations, and key considerations when choosing an architecture. All URIs and tokens in the examples are illustrative data.

## 1. Resource Server in OAuth 2.0 and OIDC

An OAuth 2.0 system typically consists of:

- **Authorization Server / OpenID Provider (OP)**: authenticates users or clients and issues tokens.
- **OAuth 2.0 Client**: obtains an access token via an allowed flow and sends it when calling APIs.
- **Resource Server**: serves APIs and validates access tokens for protected resources.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant AS as Authorization Server / OIDC Provider
    participant RS as Resource Server
    C->>AS: Request access token
    AS-->>C: Access token
    C->>RS: GET /api/orders + Authorization: Bearer ...
    RS->>RS: Validate token and check permissions
    RS-->>C: Data or HTTP 401/403
~~~

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
~~~

**OIDC is an identity layer built on OAuth 2.0.** An OpenID Provider can supply metadata and a JWK Set for the Resource Server to validate JWTs. However, the API must receive a **valid access token intended for the API**. An **ID token** serves to identify the user to the OIDC client, not as a substitute for an access token to access APIs. `oauth2ResourceServer()` and `oauth2Login()` configurations serve different roles.

## 2. Two HTTP processing models

| Criterion | Servlet / Spring MVC | Reactive / Spring WebFlux |
|---|---|---|
| HTTP infrastructure | Jakarta Servlet, typically Servlet-based Tomcat/Jetty/Undertow | Spring WebFlux + Reactor, typically using Reactor Netty |
| Request/response | `HttpServletRequest`, `HttpServletResponse` | `ServerWebExchange`, `ServerHttpRequest`, `ServerHttpResponse` |
| Common programming style | Sequential call flow, blocking allowed | `Mono<T>` / `Flux<T>` publishers, non-blocking supported |
| Security configuration builder | `HttpSecurity` | `ServerHttpSecurity` |
| Security chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| HTTP interception layer | Servlet `Filter` | Spring WebFlux `WebFilter` |
| Accessing security context | `SecurityContextHolder`, `ThreadLocal`-based by default | `ReactiveSecurityContextHolder`, Reactor `Context` |
| JWT verification | `JwtDecoder` | `ReactiveJwtDecoder` |
| Opaque token introspection | `OpaqueTokenIntrospector` | `ReactiveOpaqueTokenIntrospector` |

**Blocking vs. non-blocking is a processing and resource-usage characteristic; it does not determine OAuth 2.0 security strength.** Both can verify JWT signatures, expiration, issuer, scopes, and authorization rules. With WebFlux, non-blocking benefits only materialize if the controller → service → repository/HTTP client chain does not block the event loop with blocking calls.

Do not determine the HTTP stack just by spotting `WebClient` or `Mono` in a random file. A Spring MVC application can still use `WebClient`. If both `spring-boot-starter-web` and `spring-boot-starter-webflux` are declared, Spring Boot generally chooses a Servlet/MVC application unless configuration changes the application type.

## 3. Spring Security component map

| Responsibility | Servlet | WebFlux / Reactive |
|---|---|---|
| Declaring HTTP rules | `HttpSecurity` | `ServerHttpSecurity` |
| Configured chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Dispatching chains | `FilterChainProxy`, wired to Servlet via `DelegatingFilterProxy` | `WebFilterChainProxy` |
| Intercepting and authenticating Bearer tokens | `BearerTokenAuthenticationFilter` | `AuthenticationWebFilter` configured for Resource Server |
| Extracting Bearer token | `BearerTokenResolver` / `BearerTokenAuthenticationConverter` depending on version and customization | `ServerBearerTokenAuthenticationConverter` (`ServerAuthenticationConverter`) |
| Token representing unauthenticated credential | `BearerTokenAuthenticationToken` | `BearerTokenAuthenticationToken` |
| Coordinating authentication | `AuthenticationManager` (typically `ProviderManager`) | `ReactiveAuthenticationManager` |
| JWT authentication | `JwtAuthenticationProvider` | `JwtReactiveAuthenticationManager` |
| Verifying and decoding JWTs | `JwtDecoder`, e.g. `NimbusJwtDecoder` | `ReactiveJwtDecoder`, e.g. `NimbusReactiveJwtDecoder` |
| Converting JWT to Authentication | `JwtAuthenticationConverter` | Reactive converter; `ReactiveJwtAuthenticationConverterAdapter` can be used |
| JWT authentication result | `JwtAuthenticationToken` | `JwtAuthenticationToken` |
| Opaque token authentication | `OpaqueTokenAuthenticationProvider` | `OpaqueTokenReactiveAuthenticationManager` |
| Verifying opaque tokens | `OpaqueTokenIntrospector` | `ReactiveOpaqueTokenIntrospector` |
| Common opaque token authentication result | `BearerTokenAuthentication` | `BearerTokenAuthentication` |
| Current user context | `SecurityContextHolder` | `ReactiveSecurityContextHolder` |
| URL-based authorization | `authorizeHttpRequests()` and `requestMatchers()` | `authorizeExchange()` and `pathMatchers()` |
| Method security | `@EnableMethodSecurity` and `@PreAuthorize` | `@EnableReactiveMethodSecurity` and `@PreAuthorize` |
| Unauthenticated handling | `AuthenticationEntryPoint` | `ServerAuthenticationEntryPoint` |
| Access denied handling | `AccessDeniedHandler` | `ServerAccessDeniedHandler` |
| Testing HTTP APIs | `MockMvc` | `WebTestClient` |

Data types such as `Jwt`, `Authentication`, and `GrantedAuthority` can be shared; **the main differences lie in HTTP runtime integration and sync/reactive API signatures**. You cannot turn a `SecurityFilterChain` into the security bean of a WebFlux application merely by changing imports.

## 4. JWT processing flow on Servlet

~~~mermaid
flowchart TD
    A["Request + Bearer JWT"] --> B["DelegatingFilterProxy / FilterChainProxy"]
    B --> C["SecurityFilterChain"]
    C --> D["BearerTokenAuthenticationFilter"]
    D --> E["BearerTokenAuthenticationToken"]
    E --> F["AuthenticationManager / ProviderManager"]
    F --> G["JwtAuthenticationProvider"]
    G --> H["JwtDecoder: signature, exp, nbf, iss"]
    H --> I["JwtAuthenticationConverter"]
    I --> J["JwtAuthenticationToken + authorities"]
    J --> K["SecurityContextHolder"]
    K --> L["Authorization → Controller"]
~~~

1. The servlet container passes the request to Spring Security; `FilterChainProxy` selects the matching `SecurityFilterChain`.
2. `BearerTokenAuthenticationFilter` extracts the token from the `Authorization: Bearer ...` header and creates a `BearerTokenAuthenticationToken`.
3. `AuthenticationManager` delegates to `JwtAuthenticationProvider`; the provider uses `JwtDecoder` to verify the signature and associated validators.
4. `JwtAuthenticationConverter` maps claims/scopes into a `JwtAuthenticationToken` with a principal and authorities.
5. Successful authentication is stored in `SecurityContext`; Spring checks access rules before dispatching to the controller if permitted.

With the default `issuer-uri` configuration, the Resource Server validates issuer `iss`, timestamps `exp` / `nbf`, and the signature using trusted keys. **Audience `aud` requires its own validator when the API must restrict tokens to those issued specifically for it**. A valid signature and matching issuer do not guarantee the access token was issued for the right API.

## 5. JWT processing flow on WebFlux

~~~mermaid
flowchart TD
    A["Request + Bearer JWT"] --> B["WebFilterChainProxy"]
    B --> C["SecurityWebFilterChain"]
    C --> D["AuthenticationWebFilter"]
    D --> E["ServerBearerTokenAuthenticationConverter"]
    E --> F["BearerTokenAuthenticationToken"]
    F --> G["ReactiveAuthenticationManager"]
    G --> H["JwtReactiveAuthenticationManager"]
    H --> I["ReactiveJwtDecoder: Mono<Jwt>"]
    I --> J["JwtAuthenticationToken + authorities"]
    J --> K["Reactive SecurityContext (Reactor Context)"]
    K --> L["Authorization → WebFlux handler"]
~~~

The functional flow remains **extract token → validate → build principal/authorities → authorize**, except contracts along the pipeline accept/return publishers such as `Mono<Authentication>` and `Mono<Jwt>`. The security context is stored in Reactor `Context`, following the subscription rather than assuming thread affinity like traditional Servlet code.

In a reactive service, use `ReactiveSecurityContextHolder.getContext()`, or let the framework inject the principal into the appropriate handler. Avoid calling `SecurityContextHolder.getContext()` and assuming it accurately represents the request across thread hops; also avoid forcing reactive results with `block()` inside the request pipeline.

## 6. JWT configuration for Servlet / Spring MVC

Typical dependencies:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

In `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/demo
~~~

The `issuer-uri` value must match the JWT's `iss` claim; the path above is only an example.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class ServletResourceServerSecurity {
    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()));

        return http.build();
    }
}
~~~

Example controller:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ServletOrderController {
    @GetMapping("/api/orders/me")
    String myOrders(@AuthenticationPrincipal Jwt jwt) {
        return "Orders for subject: " + jwt.getSubject();
    }
}
~~~

This snippet shows how to retrieve `sub` after authentication. For per-user resources, the service must still verify order ownership; merely holding the `orders.read` scope does not automatically grant permission to read other users' orders.

## 7. Corresponding configuration for WebFlux

Dependencies:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

The `spring.security.oauth2.resourceserver.jwt.issuer-uri` property keeps the exact same structure as on Servlet. Spring Boot auto-configures `ReactiveJwtDecoder` on WebFlux, whereas on Servlet it configures `JwtDecoder`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class ReactiveResourceServerSecurity {
    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class ReactiveOrderController {
    @GetMapping("/api/orders/me")
    Mono<String> myOrders(@AuthenticationPrincipal Jwt jwt) {
        return Mono.just("Orders for subject: " + jwt.getSubject());
    }
}
~~~

Both configurations protect endpoints with the same scope, yet use different HTTP security components. To benefit from WebFlux, downstream business logic and I/O should support reactive execution; a controller returning `Mono` that internally invokes blocking JDBC/HTTP calls does not automatically make the processing pipeline non-blocking.

In a reactive service, authentication can be read from the Reactor Context:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Mono<String> currentPrincipalName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication())
        .map(Authentication::getName);
}
~~~

The equivalent in Servlet code where the security context has already been established:

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
String principalName = authentication.getName();
~~~

In the Servlet snippet, import `org.springframework.security.core.Authentication` and `org.springframework.security.core.context.SecurityContextHolder`. In WebFlux, the method returns `Mono<String>` to compose into a pipeline; it does not execute until subscribed.

## 8. If the access token is an opaque token, which components change?

**JWTs** usually carry self-contained claims and a signature, so the Resource Server can verify signatures locally after receiving a trusted JWK/public key. An **opaque token** is a string that the Resource Server does not need to decode itself. The standard way to validate it is to call the Authorization Server's **introspection endpoint**, check `active`, and use the returned principal/scope details.

| Stage | Servlet opaque token | WebFlux opaque token |
|---|---|---|
| Configuration | `oauth2ResourceServer(o -> o.opaqueToken(...))` on `HttpSecurity` | Same `opaqueToken(...)` DSL on `ServerHttpSecurity` |
| Authentication mechanism | `OpaqueTokenAuthenticationProvider` | `OpaqueTokenReactiveAuthenticationManager` |
| Introspection call | `OpaqueTokenIntrospector` | `ReactiveOpaqueTokenIntrospector` |
| Principal type | `OAuth2AuthenticatedPrincipal` | `OAuth2AuthenticatedPrincipal` |
| Typical Authentication | `BearerTokenAuthentication` | `BearerTokenAuthentication` |

The `application.yml` example has the exact same structure on both stacks; Spring Boot configures the introspector matching the application type:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.test/oauth2/introspect
          client-id: resource-server-api
          client-secret: ${RESOURCE_SERVER_INTROSPECTION_SECRET}
~~~

`${RESOURCE_SERVER_INTROSPECTION_SECRET}` illustrates an environment variable/secret; never store real introspection secrets in the repository.

If keeping the rules from the earlier examples, simply replace the JWT activation line with:

~~~java
// In HttpSecurity configuration for Servlet:
.oauth2ResourceServer(oauth2 -> oauth2.opaqueToken(withDefaults()))

// In ServerHttpSecurity configuration for WebFlux:
.oauth2ResourceServer(oauth2 -> oauth2.opaqueToken(withDefaults()))
~~~

Do not place these two standalone DSL lines into an independent Java class; they are **DSL replacements** for `.jwt(withDefaults())` in the two preceding examples.

With introspection, network cost and Authorization Server availability can affect every request. If near-real-time token revocation checks are required, introspection is an option; long-lived caching can weaken revocation effectiveness. WebFlux requires a reactive implementation to avoid blocking the event loop during introspection calls.

## 9. Authentication, authorization, and scope

Two stages must be distinguished:

1. **Authentication**: is the token valid, who is the principal, and was the token issued and presented according to rules?
2. **Authorization**: does the valid principal hold the necessary authorities/scopes and have permission to access the *specific resource*?

Illustrative JWT containing claims (timestamps and signature omitted for brevity):

~~~json
{
  "sub": "user-123",
  "iss": "https://idp.example.test/realms/demo",
  "aud": ["orders-api"],
  "scope": "orders.read profile"
}
~~~

Under Resource Server's common default mapping, `scope` or `scp` values are converted into `GrantedAuthority` instances prefixed with `SCOPE_`:

| Claim / condition | Authority / requirement |
|---|---|
| `scope: "orders.read profile"` | `SCOPE_orders.read` and `SCOPE_profile` |
| Rule `hasAuthority("SCOPE_orders.read")` | Accepts principals carrying the `orders.read` scope |
| `hasRole("ADMIN")` | Typically checks for `ROLE_ADMIN`, not equivalent to scope `admin` |
| Custom claims `roles`, `realm_access.roles` | Requires a custom converter or mapping policy configured by the application |

In Servlet, combining `JwtAuthenticationConverter` with `JwtGrantedAuthoritiesConverter` is a common customization point when the issuer uses a different scope claim or custom permission format. In WebFlux, the converter passed into the DSL must return a reactive type; synchronous pure claim-mapping logic can be wrapped with `ReactiveJwtAuthenticationConverterAdapter`. If authorization requires querying a database or remote service over the network, design a dedicated reactive component and avoid blocking calls on the event loop.

Both HTTP endpoints and service methods can be protected:

~~~java
// Example on a Servlet service; requires @EnableMethodSecurity in configuration.
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public OrderView findOrder(String orderId) {
    return loadOrder(orderId);
}
~~~

WebFlux uses `@EnableReactiveMethodSecurity` and methods with matching reactive return types. Checking scope only establishes the permitted category of action; the service must still verify ownership, tenant, data status, or other business conditions when required.

### Why validate `aud`?

One Authorization Server can issue tokens for multiple APIs. A token from the same issuer with a valid signature whose `aud` claim targets a different API must not be accepted by the current API. Configure an `OAuth2TokenValidator<Jwt>` or the validation mechanism appropriate for your Spring Security version to enforce the expected audience alongside the default timestamp and issuer validators. Never wait until the controller to check `aud` after the token has already cleared the security chain.

## 10. When to return 401 vs. 403?

| Scenario | Typical HTTP status | Meaning |
|---|---|---|
| API requires authentication, but no Bearer token is sent | `401 Unauthorized` | No valid authentication credentials provided |
| Token is invalid, expired, bad signature, wrong issuer, or introspection reports inactive | `401 Unauthorized` | Authentication failed |
| Valid token, but missing `SCOPE_orders.read` | `403 Forbidden` | Authenticated, but insufficient permissions |
| Valid token, sufficient permissions, and data access allowed | Decided by controller (typically 2xx) | HTTP security step allowed the request through |

The `WWW-Authenticate: Bearer ...` header may be returned per Bearer token standards, carrying appropriate error details. Servlet uses `AuthenticationEntryPoint` and `AccessDeniedHandler`; Resource Server typically provides `BearerTokenAuthenticationEntryPoint` and `BearerTokenAccessDeniedHandler`. WebFlux has the corresponding extension points `ServerAuthenticationEntryPoint` and `ServerAccessDeniedHandler`.

Authentication errors are typically resolved **inside the security chain before the controller**. Do not place JWT signature parsing inside individual controllers or turn all such errors into HTTP 500. Avoid logging full Bearer tokens, since anyone holding an unexpired token can use it as a credential.

## 11. How to choose the right class family during implementation

| Architecture question | When using Servlet | When using WebFlux |
|---|---|---|
| Which HTTP security bean? | `SecurityFilterChain(HttpSecurity)` | `SecurityWebFilterChain(ServerHttpSecurity)` |
| Custom JWT decoder? | `JwtDecoder` bean | `ReactiveJwtDecoder` bean |
| Custom introspection? | `OpaqueTokenIntrospector` bean | `ReactiveOpaqueTokenIntrospector` bean |
| Reading principal in pipeline? | Via injection or `SecurityContextHolder` | Via injection or `ReactiveSecurityContextHolder` |
| Path rules? | `requestMatchers(...)` | `pathMatchers(...)` |
| Service-level rules? | `@EnableMethodSecurity` | `@EnableReactiveMethodSecurity` |
| Testing HTTP APIs? | `MockMvc` + `spring-security-test` | `WebTestClient` + `spring-security-test` |

Some practical scenarios:

- CRUD application using Spring MVC and blocking Spring Data JPA/JDBC: **Servlet is the natural choice**; building a Resource Server does not require switching to WebFlux.
- Streaming application with WebFlux, reactive repositories, and reactive outbound HTTP: choose reactive security to preserve the same execution model.
- Only wanting to call an external service with `WebClient`: not enough reason to rewrite a servlet security chain.
- Multiple issuers or tenants: use a request-based authentication manager selector, such as `AuthenticationManagerResolver<HttpServletRequest>` (Servlet) or `ReactiveAuthenticationManagerResolver<ServerWebExchange>` (WebFlux), accepting only explicitly trusted issuers/tenants.
- API requiring rapid effect of token revocation: weigh introspection, fault tolerance, and caching. Self-verified JWTs reduce direct network calls, yet require appropriate TTL/revocation policies.

If migrating from Spring MVC to WebFlux, you can preserve the **semantics** of your rules (issuer, audience, scopes, and business permissions), yet you must convert how the security chain, decoder/introspector, method security, and context are wired. Simply changing class imports or returning `Mono` from controllers does not resolve those differences.

## 12. CSRF and sessions: avoid assumptions from the name Resource Server

OAuth 2.0 Bearer tokens in headers are commonly used for APIs that do not rely on session cookies. For pure Bearer-token APIs, disabling CSRF can be considered **within a scope verified to be safe**, depending on the client model. However, applications with browser endpoints, cookie authentication, or sessions may still need CSRF protection. Never disable CSRF by default just because `oauth2ResourceServer()` is configured.

Checking JWTs on every request does not automatically mean every session or context-persistence mechanism is disabled. If the goal is a stateless API, inspect all active authentication mechanisms, request caching, session management, and any other enabled login mechanisms, then configure them consistently for the stack.

## 13. Common misconceptions

### "If the issuer is valid, the access token has been fully validated"

Not enough. Issuer confirms who minted it; audience confirms who it was issued for; scopes/authorities define permissions. You may also need tenant, token type, client, or custom validators matching your system's token profile.

### "WebFlux also uses `BearerTokenAuthenticationFilter` like Servlet"

No. The Servlet filter is replaced by `AuthenticationWebFilter` in the reactive pipeline. Even though types like `Authentication`/`Jwt` can be shared, HTTP integration consists of two separate subsystems.

### "JWTs always need to call introspection"

No. A Resource Server can validate JWTs locally using signatures and trusted JWKs; opaque tokens typically rely on introspection. If special token revocation requirements exist, the system may opt for an additional mechanism.

### "An ID token is a Resource Server token"

No. In OIDC, an ID token serves to identify the user to the client; APIs validate access tokens tailored to that API resource.

### "Having `@AuthenticationPrincipal` means no business permission check is needed"

No. The principal parameter indicates the user or client has been authenticated. It does not guarantee they own the order passed in `/api/orders/{id}`.

### "Using `SecurityContextHolder` inside any `Mono` always works"

No. Reactive pipelines can switch threads, so use Reactor Context and `ReactiveSecurityContextHolder` for security data inside pipelines. Plain `ThreadLocal` does not automatically preserve context across every operator.

### "The `roles` claim automatically becomes `ROLE_*`"

Not by default. Resource Server normally converts `scope`/`scp` into `SCOPE_*`; provider-specific role claims require a custom converter.

## 14. Reading a request's outcome: direct comparison

Suppose both example configurations require `SCOPE_orders.read` for `GET /api/orders/**`.

**A. Valid access token with `orders.read` scope**

~~~http
GET /api/orders/me HTTP/1.1
Authorization: Bearer <valid-access-token-with-orders.read>
~~~

- Servlet: `BearerTokenAuthenticationFilter` → `JwtAuthenticationProvider` → `JwtAuthenticationToken` → `SecurityContextHolder` → MVC controller.
- WebFlux: `AuthenticationWebFilter` → `JwtReactiveAuthenticationManager` → `JwtAuthenticationToken` → Reactor SecurityContext → WebFlux handler.
- Outcome: passes HTTP rules, then controller/service continues enforcing business permissions.

**B. Valid access token, only carrying `profile` scope**: authentication succeeds, yet the required authority is missing, so the response is typically `403`.

**C. Expired access token**: the decoder rejects the credential; the request typically receives `401` and never enters the controller.

**D. JWT with valid signature and matching issuer, but `aud` belongs to another API**: if audience validation is not configured, the default validator may not reject it for audience mismatch. Add an audience validator for the resource server.

## 15. Testing and observability tips

Test scenarios should reflect the security contract: missing token, invalid/expired token, valid token lacking permissions, valid token with sufficient permissions, wrong issuer, and wrong audience. On MVC you can use `MockMvc`, and on WebFlux `WebTestClient` with `spring-security-test`. Mocking JWTs works well for testing **authorization rules**, yet does not replace integration tests covering JWK discovery, signature verification, or live introspection endpoints.

When diagnosing issues:

- If a security bean is not taking effect, confirm whether the app actually runs on Servlet or Reactive.
- If every token returns `401`, check issuer, token type, system clock, JWK/introspection URLs, and trusted algorithm settings.
- If only `403` occurs, inspect the authorities generated by the converter and the scope names in rules.
- If WebFlux hits `block()` errors or unexplained slowness, check for blocking I/O inside custom converters, custom introspectors, or services.
- If tokens intended for another API are still accepted, check audience validation prior to authorization.

## 16. Architectural summary

In **Servlet**, the processing line can be pictured as:

~~~text
HttpSecurity
  → SecurityFilterChain
  → BearerTokenAuthenticationFilter
  → AuthenticationManager
  → JwtDecoder / OpaqueTokenIntrospector
  → SecurityContextHolder
  → Authorization → MVC Controller
~~~

In **WebFlux**:

~~~text
ServerHttpSecurity
  → SecurityWebFilterChain
  → AuthenticationWebFilter
  → ReactiveAuthenticationManager
  → ReactiveJwtDecoder / ReactiveOpaqueTokenIntrospector
  → ReactiveSecurityContextHolder
  → Authorization → WebFlux Handler
~~~

Both models protect an OAuth 2.0 Resource Server. Choose the model matching your actual HTTP runtime, validate **access tokens** for the right issuer/audience, map permissions explicitly, and maintain consistent resource access policies across application layers.

## References

- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — Servlet Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Servlet Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — Reactive Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security — Reactive Bearer Tokens](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/bearer-tokens.html)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)

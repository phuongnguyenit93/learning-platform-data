# ReactiveOpaqueTokenIntrospector and the Mono Result Contract

In a **Spring Security OAuth 2.0/OIDC Resource Server running on WebFlux**, an API can validate a Bearer access token by calling the Authorization Server's (AS) **token introspection endpoint**. This approach is especially useful when the AS issues **opaque access tokens**: token strings do not need a structure that the Resource Server can decode itself; instead, the AS confirms the token's status and metadata.

On Servlet, the familiar extension point is `OpaqueTokenIntrospector`, which directly returns an `OAuth2AuthenticatedPrincipal`. In **WebFlux**, the corresponding interface is **`ReactiveOpaqueTokenIntrospector`**, which returns a **`Mono<OAuth2AuthenticatedPrincipal>`**. The difference is not just adding `Mono` to the signature: **success values, empty results, asynchronous errors, subscription timing, cancellation, retries, and avoiding blocking** all directly affect the security of the authentication mechanism.

The contract to keep in mind from the start:

> **When a token is verified as valid, emit exactly one trusted `OAuth2AuthenticatedPrincipal`; when it cannot be verified, never emit a principal that carries privileges.** An inactive token must be rejected, must not default to a privileged anonymous principal, and must not use `onErrorResume` to fall back to a "backup" user.

This guide focuses on the `ReactiveOpaqueTokenIntrospector` interface itself and its **`Mono` contract** in the context of **Reactive Introspection**: how Spring Security wires it into WebFlux, what Reactor signals mean, how to write a decorator that validates audience/issuer and preserves scopes, testing with `StepVerifier`/`WebTestClient`, as well as boundaries around network failures, performance, and token revocation.

## 1. Introspection in a Reactive Resource Server

A request:

```http
GET /api/orders/ORD-123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer opaque-access-token
```

is conceptually processed as follows:

```mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant API as WebFlux Resource Server
    participant I as ReactiveOpaqueTokenIntrospector
    participant AS as Authorization Server
    C->>API: GET /api/orders/ORD-123 + Bearer token
    API->>I: introspect(token) => Mono<Principal>
    I->>AS: HTTPS POST token introspection
    AS-->>I: active=true, scope, sub, aud, ...
    I-->>API: onNext(OAuth2AuthenticatedPrincipal)
    I-->>API: onComplete()
    API->>API: Authentication / authorities
    API->>API: HTTP authorization + owner/tenant
    API-->>C: 200 if all conditions are valid
```

For an inactive token or information that violates the contract, the desired outcome is an **authentication error** in the reactive pipeline, not a valid principal. After Authentication has been created, Spring Security still has to check **`GrantedAuthority`**, and the service still has to enforce permissions on each individual order.

### 1.1. Responsibilities of Each Component

| Component | Role | What must not be assumed |
|---|---|---|
| `SecurityWebFilterChain` | Configures WebFlux security filters and HTTP rules | Does not validate tokens on its own if resource server is not enabled |
| `ServerHttpSecurity.oauth2ResourceServer(...opaqueToken...)` | Enables Bearer authentication via introspection | Does not automatically grant all scopes to an active token |
| `OpaqueTokenReactiveAuthenticationManager` | Coordinates the introspector and authentication converter | Does not replace ownership/tenant checks |
| **`ReactiveOpaqueTokenIntrospector`** | Verifies the token, returns `Mono<OAuth2AuthenticatedPrincipal>` or an error | Is not an HTTP controller; should not decide URL authorization on its own |
| `ReactiveOpaqueTokenAuthenticationConverter` | Converts a valid introspection result into `Mono<Authentication>` | Should not turn an introspection failure into a successful auth |
| `OAuth2AuthenticatedPrincipal` | Holds attributes, authorities, and principal name | Is not by default a database user entity |
| `BearerTokenAuthentication` | Common Authentication type for opaque bearer tokens | Does not automatically grant access to every record |
| `ReactiveSecurityContextHolder` | Accesses SecurityContext within the Reactor Context | Is not a long-lived login session storage mechanism |

### 1.2. Introspection Is Not JWT Decoding

A WebFlux Resource Server can authenticate using:

- **JWT path:** `ReactiveJwtDecoder` verifies signatures/issuer/audience/timestamps according to configuration.
- **Opaque/introspection path:** `ReactiveOpaqueTokenIntrospector` queries a trusted source for token status and receives metadata.

Do not wire `ReactiveJwtDecoder` into an application and expect `ReactiveOpaqueTokenIntrospector` to run automatically, or assume a JWT-like Bearer string must always be decoded locally. The access token type and validation path must be agreed upon in the contract with the AS.

Opaque introspection can be used even when the access token actually has a JWT format, if the API intentionally wants the AS to decide token status/revocation. In that case, the Resource Server **must still** rely on the trusted introspection result rather than mixing in unverified claims from the raw token.

## 2. Exact Interface Signature

According to the Spring Security Javadoc, `ReactiveOpaqueTokenIntrospector` is a functional interface with the core method:

```java
package org.springframework.security.oauth2.server.resource.introspection;

import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import reactor.core.publisher.Mono;

@FunctionalInterface
public interface ReactiveOpaqueTokenIntrospector {
    Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
}
```

This is an **illustrative signature** of the interface; to use it, import the existing interface from Spring Security—do not redefine it in your project.

Explanation of each element:

- `String token`: the bearer credential string being verified. This is a **secret** and must be kept out of logs, exceptions, URLs, or metrics labels.
- `introspect`: represents the operation of verifying the token and retrieving attributes from the AS or a trusted source with an equivalent contract.
- `Mono<OAuth2AuthenticatedPrincipal>`: a publisher of at most **one** valid principal, or emitting an error/completing empty depending on the implementation.
- `OAuth2AuthenticatedPrincipal`: the set of attributes and authorities constructed by the introspector from **verified metadata**.

This interface has existed since **Spring Security 5.2**. In modern Spring Security versions, the standard implementation used is `SpringReactiveOpaqueTokenIntrospector`; older applications may use `NimbusReactiveOpaqueTokenIntrospector`. Constructor names, builders, and configuration APIs can vary across versions.

### 2.1. Do Not Confuse with the Servlet Interface

Servlet:

```java
OpaqueTokenIntrospector introspector;
OAuth2AuthenticatedPrincipal principal =
    introspector.introspect(token);
```

WebFlux:

```java
ReactiveOpaqueTokenIntrospector introspector;
Mono<OAuth2AuthenticatedPrincipal> publisher =
    introspector.introspect(token);
```

The two interfaces are not directly interchangeable. Calling a **blocking** introspector from a WebFlux filter can block the Netty event loop or reactive processing thread. If integrating a blocking client is unavoidable, it must be placed at a dedicated boundary with a scheduler meant for blocking I/O and evaluated for load, timeouts, and cancellation—never make that the default design.

### 2.2. Do Not Confuse with the Authentication Converter

On the reactive path there is another extension point:

```java
// Illustrative signature of the API available since Spring Security 5.8:
Mono<Authentication> convert(
    String introspectedToken,
    OAuth2AuthenticatedPrincipal authenticatedPrincipal);
```

That is `ReactiveOpaqueTokenAuthenticationConverter`. It runs **after introspection succeeds** to build the Authentication. It does not verify the token's `active` status in place of the introspector. If you need to customize **how the principal's metadata, audience, issuer, or authorities are interpreted**, you can wrap the introspector. If you need to change the **Authentication type** or perform complex conversion, consider the converter on a supported version.

## 3. The `Mono` Result Contract: Three Signal Types

In Reactor, a `Mono<T>` can emit at most one `onNext(T)` followed by `onComplete()`, just `onComplete()` with no element, or `onError(Throwable)`. Cases that must be handled explicitly:

| `Mono` signal | Reactor meaning | Meaning in token introspection |
|---|---|---|
| `onNext(principal) → onComplete()` | One success value | **Token has been verified**; principal must contain attributes/authorities per the contract |
| `onError(exception)` | Publisher failed | Invalid token, malformed response, or system error; **must not grant a successful Authentication** |
| `onComplete()` without `onNext` | Empty publisher | **No proof the token is valid**; custom wrappers should turn this into an explicit rejection if the contract requires a verified result |
| No terminal signal | Hanging publisher | Request can tie up resources; requires a timeout and error policy |
| `cancel()` from subscriber | Subscriber no longer needs the result | Does not guarantee the AS has not received the token or that all network side effects are undone |

**Important:** the interface says "return `Mono<OAuth2AuthenticatedPrincipal>`", but **you must not treat `Mono.empty()` as a way to grant access or as a complete introspection response**. If a token is invalid, use an error signal to express failure explicitly; if a delegate unexpectedly returns empty, a security wrapper can fail closed with `switchIfEmpty(Mono.error(...))`.

### 3.1. Success Case

```java
OAuth2AuthenticatedPrincipal principal =
    new DefaultOAuth2AuthenticatedPrincipal(
        "user-842",
        Map.of("sub", "user-842"),
        List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
    );

Mono<OAuth2AuthenticatedPrincipal> success =
    Mono.just(principal);
```

This is a **test fixture**. In production, `principal` is only trustworthy **after** the token has been verified by the AS/introspection source; never take a `Map` sent by an HTTP caller and wrap it in `Mono.just` to create an authentication.

### 3.2. Invalid Token Case

```java
Mono<OAuth2AuthenticatedPrincipal> invalid =
    Mono.error(new BadOpaqueTokenException("Token is inactive"));
```

`BadOpaqueTokenException` resides in package `org.springframework.security.oauth2.server.resource.introspection`. It is appropriate for signaling that the token is not accepted. Never include the raw bearer token in the message:

```java
// Unsafe: the token could be leaked in logs or error responses.
return Mono.error(new BadOpaqueTokenException(
    "Invalid token: " + token));
```

### 3.3. Empty Result Case: Fail Closed

```java
Mono<OAuth2AuthenticatedPrincipal> empty = Mono.empty();
```

A custom introspector should never intentionally return empty to "skip the check and let the request proceed." What empty means in an authentication pipeline can depend on the wired `ReactiveAuthenticationManager`/filter; it is **not** a verified principal.

A decorator can enforce the invariant:

```java
return delegate.introspect(token)
    .switchIfEmpty(Mono.error(
        new BadOpaqueTokenException(
            "Introspection returned no authenticated principal")));
```

Then the caller receives an error instead of an indeterminate result. **Never use** `defaultIfEmpty(adminPrincipal)` or `switchIfEmpty(Mono.just(fallbackPrincipal))` if that principal carries privileges: lack of authentication proof must lead to denial.

### 3.4. Hanging Publisher Case

```java
Mono<OAuth2AuthenticatedPrincipal> never = Mono.never();
```

This is not an "active token" result either. Requests could wait indefinitely without a timeout. A wrapper can bound the duration:

```java
return delegate.introspect(token)
    .timeout(Duration.ofSeconds(2));
```

Upon timeout, the publisher emits an error. **A timeout is not proof of a forged token**, so avoid converting every timeout into `BadOpaqueTokenException` with `invalid_token` semantics if the system needs to distinguish AS outages from rejected tokens. Regardless of the final configured HTTP status, **never grant privileges when verification fails**.

## 4. From RFC 7662 to `Mono<OAuth2AuthenticatedPrincipal>`

Standard **RFC 7662** introspection typically sends the token in a POST form body to the AS; the Resource Server must authenticate to the AS using an agreed method, such as client credentials via Basic authentication:

```http
POST /oauth2/introspect HTTP/1.1
Host: idp.example.com
Authorization: Basic BASE64_RESOURCE_SERVER_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

token=OPAQUE_ACCESS_TOKEN
```

This is a **protocol illustration**, not a real URL or credential. In WebFlux, `SpringReactiveOpaqueTokenIntrospector` typically handles this HTTP call. Controllers do not need to manually construct introspection requests on every endpoint.

### 4.1. Active Token Response

```json
{
  "active": true,
  "scope": "orders.read orders.update",
  "client_id": "shop-web",
  "token_type": "Bearer",
  "sub": "user-842",
  "iss": "https://idp.example.com/realms/shop",
  "aud": ["orders-api"],
  "tenant_id": "tenant-a",
  "exp": 1893459600
}
```

In RFC 7662:

- `active` is a **required** field of the introspection response.
- `scope` (if returned) is a string containing a **space-separated** list of scopes.
- `sub`, `client_id`, `aud`, `iss`, `exp`, `iat`, `nbf` may appear depending on the AS.
- `tenant_id` is a hypothetical extension, **not a required RFC 7662 claim**.

The Resource Server uses metadata from a trusted AS, not `scope` read from a query parameter or client-supplied header.

Once the token is verified by the delegate, the principal can provide:

```java
principal.getName();
principal.getAttribute("sub");
principal.getAttribute("aud");
principal.getAttribute("iss");
principal.getAuthorities();
```

By default, Spring Security's opaque resource server maps scopes to authorities with the `SCOPE_` prefix:

```text
scope in response:
    "orders.read orders.update"

GrantedAuthority:
    SCOPE_orders.read
    SCOPE_orders.update
```

`SCOPE_` is Spring Security's authority representation, not a prefix that the AS is required to include in every scope name.

### 4.2. Inactive Token Response

```json
{
  "active": false
}
```

The AS may return a very minimal response so as not to leak details about invalid tokens. In this case, the standard introspector must **reject token authentication**, never emitting a principal named `anonymous` with `SCOPE_orders.read`.

In the reactive pipeline, we expect a failure signal to be propagated to the authentication manager, such as `onError(BadOpaqueTokenException)` or an appropriate implementation exception. Do not mandate that **every** failure use the same exception class: network errors, HTTP 5xx, invalid JSON, failed AS client authentication, and `active=false` do not share the same root cause.

### 4.3. Missing Scope Is Not the Same as an Inactive Token

```json
{
  "active": true,
  "sub": "user-842",
  "aud": ["orders-api"]
}
```

If the AS accepts the token without granting `orders.read`, an Authentication can still be created **without `SCOPE_orders.read`**. A route requiring `SCOPE_orders.read` will then be denied during **authorization** (typically 403), rather than forcing the token to be treated as inactive.

If the Resource Server contract requires **scope to always be present**, a custom introspector can reject responses missing scope early. Never silently add a read scope to "work around" missing metadata.

### 4.4. `aud`, `iss`, and Scope Are Independent Checks

A token:

```json
{
  "active": true,
  "iss": "https://idp.example.com/realms/shop",
  "aud": ["payments-api"],
  "scope": "orders.read"
}
```

is not automatically suitable for the Orders API. Audience answers **which resource the token is intended for**; scope answers **which functional permissions were granted**. If the Orders API requires `aud=orders-api`, it must verify this from the trusted response or rely on an equivalently strong AS constraint. Do not assume `opaqueToken()` by default enforces every application-specific rule about audience or tenant.

## 5. Configuring a WebFlux Resource Server with Introspection

With Spring Boot 3.x / Spring Security 6.x, dependencies:

```groovy
// build.gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
```

You do not need to add `spring-boot-starter-web` just to validate opaque tokens in WebFlux; adding Spring MVC to the classpath can change Boot's web application type selection depending on configuration.

### 5.1. Configuration via application.yml

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: "${INTROSPECTION_CLIENT_SECRET}"
```

The secret value must come from an appropriate secret manager or environment variable—**never** commit a real client secret. The Resource Server must use HTTPS, validate TLS, and configure timeouts and error policies. Boot can auto-configure `ReactiveOpaqueTokenIntrospector` when the required dependencies and properties are present and the application does not override the bean/DSL.

### 5.2. Configuring SecurityWebFilterChain

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
            // Example API uses only the Bearer header, not browser
            // cookies as credentials for write requests.
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .pathMatchers(HttpMethod.PUT, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.update")
                .pathMatchers(HttpMethod.DELETE, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.delete")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults()))
            .build();
    }
}
```

Key distinctions:

- WebFlux uses `ServerHttpSecurity`/`SecurityWebFilterChain`, not Servlet `HttpSecurity`/`SecurityFilterChain`.
- `authorizeExchange` only evaluates HTTP authorization after authentication; it does not call the AS itself.
- `opaqueToken` activates the reactive introspection branch; Spring Security uses `ReactiveOpaqueTokenIntrospector`.
- The HTTP rule `SCOPE_orders.read` checks the Authentication's authorities. It **does not directly parse the scope string from the request**.
- `anyExchange().denyAll()` denies unlisted paths/methods; CORS preflight, health, actuator, and other routes must be explicitly permitted/designed according to the contract.

Disabling CSRF in this sample is only appropriate for a pure Bearer-header API where browsers do not automatically attach credentials via cookies. If the same application also has browser session/cookie login, CSRF must be designed separately.

### 5.3. Internal Flow in Spring Security

```mermaid
flowchart TD
    A["Authorization: Bearer opaque-token"] --> B["WebFlux Bearer authentication filter"]
    B --> C["OpaqueTokenReactiveAuthenticationManager"]
    C --> D["ReactiveOpaqueTokenIntrospector.introspect(token)"]
    D --> E{"Mono signal"}
    E -->|"onNext(principal)"| F["ReactiveOpaqueTokenAuthenticationConverter"]
    F --> G["BearerTokenAuthentication"]
    G --> H["Reactor SecurityContext"]
    H --> I{"HTTP / method authority?"}
    I -->|"No"| N["Typically 403"]
    I -->|"Yes"| J["Domain owner/tenant policy"]
    E -->|"onError"| K["Authentication failure"]
    E -->|"empty"| L["No principal; fail closed"]
```

This is a conceptual model; exception handlers can customize status/body, and AS unavailability errors can be handled differently from invalid tokens. The invariant is **never granting a successful Authentication when the token has not been verified**.

## 6. Using the Standard `SpringReactiveOpaqueTokenIntrospector` Implementation

In modern Spring Security, you can configure:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.oauth2.server.resource.introspection
    .ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection
    .SpringReactiveOpaqueTokenIntrospector;

@Bean
ReactiveOpaqueTokenIntrospector baseIntrospector(
        @Value("${app.security.introspection-uri}") String uri,
        @Value("${app.security.introspection-client-id}") String clientId,
        @Value("${app.security.introspection-client-secret}") String secret) {

    return SpringReactiveOpaqueTokenIntrospector
        .withIntrospectionUri(uri)
        .clientId(clientId)
        .clientSecret(secret)
        .build();
}
```

Application properties:

```yaml
app:
  security:
    introspection-uri: https://idp.example.com/oauth2/introspect
    introspection-client-id: orders-resource-server
    introspection-client-secret: "${INTROSPECTION_CLIENT_SECRET}"
```

`SpringReactiveOpaqueTokenIntrospector` provides the builder path per modern Javadoc. If a project uses an older version, check the corresponding class/constructors; older lines have `NimbusReactiveOpaqueTokenIntrospector`. Do not pick a class from memory if it does not exist in your current dependency versions in the IDE.

### 6.1. Providing Your Own Bean Changes Auto-Configuration

When an application declares a `ReactiveOpaqueTokenIntrospector` bean or explicitly configures `opaqueToken.introspector(...)`, Spring Boot/the DSL may **back off or replace** the default configuration. Therefore:

- Do not assume Boot still applies every opaque-token property to your custom-created bean.
- Avoid leaving multiple introspector beans where it is unclear which one a chain uses.
- With multiple chains, verify that the chain for `/api/**` is wired to the right introspector.
- Test a real Bearer request through the WebFlux filter, not just the introspector in isolation.

### 6.2. Explicit Override via DSL

```java
@Bean
SecurityWebFilterChain apiChain(
        ServerHttpSecurity http,
        ReactiveOpaqueTokenIntrospector introspector) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/**").authenticated()
            .anyExchange().denyAll())
        .oauth2ResourceServer(oauth2 -> oauth2
            .opaqueToken(opaque -> opaque.introspector(introspector)))
        .build();
}
```

This is an example of explicit introspector wiring, not a complete set of scope rules. For APIs with sensitive operations, replace `authenticated()` with appropriate `hasAuthority(...)`/`access(...)` rules and enforce business permissions in the service layer.

## 7. Laziness and Subscription Timing

`Mono` is a **Publisher**, not a promise that has already executed by the time the Java method returns. Many Reactor and WebClient publishers are **cold**: actual work typically begins only when a subscriber subscribes.

Example:

```java
ReactiveOpaqueTokenIntrospector introspector = token ->
    Mono.defer(() -> {
        System.out.println("Introspection subscribed");
        return remoteIntrospection(token);
    });

Mono<OAuth2AuthenticatedPrincipal> result =
    introspector.introspect("opaque-test-token");

// At this point remoteIntrospection has not necessarily been called yet.
// Work begins when a subscription occurs.
```

`remoteIntrospection` is an illustrative method returning `Mono<OAuth2AuthenticatedPrincipal>`. Never use `System.out.println` to log tokens in production. `Mono.defer` defers constructing a side-effecting publisher until subscription time.

### 7.1. Why `Mono.just(blockingCall())` Does Not Make I/O Reactive

Anti-pattern:

```java
@Override
public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
    OAuth2AuthenticatedPrincipal principal =
        blockingHttpClient.introspect(token);  // BLOCKING at call time
    return Mono.just(principal);
}
```

`Mono.just(...)` takes an **already-computed value**. The HTTP call has already executed before the Mono is returned, potentially blocking the Netty event loop. Similarly:

```java
return Mono.just(blockingHttpClient.introspect(token));
```

is still blocking.

Prefer `SpringReactiveOpaqueTokenIntrospector` with a reactive HTTP client. If you must use a blocking client with no alternative, isolate it:

```java
return Mono.fromCallable(() -> blockingHttpClient.introspect(token))
    .subscribeOn(Schedulers.boundedElastic());
```

`Schedulers.boundedElastic()` only keeps the blocking call **off the event loop**; it **does not turn a blocking library into non-blocking I/O** and does not handle HTTP client timeouts, retries, or cancellation by itself. This is a temporary bridge, not the preferred choice for a high-load Resource Server.

### 7.2. Subscribing to the Same Mono Multiple Times

```java
Mono<OAuth2AuthenticatedPrincipal> result =
    introspector.introspect(token);

result.subscribe();
result.subscribe();
```

With a typical **cold publisher**, each subscription can trigger **a new introspection call**. However, with cached/hot publishers or custom implementations, you cannot assume the number of HTTP calls strictly equals the number of subscriptions.

In a normal HTTP authentication path, the framework manages subscription. **Never call `subscribe()` yourself inside an introspector** just to "check the token early": a detached subscription creates races, fails to propagate errors to the authentication pipeline, and can perform unneeded work.

### 7.3. One Request Should Not Authenticate with Two Different Results

If an application arbitrarily subscribes twice to remote introspection during a single request, the token could be revoked between the two calls or the AS could return different metadata. Duplicate subscriptions can make logic inconsistent; the authentication framework should receive **a single properly composed publisher**.

If a result must be shared within the same chain, design the publisher composition explicitly. Never use an unbounded `cache()` that turns an authentication result into permanent authorization.

## 8. Writing a Decorator That Protects the `Mono` Contract

Suppose the Orders API requires:

- Introspection from the trusted AS must complete successfully.
- `iss` must match the allowed issuer.
- `aud` must contain `orders-api`.
- The delegate already created `SCOPE_...` authorities from `scope`; the decorator must **preserve** them, not strip them.
- If a `permissions` extension is present, only the value `order:approve` is mapped to `PERMISSION_order:approve`.
- Missing/mismatched issuer or audience, or a malformed extension type, must **fail closed**.
- Never convert empty/error into a privileged Authentication.

The following implementation does not send HTTP requests itself. It wraps an already-configured `ReactiveOpaqueTokenIntrospector` that verifies the token:

```java
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;

public final class PolicyCheckingReactiveIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;
    private final String trustedIssuer;
    private final String requiredAudience;

    public PolicyCheckingReactiveIntrospector(
            ReactiveOpaqueTokenIntrospector delegate,
            String trustedIssuer,
            String requiredAudience) {

        this.delegate = Objects.requireNonNull(delegate);
        this.trustedIssuer = Objects.requireNonNull(trustedIssuer);
        this.requiredAudience = Objects.requireNonNull(requiredAudience);
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        // Mono.defer defers the delegate call until subscription time.
        return Mono.defer(() -> delegate.introspect(token))
            // Empty does not mean the token is valid.
            .switchIfEmpty(Mono.error(new BadOpaqueTokenException(
                "No authenticated introspection principal")))
            // Validate the contract and attach approved extra authorities.
            .map(this::validateAndEnrich);
    }

    private OAuth2AuthenticatedPrincipal validateAndEnrich(
            OAuth2AuthenticatedPrincipal principal) {

        if (!trustedIssuer.equals(principal.getAttribute("iss"))) {
            throw new BadOpaqueTokenException(
                "Introspected issuer is not trusted");
        }

        Object rawAudience = principal.getAttribute("aud");
        boolean audienceMatches =
            (rawAudience instanceof String aud
                && requiredAudience.equals(aud))
            || (rawAudience instanceof Collection<?> audiences
                && audiences.contains(requiredAudience));

        if (!audienceMatches) {
            throw new BadOpaqueTokenException(
                "Introspected audience is not accepted");
        }

        Set<GrantedAuthority> authorities =
            new LinkedHashSet<>(principal.getAuthorities());

        Object rawPermissions = principal.getAttribute("permissions");

        if (rawPermissions != null) {
            if (!(rawPermissions instanceof Collection<?> permissions)) {
                throw new BadOpaqueTokenException(
                    "Malformed permissions metadata");
            }

            for (Object rawPermission : permissions) {
                if (!(rawPermission instanceof String permission)) {
                    throw new BadOpaqueTokenException(
                        "Malformed permission entry");
                }
                if ("order:approve".equals(permission)) {
                    authorities.add(new SimpleGrantedAuthority(
                        "PERMISSION_order:approve"));
                }
            }
        }

        Map<String, Object> attributes = principal.getAttributes();

        return new DefaultOAuth2AuthenticatedPrincipal(
            principal.getName(),
            attributes,
            authorities
        );
    }
}
```

### 8.1. Why Use `Mono.defer`?

`Mono.defer(() -> delegate.introspect(token))`:

- Defers calling the delegate until subscription, preventing HTTP execution when the chain is merely assembled.
- Converts synchronous exceptions thrown while invoking `delegate.introspect(token)` into a publisher error signal instead of failing synchronously outside the stream.
- Preserves Reactor composition for cancellation, timeout, and retry.

It **does not guarantee** that the inner delegate is non-blocking. If the delegate performs blocking HTTP when invoked, that blocking work still runs on the subscription thread. Thus a genuinely reactive delegate or properly configured blocking bridge must be used.

### 8.2. Why Use `switchIfEmpty`?

If the delegate violates expectations by returning `Mono.empty()`, the decorator does not create an anonymous principal or grant a default read scope. It emits an error signal so authentication cannot proceed as successful.

In a secure API, **empty is not an allow decision**. If you need to express "this token does not belong to this manager, try another manager," that is the contract of a different routing/authentication layer—design it explicitly rather than borrowing empty to bypass validation inside an opaque branch.

### 8.3. Why Not `onErrorResume(... -> Mono.just(guest))`?

`onErrorResume` is not inherently bad; it is useful for recovering from non-authentication business errors. However, in introspection:

```java
// DO NOT USE: grants privileges when the token is unverified.
return delegate.introspect(token)
    .onErrorResume(error -> Mono.just(
        fallbackPrincipalWithReadScope));
```

is **fail-open**. It can turn `active=false`, timeouts, bad client secrets, or TLS failures into API read permissions. If errors must be handled, only map them to **another safe error**, emit scrubbed metrics/logs, or apply a specifically designed and verified cache policy.

### 8.4. Why Preserve `getAuthorities()`?

`SpringReactiveOpaqueTokenIntrospector` may have mapped `scope` to `SCOPE_orders.read`. When creating a new `DefaultOAuth2AuthenticatedPrincipal`, if you only include new permissions and drop existing authorities, an HTTP rule like `hasAuthority("SCOPE_orders.read")` will fail to match even though the token was granted read scope.

Here `LinkedHashSet` preserves the original authorities and deduplicates overlapping permissions. **Preserving all authorities** is only appropriate when the delegate is trusted and those authorities belong to the API's contract; if resource-specific narrowing is needed, add an intentional filtering/rejection policy step.

### 8.5. Why Must Audience/Issuer Come After the Delegate?

A raw opaque token does not necessarily contain any claims the API can read. Even if the raw token looks like a JWT, never parse unverified `iss` or `aud` claims and treat them as trustworthy. This decorator inspects **attributes returned by a trusted delegate after introspection**.

Multi-issuer applications must select the AS and introspection endpoint from a safe configuration/allowlist; never construct an introspection URL from an unverified token claim or arbitrary header.

### 8.6. Limitations and Assumptions of the Example

This illustrative code assumes:

- The AS always returns `iss` and `aud` per the contract. Otherwise, the policy rejects; align the contract with the AS rather than silently dropping the check.
- `permissions` is an AS-confirmed extension, not self-asserted by the client.
- `aud` may be a String or a Collection of Strings; if the AS uses another format, a verified adapter must normalize it.
- The principal's `getName()` is determined by the delegate; it may represent a service client rather than an end user.
- The API also enforces ownership/tenant checks in the business service.

Do not treat this decorator as proof that an AS validated the token if `delegate` itself is a stub created in production code without validating tokens.

## 9. Bean Configuration and Wiring the Decorator into WebFlux

Example of creating the standard delegate and wrapping it with policy:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.introspection
    .ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection
    .SpringReactiveOpaqueTokenIntrospector;

@Configuration
public class IntrospectionBeans {

    @Bean
    ReactiveOpaqueTokenIntrospector reactiveOpaqueTokenIntrospector(
            @Value("${app.security.introspection-uri}") String endpoint,
            @Value("${app.security.introspection-client-id}") String id,
            @Value("${app.security.introspection-client-secret}") String secret,
            @Value("${app.security.issuer}") String issuer,
            @Value("${app.security.audience}") String audience) {

        ReactiveOpaqueTokenIntrospector remote =
            SpringReactiveOpaqueTokenIntrospector
                .withIntrospectionUri(endpoint)
                .clientId(id)
                .clientSecret(secret)
                .build();

        return new PolicyCheckingReactiveIntrospector(
            remote, issuer, audience);
    }
}
```

```yaml
app:
  security:
    introspection-uri: https://idp.example.com/oauth2/introspect
    introspection-client-id: orders-resource-server
    introspection-client-secret: "${INTROSPECTION_CLIENT_SECRET}"
    issuer: https://idp.example.com/realms/shop
    audience: orders-api
```

This bean provides **a single `ReactiveOpaqueTokenIntrospector`** for the example. If multiple beans of this type or multiple security chains exist, specify explicitly which bean each chain uses.

### 9.1. Explicit Wiring into `SecurityWebFilterChain`

```java
@Bean
SecurityWebFilterChain ordersChain(
        ServerHttpSecurity http,
        ReactiveOpaqueTokenIntrospector introspector) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyExchange().denyAll())
        .oauth2ResourceServer(oauth2 -> oauth2
            .opaqueToken(opaque -> opaque.introspector(introspector)))
        .build();
}
```

The snippet above only illustrates wiring the introspector. A real API must distinguish GET/POST/PUT/DELETE, permit allowed endpoints, and set an appropriate fallback. Never apply a single read rule to DELETE as well if the API supports deletion.

### 9.2. Difference Between `introspectionUri(...)` and `introspector(...)` DSL

- `opaqueToken.introspectionUri(...)` / `introspectionClientCredentials(...)`: configures the remote introspection used by the framework.
- **`opaqueToken.introspector(customBean)`**: replaces/overrides the introspector path with an application-provided implementation.

If you have custom audience or permission policies, merely changing the URI will not run your policy. You must wire the decorator or a version-supported policy approach.

### 9.3. Do Not Call `block()` When Creating Beans

Anti-pattern:

```java
@Bean
OAuth2AuthenticatedPrincipal bootstrapPrincipal(
        ReactiveOpaqueTokenIntrospector introspector) {
    return introspector.introspect("some-token").block();
}
```

This invokes introspection during application startup, unrelated to the current request's bearer token; it can also tie startup to an expired token or IdP availability. The bean should be the **introspector**, not a fixed principal applied to every request.

## 10. Non-Blocking: Quality Requirement of a Reactive Introspector

Returning `Mono` enables Reactor composition, but **does not automatically guarantee** the implementation is truly non-blocking.

### 10.1. Wrong: Synchronous HTTP Call Before Creating the Mono

```java
return Mono.just(restTemplate.postForObject(
    introspectionUrl, request, OAuth2AuthenticatedPrincipal.class));
```

This blocks the thread executing the call, regardless of the `Mono` return type.

### 10.2. Wrong: Calling `block()` Inside `map`

```java
return delegate.introspect(token)
    .map(principal -> blockingAclLookup(principal).block());
```

In Reactor, calling `block()` on an event-loop thread can throw an exception or severely degrade throughput. If ACL enrichment genuinely requires I/O, change `map` to `flatMap` and use a reactive repository/client:

```java
return delegate.introspect(token)
    .flatMap(principal ->
        reactiveAclService.enrich(principal));
```

In this example, `reactiveAclService.enrich` returns `Mono<OAuth2AuthenticatedPrincipal>` and must uphold the security invariant: when privileges are absent or an error occurs, **never fabricate fallback privileges**.

### 10.3. Using the Right Operators

| Operator | Appropriate when | Caution |
|---|---|---|
| `map` | Transforming a principal into a new principal with fast, non-blocking code | Do not use when the function returns a Mono |
| `flatMap` | Policy requires reactive I/O returning a Mono | Handle empty/error explicitly; never fail-open |
| `switchIfEmpty` | Empty must be converted to an explicit error | Do not create a default privileged principal |
| `timeout` | Bounding upstream wait time | A timeout is a system failure, not a default assumption of a forged token |
| `onErrorMap` | Translating exception classes to honor a contract | Do not swallow important root causes or leak tokens |
| `onErrorResume` | Only for safe policy recovery, usually re-mapping to an error | Granting fallback privileges when the AS fails is dangerous |
| `retryWhen` | Retrying suitable transient I/O errors | Do not retry invalid tokens; bound attempts and backoff |
| `doOnError` / `doFinally` | Non-sensitive observability and metrics | Never log bearer tokens or secrets |
| `cache` | Sharing results under an explicit policy | Do not turn an active token into permanent privileges |
| `subscribeOn` | Intentionally offloading a blocking boundary to a dedicated scheduler | Does not make a blocking client reactive |

## 11. Empty, Error, and Retry: Distinguishing Token Errors from Infrastructure Errors

A real system encounters at least three failure categories:

1. **Rejected token:** `active=false`, wrong audience/issuer/token profile.
2. **Unable to reach AS:** DNS, TLS, timeout, 5xx, rate limiting.
3. **Contract-violating response:** missing `active`, wrong JSON types, issuer/audience metadata failing requirements.

Never lump all of these into a single catch block that emits a principal "to keep the system running."

### 11.1. Expected Outcome Matrix

| Scenario | Expected `Mono` at introspection layer | Security behavior |
|---|---|---|
| AS returns `active=true`, valid metadata | `onNext(principal) + onComplete` | Proceed to authorization |
| AS returns `active=false` | `onError` invalid token | Do not create a successful Authentication |
| Wrong audience | `onError` token not accepted by API | Do not grant access using another resource's token |
| Wrong issuer | `onError` | Do not grant access from another issuer |
| AS timeout | `onError(TimeoutException)` or equivalent exception | **Fail closed**; report operational error |
| AS 5xx | `onError` upstream failure | Never pass through |
| AS returns non-JSON/contract-breaking body | `onError` | Never infer `active=true` |
| Delegate returns `Mono.empty()` | Wrapper converts to `onError` | Never authenticate via an empty result |
| Missing scope on an active token | May return principal lacking `SCOPE_...` | HTTP/method scope rule denies access |
| AS returns client-credentials metadata | Principal may represent a service | Do not infer an interactive user from `client_id` |

### 11.2. Retry Only with Justification

An introspection request is generally a status-reading operation, so retrying certain connection errors can be functionally acceptable. However:

- Retries increase load on the AS and can trigger a **retry storm**.
- The bearer token is transmitted again; transport and metrics must remain protected.
- Never retry `active=false`, wrong issuer/audience, or non-recoverable contract errors.
- Retries can push authentication latency past SLA and keep requests queued longer.
- Bound the retry count, overall timeout, backoff, and apply a circuit breaker where appropriate.

Conceptual example:

```java
return delegate.introspect(token)
    .timeout(Duration.ofSeconds(2))
    .retryWhen(Retry.backoff(2, Duration.ofMillis(100))
        .filter(this::isTransientInfrastructureFailure))
    .switchIfEmpty(Mono.error(
        new BadOpaqueTokenException("No introspection result")));
```

`isTransientInfrastructureFailure` is an **application-defined** predicate returning true only for retryable I/O errors; it must never return true for rejected tokens or security policy failures. `Retry` is `reactor.util.retry.Retry`. The snippet demonstrates operator composition, not a blanket recommendation for every AS.

**Place timeouts/retries at the proper layer:** HTTP client timeouts are still needed to bound connect/read phases; Reactor's `timeout` protects at the publisher level. The total request timeout must account for all retry attempts.

### 11.3. Do Not Blindly Convert Every Upstream Error to 401 invalid_token

A token confirmed inactive by the AS differs from the AS being down. For the API:

- Invalid token → typically 401.
- Active token missing scope → typically 403.
- AS timeout → infrastructure authentication failure; HTTP status may follow exception handling / custom 5xx, but **must never grant access**.

Converting every `TimeoutException` into `BadOpaqueTokenException` can cause the system to return 401 and mislead clients into thinking the token has expired or been revoked. Distinguish root causes in metrics/logs and shape public responses per security policy.

### 11.4. Cancellation

If a client closes the connection before introspection completes, the subscription may be canceled. This does not guarantee the HTTP request to the AS was recalled; the AS may already have received the token. Never log "AS never saw token" merely because the publisher was canceled.

Avoid detached subscriptions and unnecessary I/O; cancellation helps conserve resources when operators and the HTTP client support it. Observability should distinguish cancel, timeout, invalid, and success.

## 12. Scopes, Authorities, and Business Permissions After Introspection

Suppose the AS returns:

```json
{
  "active": true,
  "sub": "user-842",
  "scope": "orders.read orders.update",
  "aud": ["orders-api"],
  "tenant_id": "tenant-a"
}
```

The principal has authorities:

```text
SCOPE_orders.read
SCOPE_orders.update
```

In `SecurityWebFilterChain`:

```java
.pathMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.pathMatchers(HttpMethod.PUT, "/api/orders/**")
    .hasAuthority("SCOPE_orders.update")
```

With method security:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import reactor.core.publisher.Mono;

@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public Mono<OrderView> readOrder(String id) {
    return repository.findById(id).map(OrderView::from);
}
```

In WebFlux, `@EnableReactiveMethodSecurity` must be enabled and the method must be invoked through a supported Spring-managed proxy. `@PreAuthorize` checks authorities on the Authentication already built after introspection—it does **not** perform a new introspection HTTP call per annotation.

### 12.1. Scope Does Not Grant Access to Every Object

An `orders.read` token does not imply permission to view any order ID. The business service needs:

```text
GET /api/orders/ORD-123
  |
  +-- token active?
  +-- aud = orders-api?
  +-- has SCOPE_orders.read?
  +-- sub + issuer + tenant allowed to read ORD-123?
  +-- order state/policy permits disclosure?
```

With reactive repositories, filter in the database query by actor/tenant rather than loading all records and applying a reactive post-filter. Fields like `sub`/`tenant_id` may be absent on client-credentials tokens; policies must distinguish service identities from user identities.

### 12.2. Risk of Custom Converters Dropping `SCOPE_`

Anti-pattern:

```java
return delegate.introspect(token)
    .map(principal ->
        new DefaultOAuth2AuthenticatedPrincipal(
            principal.getName(),
            principal.getAttributes(),
            List.of(new SimpleGrantedAuthority("ROLE_USER"))));
```

This replaces the entire authority set. If the intent was only to add a role, the code dropped `SCOPE_orders.read`, causing the API to return 403 even though the AS granted the scope. You must **retain `principal.getAuthorities()`** or apply an explicit policy filter. Never add `ROLE_ADMIN` from unverified metadata.

### 12.3. `scope` Is Not `scp`/`permissions` by Default

RFC 7662 defines `scope` typically as a space-delimited string:

```json
{ "active": true, "scope": "orders.read orders.write" }
```

Some AS implementations return extensions:

```json
{ "active": true, "scp": ["orders.read", "orders.write"] }
```

Do not assume every Spring Security introspector maps `scp`/`permissions` the same way as `scope`. If the AS uses extensions, agree on the schema, authoritative source, and allowed values, and write an adapter/decorator **after introspection**. Do not blindly merge two claims that may have different semantics.

## 13. Reactor Context and Using the Principal After Authentication

In WebFlux, Spring Security uses the **Reactor Context** to propagate `SecurityContext` along the request chain. Do not assume the principal can be read from a Servlet ThreadLocal.

Example:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

public Mono<String> currentActorName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication())
        .map(Authentication::getName);
}
```

In a controller, you can inject:

```java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import reactor.core.publisher.Mono;

@GetMapping("/api/me")
public Mono<String> me(
        @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
    return Mono.just(principal.getName());
}
```

The example uses `OAuth2AuthenticatedPrincipal` because opaque resource-server Authentications typically hold that principal type. Do not copy a JWT `@AuthenticationPrincipal Jwt` example and assume it works here. In shared domain code, map different principal types into an internal contract type like `CurrentActor`.

### 13.1. Do Not Use Global SecurityContextHolder

Anti-pattern:

```java
// Do not use for multi-user WebFlux:
SecurityContextHolder.setStrategyName(
    SecurityContextHolder.MODE_GLOBAL);
```

This can cause a single Authentication to be shared across requests and users. Missing context in a detached reactive subscription must be fixed through proper publisher/context propagation, **not** a global holder.

### 13.2. Do Not Trigger a Nested Subscribe

```java
introspector.introspect(token)
    .subscribe(principal -> cachedCurrentUser = principal);

return Mono.just("ok");
```

Never use this pattern in a request filter or controller: a detached subscription can run after the response has completed, ignore errors, and mix state across users if `cachedCurrentUser` is a shared field. Let Spring Security manage the reactive authentication pipeline.

## 14. Caching Introspection: Optimization with a Security Trade-off

Introspection can add a network round-trip per request. Caching reduces latency while introducing a **revocation delay** window.

### 14.1. Do Not Use `Mono.cache()` as an Unbounded Token Store

Dangerous example:

```java
ConcurrentMap<String, Mono<OAuth2AuthenticatedPrincipal>> cache =
    new ConcurrentHashMap<>();

public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
    return cache.computeIfAbsent(
        token,
        t -> delegate.introspect(t).cache());
}
```

This pattern can retain an active principal **indefinitely** and store raw tokens as map keys in memory. If the AS revokes a token, the API may continue using the cached result. It also risks unbounded memory growth and retaining token data longer than necessary.

A production cache needs a policy:

- Key bound to **the credential and the appropriate resource/issuer/policy namespace**, not just `sub`.
- TTL shorter than or not exceeding `exp` if present.
- Bounded size and lifetime.
- Clear behavior on `active=false`, network errors, and cancellation.
- Synchronization/invalidation mechanism when privileges change or tokens are revoked if near-real-time revocation is required.
- Never log or export raw cache keys or sensitive attributes.

### 14.2. Two Tokens for the Same Subject Can Have Different Scopes

```text
token-A: sub=user-842, scope=orders.read
token-B: sub=user-842, scope=orders.read orders.delete
```

If authentication is cached solely by `sub`, token A could inherit authorities from token B. Scopes belong to **the issued access token**, not permanently to a username.

### 14.3. Cache the Result or Cache the HTTP Response?

| Cache | What is stored | Risks |
|---|---|---|
| Cache `Mono<OAuth2AuthenticatedPrincipal>` | May share publisher/result | Can cache errors/revoked tokens and fail to expire properly |
| Cache principal after introspection | Verified attributes/authorities | Can become stale on scope or issuer/audience policy changes |
| Cache HTTP introspection response | JSON metadata | Sensitive PII/claims, serialization, schema drift |
| No cache | Queries AS per request | AS availability/latency impact |

If policy mandates near-immediate token revocation, carefully evaluate any caching. Caching is an operational and security decision, **not a default property of `Mono`**.

## 15. Unit Testing the `Mono` Contract with `StepVerifier`

The focus of testing a reactive introspector is **not just inspecting return values**, but observing publisher signals:

```text
Case A: onNext(principal) -> onComplete
Case B: onError(BadOpaqueTokenException)
Case C: Mono.empty() from delegate -> wrapper converts to error
Case D: error from delegate -> no fallback principal
Case E: unsubscribed -> no remote call triggered (with Mono.defer)
Case F: original authorities preserved after mapping
```

No real IdP is needed for decorator unit tests; a fake delegate can return predetermined `Mono` instances.

### 15.1. Minimal Principal Fixture

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;

final class PrincipalFixtures {

    static final String ISSUER =
        "https://idp.example.com/realms/shop";

    static OAuth2AuthenticatedPrincipal readPrincipal() {
        Map<String, Object> attributes = new LinkedHashMap<>();
        attributes.put("sub", "user-842");
        attributes.put("iss", ISSUER);
        attributes.put("aud", List.of("orders-api"));
        attributes.put("permissions", List.of("order:approve"));

        return new DefaultOAuth2AuthenticatedPrincipal(
            "user-842",
            attributes,
            List.of(new SimpleGrantedAuthority("SCOPE_orders.read")));
    }
}
```

The fixture constructs a principal directly. It **does not prove the access token passed AS validation**; that is an intentional assumption of a wrapper unit test.

### 15.2. Testing Success and Authority Preservation

```java
import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection
    .ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class PolicyCheckingReactiveIntrospectorTest {

    private static final String TOKEN = "opaque-unit-test-token";

    @Test
    void validPrincipalPreservesScopeAndAddsApprovedPermission() {
        ReactiveOpaqueTokenIntrospector delegate =
            token -> Mono.just(PrincipalFixtures.readPrincipal());

        PolicyCheckingReactiveIntrospector subject =
            new PolicyCheckingReactiveIntrospector(
                delegate,
                PrincipalFixtures.ISSUER,
                "orders-api");

        StepVerifier.create(subject.introspect(TOKEN))
            .assertNext(principal -> {
                assertThat(principal.getName())
                    .isEqualTo("user-842");
                assertThat(principal.getAuthorities())
                    .extracting(GrantedAuthority::getAuthority)
                    .containsExactlyInAnyOrder(
                        "SCOPE_orders.read",
                        "PERMISSION_order:approve");
            })
            .verifyComplete();
    }
}
```

Key point: `StepVerifier` asserts that **one principal is emitted and the publisher completes**, while checking the authority list after mapping. No OAuth client secret or HTTP mock server is needed.

### 15.3. Testing Invalid Token

```java
@Test
void inactiveTokenCannotBecomeAuthenticatedPrincipal() {
    ReactiveOpaqueTokenIntrospector delegate =
        token -> Mono.error(
            new BadOpaqueTokenException("Token is inactive"));

    var subject = new PolicyCheckingReactiveIntrospector(
        delegate, PrincipalFixtures.ISSUER, "orders-api");

    StepVerifier.create(subject.introspect("inactive-token"))
        .expectError(BadOpaqueTokenException.class)
        .verify();
}
```

This test only proves the wrapper **does not swallow errors**. Translating JSON `active=false` into `BadOpaqueTokenException` is the delegate's responsibility and must be tested separately at the contract/adapter layer.

### 15.4. Testing Empty Fail Closed

```java
@Test
void emptyDelegateResultIsRejected() {
    ReactiveOpaqueTokenIntrospector delegate =
        token -> Mono.empty();

    var subject = new PolicyCheckingReactiveIntrospector(
        delegate, PrincipalFixtures.ISSUER, "orders-api");

    StepVerifier.create(subject.introspect("empty-token"))
        .expectError(BadOpaqueTokenException.class)
        .verify();
}
```

This directly tests the **Mono contract**. Never use `verifyComplete()` with no `onNext` as a successful authentication.

### 15.5. Testing Wrong Issuer/Audience

```java
@Test
void wrongAudienceIsRejected() {
    Map<String, Object> attributes = new HashMap<>();
    attributes.put("iss", PrincipalFixtures.ISSUER);
    attributes.put("aud", List.of("payments-api"));
    attributes.put("sub", "user-842");

    OAuth2AuthenticatedPrincipal source =
        new DefaultOAuth2AuthenticatedPrincipal(
            "user-842",
            attributes,
            List.of(new SimpleGrantedAuthority("SCOPE_orders.read")));

    ReactiveOpaqueTokenIntrospector delegate =
        token -> Mono.just(source);

    var subject = new PolicyCheckingReactiveIntrospector(
        delegate, PrincipalFixtures.ISSUER, "orders-api");

    StepVerifier.create(subject.introspect("test-token"))
        .expectError(BadOpaqueTokenException.class)
        .verify();
}
```

`HashMap` and the principal/authority imports must be added to the test class as appropriate. Similar cases include missing issuer, null/numeric audience, valid String audience, and a collection with multiple audiences. **Never use substring matching** on raw audience strings, which could wrongly accept a resource like `orders-api-other`.

### 15.6. Testing Laziness

```java
@Test
void delegateIsCalledAtSubscriptionTime() {
    AtomicInteger invocations = new AtomicInteger();

    ReactiveOpaqueTokenIntrospector delegate = token -> {
        invocations.incrementAndGet();
        return Mono.just(PrincipalFixtures.readPrincipal());
    };

    var subject = new PolicyCheckingReactiveIntrospector(
        delegate, PrincipalFixtures.ISSUER, "orders-api");

    Mono<OAuth2AuthenticatedPrincipal> result =
        subject.introspect("test-token");

    assertThat(invocations.get()).isZero();

    StepVerifier.create(result)
        .expectNextCount(1)
        .verifyComplete();

    assertThat(invocations.get()).isEqualTo(1);
}
```

`AtomicInteger` is in `java.util.concurrent.atomic`. This test proves the **wrapper uses `Mono.defer`**; it does not evaluate the production HTTP client code. A delegate with an internal cache may have its own semantics; this unit test only measures method invocations on the fake delegate.

### 15.7. Testing Infrastructure Errors Are Not Swallowed

```java
@Test
void infrastructureFailureDoesNotGrantPermission() {
    RuntimeException upstreamFailure =
        new IllegalStateException("Introspection unavailable");

    ReactiveOpaqueTokenIntrospector delegate =
        token -> Mono.error(upstreamFailure);

    var subject = new PolicyCheckingReactiveIntrospector(
        delegate, PrincipalFixtures.ISSUER, "orders-api");

    StepVerifier.create(subject.introspect("test-token"))
        .expectErrorMatches(error -> error == upstreamFailure)
        .verify();
}
```

This test does not dictate that the HTTP status must be 401; it is a publisher unit test. The HTTP status when the AS is down belongs to integration/exception handling policy.

## 16. Testing Timeouts, Cancellation, and Edge Cases

### 16.1. Virtual Time for Timeouts

Reactor Test supports virtual time to avoid real waiting:

```java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

StepVerifier.withVirtualTime(() ->
        Mono.<OAuth2AuthenticatedPrincipal>never()
            .timeout(Duration.ofSeconds(3)))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(3))
    .expectError(java.util.concurrent.TimeoutException.class)
    .verify();
```

This example verifies the semantics of the `timeout` operator, not that the HTTP client has socket timeouts configured. A separate integration test must simulate a slow AS response to verify real timeouts and error handling.

### 16.2. Cancel

```java
StepVerifier.create(
        Mono.<OAuth2AuthenticatedPrincipal>never())
    .expectSubscription()
    .thenCancel()
    .verify();
```

This test proves the publisher can be canceled, not that an upstream AS stopped processing the request. Testing real network cancellation requires an integration test with WebClient and an appropriate mock server.

### 16.3. Delegate Returning Null

A buggy implementation might do:

```java
@Override
public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
    return null; // VIOLATES API contract.
}
```

Reactive Streams does not accept null as a success element. Returning null instead of a Mono causes a programming error, not an "unauthenticated user" token. With `Mono.defer`, a delegate returning null becomes a pipeline error; never grant privileges to "work around" that bug.

Similarly:

```java
return Mono.just((OAuth2AuthenticatedPrincipal) null);
```

is invalid because `Mono.just` requires a non-null element. If a client-credentials token lacks `sub`, policy must interpret the service identity per the contract rather than constructing a null principal.

### 16.4. A Publisher Emitting Multiple Principals Is the Wrong Type

`ReactiveOpaqueTokenIntrospector` returns `Mono`, not `Flux`: one verified token must resolve to **a single principal conclusion** for the invocation, not a stream of multiple identities. Do not use `Flux.fromIterable(principals).next()` to arbitrarily pick the first principal if an AS returns multiple records; that violates the contract and risks identity confusion.

## 17. Testing the Spring Security Pipeline with `WebTestClient`

Unit tests on `PolicyCheckingReactiveIntrospector` do not prove `SecurityWebFilterChain` actually uses this implementation. To test wiring:

1. Configure a test WebFlux application with `SecurityWebFilterChain` enabling the opaque-token resource server.
2. Provide a fake `ReactiveOpaqueTokenIntrospector` with controllable behavior.
3. Send a real **Authorization: Bearer ...** header via `WebTestClient`.
4. Verify a valid token + matching scope is permitted; an invalid token gets 401; an active token missing scope gets 403.

### 17.1. Fake Introspector for Testing

```java
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.security.oauth2.server.resource.introspection
    .ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;

@TestConfiguration
class FakeIntrospectionConfiguration {

    @Bean
    @Primary
    ReactiveOpaqueTokenIntrospector testIntrospector() {
        ReactiveOpaqueTokenIntrospector delegate = token -> {
            if ("read-token".equals(token)) {
                return Mono.just(PrincipalFixtures.readPrincipal());
            }
            return Mono.error(
                new BadOpaqueTokenException("Token is inactive"));
        };

        return new PolicyCheckingReactiveIntrospector(
            delegate,
            PrincipalFixtures.ISSUER,
            "orders-api");
    }
}
```

This is a test fixture. Never publish a `testIntrospector` bean in production configuration; it accepts a literal token string without contacting a real Authorization Server.

### 17.2. HTTP Request Test

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive
    .AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class OpaqueWebFluxSecurityTest {

    @Autowired
    WebTestClient client;

    @Test
    void acceptedTokenCanCallReadApi() {
        client.get().uri("/api/orders/ORD-123")
            .headers(headers ->
                headers.setBearerAuth("read-token"))
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void inactiveTokenIsRejected() {
        client.get().uri("/api/orders/ORD-123")
            .headers(headers ->
                headers.setBearerAuth("inactive-token"))
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

This sample requires the test context to import `FakeIntrospectionConfiguration`, a controller for `/api/orders/ORD-123`, and compatible data/business policy; `@AutoConfigureWebTestClient` does not create endpoints on its own. If the security DSL **hardcodes an introspector instance** rather than injecting a bean, simply adding a `@Primary` test bean might not replace it. Ensure the test chain actually uses the configured fake.

### 17.3. Testing Missing Scope

The fake introspector can return a principal with `SCOPE_other.read` for `wrong-scope-token`; send the token in the Bearer header and expect **403** when the route requires `SCOPE_orders.read`. When the fake returns `BadOpaqueTokenException`, expect **401** for the invalid token.

The case where scope is right but the order belongs to a different tenant must be tested separately in the business service. A token with `SCOPE_orders.read` **does not automatically grant permission to read every ID**.

### 17.4. `mockOpaqueToken()` Does Not Test the Introspector

Spring Security Test provides:

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOpaqueToken;

client.mutateWith(mockOpaqueToken()
        .authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get().uri("/api/orders/ORD-123")
    .exchange()
    .expectStatus().isOk();
```

This is a good way to test **authorization with a pre-built Authentication**. However, it can **bypass `ReactiveOpaqueTokenIntrospector` and skip calling the AS**. Therefore:

- `mockOpaqueToken()` tests HTTP/method authorization.
- Fake introspector + Bearer header tests wiring/interceptor behavior.
- Mock HTTP server for the introspection endpoint tests RFC 7662 response parsing/`active`/scope mapping.
- Integration tests against a real AS (in a test environment) test client authentication, token issuance, revocation, and the metadata contract.

Never claim "introspection is tested" just because `mockOpaqueToken()` returns 200.

## 18. Contract Testing Against a Mock HTTP Introspection Endpoint

To test the **`SpringReactiveOpaqueTokenIntrospector`** implementation itself rather than only the wrapper, you can use a local mock HTTP server in tests (such as MockWebServer or WireMock) returning standard responses:

```json
{
  "active": true,
  "scope": "orders.read orders.update",
  "sub": "user-842",
  "aud": ["orders-api"],
  "iss": "https://idp.example.com/realms/shop"
}
```

and:

```json
{
  "active": false
}
```

Tests should verify:

| Fixture response/condition | Adapter outcome |
|---|---|
| `active=true`, `scope=orders.read orders.update` | One principal, with authorities `SCOPE_orders.read` and `SCOPE_orders.update` |
| `active=true`, missing scope | Principal lacks scope authority, or is rejected by additional policy |
| `active=false` | Token not authenticated, publisher errors |
| `aud=["payments-api"]` | Orders API decorator rejects |
| Wrong JSON type, e.g., `active="true"` | Does not infer valid |
| HTTP 401 from introspection endpoint | Client credentials/AS failure, no privileges granted |
| HTTP 5xx or timeout | Infrastructure error, fail closed |
| Malformed JSON body | Decode/contract error, fail closed |

Exact implementation behavior for attribute parsing can vary by version, so assert **authentication status and the authorities the API actually uses**, rather than asserting an entire object via `toString()`.

### 18.1. Do Not Hardcode Real Tokens in Fixtures

Introspection tokens are Bearer credentials—if leaked they can be replayed. Never commit:

```text
Authorization: Bearer <real-user-token>
client_secret=<real-secret>
entire raw introspection response with PII
```

into test artifacts, logs, or source control. Use valueless dummy tokens such as `opaque-test-token` and synthetic metadata. Real AS tests should use short-lived credentials, test-only scopes, and controlled cleanup.

## 19. Misconceptions That Easily Cause Vulnerabilities

| Misconception | Correct understanding |
|---|---|
| "Returning `Mono` means the HTTP call is non-blocking." | Blocking code could run before `Mono.just`; verify the implementation |
| "`Mono.empty()` means a valid anonymous token." | Empty does not prove validity; fail closed per the contract |
| "An active token can access any endpoint." | Audience/scope and business authorization are still required |
| "`onErrorResume` returning a guest principal keeps the API resilient." | Can turn a revoked token or AS outage into unauthorized access |
| "`scope=orders.write` implicitly includes read/delete." | Scopes have no default hierarchy |
| "`hasRole('orders.read')` checks an OAuth scope." | Default role prefix is `ROLE_`, whereas scope mapping is usually `SCOPE_` |
| "`scp` array is always equivalent to `scope`." | Depends on IdP/adapter; requires an explicit contract |
| "Raw JWT token contains `aud=orders-api`, so introspection isn't needed." | Unverified claims are not proof |
| "Using `@AuthenticationPrincipal Jwt` works for opaque principals." | Opaque tokens usually produce `OAuth2AuthenticatedPrincipal` |
| "Using Servlet `OpaqueTokenIntrospector` in WebFlux is fine." | It is synchronous; the reactive path uses `ReactiveOpaqueTokenIntrospector` |
| "When the AS fails, we can reuse the user's previous privileges." | Risks mixing tokens/authorities; any cache must be keyed by credential with policy-driven TTL |
| "`Mono.cache()` keeps token revocation effective immediately." | Caching can retain already-revoked tokens |
| "Calling `subscribe()` in a filter runs auth early." | Detached subscriptions create races and dropped errors |
| "Calling `block()` in `map` only takes a moment." | Can block the Netty event loop and fail on non-blocking schedulers |
| "`MockOpaqueToken` tests prove the AS returned `active=true`." | It mocks the Authentication, bypassing the real introspector |
| "HTTP 403 proves the AS rejected the token." | 403 usually means insufficient permissions; invalid tokens usually yield 401 |
| "A token with `SCOPE_orders.read` can read any order." | Domain-level owner/tenant/state checks are still required |
| "With `ReactiveOpaqueTokenAuthenticationConverter`, no introspector is needed." | The converter processes the result **after** introspection succeeds |
| "On timeout, we can allow by default." | A timeout means missing verification proof; must fail closed |
| "Cancellation means the AS never saw the token." | The request may already have reached the AS; cancellation does not undo network calls |

## 20. Production Design and Testing Checklist

When adding or customizing reactive introspection, you can implement in this order:

1. **Confirm the token contract:** opaque/reference token or introspected JWT; which AS endpoint is trusted?
2. **Enable the right WebFlux stack:** `SecurityWebFilterChain`, `ServerHttpSecurity`, and `oauth2ResourceServer(...opaqueToken...)`.
3. **Use the right interface:** `ReactiveOpaqueTokenIntrospector`, returning `Mono<OAuth2AuthenticatedPrincipal>`, never returning a principal directly or null.
4. **Define success:** only emit a principal after verification, with trusted attributes/authorities.
5. **Define failure:** inactive/error/empty tokens never produce a successful Authentication; avoid fail-open.
6. **Define identity and resource:** issuer/audience, client credentials vs. user, tenant/subject, required fields.
7. **Keep scope mapping accurate:** `scope` → `SCOPE_...`; custom permissions only via allowlist and verified sources.
8. **Ensure reactive I/O:** no `block()`, no `Mono.just(blockingCall())` on the event loop.
9. **Define timeout/retry:** bound latency and upstream failures; never retry invalid tokens; never leak credentials.
10. **Control caching:** TTL, exp, revocation, principal isolation by token/resource/issuer.
11. **Enforce business policy:** scopes are only functional permissions; owner/tenant/state must be checked separately.
12. **Unit test Mono signals:** success, error, empty, invalid, malformed, lazy subscription, scope preservation.
13. **Test the HTTP adapter:** `active=true/false`, `scope` format, HTTP/JSON/TLS/timeout errors.
14. **Test WebFlux wiring:** real Bearer header, custom introspector invoked, 401/403 at the right layers.
15. **Separate AS integration tests:** client auth, token issuance/revocation, metadata contract, and secret rotation.
16. **Production observability:** p95/p99 latency, AS timeouts, 401/403 rates, cache hits, cancellations; never log raw tokens.

### 20.1. Decision Diagram When `Mono` Completes

```mermaid
flowchart TD
    A["ReactiveOpaqueTokenIntrospector.introspect(token)"] --> B{"What signal does the publisher emit?"}
    B -->|"onNext(principal)"| C{"Did principal come from a trusted introspection source?"}
    C -->|"No"| X["Deny / authentication error"]
    C -->|"Yes"| D{"Issuer / audience / token profile valid?"}
    D -->|"No"| X
    D -->|"Yes"| E["Preserve scope authorities, custom map per policy"]
    E --> F{"HTTP/method scope granted?"}
    F -->|"No"| Y["Deny authorization"]
    F -->|"Yes"| G{"Owner / tenant / business state valid?"}
    G -->|"No"| Y
    G -->|"Yes"| H["Allow resource processing"]
    B -->|"onError"| I["Classify invalid vs AS failure<br/>grant no privileges"]
    B -->|"empty onComplete"| J["Convert to error/fail closed"]
    B -->|"does not terminate"| K["Timeout and fail closed"]
```

## 21. Summary

```text
WEBFLUX OPAQUE RESOURCE SERVER

Authorization: Bearer opaque-token
                  |
                  v
OpaqueTokenReactiveAuthenticationManager
                  |
                  v
ReactiveOpaqueTokenIntrospector
                  |
                  v
Mono<OAuth2AuthenticatedPrincipal>
  |
  +-- onNext(principal) + onComplete
  |      -> Authentication / SCOPE_ authorities
  |      -> HTTP authorization
  |      -> owner/tenant/business policy
  |
  +-- onError(...)
  |      -> Authentication failed
  |
  +-- onComplete() without principal
  |      -> Not a successful authentication;
  |         custom wrappers should fail closed
  |
  +-- does not complete
         -> timeout, no fallback privileges

Avoid:
  Mono.just(blockingIntrospection())
  Mono.empty() as default access
  onErrorResume(... -> adminPrincipal)
  subscribe() detached from authentication path
  unbounded cache()
```

**`ReactiveOpaqueTokenIntrospector` is the boundary between an untrusted Bearer token and a verified principal in WebFlux.** The `Mono<OAuth2AuthenticatedPrincipal>` contract requires code to clearly distinguish **a success value**, **no value**, **an error**, and **waiting too long**. Only a principal from trusted introspection may be used to build an Authentication; empty/error/timeout are never grounds to fabricate authorities.

In real deployments, let `SpringReactiveOpaqueTokenIntrospector` perform reactive HTTP introspection, wrap it with a policy delegate when issuer/audience checks or custom permission mapping are required, preserve `SCOPE_` unless there is a clear reason to change it, and separate your test layers: **`StepVerifier` for the publisher contract, mock HTTP for RFC 7662, `WebTestClient` for Spring Security wiring, and integration tests with a real AS for the environment contract**.

## References

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): meaning of `active`, `scope`, metadata, and introspection endpoint authorization.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): OAuth access tokens, scope boundaries, and the Resource Server model.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer credentials, `invalid_token`, `insufficient_scope`, and 401/403.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): binding access tokens to a resource/audience.
- [Spring Security Reference — Reactive Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html): `SpringReactiveOpaqueTokenIntrospector`, WebFlux wiring, authorities, and custom introspection.
- [Spring Security 6.5 Reference — Reactive Opaque Token](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/opaque-token.html): the same topic for the 6.5 line when projects have not upgraded to 7.x.
- [Spring Security API — ReactiveOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html): signature `Mono<OAuth2AuthenticatedPrincipal> introspect(String)`.
- [Spring Security API — SpringReactiveOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringReactiveOpaqueTokenIntrospector.html): implementation and builder.
- [Spring Security API — OpaqueTokenReactiveAuthenticationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/OpaqueTokenReactiveAuthenticationManager.html): creating Authentication from introspection.
- [Spring Security API — ReactiveOpaqueTokenAuthenticationConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenAuthenticationConverter.html): converting a principal into `Mono<Authentication>`.
- [Spring Security Reference — Testing OAuth 2.0 in WebFlux](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockOpaqueToken()` and limitations of authentication fixtures.
- [Project Reactor Reference — Mono](https://projectreactor.io/docs/core/release/reference/coreFeatures/mono.html): `Mono` and completion/error signals.
- [Project Reactor Reference — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html): StepVerifier and virtual time.
- [Project Reactor Reference — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): Reactor Context in reactive pipelines.
- [Spring Security Reference — Reactive WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `SecurityWebFilterChain`/`ServerHttpSecurity`.
- [OWASP API Security 2023 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): why scope is insufficient for object-level access.

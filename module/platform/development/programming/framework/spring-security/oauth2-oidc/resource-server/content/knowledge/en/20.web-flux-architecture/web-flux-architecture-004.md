# ReactiveAuthenticationManager for JWT or Opaque Tokens

## 1. Lesson Objectives

In **Spring Security OAuth 2.0/OIDC Resource Server**, WebFlux processes HTTP requests using the **Reactive Streams** model built on Project Reactor. When a client calls an API with a Bearer access token, Spring Security must authenticate the token and create an `Authentication` before checking permissions.

In the Servlet stack, developers typically encounter `AuthenticationManager`, `ProviderManager`, `JwtAuthenticationProvider`, or `OpaqueTokenAuthenticationProvider`. In the **WebFlux stack**, the corresponding extension point is **`ReactiveAuthenticationManager`**, which returns a `Mono<Authentication>` instead of a synchronous `Authentication`.

Two key implementations:

- **`JwtReactiveAuthenticationManager`**: uses `ReactiveJwtDecoder` to verify JWT access tokens (JWS, keys/algorithms, issuer, audience, timestamps, and contract-defined validations), then creates a `JwtAuthenticationToken`.
- **`OpaqueTokenReactiveAuthenticationManager`**: uses `ReactiveOpaqueTokenIntrospector` to query the Authorization Server for token status/metadata, then constructs an Authentication (typically `BearerTokenAuthentication`) from the returned principal and authorities.

HTTP examples:

```http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6...
```

or:

```http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer 8pDQyU4Xopaque...
```

Both are **Bearer credentials**, but their validation mechanisms differ. **Bearer does not automatically imply JWT**; nor can a token without dots be assumed to be a valid opaque token.

> **Key principle:** `ReactiveAuthenticationManager` is a **reactive contract for authenticating credentials**. It does not decide on its own whether a JWT key source or introspection endpoint is trustworthy, does not grant record ownership, and does not replace `AuthorizationManager` policies. Use the implementation that matches your API's **access-token contract and trust boundary**.

## 2. What Is ReactiveAuthenticationManager?

The interface belongs to package `org.springframework.security.authentication`:

```java
@FunctionalInterface
public interface ReactiveAuthenticationManager {
    Mono<Authentication> authenticate(Authentication authentication);
}
```

Three distinct outcomes:

| Reactor Signal | Interface Meaning | Security Behavior |
| --- | --- | --- |
| `Mono.just(authentication)` | Authentication succeeded; Authentication holds the accepted principal and authorities. | Continue authorization processing in the Security WebFilterChain. |
| `Mono.empty()` | The manager **could not determine** how to handle the input Authentication. | Must not be treated as “authentication succeeded”; another manager may handle it according to a designed composition. |
| `Mono.error(authenticationException)` | Authentication failed. | Halt the authentication path; filter/entry point handles the error appropriately without creating a principal. |

You must distinguish **`Mono.empty()` because the manager does not support the credential type** from **a token determined to be invalid**. For a token with a bad signature, expired timestamp, or introspection `active=false`, the authentication path must fail; never return empty and treat the caller as anonymous or fall back to a weaker mechanism.

An illustrative implementation for a custom credential:

```java
public final class ExampleReactiveAuthenticationManager
        implements ReactiveAuthenticationManager {

    @Override
    public Mono<Authentication> authenticate(Authentication authentication) {
        if (!(authentication instanceof ExampleAuthenticationToken token)) {
            return Mono.empty(); // This credential type is not supported.
        }

        return validateTrustedCredential(token)
                .switchIfEmpty(Mono.error(
                        new BadCredentialsException("Invalid credential")))
                .map(principal -> new ExampleAuthenticatedToken(principal));
    }
}
```

`ExampleAuthenticationToken`, `ExampleAuthenticatedToken`, and `validateTrustedCredential` are **hypothetical types/methods**, not built into Spring Security. The example merely illustrates the Reactor contract and fail-closed responsibility. For real JWT/opaque tokens, **do not rewrite the manager** when Spring Security already provides standard implementations.

### 2.1. Mono Is a Work Description, Not an Immediate Result

In Reactor, `Mono<Authentication>` represents an asynchronous pipeline. Results or errors are emitted to the subscriber under Reactive Streams rules. Spring Security WebFlux handles subscribing via the filter chain.

Do not do this:

```java
// WRONG in WebFlux request path: blocks the thread with a blocking call.
Authentication authentication =
        reactiveAuthenticationManager.authenticate(input).block();
```

Blocking on the Netty event loop can stall request handling or throw runtime errors. Instead, compose carefully with `flatMap`, `map`, `switchIfEmpty`, and `onErrorResume`. In particular, **`onErrorResume(error -> Mono.just(adminAuthentication))` is a critical vulnerability** because it turns an authentication failure into elevated privileges.

## 3. Comparing JWT and Opaque Paths Reactively

| Aspect | JWT Resource Server | Opaque Resource Server |
| --- | --- | --- |
| Manager | `JwtReactiveAuthenticationManager` | `OpaqueTokenReactiveAuthenticationManager` |
| Verifier component | `ReactiveJwtDecoder` | `ReactiveOpaqueTokenIntrospector` |
| Trust source | Configured issuer/JWKS/public keys; JWT validators. | Authorization Server introspection endpoint and Resource Server credentials/trust. |
| Protocol/format | Typically signed JWT JWS. | Token string verified by the AS via OAuth 2.0 Token Introspection (RFC 7662). |
| Typical I/O | Fetch JWKS/discovery and cache; verify signatures locally once keys are loaded. | HTTP introspection per token/request or per approved caching strategy. |
| Revocation before `exp` | Not automatically visible when verifying JWTs offline alone. | Can query the AS for token status; timeliness depends on caching and AS policy. |
| Common principal | `JwtAuthenticationToken` holding `Jwt`. | `BearerTokenAuthentication` holding `OAuth2AuthenticatedPrincipal`. |
| Scopes | Typically from `scope` or `scp`, mapped to `SCOPE_...`. | Typically from introspection `scope`, mapped to `SCOPE_...`. |
| Token errors | Signature, claims, algorithm, or key validation failure. | Response `active=false` or error per introspection contract. |
| Infrastructure errors | JWKS/issuer metadata unavailable, key cache issues. | Introspection timeout, AS unavailable, or invalid client secret. |

**Do not assume JWT is universally “more secure” or opaque is universally “more secure”.** Each choice has trade-offs in latency, revocation, trust boundaries, and operations. Which validation model a token uses must be dictated by the **Authorization Server and API contract**.

### 3.1. JWTs Can Also Use Introspection

An Authorization Server can issue access tokens in JWT format yet require the Resource Server to **introspect the JWT string** to check whether the token has been revoked. In that scenario, Spring Security WebFlux can use the **opaque/introspection path** even though the token has three dot-separated segments like a JWS.

“JWT manager” and “opaque manager” are **two verification mechanisms**, not an automatic classification based on dot characters.

## 4. WebFlux Flow: From HTTP Bearer to Reactor SecurityContext

```mermaid
sequenceDiagram
    participant Client as OAuth Client
    participant Filter as AuthenticationWebFilter
    participant Conv as ServerBearerTokenAuthenticationConverter
    participant Mgr as ReactiveAuthenticationManager
    participant Val as Decoder / Introspector
    participant Ctx as Reactor SecurityContext
    participant Authz as AuthorizationWebFilter
    Client->>Filter: HTTP request + Authorization: Bearer ...
    Filter->>Conv: convert(ServerWebExchange)
    Conv-->>Filter: Mono<BearerTokenAuthenticationToken>
    Filter->>Mgr: authenticate(token)
    Mgr->>Val: decode JWT or introspect token
    alt Invalid token
        Val-->>Mgr: Mono.error(...)
        Mgr-->>Filter: Authentication failure
        Filter-->>Client: 401 / Bearer challenge
    else Authentication succeeded
        Val-->>Mgr: Jwt / OAuth2AuthenticatedPrincipal
        Mgr-->>Filter: Mono<Authentication>
        Filter->>Ctx: SecurityContext in Reactor Context
        Ctx->>Authz: Authentication + authorities
        Authz-->>Client: Allow or 403
    end
```

This is a conceptual diagram for the OAuth 2.0 Resource Server flow in **Spring WebFlux**, not a Servlet diagram. Filter and converter names may vary in customized setups, but the core contract remains **extract Bearer token → reactive authentication → Reactor SecurityContext → reactive authorization**.

### 4.1. Common Roles

| Component | Responsibility |
| --- | --- |
| `ServerWebExchange` | WebFlux request/response context. |
| `SecurityWebFilterChain` | WebFlux security chain, conceptually analogous to Servlet `SecurityFilterChain` but with a different API. |
| `ServerHttpSecurity` | DSL for configuring WebFlux security. |
| `AuthenticationWebFilter` | Reads Authentication via a converter and invokes the reactive manager. |
| `ServerBearerTokenAuthenticationConverter` | Converts an HTTP Bearer credential into an unauthenticated Authentication token. |
| `ReactiveAuthenticationManager` | Validates credentials, emitting success, empty, or error. |
| `ReactiveJwtDecoder` / `ReactiveOpaqueTokenIntrospector` | Dedicated layer for verifying access tokens. |
| `ReactiveSecurityContextHolder` | Accesses SecurityContext via Reactor Context rather than relying solely on ThreadLocal. |
| `AuthorizationWebFilter` | Enforces authorization rules on the exchange carrying the security context. |

**Do not use Servlet classes by mistake**: `HttpSecurity`, `SecurityFilterChain`, `BearerTokenAuthenticationFilter`, synchronous `JwtDecoder`, and synchronous `OpaqueTokenIntrospector` belong to the Servlet pathway. WebFlux requires `ServerHttpSecurity`, `SecurityWebFilterChain`, reactive decoders/introspectors, and reactive managers.

## 5. Setting Up a Spring Boot WebFlux Resource Server

When the application is a WebFlux API, Gradle dependencies can look like:

```gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-resource-server")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
    testImplementation("io.projectreactor:reactor-test")
}
```

This snippet uses **Groovy DSL** (with parentheses). Maven or Gradle Kotlin DSL uses different syntax. Spring Boot manages compatible versions for Spring Security and Reactor.

For JWT validation, `spring-security-oauth2-jose` must be on the classpath (typically pulled in via the Resource Server starter's dependency management). If declaring Spring Security modules manually, ensure the required dependencies are present.

**Do not add `spring-boot-starter-web` just to obtain Servlet APIs** when the goal is WebFlux running on Reactor Netty. When both Spring MVC and WebFlux are present in a Boot project, web application type deduction can cause the app to run on Servlet instead of reactive; lock down the architecture clearly and verify `SecurityWebFilterChain` is actually active.

## 6. Configuring JWT on WebFlux: The Most Common Choice

Suppose the `orders-api` accepts JWT access tokens from a trusted issuer.

### 6.1. application.yml

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/shop
```

The issuer URI is used for decoder/discovery configuration and `iss` verification. Configuring JWT alone does not automatically prove the API validates the audience according to **the API's specific contract**; ensure `aud` is validated.

### 6.2. SecurityWebFilterChain

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive
        .EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class JwtWebFluxSecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders:read")
                        .pathMatchers(HttpMethod.POST, "/api/orders/**")
                            .hasAuthority("SCOPE_orders:write")
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
```

When Boot sees valid JWT configuration and the chain does not override the decoder, Spring Security can create and use a `ReactiveJwtDecoder`, connecting it with `JwtReactiveAuthenticationManager` inside the Resource Server configuration.

For an API that processes only client-sent Bearer tokens in `Authorization` and uses no browser cookies/sessions, the CSRF policy can differ from a session-based web application; **evaluate the actual credential model** before configuring CSRF. Likewise, `hasAuthority` does not replace object/tenant authorization inside services.

### 6.3. ReactiveJwtDecoder Bean with an Audience Validator

Example using an issuer-based decoder with an added `aud=orders-api` requirement:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;

@Configuration
class JwtDecoderConfig {
    private static final String ISSUER =
            "https://login.example.test/realms/shop";

    @Bean
    ReactiveJwtDecoder reactiveJwtDecoder() {
        NimbusReactiveJwtDecoder decoder =
                NimbusReactiveJwtDecoder
                        .withIssuerLocation(ISSUER)
                        .build();

        OAuth2TokenValidator<Jwt> defaults =
                JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains("orders-api")
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                                new OAuth2Error(
                                        "invalid_token",
                                        "Audience does not match orders-api",
                                        null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        defaults, audience));
        return decoder;
    }
}
```

Important technical point: **`ReactiveJwtDecoder.decode(token)` is reactive**, yet the `OAuth2TokenValidator<Jwt>` above remains a synchronous predicate-style function validating a `Jwt` object under Spring Security's contract. You do not need to manually wrap simple validators in a `Mono`. Spring Security integrates validation into the decoder pipeline.

When an API requires a specific JWT access-token profile such as **RFC 9068**, validate `typ`/token type, `iss`, `aud`, `exp`, and other profile claims—not just the signature. Depending on your Spring Security version, built-in RFC 9068 validators or builders may exist; check the Javadoc for your exact dependency.

### 6.4. JWKS, Signing Keys, and Algorithms

The JWT manager relies on the decoder to:

- Fetch public keys from a **trusted JWKS endpoint** or configured key set.
- Select keys matching `kid`/`alg` without trusting an unauthorized `jku` endpoint embedded in the token.
- Verify the JWS signature and allow only policy-approved algorithms.
- Validate `exp`/`nbf` timestamps and issuer.
- Validate audience/token profile and API-binding claims.

`kid` is only a key-selection hint, **not a source of trust**. A JWT from issuer A with a valid signature but `aud=payments-api` must still be rejected by `orders-api`.

### 6.5. Startup and Discovery

With `issuer-uri` configured, Spring Security/Boot supports metadata and JWKS discovery. Some versions or decoder construction styles perform **lazy initialization**, whereas eagerly building a decoder from an issuer in a `@Bean` may contact the issuer at startup. When the application must start independently of the AS, use Boot configurations supporting deferred discovery or configure a trusted `jwk-set-uri` alongside an issuer validator, and verify startup behavior on your exact version.

Never work around an unavailable AS by disabling signature checks or accepting any JWT whose `iss` merely resembles the expected value.

## 7. JwtReactiveAuthenticationManager: When to Instantiate Directly?

Normally the `.oauth2ResourceServer(...jwt(...))` DSL wires everything automatically; **not every project needs to declare the manager manually**.

However, if you need to manage multiple issuers, a custom resolver, or test the manager in isolation, you can create:

```java
ReactiveAuthenticationManager jwtAuthenticationManager(
        ReactiveJwtDecoder decoder) {
    return new JwtReactiveAuthenticationManager(decoder);
}
```

The `JwtReactiveAuthenticationManager(ReactiveJwtDecoder)` constructor is provided by Spring Security. The manager typically receives a `BearerTokenAuthenticationToken` from the WebFlux Bearer converter, invokes the decoder, and converts the verified `Jwt` into a `JwtAuthenticationToken`.

Conceptual internal flow:

```text
BearerTokenAuthenticationToken(rawValue)
    ↓
JwtReactiveAuthenticationManager.authenticate(...)
    ↓
ReactiveJwtDecoder.decode(rawValue)
    ↓
Verified Jwt or Mono.error(...)
    ↓
Jwt -> authorities + JwtAuthenticationToken
    ↓
Successful Mono<Authentication>
```

If the token has a bad signature or is expired, the manager must not return an authenticated `JwtAuthenticationToken`. It emits an authentication failure so the WebFlux handler returns a Bearer error. **Never manually Base64URL-decode the payload as a substitute for `ReactiveJwtDecoder`.**

### 7.1. JWT Authority Converter

JWT:

```json
{
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders:read orders:write",
  "exp": 1893456000
}
```

With the standard mapping, this produces:

```text
SCOPE_orders:read
SCOPE_orders:write
```

`scope` represents the scopes granted by the issuer and does not prove the subject can access every resource. In WebFlux, the JWT converter also follows a **reactive contract**. You can configure:

```java
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication
        .ReactiveJwtAuthenticationConverterAdapter;
import reactor.core.publisher.Mono;

Converter<Jwt, Mono<AbstractAuthenticationToken>>
        jwtAuthenticationConverter() {

    JwtGrantedAuthoritiesConverter authorities =
            new JwtGrantedAuthoritiesConverter();
    authorities.setAuthoritiesClaimName("scope");
    authorities.setAuthorityPrefix("SCOPE_");

    JwtAuthenticationConverter servletStyleConverter =
            new JwtAuthenticationConverter();
    servletStyleConverter.setJwtGrantedAuthoritiesConverter(authorities);

    return new ReactiveJwtAuthenticationConverterAdapter(
            servletStyleConverter);
}
```

The variable name `servletStyleConverter` simply reminds us that `JwtAuthenticationConverter` was designed around a synchronous interface; the adapter adapts its output for WebFlux. It does not require the application to run on the Servlet stack. Even though the converter returns `Mono`, **blocking work inside a synchronous converter does not magically become non-blocking** just by wrapping it with the adapter.

Register the converter in the DSL:

```java
.oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt ->
        jwt.jwtAuthenticationConverter(jwtAuthenticationConverter())))
```

Or when configuring the manager manually:

```java
JwtReactiveAuthenticationManager manager =
        new JwtReactiveAuthenticationManager(decoder);
manager.setJwtAuthenticationConverter(jwtAuthenticationConverter());
```

**These two wiring styles are architectural alternatives**, not something to configure side by side when the DSL already uses the proper bean/decoder/converter. Verify which manager the filter actually uses.

### 7.2. When I/O Is Needed to Compute Authorities

For example, suppose the application looks up tenant membership from a reactive database:

```text
Validated Jwt -> external identity
             -> reactive identity repository
             -> tenant-scoped authorities
             -> Authentication
```

Do not put a blocking JDBC query inside `JwtGrantedAuthoritiesConverter.convert` and expect the reactive adapter to solve it. Instead, implement a `Converter<Jwt, Mono<AbstractAuthenticationToken>>` that performs queries using a **reactive driver**, or offload legacy blocking work to an appropriately bounded and monitored scheduler.

Even when a JWT contains `role=admin`, policy must confirm that the claim is trusted and which API/tenant it applies to; never grant superuser privileges from uncontracted data.

## 8. Opaque Resource Server on WebFlux

Opaque tokens rely on the AS's OAuth 2.0 introspection endpoint.

### 8.1. application.yml

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.test/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

`INTROSPECTION_CLIENT_ID` and `INTROSPECTION_CLIENT_SECRET` are the credentials the **Resource Server uses to authenticate to the AS**, distinct from the client's Bearer access token. Secrets must come from a trusted secret manager or deployment channel and never be committed to Git.

### 8.2. SecurityWebFilterChain Using opaqueToken

```java
@Configuration
@EnableWebFluxSecurity
public class OpaqueWebFluxSecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders:read")
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.opaqueToken(Customizer.withDefaults()))
                .build();
    }
}
```

This is an **alternative** to the JWT chain in Section 6—not something to register alongside a JWT bean with the same `/**` matcher expecting Spring to inspect tokens and choose automatically. In WebFlux, Boot can auto-configure a `ReactiveOpaqueTokenIntrospector` from `opaquetoken.*` when no custom bean or DSL overrides it.

### 8.3. ReactiveOpaqueTokenIntrospector

Interface:

```java
public interface ReactiveOpaqueTokenIntrospector {
    Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
}
```

A common implementation:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.introspection
        .ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection
        .SpringReactiveOpaqueTokenIntrospector;

@Bean
ReactiveOpaqueTokenIntrospector introspector(
        @Value("${introspection.uri}") String uri,
        @Value("${introspection.client-id}") String id,
        @Value("${introspection.client-secret}") String secret) {

    return SpringReactiveOpaqueTokenIntrospector
            .withIntrospectionUri(uri)
            .clientId(id)
            .clientSecret(secret)
            .build();
}
```

The builder example reflects the API documented in current Spring Security WebFlux; older versions without the builder must use the constructor or HTTP client API supported in that version.

### 8.4. Introspection Response

Example AS response:

```json
{
  "active": true,
  "sub": "user-123",
  "client_id": "web-client",
  "aud": ["orders-api"],
  "scope": "orders:read orders:export",
  "exp": 1893456000
}
```

Metadata from the AS becomes the input for constructing the principal and authorities, typically:

```text
principal = OAuth2AuthenticatedPrincipal
authorities = [SCOPE_orders:read, SCOPE_orders:export]
Authentication = BearerTokenAuthentication
```

**HTTP 200 is not enough.** The AS may return:

```json
{"active": false}
```

when a token is expired, revoked, or unacceptable. The introspector must reject it and never construct a trusted principal.

## 9. OpaqueTokenReactiveAuthenticationManager

The reactive manager for opaque tokens:

```java
ReactiveAuthenticationManager opaqueAuthenticationManager(
        ReactiveOpaqueTokenIntrospector introspector) {
    return new OpaqueTokenReactiveAuthenticationManager(introspector);
}
```

`OpaqueTokenReactiveAuthenticationManager(ReactiveOpaqueTokenIntrospector)` is the primary constructor; the manager calls `introspect(rawToken)` and converts the result into an `Authentication`.

Pipeline:

```text
BearerTokenAuthenticationToken(rawValue)
    ↓
OpaqueTokenReactiveAuthenticationManager.authenticate(...)
    ↓
ReactiveOpaqueTokenIntrospector.introspect(rawValue)
    ↓
AS verifies introspection client credentials
    ↓
AS confirms active or inactive
    ↓
active=true -> principal + authorities -> BearerTokenAuthentication
active=false / timeout / auth error -> no authenticated principal
```

Unlike the JWT manager, the opaque manager **does not verify JWS signatures itself**. It trusts the result from the configured introspection endpoint and must honor that endpoint's contract.

### 9.1. Failed Client Credentials Differ from an Inactive Token

Do not confuse:

| Scenario | Source | Meaning |
| --- | --- | --- |
| AS returns `{"active":false}` with HTTP 200 | Access token state. | The caller's token is not active. |
| AS returns HTTP 401 when Resource Server calls introspection | Resource Server–AS credentials. | Introspection client secret, certificate, or permission may be wrong. |
| HTTP timeout, TLS failure, 503 | AS/network infrastructure. | Token cannot be verified; fail closed. |
| Token `active=true` but insufficient scope | Resource Server authorization. | Authentication may succeed, then the endpoint returns 403. |

Inside a reactive manager, **never** use `onErrorResume(error -> Mono.just(adminAuthentication))`. If the AS cannot confirm the token, the API must never mint a principal on its own.

### 9.2. Resource Binding and Audience

`active: true` does not automatically mean an access token is valid for **every API**. If the AS returns `aud`, the Resource Server can enforce an `orders-api` policy via a decorator:

```java
import java.util.Collection;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection
        .BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection
        .ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;

public final class AudienceCheckingReactiveIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;

    public AudienceCheckingReactiveIntrospector(
            ReactiveOpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        return delegate.introspect(token).flatMap(principal -> {
            Object raw = principal.getAttribute("aud");

            boolean allowed =
                    (raw instanceof String aud
                            && "orders-api".equals(aud))
                    || (raw instanceof Collection<?> audience
                            && audience.contains("orders-api"));

            return allowed
                    ? Mono.just(principal)
                    : Mono.error(new BadOpaqueTokenException(
                            "Access token is not for orders-api"));
        });
    }
}
```

The wrapper does not issue HTTP calls itself and does not create a principal when the delegate emits an error. It **fails closed** when the audience is missing. If the AS does not provide `aud` but guarantees that introspection credentials are scoped exclusively to tokens for this resource, document that guarantee; never drop audience policies merely because “the token is active”.

### 9.3. Customizing Authentication Conversion

Some Spring Security versions support `ReactiveOpaqueTokenAuthenticationConverter` on `OpaqueTokenReactiveAuthenticationManager`:

```java
OpaqueTokenReactiveAuthenticationManager manager =
        new OpaqueTokenReactiveAuthenticationManager(introspector);

manager.setAuthenticationConverter(customConverter);
```

`customConverter` must match the interface and method signature of your Spring Security version. It converts the introspected principal/attributes into an `Authentication`, optionally mapping authorities from metadata. If you only need to validate `aud` or issuer, an **introspector decorator** like the example above is clearer than transforming the authentication object.

Never use a converter to grant `ROLE_ADMIN` from a claim not guaranteed by the Authorization Server contract.

## 10. Choosing Between Managers: Do Not Rely on “Dots” in the Token

Some systems accept only JWTs, others only opaque tokens. Another system may accept **both** during a migration or for different resource categories.

**Unsafe:**

```java
// Do not guess the trust mechanism solely from the Bearer token's format.
boolean seemsJwt = rawToken.chars().filter(c -> c == '.').count() == 2;
return seemsJwt ? jwtManager : opaqueManager;
```

Because:

- Attackers control the token string sent in the request.
- JWTs can also be validated via introspection.
- Opaque tokens may contain dots.
- A token with an invalid JWT signature **must never automatically fall back** to a channel with weaker verification rules.
- Manager selection must reflect an agreed **trust domain** and **token profile**.

Choose the mechanism based on **dedicated API paths**, an **issuer allowlist**, or an explicit policy rather than sniffing the input string.

## 11. ReactiveAuthenticationManagerResolver for JWT and Opaque Tokens

Spring Security WebFlux supports `ReactiveAuthenticationManagerResolver<ServerWebExchange>` when selecting a manager at request time.

Suppose an API has two endpoint groups:

```text
/api/v2/**      → JWT access tokens
/api/legacy/**  → opaque access tokens
```

Build a resolver based on **paths defined in the API contract**:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication
        .ReactiveAuthenticationManagerResolver;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtReactiveAuthenticationManager;
import org.springframework.security.oauth2.server.resource.authentication
        .OpaqueTokenReactiveAuthenticationManager;
import org.springframework.security.oauth2.server.resource.introspection
        .ReactiveOpaqueTokenIntrospector;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Bean
ReactiveAuthenticationManagerResolver<ServerWebExchange> tokenManagerResolver(
        ReactiveJwtDecoder jwtDecoder,
        ReactiveOpaqueTokenIntrospector introspector) {

    ReactiveAuthenticationManager jwtManager =
            new JwtReactiveAuthenticationManager(jwtDecoder);

    ReactiveAuthenticationManager opaqueManager =
            new OpaqueTokenReactiveAuthenticationManager(introspector);

    return exchange -> {
        String path = exchange.getRequest()
                .getPath()
                .pathWithinApplication()
                .value();

        if (path.startsWith("/api/legacy/")) {
            return Mono.just(opaqueManager);
        }
        return Mono.just(jwtManager);
    };
}
```

Wiring it into a chain:

```java
@Bean
SecurityWebFilterChain apiSecurity(
        ServerHttpSecurity http,
        ReactiveAuthenticationManagerResolver<ServerWebExchange> resolver) {

    return http
            .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/api/legacy/**")
                        .hasAuthority("SCOPE_legacy:read")
                    .pathMatchers("/api/v2/**")
                        .hasAuthority("SCOPE_orders:read")
                    .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                    oauth2.authenticationManagerResolver(resolver))
            .build();
}
```

**This is an illustrative configuration when two genuinely independent token contracts exist.** Ensure remaining routes are not accidentally exposed and both managers enforce proper **issuer/resource/authority validators**.

### 11.1. Be Careful When Selecting by Path

- The path must be **server-controlled** and clearly mapped to the API; never trust a caller-supplied `X-Token-Type` header.
- With gateway or rewrite rules, verify whether `pathWithinApplication` and the chain matcher interpret the exact same URL.
- Never let `/api/legacy/` reach sensitive APIs requiring the new JWT policy.
- If both JWT and opaque tokens are needed **on the same endpoint**, design a strict resolver using a trusted issuer, client registration, or migration policy—never simply fall back after an authentication failure.
- Test that requests to unsupported routes are denied, not just the happy path.

### 11.2. Why Not Combine Two Managers with a Careless Fallback?

Bad example:

```java
return jwtManager.authenticate(authentication)
        .onErrorResume(error ->
                opaqueManager.authenticate(authentication));
```

A JWT with a bad signature or wrong issuer might be retried against the opaque endpoint under different constraints. In some providers, a token may exist and be active yet carry an audience for a different resource; such fallbacks easily weaken security boundaries.

If a migration genuinely requires validating two token types, enforce a **trusted discriminant and allowlist**, bind resource/issuer/audience on each manager, apply anti-confusion policies, and write negative tests for mismatched token types.

## 12. Multi-Issuer JWT: The Resolver Must Only Trust Allowlisted Issuers

When an API accepts JWTs from two Authorization Servers, Spring Security provides `JwtIssuerReactiveAuthenticationManagerResolver`.

```java
JwtIssuerReactiveAuthenticationManagerResolver resolver =
        JwtIssuerReactiveAuthenticationManagerResolver.fromTrustedIssuers(
                "https://idp-a.example.test/issuer",
                "https://idp-b.example.test/issuer");
```

Wiring the resolver into the WebFlux DSL:

```java
@Bean
SecurityWebFilterChain multiIssuerApi(ServerHttpSecurity http) {
    JwtIssuerReactiveAuthenticationManagerResolver resolver =
            JwtIssuerReactiveAuthenticationManagerResolver.fromTrustedIssuers(
                    "https://idp-a.example.test/issuer",
                    "https://idp-b.example.test/issuer");

    return http
            .authorizeExchange(exchanges -> exchanges
                    .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 ->
                    oauth2.authenticationManagerResolver(resolver))
            .build();
}
```

When selecting a manager, the system may inspect the **unverified** `iss` claim in the token to look up a candidate in the allowlist. That value is only a **routing hint**, not proof of trust. The selected manager/decoder must still verify the signature, issuer, audience, and claims.

**Do not do this:**

```java
// WRONG: creating a JWKS/issuer decoder for an arbitrary URL from an unverified token.
String issuerFromUnverifiedPayload = ...;
return ReactiveJwtDecoders.fromIssuerLocation(
        issuerFromUnverifiedPayload);
```

Risks include SSRF, fetching metadata/keys from attacker-controlled servers, memory/resource exhaustion, and accepting tokens from unapproved issuers.

### 12.1. Different Issuers May Have Different Profiles

Example:

```text
Issuer A:
  aud = orders-api
  scope = orders:read

Issuer B:
  aud = https://api.example.test/orders
  scp = ["orders.read"]
```

Do not merge scopes or audiences using substring matching. Each manager/decoder must enforce its exact contract and map into domain authorities via an allowlist. If two issuers assign different meanings to role names, prevent cross-issuer privilege escalation.

## 13. Reactive SecurityContext: Not Stored in ThreadLocal by Default

This is a foundational difference between WebFlux and Servlet.

In Servlet, code typically reads:

```java
SecurityContextHolder.getContext().getAuthentication();
```

In WebFlux, Reactor can switch execution across threads and uses **Reactor Context** to carry the security context with the subscription. Reactive code should read:

```java
Mono<Authentication> currentAuthentication =
        ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication);
```

Service example:

```java
public Mono<String> currentSubject() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
}
```

If you need subject and issuer from a JWT:

```java
public Mono<String> currentJwtSubject() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .flatMap(auth -> {
                Object principal = auth.getPrincipal();
                if (principal instanceof Jwt jwt) {
                    return Mono.justOrEmpty(jwt.getSubject());
                }
                return Mono.empty();
            });
}
```

The second snippet only applies when the pipeline holds a `JwtAuthenticationToken` whose `principal` is a `Jwt`; with opaque tokens, the principal is typically `OAuth2AuthenticatedPrincipal`. Applications using both mechanisms should define an explicit `CurrentActor` abstraction rather than casting every principal to `Jwt`.

### 13.1. Watch Out for Manual subscribe() and @Async

Never detach a security-sensitive operation via manual `subscribe()` from a controller expecting `SecurityContext` to automatically follow that subscription. A detached subscription may lack the request's Reactor Context and transaction context.

Undesirable example:

```java
// WRONG: fire-and-forget, losing control over context, errors, and security actions.
orderService.deleteOrder(orderId).subscribe();
return Mono.just(ResponseEntity.accepted().build());
```

Instead, **return the composed Mono/Flux** to the framework:

```java
return orderService.deleteOrder(orderId)
        .thenReturn(ResponseEntity.noContent().build());
```

For background jobs or queues, use dedicated actor/service identities, propagation, and independent authorization; never reuse an HTTP request's access token after it expires.

### 13.2. Security Context Does Not Turn a Token into Data Permissions

`Authentication.getName()` is the principal name produced by the converter, typically derived from `sub` or returned attributes. It is not automatically a **stable internal key** across all issuers. When reading orders, map the verified external identity to an internal user/service ID and enforce tenant/ownership constraints in queries.

## 14. Reactive Authorization: Scopes, Roles, and Object Ownership

In `SecurityWebFilterChain`, check:

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders:read")
    .pathMatchers(HttpMethod.POST, "/api/orders/**")
        .hasAuthority("SCOPE_orders:write")
    .anyExchange().authenticated())
```

However, `SCOPE_orders:read` only grants permission to perform read operations under the contract—it does not grant access to every order. A reactive service can combine method security scopes with query constraints:

```java
@Service
public class OrderService {
    private final ReactiveOrderRepository repository;
    private final ReactiveCurrentActor currentActor;

    public OrderService(ReactiveOrderRepository repository,
                        ReactiveCurrentActor currentActor) {
        this.repository = repository;
        this.currentActor = currentActor;
    }

    @PreAuthorize("hasAuthority('SCOPE_orders:read')")
    public Mono<OrderDto> getOrder(UUID orderId) {
        return currentActor.getAuthorizedActor()
                .flatMap(actor -> repository
                        .findByIdAndOwnerIdAndTenantId(
                                orderId,
                                actor.userId(),
                                actor.tenantId()))
                .map(OrderDto::from);
    }
}
```

`ReactiveOrderRepository`, `ReactiveCurrentActor`, `OrderDto`, and `getAuthorizedActor` are **hypothetical domain types/methods** that you implement yourself. `@PreAuthorize` in WebFlux requires **`@EnableReactiveMethodSecurity`** and calls going through the Spring proxy; method security is not enabled merely by having a `SecurityWebFilterChain`.

**Query-level filtering is a critical boundary** for multi-tenant data. Never return a `Flux<Order>` across all tenants and filter only with `@PostFilter` when you can constrain the query directly in the database.

## 15. Errors in the Reactive Pipeline and Bearer Responses

From an HTTP perspective, both JWT and opaque paths follow the Bearer error model, though internal causes differ.

| Scenario | Layer | Common HTTP Result |
| --- | --- | --- |
| No Bearer token sent to auth-required API | No credential yet. | **401 Unauthorized**, Bearer challenge. |
| Malformed Bearer header | Credential extraction. | **400 invalid_request** or error per resolver. |
| JWT bad signature/algorithm, expired, wrong iss/aud | `ReactiveJwtDecoder`. | **401 invalid_token**. |
| Opaque token introspection returns `active=false` | `ReactiveOpaqueTokenIntrospector`. | **401 invalid_token**. |
| Valid JWT or opaque token missing authority | Authorization WebFilter/method. | **403 Forbidden**, possibly `insufficient_scope`. |
| Valid token, user does not own resource | Domain policy. | **403 or 404** per API contract. |
| JWKS service or AS introspection unreachable | Dependency/network. | **Fail-closed**; HTTP status per handler/policy, potentially 5xx/503. |
| Invalid introspection client secret | AS rejects Resource Server. | No principal created; classify as operational error, do not conclude user token is revoked. |

Example for an invalid JWT:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

For a valid token missing a scope:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

These are common patterns, not a guarantee that every handler or custom gateway produces identical headers. In WebFlux, handlers such as `ServerBearerTokenAuthenticationEntryPoint` and `ServerBearerTokenAccessDeniedHandler` support Bearer responses. Do not mix them with Servlet handlers that have different APIs and namespaces.

### 15.1. Do Not Use onErrorResume to “Escalate Privileges”

Extremely dangerous example:

```java
return authenticationManager.authenticate(token)
        .onErrorResume(ex -> Mono.just(
                new UsernamePasswordAuthenticationToken(
                        "anonymous", "n/a",
                        AuthorityUtils.createAuthorityList("ROLE_ADMIN"))));
```

This is **fail-open**, turning an invalid-signature token or introspection timeout into an admin. Authentication paths must fail closed; if falling back to another mechanism is intentional, it requires a trusted contract and clear credential-type separation—**not** blindly trying a second manager on every error.

### 15.2. Do Not Leak Tokens or Internal Errors

When authentication fails, responses must never include raw JWTs, Bearer headers, introspection `client-secret`, internal JWKS URIs, `kid` inventories, or stack traces. Logs should use low-cardinality categories and correlation IDs. Never append `exception.getMessage()` directly into `WWW-Authenticate error_description`.

## 16. Reactive Does Not Mean Every Library Is Non-Blocking

Spring WebFlux uses non-blocking I/O, but custom code can break that property.

### 16.1. Anti-Patterns

```java
// 1. Blocking the Netty event loop.
Jwt jwt = reactiveJwtDecoder.decode(rawToken).block();

// 2. Calling synchronous RestTemplate inside reactive authentication.
return Mono.just(restTemplate.postForObject(url, request, Response.class));

// 3. Running blocking JDBC directly inside map().
return tokenMono.map(token -> jdbcTemplate.queryForObject(...));

// 4. Calling subscribe() manually and losing errors / context.
reactiveIntrospector.introspect(rawToken).subscribe();
```

Snippet 2 has an extra trap: `restTemplate.postForObject(...)` is evaluated **before** `Mono.just(...)`, meaning the blocking call executes eagerly when constructing the Mono.

### 16.2. When Calling a Blocking Library Is Unavoidable

If a legacy system only provides a synchronous `OpaqueTokenIntrospector`, you can build an **intentional** adapter, e.g.:

```java
ReactiveOpaqueTokenIntrospector adapter =
        token -> Mono.fromCallable(() -> blockingIntrospector.introspect(token))
                .subscribeOn(Schedulers.boundedElastic());
```

This is only a **transitional measure**, not true non-blocking I/O:

- The bounded elastic scheduler has thread/queue limits; high load can increase latency.
- Configure appropriate timeouts, capacity planning, tracing, and circuit breakers.
- Never allow unbounded executors or run blocking I/O on `Schedulers.parallel()`.
- Avoid holding HTTP request secrets on worker threads longer than necessary.
- Migrate to **`SpringReactiveOpaqueTokenIntrospector`/WebClient** or official reactive APIs whenever possible.

For databases, prefer R2DBC or an appropriate reactive driver, though you do not necessarily need to rewrite an entire system just to implement a single converter.

## 17. Choosing the Right Authentication and Principal Types

After the manager authenticates successfully:

| Authentication Path | Typical Authentication | Typical Principal |
| --- | --- | --- |
| JWT | `JwtAuthenticationToken` | `Jwt` |
| Opaque | `BearerTokenAuthentication` | `OAuth2AuthenticatedPrincipal` |

WebFlux controller example:

```java
@RestController
class ProfileController {

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(
            Mono<Authentication> authentication) {

        return authentication.map(auth -> Map.of(
                "authenticationType", auth.getClass().getSimpleName(),
                "principalName", auth.getName()));
    }
}
```

This example mainly illustrates retrieving the principal reactively, not recommending returning full principals or raw claims. In Spring WebFlux, you can also inject `Principal` or use `@AuthenticationPrincipal` via controller argument resolvers.

### 17.1. Same Name Does Not Mean Same User

For JWTs, `Authentication.getName()` typically uses `sub`; on the opaque path, it typically uses AS attributes. How names are extracted or normalized can change with converters. In multi-issuer systems and account linking, the business foreign key should be an **internal user ID** mapped from the verified external identity `(verified iss, verified sub)` or the corresponding service-identity contract.

Never merge accounts by email or `preferred_username` unless guaranteed unique and non-reassigned by contract.

## 18. Directly Testing JwtReactiveAuthenticationManager with StepVerifier

To separate **manager behavior** from the HTTP filter chain, you can unit test the manager using a decoder test double. The goal is to verify `Mono<Authentication>` emits success or error as expected.

```java
import static org.junit.jupiter.api.Assertions.assertTrue;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource
        .BearerTokenAuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtReactiveAuthenticationManager;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class JwtReactiveAuthenticationManagerTest {

    @Test
    void successfulDecoderProducesAuthenticatedJwtPrincipal() {
        Jwt jwt = Jwt.withTokenValue("signed-test-token")
                .header("alg", "RS256")
                .subject("user-123")
                .claim("scope", "orders:read")
                .issuedAt(Instant.parse("2030-01-01T00:00:00Z"))
                .expiresAt(Instant.parse("2030-01-01T01:00:00Z"))
                .build();

        ReactiveJwtDecoder decoder = token -> Mono.just(jwt);
        JwtReactiveAuthenticationManager manager =
                new JwtReactiveAuthenticationManager(decoder);

        Mono<Authentication> result = manager.authenticate(
                new BearerTokenAuthenticationToken("signed-test-token"));

        StepVerifier.create(result)
                .expectNextMatches(auth ->
                        auth.isAuthenticated()
                        && "user-123".equals(auth.getName())
                        && auth.getAuthorities().stream().anyMatch(
                                a -> "SCOPE_orders:read"
                                        .equals(a.getAuthority())))
                .verifyComplete();
    }
}
```

**Important:** `ReactiveJwtDecoder` in this test is a lambda **that always returns an in-memory Jwt**; it **does not actually verify signatures**, expiration, or issuer. This unit tests how the manager creates an authentication and maps authorities. To prove security, test a **real `NimbusReactiveJwtDecoder`** with a JWS JWT signed by a test key and production-like validators.

### 18.1. Testing Decoder Failure

```java
@Test
void failedJwtDecodeNeverProducesAuthentication() {
    ReactiveJwtDecoder decoder = token ->
            Mono.error(new BadJwtException("JWT is invalid"));

    JwtReactiveAuthenticationManager manager =
            new JwtReactiveAuthenticationManager(decoder);

    StepVerifier.create(manager.authenticate(
                    new BearerTokenAuthenticationToken("bad-token")))
            .expectError(AuthenticationException.class)
            .verify();
}
```

This snippet assumes `BadJwtException` and `AuthenticationException` are imported. In common Spring Security versions, the manager maps decoder errors to authentication failures. Tests should assert **no Authentication is emitted** and verify the appropriate exception type for your version without leaking raw tokens in error responses.

### 18.2. Do Not Assume a Manager Test Proves HTTP Status Codes

`StepVerifier` verifies reactive signals; it does not run:

- `AuthenticationWebFilter`.
- `SecurityWebFilterChain`.
- `AuthorizationWebFilter`.
- HTTP challenge / `WWW-Authenticate`.

Testing 401/403 requires a **WebTestClient integration test**.

## 19. Directly Testing OpaqueTokenReactiveAuthenticationManager

Using a fake introspector:

```java
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core
        .DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource
        .BearerTokenAuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication
        .OpaqueTokenReactiveAuthenticationManager;
import org.springframework.security.oauth2.server.resource.introspection
        .ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class OpaqueTokenReactiveAuthenticationManagerTest {

    @Test
    void activeResponseProducesAuthentication() {
        ReactiveOpaqueTokenIntrospector introspector = token ->
                Mono.just(new DefaultOAuth2AuthenticatedPrincipal(
                        "user-123",
                        Map.of("sub", "user-123",
                               "scope", List.of("orders:read")),
                        List.of(new SimpleGrantedAuthority(
                                "SCOPE_orders:read"))));

        var manager =
                new OpaqueTokenReactiveAuthenticationManager(introspector);

        StepVerifier.create(manager.authenticate(
                        new BearerTokenAuthenticationToken("opaque-test")))
                .expectNextMatches(auth ->
                        auth.isAuthenticated()
                        && "user-123".equals(auth.getName())
                        && auth.getAuthorities().stream().anyMatch(
                                a -> "SCOPE_orders:read"
                                        .equals(a.getAuthority())))
                .verifyComplete();
    }
}
```

The fake introspector returned a principal with `SCOPE_orders:read`. This test **does not prove** that the Spring HTTP introspector actually calls the AS, authenticates client credentials, checks `active`, or parses `scope` as in production. Those behaviors must be tested against a mock HTTP introspection server.

### 19.1. Testing Inactive/Error Cases

```java
ReactiveOpaqueTokenIntrospector inactive = token ->
        Mono.error(new BadOpaqueTokenException("inactive"));

OpaqueTokenReactiveAuthenticationManager manager =
        new OpaqueTokenReactiveAuthenticationManager(inactive);

StepVerifier.create(manager.authenticate(
                new BearerTokenAuthenticationToken("inactive-token")))
        .expectError(AuthenticationException.class)
        .verify();
```

Assumes `BadOpaqueTokenException` and `AuthenticationException` are properly imported. The goal is to ensure **no authenticated principal is produced** when the introspector rejects a token, rather than asserting an exact error message string from a particular minor version.

### 19.2. Testing Timeouts and Retry Mechanisms

A fake introspector can return:

```java
ReactiveOpaqueTokenIntrospector unavailable = token ->
        Mono.error(new OAuth2IntrospectionException(
                "AS introspection unavailable"));
```

The application must fail closed and classify dependency errors properly. If retries exist, bound retry count and duration, avoid endless credential resends, and never fall back to a privileged user when the `Mono` fails.

## 20. WebTestClient: Testing HTTP Behavior and the Filter Chain

`WebTestClient` is the appropriate tool for testing WebFlux HTTP responses. Combined with Spring Security Test, `SecurityMockServerConfigurers.mockJwt()` creates a **mock** JWT Authentication useful for testing **authorization**.

Example:

```java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockJwt;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive
        .AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class OrdersWebFluxAuthorizationTest {

    @Autowired
    WebTestClient client;

    @Test
    void readScopeMayAccessReadEndpoint() {
        client.mutateWith(mockJwt()
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_orders:read")))
                .get().uri("/api/orders")
                .exchange()
                .expectStatus().isOk();
    }

    @Test
    void missingReadScopeIsForbidden() {
        client.mutateWith(mockJwt()
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_orders:write")))
                .get().uri("/api/orders")
                .exchange()
                .expectStatus().isForbidden();
    }
}
```

This test assumes the `GET /api/orders` controller returns 200 when authorized and that `WebTestClient` is configured with Spring Security test support (many setups require `springSecurity()` when binding directly to an application context). `mockJwt()` **does not prove the decoder or introspection path** because authentication is mocked. When using `RANDOM_PORT` with a live server, test security mutator configuration can differ from binding to an application context; choose the right `WebTestClient` mode and apply Spring Security test integration per your project version.

### 20.1. Testing Real Bearer JWTs Directly

To test signatures, JWKS, issuer, audience, and `ReactiveAuthenticationManager` inside the chain:

1. Generate an RSA/EC test key pair; never use a production private key.
2. Stand up a mock JWKS endpoint or a decoder backed by the trusted test public key.
3. Configure issuer/audience validators just like production.
4. Sign a valid JWT with `scope=orders:read`.
5. Send `Authorization: Bearer <signed-test-JWS>` using `WebTestClient` (without `mockJwt()`).
6. Test invalid signatures, expired `exp`, wrong `iss`/`aud`, missing scopes, and malformed formats.
7. Verify 401 on authentication failure, 403 when authenticated without permissions, and 2xx when policy permits.

### 20.2. Testing Real Opaque Tokens via a Mock AS

For the opaque path:

1. Configure `SpringReactiveOpaqueTokenIntrospector` to point at a trusted mock introspection server.
2. Have the fake AS return `active=true` for `test-active-read` and `active=false` for `test-inactive`.
3. Have the fake AS return HTTP 401 when test introspection client credentials are wrong.
4. Assert POST request, Content-Type, Basic/client authentication, and the `token` form parameter.
5. Verify timeouts, 503s, and malformed responses create no principal and leak no tokens or secrets in errors.
6. Send real Bearer requests through the WebFlux `SecurityWebFilterChain`.

Do not simply construct a mock `OAuth2AuthenticatedPrincipal` and claim RFC 7662 HTTP behavior has been tested.

### 20.3. Integration Test Matrix

| Input | Expected Manager | Typical Outcome |
| --- | --- | --- |
| `/api/v2/orders` + JWT with valid signature, issuer, audience, scope | JWT | API processes normally. |
| `/api/v2/orders` + JWT with invalid signature | JWT | 401, no fallback to opaque. |
| `/api/v2/orders` + JWT with wrong audience | JWT | 401. |
| `/api/legacy/orders` + opaque `active=true`, valid scope | Opaque | API processes normally. |
| `/api/legacy/orders` + opaque `active=false` | Opaque | 401. |
| `/api/legacy/orders` + introspection timeout | Opaque | Fail-closed; dependency error per handler. |
| Valid JWT missing `orders:read` | JWT | 403 on read-protected endpoint. |
| Opaque `active=true` missing `legacy:read` | Opaque | 403 on read-protected endpoint. |
| JWT sent to opaque-only route | Opaque path | Accepted only if AS introspection and contract genuinely allow it; no auto-switching. |
| Opaque token sent to JWT route | JWT path | Rejected if not a valid JWT per decoder; no auto-switching. |
| JWT issuer not in allowlist | JWT resolver | Rejected without fetching arbitrary keys. |
| Same issuer but wrong API `aud` | Both paths per contract | Token rejected. |
| Valid token, user does not own order | Authorization/domain | 403 or 404 per policy. |

## 21. Performance and Reliability

Reactive authentication avoids holding threads while waiting on I/O if underlying components also support non-blocking execution. However:

| Operation | Operational Note |
| --- | --- |
| JWT signature verification | CPU-bound, potentially occurring on library-managed schedulers/threads; measure throughput and bound token size. |
| JWKS fetch/cache | Network-dependent on cache misses or key rotation; never fetch arbitrary `jku` URLs. |
| Opaque introspection | Can trigger an HTTP call per request; enforce timeouts, connection pooling, and AS capacity planning. |
| Revocation | Introspection reflects revocation faster than offline JWTs, though caching increases propagation delay. |
| Custom converter querying DB | Use a reactive repository or bounded/monitored legacy blocking scheduling. |
| Reactive context | Propagated across Reactor chains; avoid manual `subscribe()` and ThreadLocal assumptions. |
| Metrics | Count success, invalid tokens, and dependency errors without logging raw tokens or secrets. |

### 21.1. Intentional Caching

Successful opaque token introspection results may be cached by policy:

- TTL must not exceed `exp` or revocation SLA.
- Cache keys must protect raw tokens; never put tokens into logs or metrics.
- Distinguish issuer, resource, and client registration when caching for multi-tenant systems.
- An AS outage is never a reason to automatically accept unverified tokens.

For JWTs, JWKS caching caches **public key metadata**, which is different from caching an authentication decision for a specific token. Do not confuse the two cache types when assessing revocation risk.

### 21.2. Circuit Breakers Must Never Grant Access

If the introspection AS fails, a circuit breaker can shed load. It **cannot** manufacture a valid `Authentication`. Returning a safe HTTP 503 response may be preferable to letting every request generate stack traces and retry storms. Mapping exceptions to 503 must follow the application's Spring Security/HTTP handler policies and must not expose introspection client credentials.

## 22. Common Mistakes

### Mistake 1 — Using Servlet AuthenticationManager in WebFlux

`AuthenticationManager` returns `Authentication` synchronously; WebFlux needs `ReactiveAuthenticationManager` returning `Mono<Authentication>`. Do not use `.block()` as the primary bridge for every request.

### Mistake 2 — Confusing ReactiveJwtDecoder with JwtDecoder

`ReactiveJwtDecoder` differs from Servlet `JwtDecoder`. With the wrong bean type, the WebFlux DSL will not behave as expected; verify versions and WebFlux auto-configuration.

### Mistake 3 — Calling Synchronous OpaqueTokenIntrospector on the Event Loop

If a reactive introspector is unavailable, offload blocking calls to `boundedElastic` per policy or replace the implementation. Never call blocking HTTP clients directly inside `map()`.

### Mistake 4 — Trying the Opaque Manager Automatically When the JWT Manager Errors

This can introduce **token confusion** across trust domains. Only use the manager selected by contract or a safe resolver policy.

### Mistake 5 — Using an Unverified `iss` to Fetch Arbitrary JWKS

`iss` in an unverified JWT is attacker-controlled. Use an issuer allowlist, and ensure the selected decoder re-verifies issuer, signature, and audience.

### Mistake 6 — Thinking Mono.empty() Means Authentication Succeeded

Per the interface, empty means the manager made no decision; never grant an anonymous principal privileges simply because no error was thrown.

### Mistake 7 — Wrapping a JDBC or RestTemplate Call with Mono.just()

`Mono.just(restTemplate.exchange(...))` executes the blocking call eagerly before constructing the Mono. If legacy adaptation is necessary, use `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` with bounds and load testing.

### Mistake 8 — Reading SecurityContextHolder Inside Any Reactive Operator

ThreadLocal does not guarantee preserving the principal when Reactor switches threads. Use `ReactiveSecurityContextHolder` or inject the principal in WebFlux controllers.

### Mistake 9 — Using Scopes Alone and Skipping Object/Tenant Authorization

`SCOPE_orders:read` does not permit reading another user's orders. Queries must enforce owner/tenant constraints and policies.

### Mistake 10 — Mocking JWTs and Concluding Introspection/JWKS Works

`mockJwt()` and unit stubs bypass signature verification and AS HTTP calls. Write integration tests with signed JWTs or a mock introspection endpoint.

### Mistake 11 — Relying on `kid` in JWT Decoders as Proof of Trust

`kid` only selects a candidate key from a trusted JWKS. Never fetch keys from a host suggested by the token and never skip signature validation.

### Mistake 12 — Combining Multiple SecurityWebFilterChains with Overlapping Matchers Without Understanding Order

When multiple chains exist, Spring Security applies the matching chain by matcher/order; a broad chain can shadow a narrower chain. Test JWT and opaque endpoints to verify the intended resolver/manager runs.

## 23. Practical Scenarios

### Scenario A — Orders API Accepting Only JWTs

The Authorization Server issues JWS JWT access tokens with `aud=orders-api`. The WebFlux chain uses `.jwt()`, the decoder verifies signature/issuer/audience, the manager creates a `JwtAuthenticationToken`, and `hasAuthority("SCOPE_orders:read")` checks permissions before the service reads the user's order.

### Scenario B — Legacy API Accepting Only Opaque Tokens

The Authorization Server issues random access tokens, the Resource Server uses `.opaqueToken()`, and the introspector sends RFC 7662 requests using Resource Server credentials. `active=false` is rejected; `active=true` with valid scopes creates a principal and authorization runs.

### Scenario C — Migration Splitting JWT and Opaque Routes

`/api/v2/**` uses the JWT manager, `/api/legacy/**` uses the opaque manager. The resolver chooses strictly by path policy without sniffing tokens. Test mismatched token types on each route to confirm no unintended fallback occurs.

### Scenario D — Two JWT Issuers

The API trusts `https://idp-a.example.test` and `https://idp-b.example.test`. `JwtIssuerReactiveAuthenticationManagerResolver.fromTrustedIssuers(...)` selects a manager from the allowlist; each decoder must independently verify tokens and authorities without creating decoders for attacker-supplied issuers.

### Scenario E — JWKS Key Rotation Causes JWT 401s

A token uses a new `kid`; the JWKS cache has not updated or AS key publication lags. The Resource Server must refresh trusted JWKS per policy and monitor errors without letting tokens pass prior to signature verification.

### Scenario F — Introspection Timeout

The AS has not responded. The reactive pipeline must fail closed, avoiding `onErrorResume` creating a default principal. Operators investigate latency, HTTP errors, and client credentials instead of misdiagnosing every token as revoked.

### Scenario G — Context Lost on Manual subscribe()

A controller calls `subscribe()` manually to run work after returning 202; the security context can be lost and errors go unhandled. Design background workflows with separate actor identities and queues instead of extending a Bearer request's privileges indefinitely.

### Scenario H — JWT Has Scope but Wrong Tenant

Authentication succeeds and produces `SCOPE_orders:read`, yet the service must check `tenant_id` and owner mapping. A token with valid scope cannot read another tenant's orders; query-level isolation prevents data leakage.

## 24. Self-Check Questions

**1. What does `ReactiveAuthenticationManager.authenticate(...)` return?** `Mono<Authentication>`: success emits Authentication, unsupported may emit empty, failure emits an error.

**2. What is the reactive manager for JWTs named?** `JwtReactiveAuthenticationManager`, backed by `ReactiveJwtDecoder`.

**3. What is the reactive manager for opaque tokens named?** `OpaqueTokenReactiveAuthenticationManager`, backed by `ReactiveOpaqueTokenIntrospector`.

**4. Must the opaque manager only receive strings without dots?** No. It introspects tokens per contract, even if a token has JWT formatting.

**5. Why must `.block()` never be called in the WebFlux request path?** It can block the event loop, reduce throughput, and break reactive behavior.

**6. How does `ReactiveSecurityContextHolder` differ from `SecurityContextHolder`?** It retrieves the security context from the reactive subscription's Reactor Context rather than assuming Servlet's ThreadLocal is valid.

**7. Is a “valid JWT signature” enough for an API to accept a token?** No. You must also validate issuer, audience, timestamps, token profile, and permissions.

**8. Does opaque introspection returning `active=true` automatically grant access to every endpoint?** No. Resource/audience binding, scopes, and business logic still apply.

**9. Should you fall back from a JWT failure to the opaque manager?** Not by default; you need a trust contract and a safe selection mechanism rather than using fallback to ignore failures.

**10. Can a multi-issuer resolver trust any `iss` read from a token?** No. Use an issuer allowlist and ensure the decoder re-verifies the token.

**11. Does `Mono.empty()` mean valid credentials?** No; it only indicates the manager could not determine an authentication outcome.

**12. When a token is valid but missing a scope, what HTTP status is typical?** Typically 403; tokens rejected during authentication typically return 401.

**13. Why is a `StepVerifier` manager unit test insufficient on its own?** It does not exercise the WebFlux filter chain, Bearer challenge, or real JWT signature/HTTP introspection.

**14. Does `WebTestClient`'s `mockJwt()` verify JWTs?** No; it simulates authentication to test authorization rules.

**15. What if a custom converter must perform a blocking DB lookup?** Prefer a reactive repository; if legacy blocking is unavoidable, offload to `boundedElastic` with bounds and performance monitoring.

## 25. Official References

- **Spring Security Reference — Reactive OAuth 2.0 Resource Server JWT:** https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- **Spring Security Reference — Reactive OAuth 2.0 Resource Server Opaque Token:** https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html
- **Spring Security Reference — Reactive Resource Server Multi-tenancy:** https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/multitenancy.html
- **Spring Security Javadoc — ReactiveAuthenticationManager:** https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ReactiveAuthenticationManager.html
- **Spring Security Javadoc — JwtReactiveAuthenticationManager:** https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtReactiveAuthenticationManager.html
- **Spring Security Javadoc — OpaqueTokenReactiveAuthenticationManager:** https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/OpaqueTokenReactiveAuthenticationManager.html
- **Spring Security Reference — Reactive Security / Reactor Context:** https://docs.spring.io/spring-security/reference/reactive/integrations/concurrency.html
- **Spring Security Reference — WebFlux Testing:** https://docs.spring.io/spring-security/reference/reactive/test/index.html
- **RFC 6749 — OAuth 2.0 Authorization Framework:** https://www.rfc-editor.org/rfc/rfc6749
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** https://www.rfc-editor.org/rfc/rfc6750
- **RFC 7519 — JSON Web Token (JWT):** https://www.rfc-editor.org/rfc/rfc7519
- **RFC 7662 — OAuth 2.0 Token Introspection:** https://www.rfc-editor.org/rfc/rfc7662
- **RFC 8725 — JWT Best Current Practices:** https://www.rfc-editor.org/rfc/rfc8725
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** https://www.rfc-editor.org/rfc/rfc9068

**Conclusion:** A WebFlux Resource Server uses `ReactiveAuthenticationManager` to transform a Bearer credential into a `Mono<Authentication>` within a **reactive pipeline**. `JwtReactiveAuthenticationManager` relies on `ReactiveJwtDecoder` to verify JWTs; `OpaqueTokenReactiveAuthenticationManager` relies on `ReactiveOpaqueTokenIntrospector` to query the Authorization Server. Select managers using **token contracts and trust boundaries**, rather than guessing from string shape or falling back after rejection. Keep the pipeline **non-blocking and fail-closed**, propagate identity via **Reactor SecurityContext**, enforce audience/scope/tenant/ownership checks, and test both reactive signals and the HTTP filter chain to protect the API thoroughly.

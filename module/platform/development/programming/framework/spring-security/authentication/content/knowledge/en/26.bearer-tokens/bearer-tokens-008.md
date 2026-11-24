# JWT and Opaque Bearer Token Authentication Components in Spring Security WebFlux (Reactive)

## 1. Problem: Same Authorization: Bearer Header, Which Authentication Strategy?

In an **OAuth 2.0 Resource Server** built on **Spring WebFlux**, the client sends an access token in the header:

```http
GET /api/messages HTTP/1.1
Host: api.example.org
Authorization: Bearer <access-token>
```

The Resource Server must determine whether the token is valid and intended for this API, then construct an `Authentication` holding the principal and `GrantedAuthority` instances for authorization decisions.

There are two primary approaches:

- **JWT (JSON Web Token)**: the token is a decodable structure; the Resource Server verifies the signature and claims itself against trusted keys, then turns claims into principal and authorities. The central component is `ReactiveJwtDecoder`.
- **Opaque token**: the Resource Server treats the token as a string whose internal structure it does not need to know; it calls an **OAuth 2.0 Token Introspection Endpoint** provided by the Authorization Server, checks the `active` state, and retrieves attributes/permissions. The central component is `ReactiveOpaqueTokenIntrospector`.

**Note:** these are **two authentication strategies**, not merely two string formats. A JWT-formatted access token **can still be verified via introspection** when the system needs a live status decision at the Authorization Server (for example, near-real-time token/permission revocation). Spring Security's `opaqueToken()` configuration describes verification via introspection, not necessarily asserting that the token string lacks JWT structure.

### Key Design Questions

1. What kind of token is it, and what does the Authorization Server guarantee?
2. Should the Resource Server verify signatures/claims locally or query the Authorization Server per request?
3. Which principal is produced after authentication, and which scopes become `GrantedAuthority`?
4. Which permissions does the API require, and how are 401/403 handled?
5. Is the stack **WebFlux/reactive** or **Servlet**? Their corresponding APIs differ.

## 2. Reactive Processing Flow from HTTP Request to SecurityContext

```text
HTTP request + Authorization: Bearer ...
               |
               v
SecurityWebFilterChain (ServerHttpSecurity)
               |
               v
AuthenticationWebFilter
  -> ServerBearerTokenAuthenticationConverter
  -> BearerTokenAuthenticationToken (unauthenticated)
               |
               v
ReactiveAuthenticationManager.authenticate(authentication)
        |                               |
        v                               v
 JWT path                         Introspection path
 JwtReactiveAuthenticationManager  OpaqueTokenReactiveAuthenticationManager
        |                               |
 ReactiveJwtDecoder                  ReactiveOpaqueTokenIntrospector
  parse + verify signature            call Authorization Server introspection
  validate claims                     validate active/response
        |                               |
  Jwt + converter                  OAuth2AuthenticatedPrincipal + converter
        |                               |
 JwtAuthenticationToken              BearerTokenAuthentication
        +---------------+---------------+
                        |
                        v
   Reactive SecurityContext (Reactor Context) for the request
                        |
                        v
   AuthorizationWebFilter / @PreAuthorize / handler
                        |
                        v
   200 if authorized; 401 if unauthenticated;
   403 if authenticated but lacking permissions
```

The reference baseline here is **Spring Security 6.x**, with examples running on **Spring Boot 3.x, Java 17+**. The WebFlux class names and configurations below must not be confused with Servlet classes such as `BearerTokenAuthenticationFilter`, `JwtAuthenticationProvider`, `OpaqueTokenAuthenticationProvider`, `HttpSecurity`, and ThreadLocal-backed `SecurityContextHolder`.

### Key Classes and Responsibilities

| Reactive Component | Responsibility |
| --- | --- |
| `SecurityWebFilterChain` | Security filter chain for `ServerWebExchange` |
| `ServerHttpSecurity.oauth2ResourceServer(...)` | DSL enabling bearer resource server: choose `jwt(...)` or `opaqueToken(...)` |
| `ServerBearerTokenAuthenticationConverter` | Extracts bearer token from the request (defaults to `Authorization` header) |
| `BearerTokenAuthenticationToken` | Carries unauthenticated token string as input to the manager |
| `ReactiveAuthenticationManager` | Contract `Mono<Authentication> authenticate(Authentication)` |
| `JwtReactiveAuthenticationManager` | Calls decoder and converts `Jwt` into `Authentication` |
| `ReactiveJwtDecoder` | Decodes, verifies signatures, and applies validators to JWTs |
| `OpaqueTokenReactiveAuthenticationManager` | Calls introspector and creates `Authentication` from introspection data |
| `ReactiveOpaqueTokenIntrospector` | `Mono<OAuth2AuthenticatedPrincipal> introspect(String token)` |
| `ReactiveJwtAuthenticationConverterAdapter` | Adapts a synchronous JWT converter to the reactive converter contract |
| `ReactiveSecurityContextHolder` | Reads `SecurityContext` from the Reactor Context in the current pipeline |

**`ReactiveAuthenticationManager` contract:** a `Mono` emitting `Authentication` on success; may return `Mono.empty()` if the manager cannot decide for the input; returns `Mono.error(...)` if authentication fails. Invoking the method and discarding the publisher will not execute the side effects represented by the publisher.

**Never call `block()` inside a WebFlux request handler or filter** to wait on the decoder/introspector; doing so can block the event loop. The framework wires the `Mono` into the pipeline automatically.

## 3. JWT: Components and Verification Chain

### 3.1. ReactiveJwtDecoder

Core API:

```java
public interface ReactiveJwtDecoder {
    Mono<Jwt> decode(String token) throws JwtException;
}
```

The snippet above only shows the interface signature; it is not a standalone Java file. `ReactiveJwtDecoder` is usually auto-configured by Spring Boot when `spring.security.oauth2.resourceserver.jwt.issuer-uri` is set. The common implementation is `NimbusReactiveJwtDecoder`.

When receiving a valid JWT, the resource server can:

1. Parse the JWS/JWT structure, enforce an algorithm on the trusted allowlist, and select the matching signing key from the configured JWK Set or public key.
2. **Verify the signature** (never just Base64-decode the payload and trust claims).
3. Validate `exp`, `nbf`, and `iss` with configured validators. With standard `issuer-uri`, Spring Security includes an issuer validator.
4. **Verify audience (`aud`), token type, and application constraints if required by business rules**. Never assume signature and issuer verification suffice for every API.
5. Convert the decoded `Jwt` into a `JwtAuthenticationToken` via a converter, defaulting principal name to `sub` (if present) and mapping scopes to `SCOPE_...` authorities.

A JWT is a bearer token: anyone holding a valid token can use it within its permitted scope. HTTPS, keeping tokens secret, TTLs, revocation strategies, and replay defenses are responsibilities of the overall design.

### 3.2. JwtReactiveAuthenticationManager

The JWT manager takes a `BearerTokenAuthenticationToken`, passes the token string to `ReactiveJwtDecoder`, and applies a converter to produce `JwtAuthenticationToken`. These two classes are not interchangeable: the decoder handles verification and claim parsing, while the manager completes **Spring Authentication**.

```text
BearerTokenAuthenticationToken("eyJ...") 
  -> JwtReactiveAuthenticationManager
  -> ReactiveJwtDecoder.decode(token)
  -> Jwt(header + validated claims)
  -> JWT AuthenticationConverter
  -> JwtAuthenticationToken
        principal = Jwt
        authorities = [SCOPE_message:read, ...]
```

With example claims:

```json
{
  "iss": "https://idp.example.org/issuer",
  "sub": "user-42",
  "aud": ["message-api"],
  "scope": "message:read message:write",
  "exp": 1999999999
}
```

If the token is genuinely issued and passes verification, standard scopes map to `SCOPE_message:read` and `SCOPE_message:write`. The JSON above illustrates claims only; **it is not a signed JWT** and cannot be used as a real bearer token.

### 3.3. JWK Rotation and Decoder Configuration

When the Resource Server knows `issuer-uri`, Spring Security can use the issuer's discovery metadata to locate the JWK Set, then fetch and refresh public keys as needed. Never load a single static public key assuming the Authorization Server will never rotate keys.

If configuring **only `jwk-set-uri`** without a corresponding issuer validator, explicitly check whether `iss` is verified. A configuration combining issuer and JWK Set URI can retain the issuer check while pinning the key endpoint explicitly.

With multiple issuers/tenants, never take a client-supplied `iss` value and trust arbitrary issuers. The resolver/decoder must constrain the allowed issuer set before performing discovery and processing tokens.

## 4. Opaque Token: Components and Introspection

### 4.1. ReactiveOpaqueTokenIntrospector

This is the interface responsible for querying the Authorization Server about a token:

```java
public interface ReactiveOpaqueTokenIntrospector {
    Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
}
```

This is a simplified signature to explain the API. Spring Security 6.x provides `SpringReactiveOpaqueTokenIntrospector` to connect to the endpoint using configured client credentials and interpret the result.

An introspection request sends the access token to a secured Authorization Server endpoint. Example response:

```json
{
  "active": true,
  "sub": "user-42",
  "client_id": "frontend",
  "scope": "message:read message:write",
  "exp": 1999999999
}
```

`active: true` is the Authorization Server's decision per the introspection standard. If the token is invalid, expired, revoked, or unauthorized to inspect, the server may return `active: false` or an appropriate error; the resource server **must not continue treating the token as valid**.

### 4.2. OpaqueTokenReactiveAuthenticationManager

The manager takes a `BearerTokenAuthenticationToken`, calls `ReactiveOpaqueTokenIntrospector.introspect(...)`, and creates a `BearerTokenAuthentication` containing an `OAuth2AuthenticatedPrincipal` and `GrantedAuthority` instances.

```text
BearerTokenAuthenticationToken("token-value")
  -> OpaqueTokenReactiveAuthenticationManager
  -> ReactiveOpaqueTokenIntrospector.introspect(token)
  -> OAuth2AuthenticatedPrincipal(attributes, authorities)
  -> BearerTokenAuthentication
        principal = OAuth2AuthenticatedPrincipal
        authorities = [SCOPE_message:read, ...]
```

Under standard configuration, Spring Security reads scopes from the introspection response and adds the `SCOPE_` prefix. If the Authorization Server returns custom claims for roles/permissions, customize the introspector or converter per your trust contract with that server.

**Operational difference:** introspection usually requires a network call to the Authorization Server per authentication, so latency, timeouts, rate limits, and endpoint availability affect the API. Caching can reduce overhead but introduces a delay in detecting revoked tokens. Choose TTL/caching based on risk, never assuming opaque tokens are "always immediately up to date" if caching or delayed AS revocation exists.

### 4.3. Opaque Tokens Still Require Audience Checking

Even if introspection returns `active=true`, the Resource Server still needs to confirm **the token is intended for this resource** per `aud`, `client_id`, `resource`, or Authorization Server policy. A token issued for another API must not be accepted just because it is active. Audience enforcement may be performed by the Authorization Server via client/introspection policy and/or internal checks; verify it explicitly.

## 5. Spring Boot WebFlux Project Using JWT

Create a Spring Boot 3.x, Java 17+ application with **Spring Reactive Web** and **OAuth2 Resource Server**. With Gradle, required dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
```

The Resource Server starter includes the components for JWT/JOSE. If declaring individual Spring Security modules instead of the starter, JWT requires both `spring-security-oauth2-resource-server` **and** `spring-security-oauth2-jose`.

Create **`src/main/java/demo/JwtApiApplication.java`**:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
@RestController
public class JwtApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(JwtApiApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public/ping").permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/messages")
                            .hasAuthority("SCOPE_message:read")
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }

    @GetMapping("/public/ping")
    Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/api/messages")
    Mono<String> readMessages(@AuthenticationPrincipal Jwt jwt) {
        return Mono.just("message for " + jwt.getSubject());
    }
}
```

Create **`src/main/resources/application.yml`**:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org/issuer
```

**Steps to run:** replace the issuer with a real OIDC/OAuth2 issuer exposing metadata/JWKS and properly signed tokens. Run `./gradlew bootRun` (Windows: `gradlew.bat bootRun`) inside the Boot project. Command:

```bash
curl -s http://localhost:8080/public/ping
```

Returns exact body:

```text
pong
```

A **real** JWT access token issued for the API with scope `message:read` can be tested via:

```bash
curl -i -H "Authorization: Bearer <VALID_ACCESS_TOKEN>" \
  http://localhost:8080/api/messages
```

`<VALID_ACCESS_TOKEN>` is a placeholder to replace, not a runnable sample token. Once validated and authorized, the response is `message for user-42` when `sub=user-42`; if the token is missing or invalid, access to the protected route is denied.

**Goal of this example:** use `.oauth2ResourceServer(...jwt...)` DSL so the framework configures the bearer filter/manager automatically, inject the verified `Jwt` principal into the handler, and restrict authorization by scope. Never decode payloads via Base64 manually in the controller.

## 6. Switching to Opaque Introspection (Same API, Different Verification Path)

To build **a separate opaque resource server project**, keep the dependencies and `/public/ping` endpoint as before, and replace the JWT config in `apiSecurity` with:

```java
@Bean
SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/public/ping").permitAll()
                    .pathMatchers(HttpMethod.GET, "/api/messages")
                        .hasAuthority("SCOPE_message:read")
                    .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                    .opaqueToken(Customizer.withDefaults()))
            .build();
}
```

Update the endpoint principal because the authenticated principal type differs from JWT:

```java
@GetMapping("/api/messages")
Mono<String> readMessages(
        @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
    return Mono.just("message for " + principal.getName());
}
```

Add import `org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal`. These are **replacements** for the previous methods; do not keep duplicate `@Bean apiSecurity` or `@GetMapping` methods in the same class.

Switch **`application.yml`** to introspection:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.org/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

Supply `INTROSPECTION_CLIENT_ID` and `INTROSPECTION_CLIENT_SECRET` via environment variables, deploy an Authorization Server supporting introspection, and configure HTTPS and endpoint access. **Never hard-code secrets in the repo or logs.**

When the resource server introspects a token and observes `active=true` with scope `message:read`, `/api/messages` is permitted. Inactive tokens or failed introspection are rejected. On this route, the resulting `Authentication` is `BearerTokenAuthentication`, and `@AuthenticationPrincipal` receives the `OAuth2AuthenticatedPrincipal` from introspection.

### Declaring the Introspector Explicitly When Needed

If you prefer not to rely on property auto-configuration, Spring Security 6.5 supports a bean:

```java
@Bean
ReactiveOpaqueTokenIntrospector opaqueTokenIntrospector() {
    return SpringReactiveOpaqueTokenIntrospector
            .withIntrospectionUri("https://idp.example.org/oauth2/introspect")
            .clientId(introspectionClientId)
            .clientSecret(introspectionClientSecret)
            .build();
}
```

This is a **configuration fragment**; `introspectionClientId` and `introspectionClientSecret` must be injected from secure configuration, not undefined Java variables. Imports:

```java
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;
```

Use one consistent source for configuring the introspector; if you also pass a custom `introspector()` in the DSL, Boot's default bean may no longer be used.

## 7. Unit Testing Both ReactiveAuthenticationManagers Without an IdP

This is a **unit test of the conversion contract**. It uses a fake decoder/introspector and therefore **does not prove JWT signature verification or network introspection**. Its goal is verifying that each manager accepts a bearer token input, emits `Mono<Authentication>`, returns the expected Authentication type and authorities, and rejects invalid inputs.

In a Boot project with the dependencies from section 5, create **`src/test/java/demo/ReactiveManagerTest.java`**:

```java
package demo;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication.JwtReactiveAuthenticationManager;
import org.springframework.security.oauth2.server.resource.authentication.OpaqueTokenReactiveAuthenticationManager;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReactiveManagerTest {

    private static boolean hasScope(
            Iterable<? extends GrantedAuthority> authorities, String scope) {
        for (GrantedAuthority authority : authorities) {
            if (authority.getAuthority().equals("SCOPE_" + scope)) {
                return true;
            }
        }
        return false;
    }

    @Test
    void jwtManagerValidatesViaDecoderThenCreatesJwtAuthentication() {
        ReactiveJwtDecoder fakeDecoder = token -> {
            if (!"sample-jwt".equals(token)) {
                return Mono.error(new BadJwtException("Rejected demo JWT"));
            }
            // This Jwt is a fixture; it has no real cryptographic signature.
            Jwt jwt = Jwt.withTokenValue(token)
                    .header("alg", "RS256")
                    .claim("sub", "alice")
                    .claim("scope", "message:read")
                    .build();
            return Mono.just(jwt);
        };

        var manager = new JwtReactiveAuthenticationManager(fakeDecoder);

        StepVerifier.create(manager.authenticate(
                        new BearerTokenAuthenticationToken("sample-jwt")))
                .assertNext(authentication -> {
                    assertInstanceOf(JwtAuthenticationToken.class, authentication);
                    assertEquals("alice", authentication.getName());
                    assertTrue(hasScope(authentication.getAuthorities(), "message:read"));
                })
                .verifyComplete();

        StepVerifier.create(manager.authenticate(
                        new BearerTokenAuthenticationToken("wrong-jwt")))
                .expectError()
                .verify();
    }

    @Test
    void opaqueManagerIntrospectsThenCreatesBearerAuthentication() {
        ReactiveOpaqueTokenIntrospector fakeIntrospector = token -> {
            if (!"sample-opaque".equals(token)) {
                return Mono.error(new BadOpaqueTokenException("Inactive token"));
            }
            return Mono.just(new DefaultOAuth2AuthenticatedPrincipal(
                    "bob",
                    Map.of(
                            "sub", "bob",
                            "scope", List.of("message:read")),
                    List.of(new SimpleGrantedAuthority("SCOPE_message:read"))));
        };

        var manager = new OpaqueTokenReactiveAuthenticationManager(
                fakeIntrospector);

        StepVerifier.create(manager.authenticate(
                        new BearerTokenAuthenticationToken("sample-opaque")))
                .assertNext(authentication -> {
                    assertInstanceOf(BearerTokenAuthentication.class, authentication);
                    assertEquals("bob", authentication.getName());
                    assertTrue(hasScope(authentication.getAuthorities(), "message:read"));
                })
                .verifyComplete();

        StepVerifier.create(manager.authenticate(
                        new BearerTokenAuthenticationToken("wrong-opaque")))
                .expectError()
                .verify();
    }
}
```

Run `./gradlew test --tests demo.ReactiveManagerTest` (Windows: `gradlew.bat test --tests demo.ReactiveManagerTest`). Both tests are expected to **PASS** on compatible Spring Security 6.x/Boot 3.x versions. `StepVerifier` subscribes/awaits publisher completion and asserts emitted values or errors; never use `block()` in WebFlux handlers.

**Intentional limitation:** the JWT fixture replaces signature verification with a fake decoder, and the introspection fixture supplies attributes directly. Thus `sample-jwt`/`sample-opaque` **must never be sent to real systems**, and these two unit tests do not replace integration tests against JWK/introspection endpoints. End-to-end tests must verify URL, issuer, audience, signature, active state, permissions, and HTTP responses.

## 8. Customizing Claims/Attributes-to-GrantedAuthority Mapping

### 8.1. JWT Authority Converter

Spring Security 6.x typically reads scope claims like `scope` or `scp` and creates `SCOPE_message:read`. If the provider uses a different claim such as `permissions`, specify an explicit converter.

Configuration snippet (inside a `@Configuration` class, replacing `jwt(Customizer.withDefaults())` with `jwt(jwt -> jwt.jwtAuthenticationConverter(...))`):

```java
Converter<Jwt, Mono<AbstractAuthenticationToken>> jwtAuthoritiesConverter() {
    var claimsToAuthorities = new JwtGrantedAuthoritiesConverter();
    claimsToAuthorities.setAuthoritiesClaimName("permissions");
    claimsToAuthorities.setAuthorityPrefix("");

    var authenticationConverter = new JwtAuthenticationConverter();
    authenticationConverter.setJwtGrantedAuthoritiesConverter(
            claimsToAuthorities);

    return new ReactiveJwtAuthenticationConverterAdapter(authenticationConverter);
}

// Inside SecurityWebFilterChain DSL:
// .oauth2ResourceServer(oauth2 -> oauth2
//     .jwt(jwt -> jwt.jwtAuthenticationConverter(jwtAuthoritiesConverter())))
```

Required imports:

```java
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtAuthenticationConverterAdapter;
import reactor.core.publisher.Mono;
```

In this example, if the claim is:

```json
{ "permissions": ["REPORT_READ", "REPORT_WRITE"] }
```

then the authorities become `REPORT_READ` and `REPORT_WRITE` (**without** `SCOPE_`). Authorization must then use `hasAuthority("REPORT_READ")`, not `hasRole("REPORT_READ")` or `SCOPE_REPORT_READ`. This is a policy change; verify issuer/audience trust and guard against overly broad token claims before applying it.

`ReactiveJwtAuthenticationConverterAdapter` is appropriate when the wrapped converter performs **no blocking I/O**. If external DB/permission lookups are needed, implement a genuinely reactive converter; never invoke blocking JPA/JDBC directly on the event loop.

### 8.2. Opaque Token Authority Customization

With introspection, `ReactiveOpaqueTokenIntrospector` returns an `OAuth2AuthenticatedPrincipal` with `getAttributes()` and `getAuthorities()`. You can wrap the introspector to adjust authorities **after the delegate verifies token status**:

```java
ReactiveOpaqueTokenIntrospector withApplicationRole(
        ReactiveOpaqueTokenIntrospector delegate) {

    return token -> delegate.introspect(token).map(principal -> {
        // Demo policy: keep only authorities already verified by delegate.
        var authorities = List.copyOf(principal.getAuthorities());
        return new DefaultOAuth2AuthenticatedPrincipal(
                principal.getName(),
                principal.getAttributes(),
                authorities);
    });
}
```

Imports for the snippet above:

```java
import java.util.List;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
```

This snippet only shows **where to customize**; it adds no new permissions. To add internal roles, map from **verified** attributes against a trusted authority store/allowlist, handling tenants and failing closed on errors. Never trust an arbitrary `groups` string from a token or client to grant admin privileges.

In versions supporting `ReactiveOpaqueTokenAuthenticationConverter`, that is also an extension point to build `Authentication` from introspection results. Use it only when changing the principal/token type itself; configuring the introspector usually suffices for loading claims/authorities.

## 9. Token Failures, 401, and 403

Three cases carry distinct meanings:

| Scenario | Typical Expectation |
| --- | --- |
| No bearer token sent to protected endpoint | 401 Unauthorized and Bearer challenge (per exception handling config) |
| Invalid, expired, bad-signature/issuer/audience token, or inactive introspection | 401; no authenticated principal created |
| Token authenticates, missing `SCOPE_message:read` | 403 Forbidden; valid authentication, insufficient permission |
| No token, accessing `permitAll()` endpoint | Usually processed without requiring a token |
| Sending an **invalid** bearer token to a `permitAll()` endpoint | Filter may still attempt to authenticate the sent token; do not assume bad tokens are ignored on public routes |

Spring Security Resource Server uses standard Bearer error responses and may emit `WWW-Authenticate: Bearer ...` headers depending on the error. Do not hardcode error body assertions unless the application configures custom response handlers.

**Distinguish introspection network failures from rejected tokens:** if the AS is unreachable or times out, never "allow through" by default. Add monitoring and bounded retry/circuit-breaker policies; when unable to verify a token, fail closed. External system errors may return a status other than 401 depending on handlers/config; avoid claiming every introspection failure always returns 401.

## 10. Statelessness, SecurityContext, and Reactor Context

An API using only `Authorization: Bearer` usually expects **each request to prove identity independently**, without maintaining a browser login session.

- `ReactiveSecurityContextHolder` stores the context in the **Reactor Context** along the request pipeline, avoiding Servlet-style ThreadLocal `SecurityContextHolder`.
- `ServerSecurityContextRepository` is the abstraction for loading/saving context across requests; a stateless strategy can use `NoOpServerSecurityContextRepository.getInstance()`.
- If the system has other login flows using `WebSession`, or uses request caches/CSRF/stateful features, adding a JWT resource server **does not automatically make the whole app stateless**.
- A successful JWT/opaque request typically authenticates only that request; subsequent requests must provide a fresh/unexpired token. Never replace bearer tokens with custom session cookies without an explicit security design.
- Inside reactive handlers/filters, read the context with `ReactiveSecurityContextHolder.getContext()` or accept the principal via a Spring Security-injected argument.

Reactive method example reading name and authority count:

```java
// Method snippet in @RestController, requires Reactor Context populated by filters.
@GetMapping("/api/current-user")
Mono<String> currentUser() {
    return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication())
            .map(auth -> auth.getName() + ":" + auth.getAuthorities().size());
}
```

Add import `org.springframework.security.core.context.ReactiveSecurityContextHolder`. This illustrates code in a Spring WebFlux app with an appropriate security chain, not a standalone Java program.

## 11. Operational Comparison of JWT and Introspection

| Criterion | Local JWT Verification | Introspection / Opaque Strategy |
| --- | --- | --- |
| Verification component | `ReactiveJwtDecoder` | `ReactiveOpaqueTokenIntrospector` |
| Manager | `JwtReactiveAuthenticationManager` | `OpaqueTokenReactiveAuthenticationManager` |
| Produced Authentication | `JwtAuthenticationToken` | `BearerTokenAuthentication` |
| Common principal | `Jwt` | `OAuth2AuthenticatedPrincipal` |
| Permission data | Claims in verified JWT, converter | Introspection attributes/authorities, converter |
| Call Authorization Server per auth? | Typically no, except discovery/JWK refresh or custom logic | Typically yes; caching is a separate choice |
| Revocation responsiveness | Per TTL/denylist/custom revalidation | Can observe new status on next introspection; depends on AS and cache |
| Operational weaknesses | Wrong audience/trust, JWK rotation, overly long token TTL | Network latency, endpoint downtime, credentials/timeouts/rate limits |
| Best fit | Distributed APIs, high throughput, offline verification | Centralized token status control, tokens shouldn't expose claims directly |

**Selection rule:** weigh revocation requirements, latency, sensitive data exposure, scalability, trust model, and Authorization Server control. Never choose JWT just because it seems "modern," nor assume opaque is "more secure" in every scenario.

## 12. Common Implementation Mistakes

**(1) Confusing Servlet with WebFlux.** Copying `HttpSecurity`, `BearerTokenAuthenticationFilter`, `JwtAuthenticationProvider`, or `OpaqueTokenAuthenticationProvider` into a reactive app. Use `ServerHttpSecurity`, `SecurityWebFilterChain`, and the matching `*ReactiveAuthenticationManager` classes.

**(2) Base64-decoding a JWT and trusting unverified claims.** The decoder must verify JWS signature/alg/key and validators. A decoded JWT is not an authenticated JWT.

**(3) Configuring only `jwk-set-uri` and forgetting issuer/audience.** Ensure validation of the right issuer, `aud`, and API token-type policies; a valid signature from a multi-resource issuer does not prove the token belongs to this API.

**(4) Sending an OIDC ID Token to an API as a Bearer access token.** OIDC ID Tokens serve the client/RP for user login; a Resource Server normally needs an **access token** targeting the right audience.

**(5) Forgetting the `SCOPE_` prefix.** Scope `message:read` converts by default to `SCOPE_message:read`. `hasRole("message:read")` checks `ROLE_message:read` and fails to match.

**(6) Assuming opaque introspection eliminates all revocation risk.** Token status still depends on the Authorization Server, caches, timeouts, and check frequency. Test revocation behavior explicitly.

**(7) Writing a custom converter that calls `block()` on the event loop.** Reactive pipelines must stay `Mono`/`Flux` using `flatMap` and non-blocking HTTP; if blocking libraries are unavoidable, isolate them on an appropriate scheduler and monitor metrics.

**(8) Calling `ReactiveJwtDecoder.decode(token)` without subscribing or chaining the publisher.** `Mono` is lazy; returning or ignoring an unconsumed publisher skips validation.

**(9) Using ThreadLocal `SecurityContextHolder.getContext()` in reactive handlers.** Security context will not follow ThreadLocal across reactive operators. Use `ReactiveSecurityContextHolder`.

**(10) Putting bearer tokens in URL query parameters or logging raw tokens.** The `Authorization` header is the standard transport; URL tokens leak via browser history, proxies, and logs. Redact sensitive values in logs/metrics/traces.

**(11) Letting the client pick redirect or introspection URIs arbitrarily.** Introspection endpoints and issuer/JWK URLs must be managed/allowlisted. Never pass untrusted input into server-side outbound URLs causing SSRF.

**(12) Enabling both `jwt()` and `opaqueToken()` in one chain expecting auto-detection by string shape.** Pick one strategy per chain, or design a `ReactiveAuthenticationManagerResolver<ServerWebExchange>` with explicit policy when truly supporting multiple issuers/token types. Never classify tokens merely by "has two dots" to bypass validators.

**(13) Testing only status 200 and skipping negative tests.** Test missing tokens, malformed tokens, wrong `alg`, wrong issuer/audience, expired, not-before, inactive introspection, AS downtime, missing scope, and cross-tenant access.

**(14) Using a client's refresh token as an Authorization bearer token.** Refresh tokens belong at the token endpoint, never on resource server requests. Never log them or forward them to downstream APIs.

**(15) Forgetting to separate identity from permission.** `sub` identifies the token's subject; `scope`/`scp` lists permissions granted in a context. Business endpoints may still need account/tenant/resource-ownership checks.

## 13. Suggested Integration Test Scenarios

| Test | JWT | Opaque |
| --- | --- | --- |
| Valid token with `message:read` | 200; `JwtAuthenticationToken` | 200; `BearerTokenAuthentication` |
| Valid token with only `message:write` | 403 | 403 |
| No token on protected route | 401 | 401 |
| Expired token or invalidated by AS | Decoder rejects per `exp`/policy | Introspection `active=false`, rejected |
| Token signed by unknown issuer/keys | Signature/issuer rejected | AS does not recognize token |
| Right issuer, wrong `aud` | Needs aud validator, rejected | Needs introspection/policy enforcing audience, rejected |
| JWK rotated | Decoder fetches new key per policy | Independent of local JWK if using introspection only |
| AS downtime | Local JWT can continue if keys/metadata cached and policy permits | Introspection cannot verify => fail closed |
| Token revoked while `exp` still valid | Needs TTL/revocation plan | Next introspection can return inactive |
| Missing/duplicate Authorization headers | Ensure converter handles per RFC | Same |
| WebFlux request spanning multiple Reactor operators | `ReactiveSecurityContextHolder` preserves authentication | Same |

With `WebTestClient`, you can test statuses and routes using Spring Security test mock authentication helpers. However, **mock JWT/opaque** helpers test only authorization and controllers; true integration tests must send real tokens verified by the real decoder/introspector or an appropriate test IdP.

## 14. Deployment Checklist

1. Determine token format/validation strategy; choose **JWT decoding** or **opaque introspection** per Authorization Server contract.
2. Use `spring-boot-starter-webflux` and `spring-boot-starter-oauth2-resource-server`; configure `SecurityWebFilterChain` via `ServerHttpSecurity`.
3. For JWTs: validate issuer, signature, allowed algs, `exp`/`nbf`, audience, and type/tenant as required; ensure JWK rotation works.
4. For introspection: secure client secrets, HTTPS, timeouts, monitoring, cache/revocation policy, and check `active`/resource context.
5. Standardize `GrantedAuthority` and `hasAuthority`/`hasRole` rules; never grant admin roles from unmanaged claims.
6. Ensure API authorization includes both permissions and ownership/tenant constraints if required by business rules.
7. Never log bearer tokens; enforce HTTPS, configure client-appropriate CORS, and avoid passing tokens in query strings.
8. Keep the pipeline reactive; never use ThreadLocal or blocking I/O on the event loop.
9. Run manager/converter unit tests and real integration tests covering positive/negative cases and IdP outages.
10. Monitor 401/403 counts, introspection latency, JWK fetch failures, and token validator failures without exposing secrets.

### Official Documentation

- Spring Security 6.5 — OAuth2 WebFlux Resource Server: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/index.html
- Spring Security 6.5 — Reactive JWT Resource Server: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
- Spring Security 6.5 — Reactive Opaque Token: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/opaque-token.html
- Spring Security 6.5 — Reactive Bearer Tokens: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/bearer-tokens.html
- `ReactiveAuthenticationManager` API: https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/authentication/ReactiveAuthenticationManager.html
- `JwtReactiveAuthenticationManager` API: https://docs.spring.io/spring-security/site/docs/6.5.0-M1/api/org/springframework/security/oauth2/server/resource/authentication/JwtReactiveAuthenticationManager.html
- `OpaqueTokenReactiveAuthenticationManager` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/OpaqueTokenReactiveAuthenticationManager.html

**Key takeaway:** both JWT and opaque bearer tokens flow through `BearerTokenAuthenticationToken -> ReactiveAuthenticationManager -> Authentication -> Reactive SecurityContext` in WebFlux. JWT uses `ReactiveJwtDecoder` and typically produces `JwtAuthenticationToken`; introspection uses `ReactiveOpaqueTokenIntrospector` and typically produces `BearerTokenAuthentication`. The token contract, trust boundaries, and application permissions define a secure configuration.

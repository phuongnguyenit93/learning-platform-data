# Mocking ReactiveJwtDecoder and ReactiveOpaqueTokenIntrospector

## 1. Why Mock These Two Components in WebFlux Testing?

Spring Security WebFlux can authenticate access tokens in two common ways:

- **JWT:** The Resource Server passes the compact token to `ReactiveJwtDecoder`. The decoder returns `Mono<Jwt>` after decoding and verifying the token.
- **Opaque token:** The Resource Server passes the token to `ReactiveOpaqueTokenIntrospector`. The introspector calls the Authorization Server or an adapter and returns `Mono<OAuth2AuthenticatedPrincipal>` when the token is active.

When testing a reactive application, we often want to verify the entire security chain and HTTP behavior without calling a real Identity Provider. A useful approach is to **mock only the dependency at the token-verification boundary**, while keeping the upstream Spring Security components intact:

~~~text
WebTestClient
    |
    v
SecurityWebFilterChain
    |
    v
BearerTokenAuthenticationWebFilter
    |
    v
ReactiveAuthenticationManager
    |
    +---- JWT: ReactiveJwtDecoder (mock)
    |
    +---- Opaque: ReactiveOpaqueTokenIntrospector (mock)
    |
    v
Authentication + authorities
    |
    v
Authorization rules
    |
    v
Controller / service
~~~

With this approach, the test still exercises reading the Authorization header, the reactive authentication manager, converting to Authentication, authorization rules, and the controller. You control the token-verification result using Mockito.

Two goals should be distinguished:

- Mocking the decoder/introspector to test **whether the security filter chain calls the right component and handles reactive results properly**.
- Mocking Authentication directly with `mockJwt()` or `mockOpaqueToken()` to test controllers/authorization without running the decoder/introspector.

These two styles complement each other. They do not prove the same thing.

## 2. Two Reactive Interfaces with Different Contracts

### 2.1. ReactiveJwtDecoder

The `ReactiveJwtDecoder` interface is in package:

~~~java
org.springframework.security.oauth2.jwt.ReactiveJwtDecoder
~~~

Primary method:

~~~java
Mono<Jwt> decode(String token);
~~~

The input is the access token string. The result is a `Mono<Jwt>`:

- `Mono.just(jwt)`: the decoder accepted the token and returned a `Jwt`.
- `Mono.error(...)`: the token failed verification or the decoder encountered an error.
- `Mono.empty()`: not a normal success outcome for a decoder; treat it as an abnormal contract and verify how the application handles it.

In production, the decoder performs work such as parsing the compact JWT and checking the signature, key, issuer, timestamps, and configured validators. When mocking the decoder, those checks are **replaced by the stubbed result**.

### 2.2. ReactiveOpaqueTokenIntrospector

The `ReactiveOpaqueTokenIntrospector` interface is in package:

~~~java
org.springframework.security.oauth2.server.resource.introspection
~~~

Method:

~~~java
Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
~~~

The input is the opaque access token. Outcomes:

- `Mono.just(principal)`: introspection confirmed the token is active and returned attributes/authorities.
- `Mono.error(new BadOpaqueTokenException(...))`: the token is invalid or inactive.
- `Mono.error(...)` with another error: the introspection dependency or protocol encountered a problem.

In production, the introspector typically calls an RFC 7662 endpoint using a configured HTTP client. When mocking this interface, tests do not send HTTP requests to the Authorization Server; they only test how the Resource Server receives and processes the introspection result.

### 2.3. Comparison

| Characteristic | ReactiveJwtDecoder | ReactiveOpaqueTokenIntrospector |
|---|---|---|
| Input | Compact JWT | Opaque token |
| Result type | `Mono<Jwt>` | `Mono<OAuth2AuthenticatedPrincipal>` |
| Mocked component | JWT decoder | Token introspector |
| Authentication data | Claims and JWT headers | Introspection attributes |
| Bypassed when mocked | Signature/JWKS/validators in the real decoder | HTTP introspection/client authentication/AS schema |
| Used in | JWT Resource Server | Opaque-token Resource Server |

Do not pass a `Jwt` into `ReactiveOpaqueTokenIntrospector` or an `OAuth2AuthenticatedPrincipal` into the decoder. These are two distinct contracts.

## 3. Configuring a JWT Resource Server in WebFlux

A Servlet configuration uses `HttpSecurity`/`SecurityFilterChain`. WebFlux uses `ServerHttpSecurity`/`SecurityWebFilterChain`.

Example:

~~~java
@Configuration
@EnableWebFluxSecurity
public class JwtApiSecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(
            ServerHttpSecurity http,
            ReactiveJwtDecoder jwtDecoder) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public/**").permitAll()
                .pathMatchers("/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt.jwtDecoder(jwtDecoder))
            )
            .build();
    }
}
~~~

The key point is that the chain receives `ReactiveJwtDecoder` via dependency injection. In tests, replacing the decoder bean with a Mockito mock leaves the filter chain as the real configuration that still processes requests.

A production decoder may be created from an issuer location, a JWK Set URI, or custom configuration. When tests replace the decoder bean, there is no need to call real discovery/JWKS endpoints.

If the application uses auto-configuration, verify that the mocked bean is the exact bean used by the chain. If multiple decoders or multiple `SecurityWebFilterChain` beans exist, identify clearly which chain and decoder correspond to the endpoint under test.

## 4. Mocking ReactiveJwtDecoder with Mockito

### 4.1. Using @MockitoBean in the Spring Test Context

With Spring Framework 6.2 / Spring Boot 3.4+, you can use `@MockitoBean` to replace a bean in the ApplicationContext with a Mockito mock:

~~~java
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringBootTest
@AutoConfigureWebTestClient
class JwtResourceServerTests {

    @Autowired
    WebTestClient webTestClient;

    @MockitoBean
    ReactiveJwtDecoder jwtDecoder;
}
~~~

`@MockitoBean` lives in package:

~~~java
org.springframework.test.context.bean.override.mockito.MockitoBean
~~~

On older Spring Boot versions, projects may use `@MockBean`:

~~~java
import org.springframework.boot.test.mock.mockito.MockBean;

@MockBean
ReactiveJwtDecoder jwtDecoder;
~~~

`@MockBean` has been deprecated in newer Boot versions in favor of bean override annotations. Use the annotation available in your project's dependency version; never declare both for the same bean.

### 4.2. Creating a Mock Jwt

A `Jwt` object for testing can be constructed with the builder:

~~~java
private Jwt jwtWithReadScope() {
    Instant now = Instant.now();

    return Jwt.withTokenValue("jwt-fixture-001")
        .header("alg", "RS256")
        .header("kid", "test-key-01")
        .issuer(URI.create("https://id.example.test/realms/shop"))
        .subject("user-123")
        .audience(List.of("orders-api"))
        .issuedAt(now)
        .expiresAt(now.plusSeconds(300))
        .claim("scope", "orders.read")
        .claim("tenant_id", "tenant-a")
        .claim("client_id", "orders-web")
        .build();
}
~~~

Imports:

~~~java
import java.net.URI;
import java.time.Instant;
import java.util.List;

import org.springframework.security.oauth2.jwt.Jwt;
~~~

The `alg` and `kid` headers here are merely metadata on the test-constructed JWT object. Because the decoder is mocked, this object is not a genuinely signed and verified compact JWT. Do not use this test to claim RS256 signature verification or JWKS configuration works.

### 4.3. Stubbing the Decoder to Return Mono.just

~~~java
@Test
void acceptsJwtAndAllowsReadScope() {
    Jwt jwt = jwtWithReadScope();

    when(jwtDecoder.decode("jwt-fixture-001"))
        .thenReturn(Mono.just(jwt));

    webTestClient.get()
        .uri("/api/orders/42")
        .headers(headers ->
            headers.setBearerAuth("jwt-fixture-001")
        )
        .exchange()
        .expectStatus().isOk();

    verify(jwtDecoder).decode("jwt-fixture-001");
}
~~~

Mockito/Reactor imports:

~~~java
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import reactor.core.publisher.Mono;
~~~

`WebTestClient` sends the Bearer token normally. The security chain extracts the token, calls the mocked decoder, and uses the returned `Jwt` to build authentication. Because the `Jwt` has scope `orders.read`, the default converter creates the `SCOPE_orders.read` authority and the URL policy allows the request.

This is a security-chain integration test at the Resource Server authentication layer. It does not yet test the real decoder.

### 4.4. Verifying Missing Scope Returns 403

~~~java
@Test
void authenticatedJwtWithoutRequiredScopeIsForbidden() {
    Instant now = Instant.now();

    Jwt jwt = Jwt.withTokenValue("jwt-profile-only")
        .header("alg", "RS256")
        .subject("user-123")
        .issuedAt(now)
        .expiresAt(now.plusSeconds(300))
        .claim("scope", "profile.read")
        .build();

    when(jwtDecoder.decode("jwt-profile-only"))
        .thenReturn(Mono.just(jwt));

    webTestClient.get()
        .uri("/api/orders/42")
        .headers(headers ->
            headers.setBearerAuth("jwt-profile-only")
        )
        .exchange()
        .expectStatus().isForbidden();

    verify(jwtDecoder).decode("jwt-profile-only");
}
~~~

This test proves the token was accepted as a JWT Authentication, yet its authorities did not satisfy the policy. The result is typically 403.

### 4.5. Decoder Returning an Authentication Error

When the decoder emits a JWT error, the Resource Server must handle it as an authentication failure:

~~~java
@Test
void decoderFailureProducesUnauthorizedResponse() {
    when(jwtDecoder.decode("bad-jwt"))
        .thenReturn(Mono.error(
            new JwtException("Invalid test token")
        ));

    webTestClient.get()
        .uri("/api/orders/42")
        .headers(headers -> headers.setBearerAuth("bad-jwt"))
        .exchange()
        .expectStatus().isUnauthorized();

    verify(jwtDecoder).decode("bad-jwt");
}
~~~

Imports:

~~~java
import org.springframework.security.oauth2.jwt.JwtException;
~~~

In tests, the message is just internal error detail. Never echo exception details or raw tokens back to clients in production responses.

### 4.6. Decoder Is Not Called Without a Bearer Token

~~~java
@Test
void missingBearerTokenDoesNotInvokeDecoder() {
    webTestClient.get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isUnauthorized();

    verifyNoInteractions(jwtDecoder);
}
~~~

This test verifies that protected endpoints reject anonymous requests and that the decoder is not invoked when no token is present.

Imports:

~~~java
import static org.mockito.Mockito.verifyNoInteractions;
~~~

## 5. Mocking ReactiveOpaqueTokenIntrospector

### 5.1. Configuring an Opaque-Token Resource Server

An opaque-token chain can be configured as follows:

~~~java
@Configuration
@EnableWebFluxSecurity
public class OpaqueApiSecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(
            ServerHttpSecurity http,
            ReactiveOpaqueTokenIntrospector introspector) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/partners/**")
                    .hasAuthority("SCOPE_partner.reports.read")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(opaque ->
                    opaque.introspector(introspector)
                )
            )
            .build();
    }
}
~~~

This chain uses the injected introspector. In tests, mock that interface to control active/inactive responses and attributes.

JWT and opaque-token DSLs are two choices for Resource Server configuration. If an application supports both, clearly define which endpoints/chains use which token type, avoiding ambiguous configurations or letting one endpoint accept out-of-contract tokens.

### 5.2. Creating an OAuth2AuthenticatedPrincipal

Use `DefaultOAuth2AuthenticatedPrincipal` to build a mock principal:

~~~java
private OAuth2AuthenticatedPrincipal activePartnerPrincipal() {
    Map<String, Object> attributes = new HashMap<>();
    attributes.put("sub", "partner-user-01");
    attributes.put("client_id", "partner-client");
    attributes.put("scope", "partner.reports.read");
    attributes.put("tenant_id", "partner-a");

    Collection<GrantedAuthority> authorities = List.of(
        new SimpleGrantedAuthority("SCOPE_partner.reports.read")
    );

    return new DefaultOAuth2AuthenticatedPrincipal(
        "partner-user-01",
        attributes,
        authorities
    );
}
~~~

Imports:

~~~java
import java.util.Collection;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
~~~

In this example, the principal has both attributes and authorities. The introspector implementation is typically responsible for constructing the principal and authorities from the response contract. Tests must use the exact principal shape the application expects to receive.

### 5.3. Stubbing the Introspector to Return an Active Principal

~~~java
@Test
void activeOpaqueTokenCanReadPartnerReport() {
    when(introspector.introspect("opaque-fixture-001"))
        .thenReturn(Mono.just(activePartnerPrincipal()));

    webTestClient.get()
        .uri("/api/partners/reports/2026")
        .headers(headers ->
            headers.setBearerAuth("opaque-fixture-001")
        )
        .exchange()
        .expectStatus().isOk();

    verify(introspector).introspect("opaque-fixture-001");
}
~~~

The request still uses the Bearer scheme. The difference is on the server side: the token is passed to `ReactiveOpaqueTokenIntrospector` instead of a JWT decoder.

### 5.4. Missing Authority After Introspection Returns 403

~~~java
@Test
void activeOpaqueTokenWithoutReportScopeIsForbidden() {
    OAuth2AuthenticatedPrincipal principal =
        new DefaultOAuth2AuthenticatedPrincipal(
            "partner-user-01",
            Map.of(
                "sub", "partner-user-01",
                "scope", "partner.profile.read"
            ),
            List.of(
                new SimpleGrantedAuthority(
                    "SCOPE_partner.profile.read"
                )
            )
        );

    when(introspector.introspect("opaque-profile-token"))
        .thenReturn(Mono.just(principal));

    webTestClient.get()
        .uri("/api/partners/reports/2026")
        .headers(headers ->
            headers.setBearerAuth("opaque-profile-token")
        )
        .exchange()
        .expectStatus().isForbidden();
}
~~~

Here the token was confirmed active by the introspector, but the principal lacks the authority required by the endpoint. This differs from an inactive token, which must fail at authentication.

### 5.5. Introspector Rejecting an Inactive Token

A contract-compliant introspector typically emits `BadOpaqueTokenException` when a token is inactive:

~~~java
@Test
void inactiveOpaqueTokenIsUnauthorized() {
    when(introspector.introspect("inactive-token"))
        .thenReturn(Mono.error(
            new BadOpaqueTokenException("Token is inactive")
        ));

    webTestClient.get()
        .uri("/api/partners/reports/2026")
        .headers(headers -> headers.setBearerAuth("inactive-token"))
        .exchange()
        .expectStatus().isUnauthorized();

    verify(introspector).introspect("inactive-token");
}
~~~

Import:

~~~java
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
~~~

When mocking the introspector, model the contract accurately: an inactive token is represented by an authentication error. Never return a principal with attribute `active=false` and expect the Resource Server to interpret it as inactive; interpreting the introspection response belongs to the introspector.

## 6. Using @MockitoBean and WebTestClient for Filter Chain Tests

A complete test class may look like:

~~~java
@SpringBootTest
@AutoConfigureWebTestClient
class JwtResourceServerTests {

    @Autowired
    WebTestClient webTestClient;

    @MockitoBean
    ReactiveJwtDecoder jwtDecoder;

    @Test
    void authenticatedJwtCanReadOrders() {
        Jwt jwt = jwtWithReadScope();

        when(jwtDecoder.decode("jwt-fixture-001"))
            .thenReturn(Mono.just(jwt));

        webTestClient.get()
            .uri("/api/orders/42")
            .headers(h -> h.setBearerAuth("jwt-fixture-001"))
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

This example targets Spring Framework 6.2+; if your project uses an older Spring Boot version, replace `@MockitoBean` with `@MockBean` as appropriate for that version.

With `@WebFluxTest` slice tests, import the security configuration and controller under test. Slice tests may not load the entire application configuration, so never assume a mocked bean is automatically wired into the chain. `@SpringBootTest` is useful when you want to verify wiring close to the real application.

## 7. Mocking Decoder/Introspector vs. Mocking Authentication

Spring Security Test also provides WebFlux request mutators such as `mockJwt()` and `mockOpaqueToken()` (names/packages/availability depend on version). They place a mock Authentication directly into the request.

| Goal | Approach | Component called? |
|---|---|---|
| Test URL authorization with a mock JWT principal | `mockJwt()` | Does not call ReactiveJwtDecoder |
| Test controller with a mock opaque principal | `mockOpaqueToken()` | Does not call ReactiveOpaqueTokenIntrospector |
| Test Bearer extraction and JWT authentication manager | Mock ReactiveJwtDecoder, send Bearer header | Yes |
| Test Bearer extraction and opaque authentication manager | Mock ReactiveOpaqueTokenIntrospector, send Bearer header | Yes |
| Test real JWT signatures | Real decoder with test key/JWKS | Yes |
| Test real HTTP introspection | Real introspector with mock HTTP server/sandbox | Yes |

Never use `mockJwt()` and then `verify(jwtDecoder).decode(...)`: the request post-processor bypasses the decoder, so the mock is never invoked. Likewise, `mockOpaqueToken()` does not invoke the introspector.

## 8. Testing Reactive Errors and Publisher Behavior

Because both interfaces return a Reactor `Mono`, stubs must return a publisher. Never return a `Jwt` or principal directly from Mockito.

### 8.1. Success

~~~java
when(jwtDecoder.decode("good-token"))
    .thenReturn(Mono.just(jwt));
~~~

### 8.2. Authentication Failure

~~~java
when(jwtDecoder.decode("bad-token"))
    .thenReturn(Mono.error(new JwtException("Invalid JWT")));
~~~

### 8.3. Introspection Failure

~~~java
when(introspector.introspect("inactive-token"))
    .thenReturn(Mono.error(
        new BadOpaqueTokenException("Inactive token")
    ));
~~~

### 8.4. Empty Publisher

`Mono.empty()` differs from `Mono.error(...)` and `Mono.just(...)`. Do not use empty to represent an invalid token if the component contract expects an authentication exception. An empty publisher can cause unexpected behavior in the authentication pipeline; if the application has a custom wrapper/adapter, explicitly test the empty case and define how it translates to an error.

### 8.5. Do Not Block the Reactive Pipeline

In WebFlux tests, use `WebTestClient` and let the framework subscribe to the publisher. Never call `block()` inside controllers, filters, or reactive authentication code just to make testing easier. When testing a standalone reactive service/adapter, you can use `StepVerifier`:

~~~java
StepVerifier.create(tokenService.resolve("test-token"))
    .expectNextMatches(result ->
        result.getSubject().equals("user-123")
    )
    .verifyComplete();
~~~

`StepVerifier` is suited for verifying the publisher contract of reactive code written by the application. It does not replace HTTP integration tests through `SecurityWebFilterChain`.

## 9. Testing Claims, Authorities, and Principal Shape

### 9.1. JWT Claims

With a mocked decoder returning `Jwt`, verify:

- The subject is read properly by the controller.
- Issuer/audience claims propagate properly to the application layer.
- The tenant claim is read properly.
- Custom claims have the data types expected by converters/services.
- Authorities are built according to scope/role mapping.
- Missing or wrong-typed claims never grant unintended permissions.

Note: because the mocked decoder returns a `Jwt` directly, this test does not prove issuer/audience validators executed. To test validators, test the real decoder.

### 9.2. Opaque Principal Attributes

With a mocked introspector returning `OAuth2AuthenticatedPrincipal`, verify:

- Subject and client ID.
- Scopes/authorities.
- Tenant or partner identifier.
- Optional/missing attributes.
- Data types of claims.
- Allowed/denied permissions.

Do not assume an opaque principal has `Jwt#getClaims()`. Use the `OAuth2AuthenticatedPrincipal#getAttribute(...)` or `getAttributes()` contract.

### 9.3. Do Not Mix Roles and Scopes

For example, authority `SCOPE_orders.read` is not the same as `ROLE_ADMIN`. When stubbing a JWT/opaque principal, create authorities matching the policy under test. If a production converter builds authorities, write dedicated tests for the converter and its wiring.

## 10. Verifying Correct HTTP Semantics

| Request/result | Meaning | Typical outcome |
|---|---|---|
| No Bearer token on a protected route | Unauthenticated | 401 |
| JWT decoder returns `Mono.just(jwt)`, valid scope | Authenticated and authorized | 2xx |
| JWT decoder returns JWT missing scope | Authenticated but insufficient permissions | 403 |
| JWT decoder emits `JwtException` | Authentication failure | 401 |
| Introspector returns principal with scope | Active opaque token | 2xx |
| Introspector emits `BadOpaqueTokenException` | Inactive/invalid token | 401 |
| Principal active but missing scope | Authorization denied | 403 |
| Introspection service unavailable | Dependency failure | Per the application's exception translation and availability policy |

Do not assume every error from the introspector must become the same HTTP status. `BadOpaqueTokenException` describes an invalid token; network failures, timeouts, or bad Resource Server credentials with the AS are separate operational failure modes. Verify the application's exception mapping and authentication entry point rather than lumping everything into "invalid token."

## 11. Confirming the Mocked Decoder Is Used by the Chain

A common mistake is mocking the right interface while the chain uses a different decoder instantiated inside configuration.

Check the following:

1. Security configuration accepts `ReactiveJwtDecoder` via constructor/bean injection.
2. `@MockitoBean` replaces the right bean in the context.
3. There are not multiple `ReactiveJwtDecoder` beans where another qualifier is used.
4. Requests enter the intended `SecurityWebFilterChain`.
5. Tests send `Authorization: Bearer ...` rather than attaching Authentication directly with a mock post-processor.
6. After the `WebTestClient` exchange completes, `verify(jwtDecoder).decode(token)` confirms the decoder was called.

For opaque tokens, apply the same checks to `ReactiveOpaqueTokenIntrospector`.

If the decoder/introspector is not called, check route matchers, security chain ordering, test context, and how the test client is bound. Never change assertions to make a test pass when the component under test was never invoked.

## 12. Common Pitfalls When Mocking Reactive Components

### Mistake 1 — Returning an Object Instead of a Mono

Wrong:

~~~java
when(jwtDecoder.decode("token")).thenReturn(jwt);
~~~

Right:

~~~java
when(jwtDecoder.decode("token")).thenReturn(Mono.just(jwt));
~~~

Likewise, the introspector must return `Mono.just(principal)`.

### Mistake 2 — Using Mono.just(null)

Reactor forbids `Mono.just(null)`. Use `Mono.empty()` if the contract genuinely allows empty; for invalid tokens, typically emit an authentication exception via `Mono.error(...)`.

### Mistake 3 — Also Mocking AuthenticationManager

If the goal is to test decoder/introspector integration, mocking `ReactiveAuthenticationManager` skips the component you wanted to test. Mock only the decoder or introspector, keeping the real authentication manager and filter chain.

### Mistake 4 — Using mockJwt() and Then Verifying the Decoder

`mockJwt()` creates Authentication directly. The decoder is never called.

### Mistake 5 — Using mockOpaqueToken() and Then Verifying the Introspector

`mockOpaqueToken()` also bypasses the introspector. Use a Bearer header and mock the dependency.

### Mistake 6 — Thinking a Builder-Constructed JWT Object Has a Signature

`Jwt.withTokenValue(...)` creates an object for testing principals/claims. It does not produce a validly signed compact JWT. Signatures are only checked when a compact token goes through a real decoder.

### Mistake 7 — Expecting a Mocked Decoder to Validate Issuer/Audience Automatically

A mocked decoder only returns the stubbed result. If the stub returns `Mono.just(jwt)`, the Resource Server accepts that `Jwt`; validators inside the real decoder have been replaced. Use invalid tokens and a real decoder when the goal is testing validation.

### Mistake 8 — Stubbing One Token While Sending Another

Mockito stubs by argument. If the request sends a different token string, the stub may not match and return `null`, causing confusing errors. Use a constant for the fixture token and inspect invocation arguments.

### Mistake 9 — Forgetting Reactive Work Runs on Subscribe

Some calls happen when the `WebTestClient` exchange subscribes to the publisher. Call `verify(...)` after the exchange completes. Never verify before the publisher has executed.

### Mistake 10 — Using the Wrong @MockBean/@MockitoBean Version

Annotations and packages depend on Spring Framework/Boot versions. Check your dependency tree and test API for your project's version before choosing a bean override annotation.

## 13. Layered Testing Strategy

A WebFlux Resource Server test suite can be structured as:

~~~mermaid
flowchart TD
    A["Unit test converter / adapter"] --> B["WebTestClient + mocked decoder/introspector"]
    B --> C["Signed JWT + real ReactiveJwtDecoder"]
    B --> D["HTTP stub + real ReactiveOpaqueTokenIntrospector"]
    C --> E["JWKS / issuer / audience / expiry"]
    D --> F["Introspection protocol / active / timeout"]
    E --> G["Authorization and API behavior"]
    F --> G
~~~

### Layer 1 — Unit Tests for Application Reactive Code

Test custom claim converters, adapters, principal mapping, and error mapping. Use Mockito and `StepVerifier` when verifying publisher behavior.

### Layer 2 — WebTestClient with Mocked Decoder/Introspector

Keep the real `SecurityWebFilterChain`, send Bearer headers, and mock the exact interface. Verify tokens reach the dependency, Authentication is built, authorities are enforced, and HTTP status codes are right.

### Layer 3 — Real Decoder with Test Signing Keys

Use a test private key to sign JWTs and a test public key/JWKS to verify them. Verify signatures, issuer, audience, timestamps, algorithms, and key rotation. Never use production signing keys.

### Layer 4 — Real Introspector with HTTP Stub or Sandbox

Use a mock HTTP server to verify introspection requests, client authentication, `active` responses, schemas, timeouts, and error mapping. Sandbox tests confirm contracts with real providers when needed.

There is no need to call a production Authorization Server on every pull request. Unit and WebFlux integration tests should be deterministic and network-independent.

## 14. Checklist When Mocking ReactiveJwtDecoder or ReactiveOpaqueTokenIntrospector

- [ ] Confirmed whether the endpoint uses JWT or opaque tokens.
- [ ] Mocked the matching reactive interface.
- [ ] Stubs return `Mono.just(...)` or `Mono.error(...)`, never raw objects directly.
- [ ] Kept `SecurityWebFilterChain` and reactive authentication manager intact.
- [ ] Sent Bearer tokens via the Authorization header.
- [ ] Verified the mock dependency was actually invoked.
- [ ] Tested accepted tokens.
- [ ] Tested invalid/inactive tokens.
- [ ] Tested authenticated principals lacking authority returning 403.
- [ ] Verified JWT claims or opaque attributes match the principal contract.
- [ ] Did not treat a mocked decoder as a test of signature/issuer/audience/JWKS.
- [ ] Did not treat a mocked introspector as a test of HTTP introspection/client authentication.
- [ ] Included real decoder tests with test keys if the application relies on JWT validation.
- [ ] Included real introspector tests with an HTTP stub if the application relies on opaque introspection.
- [ ] Did not use `mockJwt()`/`mockOpaqueToken()` when the goal is verifying decoder/introspector invocation.
- [ ] Verified version compatibility of `@MockitoBean` or `@MockBean`.

## 15. Conclusion

`ReactiveJwtDecoder` and `ReactiveOpaqueTokenIntrospector` are two distinct access-token verification boundaries in Spring Security WebFlux. Mocking them with Mockito allows testing the security filter chain without calling a real issuer:

- For JWTs, stub `decode(token)` to return `Mono<Jwt>` or an error.
- For opaque tokens, stub `introspect(token)` to return `Mono<OAuth2AuthenticatedPrincipal>` or an error.
- Send Bearer tokens via `WebTestClient` so requests traverse the reactive authentication manager and `SecurityWebFilterChain`.
- Use `mockJwt()`/`mockOpaqueToken()` when you only want to test authorization with a mock Authentication.
- Use real decoders/introspectors with test keys or HTTP stubs when verifying JWT signatures or the introspection protocol.

Keeping a clear boundary between mock authentication, mocked token-verification dependencies, and real-provider integration ensures tests state accurately what they have proved.

### References

- [Spring Security Reference — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security Reference — Reactive OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security Reference — Testing Reactive Applications](https://docs.spring.io/spring-security/reference/reactive/test/web/index.html)
- [Spring Security API — ReactiveJwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/ReactiveJwtDecoder.html)
- [Spring Security API — ReactiveOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html)
- [Spring Security API — Jwt](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/Jwt.html)
- [Spring Security API — DefaultOAuth2AuthenticatedPrincipal](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/DefaultOAuth2AuthenticatedPrincipal.html)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)

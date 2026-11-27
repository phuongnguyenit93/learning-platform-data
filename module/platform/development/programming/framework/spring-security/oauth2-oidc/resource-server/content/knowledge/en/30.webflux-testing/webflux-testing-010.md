# Distinguishing Mock Identity from End-to-End Real Token Verification

When testing a **Spring Security WebFlux Resource Server application**, there are two very different goals:

- Verifying whether an authenticated caller is permitted to perform an action.
- Verifying whether a real Bearer access token traverses the entire authentication process—from the HTTP header to the decoder or introspection endpoint—before permission is granted.

Spring Security Test provides helpers such as **jwt()**, **mockOpaqueToken()**, and **mockUser()** to construct test identities. These helpers enable fast authorization testing, yet they inject Authentication directly into the request's security context. They **do not simulate the full real-world token verification flow**.

To verify real tokens, tests must send an `Authorization: Bearer ...` header through the WebFlux filter chain and let Spring Security invoke `ReactiveJwtDecoder` or `ReactiveOpaqueTokenIntrospector`. To test signatures, issuers, audiences, expiry, JWKS, or HTTP introspection, you must use a real decoder/introspector with appropriate test keys, metadata, or an HTTP test server.

This lesson clearly distinguishes testing layers, how to build test JWTs with claims/authorities, how to use `WebTestClient`, and how to design tests progressing from mock identities to end-to-end token verification.

## 1. Two Different Testing Goals

Suppose the Orders API has an endpoint:

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer <access-token>
~~~

The API only permits callers with scope `orders.read`, the right audience `orders-api`, and belonging to the tenant owning the order.

We need to test multiple layers:

1. Does the HTTP request carry a Bearer token?
2. Is the Bearer token extracted properly?
3. Is the token a JWT or opaque token per contract?
4. Does the JWT have a valid signature, issuer, audience, and timestamps; or does introspection return `active=true`?
5. Are authorities mapped properly from claims?
6. Does the caller hold the required scope/role?
7. Is the caller authorized to access that specific tenant/order?

**Mock identity** typically starts at step 5 or step 6: the test supplies a pre-built Authentication. **Real token verification** starts from the HTTP Bearer header and traverses the Resource Server's authentication mechanism.

~~~mermaid
flowchart TD
    A["WebTestClient request"] --> B["BearerTokenAuthenticationWebFilter"]
    B --> C["ReactiveAuthenticationManager"]
    C --> D{"Token strategy"}
    D --> E["ReactiveJwtDecoder"]
    D --> F["ReactiveOpaqueTokenIntrospector"]
    E --> G["Signature + issuer + time + audience/profile"]
    F --> H["Introspection active + claims"]
    G --> I["JwtAuthenticationConverter"]
    H --> J["Opaque principal + authorities"]
    I --> K["Reactive SecurityContext"]
    J --> K
    K --> L["Authorization rules / method security"]
    L --> M["Controller / service / repository"]
~~~

With `mockJwt()` or `mockOpaqueToken()`, the test creates the identity at the SecurityContext layer, so Bearer parsing, HTTP decoder/introspection calls, and cryptographic verification are not executed as shown in the diagram above.

## 2. WebFlux Testing Tools

The application needs the test dependency:

~~~xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

If using Spring Boot dependency management, let Boot manage the Spring Security Test version in sync with the Spring Security runtime.

Commonly used tools:

| Tool | Role |
| --- | --- |
| WebTestClient | Sends HTTP requests against a WebFlux application or test server |
| SecurityMockServerConfigurers.mockJwt() | Builds a JWT Authentication for tests |
| SecurityMockServerConfigurers.mockOpaqueToken() | Builds an opaque-token Authentication for tests |
| SecurityMockServerConfigurers.mockUser() | Builds a user Authentication without needing a JWT |
| ReactiveJwtDecoder | Verifies JWTs in a reactive Resource Server |
| ReactiveOpaqueTokenIntrospector | Verifies opaque tokens via introspection in a reactive Resource Server |
| StepVerifier | Tests publishers, converters, validators, or reactive services in isolation |
| HTTP stub server | Tests real discovery, JWKS, or introspection requests/responses |

Common static imports:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOpaqueToken;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
~~~

Exact package and API names must match the `spring-security-test` version in your project.

## 3. Configuring a Reactive Resource Server for Testing

Example of an API accepting only Bearer JWTs:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ApiSecurityConfiguration {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

This is an illustrative configuration for a Bearer API. If the application also serves browser sessions, CSRF, and other routes, keep separate policies per security chain or matcher. Never disable CSRF application-wide just to make API tests easier to run.

Controller:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    @GetMapping("/api/orders/{id}")
    OrderView get(
            @PathVariable String id,
            @AuthenticationPrincipal Jwt jwt) {
        return new OrderView(id, jwt.getSubject());
    }
}

record OrderView(String id, String requestedBy) {
}
~~~

In production, the endpoint also needs tenant/owner checks in the service/repository. The controller example above only illustrates retrieving the `Jwt` principal.

## 4. Using mockJwt() to Test Authorization

A minimal test:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class OrderAuthorizationTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void readerCanGetOrder() {
        webTestClient
            .mutateWith(mockJwt())
            .get()
            .uri("/api/orders/123")
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

`mockJwt()` builds a mock JWT Authentication in the reactive security context for the request. The request still passes through the application's authorization rules, so tests can verify `hasAuthority`, `hasRole`, method security, and controller behavior.

There is no need to send a compact JWT string or configure keys to run this authorization test.

### Customizing Subject and Claims

~~~java
webTestClient
    .mutateWith(mockJwt().jwt(jwt -> jwt
        .subject("user-42")
        .issuer("https://auth.example.com/realms/shop")
        .audience(List.of("orders-api"))
        .claim("scope", "orders.read")
        .claim("tenant_id", "tenant-a")))
    .get()
    .uri("/api/orders/123")
    .exchange()
    .expectStatus().isOk();
~~~

Claims set directly on the test `Jwt`:

| Claim | Purpose in tests |
| --- | --- |
| sub | Subject/caller |
| iss | Issuer used by application logic |
| aud | Target resource/API for the token |
| scope or scp | Access permissions per issuer contract |
| exp, nbf, iat | Timestamps if test code reads them |
| client_id | OAuth client |
| tenant_id | Tenant context |
| roles, permissions | Custom permissions if supported by converter |

**Setting a past exp claim inside mockJwt() does not automatically test token expiration.** The helper already constructed Authentication; the JWT decoder and timestamp validators are never invoked.

## 5. Creating Authorities Directly with mockJwt()

If the goal is only to test an authority rule, you can specify authorities directly:

~~~java
import org.springframework.security.core.authority.SimpleGrantedAuthority;

webTestClient
    .mutateWith(mockJwt().authorities(
        new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get()
    .uri("/api/orders/123")
    .exchange()
    .expectStatus().isOk();
~~~

This is a fast way to verify:

- `hasAuthority("SCOPE_orders.read")`.
- `hasRole("ORDER_ADMIN")` with authority `ROLE_ORDER_ADMIN`.
- Custom authorization managers.
- Method security based on `GrantedAuthority`.

However, when passing authorities directly, the test **does not test the claim-to-authority converter**. A token with `roles: ["ADMIN"]` does not automatically become `ROLE_ADMIN` unless a converter is configured to do so.

### Distinguishing hasRole and hasAuthority

~~~java
.hasRole("ADMIN")
~~~

typically checks for authority `ROLE_ADMIN` due to the default role prefix.

~~~java
.hasAuthority("ROLE_ADMIN")
~~~

matches the string `ROLE_ADMIN` exactly.

For scopes:

~~~java
.hasAuthority("SCOPE_orders.read")
~~~

create the authority with the matching prefix in tests or declare the `scope` claim so the default converter maps it.

## 6. Using mockOpaqueToken() for Opaque Principal Authorization

If the application uses opaque tokens:

~~~java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults()))
~~~

you can use `mockOpaqueToken()` to build a test principal:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOpaqueToken;

webTestClient
    .mutateWith(mockOpaqueToken())
    .get()
    .uri("/api/orders/123")
    .exchange()
    .expectStatus().isOk();
~~~

You can customize attributes and authorities using the API of your version. Conceptual example:

~~~java
webTestClient
    .mutateWith(mockOpaqueToken()
        .attributes(attributes -> {
            attributes.put("sub", "service-orders");
            attributes.put("tenant_id", "tenant-a");
        })
        .authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get()
    .uri("/api/orders/123")
    .exchange()
    .expectStatus().isOk();
~~~

`mockOpaqueToken()` creates an Authentication/principal for the test. It **does not call ReactiveOpaqueTokenIntrospector**, does not send an HTTP POST to an introspection endpoint, and does not check `active: true/false`.

## 7. Using mockUser() When Tests Do Not Depend on JWTs

Not every security test needs a Resource Server principal. If a controller/service relies only on authorities or username:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

webTestClient
    .mutateWith(mockUser("alice").roles("ADMIN"))
    .get()
    .uri("/admin/dashboard")
    .exchange()
    .expectStatus().isOk();
~~~

`mockUser()` constructs a user Authentication. It is useful for general authorization rules, yet its principal is not a `Jwt` and lacks OAuth2 Resource Server semantics.

If the controller accepts `@AuthenticationPrincipal Jwt`, use `mockJwt()` or test the Bearer flow. Never use `mockUser()` and assume the controller will receive a `Jwt`.

## 8. Distinguishing Mock Identity from Real Bearer Tokens

This is the most important distinction when designing a test suite:

| Check | mockJwt() / mockOpaqueToken() | Real Bearer header + decoder/introspector |
| --- | --- | --- |
| Is the HTTP Bearer header parsed? | No | Yes |
| Does the Bearer filter process the token? | Not through the normal Bearer authentication path | Yes |
| Is ReactiveJwtDecoder called? | No | Yes for JWT |
| Is ReactiveOpaqueTokenIntrospector called? | No | Yes for opaque tokens |
| Is the JWT signature verified? | No | Only when using a real decoder |
| Do issuer/time/audience validators run? | No | Only when using a real decoder/validators |
| Is an HTTP introspection request sent? | No | Only when using a real HTTP introspector |
| Do authorization rules run? | Yes | Yes |
| Does controller/method security run? | Yes | Yes |

Therefore, never use a passing `mockJwt()` test to conclude "the Resource Server verified the access token properly." That test proves authorization policies work with a pre-built JWT principal.

## 9. Testing the Bearer Filter with a Mocked ReactiveJwtDecoder

To test the real path of a Bearer header without generating keys/signatures in that test, mock `ReactiveJwtDecoder` and send the header:

~~~java
import static org.mockito.Mockito.when;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

@SpringBootTest
@AutoConfigureWebTestClient
class BearerPipelineTest {

    @Autowired
    WebTestClient webTestClient;

    @MockitoBean
    ReactiveJwtDecoder jwtDecoder;

    @Test
    void bearerHeaderIsPassedToReactiveDecoder() {
        Instant issuedAt = Instant.parse("2026-11-01T10:00:00Z");
        Jwt jwt = Jwt.withTokenValue("test-token")
            .header("alg", "RS256")
            .issuer("https://auth.example.com/realms/shop")
            .subject("user-42")
            .audience(List.of("orders-api"))
            .issuedAt(issuedAt)
            .expiresAt(issuedAt.plusSeconds(300))
            .claim("scope", "orders.read")
            .build();

        when(jwtDecoder.decode("test-token"))
            .thenReturn(Mono.just(jwt));

        webTestClient.get()
            .uri("/api/orders/123")
            .headers(headers -> headers.setBearerAuth("test-token"))
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

This test sends a real Bearer header through the WebFlux security filter. Spring Security extracts the token and calls the mocked `ReactiveJwtDecoder`. This lets you verify:

- The Bearer header is received.
- The reactive authentication manager calls the decoder.
- The configured JWT authentication converter is applied.
- Authorization rules and the controller execute after authentication succeeds.

However, the mocked decoder simply returns the test-specified `Jwt`. **This test does not verify signature, JWKS, issuer, audience, or expiry using real cryptography/validators.**

In newer Spring Framework versions you can use `@MockitoBean`; older Spring Boot projects typically use `@MockBean`. Pick the annotation matching your active dependency.

### Invalid Token in a Mocked Decoder Test

~~~java
when(jwtDecoder.decode("bad-token"))
    .thenReturn(Mono.error(new JwtException("Invalid JWT")));

webTestClient.get()
    .uri("/api/orders/123")
    .headers(headers -> headers.setBearerAuth("bad-token"))
    .exchange()
    .expectStatus().isUnauthorized();
~~~

This tests the branch where the decoder signals an error and the HTTP authentication entry point returns 401. It does not prove a specific signature failed; the mocked decoder was programmed to emit an error.

## 10. Testing the Opaque Bearer Pipeline with a Mocked ReactiveOpaqueTokenIntrospector

For opaque tokens, send a Bearer header and mock the introspector:

~~~java
import static org.mockito.Mockito.when;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

@SpringBootTest
@AutoConfigureWebTestClient
class OpaqueBearerPipelineTest {

    @Autowired
    WebTestClient webTestClient;

    @MockitoBean
    ReactiveOpaqueTokenIntrospector introspector;

    @Test
    void activeTokenIsConvertedToAuthenticatedPrincipal() {
        var principal = new DefaultOAuth2AuthenticatedPrincipal(
            "service-orders",
            Map.of("sub", "service-orders", "tenant_id", "tenant-a"),
            List.of(new SimpleGrantedAuthority("SCOPE_orders.read")));

        when(introspector.introspect("opaque-test-token"))
            .thenReturn(Mono.just(principal));

        webTestClient.get()
            .uri("/api/orders/123")
            .headers(headers ->
                headers.setBearerAuth("opaque-test-token"))
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

This test confirms the Bearer pipeline calls the reactive introspector and passes the principal into authorization. It **does not test the HTTP request to the Authorization Server**, because the introspector is mocked.

### Inactive Token

The introspector can emit `BadOpaqueTokenException`:

~~~java
when(introspector.introspect("inactive-token"))
    .thenReturn(Mono.error(
        new BadOpaqueTokenException("Token is inactive")));

webTestClient.get()
    .uri("/api/orders/123")
    .headers(headers -> headers.setBearerAuth("inactive-token"))
    .exchange()
    .expectStatus().isUnauthorized();
~~~

### Active but Missing Scope

If the introspector returns a valid principal without `SCOPE_orders.read`, authentication succeeds yet authorization is denied:

~~~java
var principal = new DefaultOAuth2AuthenticatedPrincipal(
    "user-42",
    Map.of("sub", "user-42"),
    List.of(new SimpleGrantedAuthority("SCOPE_profile.read")));

when(introspector.introspect("active-without-order-scope"))
    .thenReturn(Mono.just(principal));

webTestClient.get()
    .uri("/api/orders/123")
    .headers(headers ->
        headers.setBearerAuth("active-without-order-scope"))
    .exchange()
    .expectStatus().isForbidden();
~~~

This is the difference between `active=false`/authentication failure and `active=true` with insufficient permissions: typically 401 and 403, respectively.

## 11. Testing the Real Decoder with Signed JWTs

To verify signatures, you must use a real `ReactiveJwtDecoder` and a test key pair. One approach is generating an RSA key pair in the test, signing a compact JWT with the private key, and configuring the decoder with the matching public key.

The example below illustrates the decoder/validator setup. The test project needs a compatible JOSE/JWT library (Spring Security OAuth2 JOSE uses Nimbus JOSE JWT):

~~~java
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.Date;

import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;

String issuer = "https://auth.test.example/issuer";
Instant now = Instant.now();

RSAKey signingKey = new RSAKeyGenerator(2048)
    .keyID("test-rsa-1")
    .generate();

JWTClaimsSet claims = new JWTClaimsSet.Builder()
    .issuer(issuer)
    .subject("user-42")
    .audience("orders-api")
    .issueTime(Date.from(now.minusSeconds(5)))
    .expirationTime(Date.from(now.plusSeconds(300)))
    .claim("scope", "orders.read")
    .build();

SignedJWT signedJwt = new SignedJWT(
    new JWSHeader.Builder(JWSAlgorithm.RS256)
        .keyID(signingKey.getKeyID())
        .build(),
    claims);
signedJwt.sign(new RSASSASigner(signingKey.toPrivateKey()));
String compactToken = signedJwt.serialize();

NimbusReactiveJwtDecoder decoder =
    NimbusReactiveJwtDecoder.withPublicKey(
        (RSAPublicKey) signingKey.toPublicKey()).build();

OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
    jwt.getAudience().contains("orders-api")
        ? OAuth2TokenValidatorResult.success()
        : OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", "Wrong audience", null));

decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
    JwtValidators.createDefaultWithIssuer(issuer),
    audienceValidator));
~~~

This example builds the token and decoder using an in-memory test key. When `decoder.decode(compactToken)` is called, the decoder must verify the RSA signature and configured validators. Never use production keys.

### Sending the Signed Token via WebTestClient

Wire the real decoder into the test configuration, then:

~~~java
webTestClient.get()
    .uri("/api/orders/123")
    .headers(headers -> headers.setBearerAuth(compactToken))
    .exchange()
    .expectStatus().isOk();
~~~

Negative cases should create tokens signed with another key, wrong issuer, wrong audience, expired timestamps, `nbf` in the future, or disallowed algorithms. Each case must go through the Bearer header to verify the filter/decoder returns 401 per contract.

If using a JWKS endpoint instead of a direct public key, run an HTTP test server serving JWKS and configure the decoder to fetch keys from the test URI. Then you can test `kid`, JWKS fetching, caching, unknown keys, and rotation. A decoder configured with a direct public key does not test HTTP discovery/JWKS.

## 12. Testing Issuer, Audience, and Expiration

A valid signature is not enough. The Resource Server must enforce token profile conditions:

| Condition | Test token | Expected result |
| --- | --- | --- |
| Valid issuer | `iss` matches trusted issuer | May proceed |
| Different issuer | `iss` does not match | 401 |
| Valid audience | `aud` contains `orders-api` | May proceed |
| Different audience | Only `payments-api` | 401 |
| Expired token | `exp` in the past | 401 |
| Not yet valid | `nbf` in the future beyond clock skew | 401 |
| Invalid signature | Valid payload but invalid signature | 401 |
| Disallowed algorithm | Token uses `alg` outside allowlist | 401 |
| Missing scope | Valid token lacking `orders.read` | 403 |

`mockJwt()` can set these claims to test business code that reads them, yet it does not execute the validators. Use a real decoder when the goal is verifying token acceptance.

## 13. Testing Real HTTP Introspection with a Test Server

If the application uses opaque tokens, testing the entire protocol requires letting the real introspector call a test HTTP server.

In the test:

1. Start a local HTTP stub server (such as WireMock or MockWebServer).
2. Point `introspection-uri` to the stub.
3. Configure test client ID/secret.
4. Send a Bearer token request via `WebTestClient`.
5. Verify the stub receives a POST on the right path/content type with the token in the body.
6. Verify client authentication matches the configured method.
7. Return introspection responses per scenario.

Active response:

~~~json
{
  "active": true,
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1893456000
}
~~~

Inactive response:

~~~json
{
  "active": false
}
~~~

Matrix:

| Stub response | Meaning | Typical API outcome |
| --- | --- | --- |
| 200 + `active: true`, sufficient claims | Token accepted by AS | Proceeds to authorization |
| 200 + `active: false` | Inactive token | 401 |
| 200 but missing/wrong-typed `active` | Response violates contract | Fail closed |
| 401 from introspection endpoint | Client auth may be wrong | Authentication dependency failure |
| 403 from introspection endpoint | Client not permitted to introspect | Never treat user token as valid |
| 429 | AS rate limit | Do not grant Authentication |
| 5xx/timeout/TLS error | AS unavailable | Fail closed per policy |
| 200 active but missing scope | Token active, insufficient permissions | 403 |

A mocked `ReactiveOpaqueTokenIntrospector` does not check the HTTP details above. Only tests with a real introspector and an HTTP stub verify the request/response protocol.

Never use production access tokens or production secrets in a test server. Never log raw tokens or client secrets.

## 14. Claims and Authorities Are Not the Same Thing

A JWT may contain:

~~~json
{
  "sub": "user-42",
  "scope": "orders.read orders.export",
  "roles": ["ORDER_MANAGER"],
  "tenant_id": "tenant-a"
}
~~~

Claims are data inside the token. `GrantedAuthority` instances are the permissions Spring Security uses for authorization. The converter decides how they map.

With the default converter, `scope` is typically mapped to:

~~~text
SCOPE_orders.read
SCOPE_orders.export
~~~

A custom `roles` claim does not automatically become `ROLE_ORDER_MANAGER` unless the application configures a matching converter.

Custom converter example:

~~~java
import java.util.Collection;
import java.util.List;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;

final class RoleAuthoritiesConverter
        implements Converter<Jwt, Collection<GrantedAuthority>> {

    @Override
    public Collection<GrantedAuthority> convert(Jwt jwt) {
        List<String> roles = jwt.getClaimAsStringList("roles");
        if (roles == null) {
            return List.of();
        }
        return roles.stream()
            .map(role -> new SimpleGrantedAuthority("ROLE_" + role))
            .toList();
    }
}
~~~

To test the production mapping, there are two options:

- Unit test the converter directly with a `Jwt` object.
- Send a Bearer header through the filter chain with `ReactiveJwtDecoder` returning the JWT and the real `jwtAuthenticationConverter` configured.

If you only use `mockJwt().authorities(...)`, the test specifies authorities explicitly and **bypasses the converter**. If using `mockJwt().jwt(...)`, verify how your version's post-processor builds authorities from claims; never assume it invokes your production converter bean.

## 15. Claims for Tenant and Object-Level Authorization

Suppose the token has:

~~~json
{
  "sub": "user-42",
  "scope": "orders.read",
  "tenant_id": "tenant-a"
}
~~~

The service must scope queries by tenant:

~~~java
Order findOrder(String orderId, Jwt jwt) {
    String tenantId = jwt.getClaimAsString("tenant_id");
    if (tenantId == null) {
        throw new AccessDeniedException("Tenant is required");
    }
    return repository.findByIdAndTenantId(orderId, tenantId)
        .orElseThrow(() ->
            new AccessDeniedException("Order is not accessible"));
}
~~~

Mock identity for the test:

~~~java
webTestClient
    .mutateWith(mockJwt().jwt(jwt -> jwt
        .subject("user-42")
        .claim("scope", "orders.read")
        .claim("tenant_id", "tenant-a")))
    .get()
    .uri("/api/orders/order-100")
    .exchange()
    .expectStatus().isOk();
~~~

Add another test using `tenant-b`, verify the repository only queries by the principal's tenant, and confirm another tenant's data is never returned. Scope only authorizes calling the feature; it does not grant permission to read every order.

## 16. Reactive Method Security

In WebFlux, method security must be enabled with:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
class ReactiveMethodSecurityConfiguration {
}
~~~

A reactive service:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.oauth2.jwt.Jwt;
import reactor.core.publisher.Mono;

class ReportService {

    @PreAuthorize("hasAuthority('SCOPE_reports.read')")
    Mono<String> readReport(Jwt jwt) {
        return Mono.just("report-for-" + jwt.getSubject());
    }
}
~~~

Testing via `WebTestClient`:

~~~java
webTestClient
    .mutateWith(mockJwt().jwt(jwt -> jwt
        .subject("analyst-7")
        .claim("scope", "reports.read")))
    .get()
    .uri("/api/reports")
    .exchange()
    .expectStatus().isOk();
~~~

In reactive method security, `SecurityContext` is propagated via Reactor Context. Do not assume `SecurityContextHolder` `ThreadLocal` holds `Authentication` in every callback. If testing a service publisher directly, subscribe in a context containing `Authentication` using reactive test support; never call `block()` inside the application to force a reactive flow to be imperative.

## 17. Testing ReactiveSecurityContextHolder and Request Isolation

A reactive controller or service can read `Authentication` from Reactor Context:

~~~java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Mono<String> currentSubject() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName());
}
~~~

In tests using `mockJwt()`, the context is supplied for the `WebTestClient` request. Each request gets its own principal:

~~~java
webTestClient
    .mutateWith(mockJwt().jwt(jwt -> jwt.subject("alice")))
    .get().uri("/api/whoami")
    .exchange()
    .expectBody()
    .jsonPath("$.subject").isEqualTo("alice");

webTestClient
    .mutateWith(mockJwt().jwt(jwt -> jwt.subject("bob")))
    .get().uri("/api/whoami")
    .exchange()
    .expectBody()
    .jsonPath("$.subject").isEqualTo("bob");
~~~

Never store a request's `Authentication` in a singleton field or `ThreadLocal`. Never share a mutable `SecurityContext` across requests. When tests run in parallel, each `WebTestClient` exchange must keep the right request context.

## 18. @WebFluxTest and @SpringBootTest

### @WebFluxTest

`@WebFluxTest` fits when you only need the controller slice. You can import the security configuration and mock required dependencies:

~~~java
@WebFluxTest(OrderController.class)
@Import(ApiSecurityConfiguration.class)
class OrderControllerWebFluxTest {

    @Autowired
    WebTestClient webTestClient;

    @MockitoBean
    ReactiveJwtDecoder jwtDecoder;
}
~~~

On older Spring Test versions, replace `@MockitoBean` with `@MockBean` if appropriate. You may need to mock other beans referenced by the security config.

### @SpringBootTest

Use `@SpringBootTest` with `@AutoConfigureWebTestClient` when you need to test:

- The full reactive security chain.
- Custom filters and filter ordering.
- Reactive method security.
- Real converter/decoder/introspector beans.
- Service/repository integration.
- Multiple `SecurityWebFilterChain` instances and matchers.

For tests needing real TLS handshakes or network behavior, you may need to run the server on a random port and configure an HTTPS test client; `WebTestClient` bound directly to the application context does not perform a real TLS handshake.

## 19. Testing Missing Tokens, Invalid Tokens, and Insufficient Scope

A minimal API suite should distinguish:

~~~java
@Test
void missingBearerTokenIsUnauthorized() {
    webTestClient.get()
        .uri("/api/orders/123")
        .exchange()
        .expectStatus().isUnauthorized();
}

@Test
void validIdentityWithoutScopeIsForbidden() {
    webTestClient
        .mutateWith(mockJwt().jwt(jwt -> jwt
            .subject("profile-user")
            .claim("scope", "profile.read")))
        .get()
        .uri("/api/orders/123")
        .exchange()
        .expectStatus().isForbidden();
}

@Test
void readerCanAccessOrder() {
    webTestClient
        .mutateWith(mockJwt().jwt(jwt -> jwt
            .subject("reader-42")
            .claim("scope", "orders.read")))
        .get()
        .uri("/api/orders/123")
        .exchange()
        .expectStatus().isOk();
}
~~~

Typical outcomes:

| Scenario | Meaning | Typical HTTP status |
| --- | --- | --- |
| No Bearer token | Unauthenticated | 401 |
| Decoder/introspector finds token invalid | Authentication failure | 401 |
| Valid token missing scope | Authorization failure | 403 |
| Valid token with sufficient scope | Permitted by authorization | 2xx per controller |

If the application has a custom entry point/access denied handler, verify status/body/headers per the actual contract.

## 20. Testing Multiple SecurityWebFilterChains

A WebFlux application can have separate chains for APIs, browser login, actuator, or internal endpoints. In that case, tests must prove requests enter the intended chain.

Example API chain and fallback:

~~~java
@Bean
@Order(1)
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**"))
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}

@Bean
@Order(100)
SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().denyAll())
        .build();
}
~~~

This example illustrates ordering and matchers; matcher classes/APIs must match your version. Test:

- `/api/**` without a token returns 401 from the Resource Server.
- `/api/**` with a JWT missing scope returns 403.
- Routes not matching the API chain are rejected by the fallback.
- Browser routes go through the OAuth2 Login chain if the application has one.

`mockJwt()` can help test authorization once the chain is selected, yet does not prove the API chain's Bearer filter processed the header. To test chain authentication, send a real Bearer header and use an appropriate decoder.

## 21. CSRF and State-Changing Requests in WebFlux

Never disable CSRF across the entire WebFlux application just to make POST tests easier.

- APIs that only accept Bearer tokens in the Authorization header and do not rely on automatically sent cookies for authentication can typically configure CSRF accordingly for the API.
- Browsers using session cookies require CSRF consideration because browsers attach cookies automatically.
- If the same application has both API and browser chains, separate policies by chain.

Spring Security Test has a CSRF helper for WebFlux:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

webTestClient
    .mutateWith(mockUser("alice").roles("ADMIN"))
    .mutateWith(csrf())
    .post()
    .uri("/app/profile")
    .exchange()
    .expectStatus().isOk();
~~~

CSRF tests should reflect the route's real authentication mechanism. A request using `mockJwt()` does not by itself prove the browser session/cookie CSRF policy is right.

## 22. Do Not Use Mock Helpers to Claim Full Token Pipeline Coverage

Test helpers are useful yet bounded:

| Helper | What it creates | What it does not verify |
| --- | --- | --- |
| mockJwt() | JWT principal/Authentication for reactive request | Bearer parsing, signature, JWKS, issuer/audience/time validators |
| mockOpaqueToken() | Opaque principal/Authentication for reactive request | HTTP introspection, client authentication, active responses |
| mockUser() | User Authentication | JWT claims, Resource Server decoder/introspector |
| @WithMockUser | User Authentication in the appropriate test context | OAuth2 access token validation |
| ReactiveJwtDecoder mock | Test-controlled decode result | Cryptographic verification |
| ReactiveOpaqueTokenIntrospector mock | Test-controlled principal | Introspection HTTP protocol |

These limitations do not make the helpers less valuable; they make testing each layer fast. The mistake happens when using a result from one layer to draw conclusions about another layer.

## 23. Real Token Testing Matrix

For JWT:

| Scenario | Component that must run for real | Expected result |
| --- | --- | --- |
| Valid signature, trusted key | ReactiveJwtDecoder + public key/JWKS | Authentication can succeed |
| Invalid signature | Real decoder | 401 |
| Wrong issuer | Real issuer validator | 401 |
| Wrong audience | Real audience validator | 401 |
| Expired token | Real timestamp validator | 401 |
| `nbf` in the future | Real timestamp validator | 401 |
| Non-existent `kid` | Real JWKS decoder/client | 401 |
| JWKS endpoint timeout | HTTP test server + real decoder | Fail closed for unverified tokens |
| Key rotation | JWKS server rotating keys + real cache | Behavior matches overlap/refresh policy |
| Missing scope | Real decoder + converter + authorization | 403 |

For opaque tokens:

| Scenario | Component that must run for real | Expected result |
| --- | --- | --- |
| `active: true`, sufficient scope | Real HTTP reactive introspector | Permitted |
| `active: false` | Real HTTP introspection | 401 |
| Missing `active`/wrong schema | Real introspection parser | Fail closed |
| Wrong introspection client auth | HTTP stub/test AS | Do not create Authentication |
| HTTP 429/5xx/timeout | HTTP test server | Do not accept new tokens |
| Active but wrong audience | Introspector + profile validator | 401 |
| Active but missing scope | Introspector + authorization | 403 |
| Revoked token | Test AS + real introspection | Inactive per propagation/cache policy |

## 24. Question-Based Test Selection Matrix

| Question to answer | Appropriate test |
| --- | --- |
| Can someone with `orders.read` call GET? | `mockJwt()` |
| Does the controller read the `tenant_id` claim properly? | `mockJwt().jwt(...)` |
| Is the `roles` claim mapped to `ROLE_ADMIN`? | Converter unit test or Bearer flow |
| Is the Bearer header parsed and passed to the decoder? | Real header + mocked `ReactiveJwtDecoder` |
| Is the JWT signature valid? | Real header + real decoder/key |
| Are issuer/audience/exp checked? | Real decoder + real validators |
| Is a new JWKS `kid` fetched? | Real decoder + JWKS test server |
| Does the introspection POST have the right client auth/body? | Real reactive introspector + HTTP stub |
| Is `active:false` rejected? | Real introspector or mock for the authentication branch |
| Does method security run inside Reactor Context? | `mockJwt()` via `WebTestClient` and reactive service |
| Can another tenant read an order? | Mock principal + service/repository test |
| Does the TLS handshake require a client cert? | HTTPS test server with test CA/client certificate |

## 25. Common Pitfalls

**"mockJwt() passing means real JWTs are verified."** No. The helper builds Authentication, bypassing the decoder and signature checks.

**"I set exp in the past yet the request still returns 200."** That is because `mockJwt()` does not run the timestamp validator. Send a Bearer token through the real decoder to test expiration.

**"I set the wrong iss yet the test still passes."** Claims are just data on the mocked JWT. The issuer validator is never called.

**"I set the wrong aud yet the Resource Server still lets it through."** `mockJwt()` does not check audience automatically. Test the real decoder validator.

**"mockOpaqueToken() tests the introspection endpoint."** No. It builds a principal; use an HTTP stub and real introspector to test the protocol.

**"I used mockUser() for a controller expecting Jwt."** A mock user's principal is not a `Jwt`. Use `mockJwt()` or the Bearer flow.

**"Adding a roles claim makes Spring automatically create ROLE_..."** No. A converter or explicitly specified test authorities are required.

**"Mocking ReactiveJwtDecoder means signatures were tested."** No. The mock returns objects according to the test's stubbing.

**"WebTestClient bound to a controller proves TLS mTLS works."** Not necessarily. Use a real HTTPS test server with a client certificate when testing handshakes.

**"Reactive SecurityContext lives in ThreadLocal."** Never assume that. WebFlux uses Reactor Context; use the reactive security APIs.

**"A single 200 test is enough."** No. You also need missing token, invalid token, insufficient scope, wrong audience/issuer, remote outages, and business authorization.

## 26. Workflow for Building a WebFlux Test Suite

1. **Separate test questions:** authorization, controller principal, converter, Bearer parsing, token validation, or introspection protocol.
2. **Use mockJwt() for JWT authorization:** declare minimal subject, scope, tenant, and claims.
3. **Use mockOpaqueToken() for opaque principal authorization:** declare attributes/authorities per contract.
4. **Use mockUser() when the endpoint only needs a generic user/role:** no JWT principal needed.
5. **Test reactive method security:** enable `@EnableReactiveMethodSecurity` and run requests inside Reactor Context.
6. **Test the Bearer pipeline:** send a real Authorization header and mock `ReactiveJwtDecoder` or `ReactiveOpaqueTokenIntrospector`.
7. **Test JWT cryptography:** real decoder, test key pair, issuer/audience/time validators.
8. **Test JWKS:** HTTP test server, `kid`, caching, unknown keys, and key rotation.
9. **Test HTTP introspection:** stub endpoint, client authentication, request body, active/inactive, timeouts, and error statuses.
10. **Test business policies:** tenant, owner, sharing, and repository queries.
11. **Test WebFlux context isolation:** multiple requests/principals, no `ThreadLocal` or mutable global context.
12. **Test topology when needed:** multiple `SecurityWebFilterChain` instances, proxies, TLS, and mTLS using an appropriate server.

**Key takeaway:** `mockJwt()`, `mockOpaqueToken()`, and `mockUser()` construct identities to test **authorization** in WebFlux. They do not verify real Bearer tokens. To test the entire chain, send an `Authorization: Bearer ...` header via `WebTestClient`, let `BearerTokenAuthenticationWebFilter` call `ReactiveJwtDecoder` or `ReactiveOpaqueTokenIntrospector`, and verify validators, converters, and authorization. Use real decoders/introspectors with test keys/JWKS or an HTTP test server when you need to prove signatures, issuer, audience, expiry, introspection, and behavior during Authorization Server failures.

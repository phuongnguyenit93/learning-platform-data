# WebTestClient with SecurityWebFilterChain

In a Spring WebFlux application, **WebTestClient** helps test HTTP endpoints reactively, while **SecurityWebFilterChain** is where Spring Security applies authentication, authorization, CSRF, and security WebFilters to requests. When testing a Resource Server, you need to ensure requests go through the right security chain and that results are observed at the HTTP boundary.

A WebFlux test can verify multiple layers:

- Without credentials: protected endpoints return `401 Unauthorized`.
- Authenticated but missing authority/scope: returns `403 Forbidden`.
- JWT with the appropriate scope: request is allowed through the security chain.
- Public routes: accessible according to policy.
- POST/PUT/DELETE: conforms to the application's CSRF policy.
- JWT with invalid signature, issuer, audience, or expiration: the real decoder rejects the token.
- Custom converter, method security, and multiple security chains: work properly with real requests.

Key distinction: **test helpers like `mockJwt()` create a mock authentication to test authorization; they do not prove that `ReactiveJwtDecoder` verified the JWT signature**. When you need to test token validation, you must send a genuinely signed Bearer token through the filter chain and let the real decoder process it.

This lesson belongs to the **WebFlux Testing** chapter in the **Spring Security OAuth 2.0 OIDC Resource Server** module. The examples use the Spring Security reactive stack and JUnit 5. Specific API/annotation names may vary across Spring Boot/Spring Security versions; use your project's dependency versions.

## 1. Role of WebTestClient and SecurityWebFilterChain

WebFlux uses a reactive pipeline based on `Publisher`/`Mono`/`Flux`. Security is applied via `WebFilter` and `SecurityWebFilterChain`, rather than Spring MVC's Servlet `FilterChainProxy`/`SecurityFilterChain`.

~~~text
WebTestClient
     |
     v
HTTP request / exchange
     |
     v
WebFlux WebHandler
     |
     v
WebFilter chain
     |
     +--> SecurityWebFilterChain
     |       |
     |       +--> SecurityContext
     |       +--> Authentication
     |       +--> Authorization
     |       +--> CSRF / exception handling
     |
     v
RouterFunction / Controller
     |
     v
HTTP response
~~~

`WebTestClient` can bind directly to a controller, an application context, or a running server. The binding approach determines the level of integration being tested:

| Binding approach | Scope | When appropriate |
|---|---|---|
| `bindToController(...)` | Selected controller/WebFlux handler | Testing simple HTTP mappings/handlers; required filters must be configured manually |
| `bindToRouterFunction(...)` | RouterFunction and corresponding handler | Testing functional endpoints |
| `bindToApplicationContext(...)` | WebFlux application context and filter beans | Testing the security chain alongside application wiring in a mock server environment |
| `bindToServer()` | Running HTTP server | End-to-end testing across the network boundary |
| Spring Boot `@SpringBootTest` + `@AutoConfigureWebTestClient` | Application started with the test context | Integration tests closer to production |

If the goal is to test `SecurityWebFilterChain`, a controller-only client does not automatically ensure security filters are installed. Use application context binding with `springSecurity()`, or let Spring Boot configure the test client against the real application.

## 2. Dependencies for WebFlux Security Tests

With Spring Boot, the core dependencies are:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

`spring-boot-starter-test` provides JUnit Jupiter, AssertJ, and common test utilities. `spring-security-test` provides reactive test support such as `mockUser()`, `mockJwt()`, `mockAuthentication()`, and `csrf()`.

You do not need to add the Spring MVC starter to a pure WebFlux application just to use `WebTestClient`. Mixing `spring-boot-starter-web` and `spring-boot-starter-webflux` can cause Boot to choose the Servlet application type depending on the classpath/configuration; be explicit about whether the application runs on reactive or Servlet.

## 3. Configuring the SecurityWebFilterChain Under Test

Example Resource Server protecting an Orders API:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableReactiveMethodSecurity
class OrdersSecurityConfiguration {

    @Bean
    SecurityWebFilterChain ordersSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public/**").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

In this configuration:

- `permitAll()` for public routes.
- GET Orders requires the `SCOPE_orders.read` authority.
- POST Orders requires `SCOPE_orders.write`.
- All remaining requests must be authenticated.
- `oauth2ResourceServer().jwt()` configures Bearer JWT authentication via the reactive decoder.
- `@EnableReactiveMethodSecurity` enables method-level authorization for the reactive stack if the application uses `@PreAuthorize` or other method security annotations.

### 3.1. CSRF Policy Must Be Explicitly Decided

WebFlux security enables CSRF protection by default. For an API that only accepts access tokens via the Authorization header and does not rely on automatically sent cookies/sessions, the application can explicitly disable CSRF:

~~~java
return http
    .csrf(ServerHttpSecurity.CsrfSpec::disable)
    .authorizeExchange(...)
    .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
    .build();
~~~

Only disable it when the authentication model is truly stateless bearer-token and does not rely on browser cookies for automatic authentication. If the application uses session cookies/OAuth2 Login or cookie-based authentication, CSRF protection may still be needed. In that case, POST tests must send a valid CSRF token.

### 3.2. Reactive Controller for Testing

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/orders")
class OrdersController {

    @GetMapping("/{id}")
    Mono<OrderResponse> findById(@PathVariable String id) {
        if ("missing".equals(id)) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Order not found"));
        }
        return Mono.just(new OrderResponse(id, "CREATED"));
    }

    @PostMapping
    Mono<OrderResponse> create(@RequestBody CreateOrderRequest request) {
        return Mono.just(new OrderResponse("order-100", "CREATED"));
    }
}

record OrderResponse(String id, String status) {}
record CreateOrderRequest(String sku, int quantity) {}
~~~

This controller is just a minimal example to illustrate the security boundary. In a real application, the handler can call reactive services and return `Mono`/`Flux`; `WebTestClient` will subscribe and inspect the response without needing to call `.block()` in production code.

## 4. Two Ways to Initialize WebTestClient with Security

### 4.1. Spring Boot Integration Test with a Random Server Port

When you need to test the real application over an HTTP server:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class OrdersHttpIntegrationTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void publicEndpointIsAccessible() {
        webTestClient.get()
            .uri("/public/health")
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

`RANDOM_PORT` starts a real server on a random port. `WebTestClient` sends requests over the network stack; the test covers server startup, routing, WebFilters, the security chain, and response handling. This approach is slower than a mock application context, but valuable when you need to verify real integration configuration.

If the application requires an issuer/JWKS endpoint during startup, the test needs to configure a suitable test issuer/decoder so it does not depend on external network calls. Testing with real tokens is covered below.

### 4.2. Binding to the Application Context and Applying Spring Security

If you do not need to open a TCP server:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class OrdersApplicationContextTest {

    @Autowired
    ApplicationContext applicationContext;

    WebTestClient webTestClient;

    @BeforeEach
    void setUp() {
        webTestClient = WebTestClient
            .bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void publicEndpointIsAccessible() {
        webTestClient.get()
            .uri("/public/health")
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

`springSecurity()` adds the integration needed so security filters in the application context are applied when `WebTestClient` handles requests. If you omit this step, the test may run the handler without going through the security chain, leading to misleading security results.

### 4.3. Do Not Use bindToController and Conclude the Security Chain Was Tested

For example:

~~~java
WebTestClient client = WebTestClient
    .bindToController(new OrdersController())
    .build();
~~~

This client is useful for controller-only tests. However, without installing `SecurityWebFilterChain`/security filters, it does not prove the endpoint is protected by the application's configuration. When testing `SecurityWebFilterChain`, use application context binding or a Boot integration test.

## 5. Using mockJwt() to Test Authorization

For a JWT Resource Server, `mockJwt()` is a convenient test helper to create a mock `JwtAuthenticationToken` for the request. It allows testing path rules and scope authorities without calling an Authorization Server or verifying signatures.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

@SpringBootTest
class OrdersAuthorizationTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void ordersReadScopeCanReadOrder() {
        webTestClient
            .mutateWith(mockJwt().jwt(jwt ->
                jwt.claim("scope", "orders.read")))
            .get()
            .uri("/api/orders/42")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo("42")
            .jsonPath("$.status").isEqualTo("CREATED");
    }

    @Test
    void ordersWriteScopeCannotReadOrder() {
        webTestClient
            .mutateWith(mockJwt().jwt(jwt ->
                jwt.claim("scope", "orders.write")))
            .get()
            .uri("/api/orders/42")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

Spring Security's default JWT authority converter maps a space-delimited `scope` claim to authorities prefixed with `SCOPE_`. Therefore, `scope=orders.read` produces the `SCOPE_orders.read` authority under the default configuration. If the application uses a custom `JwtAuthenticationConverter`, the test must reflect the actual mapping.

### 5.1. Creating Multiple Scopes in a Mock JWT

~~~java
webTestClient
    .mutateWith(mockJwt().jwt(jwt ->
        jwt.claim("scope", "orders.read orders.write")))
    .get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk();
~~~

The `scope` value in an OAuth access token is typically a space-separated string of scopes. The test helper uses mock claims; a signed compact JWT is not needed for this authorization-only goal.

### 5.2. Configuring Authorities Directly

~~~java
import org.springframework.security.core.authority.SimpleGrantedAuthority;

webTestClient
    .mutateWith(mockJwt().authorities(
        new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk();
~~~

This gives the test exact control over the authorities attached to the authentication. It **does not test** how the `scope`/`scp` claim is converted into authorities by the converter. Choose claim-based or authority-based depending on the layer you need to test.

### 5.3. Mock JWT Can Include Subject and Issuer

~~~java
webTestClient
    .mutateWith(mockJwt().jwt(jwt -> jwt
        .subject("alice")
        .issuer("https://login.example.test")
        .claim("aud", "orders-api")
        .claim("scope", "orders.read")))
    .get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk();
~~~

These claims are useful for controller/method-security tests. However, `mockJwt()` does not verify that the issuer, audience, or signature is actually accepted by the decoder. Do not use this test as evidence that JWT validation is working.

## 6. Testing 401, 403, and Public Endpoints

A basic security test suite should distinguish three cases:

| Request | Authentication | Authority | Typically expected result |
|---|---|---|---|
| GET `/public/health` | Not required | Not required | 200 |
| GET `/api/orders/42` without token | Unauthenticated | None | 401 |
| GET `/api/orders/42` with valid token missing `orders.read` | Authenticated | Missing scope | 403 |
| GET `/api/orders/42` with token and `orders.read` | Authenticated | Sufficient scope | 200 |

Example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

@SpringBootTest
class OrdersSecurityStatusTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void publicEndpointDoesNotRequireAuthentication() {
        webTestClient.get()
            .uri("/public/health")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void protectedEndpointRequiresAuthentication() {
        webTestClient.get()
            .uri("/api/orders/42")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedPrincipalWithoutRequiredScopeIsForbidden() {
        webTestClient
            .mutateWith(mockJwt().jwt(jwt ->
                jwt.claim("scope", "profile.read")))
            .get()
            .uri("/api/orders/42")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void authenticatedPrincipalWithRequiredScopeIsAllowed() {
        webTestClient
            .mutateWith(mockJwt().jwt(jwt ->
                jwt.claim("scope", "orders.read")))
            .get()
            .uri("/api/orders/42")
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

No token on a protected endpoint typically results in 401 because the Resource Server requires authentication. A valid token missing the required authority typically results in 403. Custom exception handling may change the response body, but should not turn a lack of permissions into a successful request.

### 6.1. Using mockUser() for Applications with UserDetails Authentication

`mockUser()` creates a mock user authentication. It is suitable when testing general authorization rules or applications using form login/basic/session authentication:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

webTestClient
    .mutateWith(mockUser().roles("ADMIN"))
    .get()
    .uri("/admin/report")
    .exchange()
    .expectStatus().isOk();
~~~

`mockUser()` does not create a `JwtAuthenticationToken` and does not test the Resource Server JWT flow. If an endpoint requires `SCOPE_orders.read`, use `mockJwt()` or an authentication fixture with the appropriate authority.

### 6.2. Using mockAuthentication() When a Custom Principal Is Needed

`mockAuthentication()` lets you set a mock `Authentication` on the request. This example is useful when testing a custom principal or a non-JWT authentication type:

~~~java
import org.springframework.security.authentication.TestingAuthenticationToken;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockAuthentication;

var authentication = new TestingAuthenticationToken(
    "alice", "not-a-real-credential", "SCOPE_orders.read");
authentication.setAuthenticated(true);

webTestClient
    .mutateWith(mockAuthentication(authentication))
    .get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk();
~~~

This is a mock pre-authenticated test principal. Do not use `TestingAuthenticationToken` as an authentication mechanism in production, and do not treat this test as proof that JWT signatures are verified.

## 7. Testing CSRF with WebTestClient

If `SecurityWebFilterChain` keeps CSRF protection enabled, a POST without a CSRF token may be rejected even when the request is already authenticated. This is especially important for cookie/session-based browser applications.

### 7.1. POST Without a CSRF Token

~~~java
@Test
void postWithoutCsrfTokenIsRejectedWhenCsrfIsEnabled() {
    webTestClient
        .mutateWith(mockJwt().jwt(jwt ->
            jwt.claim("scope", "orders.write")))
        .post()
        .uri("/api/orders")
        .bodyValue(new CreateOrderRequest("sku-123", 2))
        .exchange()
        .expectStatus().isForbidden();
}
~~~

This test assumes CSRF is enabled and there is no custom CSRF repository/exception handler altering the response details.

### 7.2. POST with a CSRF Token

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

@Test
void postWithCsrfTokenAndWriteScopeIsAllowed() {
    webTestClient
        .mutateWith(mockJwt().jwt(jwt ->
            jwt.claim("scope", "orders.write")))
        .mutateWith(csrf())
        .post()
        .uri("/api/orders")
        .bodyValue(new CreateOrderRequest("sku-123", 2))
        .exchange()
        .expectStatus().isOk();
}
~~~

If a stateless API application intentionally disabled CSRF because it only uses Bearer headers and does not use automatically sent cookies, the test does not need `csrf()`. Tests must reflect **the chain's actual CSRF policy**, rather than adding helpers just to make tests pass.

### 7.3. CSRF and Authentication Are Separate Conditions

A POST request can be blocked by CSRF before reaching authorization rules or the controller. So when debugging a 403, check:

- Was a CSRF token sent when required by policy?
- Is Authentication established?
- Does the principal have the required authority?
- Is method security or a custom authorization manager denying the request?

Do not assume every 403 means a missing scope.

## 8. Testing Real JWTs Through ReactiveJwtDecoder

Mock JWT helpers bypass the token decoder. To test signature, issuer, audience, and timestamps, send a genuinely signed compact JWT in the Authorization Bearer header and configure `ReactiveJwtDecoder` to verify it.

### 8.1. Why a Dedicated Test Signing Key Is Needed

In integration tests, you can generate an RSA key pair dedicated to testing:

~~~text
Test private key:
    signs JWT fixtures
    used only at test runtime

Test public key:
    configures ReactiveJwtDecoder
    used to verify signatures

Production:
    uses real issuer/JWKS
    does not trust test keys
~~~

Do not use the production issuer's private signing key in tests. Do not call external networks to fetch tokens in every test; local fixtures keep tests repeatable and reliable.

### 8.2. Testing the Decoder with Issuer and Audience Validators

Example test configuration:

~~~java
import java.security.interfaces.RSAPublicKey;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;

@TestConfiguration
class TestJwtDecoderConfiguration {

    static final String ISSUER = "https://issuer.test";
    static final String AUDIENCE = "https://api.test/orders";

    @Bean
    TestRsaKeys testRsaKeys() {
        return new TestRsaKeys();
    }

    @Bean
    @Primary
    ReactiveJwtDecoder testReactiveJwtDecoder(TestRsaKeys keys) {
        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withPublicKey(
                (RSAPublicKey) keys.keyPair().getPublic())
                .signatureAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(AUDIENCE)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token",
                        "Token audience is not accepted", null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                audienceValidator
            )
        );
        return decoder;
    }
}
~~~

`JwtValidators.createDefaultWithIssuer` preserves the default issuer and timestamp checks; the audience validator is composed via `DelegatingOAuth2TokenValidator`. Calling `setJwtValidator(audienceValidator)` alone could unintentionally replace the default validators.

`TestRsaKeys` is an application-created test fixture to keep a consistent key pair between the encoder and decoder. Place the test bean in the test source set and ensure this is the decoder actually used by `SecurityWebFilterChain`. If the production configuration already declares its own decoder, use a dedicated test profile/context or replace the bean using an appropriate test mechanism instead of creating two competing decoders.

### 8.3. Creating Signed JWTs with NimbusJwtEncoder

Spring Security OAuth2 JOSE provides `NimbusJwtEncoder`. You can build a JWK source from the test key pair:

~~~java
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import com.nimbusds.jose.jwk.source.JWKSource;
import com.nimbusds.jose.proc.SecurityContext;

import org.springframework.context.annotation.Bean;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;

@TestConfiguration
class TestJwtEncoderConfiguration {

    @Bean
    JwtEncoder testJwtEncoder(TestRsaKeys keys) {
        RSAKey rsaJwk = new RSAKey.Builder(
                (RSAPublicKey) keys.keyPair().getPublic())
            .privateKey((RSAPrivateKey) keys.keyPair().getPrivate())
            .keyID("test-key")
            .build();

        JWKSource<SecurityContext> jwkSource =
            new ImmutableJWKSet<>(new JWKSet(rsaJwk));
        return new NimbusJwtEncoder(jwkSource);
    }
}
~~~

`TestRsaKeys` can generate the key pair once:

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;

final class TestRsaKeys {

    private final KeyPair keyPair;

    TestRsaKeys() {
        try {
            KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
            generator.initialize(2048);
            this.keyPair = generator.generateKeyPair();
        } catch (Exception ex) {
            throw new IllegalStateException("Cannot create test RSA keys", ex);
        }
    }

    KeyPair keyPair() {
        return keyPair;
    }
}
~~~

For both encoder and decoder beans to use the same key pair, register `TestRsaKeys` as a singleton bean in the test configuration. Do not generate a separate new key pair inside each bean.

### 8.4. Creating Token Fixtures with Appropriate Claims

~~~java
import java.time.Instant;
import java.util.List;

import org.springframework.security.oauth2.jose.jws.JwsHeader;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;

String signedToken(
        JwtEncoder encoder,
        String audience,
        String scope,
        Instant expiresAt) {

    Instant now = Instant.now();
    JwtClaimsSet claims = JwtClaimsSet.builder()
        .issuer(TestJwtDecoderConfiguration.ISSUER)
        .subject("alice")
        .audience(List.of(audience))
        .issuedAt(now.minusSeconds(5))
        .expiresAt(expiresAt)
        .claim("scope", scope)
        .build();

    JwsHeader headers = JwsHeader.with(SignatureAlgorithm.RS256)
        .keyId("test-key")
        .build();

    return encoder.encode(
        JwtEncoderParameters.from(headers, claims)
    ).getTokenValue();
}
~~~

The `audience`, `scope`, and `expiresAt` parameters let you create positive and negative tokens all signed with the same test key. That way, an invalid-audience test proves the audience validator is working rather than being rejected due to the signature.

### 8.5. Sending Real Tokens via WebTestClient

~~~java
import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.context.annotation.Import;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
@Import({TestJwtDecoderConfiguration.class, TestJwtEncoderConfiguration.class})
class OrdersRealJwtIntegrationTest {

    @Autowired
    WebTestClient webTestClient;

    @Autowired
    JwtEncoder testJwtEncoder;

    @Test
    void acceptsSignedTokenWithCorrectIssuerAudienceAndScope() {
        String token = signedToken(
            testJwtEncoder,
            TestJwtDecoderConfiguration.AUDIENCE,
            "orders.read",
            Instant.now().plusSeconds(300)
        );

        webTestClient.get()
            .uri("/api/orders/42")
            .headers(headers -> headers.setBearerAuth(token))
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void rejectsSignedTokenForAnotherAudience() {
        String token = signedToken(
            testJwtEncoder,
            "https://api.test/payments",
            "orders.read",
            Instant.now().plusSeconds(300)
        );

        webTestClient.get()
            .uri("/api/orders/42")
            .headers(headers -> headers.setBearerAuth(token))
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

This is an integration test following the configured test decoder/encoder model. The wrong-audience token still has a valid signature and correct issuer, so 401 tests the audience boundary accurately. A token missing scope but with valid issuer/audience can be authenticated and then receive 403 at authorization.

### 8.6. Testing Expired Tokens and Insufficient Scope

Create an expired token with a valid signature:

~~~java
String expiredToken = signedToken(
    testJwtEncoder,
    TestJwtDecoderConfiguration.AUDIENCE,
    "orders.read",
    Instant.now().minusSeconds(120)
);
~~~

Send this token to a protected endpoint and expect 401. The expiration timestamp should be far enough in the past that it will not be accepted due to clock skew.

Token with valid issuer, audience, and expiry, but missing scope:

~~~java
String insufficientScopeToken = signedToken(
    testJwtEncoder,
    TestJwtDecoderConfiguration.AUDIENCE,
    "orders.write",
    Instant.now().plusSeconds(300)
);
~~~

Send this token to GET Orders. The decoder can authenticate the token, then the authorization rule denies it for missing `SCOPE_orders.read`; the result is typically 403. This separates token validation from endpoint authorization.

## 9. Slice Testing with @WebFluxTest

`@WebFluxTest` loads a partial WebFlux application context, typically focusing on controllers/handlers and related WebFlux components. It starts faster than a full `@SpringBootTest`, but does not automatically bring in the entire application configuration.

Example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

@WebFluxTest(controllers = OrdersController.class)
@Import(OrdersSecurityConfiguration.class)
class OrdersControllerSliceTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void requestWithoutJwtIsUnauthorized() {
        webTestClient.get()
            .uri("/api/orders/42")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void requestWithReadScopeIsAllowed() {
        webTestClient
            .mutateWith(mockJwt().jwt(jwt ->
                jwt.claim("scope", "orders.read")))
            .get()
            .uri("/api/orders/42")
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

If the controller depends on services/repositories, the slice test needs to mock the dependencies excluded from the slice. Depending on the Spring Boot version, use the appropriate bean override annotation such as `@MockitoBean` or `@MockBean`. Do not import the entire application config unnecessarily just to get the test context to start.

### 9.1. What Does a Slice Test Verify?

`@WebFluxTest` is well-suited to verify:

- Path/method mappings and request body binding.
- Response status/body/headers.
- The security chain imported and applied within the slice.
- Authorities required for the endpoint.
- Error mapping at the controller/WebFlux layer.

It does not automatically prove:

- Production issuer/JWKS discovery works.
- The production decoder has the right key/algorithm.
- OAuth clients or external databases are fully configured.
- Gateways/proxies outside the application forward headers properly.

### 9.2. Do Not Confuse Slice Tests with Full Integration

If a test only imports `OrdersSecurityConfiguration` while production also has another chain, custom filters, a security context repository, or gateway integration, the slice may not cover those components. Use slice tests for fast feedback; use full context/server integration tests for critical wiring boundaries.

## 10. Testing Method Security in WebFlux

Path authorization and method authorization are two separate layers. An endpoint may be permitted at the HTTP path level while the service method still requires a specific scope.

Service example:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
class SecureOrdersService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    Mono<OrderResponse> read(String id) {
        return Mono.just(new OrderResponse(id, "CREATED"));
    }
}
~~~

With reactive method security, methods return reactive types like `Mono`/`Flux` so Spring Security can apply authorization during reactive execution. Configuration must enable `@EnableReactiveMethodSecurity`.

### 10.1. Testing Method Security over HTTP

An HTTP test using a mock JWT with the appropriate scope:

~~~java
webTestClient
    .mutateWith(mockJwt().jwt(jwt ->
        jwt.claim("scope", "orders.read")))
    .get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk();
~~~

With a token missing the scope:

~~~java
webTestClient
    .mutateWith(mockJwt().jwt(jwt ->
        jwt.claim("scope", "orders.write")))
    .get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isForbidden();
~~~

To test method security independently of HTTP mapping, you can invoke the service bean from the test context and subscribe to the result. However, confirm that the call goes through the Spring proxy; direct internal method calls within the same class (self-invocation) can bypass proxy-based method security.

### 10.2. Testing Method Security Without Relying Solely on Controller Status

If an endpoint has a path rule `hasAuthority("SCOPE_orders.read")` and the method also requires the same authority, a missing-scope test may be blocked at the path before reaching the service method. To prove the method annotation independently, you can test with an endpoint that allows authenticated users at the path level while the service method requires the scope, or test the service proxy directly.

## 11. Testing Multiple SecurityWebFilterChains

A WebFlux application may declare multiple `SecurityWebFilterChain` beans, for example:

- An API chain for `/api/**`.
- An Actuator chain for `/actuator/**`.
- A browser/login chain for remaining UI routes.

Spring Security selects the first chain whose matcher matches according to `@Order`. Tests must prove that **requests enter the intended chain**, not merely that some chain executed.

### 11.1. Map Out a Route Table Before Writing Tests

| Request path | Expected chain | Authentication | Permission |
|---|---|---|---|
| `/api/orders/42` | API Resource Server | Bearer JWT | `SCOPE_orders.read` |
| `/actuator/health` | Actuator policy | Per exposure policy | May be public |
| `/ui/profile` | Browser/session chain | OAuth2 Login/session | Authenticated user |

### 11.2. Testing Each Route Zone

~~~java
@Test
void apiRouteRequiresBearerAuthentication() {
    webTestClient.get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isUnauthorized();
}

@Test
void healthEndpointUsesItsConfiguredPolicy() {
    webTestClient.get()
        .uri("/actuator/health")
        .exchange()
        .expectStatus().isOk();
}
~~~

The health route example is only public if the chain/actuator exposure policy actually permits it. Do not copy a `200` expectation blindly to every application.

### 11.3. Incorrect Chain Order Can Skew Tests

If a broader chain like `anyExchange()` comes before the `/api/**` chain, API requests may be handled by the broader chain and skip the JWT Resource Server config. Testing representative routes for each chain helps catch incorrect matchers or ordering.

When multiple chains exist, use a real test token for at least one key API request to confirm that the chain with the real decoder/validators is selected.

## 12. Testing a Custom JWT Authority Converter

By default, Spring Security converts scopes in the `scope` or `scp` claim into authorities prefixed with `SCOPE_`. Some issuers use custom claims like `roles`, `permissions`, or nested structures. When an application has a custom converter, that mapping needs to be tested.

### 12.1. Example Policy Using a roles Claim

Suppose the application wants to map:

~~~json
{
  "sub": "alice",
  "roles": ["ORDER_READER", "ORDER_APPROVER"]
}
~~~

to authorities:

~~~text
ROLE_ORDER_READER
ROLE_ORDER_APPROVER
~~~

Do not assume Spring Security automatically maps every `roles` claim according to your application's conventions. The converter must be explicitly configured.

### 12.2. Testing the Converter at the Authorization Layer

If the converter is designed as a standalone bean, you can directly unit-test converting claims to authorities using a test-constructed `Jwt` object. Then add an integration test confirming that the converter bean is actually wired into the Resource Server:

~~~java
webTestClient
    .mutateWith(mockJwt().jwt(jwt -> jwt
        .claim("roles", List.of("ORDER_READER"))))
    .get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk();
~~~

This example only succeeds if the `mockJwt` configurer or test authentication setup uses the same expected authority mapping. If default `mockJwt` still only reads `scope`, set authorities directly for authorization tests and write separate tests for the real converter. To confirm the converter is wired into the decoder, send a genuinely signed JWT in a request as shown earlier.

### 12.3. Testing Incorrect Claim Mappings

A token with `roles` equal to `ORDER_APPROVER` should not accidentally receive permission to read orders if policy only grants that permission to `ORDER_READER`. Create negative cases for similar roles/permissions to detect overly broad prefixes or mappings.

## 13. Verifying Methods, Headers, and Response Bodies

`WebTestClient` can verify an endpoint's entire HTTP contract after a request passes the security chain.

### 13.1. Checking Status and JSON

~~~java
webTestClient
    .mutateWith(mockJwt().jwt(jwt ->
        jwt.claim("scope", "orders.read")))
    .get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBody()
    .jsonPath("$.id").isEqualTo("42")
    .jsonPath("$.status").isEqualTo("CREATED");
~~~

Security tests should not only assert status codes when endpoints have important response contracts. You can verify the body, content type, cache headers, and response headers required by application policy.

### 13.2. Testing Individual HTTP Methods

GET and POST may require different scopes. Test both:

~~~java
@Test
void readScopeCannotCreateOrder() {
    webTestClient
        .mutateWith(mockJwt().jwt(jwt ->
            jwt.claim("scope", "orders.read")))
        .post()
        .uri("/api/orders")
        .bodyValue(new CreateOrderRequest("sku-123", 2))
        .exchange()
        .expectStatus().isForbidden();
}
~~~

If CSRF is still enabled, the POST test needs a CSRF token; if the API has disabled CSRF under a stateless bearer policy, the test only needs scope authorization.

### 13.3. Testing Business Errors After Security

A principal with a valid scope can still receive `404` when an order does not exist:

~~~java
webTestClient
    .mutateWith(mockJwt().jwt(jwt ->
        jwt.claim("scope", "orders.read")))
    .get()
    .uri("/api/orders/missing")
    .exchange()
    .expectStatus().isNotFound();
~~~

This proves the request passed authentication/authorization before reaching the business handler. Do not return `404` for all security errors to mask chain configuration; keep response semantics consistent with API policy.

## 14. Reactive Execution and Context Propagation in Tests

WebFlux security stores `SecurityContext` in the reactive context. Consequently, how tests or service code are written can affect whether `Authentication` is visible in the reactive pipeline.

### 14.1. Do Not Block the Reactive Pipeline to Read SecurityContext

In WebFlux production code, avoid:

~~~java
// Not recommended inside a reactive request pipeline
Authentication authentication =
    ReactiveSecurityContextHolder.getContext().block()
        .getAuthentication();
~~~

Instead, compose the reactive chain:

~~~java
return ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .flatMap(authentication -> service.loadFor(authentication));
~~~

`WebTestClient` subscribes to the request pipeline and awaits the response on the test exchange. There is no need to call `block` in tests to retrieve `Authentication`; assert the response or use reactive test utilities at the service layer.

### 14.2. Testing Principals Injected into Handlers

A controller can accept the principal:

~~~java
@GetMapping("/me")
Mono<Map<String, String>> me(@AuthenticationPrincipal Jwt jwt) {
    return Mono.just(Map.of("subject", jwt.getSubject()));
}
~~~

Testing with a mock JWT:

~~~java
webTestClient
    .mutateWith(mockJwt().jwt(jwt -> jwt.subject("alice")))
    .get()
    .uri("/api/me")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.subject").isEqualTo("alice");
~~~

For controllers accepting `@AuthenticationPrincipal`, the principal type depends on the `Authentication` created. If a custom authentication converter is used, the principal might no longer be a `Jwt`; tests should verify the expected principal type.

### 14.3. Async Work Does Not Automatically Inherit Request Context

Do not assume `SecurityContext` is automatically propagated to every executor, scheduler, or background task. If a handler dispatches work to a separate thread pool, design controlled context propagation. Tests must confirm user context is passed where needed and does not leak to other requests.

Do not store `SecurityContext` in a static mutable field to make tests pass; doing so can cause cross-request data leakage.

## 15. Testing CSRF, CORS, and Security Response Headers

CSRF and CORS are two different mechanisms:

- CSRF controls requests made on behalf of a browser session/cookie.
- CORS determines which browser origins are allowed to read responses and send requests requiring preflight headers/methods.

### 15.1. Testing CORS Preflight

If a browser client sends an Authorization header or custom headers, test OPTIONS preflight:

~~~java
webTestClient.options()
    .uri("/api/orders")
    .header(HttpHeaders.ORIGIN, "https://shop.example.test")
    .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
    .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS, "authorization")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().valueEquals(
        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
        "https://shop.example.test");
~~~

The exact response depends on the CORS configuration and version. Verify the origin allowlist, methods, headers, credentials, and exposed response headers against the frontend contract. Do not allow all origins together with credentials just to simplify tests.

### 15.2. CORS Preflight Is Not Proof of Authentication

Preflight OPTIONS requests are usually handled before the browser sends the actual request with Authorization. An `OPTIONS 200` does not prove GET/POST requests are authenticated or authorized. Test actual requests separately.

### 15.3. Security Headers

If the API or browser app has policies for HSTS, cache control, content type options, or CSP, check response headers at the HTTP boundary:

~~~java
webTestClient.get()
    .uri("/public/health")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().exists("X-Content-Type-Options");
~~~

Do not assert a header if the application does not configure it or has no corresponding requirement. APIs and browser UIs may require different security header policies.

## 16. Troubleshooting WebTestClient and SecurityWebFilterChain

| Symptom | Common cause | What to check |
|---|---|---|
| Protected endpoint returns 200 without a token | Security chain not installed on test client or matcher does not match | Bind application context, apply `springSecurity`, check chain order/matcher |
| All requests return 401 including `mockJwt` | Test client lacks security test configurer or route hits another chain | Check `WebTestClient` builder, selected filter chain, and `spring-security-test` dependency |
| `mockJwt` has correct scope but returns 403 | Authority prefix/custom converter differs from expectations | Inspect Authentication authorities and the real converter |
| Genuinely signed token returns 401 | Wrong signature, issuer, audience, exp/nbf, or decoder wiring | Verify each validator; check the corresponding public key |
| Wrong-audience token still returns 200 | Audience validator not attached to the real decoder or test uses `mockJwt` | Send a signed JWT via Bearer header and inspect the decoder bean |
| POST returns 403 despite correct scope | CSRF is enabled and request lacks a token | Use `csrf()` when required by policy or review stateless API CSRF policy |
| `@WebFluxTest` test lacks `SecurityWebFilterChain` | Slice did not import the security configuration | Import the required chain/config into the slice |
| Test context calls real issuer/JWKS | Auto-configuration discovery depends on the network | Use a test decoder/JWK fixture or local mock issuer |
| Method security does not block | Reactive method security not enabled, call bypasses proxy, or unsuitable return type | Check annotations/configuration/proxy and reactive return type |
| Request across multiple chains yields unexpected results | Wrong `@Order` or overly broad `securityMatcher` | Test each path and chain matcher |
| `SecurityContext` lost in async flow | Reactive context not propagated to execution path | Check Reactor context and custom schedulers/executors |
| CORS OPTIONS succeeds but GET fails | Preflight only checks CORS, not the Bearer token | Test the actual request separately |

### 16.1. Enabling Security Logging with Care

In test environments, you can raise the log level for Spring Security to understand which chain/provider is invoked:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
~~~

Do not enable verbose HTTP logging with raw Authorization headers in production. If logs contain tokens or sensitive claims, apply redaction and restrict access.

### 16.2. Determining Whether a Test Uses a Mock or Real Decoder

Ask three questions:

1. Does the request use `mutateWith(mockJwt())`? If yes, Authentication is mocked and the decoder is typically bypassed.
2. Does the request carry `Authorization: Bearer` with a signed JWT? If yes, the Resource Server filter can invoke the real decoder.
3. Which `ReactiveJwtDecoder` bean in the test context is used by the chain? Check test config/auto-configuration and bean selection.

If the goal is audience/signature validation, you must have tests covering questions 2 and 3.

## 17. Checklist for Designing a WebTestClient Security Test Suite

### 17.1. Test Setup

- [ ] Confirmed whether the application is WebFlux reactive or Servlet MVC.
- [ ] Appropriate `spring-boot-starter-webflux` and `spring-security-test` dependencies are present.
- [ ] `WebTestClient` is bound to the application context or server matching the scope under test.
- [ ] If bound to the application context, `springSecurity()` is applied.
- [ ] The actual `SecurityWebFilterChain` is imported/initialized in the test context.
- [ ] If using `@WebFluxTest`, the necessary security configuration is imported.
- [ ] Unit/slice tests do not depend on an external Authorization Server/JWKS.

### 17.2. Authentication and Authorization

- [ ] Protected routes without a token are rejected (typically 401).
- [ ] Public routes are accessible according to policy.
- [ ] `mockJwt` with sufficient authority is allowed.
- [ ] `mockJwt` missing scope is denied (typically 403).
- [ ] Distinguished `mockUser`/`mockAuthentication` from JWT Resource Server authentication.
- [ ] Custom authority converter has dedicated tests.
- [ ] Method security and path authorization are tested at the appropriate layers.
- [ ] Multiple `SecurityWebFilterChain` instances are tested for matcher/order.

### 17.3. Token Validation

- [ ] Tests exist for genuinely signed JWTs via Bearer header and real `ReactiveJwtDecoder`.
- [ ] Tokens with valid issuer/audience/time/signature are accepted.
- [ ] Tokens with invalid signatures are rejected.
- [ ] Tokens with invalid issuers are rejected.
- [ ] Tokens with invalid audiences are rejected.
- [ ] Expired/not-before-invalid tokens are rejected.
- [ ] Valid tokens missing scope are distinguished from invalid tokens.
- [ ] Test decoder uses a dedicated test key, never the production private key.

### 17.4. HTTP and Operations

- [ ] CSRF tests reflect the application's actual policy.
- [ ] CORS preflight and actual requests are tested separately.
- [ ] Response status/body/headers are asserted where contracts exist.
- [ ] Reactive `SecurityContext` is neither blocked nor stored statically.
- [ ] Async context propagation is tested if the application uses custom schedulers/executors.
- [ ] Access tokens or raw Authorization headers are not logged.
- [ ] Slice tests and full integration tests have clearly defined scopes.

## 18. Conclusion

`WebTestClient` is the natural HTTP testing tool for WebFlux. When the goal is to test `SecurityWebFilterChain`, include the real security filters in the test client via application context binding with `springSecurity()`, or use a Spring Boot integration test with an auto-configured `WebTestClient`.

For fast authorization checks, `mockJwt()` creates a mock `Authentication` with the desired claims/authorities. It is useful for 401/403, scope rules, controllers, and method security, but it does not run JWT signature validation. For issuer, audience, expiry, and signatures, create a genuinely test-signed JWT, send it in the Authorization Bearer header, and let `ReactiveJwtDecoder` verify it.

A solid test suite should distinguish:

~~~text
Authentication:
    no token / invalid token → reject
    valid JWT → authenticated

Authorization:
    valid principal + required scope → allow
    valid principal + missing scope → deny

HTTP/application:
    CSRF, CORS, route matcher, method security,
    response body and business errors
~~~

WebFlux security relies on the reactive context and the `WebFilter` chain, so do not use Servlet test setups as if they were the same runtime. Testing the right chain, the right decoder, the right context, and the right application policy is what makes `WebTestClient` results meaningful.

## References

- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
- [Spring Security — Reactive Test Support](https://docs.spring.io/spring-security/reference/reactive/test/index.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/index.html)
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security — CSRF Protection for WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Boot — @WebFluxTest](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/test/autoconfigure/web/reactive/WebFluxTest.html)
- [Spring Security — SecurityMockServerConfigurers Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.html)
- [Spring Security — ReactiveJwtDecoder Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/ReactiveJwtDecoder.html)
- [Spring Security — NimbusReactiveJwtDecoder Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)

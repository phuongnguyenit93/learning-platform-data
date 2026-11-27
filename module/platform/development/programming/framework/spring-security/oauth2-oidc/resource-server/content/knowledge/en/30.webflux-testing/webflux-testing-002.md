# mockJwt() and Customizing Claims and Authorities

When testing a **Spring Security WebFlux Resource Server application using JWT access tokens**, you often need to verify whether routes require the right scopes, which principal/claims controllers read, and whether method security blocks the right users. These tests do not necessarily have to generate signed JWTs or call an Authorization Server. Spring Security Test provides **§mockJwt()§** to construct a mock JWT authentication inside a **WebTestClient** request.

§mockJwt()§ is especially useful when focusing on post-authentication handling:

- Customizing claims such as §sub§, §iss§, §aud§, §tenant_id§, or §client_id§.
- Assigning authorities such as §SCOPE_orders.read§ and §ROLE_ADMIN§.
- Testing §JwtAuthenticationToken§, §@AuthenticationPrincipal Jwt§, and reactive controllers.
- Testing HTTP authorization, §@PreAuthorize§, and 401/403 cases.

However, §mockJwt()§ **pre-populates an already-authenticated Authentication for the test**. It does not run §ReactiveJwtDecoder§, does not verify the JWT signature, does not fetch JWKS, does not check issuer/audience/expiry with production validators, and does not call the Authorization Server. To test those steps, you must send a Bearer JWT through the filter chain with a test decoder or a test issuer/JWKS.

> **Rule of thumb:** §mockJwt()§ tests how the application handles a JWT principal after authentication; Bearer-header integration tests check how the application authenticates a JWT.

This lesson belongs to the **WebFlux Testing** chapter in the Spring Security OAuth 2.0 OIDC Resource Server module. It covers the test API, customizing claims and authorities, controller binding, HTTP/method authorization, configuring the WebFlux test context, and distinguishing mock authentication from JWT decoder integration.

## 1. JWT Resource Server in WebFlux

When a client sends a JWT access token to a WebFlux API, Spring Security typically executes:

~~~mermaid
sequenceDiagram
    participant C as OAuth Client
    participant API as WebFlux Resource Server
    participant AS as Authorization Server / JWKS
    C->>API: Authorization: Bearer JWT
    API->>API: AuthenticationWebFilter
    API->>API: BearerTokenAuthenticationConverter
    API->>API: ReactiveAuthenticationManager
    API->>AS: Fetch/refresh JWKS when needed
    API->>API: ReactiveJwtDecoder verifies token
    API->>API: Build JwtAuthenticationToken
    API->>API: Authorization + controller
    API-->>C: Response
~~~

Key components:

| Component | Role |
|---|---|
| §AuthenticationWebFilter§ | Reactive security filter that handles authentication |
| §ServerBearerTokenAuthenticationConverter§ | Reads the Bearer token from the request |
| §ReactiveAuthenticationManager§ | Coordinates asynchronous authentication |
| §JwtReactiveAuthenticationManager§ | Uses the decoder to verify the JWT and build authentication |
| §ReactiveJwtDecoder§ | Decodes/verifies the JWT, checks the signature and configured validators |
| §JwtAuthenticationToken§ | Authentication holding the JWT principal and authorities |
| §ReactiveAuthorizationManager§ | Decides access permissions for exchanges/methods |
| §ReactiveSecurityContextHolder§ | Accesses the SecurityContext within the reactive execution context |

A test request using §mockJwt()§ skips Bearer token parsing, the decoder, and JWKS. The helper places a §JwtAuthenticationToken§ into the security context so authorization and controllers can be tested.

## 2. What Is §mockJwt()§ and Where to Import It?

§mockJwt()§ is a **WebTestClient configurer** in §spring-security-test§. The API resides in §SecurityMockServerConfigurers§ of the reactive test support package.

Static import:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;
~~~

Gradle dependency:

~~~groovy
dependencies {
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Maven dependency:

~~~xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

If the project uses the Spring Boot BOM, let dependency management pick the version matching the Spring Security runtime. Do not pin a separate test module version from a different runtime line.

### 2.1. Basic Usage

With a Spring Boot-configured §WebTestClient§:

~~~java
@Test
void requestWithMockJwtIsAuthenticated() {
    webTestClient
        .mutateWith(mockJwt())
        .get()
        .uri("/api/orders")
        .exchange()
        .expectStatus().isOk();
}
~~~

§mutateWith(mockJwt())§ applies mock JWT authentication to the request sent by the mutated client. This is the common usage in reactive integration tests.

### 2.2. The Test Helper Does Not Need a Compact JWT

The test does not need to build a three-part JWT string:

~~~text
base64url(header).base64url(payload).signature
~~~

§mockJwt()§ constructs a §Jwt§ object along with a §JwtAuthenticationToken§ in the test context. The default token/header/claims values are fixtures provided by the helper; they do not represent a token signed by a real issuer.

### 2.3. Do Not Confuse with Servlet MockMvc

WebFlux uses:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;
~~~

Servlet MVC uses a different request post-processor in §SecurityMockMvcRequestPostProcessors§. Do not accidentally import the MockMvc helper when testing §WebTestClient§. The two stacks configure test requests differently despite sharing the name §mockJwt()§.

## 3. Customizing JWT Claims

§mockJwt()§ allows customizing §Jwt.Builder§ via a consumer function. You can set claims reflecting the principal and metadata used by your API.

### 3.1. Setting Subject and Custom Claims

~~~java
webTestClient
    .mutateWith(mockJwt().jwt(jwt -> jwt
        .claim("sub", "alice")
        .claim("tenant_id", "tenant-a")
        .claim("client_id", "orders-web")
        .claim("email", "alice@example.test")))
    .get()
    .uri("/api/me")
    .exchange()
    .expectStatus().isOk();
~~~

The claims above are mock test data. For example:

| Claim | Common meaning |
|---|---|
| §sub§ | Subject identifying the user/service within the issuer |
| §tenant_id§ | Tenant according to the Authorization Server contract |
| §client_id§ | OAuth client associated with the access token |
| §email§ | Profile claim if issued by the issuer and the API has a reason to use it |

Do not treat adding §tenant_id§ or §email§ manually in a test as proof that the real issuer emits that claim. Test fixtures must reflect the schema agreed upon with the issuer.

### 3.2. Setting Issuer and Audience in the Fixture

If a controller or service reads issuer/audience:

~~~java
webTestClient
    .mutateWith(mockJwt().jwt(jwt -> jwt
        .claim("iss", "https://identity.example.test")
        .claim("sub", "alice")
        .claim("aud", List.of("orders-api"))
        .claim("tenant_id", "tenant-a")))
    .get()
    .uri("/api/me")
    .exchange()
    .expectStatus().isOk();
~~~

Setting §iss§ and §aud§ tests code that consumes those claims. It **does not run the issuer validator or audience validator**. A test with §aud=orders-api§ can still pass even if the production decoder has the wrong audience configured, because §mockJwt()§ bypasses the decoder. Write dedicated decoder tests for validation.

### 3.3. Timestamps and Token ID

If business code reads timestamp claims or the token ID, you can include them in the fixture:

~~~java
webTestClient
    .mutateWith(mockJwt().jwt(jwt -> jwt
        .claim("sub", "alice")
        .claim("jti", "test-token-001")
        .claim("iat", Instant.parse("2026-01-01T10:00:00Z"))
        .claim("exp", Instant.parse("2026-01-01T10:10:00Z"))))
    .get()
    .uri("/api/token-info")
    .exchange()
    .expectStatus().isOk();
~~~

Depending on the Spring Security version, the builder may provide convenience methods for timestamps/subject; use the builder API matching your project's version. For custom claims, ensure data types are compatible with NumericDate and the application's mappers.

Do not use this fixture to prove the expiry validator runs. That test requires a Bearer token going through §ReactiveJwtDecoder§ or testing the validator directly.

### 3.4. Default Claims

§mockJwt()§ provides a default JWT fixture so tests can run without declaring every field. Default claims/authorities are an implementation detail of Spring Security Test and may change across versions. Business tests should explicitly set §sub§, §aud§, tenant, and required authorities instead of relying implicitly on defaults.

## 4. Customizing Authorities

Claims describe token data; **authorities** are the permissions checked by the Spring Security authorization engine. The two are related, but should not be treated as identical.

### 4.1. Setting a Scope Authority Directly

If the endpoint requires §SCOPE_orders.read§:

~~~java
webTestClient
    .mutateWith(mockJwt().authorities(
        new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get()
    .uri("/api/orders")
    .exchange()
    .expectStatus().isOk();
~~~

Import:

~~~java
import org.springframework.security.core.authority.SimpleGrantedAuthority;
~~~

When calling §authorities(...)§, the test explicitly defines the mock authentication's permissions. This is a clear way to test an authorization branch without depending on the claim converter.

### 4.2. Assigning Multiple Authorities

~~~java
webTestClient
    .mutateWith(mockJwt().authorities(
        new SimpleGrantedAuthority("SCOPE_orders.read"),
        new SimpleGrantedAuthority("SCOPE_orders.write"),
        new SimpleGrantedAuthority("ROLE_SUPPORT")))
    .get()
    .uri("/api/orders")
    .exchange()
    .expectStatus().isOk();
~~~

This example includes two scopes and one role. Assign only the permissions needed for the test; do not grant §ROLE_ADMIN§ by default to every mock principal, as tests could miss least-privilege bugs.

### 4.3. Scope Claim vs. Scope Authority

A JWT access token may carry:

~~~json
{
  "scope": "orders.read orders.write"
}
~~~

Spring Security typically uses §JwtGrantedAuthoritiesConverter§ to map scopes to:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Some issuers use the §scp§ claim or an array format; in those cases the application may configure a custom converter. In tests:

- If you want to test a controller/authorization with a defined set of permissions, set §.authorities(...)§.
- If you want to test how the production converter reads the §scope§/§scp§ claim, test the converter separately or send a Bearer JWT through the authentication pipeline with a test decoder.

Do not assume that adding §scope§ to claims via §.jwt(...)§ always tests your application's custom converter. §mockJwt()§ already constructs the authentication and may use the test helper's default converter; the custom production converter is not necessarily invoked.

### 4.4. Permissions and Claims Are Separate Inputs

Example:

~~~java
webTestClient
    .mutateWith(mockJwt()
        .jwt(jwt -> jwt
            .claim("sub", "alice")
            .claim("tenant_id", "tenant-a")
            .claim("scope", "orders.read"))
        .authorities(new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get()
    .uri("/api/orders")
    .exchange()
    .expectStatus().isOk();
~~~

This test sets up both metadata and an authority. If the production converter is broken and fails to map scopes, the test can still pass because the authority was assigned directly. Therefore, this is an **authorization test**, not a converter test.

## 5. Controllers Receiving the JWT Principal in WebFlux

After JWT authentication succeeds, a controller can receive the principal as a §Jwt§ or §JwtAuthenticationToken§.

### 5.1. Using §@AuthenticationPrincipal Jwt§

~~~java
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class CurrentUserController {

    @GetMapping("/api/me")
    Mono<Map<String, String>> me(@AuthenticationPrincipal Jwt jwt) {
        return Mono.just(Map.of(
            "subject", jwt.getSubject(),
            "tenant", jwt.getClaimAsString("tenant_id")
        ));
    }
}
~~~

Test:

~~~java
webTestClient
    .mutateWith(mockJwt().jwt(jwt -> jwt
        .claim("sub", "alice")
        .claim("tenant_id", "tenant-a")))
    .get()
    .uri("/api/me")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.subject").isEqualTo("alice")
    .jsonPath("$.tenant").isEqualTo("tenant-a");
~~~

§@AuthenticationPrincipal§ retrieves the principal from the current SecurityContext. For a JWT Resource Server, the principal is a §Jwt§ object; it is not the general §OAuth2AuthenticatedPrincipal§ used in opaque-token authentication.

### 5.2. Using §JwtAuthenticationToken§

If both authorities and the JWT are needed:

~~~java
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class TokenDetailsController {

    @GetMapping("/api/token-details")
    Mono<Map<String, Object>> details(
            @AuthenticationPrincipal JwtAuthenticationToken authentication) {
        return Mono.just(Map.of(
            "subject", authentication.getName(),
            "authorities", authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .toList(),
            "claims", authentication.getToken().getClaims()
        ));
    }
}
~~~

In many cases, injecting §Jwt§ is sufficient. If a controller needs authentication metadata, you can use §Authentication§ or §JwtAuthenticationToken§ via supported method argument resolvers. Avoid returning all claims to clients in production as they may contain internal details or PII; the example only illustrates access patterns.

### 5.3. Using §ReactiveSecurityContextHolder§ in Services

In a reactive service that does not receive the principal directly via a method argument, you can read the SecurityContext from the Reactor context:

~~~java
Mono<String> currentSubject() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .cast(JwtAuthenticationToken.class)
        .map(JwtAuthenticationToken::getToken)
        .map(Jwt::getSubject);
}
~~~

Imports:

~~~java
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.oauth2.jwt.Jwt;
~~~

Tests with §mockJwt()§ can verify the service reads the subject from the reactive context. Avoid calling §subscribe()§ inside the service; return a §Mono§ so Spring WebFlux preserves the context across the pipeline.

## 6. Configuring WebFlux Security for Testing

A JWT Resource Server API may be configured as:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
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

In production, §ReactiveJwtDecoder§ must be supplied via issuer/JWK configuration or an explicit bean. This example only illustrates the security chain. If the test context requires a decoder bean to initialize the filter chain, provide a test bean even if §mockJwt()§ tests do not invoke it.

### 6.1. Do Not Disable CSRF Mechanically

APIs that only accept Bearer tokens via the Authorization header typically do not use cookies sent automatically by browsers. However, an application may have session/cookie endpoints in the same context. Only disable CSRF when the credential model and chain matcher allow it; do not copy a stateless configuration across the entire application just to make POST tests easier.

### 6.2. Separate Chains If the Application Is Both a Client and an API

A WebFlux application may use both OAuth2 Login and act as a Resource Server. Separate rules for browser sessions and Bearer APIs to avoid having §mockJwt()§ tests accidentally verify a different chain than the one protecting the endpoint. With multiple chains, confirm matchers/ordering and the endpoint under test.

## 7. Full Test with §@WebFluxTest§

§@WebFluxTest§ is suitable for testing controllers and the WebFlux slice. §WebTestClient§ is injected to send requests through the test server.

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.reactive.server.WebTestClient;

@WebFluxTest(CurrentUserController.class)
@Import(ApiSecurityConfiguration.class)
class CurrentUserControllerTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void returnsSubjectAndTenantFromJwt() {
        webTestClient
            .mutateWith(mockJwt().jwt(jwt -> jwt
                .claim("sub", "alice")
                .claim("tenant_id", "tenant-a")))
            .get()
            .uri("/api/me")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.subject").isEqualTo("alice")
            .jsonPath("$.tenant").isEqualTo("tenant-a");
    }
}
~~~

Depending on the Spring Boot version and Resource Server setup, the context may require a §ReactiveJwtDecoder§ bean even though the mock post-processor bypasses the decoder at runtime. In that case, provide a test bean or import a test configuration. Do not configure tests to accidentally perform real issuer discovery when the test only needs mock authentication.

### 7.1. Test Configuration Providing an Unused Decoder

A test decoder can fail fast if a request accidentally enters the Bearer authentication path:

~~~java
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import reactor.core.publisher.Mono;

@TestConfiguration
class MockJwtTestConfiguration {

    @Bean
    @Primary
    ReactiveJwtDecoder testReactiveJwtDecoder() {
        return token -> Mono.error(
            new BadJwtException("Unexpected decoder invocation in mockJwt test"));
    }
}
~~~

Import this configuration into the test slice when needed:

~~~java
@Import({ApiSecurityConfiguration.class, MockJwtTestConfiguration.class})
~~~

This bean does not verify tokens; it makes explicit that tests expect §mockJwt()§ to pre-populate authentication. If a test needs to exercise the decoder, use a dedicated test decoder with the corresponding behavior instead of this fail-fast bean.

### 7.2. If Using §bindToApplicationContext§

When building §WebTestClient§ manually instead of using Boot test auto-configuration, attach the Spring Security WebFlux filter chain:

~~~java
webTestClient = WebTestClient
    .bindToApplicationContext(context)
    .apply(springSecurity())
    .configureClient()
    .build();
~~~

Static import:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;
~~~

Without integrating the filter chain, the test may simply invoke the controller without checking real authorization. Ensure both §mockJwt()§ and security filters participate in the request pipeline.

## 8. Testing 401, 403, and 2xx

Suppose the GET endpoint requires §SCOPE_orders.read§ and all other endpoints require authentication.

### 8.1. No Authentication: 401

~~~java
@Test
void requestWithoutJwtIsUnauthorized() {
    webTestClient
        .get()
        .uri("/api/orders")
        .exchange()
        .expectStatus().isUnauthorized();
}
~~~

The request does not use §mockJwt()§ because the goal is to test the unauthenticated case. If the endpoint is covered by §permitAll()§ or protected by a different matcher, the expected status will differ.

### 8.2. With JWT but Missing Scope: 403

~~~java
@Test
void jwtWithoutReadScopeIsForbidden() {
    webTestClient
        .mutateWith(mockJwt().authorities(
            new SimpleGrantedAuthority("SCOPE_profile.read")))
        .get()
        .uri("/api/orders")
        .exchange()
        .expectStatus().isForbidden();
}
~~~

The mock JWT is authenticated, but its authority does not satisfy the policy. This is the right test to prove the endpoint does not allow arbitrary principals simply for being logged in.

### 8.3. With the Right Scope: 200

~~~java
@Test
void jwtWithReadScopeCanReadOrders() {
    webTestClient
        .mutateWith(mockJwt()
            .jwt(jwt -> jwt.claim("sub", "alice"))
            .authorities(new SimpleGrantedAuthority("SCOPE_orders.read")))
        .get()
        .uri("/api/orders")
        .exchange()
        .expectStatus().isOk();
}
~~~

This test verifies the authorization rule after authentication. It does not prove that a genuinely signed JWT will be accepted by the decoder.

### 8.4. POST Requiring the Write Scope

~~~java
@Test
void readOnlyJwtCannotCreateOrder() {
    webTestClient
        .mutateWith(mockJwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")))
        .post()
        .uri("/api/orders")
        .bodyValue(Map.of("sku", "SKU-100"))
        .exchange()
        .expectStatus().isForbidden();
}
~~~

If the POST endpoint uses CSRF or has a custom filter, the status may reflect that layer before authorization. In a pure Bearer API, CSRF configuration must match the threat model. Tests need to know whether they are testing CSRF or scope.

## 9. Method Security in WebFlux

HTTP matchers are not the only authorization layer. A reactive service can use §@PreAuthorize§ to check scopes:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
class OrderQueryService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    Mono<String> listOrders() {
        return Mono.just("orders");
    }
}
~~~

Enable reactive method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
class ReactiveMethodSecurityConfiguration {
}
~~~

### 9.1. Testing Method Security with mockJwt

Invoke the endpoint through the controller/service proxy:

~~~java
@Test
void methodSecurityAllowsReadScope() {
    webTestClient
        .mutateWith(mockJwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")))
        .get()
        .uri("/api/orders")
        .exchange()
        .expectStatus().isOk();
}
~~~

And the missing-permission case:

~~~java
@Test
void methodSecurityRejectsMissingReadScope() {
    webTestClient
        .mutateWith(mockJwt().authorities(
            new SimpleGrantedAuthority("SCOPE_profile.read")))
        .get()
        .uri("/api/orders")
        .exchange()
        .expectStatus().isForbidden();
}
~~~

Method security tests must load the §@EnableReactiveMethodSecurity§ configuration and invoke methods through the Spring bean proxy. If a test directly calls an object instantiated with §new§, annotations may not be applied.

### 9.2. Reactive Return Types

Reactive method security supports methods returning publishers when configured appropriately. Do not convert methods to blocking just to make testing easier. Verify subscription/error signals and HTTP mapping in the WebFlux pipeline.

## 10. Testing Custom Claims and Domain Authorization

An access token may contain §tenant_id§, §organization_id§, or custom business claims. Controllers/services must treat these claims as data from the authenticated principal.

### 10.1. Testing an Allowed Tenant

~~~java
@Test
void userCanReadOwnTenantOrders() {
    webTestClient
        .mutateWith(mockJwt()
            .jwt(jwt -> jwt
                .claim("sub", "alice")
                .claim("tenant_id", "tenant-a"))
            .authorities(new SimpleGrantedAuthority("SCOPE_orders.read")))
        .get()
        .uri("/api/tenants/tenant-a/orders")
        .exchange()
        .expectStatus().isOk();
}
~~~

### 10.2. Testing a Different Tenant

~~~java
@Test
void userCannotReadAnotherTenantOrders() {
    webTestClient
        .mutateWith(mockJwt()
            .jwt(jwt -> jwt
                .claim("sub", "alice")
                .claim("tenant_id", "tenant-a"))
            .authorities(new SimpleGrantedAuthority("SCOPE_orders.read")))
        .get()
        .uri("/api/tenants/tenant-b/orders")
        .exchange()
        .expectStatus().isForbidden();
}
~~~

The 403 result assumes the application actually compares the tenant in the principal with the requested tenant. §mockJwt()§ only provides the claim fixture; it does not create tenant authorization on its own. If the controller/service lacks a tenant check, both tests may return 200.

### 10.3. Subject and Issuer

A subject is typically unique only within an issuer. In a multi-issuer system, the identity key needs to combine the verified issuer and subject:

~~~text
principal identity = (verified iss, sub)
~~~

You can test the case where two issuers share the same §sub§ yet represent two distinct principals. Note that §mockJwt()§ sets claims to test identity logic; this test does not check decoder issuer validation.

## 11. Comparing §mockJwt()§ and §mockOpaqueToken()§

Spring Security Test has distinct helpers for JWT and opaque tokens:

| Aspect | §mockJwt()§ | §mockOpaqueToken()§ |
|---|---|---|
| Authentication type | JWT Resource Server | Opaque bearer Resource Server |
| Principal | §Jwt§ | §OAuth2AuthenticatedPrincipal§ |
| Authentication | §JwtAuthenticationToken§ | §BearerTokenAuthentication§ |
| Claims/attributes | JWT claims | Opaque principal attributes |
| Authorities | Customizable | Customizable |
| Real decoder/introspector | Does not invoke decoder | Does not invoke introspector |
| Common usage | WebFlux JWT tests | WebFlux opaque-token tests |

Do not use §mockJwt()§ to test a controller designed to receive an opaque principal, or §mockOpaqueToken()§ to prove JWT signature validation works. Choose the helper matching your production Resource Server type.

## 12. Limitations of §mockJwt()§ and Tests That Must Be Written Separately

§mockJwt()§ does not test:

- Whether the compact JWT parser accepts the token properly.
- Whether the JWS signature is valid.
- Key ID/JWKS rotation and algorithm allowlisting.
- Whether the issuer validator rejects unknown issuers.
- Whether the audience validator enforces the correct resource.
- Whether §exp§/§nbf§/§iat§ validators run.
- Whether the JWT access-token profile/§typ§ is correct.
- Whether a custom §ReactiveJwtDecoder§ or authentication manager is invoked.
- DPoP proofs, §cnf§ key binding, or token replay stores.

These aspects require separate decoder/validator tests, Bearer-header integration tests, or DPoP tests.

### 12.1. Testing Decoder Validators Directly

If you have a custom §OAuth2TokenValidator<Jwt>§, you can construct a §Jwt§ fixture and invoke the validator directly to verify claim checks. This proves policy logic, but not that the filter chain invokes the validator. Add a decoder integration test if you want to verify wiring.

### 12.2. Testing the Bearer Header Through the Reactive Filter Chain

Send the token in the header instead of using a mock post-processor:

~~~java
webTestClient
    .get()
    .uri("/api/orders")
    .headers(headers -> headers.setBearerAuth("test-compact-jwt"))
    .exchange()
    .expectStatus().isOk();
~~~

The test context needs to provide a test §ReactiveJwtDecoder§ with deterministic behavior. You can use a decoder stub:

~~~java
@Bean
ReactiveJwtDecoder testDecoder() {
    return token -> {
        if (!"test-compact-jwt".equals(token)) {
            return Mono.error(new BadJwtException("Unknown token"));
        }
        Jwt jwt = Jwt.withTokenValue(token)
            .header("alg", "test")
            .claim("iss", "https://issuer.test")
            .claim("sub", "alice")
            .claim("aud", List.of("orders-api"))
            .claim("scope", "orders.read")
            .issuedAt(Instant.now().minusSeconds(30))
            .expiresAt(Instant.now().plusSeconds(300))
            .build();
        return Mono.just(jwt);
    };
}
~~~

This is a **stub decoder**; it does not verify a compact JWT signature. It tests Bearer filter → manager → decoder wiring and everything downstream of the decoder. To test JWS signatures, JWKS, key rotation, and algorithm policies, use a real test decoder/JWK or a test issuer with a private key/public JWKS.

### 12.3. Inactive/Error Tests Do Not Belong to mockJwt

JWT Resource Servers do not call an introspection endpoint for standard JWTs. Cases like invalid signatures, wrong issuers, or expired tokens require decoder tests. If you want to test opaque token §active=false§, use an opaque introspector test; do not apply opaque semantics to §mockJwt()§.

## 13. §@WebFluxTest§, §@SpringBootTest§, and WebTestClient Setup

### 13.1. §@WebFluxTest§

Use when you only need the controller slice:

~~~java
@WebFluxTest(controllers = OrdersController.class)
@Import({ApiSecurityConfiguration.class,
         ReactiveMethodSecurityConfiguration.class})
class OrdersControllerTest {
    @Autowired
    WebTestClient webTestClient;
}
~~~

Import the security configuration if the slice does not load it automatically. Services/repositories depended on by the controller may need mock beans using your Spring Boot version's test mechanism.

### 13.2. §@SpringBootTest§

Use when you want to test the application context, filter chains, service proxies, and method security close to production:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class OrdersSecurityIntegrationTest {
    @Autowired
    WebTestClient webTestClient;
}
~~~

This test initializes more components. Test configuration must isolate databases, message brokers, and external identity providers; never let CI depend on the production issuer.

### 13.3. §bindToApplicationContext§

If creating the client manually:

~~~java
WebTestClient webTestClient = WebTestClient
    .bindToApplicationContext(context)
    .apply(springSecurity())
    .configureClient()
    .build();
~~~

Static import:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;
~~~

Ensure the Spring Security WebFlux filter chain is attached to the client. If binding directly to a controller without security filters, results do not represent the application's HTTP authorization.

## 14. Testing Converters That Map Claims to Authorities

Production may configure §JwtGrantedAuthoritiesConverter§ or a custom converter. For example, an issuer sends scopes in a §permissions§ array:

~~~json
{
  "sub": "alice",
  "permissions": ["orders.read", "orders.write"]
}
~~~

A converter can map this to:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

When testing with:

~~~java
.mutateWith(mockJwt().authorities(
    new SimpleGrantedAuthority("SCOPE_orders.read")))
~~~

you bypass the converter. To test the converter:

1. Create a §Jwt§ fixture with the §permissions§ claim.
2. Call the production converter directly.
3. Assert the generated authorities.
4. Add a Bearer-header integration test through the authentication manager/decoder configured with that converter.

Do not assign authorities manually and conclude the converter works.

### 14.1. Testing the Converter Directly

~~~java
@Test
void permissionsClaimMapsToAuthorities() {
    Jwt jwt = Jwt.withTokenValue("test")
        .header("alg", "none")
        .claim("sub", "alice")
        .claim("permissions", List.of("orders.read", "orders.write"))
        .build();

    Collection<GrantedAuthority> authorities =
        permissionsAuthoritiesConverter.convert(jwt);

    assertThat(authorities)
        .extracting(GrantedAuthority::getAuthority)
        .containsExactlyInAnyOrder(
            "SCOPE_orders.read",
            "SCOPE_orders.write");
}
~~~

This snippet assumes the production converter §permissionsAuthoritiesConverter§ is an injected bean and uses AssertJ. This JWT fixture is strictly for converter testing; an §alg=none§ header must never be used to verify production tokens.

## 15. Common Pitfalls

| Symptom | Cause | How to fix |
|---|---|---|
§mockJwt()§ test returns 403 | Missing authority required by the endpoint | Set §.authorities(...)§ with the right scope |
Controller receives a null principal | Security filters did not run or test omits the helper | Check WebTestClient and Spring Security setup |
Controller receives wrong principal type | Endpoint expects opaque principal while testing JWT | Use the helper matching the token type |
Test passes despite invalid JWT signature | §mockJwt()§ bypasses the decoder | Send Bearer JWT through a decoder integration test |
Test passes despite wrong audience | Claims fixture does not run audience validator | Test the real validator/decoder |
Custom scope converter is broken yet test passes | Authority was assigned directly | Test the converter separately and the Bearer pipeline |
§@WithMockUser§ passes but controller fails | Principal type is not §Jwt§ | Use §mockJwt()§ |
§@AuthenticationPrincipal Jwt§ does not bind | SecurityContext lacks JwtAuthenticationToken | Check the authentication fixture and filter chain |
Reactive method security does not run | Missing §@EnableReactiveMethodSecurity§ or bypassing proxy | Import config and call via Spring bean |
WebFlux test accidentally calls real issuer | Test context uses production discovery/JWKS | Inject a test decoder and isolate properties |
POST rejected before scope check | CSRF or custom filter | Identify the rejecting layer; configure test to match policy |
Two tests using default claims behave differently after upgrade | Relied on helper defaults | Set claims/authorities explicitly |
Direct controller test returns 200 | Does not traverse security filter chain | Use WebFluxTest/SpringBootTest or apply springSecurity |
Different-tenant test still returns 200 | Missing domain authorization or only checks scope | Check tenant/owner in the service |

## 16. Test Selection Matrix

| Question | Tool |
|---|---|
Does the controller read §sub§ and §tenant_id§ properly? | §mockJwt().jwt(...)§ |
Does GET require §SCOPE_orders.read§? | §mockJwt().authorities(...)§ |
Does a missing scope return 403? | §mockJwt()§ with the wrong authority |
Does missing JWT return 401? | WebTestClient without mock authentication |
Does method security block properly? | §mockJwt()§ + reactive method security config |
Does the custom claim converter work? | Converter unit test and Bearer integration |
Is the Bearer header read? | WebTestClient + Authorization header |
Does the decoder verify signature/JWKS? | Real test decoder/JWKS |
Do issuer/audience/expiry validators run? | Validator/decoder integration test |
Does JWT key rotation work? | Test JWKS server and signed tokens |
Does opaque introspection handle active=false? | Opaque introspector test, not mockJwt |
Are DPoP proof/replay checks valid? | DPoP verifier/replay integration test |

## 17. Workflow for Writing WebFlux Tests with mockJwt()

A practical sequence:

1. **Choose the right token type:** Does the API use JWT or opaque tokens; for JWT, use §mockJwt()§.
2. **Load the filter chain:** Confirm `WebTestClient` runs the right Spring Security WebFlux filters.
3. **Build claims:** Set §sub§, tenant, issuer/audience, or metadata needed by the controller.
4. **Build authorities:** Assign exact scopes/roles for the authorization branch.
5. **Verify the controller:** Check §@AuthenticationPrincipal Jwt§ or reactive SecurityContext.
6. **Verify permissions:** Test missing token, missing scope, sufficient scope, and wrong tenant.
7. **Verify method security:** Enable reactive method security and call services via the Spring proxy.
8. **Test converters separately:** Do not pre-assign authorities if the goal is to test claim mapping.
9. **Test the decoder separately:** Send a Bearer JWT through the filter chain with a test decoder/JWKS.
10. **Keep tests independent:** Do not let mock-authentication tests accidentally call the real Authorization Server.

## 18. Conclusion

~~~text
mockJwt()
  = WebTestClient mock authentication for JWT Resource Server
  = customize Jwt claims
  = customize GrantedAuthority values
  = test controller / method / HTTP authorization

mockJwt()
  != parse a compact Bearer JWT
  != verify JWS signature or JWKS
  != run ReactiveJwtDecoder validators
  != prove issuer / audience / expiry validation

BEARER INTEGRATION TEST
  Authorization: Bearer <test JWT>
       |
       v
  AuthenticationWebFilter
       |
       v
  ReactiveAuthenticationManager
       |
       v
  ReactiveJwtDecoder
       |
       v
  JwtAuthenticationToken
       |
       v
  Authorization + Controller
~~~

§mockJwt()§ is the right tool for testing **how the application handles a JWT principal after authentication** in WebFlux. Use §.jwt(...)§ to customize claims and §.authorities(...)§ to set permissions explicitly; from there, verify controller arguments, scope rules, method security, and tenant policies.

When you need to prove real tokens are verified, send a Bearer JWT through WebTestClient and configure an appropriate §ReactiveJwtDecoder§/test JWKS. Separating mock-principal tests from decoder tests keeps results clear: one group proves authorization/controllers work with an authenticated principal, while the other proves the Resource Server only creates a principal when the JWT satisfies the trust contract.

## References

- [Spring Security Reference — Testing Reactive Applications](https://docs.spring.io/spring-security/reference/reactive/test/index.html): test support for WebFlux and WebTestClient.
- [Spring Security Reference — Testing OAuth 2.0](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): reactive OAuth2 test support and §mockJwt()§.
- [Spring Security API — SecurityMockServerConfigurers](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.html): WebTestClient configurers such as §mockJwt()§ and §springSecurity()§.
- [Spring Security Reference — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): ReactiveJwtDecoder, authentication manager, and JWT validation.
- [Spring Security API — JwtAuthenticationToken](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationToken.html): JWT authentication and authorities.
- [Spring Security API — Jwt](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/Jwt.html): JWT claims and builder.
- [Spring Security Reference — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): reactive method authorization.
- [Spring Security Reference — Reactive Test Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html): integrating Spring Security with WebTestClient.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): JWT claims such as §iss§, §sub§, §aud§, §iat§, §exp§ and §jti§.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access-token profile and validation requirements.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer token request semantics.

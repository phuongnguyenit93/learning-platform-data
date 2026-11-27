# MockMvc with the Real Spring Security Filter Chain

When testing a **Spring Security Servlet Resource Server**, we often need to verify that an HTTP request passes through the exact filter chain used by the application: the bearer token is extracted, the `AuthenticationManager` is selected, the JWT or opaque token is verified, the `SecurityContext` is established, authorization rules are applied, and the correct HTTP result is returned.

`MockMvc` allows sending requests through Spring MVC without opening a real HTTP port. When configured properly, it still runs the **real Spring Security `FilterChainProxy` and `SecurityFilterChain`** from the application context. This makes MockMvc suitable for testing many important behaviors:

- Private endpoints reject requests without a token.
- Bearer tokens with an invalid signature, issuer, audience, or that are expired are rejected.
- Valid tokens are mapped to the correct principal and authorities.
- Missing scopes result in 403.
- The right `SecurityFilterChain` is selected according to `securityMatcher` and `@Order`.
- CSRF, CORS, exception handling, and method security operate as configured.
- The JWT decoder or opaque introspector is invoked properly in the authentication path.

The key distinction is that **MockMvc can run the real filter chain while the test still mocks authentication**. For example, `.with(jwt())`, `.with(opaqueToken())`, and `@WithMockUser` typically place a pre-built `Authentication` into the `SecurityContext`; they are very useful for testing authorization, but they do not prove that the bearer filter, decoder, JWT signature, JWKS, or introspection actually work.

> **Principle:** choose the testing level based on the question you need to answer. Use mock authentication to check authorization rules; send `Authorization: Bearer ...` through the filter chain to check the authentication pipeline; use a test key/JWKS server or mock introspection server to check token verification; use a real test server/network when you need to verify TLS, proxies, and infrastructure.

This article focuses on **Spring Security Servlet with Spring MVC Test/MockMvc**. Examples use Java 17+, JUnit 5, Spring Boot, and modern Spring Security. WebFlux uses `WebTestClient` and `SecurityMockServerConfigurers`, not `MockMvc`.

## 1. What does MockMvc actually test?

MockMvc simulates the Servlet API and Spring MVC dispatch in memory. With appropriate Spring Security configuration, requests still go through the filter chain before reaching `DispatcherServlet` and the controller.

~~~text
MockMvc.perform(request)
        |
        v
Registered Servlet filters
        |
        v
FilterChainProxy
        |
        v
First matching SecurityFilterChain
        |
        +-- SecurityContextHolderFilter
        +-- CsrfFilter (if enabled)
        +-- BearerTokenAuthenticationFilter
        +-- AnonymousAuthenticationFilter
        +-- ExceptionTranslationFilter
        +-- AuthorizationFilter
        |
        v
DispatcherServlet
        |
        v
Controller / service
        |
        v
MockMvc ResultActions
~~~

The exact filter order depends on configuration and version; the diagram above describes common components, not an exhaustive list or absolute ordering for every application.

### 1.1. `FilterChainProxy` is the entry point of Spring Security

In a Servlet application, Spring Security typically registers a filter bean named:

~~~text
springSecurityFilterChain
~~~

This bean is usually a `FilterChainProxy`. It holds a list of `SecurityFilterChain` instances, evaluates request matchers in order, and selects the matching chain.

An application might have:

~~~text
@Order(1) /api/admin/**  -> admin SecurityFilterChain
@Order(2) /api/**        -> API Resource Server chain
@Order(3) /**            -> browser/fallback chain
~~~

MockMvc can only test chain selection if `FilterChainProxy` is actually attached to the MockMvc request pipeline.

### 1.2. What MockMvc does not test automatically

MockMvc does not open an HTTP socket and does not simulate the entire deployment infrastructure on its own. Therefore, it does not replace testing:

- Real TLS handshakes, server certificates, and client certificates.
- Real-world reverse proxies, load balancers, ingress, and forwarded headers.
- Real DNS, firewalls, egress policies, and network timeouts.
- HTTP connection pooling between processes.
- Actual browser CORS enforcement.
- Production container behavior such as Tomcat/Jetty/Undertow in every detail.
- A real OAuth Authorization Server, unless the test actively calls a test AS.
- Real browser cookie behavior and browser SameSite policies.

MockMvc is suitable for **Servlet filter chain and MVC integration**; infrastructure testing requires additional integration tests via a real server or staging environment.

## 2. Dependencies needed for MockMvc and Spring Security Test

With Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

`spring-boot-starter-test` provides JUnit Jupiter, Spring Test, MockMvc, AssertJ, and Mockito according to Spring Boot dependency management. `spring-security-test` provides annotations and request post processors such as:

- `@WithMockUser`
- `@WithUserDetails`
- `user()`
- `jwt()`
- `opaqueToken()`
- `authentication()`
- `csrf()`
- `httpBasic()`
- `formLogin()`

There is no need to specify a separate version for Spring Security Test if the Spring Boot BOM already manages the corresponding version. Mixing a different minor version of `spring-security-test` with the Spring Security runtime can cause method/class errors or hard-to-diagnose behavior.

## 3. Standard ways to attach the real filter chain to MockMvc

### 3.1. Using `webAppContextSetup` and `springSecurity()`

When building MockMvc manually from a `WebApplicationContext`, the standard approach is:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;

@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextConfiguration(classes = Application.class)
class ApiSecurityTests {

    @Autowired
    WebApplicationContext context;

    MockMvc mvc;

    @BeforeEach
    void setUp() {
        this.mvc = MockMvcBuilders
            .webAppContextSetup(this.context)
            .apply(springSecurity())
            .build();
    }
}
~~~

`springSecurity()` configures MockMvc with Spring Security. Specifically, it adds the `springSecurityFilterChain` bean as a filter and sets up `TestSecurityContextHolder` support for request post processors/annotations.

This is an important point: **do not simply import a `SecurityFilterChain` bean and assume MockMvc already runs it**. You must ensure `FilterChainProxy` is registered in the request pipeline.

### 3.2. Using `@SpringBootTest` and `@AutoConfigureMockMvc`

In Spring Boot applications, the more common approach is to let Boot create MockMvc:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrdersApiSecurityIntegrationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void requestWithoutTokenIsUnauthorized() throws Exception {
        mvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

`@SpringBootTest` loads the application context and `@AutoConfigureMockMvc` configures MockMvc. By default, MockMvc auto-configuration registers the application's servlet filters; the Spring Security filter chain is applied if the filter bean is in the context.

By default, keep `addFilters=true`. Configuring:

~~~java
@AutoConfigureMockMvc(addFilters = false)
~~~

prevents MockMvc from registering the application context's filters. This is a common reason why security tests return 200 even though production would return 401/403. Do not use this option for tests intended to verify the Spring Security filter chain.

### 3.3. Using `@WebMvcTest` for slice tests

`@WebMvcTest` loads only the necessary MVC slice without starting the entire application. You can import the actual security config:

~~~java
@WebMvcTest(controllers = OrdersController.class)
@Import(ApiSecurityConfiguration.class)
class OrdersControllerSecurityTests {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    OrdersService ordersService;
}
~~~

`@MockitoBean` is the modern Spring Framework annotation for replacing a bean in the test context; in older Spring Boot/Spring Framework versions, a project may use `@MockBean`. Choose the annotation matching the project's dependency version.

Notes:

- Import the exact production `SecurityFilterChain` you want to test.
- Mock dependent services/repositories so the test focuses on MVC/security.
- Do not import a permissive `TestSecurityConfiguration` and treat the result as production security.
- If `@WebMvcTest` auto-configures default security because it cannot find the application config, verify that the real chain is imported.
- Do not use `addFilters=false` if the goal is to test security.

### 3.4. When to use `standaloneSetup`?

~~~java
MockMvcBuilders
    .standaloneSetup(new OrdersController(service))
    .build();
~~~

`standaloneSetup` creates MockMvc from the provided controller without loading a full `WebApplicationContext`. It is suitable for small controller tests, but it does not automatically attach the application's full `FilterChainProxy`.

You can add the filter explicitly:

~~~java
MockMvcBuilders
    .standaloneSetup(controller)
    .apply(springSecurity(filterChainProxy))
    .build();
~~~

This approach is only suitable when you explicitly supply the real filter chain and understand which MVC beans/configurations are missing. For security integration testing, `webAppContextSetup` or `@SpringBootTest` usually reflects the application better.

### 3.5. Avoid registering FilterChainProxy twice

If you already use:

~~~java
.apply(springSecurity())
~~~

do not add the same `FilterChainProxy` again via `.addFilters(...)` or another mechanism. Duplicate filter registration can cause a request to pass through the security chain multiple times, causing confusing behavior such as repeated CSRF/token processing or altered context.

## 4. Distinguishing real filter chain tests from mock authentication

This is the most important distinction when writing tests.

| Approach | Runs `FilterChainProxy`? | Runs Bearer filter? | Calls JWT decoder/introspector? | Best used for |
|---|---:|---:|---:|---|
| `@SpringBootTest` + MockMvc + bearer header | Yes | Yes | Yes if configured for real | Integration security pipeline |
| `webAppContextSetup` + `springSecurity()` + bearer header | Yes | Yes | Yes if configured for real | Integration security pipeline |
| `.with(jwt())` | Yes, if MockMvc attaches the filter chain | Not via the normal bearer parsing path | No | Authorization with a mock JWT |
| `.with(opaqueToken())` | Yes, if the filter chain is attached | Not via the normal introspection path | No | Authorization with a mock opaque principal |
| `.with(user("..."))` | Yes, if the filter chain is attached | No | No | Authorization rules with a mock user |
| `@WithMockUser` | Yes, if the filter chain is attached | No | No | Method/HTTP authorization |
| `.with(authentication(...))` | Yes, if the filter chain is attached | No | No | Testing rules with a custom-built Authentication |
| Mock `JwtDecoder` + bearer header | Yes | Yes | Mock decoder is called, does not verify real signature | Bearer filter/provider wiring |
| Real `JwtDecoder` + signed test JWT | Yes | Yes | Yes, verifies real signature | JWT authentication integration |

**Real MockMvc and real authentication are two different concepts.** `.with(jwt())` can pass through the real filter chain, but it installs a mock JWT authentication into the request/security context, so it does not run the full bearer token process.

### 4.1. `jwt()` creates a mock Jwt

Example:

~~~java
mvc.perform(get("/api/orders")
        .with(jwt()))
    .andExpect(status().isOk());
~~~

Spring Security Test creates a sample `Jwt` and places the corresponding authentication into the request. The default sample JWT may use header `alg=none`; it is not a signed JWS token and does not require a `JwtDecoder` for verification.

You can customize claims:

~~~java
mvc.perform(get("/api/orders")
        .with(jwt().jwt(jwt -> jwt
            .subject("user-42")
            .claim("iss", "https://idp.example.com")
            .claim("aud", List.of("orders-api"))
            .claim("scope", "orders.read")
        )))
    .andExpect(status().isOk());
~~~

Or specify authorities explicitly:

~~~java
mvc.perform(get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )))
    .andExpect(status().isOk());
~~~

When passing `.authorities(...)`, the test directly controls the list of permissions. This is useful for testing `hasAuthority`, but it does not prove that the production `JwtAuthenticationConverter` maps claims correctly.

### 4.2. `opaqueToken()` also creates a mock principal

~~~java
mvc.perform(get("/api/orders")
        .with(opaqueToken()))
    .andExpect(status().isOk());
~~~

The request post processor creates a sample `BearerTokenAuthentication` with principal/attributes/authorities. It does not need to call an Authorization Server and does not run a real `OpaqueTokenIntrospector`.

You can customize attributes and authorities:

~~~java
mvc.perform(get("/api/orders")
        .with(opaqueToken()
            .attributes(attrs -> attrs.put("sub", "user-42"))
            .authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
    .andExpect(status().isOk());
~~~

This is how you test authorization of an opaque principal. To test client authentication, the introspection URL, `active`, timeouts, or response parsing, you must send a bearer token through the filter chain with a real introspector and a test endpoint.

### 4.3. `@WithMockUser` does not verify bearer tokens either

~~~java
@Test
@WithMockUser(username = "mai", authorities = "SCOPE_orders.read")
void userCanReadOrders() throws Exception {
    mvc.perform(get("/api/orders"))
        .andExpect(status().isOk());
}
~~~

This annotation sets up the `SecurityContext` for the test. It does not simulate JWT, issuer, audience, signature, JWKS, or introspection. Use it when the test's question is "is this authority allowed to call this route?".

### 4.4. Do not use `jwt()` to test 401 for an invalid JWT

Example with the wrong target:

~~~java
@Test
void invalidJwtIsRejected() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt()))
        .andExpect(status().isUnauthorized());
}
~~~

`.with(jwt())` already supplies a mock authentication, so the test does not pass an invalid bearer string through the decoder. It does not test the invalid signature case. To test an invalid JWT, send:

~~~http
Authorization: Bearer <malformed-or-invalid-token>
~~~

via a normal request, without attaching `.with(jwt())`.

## 5. Testing HTTP authorization with `jwt()` first

Before writing integration tests with real tokens, you can use short tests to verify the scope policy.

Suppose:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders/**")
        .hasAuthority("SCOPE_orders.write")
    .anyRequest().denyAll()
)
~~~

Tests:

~~~java
@Test
void readScopeCanReadOrders() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isOk());
}

@Test
void readScopeCannotCreateOrders() throws Exception {
    mvc.perform(post("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isForbidden());
}

@Test
void missingScopeCannotReadOrders() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt().authorities()))
        .andExpect(status().isForbidden());
}
~~~

If CSRF is enabled, POST requests need a valid CSRF token. See section 10.

These tests help verify:

- Request matchers match the right route/method.
- Authority prefixes are correct.
- Read/write rules are not inverted.
- `denyAll()` is applied to undeclared routes.

They do not test the origin of the authority. If the production converter generates the wrong scope, you need additional converter tests or integration tests with real tokens.

## 6. Testing bearer authentication through the real filter chain

To verify that the Bearer filter works, send the token in the `Authorization` header:

~~~java
@Test
void requestWithoutTokenIsUnauthorized() throws Exception {
    mvc.perform(get("/api/orders"))
        .andExpect(status().isUnauthorized());
}

@Test
void malformedBearerTokenIsRejected() throws Exception {
    mvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer not-a-jwt"))
        .andExpect(status().isUnauthorized());
}
~~~

This test goes through Spring Security's real request path inside MockMvc. For a JWT Resource Server, `BearerTokenAuthenticationFilter` extracts the token and invokes the authentication manager/provider; the provider invokes the decoder.

If the API uses opaque tokens, the bearer token request also goes through the filter, but the provider invokes `OpaqueTokenIntrospector`.

### 6.1. Checking WWW-Authenticate

The bearer authentication entry point typically returns a challenge:

~~~java
mvc.perform(get("/api/orders"))
    .andExpect(status().isUnauthorized())
    .andExpect(header().string(
        HttpHeaders.WWW_AUTHENTICATE,
        containsString("Bearer")
    ));
~~~

The exact challenge/error content depends on the entry point and version. Do not lock tests to the entire internal message string if the application does not have a fixed response contract.

### 6.2. Distinguishing 401 and 403

| Scenario | Typical result | Reason |
|---|---|---|
| No token on private route | 401 | Not authenticated |
| Malformed bearer token | 401 | Authentication failed |
| Invalid JWT signature | 401 | Token invalid |
| Wrong issuer/audience | 401 | Claims validation failed |
| Valid token but missing scope | 403 | Authentication succeeded, authorization failed |
| Mock user has wrong authority | 403 | Insufficient permissions |
| Missing CSRF token on POST when CSRF is enabled | 403 | Rejected by CSRF filter |
| Request does not match chain or another chain is selected | Depends on selected chain | Must check filter-chain routing |

A test that only asserts 403 without identifying the cause can mask bugs: it could be CSRF, a missing authority, or a custom access-denied handler. Design tests so you know which filter rejected the request.

## 7. `@SpringBootTest` with a real JWT decoder and test keys

A good integration test for JWT can use a dedicated test RSA key pair. We sign the JWT with the private key and verify it with the public key. That way no production Authorization Server is needed, yet real signature verification is still tested.

### 7.1. Creating a test key pair

~~~java
@TestConfiguration
static class JwtTestConfiguration {

    static final String ISSUER =
        "https://idp.test.example/realms/orders";

    static final String AUDIENCE = "orders-api";

    @Bean
    KeyPair testRsaKeyPair() throws Exception {
        KeyPairGenerator generator =
            KeyPairGenerator.getInstance("RSA");

        generator.initialize(2048);
        return generator.generateKeyPair();
    }

    @Bean
    JwtEncoder testJwtEncoder(KeyPair testRsaKeyPair) {
        RSAKey rsaJwk = new RSAKey.Builder(
                (RSAPublicKey) testRsaKeyPair.getPublic())
            .privateKey((RSAPrivateKey) testRsaKeyPair.getPrivate())
            .keyID("test-key")
            .build();

        JWKSource<SecurityContext> jwkSource =
            new ImmutableJWKSet<>(new JWKSet(rsaJwk));

        return new NimbusJwtEncoder(jwkSource);
    }

    @Bean
    @Primary
    JwtDecoder testJwtDecoder(KeyPair testRsaKeyPair) {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withPublicKey((RSAPublicKey) testRsaKeyPair.getPublic())
            .signatureAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(AUDIENCE)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token"));

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

Main imports:

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.proc.SecurityContext;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
~~~

The line `com.nimbusds.jose.jose.JWSAlgorithm` in the list above is **unnecessary and not an import used in the example**; omit that line when creating the Java file. Nimbus classes are managed by Spring Security's OAuth2 JOSE dependency.

This is a test configuration using `JwtEncoder` to sign and `NimbusJwtDecoder` to verify. `@Primary` gives the test decoder precedence when another decoder exists in the context; in real projects, import the test configuration explicitly and avoid letting the production decoder accidentally call an endpoint.

### 7.2. Creating a signed test access token

~~~java
private String signedToken(
        JwtEncoder encoder,
        String subject,
        List<String> scopes,
        Instant now) {

    JwtClaimsSet claims = JwtClaimsSet.builder()
        .issuer(JwtTestConfiguration.ISSUER)
        .subject(subject)
        .audience(List.of(JwtTestConfiguration.AUDIENCE))
        .issuedAt(now)
        .expiresAt(now.plusSeconds(300))
        .claim("scope", String.join(" ", scopes))
        .build();

    JwsHeader headers = JwsHeader.with(SignatureAlgorithm.RS256)
        .keyId("test-key")
        .build();

    return encoder.encode(
        JwtEncoderParameters.from(headers, claims)
    ).getTokenValue();
}
~~~

Imports:

~~~java
import java.time.Instant;
import java.util.List;

import org.springframework.security.oauth2.jose.jws.JwsHeader;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
~~~

This token has a real RSA signature from the private test key. The decoder uses the public test key to verify it. It is still a test fixture; never use this private key in any production environment.

### 7.3. Sending the bearer token through MockMvc

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@Import(JwtTestConfiguration.class)
class JwtFilterChainIntegrationTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    JwtEncoder jwtEncoder;

    @Test
    void signedTokenWithReadScopeCanAccessOrders() throws Exception {
        String token = signedToken(
            jwtEncoder,
            "user-42",
            List.of("orders.read"),
            Instant.now()
        );

        mvc.perform(get("/api/orders")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    "Bearer " + token
                ))
            .andExpect(status().isOk());
    }
}
~~~

This test does not use `.with(jwt())`. Therefore, the bearer token passes through the filter chain, provider, and real test decoder, including signature verification.

### 7.4. Testing invalid signatures

Create a token signed by a **different key pair** but with the same issuer/audience. The application's decoder does not have the corresponding public key, so signature verification must fail.

~~~text
Key A: trusted by test decoder
Key B: attacker / other test key

Token signed with Key B
  -> Bearer request
  -> decoder verifies with public key A
  -> signature invalid
  -> 401
~~~

Do not just tamper with the payload of a signed token while keeping the old signature; that also produces an invalid signature, but it does not test the different-key case. Both cases can be useful.

### 7.5. Testing issuer, audience, and expiration

Use a helper to generate tokens with variable values:

| Token | Expected |
|---|---|
| Correct `iss`, `aud=orders-api`, valid signature, not expired | Authentication succeeds |
| Different `iss` | 401 |
| `aud=billing-api` | 401 |
| `exp` in the past | 401 |
| `nbf` in the future beyond clock skew | 401 |
| Invalid signature | 401 |
| `alg` not in allowlist | 401 |

When testing timestamps, set `Instant` explicitly instead of relying on a hardcoded past time. If the decoder uses a custom `Clock`, configure a test clock to avoid flaky tests.

## 8. Testing real HTTP JWKS with a mock server

Testing with a direct public key is enough to verify JWS verification, but it does not test the HTTP fetch to the JWKS endpoint. When you need to verify that `NimbusJwtDecoder` fetches keys properly, run an HTTP stub.

### 8.1. JWKS test flow

~~~text
Mock HTTP server
   |
   +-- GET /jwks
   |      |
   |      +-- Returns JWK Set containing only the public test key
   |
Spring Resource Server
   |
   +-- JwtDecoder.withJwkSetUri(testServerUrl)
   |
MockMvc request with JWT signed by private test key
   |
   +-- Decoder fetches JWKS
   +-- Verifies signature
   +-- Validates issuer/audience
   +-- Controller
~~~

You can use WireMock, MockWebServer, or whatever HTTP stub the project already uses. There is no requirement to add another library if the current test framework already provides a mock server.

### 8.2. JWK Set response

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "test-key",
      "use": "sig",
      "alg": "RS256",
      "n": "<base64url-public-modulus>",
      "e": "AQAB"
    }
  ]
}
~~~

The response contains only the public key. The private key used to sign the JWT must remain in the test fixture.

### 8.3. What to assert

- Request goes to the correct JWKS path.
- The JWKS endpoint is not called when the test does not need a new key and the cache is still valid.
- A token with a matching `kid` is verified.
- A token signed with a different key is rejected.
- When JWKS is updated with a new key, the decoder can fetch the new key according to its refresh behavior.
- When JWKS times out or returns invalid JSON, authentication fails.
- An unknown `kid` does not cause the Resource Server to fetch a URL supplied by an arbitrary JWT header.

Do not assert that every JWT request triggers an HTTP JWKS request; the decoder has its own caching and refresh behavior.

## 9. Testing opaque tokens and introspection

### 9.1. Mock opaque token only tests authorization

~~~java
mvc.perform(get("/api/orders")
        .with(opaqueToken()
            .attributes(attrs -> {
                attrs.put("sub", "user-42");
                attrs.put("aud", List.of("orders-api"));
            })
            .authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
    .andExpect(status().isOk());
~~~

This is a test of HTTP authorization with a mock opaque principal. It does not call an introspection endpoint.

### 9.2. Testing real introspection via a stub

Configure `OpaqueTokenIntrospector` to point to the mock endpoint:

~~~text
POST /introspect
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <test-resource-server-credentials>
token=opaque-test-token
~~~

Active stub response:

~~~json
{
  "active": true,
  "sub": "user-42",
  "client_id": "test-client",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 2000000300
}
~~~

Inactive stub response:

~~~json
{
  "active": false
}
~~~

Send a real request:

~~~java
mvc.perform(get("/api/orders")
        .header(
            HttpHeaders.AUTHORIZATION,
            "Bearer opaque-test-token"
        ))
    .andExpect(status().isOk());
~~~

The `active=false` test must verify that no controller business action is invoked. If the introspection endpoint returns HTTP 401/403 due to invalid credentials, that is a configuration/resource-server client error; the response must not be treated as active.

### 9.3. Useful assertions

- HTTP method is POST.
- Token is in the form body per contract.
- Introspection client authentication is correct.
- Endpoint URL matches the test environment.
- `active=false` is rejected.
- Wrong audience cannot access the API if the contract requires audience validation.
- Scopes are mapped to `SCOPE_*`.
- Timeout or 5xx does not create an authenticated principal.
- Raw tokens or client secrets are not logged.
- Cache behavior matches revocation policy if caching is used.

## 10. CSRF in MockMvc

The CSRF filter can cause a POST request to return 403 before the request reaches the controller or authorization logic.

### 10.1. Adding a CSRF token for unsafe requests

~~~java
mvc.perform(post("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.write")
        ))
        .with(csrf()))
    .andExpect(status().isCreated());
~~~

The `csrf()` request post processor adds a valid CSRF token according to the test mechanism. You can send the token via a header:

~~~java
mvc.perform(post("/api/orders")
        .with(user("mai"))
        .with(csrf().asHeader()))
    .andExpect(status().isCreated());
~~~

### 10.2. Testing missing CSRF

~~~java
mvc.perform(post("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.write")
        )))
    .andExpect(status().isForbidden());
~~~

If CSRF is enabled, a request with valid authentication and the right authority can still be rejected due to a missing CSRF token.

### 10.3. When should a bearer-only API disable CSRF?

An API that only accepts credentials via `Authorization: Bearer` explicitly attached by the client usually has a different CSRF threat model than cookie-based authentication. You can configure:

~~~java
.csrf(AbstractHttpConfigurer::disable)
~~~

However, do not disable CSRF solely because the API uses JWT or `SessionCreationPolicy.STATELESS`. If the access token is sent automatically via cookies or the application uses a session cookie, CSRF still needs to be considered.

Tests must reflect the application's actual policy rather than mechanically adding `.with(csrf())` so that every POST passes.

## 11. Testing multiple SecurityFilterChains

An application may have multiple chains with different matchers and orders:

~~~java
@Bean
@Order(1)
SecurityFilterChain adminChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/admin/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().hasAuthority("SCOPE_admin"))
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
        .build();
}

@Bean
@Order(2)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().hasAuthority("SCOPE_api"))
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
        .build();
}

@Bean
@Order(3)
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth.anyRequest().denyAll())
        .build();
}
~~~

This is a configuration outline; in a real application you must pay attention to shared beans, decoders, and chain configurers.

### 11.1. Testing that a route selects the right chain

~~~java
@Test
void adminRouteRequiresAdminScope() throws Exception {
    mvc.perform(get("/api/admin/reports")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_api")
            )))
        .andExpect(status().isForbidden());
}

@Test
void regularApiRouteAcceptsApiScope() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_api")
            )))
        .andExpect(status().isOk());
}
~~~

These two tests show different policies by path. However, because they use `.with(jwt())`, they test **authorization after the chain is selected**, without verifying the decoder or bearer filter.

### 11.2. Checking `@Order` and matcher overlap

Some common mistakes:

- The `/api/**` chain comes before `/api/admin/**`, causing admin requests to select the general chain.
- The first chain matches every request, so subsequent chains are never used.
- Missing fallback chain, leaving some requests without any matching chain.
- `securityMatcher` and controller paths are out of sync.
- Context path or servlet path makes matchers behave differently than expected.
- Tests only call one happy-path URL and miss shadowed chains.

There should be at least one test per chain and one test for a URL that does not match specific chains.

### 11.3. Testing request-based resolvers

If you use `AuthenticationManagerResolver<HttpServletRequest>` for JWT/opaque or multiple issuers, also test:

- Request path/host selects the right manager.
- Unknown route rejects the manager or is denied by the chain.
- Invalid JWT does not fall back to another manager outside policy.
- The resolver does not fetch an issuer/JWKS URL arbitrarily provided by the request.
- The resolver does not store request objects in singleton/shared state.
- Per-issuer decoder/introspector applies the proper validators.

## 12. Testing Authentication and Authorization separately

A real filter chain has multiple layers. Categorize tests so failures pinpoint where the problem lies.

| Layer | Question | How to test |
|---|---|---|
| Bearer extraction | Is the header token read properly? | Send `Authorization: Bearer ...` |
| Authentication manager | Is the right provider selected? | Bearer integration test + verify interactions |
| JWT decoder | Are signature/issuer/audience valid? | Signed token test + real decoder |
| JWKS retrieval | Is the key source correct? | Mock JWKS HTTP server |
| Opaque introspection | Are `active` and client auth correct? | Introspection HTTP stub |
| SecurityContext | Are principal/authorities set? | Controller test reading Authentication |
| HTTP authorization | Are scope/role rules right? | `jwt()`/`opaqueToken()` |
| Method security | Is `@PreAuthorize` right? | MockMvc + method security enabled |
| Business authorization | Are tenant/owner/ACL right? | Service integration test |
| Error translation | Are 401/403 responses right? | MockMvc + assertions |

Do not lump everything into one giant test. A good test suite has unit tests for converters/validators, fast authorization tests, and a few integration tests going through the real bearer filter.

## 13. Testing `@PreAuthorize` and method security

If the application uses:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public OrderDto findOrder(String id) {
    ...
}
~~~

method security must be enabled in the application/test context:

~~~java
@EnableMethodSecurity
@Configuration
class MethodSecurityConfiguration {
}
~~~

A MockMvc test with a mock JWT:

~~~java
mvc.perform(get("/api/orders/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )))
    .andExpect(status().isOk());
~~~

can pass through HTTP filters and the method security interceptor. Even if the HTTP layer permits the route, method security can still deny at the service method.

Test all of:

- Having the required authority.
- Missing authority.
- User principal calling a service-only method.
- Incorrect tenant/object ownership.
- Method invocation does not occur when denied.

`@WithMockUser` or `jwt()` can help verify method security policies; to test authority mapping from JWT claims, you need real tokens passing through the decoder.

## 14. Testing a custom JwtAuthenticationConverter

If the application maps:

~~~text
scope=orders.read
caller_kind=user
~~~

to:

~~~text
SCOPE_orders.read
CALLER_USER
~~~

there are two levels of testing.

### 14.1. Unit testing the converter

Create a test `Jwt` object and call the converter directly:

~~~java
Jwt jwt = Jwt.withTokenValue("test-token")
    .header("alg", "RS256")
    .issuer("https://idp.test.example")
    .subject("user-42")
    .claim("scope", "orders.read")
    .claim("caller_kind", "user")
    .build();

Collection<GrantedAuthority> authorities =
    converter.convert(jwt);
~~~

Assert that `SCOPE_orders.read` and `CALLER_USER` are present. This is only a mapping unit test; the directly constructed `Jwt` object does not have a verified signature.

### 14.2. Integration testing the converter through the bearer flow

Create a real signed JWT with the claims above and send it in the Bearer header. After the decoder verifies it, the production `JwtAuthenticationConverter` is invoked.

This test verifies:

- The decoder accepts the token.
- The converter is called in the pipeline.
- Scopes are mapped correctly.
- Custom caller markers are mapped correctly.
- Endpoints requiring both caller kind and scope behave according to contract.

Do not add `.with(jwt())` to this integration request because it will bypass the converter attached in `JwtAuthenticationProvider` along the normal bearer path.

## 15. Testing authentication entry point and access denied handler

Applications may standardize JSON error responses:

~~~java
.exceptionHandling(exceptions -> exceptions
    .authenticationEntryPoint(customAuthenticationEntryPoint)
    .accessDeniedHandler(customAccessDeniedHandler)
)
~~~

Tests should distinguish:

**Unauthenticated:**

~~~java
mvc.perform(get("/api/orders"))
    .andExpect(status().isUnauthorized())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON
    ));
~~~

**Authenticated but forbidden:**

~~~java
mvc.perform(get("/api/orders")
        .with(jwt().authorities()))
    .andExpect(status().isForbidden())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON
    ));
~~~

Validate the response body against the API's public contract, without coupling tests to stack traces, class names, or internal exception messages.

If the bearer token is invalid, the authentication entry point handles the authentication error. If the token is valid but lacks permissions, the access denied handler handles it. If the service throws a business error, `@ControllerAdvice`/MVC exception handling may handle it under a different contract.

## 16. Testing CORS and preflight

CORS preflight is typically an `OPTIONS` request without a bearer token:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

MockMvc can verify response headers from the CORS configuration:

~~~java
mvc.perform(options("/api/orders")
        .header(HttpHeaders.ORIGIN, "https://app.example.com")
        .header(
            HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
            "GET"
        )
        .header(
            HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
            "authorization"
        ))
    .andExpect(status().isOk())
    .andExpect(header().string(
        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
        "https://app.example.com"
    ));
~~~

The exact status and headers depend on the CORS config. Preflight is usually processed before authentication; no token is required if the policy allows it.

MockMvc tests the server-side CORS filter/configuration, but does not simulate browser enforcement. A real browser also enforces the CORS protocol and may block JavaScript from reading the response even if the server returned data.

## 17. Testing Session and SecurityContext persistence

A bearer-only Resource Server is usually stateless:

~~~java
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
~~~

Tests can verify that every request must carry a bearer token and does not unintentionally reuse authentication from a session.

If the application has both browser sessions and an API bearer chain, test the two chains separately:

- UI routes use session/cookies according to policy.
- API routes require a bearer token.
- `JSESSIONID` does not automatically become Bearer authentication if the API contract forbids it.
- Sessions do not leak principals from an earlier request to another tenant/user.
- SecurityContext is cleared/persisted according to the proper repository and policy.

MockMvc provides `MockHttpSession`; you can send the same session across multiple requests to test session-based flows. However, for stateless APIs, do not use a session in bearer tests to mask a request missing a token.

## 18. Testing CSRF and security context with annotations

`@WithMockUser` sets up the context before the test method runs. Spring Security Test integrates `TestSecurityContextHolderPostProcessor` when MockMvc is configured via `springSecurity()`.

Example:

~~~java
@Test
@WithMockUser(username = "mai", authorities = "SCOPE_orders.read")
void readRouteWorksForMockUser() throws Exception {
    mvc.perform(get("/api/orders"))
        .andExpect(status().isOk());
}
~~~

Annotations are useful for tests needing a pre-existing principal. However, if the test method needs the bearer filter, remove the annotation and send a bearer header.

Do not mix `@WithMockUser` and another Bearer token in the same test unless the goal is to test a very specific precedence/interaction. If both supply authentication, the test may not be checking the principal you think it is.

## 19. Practical tests for `BearerTokenAuthenticationFilter`

One way to verify that the bearer filter is invoked is to send a token header and observe the test decoder/introspector dependency.

Example using Mockito:

~~~java
verify(jwtDecoder).decode(anyString());
~~~

If the decoder is a mock, the test proves the filter/provider calls the decoder with the token. It does **not** prove the signature is verified.

For introspection:

~~~java
verify(opaqueTokenIntrospector).introspect("opaque-test-token");
~~~

A mock introspector can return an active principal to test the pipeline, but it does not test the HTTP client, credentials, or response parsing.

To test the real provider and real network client, replace the mock with a decoder/introspector pointing to a test key or HTTP stub.

## 20. Common anti-patterns

### 20.1. Disabling all filters and then testing security status

~~~java
@AutoConfigureMockMvc(addFilters = false)
~~~

When filters are disabled, requests do not run the Spring Security filter chain. A 200 test does not prove that the production API permits the request.

### 20.2. Using `jwt()` and claiming the signature was verified

`jwt()` creates a mock authentication. It does not invoke `JwtDecoder` to verify a signature.

### 20.3. Using `opaqueToken()` and claiming the introspection endpoint works

`opaqueToken()` creates a mock `BearerTokenAuthentication`. It does not send a request to the AS.

### 20.4. Using `@WithMockUser` to test JWT claims

`@WithMockUser` does not create a JWT. It does not test `iss`, `aud`, `exp`, `kid`, `scope`, or a custom claim converter.

### 20.5. Mocking the entire `SecurityFilterChain`

If you replace the production `SecurityFilterChain` with a permitAll test chain, the test no longer tests the real policy. Only mock external dependencies such as services, repositories, or the decoder/introspector when the test goal permits.

### 20.6. Using standaloneSetup without attaching the security filter

Controller tests may pass without ever running security. Use `webAppContextSetup` or provide a real `FilterChainProxy`.

### 20.7. Asserting a single status for all errors

A 403 can come from CSRF, a missing authority, or a custom access denied handler. A 401 can come from a malformed token, wrong issuer, or decoder exception. Add the necessary assertions/verification to know the cause.

### 20.8. Not testing the fallback chain

Requests outside matchers may not go through any chain if a fallback is missing. Test unknown routes and special admin routes.

### 20.9. Using production tokens in tests

Never take real bearer tokens from logs, browsers, or production environments as fixtures. Generate test keys/tokens or use a test Authorization Server.

### 20.10. Flaky tests dependent on wall-clock time

JWT `exp`/`nbf` can cause a test that passes today to fail tomorrow. Build claims relative to `Instant.now()` or a controlled test clock.

### 20.11. Using `@SpringBootTest` for every test

Full contexts are slower than slice tests. Use `@WebMvcTest` for MVC/security slices, unit tests for converters/validators, and a few integration tests for the full bearer pipeline.

### 20.12. Not checking side effects on rejection

In addition to asserting 401/403, you can verify the service was not called:

~~~java
verifyNoInteractions(ordersService);
~~~

This helps catch bugs where a controller/service still runs even though the final security response is rejected at another layer.

## 21. Recommended test matrix for a Resource Server

| Group | Request | Expectation | Test level |
|---|---|---|---|
| Public route | No token | 200 | MockMvc + real chain |
| Private route | No token | 401 | Real bearer filter chain |
| Malformed token | Bearer invalid string | 401 | Real bearer filter chain |
| JWT signature invalid | Token signed with different key | 401 | Real decoder |
| Wrong issuer | JWT with different `iss` | 401 | Real decoder/validator |
| Wrong audience | `aud` different from API | 401 | Real decoder/validator |
| Expired JWT | `exp` in the past | 401 | Real decoder/validator |
| Valid JWT | Signed test token | 200 if scope sufficient | Real decoder |
| Missing scope | Valid JWT but missing scope | 403 | Real decoder or mock JWT for authorization |
| Opaque active | Introspection active=true | 200 if scope sufficient | Real introspector + stub |
| Opaque inactive | Introspection active=false | 401 | Real introspector + stub |
| Introspection timeout | Test AS timeout | Not authenticated | Real introspector + stub |
| CSRF missing | POST when CSRF enabled | 403 | Real chain |
| CSRF valid | POST + csrf token | Proceeds if authorized | Real chain |
| Admin chain | Regular API scope | 403 | Chain selection + authorization |
| Unknown route | Does not match route | Deny | Fallback chain |
| Method security | Missing authority | Access denied | MVC + method security |
| Tenant mismatch | Valid token, wrong tenant | 403/404 per policy | Service integration |
| CORS preflight | OPTIONS valid Origin | CORS response | MockMvc CORS |
| Converter mapping | User/service claims | Correct authority | Unit + signed JWT integration |

Not every case needs a separate full Spring context. You can group tests by fixture and use the appropriate unit/slice/integration layers.

## 22. Organizing test classes by purpose

An easy-to-maintain structure:

~~~text
src/test/java
  security/
    CallerAuthoritiesConverterTests.java
    AudienceValidatorTests.java
    ApiAuthorizationMockMvcTests.java
    JwtBearerFilterChainTests.java
    OpaqueIntrospectionFilterChainTests.java
    MultiSecurityFilterChainRoutingTests.java
    CsrfAndCorsMockMvcTests.java
    MethodSecurityTests.java
  support/
    TestJwtFactory.java
    TestJwksServer.java
    TestIntrospectionServer.java
    SecurityTestConfiguration.java
~~~

Suggestions:

- `*Tests` unit: converters, validators, mapping.
- `*MockMvcTests` authorization: using `jwt()`, `opaqueToken()`, `user()`.
- `*FilterChainTests` integration: sending real Bearer headers through `MockMvc`.
- `*Server` fixtures: test JWKS/introspection endpoints.
- `TestJwtFactory`: signs tokens with a test private key and customizable claims.
- `SecurityTestConfiguration`: contains only test keys/decoders/endpoints, without altering production policy.

Folder/class names are just examples; what matters is clearly separating mock-authentication tests from bearer-pipeline tests.

## 23. Debugging when MockMvc does not run the filter chain as expected

If an endpoint returns 200 without a token:

1. Check whether `@AutoConfigureMockMvc(addFilters = false)` is being used.
2. If building MockMvc manually, is `.apply(springSecurity())` present?
3. Is the `FilterChainProxy` bean `springSecurityFilterChain` in the application context?
4. Does any `SecurityFilterChain` match the request?
5. Does the chain have `permitAll()` or an overly broad matcher?
6. Does the test use `.with(jwt())`, `.with(user())`, `@WithMockUser`, or `.with(authentication())`?
7. Does any test config replace the production security config?
8. Has `@WebMvcTest` imported the right security configuration?
9. Does any custom filter bypass the route on its own?
10. Does the request path have a context path/servlet path that makes the matcher behave differently than expected?

If a request returns 403 instead of 401:

- Check whether CSRF is blocking POST/PUT/PATCH/DELETE.
- Check whether the principal is authenticated but missing an authority.
- Check `AccessDeniedHandler`.
- Check `@PreAuthorize`.
- Check which chain was selected.

If a Bearer token request does not call the decoder:

- Verify the header is `Authorization: Bearer ...`.
- Remove `jwt()`/`authentication()` request post processors.
- Verify `oauth2ResourceServer().jwt(...)` or the proper resolver is configured.
- Verify the request enters the right `SecurityFilterChain`.
- Check whether the route is permitAll; an invalid token is still usually processed if a bearer header is sent, though exact behavior depends on token resolver/filter config.

## 24. Limitations that must be tested outside MockMvc

A good security test suite does not stop at MockMvc.

| Aspect | MockMvc | Test server/staging |
|---|---|---|
| Request matchers and filter ordering | Yes | Yes |
| Bearer extraction/provider | Yes | Yes |
| JWT signature with test keys | Yes | Yes |
| JWKS HTTP fetch via mock server | Yes | Yes |
| Introspection HTTP call via stub | Yes | Yes |
| CSRF/CORS server config | Yes | Yes |
| TLS handshake | Not fully simulated | Yes |
| mTLS client certificate | Not fully simulated | Yes |
| Reverse proxy forwarded headers | Only simulated via request attributes | Yes |
| DNS/firewall/egress | No | Yes |
| Browser CORS enforcement | No | Browser E2E |
| Cookie SameSite behavior | Does not simulate browser | Browser E2E |
| Connection timeout/load balancer | Does not simulate real infrastructure | Yes |
| Multiple replicas/shared cache | No | Distributed integration test |

If the Resource Server uses mTLS-bound access tokens, DPoP, proxy headers, or network trust, add specialized tests. MockMvc can test request-aware verifiers using fake request attributes, but that does not prove real TLS certificates are verified by the container.

## 25. Self-check questions

**1.** What must be done for MockMvc to use the real Spring Security filter chain?

> Use `webAppContextSetup(context).apply(springSecurity()).build()` or Spring Boot `@AutoConfigureMockMvc` with filters enabled.

**2.** What component does `springSecurity()` add to MockMvc?

> It registers the `springSecurityFilterChain` bean (usually `FilterChainProxy`) as a filter and integrates TestSecurityContextHolder.

**3.** Does `@AutoConfigureMockMvc(addFilters=false)` test Spring Security?

> No. It disables servlet filter registration for MockMvc.

**4.** Does `.with(jwt())` verify the JWT signature?

> No. It creates a mock `Jwt`/authentication for testing authorization.

**5.** Does `.with(opaqueToken())` call the introspection endpoint?

> No. It creates a mock `BearerTokenAuthentication`.

**6.** Does `@WithMockUser` go through `BearerTokenAuthenticationFilter`?

> No. It sets up the SecurityContext with a mock user.

**7.** What must you do to test a real JWT signature?

> Create a JWT signed with a private test key, send it via `Authorization: Bearer`, and have the decoder verify it using a test public key/JWKS.

**8.** What is needed to test real introspection via MockMvc?

> A real introspector pointing to an HTTP stub/test AS and a Bearer request without using the `opaqueToken()` mock post processor.

**9.** Why is an `@Order` test needed when there are multiple `SecurityFilterChain` beans?

> Because `FilterChainProxy` selects the first matching chain; a general chain can shadow a specific chain.

**10.** Does a POST returning 403 necessarily mean a missing scope?

> No. It could be a missing CSRF token or rejection by method security/access denied policy.

**11.** Does MockMvc test TLS/mTLS handshakes?

> Not completely. Real test servers/containers and TLS clients are needed.

**12.** Why is `jwt()` useful even though it does not verify signatures?

> It enables fast testing of HTTP authorization rules with custom claims/authorities without building cryptographic tokens in every test.

**13.** Does testing a signed JWT directly with a public key test JWKS fetching?

> No. It tests the signature; to test HTTP JWKS retrieval you need a mock JWKS server.

**14.** Should you mock the entire `SecurityFilterChain` in integration tests?

> Not if the goal is to verify the production filter chain; only mock dependencies outside security when needed.

**15.** Why verify that the service is not called when a token is rejected?

> To be sure there are no business side effects before the security decision completes.

## 26. References

- [Spring Security — Setting Up MockMvc and Spring Security](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html): `FilterChainProxy`, `springSecurity()`, and TestSecurityContextHolder.
- [Spring Security — Testing OAuth 2.0 with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): `jwt()`, `opaqueToken()`, `authentication()`, and limitations of mock authentication.
- [Spring Security — MockMvc Request Post Processors](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/request-post-processors.html): `user`, `csrf`, `httpBasic`, form login, and request processors.
- [Spring Security 6.5 — Setting Up MockMvc](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html): API and setup comparison for the 6.5 line.
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html): testing `@PreAuthorize` and method security.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): Spring MVC Test, `webAppContextSetup`, and `standaloneSetup`.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@SpringBootTest`, test slices, and context.
- [Spring Boot — Auto-configured MockMvc](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@AutoConfigureMockMvc` and servlet filters.
- [Spring Security — Servlet OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): decoder, validators, bearer authentication.
- [Spring Security — Servlet OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection and opaque authentication.
- [Spring Security — Authorization HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): request matchers, authority, and deny rules.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF filter and token behavior.
- [Spring Security — CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): CORS filter and preflight.

**Conclusion:** MockMvc can test the **real Spring Security filter chain** when requests are routed through `FilterChainProxy` using `springSecurity()` or Boot MockMvc auto-configuration with filters enabled. However, `.with(jwt())`, `.with(opaqueToken())`, and `@WithMockUser` only create mock authentication to test authorization. To verify that the Resource Server processes bearer tokens properly, send `Authorization: Bearer ...` through MockMvc; use JWTs signed with a test key and a real decoder, or a stub introspection server to test each provider. Combine unit tests, authorization tests, bearer-pipeline integration tests, and infrastructure tests when TLS/proxy/network coverage is needed to obtain appropriate evidence for each security layer.

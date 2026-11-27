# Writing Mock Identity Tests and Real Signature & Introspection Tests

A Spring Security OAuth 2.0 Resource Server test suite needs to answer two distinct questions:

1. Once the application has an `Authentication`, do the controller, service, and authorization rules handle principals, scopes, roles, tenants, and access permissions properly?
2. When a client sends a real Bearer token, does the Resource Server extract the token, verify the JWT signature or call the introspection endpoint, validate the result, and build the right `Authentication`?

The first question fits **mock identity tests**. The second requires **authentication integration tests** that traverse `SecurityFilterChain` and use a real decoder/introspector or a test server implementing the matching HTTP contract.

Spring Security provides helpers such as **`jwt()`**, **`opaqueToken()`**, **`mockJwt()`**, and **`mockOpaqueToken()`** to create test identities quickly. These helpers do not sign JWTs, do not verify signatures, and do not call an Authorization Server. Using them alone proves authorization policies work with a pre-constructed `Authentication`, but does not prove real-world access tokens are properly verified.

This lesson builds a complete test strategy for both Servlet and WebFlux: mocking identities for policy checks, signing JWTs with test keys to test signatures, sending tokens through an HTTP test introspection endpoint to verify the opaque-token flow, and testing invalid, inactive, insufficient-scope, and connection-error cases.

## 1. Three Layers to Test Separately

A Resource Server processes requests along a chain:

~~~mermaid
flowchart TD
    R[HTTP request + Authorization Bearer] --> E[Bearer token extraction]
    E --> V{JWT or opaque?}
    V -->|JWT| D[JwtDecoder / ReactiveJwtDecoder]
    V -->|Opaque| I[OpaqueTokenIntrospector / ReactiveOpaqueTokenIntrospector]
    D -->|Valid signature and claims| A[Authentication]
    I -->|active=true and valid attributes| A
    D -->|Invalid| U[Authentication failure]
    I -->|Inactive / verification error| U
    A --> Z[Authorization: scope, role, tenant]
    Z -->|Authorized| C[Controller / service]
    Z -->|Insufficient permission| F[403 Forbidden]
~~~

The test suite can be divided into three layers:

| Layer | Goal | Tools |
|---|---|---|
| Mock identity | Verify controllers, services, scopes, roles, tenants, ownership | MockMvc + `jwt()`/`opaqueToken()`; WebTestClient + `mockJwt()`/`mockOpaqueToken()` |
| JWT signature | Verify Bearer extraction, signature, issuer, audience, timestamps, algorithm | `JwtEncoder` signing test tokens + real `JwtDecoder` + `SecurityFilterChain` |
| Opaque introspection | Verify Bearer extraction, HTTP request, client authentication, `active`, scopes, and attributes | Test HTTP introspection server + real `OpaqueTokenIntrospector` |

A single test may span multiple layers, so be clear about what it actually proves. For example, MockMvc with `jwt()` still executes the authorization filter chain when Spring Security filters are attached, yet the helper injects a `JwtAuthenticationToken` into the test context instead of decoding a Bearer token.

## 2. Choosing Helpers by Identity Type

Not every `Authentication` is the same. Choose the test helper matching the principal type your controller or service actually expects.

| Helper | Authentication / principal | When to use |
|---|---|---|
| `@WithMockUser` or `user()` | `UsernamePasswordAuthenticationToken` / `UserDetails` | General role or method security tests |
| `jwt()` | `JwtAuthenticationToken` / `Jwt` | Servlet Resource Server JWT authorization |
| `opaqueToken()` | `BearerTokenAuthentication` / `OAuth2AuthenticatedPrincipal` | Servlet Resource Server opaque-token authorization |
| `mockJwt()` | `JwtAuthenticationToken` / `Jwt` | WebFlux Resource Server JWT authorization |
| `mockOpaqueToken()` | `BearerTokenAuthentication` / `OAuth2AuthenticatedPrincipal` | WebFlux Resource Server opaque-token authorization |
| `oidcLogin()` / `mockOidcLogin()` | `OAuth2AuthenticationToken` / `OidcUser` | OAuth2/OIDC Login flows |

**OIDC Login and Resource Server Bearer authentication are two different flows.** If an API receives an access token in the `Authorization` header, do not use `oidcLogin()` merely because the system uses OpenID Connect.

### 2.1. Test Dependencies

With Spring Boot dependency management, add test modules compatible with your Spring Security runtime:

~~~groovy
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

When testing real signed JWTs, the application also needs the appropriate JOSE module. When using `NimbusJwtEncoder`/`NimbusJwtDecoder`, dependencies manage the Spring Security/Nimbus versions via the project's BOM.

To stand up a local HTTP introspection endpoint in tests, you can use `MockWebServer`:

~~~groovy
dependencies {
    testImplementation("com.squareup.okhttp3:mockwebserver")
}
~~~

Use a `MockWebServer` version compatible with the OkHttp version managed by your project. The test examples below use dummy tokens and dummy credentials, never production secrets.

## 3. Mocking Identity in Servlet with MockMvc

Spring Security Test provides `RequestPostProcessor` helpers for MockMvc. These inject an `Authentication` into the test request so authorization rules and controllers can consume it.

### 3.1. JWT with `jwt()`

Controller example:

~~~java
@RestController
class OrderController {

    @GetMapping("/api/orders")
    List<String> orders(@AuthenticationPrincipal Jwt jwt) {
        return List.of(
            jwt.getSubject(),
            jwt.getClaimAsString("tenant_id")
        );
    }
}
~~~

Test:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void authenticatedUserCanReadOrders() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt().jwt(jwt -> jwt
                .claim("sub", "alice")
                .claim("tenant_id", "tenant-a")
                .claim("scope", "orders.read")
            )))
        .andExpect(status().isOk());
}
~~~

The default JWT produced by this helper has header `alg=none` and claims `sub=user`, `scope=read`. You can customize headers, claims, and authorities per scenario.

**`jwt()` does not verify signatures.** It creates a `JwtAuthenticationToken` for testing. Use this helper when testing authorization or how controllers read claims.

### 3.2. Granting Authorities Directly

If you only want to test a specific rule:

~~~java
mvc.perform(get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )))
    .andExpect(status().isOk());
~~~

This bypasses converting the `scope` claim into authorities. If you want to test a custom `JwtAuthenticationConverter`, supply the claims and let the production converter run in the filter chain or unit-test the converter separately.

### 3.3. Testing Missing Scope

~~~java
@Test
void writeOnlyTokenCannotReadOrders() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.write")
            )))
        .andExpect(status().isForbidden());
}
~~~

This test proves the read rule requires `SCOPE_orders.read`. It does not prove tokens are signed or that the decoder rejects bad signatures.

### 3.4. Opaque Principal with `opaqueToken()`

For a controller accepting `BearerTokenAuthentication`:

~~~java
@GetMapping("/api/profile")
String profile(BearerTokenAuthentication authentication) {
    return (String) authentication.getTokenAttributes().get("sub");
}
~~~

Test:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.opaqueToken;

@Test
void opaquePrincipalProvidesSubject() throws Exception {
    mvc.perform(get("/api/profile")
            .with(opaqueToken()
                .attributes(attributes -> {
                    attributes.put("sub", "alice");
                    attributes.put("tenant_id", "tenant-a");
                })
            ))
        .andExpect(status().isOk())
        .andExpect(content().string("alice"));
}
~~~

By default `opaqueToken()` creates a `BearerTokenAuthentication` whose principal has `sub=user` and authority `SCOPE_read`. You can override attributes, authorities, or supply a complete principal.

### 3.5. Role Tests with `@WithMockUser`

~~~java
@Test
@WithMockUser(username = "admin", roles = "ADMIN")
void adminCanDeleteOrder() throws Exception {
    mvc.perform(delete("/api/orders/42"))
        .andExpect(status().isNoContent());
}
~~~

`roles="ADMIN"` produces authority `ROLE_ADMIN`. This test fits general role-based policies. If the endpoint expects `BearerTokenAuthentication` or `Jwt` claims, use the appropriate OAuth2 helper.

## 4. Mocking Identity in WebFlux with `WebTestClient`

For WebFlux, Spring Security Test provides `WebTestClientConfigurer` helpers to attach an `Authentication` to `ServerWebExchange`.

### 4.1. JWT with `mockJwt()`

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;

@Test
void jwtPrincipalCanReadOrders() {
    webTestClient
        .mutateWith(mockJwt().jwt(jwt -> jwt
            .claim("sub", "alice")
            .claim("tenant_id", "tenant-a")
            .claim("scope", "orders.read")
        ))
        .get()
        .uri("/api/orders")
        .exchange()
        .expectStatus().isOk();
}
~~~

`mockJwt()` creates a test `JwtAuthenticationToken` and places it in the security context. It does not send a compact JWT through the Bearer filter and does not invoke `ReactiveJwtDecoder`.

### 4.2. Opaque Principal with `mockOpaqueToken()`

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOpaqueToken;

@Test
void opaquePrincipalCanReadOrders() {
    webTestClient
        .mutateWith(mockOpaqueToken()
            .attributes(attributes -> {
                attributes.put("sub", "alice");
                attributes.put("tenant_id", "tenant-a");
                attributes.put("scope", "orders.read");
            })
            .authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )
        )
        .get()
        .uri("/api/orders")
        .exchange()
        .expectStatus().isOk();
}
~~~

`mockOpaqueToken()` creates a `BearerTokenAuthentication` with an `OAuth2AuthenticatedPrincipal`. By default the helper uses `sub=user`, `scope=read`, and `SCOPE_read`.

### 4.3. Attaching Spring Security to `WebTestClient`

When binding a client to an application context, ensure the Spring Security filter chain is applied:

~~~java
WebTestClient client = WebTestClient
    .bindToApplicationContext(applicationContext)
    .apply(springSecurity())
    .configureClient()
    .build();
~~~

In Spring Boot WebFlux integration tests, you can use the auto-configured `WebTestClient`. In WebFlux slice tests, import `SecurityWebFilterChain` and its required supporting beans.

### 4.4. Testing Reactive Method Security

If a service uses `@PreAuthorize`, enable `@EnableReactiveMethodSecurity` and invoke the Spring-managed service bean. Mock identities can verify authority/tenant policies at the service boundary, but do not replace introspection or JWT signature tests.

## 5. Mock Authentication Is Not Equivalent to a Mock Decoder

Three testing approaches are commonly confused:

| Approach | Bearer token extraction | Real decoder/introspector | Authorization |
|---|---:|---:|---:|
| `jwt()`/`mockJwt()` | No | No | Yes |
| `opaqueToken()`/`mockOpaqueToken()` | No | No | Yes |
| Mock `JwtDecoder` / Mock `Introspector` in filter chain | Yes | No, uses test double | Yes |
| Signed JWT + real decoder | Yes | Real JWT decoder | Yes |
| Bearer token + HTTP introspection test server | Yes | Real introspector calling HTTP | Yes |

A mocked decoder can be useful for testing `BearerTokenAuthenticationFilter`, exception handling, and `Authentication` mapping. However, it does not test signatures.

Similarly, a mocked introspector can test integration between the provider and a test principal. It does not prove HTTP requests to the Authorization Server are constructed properly.

## 6. Signing JWTs with Test RSA Keys

To test real signatures, a test must:

1. Generate a test-only RSA key pair.
2. Sign the JWT with the private key.
3. Configure the Resource Server decoder with the matching public key.
4. Send the compact JWT via `Authorization: Bearer`.
5. Let `SecurityFilterChain` invoke the decoder and verify the signature.
6. Test both valid and invalid tokens.

The private key is used solely to sign test tokens. The Resource Server receives only the public key for verification.

### 6.1. Creating Test Keys and Encoder

Spring Security with Nimbus example:

~~~java
import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.TestConfiguration;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import com.nimbusds.jose.proc.SecurityContext;
import com.nimbusds.jose.jwk.source.JWKSource;

@TestConfiguration
class JwtTestConfiguration {

    @Bean
    RSAKey testRsaKey() throws JOSEException {
        return new RSAKeyGenerator(2048)
            .keyID("test-key")
            .generate();
    }

    @Bean
    JwtEncoder testJwtEncoder(RSAKey testRsaKey) {
        JWKSource<SecurityContext> source =
            new ImmutableJWKSet<>(new JWKSet(testRsaKey));

        return new NimbusJwtEncoder(source);
    }
}
~~~

The RSA key is generated when the test context initializes. Never commit private keys or reuse this test key in real environments.

### 6.2. Configuring the Decoder with the Public Key

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@TestConfiguration
class JwtDecoderTestConfiguration {

    static final String ISSUER = "https://issuer.test";
    static final String AUDIENCE = "orders-api";

    @Bean
    JwtDecoder testJwtDecoder(RSAKey testRsaKey) throws JOSEException {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withPublicKey(testRsaKey.toRSAPublicKey())
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience().contains(AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }

            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Required audience is missing",
                    null
                )
            );
        };

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

The decoder uses the public key to verify the `RS256` signature. Default validators check issuer and timestamps; the audience validator verifies the Resource Server receives tokens with the expected audience.

If the production config also checks tenant, token profile, or required claims, add the corresponding validators to the chain. Do not replace all default validators with an audience-only validator.

### 6.3. Generating Signed JWTs per Test

~~~java
import java.time.Instant;
import java.util.List;

import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwsHeader;

String signedToken(
        JwtEncoder encoder,
        String issuer,
        String audience,
        Instant issuedAt,
        Instant expiresAt) {

    JwtClaimsSet claims = JwtClaimsSet.builder()
        .issuer(issuer)
        .subject("alice")
        .audience(List.of(audience))
        .issuedAt(issuedAt)
        .expiresAt(expiresAt)
        .claim("scope", "orders.read")
        .claim("tenant_id", "tenant-a")
        .build();

    JwsHeader headers = JwsHeader
        .with(SignatureAlgorithm.RS256)
        .keyId("test-key")
        .build();

    return encoder.encode(
        JwtEncoderParameters.from(headers, claims)
    ).getTokenValue();
}
~~~

The token is signed using the private key in the JWK source. The Resource Server then receives the compact token and verifies it itself using the configured public key.

### 6.4. Sending the Signed Token Through MockMvc

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@Import({JwtTestConfiguration.class, JwtDecoderTestConfiguration.class})
class SignedJwtResourceServerTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    JwtEncoder jwtEncoder;

    @Test
    void validSignedJwtPassesAuthenticationAndAuthorization() throws Exception {
        Instant now = Instant.now();

        String token = signedToken(
            jwtEncoder,
            JwtDecoderTestConfiguration.ISSUER,
            JwtDecoderTestConfiguration.AUDIENCE,
            now.minusSeconds(10),
            now.plusSeconds(300)
        );

        mvc.perform(get("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
            .andExpect(status().isOk());
    }
}
~~~

This is an integration test passing through Bearer token extraction and the decoder. Do not call `jwt()` or `authentication()` on the request.

The test must use the actual `SecurityFilterChain` or a test chain configured with the same Resource Server, authorization rules, and validators under test.

## 7. Testing Bad Signature, Wrong Issuer, Wrong Audience, and Expiry

A test suite with only valid tokens is insufficient. You must prove the decoder rejects near-valid tokens that violate each condition.

### 7.1. Token Signed with an Untrusted Key

Create a second RSA key pair and separate encoder:

~~~java
RSAKey otherKey = new RSAKeyGenerator(2048)
    .keyID("other-key")
    .generate();

JwtEncoder attackerEncoder = new NimbusJwtEncoder(
    new ImmutableJWKSet<>(
        new JWKSet(otherKey)
    )
);
~~~

Use that encoder to create a JWT with valid issuer/audience but signed by a different private key. Send the token via the `Authorization` header and expect authentication to fail.

~~~java
mvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + tokenSignedByOtherKey))
    .andExpect(status().isUnauthorized());
~~~

This is a real signature check: the decoder lacks the corresponding public key and cannot verify the JWS.

### 7.2. Token with Wrong Issuer

Sign the token with the valid test private key, but set the `iss` claim to something other than the configured issuer. A valid signature must still be rejected by the issuer validator.

### 7.3. Token with Wrong Audience

Sign the token with audience `billing-api` instead of `orders-api`. The decoder verifies the signature, yet the audience validator must reject it.

### 7.4. Expired or Not-Yet-Valid Token

Use `expiresAt` in the past or `notBefore` in the future. Test clock skew per the application's configuration.

### 7.5. Distinguishing Causes of `401`

| Scenario | Expected result |
|---|---|
| Missing Bearer token on protected endpoint | 401 |
| Malformed token | 401 |
| Invalid signature | 401 |
| Wrong issuer | 401 |
| Wrong audience | 401 |
| Expired token | 401 |
| Valid token lacking scope | 403 |
| Valid token, sufficient scope, right tenant | Passes authorization |

`401` usually indicates authentication failure; `403` usually indicates authenticated but insufficient permissions. Inspect responses and test logs to see which layer rejected the request.

## 8. Testing a Real JWKS Endpoint via an HTTP Test Server

A decoder using a direct public key verifies signatures, but does not test fetching keys from a JWKS endpoint.

If the application configures `jwk-set-uri`, add tests for:

- HTTP `GET` to the JWKS URI.
- Parsing the JSON JWK Set.
- Selecting the right key by `kid` in the JWT.
- Reusing the cached key set.
- Key rotation and unknown `kid`.
- JWKS timeout or HTTP `5xx`.
- Ensuring keys from another issuer are not misused.

You can use `MockWebServer` to serve the public JWK Set:

~~~java
String jwksJson = new JWKSet(testRsaKey.toPublicJWK()).toString();

server.enqueue(
    new MockResponse()
        .setResponseCode(200)
        .addHeader("Content-Type", "application/json")
        .setBody(jwksJson)
);
~~~

Configure the decoder with `server.url("/jwks")` as its JWK Set URI, then send a JWT signed with the matching private key through `SecurityFilterChain`.

After the request, verify the server received `GET /jwks`. This tests both signature verification and JWKS HTTP retrieval. It remains a local test server, not a production Authorization Server.

## 9. Real Introspection: Sending Bearer Tokens Over an HTTP Endpoint

With opaque tokens, the Resource Server calls the Authorization Server's introspection endpoint. Spring Security Servlet uses `OpaqueTokenAuthenticationProvider` with `OpaqueTokenIntrospector`; WebFlux uses their reactive counterparts.

Servlet flow:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant F as BearerTokenAuthenticationFilter
    participant P as OpaqueTokenAuthenticationProvider
    participant I as OpaqueTokenIntrospector
    participant AS as Introspection test server

    C->>F: Authorization: Bearer opaque-token
    F->>P: BearerTokenAuthenticationToken
    P->>I: introspect(opaque-token)
    I->>AS: POST /introspect + client authentication
    AS-->>I: active=true, sub, scope
    I-->>P: OAuth2AuthenticatedPrincipal
    P-->>F: BearerTokenAuthentication
    F-->>C: Continue to authorization/controller
~~~

Unlike `opaqueToken()`, this request actually invokes the introspection HTTP client. The test server can verify the request body, client authentication, and response parsing.

### 9.1. Standing Up an Introspection Endpoint with `MockWebServer`

Start the server before tests:

~~~java
static MockWebServer introspectionServer;

@BeforeAll
static void startServer() throws IOException {
    introspectionServer = new MockWebServer();
    introspectionServer.start();
}

@AfterAll
static void stopServer() throws IOException {
    introspectionServer.shutdown();
}
~~~

Configure the introspector pointing to the local URL:

~~~java
@Bean
OpaqueTokenIntrospector testIntrospector() {
    return SpringOpaqueTokenIntrospector
        .withIntrospectionUri(
            introspectionServer.url("/introspect").toString()
        )
        .clientId("resource-server")
        .clientSecret("test-secret")
        .build();
}
~~~

In the test application, attach the introspector to `SecurityFilterChain`:

~~~java
@Bean
SecurityFilterChain testSecurity(
        HttpSecurity http,
        OpaqueTokenIntrospector testIntrospector) throws Exception {

    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .opaqueToken(opaque -> opaque
                .introspector(testIntrospector)
            )
        )
        .build();
}
~~~

If the application already has a production `SecurityFilterChain`, tests should override the endpoint/credentials or introspector via test configuration while preserving the authorization rules under test.

### 9.2. Testing an Active Token

Before calling the endpoint, enqueue a response:

~~~java
introspectionServer.enqueue(
    new MockResponse()
        .setResponseCode(200)
        .addHeader("Content-Type", "application/json")
        .setBody("""
            {
              "active": true,
              "sub": "alice",
              "scope": "orders.read",
              "tenant_id": "tenant-a",
              "aud": ["orders-api"]
            }
            """)
);
~~~

Send the Bearer token normally:

~~~java
mvc.perform(get("/api/orders")
        .header(
            HttpHeaders.AUTHORIZATION,
            "Bearer opaque-test-token"
        ))
    .andExpect(status().isOk());
~~~

After the request, inspect the introspection server:

~~~java
RecordedRequest request =
    introspectionServer.takeRequest(1, TimeUnit.SECONDS);

assertThat(request).isNotNull();
assertThat(request.getMethod()).isEqualTo("POST");
assertThat(request.getPath()).isEqualTo("/introspect");
assertThat(request.getHeader("Authorization"))
    .startsWith("Basic ");
assertThat(request.getBody().readUtf8())
    .contains("token=opaque-test-token");
~~~

This proves the Resource Server sent the token to the endpoint, used client authentication, and parsed the response to build the principal. The test token is a dummy opaque string, not a production access token.

### 9.3. Verifying Client Authentication

If using HTTP Basic, verify the header constructed from the test client ID/secret:

~~~java
String credentials = "resource-server:test-secret";
String encoded = Base64.getEncoder().encodeToString(
    credentials.getBytes(StandardCharsets.UTF_8)
);

assertThat(request.getHeader("Authorization"))
    .isEqualTo("Basic " + encoded);
~~~

Never print real client secrets into test output. If test credentials contain special characters, verify the exact encoding contract of the Spring Security builder to catch double-encoding.

### 9.4. Inactive Token

Enqueue:

~~~java
introspectionServer.enqueue(
    new MockResponse()
        .setResponseCode(200)
        .addHeader("Content-Type", "application/json")
        .setBody("""
            {
              "active": false
            }
            """)
);
~~~

Send the Bearer token and expect authentication to fail, typically with `401`. The controller is never executed.

### 9.5. Active Token Lacking Scope

Enqueue:

~~~json
{
  "active": true,
  "sub": "alice",
  "scope": "orders.write"
}
~~~

`GET /api/orders` must be denied by authorization, typically with `403`. This distinction is vital:

- `active=false`: token fails authentication.
- `active=true` lacking `orders.read`: token authenticates, yet lacks sufficient permissions.

## 10. Introspection with WebFlux

Reactive Resource Server uses `ReactiveOpaqueTokenIntrospector`. In tests, point a reactive introspector to `MockWebServer`:

~~~java
@Bean
ReactiveOpaqueTokenIntrospector testReactiveIntrospector() {
    return SpringReactiveOpaqueTokenIntrospector
        .withIntrospectionUri(
            introspectionServer.url("/introspect").toString()
        )
        .clientId("resource-server")
        .clientSecret("test-secret")
        .build();
}
~~~

Attach to `SecurityWebFilterChain`:

~~~java
@Bean
SecurityWebFilterChain testReactiveSecurity(
        ServerHttpSecurity http,
        ReactiveOpaqueTokenIntrospector testReactiveIntrospector) {

    return http
        .authorizeExchange(authorize -> authorize
            .pathMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyExchange().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .opaqueToken(opaque -> opaque
                .introspector(testReactiveIntrospector)
            )
        )
        .build();
}
~~~

Send the Bearer token via `WebTestClient`:

~~~java
webTestClient
    .get()
    .uri("/api/orders")
    .headers(headers -> headers.setBearerAuth("opaque-test-token"))
    .exchange()
    .expectStatus().isOk();
~~~

Then retrieve the `RecordedRequest` from `MockWebServer` to check the `POST` path, Basic authentication, and form body.

This tests through the reactive filter chain and reactive HTTP client. Do not use `mockOpaqueToken()` in this scenario because that helper injects `BearerTokenAuthentication` into the test exchange without calling the introspector.

## 11. Testing Introspection Errors and Fail-Closed Behavior

Do not test only `active=true` responses. Cover the following cases:

| Introspection response | Expected outcome to verify |
|---|---|
| `active=true`, right scope | Authentication succeeds, authorization may allow |
| `active=true`, missing scope | Authentication succeeds, authorization denies |
| `active=false` | Authentication fails |
| HTTP `401`/`403` from AS | Client authentication/configuration failure |
| HTTP `5xx` | No successful `Authentication` created |
| Timeout | Does not fail open |
| Malformed JSON | No bogus principal created |
| Missing required claim | Policy/mapping handles explicitly |
| Wrong data type | No unintended permissions granted |

Do not assume every AS error returns the exact same HTTP status. Entry points and exception translation can differ per error. What matters is that the request is never treated as authenticated without a valid introspection result.

### 11.1. Do Not Mock Responses When Testing HTTP Integration

Using:

~~~java
when(introspector.introspect("opaque-token"))
    .thenReturn(principal);
~~~

only proves the provider calls the mocked introspector. It does not test HTTP method, URL, body, client credentials, JSON parsing, timeouts, or `active` handling.

Use an HTTP test server whenever you need to verify those aspects.

### 11.2. Testing Against a Real Authorization Server

`MockWebServer` tests the client's HTTP contract using test-controlled responses. It does not prove the real Authorization Server has the right policy.

For critical releases, add a contract/integration test suite against a sandbox Authorization Server or Testcontainers:

- Provision a dedicated test client.
- Obtain an access token using the appropriate grant.
- Send the JWT/opaque token to the Resource Server.
- Revoke the opaque token if supported by the AS.
- Verify introspection returns `active=false` after revocation per SLA.
- Verify audience/scope and issuer policies.
- Clean up test clients, users, and tokens after running.

Never use production environments or production credentials in test suites.

## 12. JWTs Can Be Verified via Introspection

JWTs are usually verified locally by signature and claims. However, a system may opt to introspect JWTs if it needs per-request revocation checks at the Authorization Server.

In that setup, the Resource Server uses Opaque Token support to send the token to the introspection endpoint. `Authentication` follows the opaque-token flow and principal attributes come from the introspection response.

Do not confuse the two modes:

| Mode | How verification works | What to test |
|---|---|---|
| JWT decoder | Signature, issuer, audience, timestamps, type | Sign JWT and pass through real `JwtDecoder` |
| Introspection, even if token is JWT-formatted | AS returns `active` and attributes | Send Bearer token through introspection endpoint |
| Mock JWT | Test `Authentication` injected | Authorization/controller |
| Mock opaque | Test `BearerTokenAuthentication` injected | Authorization/controller |

If using introspection for JWTs, tests must confirm the introspection endpoint is actually called. Do not rely on a signature test to conclude revocation is checked.

## 13. Mocking the Decoder/Introspector in Filter Chain Tests

There is a useful middle ground: sending `Authorization: Bearer` through the filter chain while replacing the decoder or introspector with a test double.

### 13.1. Mocking `JwtDecoder`

When the decoder is mocked:

- `BearerTokenAuthenticationFilter` still extracts the token.
- The authentication provider still calls the decoder.
- Tests can verify the exact token string is passed.
- Tests can verify exception mapping and authorization.
- Real cryptographic signatures and validators are not tested.

Example:

~~~java
when(jwtDecoder.decode("test-token"))
    .thenReturn(testJwt);
~~~

Send request:

~~~java
mvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer test-token"))
    .andExpect(status().isOk());
~~~

### 13.2. Mocking `OpaqueTokenIntrospector`

Similarly, mocking the introspector verifies the token is passed to the introspector and the resulting principal populates `Authentication`.

However, HTTP client behavior and introspection response parsing remain untested.

### 13.3. Using Test Doubles for the Right Purpose

| Test double | What it tests | What it misses |
|---|---|---|
| Mock Authentication helper | Authorization and principal binding | Bearer extraction, decoder, introspection |
| Mock `JwtDecoder` | Bearer extraction, provider/filter integration | Cryptographic signatures, claims validators |
| Mock `OpaqueTokenIntrospector` | Bearer extraction, provider integration | HTTP request/response, client auth |
| Local introspection HTTP server | HTTP client, body, credentials, response parsing | Production Authorization Server policies |
| Real Authorization Server sandbox | Contract between AS and Resource Server | Not a substitute for fast unit tests |

## 14. Verifying `SecurityFilterChain` Actually Runs

A test can return `200` even if security filters are not attached. When testing a Resource Server, verify the test harness actually runs the filter chain.

### 14.1. MockMvc

With Spring Boot:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ResourceServerTests {

    @Autowired
    MockMvc mvc;
}
~~~

Never use `addFilters = false` in tests meant to verify Bearer tokens. When creating MockMvc manually via `WebApplicationContext`, apply `springSecurity()`.

### 14.2. `WebTestClient`

With an application context:

~~~java
WebTestClient client = WebTestClient
    .bindToApplicationContext(applicationContext)
    .apply(springSecurity())
    .configureClient()
    .build();
~~~

If binding directly to a controller with `bindToController()`, tests can bypass most security configuration. Use the application context or a live server integration test when verifying the filter chain.

### 14.3. CSRF and HTTP Methods

If CSRF is enabled, `POST`/`PUT`/`PATCH`/`DELETE` requests may be rejected before scope authorization runs. With MockMvc, add `csrf()` to tests focusing on scopes/roles, or write dedicated CSRF tests.

Never disable CSRF just to make tests pass. For stateless Bearer-only APIs, CSRF decisions must reflect how credentials are transported and the threat model.

## 15. Testing Tenant, Subject, and Resource Ownership

Valid authentication does not mean the principal can read every resource.

Suppose an endpoint requires:

- `SCOPE_orders.read`.
- `tenant_id` must be `tenant-a`.
- `subject` must be the order's owner.
- The order must exist.

Test matrix:

| Principal | Scope | Tenant | Owner | Result |
|---|---|---|---|---|
| Alice | `orders.read` | `tenant-a` | Alice | Allowed |
| Alice | `orders.write` | `tenant-a` | Alice | Denied read |
| Bob | `orders.read` | `tenant-a` | Alice | Denied |
| Alice | `orders.read` | `tenant-b` | Alice | Denied |
| Alice | `orders.read` | `tenant-a` | Does not exist | 404 per API contract |

Mock identity tests work well for running this matrix quickly. Follow up with a few integration tests using signed JWTs or introspection principals to confirm real claims populate the expected fields.

In particular, never take tenant or subject from query parameters in place of verified claims. Repository queries should constrain tenant/owner right at the database.

## 16. Testing Custom Authority Mapping

A token may carry scope or role claims under a custom contract. Separate two questions:

1. Does the decoder/introspector verify the token and expose the right claims?
2. Does the converter map those claims to the right `GrantedAuthority` instances?

Example JWT claims:

~~~json
{
  "sub": "alice",
  "scope": "orders.read",
  "roles": ["ORDER_MANAGER"]
}
~~~

If a custom `JwtAuthenticationConverter` maps the role to `ROLE_ORDER_MANAGER`, you can write:

- Unit tests on the converter using a `Jwt` test object to verify mapping.
- Signed JWT integration tests to verify decoder and converter working together.
- Negative tests without `roles` to ensure permissions are never self-granted.

Opaque tokens work the same way: use an introspection HTTP response with `scope`/`roles` and assert the resulting authorities after authentication. Never infer `ROLE_ADMIN` merely because the response contains an attribute named `roles` if no mapper is configured.

## 17. Summary Table for the Test Suite

A practical test suite can be organized as follows:

| Group | Test case | Tools | What it proves |
|---|---|---|---|
| Mock JWT | Sufficient scope | `jwt()`/`mockJwt()` | Authorization |
| Mock JWT | Missing scope | `jwt()`/`mockJwt()` | `403` policy |
| Mock opaque | Attributes and principal name | `opaqueToken()`/`mockOpaqueToken()` | Controller binding |
| Role | Admin/user | `@WithMockUser` | Role policy |
| Real JWT | Valid RSA signature | `JwtEncoder` + `JwtDecoder` | Cryptographic verification |
| Real JWT | Invalid signature | Different key | Decoder rejects |
| Real JWT | Wrong issuer/audience | Signed token with different claims | Claim validation |
| Real JWT | Expired | Expired signed token | Timestamp validation |
| JWKS | Key fetch and key rotation | Local JWKS HTTP server | JWK retrieval/cache |
| Real opaque | `active=true` | `MockWebServer` + real introspector | HTTP introspection |
| Real opaque | `active=false` | `MockWebServer` + real introspector | Authentication rejection |
| Real opaque | Missing scope | Introspection response | `403` authorization |
| Opaque error | Timeout/`5xx` | HTTP test server | Fail-closed |
| Multi-tenant | Tenant mismatch | Signed token/introspection | Tenant isolation |
| Integration | AS sandbox | Testcontainers/sandbox | AS contract |

## 18. Common Anti-Patterns

**Using `jwt()` and claiming JWT signatures were tested.** The helper injects `JwtAuthenticationToken` without invoking the decoder.

**Using `opaqueToken()` and claiming introspection ran.** The helper injects `BearerTokenAuthentication` without calling any endpoint.

**Calling a mocked `JwtDecoder` test a signature integration test.** A mocked decoder never verifies JWS.

**Mocking the introspector and concluding HTTP Basic and body formatting are right.** Mocks send no HTTP requests.

**Testing only valid tokens.** You also need wrong keys, wrong issuers, wrong audiences, expirations, inactive tokens, and missing scopes.

**Disabling security filters so tests turn green easily.** Passing results prove nothing about Resource Server behavior.

**Confusing OIDC Login with Resource Server.** `oidcLogin()` does not replace Bearer access-token flows.

**Using production keys in tests.** Test private keys must be generated separately and never reused.

**Putting real secrets in `MockWebServer` fixtures.** Use dummy credentials only.

**Not inspecting the introspection request.** A `200` status alone does not prove the token was sent to the expected endpoint.

**Not distinguishing `401` and `403`.** An inactive token and a token lacking scope are two distinct outcomes.

**Testing only `JwtDecoder.decode()` directly.** This misses Bearer extraction, `SecurityFilterChain`, and exception translation; add HTTP request integration tests.

**Skipping JWKS tests when the app uses a remote JWK Set.** Public-key unit tests do not verify HTTP fetching, caching, or key rotation.

**Retrying or failing open when the introspection endpoint errors.** Without a valid verification result, never create a successful `Authentication`.

## 19. Implementing the Test Strategy

**Step 1 — Inventory Authentication types.** Identify whether the API uses JWTs, opaque tokens, OIDC Login, or sessions.

**Step 2 — Write mock identity tests.** Use `jwt()`/`opaqueToken()` for Servlet and `mockJwt()`/`mockOpaqueToken()` for WebFlux to test controllers, scopes, roles, tenants, and ownership.

**Step 3 — Test authority converters.** Test scopes, roles, custom claims, and principal mapping independently.

**Step 4 — Generate test signing keys.** Use ephemeral RSA/EC key pairs; private keys sign only test tokens.

**Step 5 — Wire a real decoder.** Use the public key or a JWKS test endpoint along with issuer/audience/time validators.

**Step 6 — Send real Bearer tokens.** Do not use authentication helpers in tests meant to verify signatures.

**Step 7 — Test invalid tokens.** Invalid signatures, issuers, audiences, `typ`, `exp`, `nbf`, and untrusted algorithms.

**Step 8 — Stand up an introspection HTTP test server.** Return `active=true`/`false`, scopes, and attributes per scenario.

**Step 9 — Send Bearer tokens through the filter chain.** Assert `POST`, endpoint path, client authentication, token body, and resulting principal.

**Step 10 — Test AS errors.** `401`/`403`, `5xx`, timeouts, malformed JSON, and responses missing claims.

**Step 11 — Test tenant and ownership.** Right scope with wrong tenant/owner must still be denied.

**Step 12 — Run AS contract tests when needed.** Use a sandbox or Testcontainers to confirm real Authorization Server behavior.

**Step 13 — Keep the test harness honest.** MockMvc/`WebTestClient` must attach Spring Security filters; never accidentally bypass the filter chain.

## 20. Self-Check Questions

**1. What do `jwt()` and `mockJwt()` test?**

They construct a test `JwtAuthenticationToken` to test authorization and how the application consumes JWT claims.

**2. Do those two helpers verify signatures?**

No. They do not invoke `JwtDecoder`.

**3. Do `opaqueToken()` and `mockOpaqueToken()` call the introspection endpoint?**

No. They create a test `BearerTokenAuthentication` with an `OAuth2AuthenticatedPrincipal`.

**4. What is needed to test real JWT signatures?**

A JWT signed with a test private key, a real decoder using the matching public key, and a Bearer request passing through `SecurityFilterChain`.

**5. Why test invalid signatures?**

To prove the decoder rejects tokens not signed by a trusted key.

**6. What is needed to test JWKS retrieval?**

Stand up a test JWKS HTTP endpoint, pass a signed JWT through a decoder configured with the JWK Set URI, and verify requests/key selection/caching.

**7. What is needed to test HTTP introspection?**

A real Bearer token through the filter chain, a real introspector pointing to an HTTP test server, and assertions on both request and response.

**8. How does `active=false` differ from missing scope?**

`active=false` fails authentication, typically returning `401`. `active=true` lacking scope leads to an authorization denial, typically returning `403`.

**9. Does a mocked decoder prove signatures?**

No. It merely replaces the decoder in tests.

**10. Is `MockWebServer` a real Authorization Server?**

No. It is an HTTP test server for verifying the introspection client's request/response contract. An AS sandbox is required to test Authorization Server behavior itself.

**11. When should `@WithMockUser` be used?**

When a test only needs a generic principal/role and does not depend on `Jwt` or `BearerTokenAuthentication`.

**12. Why test through `SecurityFilterChain`?**

To confirm Bearer extraction, the authentication provider, decoder/introspector, exception translation, and authorization work together as in real requests.

## Conclusion

A strong Resource Server test suite does not choose between mocks and integration tests; it uses each for its intended purpose.

**Mock identity tests** run fast and focus on controllers, method security, scopes, roles, tenants, and ownership. **JWT signature tests** must sign tokens with test private keys and send Bearer tokens through a real decoder verified by public keys. **Opaque introspection tests** must send Bearer tokens through the filter chain to an HTTP introspection endpoint and verify the request, client authentication, active status, attributes, and authorities.

Keeping these test layers separate makes it crystal clear what has been proved. `jwt()`/`mockJwt()` do not check signatures; `opaqueToken()`/`mockOpaqueToken()` do not call introspection; mocked decoders/introspectors do not test cryptography or HTTP. To test the full path, use a real `SecurityFilterChain`, test keys, JWKS/introspection test servers, and both positive and negative cases.

**The target outcome is that valid tokens are verified and receive only their intended permissions; tokens with invalid signatures, wrong issuer/audience, inactive status, expiration, or insufficient permissions are rejected at the right layer.**

### References

- [Spring Security — Testing OAuth 2.0 with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html)
- [Spring Security — Testing OAuth 2.0 with WebTestClient](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html)
- [Spring Security — Servlet Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — Servlet Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — Reactive Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security API — NimbusJwtEncoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtEncoder.html)
- [Spring Security API — NimbusJwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html)
- [Spring Security API — SpringOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringOpaqueTokenIntrospector.html)
- [Spring Security API — SpringReactiveOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringReactiveOpaqueTokenIntrospector.html)
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
- [OkHttp — MockWebServer](https://github.com/square/okhttp/tree/master/mockwebserver)
- [RFC 7515 — JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)

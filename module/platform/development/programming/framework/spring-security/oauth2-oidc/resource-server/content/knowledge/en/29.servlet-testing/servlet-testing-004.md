# @WithMockUser Does Not Fully Simulate a Resource Server Principal

## 1. Core difference

In Spring Security Servlet, `@WithMockUser` creates an authenticated `UsernamePasswordAuthenticationToken` with a principal of type `UserDetails`. A JWT Resource Server request goes through `BearerTokenAuthenticationFilter`, `JwtAuthenticationProvider`, `JwtDecoder`, and `JwtAuthenticationConverter`, and then creates a `JwtAuthenticationToken` with a principal of type `Jwt`.

Therefore, `@WithMockUser` bypasses Bearer token extraction, the decoder, signature, issuer, audience, expiration, and claim conversion. A test can prove an authority is allowed to call an endpoint, but it does not prove the Resource Server verified a token or created the right principal.

**Choose the helper based on what you need to test:** `@WithMockUser` for authority-only tests; MockMvc `jwt()` for JWT principal/claims; signed Bearer JWTs through the filter chain for decoder and converter integration tests.

## 2. Principals differ across authentication mechanisms

| Mechanism | Typical Authentication | Typical Principal | Servlet test helper |
|---|---|---|---|
| `@WithMockUser` | `UsernamePasswordAuthenticationToken` | `UserDetails` / `User` | `@WithMockUser` |
| Resource Server JWT | `JwtAuthenticationToken` | `Jwt` | MockMvc `jwt()` |
| Resource Server opaque token | `BearerTokenAuthentication` | `OAuth2AuthenticatedPrincipal` | MockMvc `opaqueToken()` |
| OIDC Login | OAuth2 Login Authentication | `OidcUser` | `oidcLogin()` |
| OAuth2 Login | OAuth2 Login Authentication | `OAuth2User` | `oauth2Login()` |
| Custom Authentication | Implementation-dependent | Principal contract-dependent | `authentication()` |

Specific classes may vary by provider and version, but the principal contract is the key point to watch.

### 2.1. @WithMockUser creates UserDetails

~~~java
@Test
@WithMockUser(username = "alice", roles = {"ADMIN"})
void adminCanReadReport() throws Exception {
    mvc.perform(get("/api/admin/report"))
        .andExpect(status().isOk());
}
~~~

The annotation creates user `alice`, the principal is `UserDetails`, and role `ADMIN` becomes authority `ROLE_ADMIN`. If no attributes are passed, Spring Security Test defaults to user `user` and role `USER`.

`roles` automatically adds the `ROLE_` prefix; `authorities` uses the exact authority string:

~~~java
@WithMockUser(roles = "ADMIN")
// ROLE_ADMIN

@WithMockUser(authorities = "SCOPE_orders.read")
// SCOPE_orders.read
~~~

If the policy uses OAuth scope authorities, use `authorities` or a JWT-aware helper. Do not use `roles` and expect Spring to convert it to `SCOPE_...` automatically.

### 2.2. JWT Resource Server creates JwtAuthenticationToken

A JWT access token might contain:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "tenant_id": "tenant-a"
}
~~~

With the default converter, scope values are typically converted into `SCOPE_orders.read` and `SCOPE_orders.write`. `JwtAuthenticationToken` holds the JWT principal and authorities. A controller can receive:

~~~java
@GetMapping("/api/me")
MeResponse me(@AuthenticationPrincipal Jwt jwt) {
    return new MeResponse(
        jwt.getSubject(),
        jwt.getClaimAsString("tenant_id")
    );
}
~~~

`@WithMockUser` does not create a `Jwt`, so it does not provide `iss`, `aud`, `sub`, or `tenant_id` according to the access token contract.

## 3. Specific limitations of @WithMockUser

### 3.1. Wrong principal type

If a controller requires `@AuthenticationPrincipal Jwt`, `@WithMockUser` supplies a `UserDetails` principal. The resolver cannot turn a User into a Jwt. With the default `@AuthenticationPrincipal`, an argument of the wrong type may receive `null`; if `errorOnInvalidType = true` is enabled, the mismatch raises an error instead of silently receiving null.

~~~java
@GetMapping("/api/me")
MeResponse me(
        @AuthenticationPrincipal(errorOnInvalidType = true) Jwt jwt) {
    return new MeResponse(
        jwt.getSubject(),
        jwt.getClaimAsString("tenant_id")
    );
}
~~~

### 3.2. Does not test JWT validation

`@WithMockUser` does not run:

- Bearer token extraction.
- `JwtDecoder` and signature verification.
- Issuer, audience, expiry, and not-before validation.
- JWKS lookup, key rotation, or algorithm policy.
- Token profile validators.
- Custom claim-to-authority converters.
- DPoP/certificate-bound token checks if implemented by the application.

### 3.3. Does not simulate opaque tokens or OIDC Login

An opaque Resource Server normally creates an `OAuth2AuthenticatedPrincipal` after introspection; OIDC Login creates an `OidcUser`. `@WithMockUser` does not simulate either principal.

### 3.4. Does not test credentials in the HTTP request

Tests with `@WithMockUser` do not prove the client sent the right `Authorization: Bearer ...`, that the token is parsed properly, that invalid tokens return 401, or that the API does not redirect to a browser login.

## 4. When @WithMockUser is still appropriate

The annotation is appropriate when a test only checks authorization based on a generic Authentication, without depending on a JWT principal or token conversion.

~~~java
@Test
@WithMockUser(authorities = "SCOPE_orders.read")
void readAuthorityCanAccessReadEndpoint() throws Exception {
    mvc.perform(get("/api/orders/42"))
        .andExpect(status().isOk());
}

@Test
@WithMockUser(authorities = "SCOPE_profile")
void unrelatedAuthorityCannotReadOrders() throws Exception {
    mvc.perform(get("/api/orders/42"))
        .andExpect(status().isForbidden());
}
~~~

These tests verify which authority URL authorization accepts. Name tests like "read authority can access endpoint"; do not name them "valid JWT can read order" since no JWT was verified.

With method security:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public OrderDto load(String id) {
    return repository.findDtoById(id);
}
~~~

`@WithMockUser(authorities = "SCOPE_orders.read")` can test an authority-only rule. However, if the expression reads `authentication.principal.claims['tenant_id']`, a UserDetails principal does not satisfy the contract; use a JWT-aware context.

## 5. MockMvc jwt() for a mock JWT principal

Spring Security Test provides the `jwt()` request post-processor in Servlet/MockMvc. It creates a `JwtAuthenticationToken` and `Jwt` principal, suited for controller and authorization tests that depend on claims.

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
~~~

### 5.1. Testing a controller reading the Jwt principal

~~~java
@Test
void jwtPrincipalProvidesSubjectAndTenant() throws Exception {
    mvc.perform(get("/api/me")
            .with(jwt().jwt(jwt -> jwt
                .subject("user-123")
                .claim("tenant_id", "tenant-a")
            )))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.subject").value("user-123"))
        .andExpect(jsonPath("$.tenantId").value("tenant-a"));
}
~~~

The helper attaches a mock JWT Authentication to the request. The controller receives the right principal type and can read claims.

**Limitation:** `jwt()` does not invoke `JwtDecoder` to verify signatures. The JWT object is built in the test, not a compact token sent via a Bearer header.

### 5.2. Testing scope authorities

~~~java
@Test
void jwtWithReadScopeCanReadOrders() throws Exception {
    mvc.perform(get("/api/orders/42")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isOk());
}

@Test
void jwtWithoutReadScopeIsForbidden() throws Exception {
    mvc.perform(get("/api/orders/42")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_profile")
            )))
        .andExpect(status().isForbidden());
}
~~~

`jwt().authorities(...)` explicitly assigns authorities to test authorization; it does not test the application's converter.

### 5.3. Testing claims

~~~java
@Test
void jwtPrincipalContainsResourceClaims() throws Exception {
    mvc.perform(get("/api/me")
            .with(jwt().jwt(jwt -> jwt
                .issuer(URI.create("https://id.example.test/realms/shop"))
                .subject("user-123")
                .audience(List.of("orders-api"))
                .claim("client_id", "orders-web")
                .claim("tenant_id", "tenant-a")
                .claim("scope", "orders.read")
            )))
        .andExpect(status().isOk());
}
~~~

These claims are merely constructed for the controller/policy to read; they are not proved to be signed by a real issuer.

### 5.4. jwt() does not prove the application converter is called

If the test assigns `SCOPE_orders.read` itself, the converter could be broken and the test would still pass. Test the converter separately and add a Bearer integration test.

## 6. opaqueToken() for an opaque Resource Server principal

For opaque tokens, the post-introspection principal is typically `OAuth2AuthenticatedPrincipal`, not Jwt. MockMvc helper:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.opaqueToken;
~~~

~~~java
@Test
void opaquePrincipalCanAccessPartnerReport() throws Exception {
    mvc.perform(get("/api/partners/reports/2026")
            .with(opaqueToken()
                .attributes(attributes -> {
                    attributes.put("sub", "partner-user-01");
                    attributes.put("client_id", "partner-client");
                })
                .authorities(
                    new SimpleGrantedAuthority(
                        "SCOPE_partner.reports.read"
                    )
                )
            ))
        .andExpect(status().isOk());
}
~~~

`opaqueToken()` tests principal attributes and authorization. It does not call a real introspection endpoint, so it does not test client authentication, `active`, timeouts, HTTP status, schema drift, caching, or revocation. To test those parts, test `OpaqueTokenIntrospector` or use an HTTP stub/sandbox.

## 7. oidcLogin() for an OIDC browser principal

Browser controllers may receive `OidcUser`:

~~~java
@GetMapping("/console/profile")
Profile profile(@AuthenticationPrincipal OidcUser user) {
    return new Profile(user.getSubject(), user.getEmail());
}
~~~

Test using:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oidcLogin;

@Test
void oidcUserHasIdTokenAndUserInfoClaims() throws Exception {
    mvc.perform(get("/console/profile")
            .with(oidcLogin()
                .idToken(token -> token.subject("browser-user-01"))
                .userInfo(userInfo ->
                    userInfo.email("browser@example.test")
                )
            ))
        .andExpect(status().isOk());
}
~~~

`oidcLogin()` simulates an OIDC Login principal; it does not simulate a Resource Server `JwtAuthenticationToken`. `oauth2Login()` is also for OAuth2 Login principals, not JWT access tokens.

## 8. authentication() and custom @WithSecurityContext

### 8.1. Passing Authentication explicitly

~~~java
Jwt jwt = Jwt.withTokenValue("test-token")
    .header("alg", "none")
    .issuer(URI.create("https://id.example.test/realms/shop"))
    .subject("user-123")
    .audience(List.of("orders-api"))
    .issuedAt(Instant.parse("2026-11-15T00:00:00Z"))
    .expiresAt(Instant.parse("2026-11-15T00:05:00Z"))
    .claim("tenant_id", "tenant-a")
    .build();

JwtAuthenticationToken authentication =
    new JwtAuthenticationToken(
        jwt,
        List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
    );

mvc.perform(get("/api/me")
        .with(authentication(authentication)))
    .andExpect(status().isOk());
~~~

This JWT object is constructed directly. The `alg` header inside the object does not make it a signed compact JWT; do not use this test to conclude the decoder verified signatures.

### 8.2. Custom annotation with @WithSecurityContext

If many tests need the same JWT principal, you can create a custom annotation, e.g., `@WithJwtPrincipal`. This is an application-defined annotation, not a default built-in annotation of Spring Security Test.

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD, ElementType.TYPE})
@WithSecurityContext(factory = WithJwtPrincipal.Factory.class)
public @interface WithJwtPrincipal {

    String subject() default "user-123";
    String tenant() default "tenant-a";
    String[] authorities() default {"SCOPE_orders.read"};

    final class Factory
            implements WithSecurityContextFactory<WithJwtPrincipal> {

        @Override
        public SecurityContext createSecurityContext(
                WithJwtPrincipal annotation) {

            Instant now = Instant.parse("2026-11-15T00:00:00Z");

            Jwt jwt = Jwt.withTokenValue("synthetic-test-token")
                .header("alg", "none")
                .issuer(URI.create("https://id.example.test/realms/shop"))
                .subject(annotation.subject())
                .audience(List.of("orders-api"))
                .issuedAt(now)
                .expiresAt(now.plusSeconds(300))
                .claim("tenant_id", annotation.tenant())
                .build();

            List<GrantedAuthority> authorities =
                Arrays.stream(annotation.authorities())
                    .map(SimpleGrantedAuthority::new)
                    .collect(Collectors.toList());

            SecurityContext context =
                SecurityContextHolder.createEmptyContext();

            context.setAuthentication(
                new JwtAuthenticationToken(jwt, authorities)
            );
            return context;
        }
    }
}
~~~

Additional imports:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.net.URI;
import java.time.Instant;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.test.context.support.WithSecurityContext;
import org.springframework.security.test.context.support.WithSecurityContextFactory;
~~~

Usage:

~~~java
@Test
@WithJwtPrincipal(
    subject = "tenant-a-user",
    tenant = "tenant-a",
    authorities = {"SCOPE_orders.read"}
)
void tenantUserCanReadOwnOrders() throws Exception {
    mvc.perform(get("/api/orders/42"))
        .andExpect(status().isOk());
}
~~~

This annotation produces the right principal shape and claims for the test context. It still bypasses Bearer token parsing, JWT signatures, issuer/audience validators, and converters. For deterministic time tests, use a fixed clock or inject a clock instead of relying on the machine clock.

## 9. Testing JwtAuthenticationConverter separately

If the Resource Server uses a custom `JwtAuthenticationConverter`, test the converter directly. Example:

~~~java
JwtGrantedAuthoritiesConverter grantedAuthorities =
    new JwtGrantedAuthoritiesConverter();

grantedAuthorities.setAuthoritiesClaimName("scope");
grantedAuthorities.setAuthorityPrefix("SCOPE_");

JwtAuthenticationConverter converter =
    new JwtAuthenticationConverter();

converter.setJwtGrantedAuthoritiesConverter(grantedAuthorities);
~~~

Test:

~~~java
@Test
void convertsScopeClaimIntoAuthorities() {
    Jwt jwt = Jwt.withTokenValue("synthetic")
        .header("alg", "none")
        .subject("user-123")
        .claim("scope", "orders.read orders.write")
        .build();

    AbstractAuthenticationToken authentication =
        converter.convert(jwt);

    assertThat(authentication.getAuthorities())
        .extracting(GrantedAuthority::getAuthority)
        .containsExactlyInAnyOrder(
            "SCOPE_orders.read",
            "SCOPE_orders.write"
        );
}
~~~

Also test valid/wrong claim types, missing claims, roles outside the allowlist, scopes not belonging to the API, and invalid tenant claims. Testing the converter directly does not prove the decoder/filter chain calls the converter; add a Bearer integration test.

## 10. Integration testing with a signed Bearer JWT

### 10.1. Security configuration

~~~java
@Configuration
@EnableWebSecurity
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

The example illustrates the Servlet stack. The decoder needs appropriate issuer/audience validators; `Customizer.withDefaults()` does not replace a trust contract.

### 10.2. Sending the token via the Authorization header

Suppose the test fixture `testTokens` signs JWTs with a test-only private key and the test context configures the decoder with the matching public key:

~~~java
@Test
void signedBearerTokenPassesThroughResourceServer() throws Exception {
    String token = testTokens.issue(
        "user-123",
        TRUSTED_ISSUER,
        List.of("orders-api"),
        "orders.read",
        "tenant-a"
    );

    mvc.perform(get("/api/orders/42")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andExpect(status().isOk());
}
~~~

This test passes through MockMvc, the Spring Security filter chain, Bearer extraction, the JWT decoder, signature/claims validators, the Authentication converter, authorization, and controller/service. `testTokens` is a test-only factory; never use production access tokens or signing keys.

### 10.3. Token with an invalid signature

~~~java
@Test
void invalidSignatureIsRejected() throws Exception {
    String token = tokenSignedByUntrustedKey();

    mvc.perform(get("/api/orders/42")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andExpect(status().isUnauthorized());
}
~~~

The token is signed by a key different from the public key trusted by the decoder. This tests the real signature path; `jwt()` cannot replace it.

### 10.4. Wrong audience

~~~java
@Test
void wrongAudienceIsRejected() throws Exception {
    String token = testTokens.issue(
        "user-123",
        TRUSTED_ISSUER,
        List.of("billing-api"),
        "orders.read",
        "tenant-a"
    );

    mvc.perform(get("/api/orders/42")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andExpect(status().isUnauthorized());
}
~~~

### 10.5. Real principal at the controller

~~~java
@Test
void signedTokenProvidesExpectedPrincipalClaims() throws Exception {
    String token = testTokens.issue(
        "user-123",
        TRUSTED_ISSUER,
        List.of("orders-api"),
        "orders.read",
        "tenant-a"
    );

    mvc.perform(get("/api/me")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.subject").value("user-123"))
        .andExpect(jsonPath("$.tenantId").value("tenant-a"));
}
~~~

This test verifies JWT validation and that the principal claims reach the controller.

## 11. Testing custom converters through the filter chain

If configuring:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt
        .jwtAuthenticationConverter(customJwtAuthenticationConverter)
    )
)
~~~

you need an integration test with a Bearer JWT containing the claims the converter reads, for example:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "app_roles": ["STORE_MANAGER"],
  "tenant_id": "tenant-a"
}
~~~

Verify that the decoder accepts the token, scope becomes `SCOPE_orders.read`, role becomes `ROLE_STORE_MANAGER` if mapping permits, roles outside the allowlist do not grant global admin, and the controller receives the right tenant JWT claim.

A test using `jwt().authorities(...)` does not prove the custom converter was invoked.

## 12. Distinguishing 401 and 403

| Scenario | Authentication | Authorization | Typical HTTP status |
|---|---|---|---|
| No token to protected API | Not authenticated | Does not reach permission policy | 401 |
| Invalid JWT signature | Authentication failure | Does not reach URL authorization | 401 |
| Wrong issuer/audience/expiry | Authentication failure | Does not reach URL authorization | 401 |
| Valid JWT, missing scope | Authenticated JwtAuthenticationToken | Denied | 403 |
| Valid JWT, sufficient scope but wrong tenant | Authenticated | Domain authorization denied | 403 or 404 per policy |
| @WithMockUser missing authority | Mock authenticated User | Denied | 403 |
| @WithMockUser sufficient authority | Mock authenticated User | Allowed | Passes URL policy |

Do not use `@WithMockUser` to test invalid tokens. The annotation creates a valid Authentication in the test context, not an invalid token.

## 13. Configuring MockMvc security properly

Spring Boot test example:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrdersSecurityTests {

    @Autowired
    MockMvc mvc;
}
~~~

With manually built MockMvc:

~~~java
mvc = MockMvcBuilders
    .webAppContextSetup(context)
    .apply(springSecurity())
    .build();
~~~

Static import:

~~~java
import static org.springframework.security.test.web.servlet.setup
    .SecurityMockMvcConfigurers.springSecurity;
~~~

Annotation-based test contexts like `@WithMockUser` use the Spring Security Test listener; request post-processors like `jwt()` attach Authentication to a specific request. Make sure MockMvc runs through the real filter chain when the goal is integration testing.

### 13.1. Be careful with addFilters = false

~~~java
@AutoConfigureMockMvc(addFilters = false)
~~~

can prevent security filters from running. Pure controller tests might use this setting for their own purposes, but the result must never be used to conclude Resource Server authentication works.

## 14. Servlet and WebFlux helpers differ

| Purpose | Servlet / MockMvc | WebFlux / WebTestClient |
|---|---|---|
| Mock user | `@WithMockUser` or `user()` | `@WithMockUser` or reactive test support |
| Mock JWT principal | `jwt()` | `mockJwt()` |
| Mock opaque token | `opaqueToken()` | Version-dependent reactive opaque-token support |
| HTTP test client | `MockMvc` | `WebTestClient` |
| Security chain | `SecurityFilterChain` | `SecurityWebFilterChain` |

`mockJwt()` in `SecurityMockServerConfigurers` is for WebFlux/WebTestClient. Do not import reactive helpers into Servlet MockMvc tests. Check packages/overloads for your Spring Security version.

## 15. Test helper selection matrix

| Goal | Appropriate helper | Does not prove |
|---|---|---|
| Authority-only method security | `@WithMockUser` | JWT principal/claims/decoder |
| Controller receiving Jwt | MockMvc `jwt()` | Signature, issuer, audience, configured converter |
| JWT claims in controller | `jwt().jwt(...)` | Real token signed by issuer |
| Opaque principal attributes | `opaqueToken()` | Introspection HTTP request/response |
| OIDC Login principal | `oidcLogin()` | Resource Server access-token authentication |
| Custom Authentication | `authentication(...)` | Provider/decoder pipeline |
| Reusable synthetic JWT context | Custom `@WithSecurityContext` | Bearer parsing/signature validation |
| Claim-to-authority converter | Converter unit test | Full filter-chain wiring |
| JWT signature/issuer/audience/expiry | Signed Bearer token through MockMvc | Production IdP availability |
| JWKS/key rotation | Decoder integration with JWKS stub/sandbox | Browser login unless tested separately |
| Opaque introspection | HTTP stub + real introspector | JWT decoder |

## 16. Common mistakes

### Mistake 1 — Using @WithMockUser and concluding the Jwt principal works

The annotation creates `UserDetails`, not `Jwt`. Use `jwt()` or a real Bearer JWT.

### Mistake 2 — Using roles instead of scope authority

`roles = ADMIN` creates `ROLE_ADMIN`, not `SCOPE_orders.read`.

### Mistake 3 — Setting authorities in jwt() and concluding the converter is right

`jwt().authorities(...)` already specifies the final result. Test the converter separately and test Bearer integration.

### Mistake 4 — Using jwt() to test signatures

The request post-processor creates a mock `JwtAuthenticationToken`; the decoder is not invoked. Send a compact JWT signed with a test key in the Authorization header.

### Mistake 5 — Using @WithMockUser to test issuer/audience

The annotation performs no issuer/audience validation. Use a decoder integration test with a properly signed token carrying invalid claims.

### Mistake 6 — Using oidcLogin() for Bearer APIs

The OIDC Login principal is `OidcUser`; a JWT Resource Server API typically uses `JwtAuthenticationToken`.

### Mistake 7 — Using the opaque helper while expecting to test the introspection endpoint

`opaqueToken()` simulates an existing authentication; it does not call the Authorization Server. Use an HTTP stub for the introspector.

### Mistake 8 — Disabling security filters in tests while still asserting security behavior

If the filter chain does not run, the test does not protect token extraction/validation.

### Mistake 9 — Tests only checking HTTP 200

A request may pass mock Authentication while the controller fails to receive the right claims or uses the wrong tenant. Assert principal/response and negative cases.

### Mistake 10 — Naming a test "valid JWT" when no compact JWT is decoded

Test names must reflect what was actually tested. If only creating a mock `JwtAuthenticationToken`, call it a JWT-principal/authorization test.

## 17. Layered testing strategy

~~~mermaid
flowchart TD
    A["JWT claim / authority converter unit tests"] --> B["MockMvc jwt() principal + authorization tests"]
    B --> C["Signed Bearer JWT through SecurityFilterChain"]
    C --> D["JWKS / issuer / audience / expiry integration tests"]
    D --> E["Tenant, owner, method-security and API behavior"]
~~~

1. **Converter tests:** claim schema, authority prefix, allowlist, and invalid claim types.
2. **Principal/authorization tests:** `jwt()` for JWT principals; `@WithMockUser` for generic authorities.
3. **Bearer filter-chain integration:** signed token, test private key, and decoder using public key; test extraction, signature, issuer, audience, time, and converter.
4. **Provider/edge integration:** JWKS, rotation, discovery, proxy, introspection, and error responses.

## 18. Checklist before choosing @WithMockUser

- [ ] Does the test only care about authorities or does it need a JWT principal?
- [ ] Does the controller take `@AuthenticationPrincipal Jwt`?
- [ ] Does method security read `authentication.principal.claims`?
- [ ] Does the test need issuer, audience, subject, or tenant claims?
- [ ] Do you need to test the scope/role converter?
- [ ] Do you need to test signature, expiry, issuer, or audience?
- [ ] Do you need to test Bearer header parsing and the 401 challenge?
- [ ] Is the token a JWT, opaque token, or OIDC Login principal?
- [ ] Are you using the right MockMvc helper vs WebTestClient helper?
- [ ] Does the test accidentally disable security filters?
- [ ] Does the test name accurately reflect what was mocked?
- [ ] Are there integration tests going through the Resource Server filter chain with signed tokens?

## 19. Conclusion

`@WithMockUser` fits tests that only need an authenticated user and authorities. It **does not fully simulate a Resource Server principal**: its principal is `UserDetails`, whereas a JWT Resource Server creates a `JwtAuthenticationToken` with a `Jwt` principal.

In Servlet testing:

- Use `@WithMockUser` for authority-only authorization.
- Use MockMvc `jwt()` for JWT principal/claims and authorization behavior.
- Use `opaqueToken()` for opaque principals.
- Use `oidcLogin()` for OIDC browser principals.
- Use custom `@WithSecurityContext` when a reusable synthetic principal is needed.
- Use **signed Bearer JWTs through MockMvc and a real decoder** to test token extraction, signatures, issuer, audience, time validators, and converter wiring.

No single helper replaces every testing layer. Choose the helper according to the principal contract and verify real tokens at the integration boundary used by the Resource Server.

### References

- [Spring Security Reference — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security Reference — Testing MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html)
- [Spring Security Reference — MockMvc Request Post Processors](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/request-post-processors.html)
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security Reference — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [Spring Security API — WithMockUser](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/support/WithMockUser.html)
- [Spring Security API — JwtAuthenticationToken](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationToken.html)
- [Spring Security API — Jwt](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/Jwt.html)
- [Spring Security API — SecurityMockMvcRequestPostProcessors](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/servlet/request/SecurityMockMvcRequestPostProcessors.html)

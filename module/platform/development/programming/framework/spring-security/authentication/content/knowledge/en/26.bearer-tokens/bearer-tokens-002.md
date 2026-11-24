# OAuth2 Resource Server Token Reception and Validation in Spring Security

## 1. Objectives

An API receiving a request with an `Authorization: Bearer <access-token>` header must decide **whether the token was issued by a trusted source, is valid, is intended for this API, and carries the appropriate permissions**. Spring Security provides **OAuth2 Resource Server** for this job: decoding/verifying JWTs or calling token introspection for opaque tokens, building an `Authentication`, and then enforcing authorization.

This lesson belongs to the **Bearer token** topic of the Spring Security - authentication module. After this lesson, you will be able to:

- Explain the role of the Resource Server (RS) compared to the Authorization Server (AS) and OAuth2 Client.
- Trace the path from the Bearer header through `BearerTokenAuthenticationFilter`, the provider, `SecurityContext`, and access control.
- Distinguish verification of **signed JWTs** from **opaque tokens via introspection**.
- Validate signature, issuer, audience, expiration, and scopes/authorities; avoid token confusion patterns.
- Build a Spring Boot 3.x / Spring Security 6.x / Java 17+ API and test 401, 403, and 200 responses.
- Understand the limits of token validation regarding tenants, account status, business data, key rotation, token revocation, and WebFlux.

The main examples use **Spring MVC/Servlet**. WebFlux differences are highlighted separately. A Resource Server **does not issue access tokens itself**, does not replace an Authorization Server, and does not provide a login page on its own.

## 2. Resource Server in the OAuth2 Model

Three roles must be distinguished:

| Role | Responsibility |
| --- | --- |
| **Authorization Server** | Authenticates/authorizes via appropriate flows, issues access tokens, and may publish JWKS and an introspection endpoint |
| **Client** | Obtains an access token per granted permissions and sends it to the target API |
| **Resource Server** | Protects the API, verifies access tokens, and permits only operations with appropriate permissions |

For example, an employee uses an app to read reports. The AS issues an access token with audience `reports-api` and scope `reports.read` to the client. The client sends:

```http
GET /api/reports HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
```

Spring Security validates the token before the controller accesses report data. Having a valid token **is not enough** to read reports belonging to any tenant or user: the system must also check ownership and business policies.

Processing flow:

```text
Client
  │ Bearer access token over HTTPS
  ▼
Spring Security Filter Chain
  │ Extract credential
  ▼
AuthenticationManager / Provider
  │ JWT decoder or opaque introspector
  ▼
Authenticated principal + GrantedAuthorities
  │
  ▼
AuthorizationFilter / @PreAuthorize / domain policy
  │
  ├── Sufficient permissions → Controller/Service
  └── Insufficient permissions → Reject request
```

**Bearer** means the party holding the token can use it when no additional sender-constrained protection exists. Therefore, transmitting over HTTPS, keeping tokens safe, minimizing lifetimes, and avoiding logging or placing tokens in URLs are essential requirements.

## 3. How Are Tokens Read and Processed?

In the Servlet stack, Spring Security provides `BearerTokenAuthenticationFilter`. The filter typically uses `BearerTokenResolver` to read the `Authorization: Bearer ...` header, then creates an **unauthenticated** `BearerTokenAuthenticationToken`.

JWT flow:

```text
HTTP Authorization: Bearer eyJ...
          ↓
BearerTokenAuthenticationFilter
          ↓ BearerTokenAuthenticationToken
AuthenticationManager (typically ProviderManager)
          ↓
JwtAuthenticationProvider
          ├── JwtDecoder (e.g., NimbusJwtDecoder)
          │   ├── Verify signature and public JWK
          │   └── Validate issuer, timestamps, audience, and policy
          └── JwtAuthenticationConverter
                 └── scopes/claims → GrantedAuthorities
          ↓
JwtAuthenticationToken (authenticated)
          ↓
SecurityContextHolder
          ↓
Authorization rules → API Controller
```

If the token is opaque and introspection is configured, the corresponding provider is `OpaqueTokenAuthenticationProvider`, which uses `OpaqueTokenIntrospector` to query the Authorization Server. The result is typically a `BearerTokenAuthentication` containing an `OAuth2AuthenticatedPrincipal`.

Do not write a custom filter using `request.getHeader("Authorization").substring(7)`: the framework already handles malformed headers, wrong schemes, and many error cases according to the Bearer Token specification. By default, the token is in the **Authorization header**. Putting tokens in query strings is discouraged because URLs easily leak via browser history, access logs, Referer headers, and monitoring tools.

### Authentication vs. Authorization

**Authentication** answers "Is the token valid and trustworthy according to the API's configuration?" **Authorization** answers "Is the authenticated principal allowed to perform this action on this resource?"

A token with a valid issuer, signature, and audience but missing the `reports.read` scope must still be rejected when requesting to read reports. In typical cases, a missing or invalid token → HTTP **401**; a valid token lacking authority → HTTP **403**.

## 4. JWT: Signature, Claims, and Mandatory Checks

A JWT access token typically has the form `header.payload.signature` (a JWS-signed JWT). You can Base64URL-decode it to read claims **without having the private key**, so the payload **is not encrypted secret content**. Being able to read the payload **does not prove** the token is trustworthy.

Illustrative payload example (not a usable JWT):

```json
{
  "iss": "https://idp.example.test/realm/training",
  "sub": "person-42",
  "aud": ["reports-api"],
  "scope": "reports.read reports.write",
  "iat": 1761000000,
  "nbf": 1761000000,
  "exp": 1761003600
}
```

Important checks:

| Check | Purpose |
| --- | --- |
| Signature + algorithm | Ensure the data is signed with a trusted key and allowed algorithm; reject `alg=none` and invalid keys/algorithms |
| `iss` | Matches the issuer allowed by the API; do not accept tokens from arbitrary issuers |
| `aud` | Contains the audience/resource identifier of **this API**; do not accept tokens intended for another API |
| `exp` | Token is unexpired, accounting for reasonable configured clock skew |
| `nbf` | Token has reached the time when it is permitted to be used |
| `iat` | Issuance time, checked against issuance rules if the system requires them |
| `scope` or `scp` | Granted scopes, converted into authorities |
| `sub` / `client_id` | Subject is a user or client application; interpret per grant type and AS contract |
| `typ`, token profile | Verify the right access token type if required by policy/AS, avoiding ID token confusion |

**Wrong audience is a very common bug.** A JWT issued by a trusted AS for `inventory-api` may have a valid signature and `exp`, yet `reports-api` **must not** accept it merely because it shares the issuer. Checking scope does not replace checking audience.

**A signed JWT is not automatically invalidated when a user logs out or an account is locked.** If you only check the signature and `exp`, the token can remain valid until expiration. The system needs appropriate token lifetimes, revocation/denylists, or introspection if it needs to reflect pre-expiry revocation.

## 5. JWT vs. Opaque Token

| Property | JWT local validation | Opaque token introspection |
| --- | --- | --- |
| Shape | Claims data + signature, typically three parts | String not directly interpreted at the RS |
| Verification method | `JwtDecoder` checks signature + claims against JWK and validators | `OpaqueTokenIntrospector` asks the AS for `active` and metadata |
| Network per request | Usually no, except when fetching/refreshing JWK | Usually makes a request to the introspection endpoint |
| Token revocation | Needs separate policy, may not update immediately | Can observe revocation status sooner depending on AS/cache |
| Principal after auth | Usually `JwtAuthenticationToken` / `Jwt` | Usually `BearerTokenAuthentication` / `OAuth2AuthenticatedPrincipal` |
| Scope mapping | `SCOPE_<scope>` by convention | `SCOPE_<scope>` by convention |

**Do not confuse format with verification method.** A JWT can also be introspected to check revocation; an opaque token has no JWT payload for the RS to read itself. Choose an approach based on the AS contract, trust level, latency, revocation needs, and API protection.

## 6. Configuring a JWT Resource Server in Spring Boot 3

The example below uses Java 17+, Spring Boot 3.x, Spring Security 6.x, and Spring MVC. The project has a standard Gradle wrapper, Spring Boot plugin, and dependency management; the Authorization Server/JWKS live outside the application.

### 6.1. Dependencies

The `dependencies` block in `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

The resource server starter pulls in the components to validate Bearer JWTs. If declaring Spring Security libraries manually, JWT also needs `spring-security-oauth2-jose` in addition to `spring-security-oauth2-resource-server`.

### 6.2. Issuer, JWKS URL, and Audience

Create `src/main/resources/application.yml`:

```yaml
security:
  jwt:
    issuer: ${JWT_ISSUER}
    jwk-set-uri: ${JWT_JWK_SET_URI}
    audience: ${JWT_AUDIENCE}
```

These three `security.jwt.*` keys are **custom properties for this example**, injected into the `JwtDecoder` bean in section 6.3. They do not automatically enable the resource server without the Java configuration below.

Environment values can be set as follows:

```bash
export JWT_ISSUER='https://idp.example.test/realm/training'
export JWT_JWK_SET_URI='https://idp.example.test/realm/training/protocol/openid-connect/certs'
export JWT_AUDIENCE='reports-api'
```

URLs containing `example.test` **are for illustration only**, not a live Authorization Server. In practice you must specify the exact issuer (matching `iss`), the JWKS path published by the AS, and the audience issued by the AS for the API. **Never derive a trusted JWKS URI or issuer from query parameters, headers, or an unverified JWT.**

### 6.3. Complete Java Source

All files are in the `com.example.resourceapi` package, located under `src/main/java/com/example/resourceapi/`.

**`ResourceApiApplication.java`**

```java
package com.example.resourceapi;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResourceApiApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResourceApiApplication.class, args);
    }
}
```

**`SecurityConfig.java`**

```java
package com.example.resourceapi;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/reports")
                        .hasAuthority("SCOPE_reports.read")
                        .anyRequest().authenticated())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .csrf(AbstractHttpConfigurer::disable)
                .oauth2ResourceServer(resource -> resource
                        .jwt(Customizer.withDefaults()))
                .build();
    }

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${security.jwt.jwk-set-uri}") String jwkSetUri,
            @Value("${security.jwt.issuer}") String issuer,
            @Value("${security.jwt.audience}") String audience) {

        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withJwkSetUri(jwkSetUri).build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audienceRule = token ->
                token.getAudience().contains(audience)
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                                new OAuth2Error(
                                        "invalid_token",
                                        "Required audience is missing",
                                        null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        issuerAndTime, audienceRule));
        return decoder;
    }
}
```

**Rationale for each configuration:**

1. `oauth2ResourceServer(...jwt(...))` attaches the Bearer JWT validation component to the Servlet SecurityFilterChain, using the `JwtDecoder` bean defined here.
2. `NimbusJwtDecoder.withJwkSetUri(...)` verifies signatures using public keys from a trusted JWK Set; the **AS's private signing key** is neither needed nor should it be placed on the RS.
3. `JwtValidators.createDefaultWithIssuer(...)` applies default issuer and timestamp validators. `audienceRule` is **combined with**, rather than replacing, issuer/time checks via `DelegatingOAuth2TokenValidator`.
4. `reports.read` is mapped by convention to `SCOPE_reports.read`. The `hasAuthority(...)` rule enforces **authorization** after valid authentication.
5. `SessionCreationPolicy.STATELESS` fits an API that accepts only Bearer tokens in this example. `csrf(AbstractHttpConfigurer::disable)` **is appropriate here only because the API does not use cookies or browser sessions as credentials**. If combining UI login/cookies, analyze CSRF and split security chains appropriately.
6. `anyRequest().authenticated()` protects URLs not explicitly permitted. In a real system, define granular policies for write/update/delete endpoints and multi-tenant data.

**`ReportController.java`**

```java
package com.example.resourceapi;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {

    @GetMapping("/api/reports")
    public String reports() {
        return "report: permitted";
    }
}
```

These Java files form a complete Spring Boot program demonstrating Resource Server wiring in a properly configured project. Access token issuance and JWKS hosting are the responsibility of an external AS. The controller runs only after the filters allow the request through.

### 6.4. Manual Testing with an Access Token from the AS

Run from the project directory:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Once a real AS issues a token **for audience `reports-api`** with scope `reports.read`, you can test:

```bash
curl -i http://localhost:8080/api/reports
curl -i -H 'Authorization: Bearer <VALID_ACCESS_TOKEN>' http://localhost:8080/api/reports
```

The placeholder must be replaced with a real token in the test environment. Never commit tokens, paste them into public docs, or leave them in shared shell history.

With a valid token, the endpoint returns HTTP 200 with expected body:

```text
report: permitted
```

Requests without a token typically receive 401. A validly signed token with the wrong audience or expired timestamp is still rejected; an authenticated token lacking `reports.read` typically receives 403. These are **expected outcomes based on configuration**, not stdout/HTTP observed from an AS in this lesson. Over a real network, use HTTPS.

## 7. Auto-Configuration with issuer-uri

If you do not need a custom decoder, Spring Boot supports configuring a JWT Resource Server using an issuer URI:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realm/training
```

With the starter and appropriate `oauth2ResourceServer(...jwt(...))` configuration, Spring Security can discover metadata/JWKS from the issuer and verify signatures, `iss`, `exp`, and `nbf`. Still, **you must validate the audience as required by the API**; do not assume `issuer-uri` checks every expected audience.

You can declare `jwk-set-uri` when separating key configuration from discovery, but must not drop issuer/time validators as a result. Across different Spring Boot/Security versions, discovery timing, key loading, or startup coupling may vary; consult the version-matched docs and test temporary IdP unavailability. Once you explicitly define a `JwtDecoder` bean as in section 6.3, that bean becomes the primary verification configuration; do not expect Boot to automatically merge properties without checking guarantees.

## 8. Scopes and GrantedAuthorities

Given a JWT with claims:

```json
{
  "sub": "alice",
  "scope": "reports.read reports.write"
}
```

Spring Security typically creates the authorities:

```text
SCOPE_reports.read
SCOPE_reports.write
```

Therefore, the rule:

```java
.requestMatchers(HttpMethod.GET, "/api/reports")
.hasAuthority("SCOPE_reports.read")
```

is a DSL snippet inside `authorizeHttpRequests`. It is **different from** `hasRole("ADMIN")`, which normally looks for `ROLE_ADMIN`. Never assume `scope=admin` means `ROLE_ADMIN` unless the system implements an explicit, controlled authority mapping.

When a provider uses a different claim, you can customize `JwtGrantedAuthoritiesConverter` and `JwtAuthenticationConverter`. Example **snippet replacing the default jwt configuration**, placed inside the filter chain bean method with appropriate imports added:

```java
JwtGrantedAuthoritiesConverter permissions =
        new JwtGrantedAuthoritiesConverter();
permissions.setAuthoritiesClaimName("permissions");
permissions.setAuthorityPrefix("PERMISSION_");

JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
converter.setJwtGrantedAuthoritiesConverter(permissions);

http.oauth2ResourceServer(resource -> resource
        .jwt(jwt -> jwt.jwtAuthenticationConverter(converter)));
```

Imports:

```java
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
```

This snippet is not a standalone class; configure it only when the AS has a trusted `permissions` claim contract and the API defines a clear policy. If the application needs object-level permission checks (which tenant or owner a report belongs to), scopes are only the initial check; the service must still check verified identity against business data.

With the client-credentials grant, a token may represent a **client application** rather than an employee; never assume every bearer token maps to a local user.

## 9. MockMvc Testing: Distinguishing 401, 403, and Success

In `src/test/java/com/example/resourceapi/ResourceApiSecurityTest.java`:

```java
package com.example.resourceapi;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "security.jwt.issuer=https://idp.example.test/realm/training",
        "security.jwt.jwk-set-uri=https://idp.example.test/jwks",
        "security.jwt.audience=reports-api"
})
@AutoConfigureMockMvc
class ResourceApiSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void missingTokenIsUnauthorized() throws Exception {
        mvc.perform(get("/api/reports"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedWithReadScopeCanAccess() throws Exception {
        mvc.perform(get("/api/reports")
                .with(jwt().authorities(
                        new SimpleGrantedAuthority("SCOPE_reports.read"))))
                .andExpect(status().isOk())
                .andExpect(content().string("report: permitted"));
    }

    @Test
    void authenticatedWithoutReadScopeIsForbidden() throws Exception {
        mvc.perform(get("/api/reports")
                .with(jwt().authorities(
                        new SimpleGrantedAuthority("SCOPE_other"))))
                .andExpect(status().isForbidden());
    }
}
```

Run:

```bash
./gradlew test
```

All three tests are expected to pass in a Boot 3.x project configured as above. **Limitation:** the `jwt()` helper from `spring-security-test` injects a simulated `Authentication` into the request; **it does not verify JWT signature, `iss`, `aud`, expiration, or JWKs from a real AS**. Thus these tests prove security rules/controller behavior, not that the JWT decoder is correct.

To test the authentication path end-to-end, run HTTP tests with `Authorization: Bearer <real-jwt-signed-with-test-key>` through `BearerTokenAuthenticationFilter` and `JwtDecoder` against a controlled test JWKS server. Cover: tampered signature, wrong algorithm, wrong issuer, different audience, expired token, before `nbf`, mismatched `kid`, JWKS rotation, valid token missing scope, and AS/JWKS unavailability. Never use production private keys in tests.

## 10. Opaque Token Branch with Introspection

Some ASs issue opaque access tokens; the RS cannot decode or verify their signatures locally. In that case, use the OAuth2 token introspection endpoint. Example **configuration replacing the JWT branch**, keeping the Resource Server dependency:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.test/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

And replace `.jwt(Customizer.withDefaults())` in the DSL with:

```java
.oauth2ResourceServer(resource -> resource
        .opaqueToken(Customizer.withDefaults()))
```

This is a configuration snippet, not a standalone class. The opaque branch uses `OpaqueTokenAuthenticationProvider` and `OpaqueTokenIntrospector`; the token is sent to the introspection endpoint along with client authentication credentials. Illustrative response example:

```json
{
  "active": true,
  "sub": "person-42",
  "client_id": "web-client",
  "scope": "reports.read"
}
```

The AS returns `active=false` when the token is no longer valid under its policies; the Resource Server rejects it. When `active=true`, Spring Security can map scopes to `SCOPE_reports.read` for authorization.

**You must also check audience/resource and API policy in the introspection workflow.** A token that is active at the AS is not automatically valid for every RS. If the endpoint does not return sufficient metadata, enforce resource binding at the AS or add appropriate trust validation logic.

Introspection typically incurs a network round trip per request, so configure timeouts, metrics, rate limits, appropriate circuit breakers/backoff, and cache TTL decisions. Caching improves throughput but can delay detection of revoked tokens. Never log tokens or introspection client secrets. If using introspection to validate a JWT-formatted token, Spring Security still processes it via the **introspection/opaque branch**, not automatically switching to `JwtAuthenticationToken`.

## 11. 401, 403 Status Codes and Response Headers

| Scenario | Typically Returns | Explanation |
| --- | --- | --- |
| Missing token on protected endpoint | 401 | No Authentication present |
| Malformed JWT, bad signature, wrong issuer/audience, expired | 401 | Token failed authentication |
| Valid bearer token lacking required scope | 403 | Authentication succeeded, Authorization denied |
| Valid token, matching permissions, allowed by data policy | 2xx | Controller executes |
| AS/introspection unavailable | Auth/infrastructure error requiring dedicated handling | Must not let unverified request proceed |

The bearer mechanism per RFC 6750 can send `WWW-Authenticate: Bearer` with an error like `invalid_token` or `insufficient_scope` when appropriate. Do not hardcode expectations that all errors produce the same HTTP status if the application uses a custom `AuthenticationEntryPoint`/`AccessDeniedHandler`; test the actual behavior of the deployed filter chain.

**Fail closed** when unable to authenticate. Still, logging and metrics should distinguish genuinely invalid tokens from network failures reaching JWKS/introspection, avoiding misattributing operational outages to user errors.

## 12. Common Security Mistakes

1. **Only Base64-decoding a JWT and trusting the payload.** Unverified data can be forged by an attacker. Use a real `JwtDecoder` and validators.
2. **Omitting audience validation.** A valid JWT for another resource could be mistakenly accepted. The AS must issue tokens with the right audience and the RS must check it.
3. **Trusting any issuer or JWK URL declared by the client.** An unverified token cannot select its own trusted key source. Use a safe allowlist/configuration.
4. **Using an OIDC ID token instead of an access token.** An OIDC ID token is for the relying party, not a bearer access token for an API.
5. **Confusing scopes with internal roles.** `SCOPE_reports.read` does not automatically imply `ROLE_ADMIN`.
6. **Checking only `authenticated()` with multi-tenant data.** Both scopes and object-level access checks are needed.
7. **Disabling CSRF globally when the app still uses sessions/cookies.** Design separate chains for bearer APIs and browser UIs.
8. **Putting bearer tokens in URLs or logs.** Tokens can be reused by anyone who obtains them.
9. **Not handling key rotation/caching.** JWKS changes or IdP failures can cause API outages.
10. **Treating MockMvc `jwt()` as signature testing.** It bypasses the decoder; add real JWT integration tests.
11. **Checking only `exp` and ignoring account status.** A JWT may remain unexpired when an account is locked; implement revocation/account policies.
12. **Trusting `scope=admin` from a wrong-issuer/wrong-audience token.** Authorization is meaningful only after authentication is proven.

## 13. Multi-Issuer and Gateways

When an API accepts tokens from multiple ASs or tenants, configure an explicit set of trusted issuers and select the matching `AuthenticationManager`/decoder. You can use `AuthenticationManagerResolver<HttpServletRequest>` or Spring Security's multi-tenancy support; what matters is an **issuer allowlist**, signature verification after selection, proper audience for the API, and tenant isolation.

Reading the `iss` claim **before** verification to select a decoder is only a routing step, not accepting that claim as true. Never take an arbitrary URL from an unverified `iss` and fetch keys on the client's demand.

If the API sits behind a gateway that already validated the token, the system must clearly define whether the backend still validates the bearer token or trusts forwarded identity over a protected channel (mTLS, network isolation, header stripping/overwriting). A client-supplied `X-User` header is not authentication proof. Also never forward a token from API A to API B when the audience is only for A; use token exchange or a flow that issues a token for the target resource when needed.

## 14. Operations and Limitations

- **Token protection:** TLS, secure storage, never log bearer tokens, never share secrets/JWK private keys.
- **Resources:** JWT signature verification consumes CPU; introspection consumes network and AS capacity. Measure p95/p99 latency, timeouts, JWKS cache behavior, and error rates.
- **Time synchronization:** `exp`/`nbf` depend on clocks; use a small reasonable clock skew, never turn it into arbitrary token lifetime extension.
- **Permissions:** a token with the right scope still needs object-level authorization, tenant checks, and business policy enforcement.
- **CORS:** controls browser origins, but CORS is not authentication and does not block non-browser clients.
- **Rate limiting:** limits abuse and protects the AS/JWKS from being overwhelmed by invalid token requests.
- **Revocation:** consider short-lived access tokens, introspection, denylists, or internal status checks as needed; each choice trades off revocation latency and throughput.
- **Token profile:** when the AS follows RFC 9068 or a custom format, the RS must check required claims/token typing per contract; do not rely solely on signature.

## 15. How Does WebFlux Differ?

The Spring MVC code above uses `HttpSecurity`, `SecurityFilterChain`, and `JwtDecoder`. Spring WebFlux applications use `ServerHttpSecurity`, `SecurityWebFilterChain`, and `ReactiveJwtDecoder` or `ReactiveOpaqueTokenIntrospector`. Trust boundaries, issuer/audience checks, signatures, scopes, and authorization are essentially the same, while the APIs and lifecycle are reactive.

The WebFlux snippet **illustrates configuration only**, is not a standalone runnable class, and requires a real decoder and validation:

```java
@Bean
SecurityWebFilterChain api(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/api/**").authenticated()
                    .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                    .jwt(Customizer.withDefaults()))
            .build();
}
```

The types live in `org.springframework.security.config.web.server.ServerHttpSecurity`, `org.springframework.security.web.server.SecurityWebFilterChain`, and `org.springframework.security.config.Customizer`. Do not copy `HttpSecurity` into WebFlux or use a Servlet `JwtDecoder` as a `ReactiveJwtDecoder`.

## 16. Exercises and Summary

Try these scenarios in a test environment with a controlled AS/JWKS:

1. Create an access token with a valid signature and matching issuer/scope, but `aud=inventory-api`. Why must `reports-api` reject it?
2. Send a token with the right audience but missing `reports.read`. Analyze which step returns an error and whether 401 or 403 is expected.
3. Test an invalid JWT signature, expired token, future `nbf`, JWKS key rotation, and an unavailable IdP.
4. Compare the latency of local JWT validation against opaque introspection. Try revoking a token to observe the difference.
5. Add a tenant-based access rule in the service. Explain why the `reports.read` scope is insufficient to view another tenant's report.
6. Distinguish `oauth2Login()`, `oauth2Client()`, and `oauth2ResourceServer()` in an application hosting both a website and an API.

Key takeaway: **The Resource Server verifies and enforces permissions on received access tokens.** JWTs require signature/issuer/audience/time and permission checks; opaque tokens require introspection plus trusted metadata and authorization. Authentication and authorization are two separate steps; both must be right for an API to be secure.

**Official references:**

- [Spring Security 6.5 – OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/index.html)
- [Spring Security 6.5 – JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
- [Spring Security 6.5 – Opaque Token](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security 6.5 – Bearer Tokens](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/bearer-tokens.html)
- [RFC 6750 – Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750), [RFC 7662 – Token Introspection](https://www.rfc-editor.org/rfc/rfc7662), [RFC 9068 – JWT Access Token Profile](https://www.rfc-editor.org/rfc/rfc9068).
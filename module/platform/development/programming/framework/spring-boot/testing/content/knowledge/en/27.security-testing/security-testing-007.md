# Mocked Authentication Does Not Prove Token Signatures or the Full Authentication Flow

## 1. Core problem: a 200 HTTP test has not necessarily verified authentication

In Spring Boot, a security test can turn “green” very easily:

~~~java
mockMvc.perform(get("/api/orders/me")
        .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders:read"))))
        .andExpect(status().isOk());
~~~

Or:

~~~java
@Test
@WithMockUser(username = "alice",
              authorities = "SCOPE_orders:read")
void userCanAccessOrders() throws Exception {
    mockMvc.perform(get("/api/orders/me"))
            .andExpect(status().isOk());
}
~~~

Both are helpful when testing **authorization**, yet they **do not prove**:

- That user `alice` actually exists in the database or identity provider.
- That passwords, MFA, sessions, redirects, OAuth2 Authorization Code, or PKCE executed.
- That the client sent a valid `Authorization: Bearer ...` over the network.
- That the JWT carries a valid algorithm signature signed by a trusted issuer's private key.
- That the JWT was verified by a real `JwtDecoder` against a public key/JWKS.
- That `iss`, `aud`, `exp`, `nbf`, token type, and required claims were checked properly.
- That forged, expired, wrong-audience, or payload-tampered tokens are rejected.
- That key rotation and JWKS discovery work against a real authorization server.

This is not a bug in `@WithMockUser` or `jwt()`. These helpers **intentionally** place a pre-built `Authentication` into the Spring Security test context so you can test policies without logging in or signing tokens. The mistake happens when test results are interpreted beyond the scope they actually exercised.

This lesson teaches how to stratify Spring Security tests by goal using **Java 17, Spring Boot 3.5.16, Spring Security 6.5, JUnit Jupiter, MockMvc**, and a lab that generates an RSA key pair inside tests and signs real JWTs with `NimbusJwtEncoder`. The HTTP Bearer path runs through the real filter and `NimbusJwtDecoder`; forged signatures, wrong issuer/audience, expired tokens, future `nbf`, and missing scopes are tested individually.

### Learning objectives

1. Distinguish **authentication** (identifying who), **authorization** (what they may do), and **token validation** (verifying evidence).
2. Understand the exact scope of `@WithMockUser`, `user()`, `jwt()`, `oauth2Login()`, `oidcLogin()`, and mocked `JwtDecoder`.
3. Never treat the presence of a pre-constructed `SecurityContext` as proof of having gone through login.
4. Understand the three-part `header.payload.signature` JWT format, JWS signatures, and the rule that *a decoded payload is untrusted*.
5. Test real Bearer tokens through `BearerTokenAuthenticationFilter`, `JwtAuthenticationProvider`, and `JwtDecoder`.
6. Distinguish HTTP `401 Unauthorized` from `403 Forbidden`.
7. Test RSA signatures, issuer, audience, expiration, not-before, scope/authority, and forbidden algorithms.
8. Understand why signed-token resource-server tests do not replace testing full OAuth2/OIDC Authorization Code + PKCE, token endpoints, MFA, cookies, and sessions.
9. Use test-only key pairs without needing real private keys or touching production issuers.
10. Choose unit, MVC slice, security filter-chain integration, and identity-provider end-to-end tests based on risk.

## 2. Three concepts often conflated

### 2.1. Authentication: identifying the caller

Authentication is the process of verifying a caller's credentials/evidence:
- Username + password.
- Session cookie backed by a server-side session or token.
- Verified Bearer JWT access token.
- Introspected opaque access token.
- mTLS client certificate, passkey/WebAuthn, SAML assertions, or other mechanisms.

Once an `Authentication` object sits in `SecurityContextHolder`, downstream components treat the caller as authenticated. However, **having a test helper place that object there** does not mean credentials passed through a real authentication provider.

### 2.2. Authorization: deciding access permissions

Authorization evaluates authorities, scopes, roles, ownership, tenant context, and business policies. For example, an endpoint:

~~~java
.requestMatchers("/api/orders/me")
.hasAuthority("SCOPE_orders:read")
~~~

answers “does the caller hold the required authority?”, **not** “did that authority originate from a validly signed JWT?”. When a test supplies the authority directly, the policy can still be verified, yet the authority's source is a test fixture.

### 2.3. Token validation: verifying evidence

For an OAuth2 Resource Server accepting Bearer JWTs, the real execution path typically includes:

~~~text
HTTP request
  |
  | Authorization: Bearer eyJ...
  v
BearerTokenAuthenticationFilter
  |
  v
AuthenticationManager / JwtAuthenticationProvider
  |
  v
JwtDecoder
  |-- parse compact JWS
  |-- enforce trusted algorithms
  |-- select matching public key (local/JWKS)
  |-- verify signature
  |-- validate exp / nbf / iss / aud / token type ...
  v
JwtAuthenticationConverter
  |-- convert scope / scp -> SCOPE_...
  v
JwtAuthenticationToken / SecurityContext
  |
  v
AuthorizationFilter / method security
  |
  v
Controller and business logic
~~~

MockMvc `jwt()` and `@WithMockUser` jump in near the end of the pipeline: they supply or simulate `Authentication` without producing a signed, verified Bearer token. Proving signatures requires testing the real token-evidence path.

## 3. Exact scope of test helpers

### 3.1. @WithMockUser

`@WithMockUser` creates a fake user in the test context. The user need not exist in `UserDetailsService` or a database. Per Spring Security docs, the `Authentication` placed in context is a `UsernamePasswordAuthenticationToken` with a Spring Security `User` principal.

~~~java
@WithMockUser(username = "alice",
              roles = "ADMIN")
@Test
void adminPolicy() {
    // @PreAuthorize/authorization rules can use ROLE_ADMIN.
}
~~~

This is a snippet, not a standalone runnable test. It is valuable when testing `hasRole("ADMIN")` policies. However, the test **never invokes** password encoders, credential checkers, login forms, OAuth2 authorization servers, Bearer JWT decoders, or MFA.

**Notes on roles vs authorities:**
- `roles = "ADMIN"` generates authority `ROLE_ADMIN`.
- `authorities = "SCOPE_orders:read"` generates that exact authority.
- Spring OAuth2 JWT resource servers typically convert scope `orders:read` into `SCOPE_orders:read`.
- Role/scope names must match policy exactly; never reason backward from a mock role to a real JWT scope.

### 3.2. MockMvc .with(user(...))

~~~java
mvc.perform(get("/api/orders/me")
        .with(user("alice").authorities(
                new SimpleGrantedAuthority("SCOPE_orders:read"))))
        .andExpect(status().isOk());
~~~

This snippet uses `SecurityMockMvcRequestPostProcessors.user(...)` and Spring Security MockMvc integration. It likewise supplies a mock user without sending a real username/password for verification. Use it for request-scoped authorization scenarios.

### 3.3. MockMvc .with(jwt())

~~~java
mvc.perform(get("/api/orders/me")
        .with(jwt().jwt(builder ->
                builder.claim("sub", "alice"))
                .authorities(
                        new SimpleGrantedAuthority(
                                "SCOPE_orders:read"))))
        .andExpect(status().isOk());
~~~

`SecurityMockMvcRequestPostProcessors.jwt()` creates a `JwtAuthenticationToken` and attaches it to the request/`SecurityContext`. The API docs emphasize that details are declared directly and **do not require the JWT to be valid**.

It tests well:
- URL/method policy rules for a simulated JWT principal.
- Authorities **assigned directly** in the test.
- Controller/service handling of principal ID/claims once `SecurityContext` is populated.
- Negative cases when the caller lacks an authority supplied by the test.

It **does not** test:
- RSA/ECDSA/HMAC signatures or `alg`.
- JWKS discovery/refresh, `kid`, or key rotation.
- Compact JWT serialization from HTTP headers.
- Whether `iss`, `aud`, `exp`, `nbf` are rejected by the decoder.
- Whether the authentication filter actually calls `JwtDecoder`.

When using `jwt().authorities(...)`, a test can even assign the expected scope **even if the mock JWT lacks the matching `scope` claim**. That is fine for isolating policy, yet wrong if labeled “tested scope claim converter end-to-end”.

### 3.4. Mocking JwtDecoder

With `@MockitoBean JwtDecoder decoder` and a stub:

~~~java
when(decoder.decode("sample-token"))
        .thenReturn(fakeJwt);
~~~

you can test that the Bearer header reaches the filter, the decoder is called, and a `Jwt` object is converted/authorized. Still, this is **not real signature verification**: the mock decoder returns whatever the test tells it to, even if the token string has no signature. Verifying signatures requires a real decoder with real **test-only** keys.

In Spring Boot 3.5/Spring Framework 6.2, `@MockitoBean` replaces a bean in the Spring context via test bean overriding. It differs from Mockito's `@Mock` (which does not replace Spring beans) and replaces the deprecated older `@MockBean`.

### 3.5. oauth2Login()/oidcLogin()

Spring Security Test also provides `oauth2Login()` and `oidcLogin()` MockMvc postprocessors. They populate `OAuth2AuthenticationToken`/OIDC principals and authorities to test **downstream paths** once logged in. They do not open a browser to an Identity Provider, redirect to the authorize endpoint, exchange authorization codes at the token endpoint, verify PKCE, fetch JWKS, or enforce MFA.

### 3.6. Opaque token postprocessor

`opaqueToken()` plays the same role for resource servers using token introspection: it simulates an authenticated principal/claims and **does not perform** real HTTP introspection against an authorization server. To verify opaque token validity, use a real `OpaqueTokenIntrospector` or a test IdP/introspection stub in an integration environment.

## 4. Why can a valid-looking JWT payload still be forged?

### 4.1. Three parts of a compact JWT

A JWS-signed JWT typically takes the form:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

Example header:

~~~json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "test-key"
}
~~~

Example claims:

~~~json
{
  "iss": "https://issuer.example.test",
  "sub": "alice",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "iat": 1760000000,
  "nbf": 1760000000,
  "exp": 1760000300
}
~~~

The numeric timestamps here **only illustrate structure**, not usable claims for the current date. A JWT decoded via Base64URL **has not** been verified. Anyone can craft a payload with `sub=admin` or `scope=orders:read`; only a valid signature under the trust policy proves the contents were not tampered with since a trusted signer signed it.

### 4.2. What is RS256?

`RS256` uses RSA signatures with SHA-256:
- The authorization server/issuer holds the **private key** to sign.
- The resource server uses the corresponding **public key** to verify.
- If an attacker alters the payload or signs with a different private key, signature verification fails.
- `kid` selects a public key from JWKS; `kid` itself **does not prove trust**.

Other algorithms like ES256 or HS256 have different key models. A Resource Server must enforce an allowlist of accepted algorithms and matching key types; never choose trust policy solely from the attacker-supplied `alg` header.

### 4.3. alg=none and algorithm confusion

A token with `{"alg":"none"}` is not a JWT signed under an RS256 policy. A decoder configured to allow only RS256 must reject it. Similarly, never accidentally allow HS256 on an endpoint expecting an RSA public key or treat public key bytes as an HMAC secret. Ensure algorithm policy is configured on the verifier rather than trusting claims inside the token.

Defensive tests can craft unsigned/wrong-alg/tampered tokens and assert 401. You do not implement a weak signing path to prove safety; you simply verify the decoder **refuses** them.

### 4.4. iss, aud, and scope differ

- `iss`: who issued the token. The Resource Server must trust that issuer.
- `aud`: which resource the token is intended for. Right issuer with an audience for another API must not be accepted here.
- `sub`: subject identity; does not grant authority by itself.
- `scope`/`scp`: delegated permissions, typically mapped to `SCOPE_...`.
- `exp`: expiration timestamp; clock skew may apply.
- `nbf`: not valid before this timestamp; clock skew may apply.
- `iat`: issued-at time, useful for token age/diagnostics, not a substitute for validators.
- `jti`: token ID, useful for replay/revocation if backed by a store/policy.
- `typ`: distinguishes token types if required by the API; never treat every signed JWT as an access token.

**A valid signature does not automatically mean the token is authorized for use.** A signed ID token or an access token for another audience can be invalid for this API.

## 5. Resource Server authentication with Spring Security

### 5.1. Dependencies actually required

A JWT OAuth2 Resource Server needs:
- `spring-security-oauth2-resource-server` for Bearer token filter/provider.
- `spring-security-oauth2-jose` for JWT parsing/signatures/JWS/JWK.
- `spring-security-test` in tests for `@WithMockUser`, `jwt()`, and security test support.

Spring Boot starter `spring-boot-starter-oauth2-resource-server` bundles the required runtime artifacts. `spring-boot-starter-test` brings JUnit/AssertJ/Mockito but does not replace `spring-security-test`.

### 5.2. Common production configuration

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org/real-issuer
          audiences: https://orders-api.example.org
~~~

This is a **production configuration sample**; do not copy it into the demo lab. In supported Spring Security/Boot versions, `issuer-uri` lets the Resource Server discover metadata/JWKS and validate the issuer. `audiences` enforces `aud` checks. Never assume audience is checked if the app **has not configured a validator or `audiences`**.

Another option when the JWKS URI is known:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org/real-issuer
          jwk-set-uri: https://idp.example.org/real-issuer/keys
          audiences: https://orders-api.example.org
~~~

Setting `jwk-set-uri` explicitly can avoid startup/first-request discovery coupling depending on configuration, while still validating the issuer. In practice, the JWKS endpoint must be a **trusted HTTPS location**, never automatically fetching arbitrary URLs from untrusted `jku`/`x5u` JWT headers.

### 5.3. What does Spring Security check by default?

Per Spring Security 6.5 docs, a typical JWT Resource Server:
- Verifies the signature using keys from JWKS or a decoder bean.
- Validates `exp`, `nbf`, and `iss` when issuer is configured.
- Converts scopes into `SCOPE_`-prefixed authorities.
- Can validate `aud` via Boot properties or a custom `OAuth2TokenValidator`.

Inspect your **application's real configuration**: if you replace the `JwtDecoder` bean or install a custom authentication converter, defaults may differ from examples. Tests should guard validator configuration too.

### 5.4. 401 and 403

| Scenario | Typical expected status | Reason |
| --- | --- | --- |
| No Bearer credential on protected endpoint | 401 | Unauthenticated |
| Malformed Bearer string | 401 | Cannot be decoded |
| Invalid signature | 401 | Untrusted evidence |
| Expired / not-yet-valid JWT | 401 | Invalid token |
| Wrong issuer/audience | 401 | Unaccepted token |
| Valid JWT missing `orders:read` | 403 | Authenticated yet missing authority |
| Valid JWT with right scope | 200 | Authentication + authorization succeeded |
| Mock user granted right authority | Can be 200 | **Does not prove token was verified** |

HTTP statuses can vary if an application customizes entry points or error handling. With the default Bearer resource server, 401 vs 403 is the fundamental distinction to assert. You may inspect `WWW-Authenticate: Bearer ...` when required by contract, avoiding hard-coding sensitive error details.

## 6. Multi-layered testing strategy

### 6.1. Layer 1: pure unit policy tests

Use Java/JUnit/Mockito to verify business permissions like “owners see their own orders, admins see all orders” without web or JWT layers. Fixtures for principal/roles/ownerId must be explicit. This layer is cheap, fast, and covers many domain branches.

### 6.2. Layer 2: @WebMvcTest + mocked Authentication

Keep controllers and Spring Security filter/authorization config, using `@WithMockUser` or `jwt()` to populate identities/authorities. Great for verifying:
- URL matchers / `hasAuthority` / method security if needed beans are imported.
- HTTP 200/403 for pre-built principals.
- Principal mapping inside controllers.

**Never** label this layer `JWT signature test`, `login flow test`, or `IdP integration test`.

### 6.3. Layer 3: resource-server authentication integration

Use `@SpringBootTest + @AutoConfigureMockMvc` with the real filter chain, real `JwtDecoder`, and JWTs signed with a **test private key**. Send real HTTP `Authorization` headers:

~~~text
Authorization: Bearer <compact-signed-JWS>
~~~

These tests verify:
- Header extraction and Bearer authentication filter.
- JWS signature verification.
- `exp`/`nbf`, issuer, and audience validators when configured.
- Authority conversion from `scope` and access policy.
- Status 401/403/200.

Because the JWT is created by a **test encoder** and in-memory keypair, it still does not prove the production authorization server issues valid tokens, nor JWKS network discovery/caching/rotation, OAuth2 redirect/code exchange, or MFA.

### 6.4. Layer 4: JWKS/issuer integration

Run a local test HTTP server serving issuer metadata and JWKS:
- Configure Resource Server `issuer-uri`/`jwk-set-uri` to the test URL.
- Issue JWTs signed with the matching private key.
- Verify metadata/JWKS requests, algorithm allowlist, and `kid` selection.
- Rotate Key A -> B and verify cache/refresh semantics and old-key acceptance policy.
- Test JWKS unavailable, HTTPS/certificate errors, and timeouts as required.
- Verify issuer/audience checks even when signatures are valid.

Fast CI does not need a real IdP; a stub server provides stable contract responses. Still, stubs only prove the application works against the **simulated contract**.

### 6.5. Layer 5: full OAuth2/OIDC flow

When the system uses Authorization Code + PKCE, cookies/sessions, and OIDC, test at the browser/real authorization server test-tenant level:
1. Client generates `state`/`nonce` and PKCE code verifier/challenge.
2. Browser redirects to authorization endpoint.
3. User logs in, completing MFA if configured.
4. Authorization server issues authorization code and redirects back.
5. Client posts code + `code_verifier` to token endpoint.
6. Token endpoint validates client/`redirect_uri`/code/PKCE.
7. Client receives tokens, validates ID token/nonce for OIDC, and establishes session per design.
8. Resource server receives access token, verifies it, and authorizes access.
9. Test logout, revoked sessions/tokens, expired tokens, CSRF/cookies, and negative flows.

`@WithMockUser`/`jwt()` **perform none of these steps**. Even Layer 3's signed-JWT resource-server test only tests **the API accepting the token**, not how the token was issued.

### 6.6. Selection matrix

| Tool | Exercises Spring Security policy? | Real Bearer header? | Verifies signature? | Full login/IdP flow? |
| --- | --- | --- | --- | --- |
| Pure unit + mocked principal | Depends on invocation | No | No | No |
| `@WithMockUser` | Yes, with context/filters enabled | No | No | No |
| MockMvc `user()` | Yes | No | No | No |
| MockMvc `jwt()` | Yes | No | No | No |
| `@MockitoBean JwtDecoder` | Yes + Bearer filter if header sent | Possibly | **No** | No |
| Real `NimbusJwtDecoder` + signed JWT | Yes | Yes | **Yes** | No |
| Real decoder + test JWKS server | Yes | Yes | Yes, including key discovery | No |
| Browser + test IdP + API | Yes | Yes | Yes | Whichever flow steps are actually executed |

## 7. Java 17 / Spring Boot 3.5.16 lab: mock vs real RSA JWT

### 7.1. Lab objective

Build an API `GET /api/orders/me` accepting only authority `SCOPE_orders:read`, returning JSON with the principal name and `Authentication` class in context. Two test classes:

1. **MockAuthenticationMvcTest**: uses `@WithMockUser` or `jwt()` to prove authorization policies can PASS without any Bearer JWT signature.
2. **SignedJwtResourceServerTest**: uses a test RSA keypair, signs JWS tokens with `NimbusJwtEncoder`, and calls the endpoint via `Authorization: Bearer ...`. A real `NimbusJwtDecoder` verifies signatures, issuer, audience, and time window; tests verify invalid tokens are rejected.

Keypair design:
- RSA 2048 generated once in the Spring TestContext.
- Private key **lives only in `src/test/java`**, never packaged for production.
- Test `JwtEncoder` signs with the private key.
- Test `JwtDecoder` verifies with the public key.
- `JwtValidators.createDefaultWithIssuer` validates issuer and timestamps.
- Custom audience validator requires `aud` to contain `orders-api`.
- Spring Security's default scope conversion produces `SCOPE_orders:read`.
- A different RSA key, even with the same `kid` and claims, is rejected.

**Scope:** JUnit/MockMvc uses mock servlet requests without opening a TCP server; this **does not** diminish JWT signature/filter-chain verification because the HTTP `Authorization` header still traverses the real filter and decoder. It does not test TLS/network proxies, browser logins, or external IdPs.

### 7.2. Directory structure

~~~text
auth-mock-vs-real-lab/
├── pom.xml
├── src/main/
│   ├── java/com/example/authlab/
│   │   ├── AuthLabApplication.java
│   │   ├── ApiSecurityConfig.java
│   │   └── OrdersController.java
│   └── resources/application.properties
└── src/test/java/com/example/authlab/
    ├── TestJwtSupportConfig.java
    ├── MockAuthenticationMvcTest.java
    └── SignedJwtResourceServerTest.java
~~~

Match package and file names exactly. Every Java class contains full imports to compile. Code in Sections 7.3–7.9 forms an **intended runnable project**, distinct from the short conceptual snippets in other sections.

### 7.3. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>auth-mock-vs-real-lab</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Spring Boot 3.5's Maven BOM manages compatible Spring Security, Spring Test, Nimbus JOSE, Mockito, and JUnit versions. Do not add a separate unaligned Nimbus version unless needed.

### 7.4. application.properties

`src/main/resources/application.properties`:

~~~properties
spring.application.name=auth-mock-vs-real-lab
server.port=8080
~~~

**Intent:** The lab omits production `issuer-uri` from main configuration. When running JUnit, the test-only decoder bean is `@Import`-ed from `TestJwtSupportConfig`. To run `mvn spring-boot:run` standalone, supply production-like issuer/JWKS settings or a runtime `JwtDecoder` bean; never put test private keys under `src/main` just to let the app boot.

### 7.5. AuthLabApplication.java

~~~java
package com.example.authlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(AuthLabApplication.class, args);
    }
}
~~~

### 7.6. ApiSecurityConfig.java

~~~java
package com.example.authlab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                HttpMethod.GET, "/api/orders/me")
                        .hasAuthority("SCOPE_orders:read")
                        .anyRequest().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

Explanation:
- The URL matcher requires the exact authority `SCOPE_orders:read`.
- Resource Server JWT authentication is enabled via `oauth2ResourceServer(...jwt...)`.
- CSRF is left as-is: the demo only exposes GET so it does not depend on CSRF. For stateless REST APIs with POST/PUT, decide CSRF based on cookie/session/credential threat modeling; never turn off protections just so tests PASS easily.
- No `JwtDecoder` is configured in main: the integration test supplies a real decoder using the test public key. Production uses approved issuer/JWKS settings.
- `@EnableMethodSecurity` is omitted because the example only tests URL policy; if a business service uses `@PreAuthorize`, enable method security and write tests at that boundary.

### 7.7. OrdersController.java

~~~java
package com.example.authlab;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrdersController {

    @GetMapping("/me")
    public Map<String, String> currentUser() {
        Authentication authentication =
                SecurityContextHolder.getContext()
                        .getAuthentication();

        return Map.of(
                "principal", authentication.getName(),
                "authenticationType",
                authentication.getClass().getSimpleName());
    }
}
~~~

This controller only exposes test-readable principal/type; it is not a production orders API. In production applications, avoid exposing authentication implementation class names on public APIs, and prefer method parameters/principal abstractions or appropriate security services.

Endpoint:
- MockUser -> `UsernamePasswordAuthenticationToken`.
- Mock `jwt()` and real verified Bearer JWT -> `JwtAuthenticationToken`.
- Both types can still satisfy `hasAuthority` when the authority is supplied. That is precisely what this lesson demonstrates.

### 7.8. TestJwtSupportConfig.java — test-only keypair and validators

`src/test/java/com/example/authlab/TestJwtSupportConfig.java`:

~~~java
package com.example.authlab;

import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;

@TestConfiguration(proxyBeanMethods = false)
public class TestJwtSupportConfig {

    public static final String ISSUER =
            "https://issuer.example.test";
    public static final String AUDIENCE = "orders-api";
    public static final String KEY_ID = "test-key";

    @Bean
    KeyPair testSigningKey() throws GeneralSecurityException {
        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        return generator.generateKeyPair();
    }

    @Bean
    JwtEncoder testJwtEncoder(KeyPair testSigningKey) {
        RSAKey jwk = new RSAKey.Builder(
                (RSAPublicKey) testSigningKey.getPublic())
                .privateKey(
                        (RSAPrivateKey) testSigningKey.getPrivate())
                .keyID(KEY_ID)
                .build();

        return new NimbusJwtEncoder(
                new ImmutableJWKSet<>(
                        new JWKSet(jwk)));
    }

    @Bean
    JwtDecoder testJwtDecoder(KeyPair testSigningKey) {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
                .withPublicKey(
                        (RSAPublicKey) testSigningKey.getPublic())
                .build();

        OAuth2TokenValidator<Jwt> audienceValidator =
                jwt -> jwt.getAudience() != null
                        && jwt.getAudience().contains(AUDIENCE)
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                            new OAuth2Error(
                                    "invalid_token",
                                    "Token audience is not orders-api",
                                    null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        JwtValidators.createDefaultWithIssuer(
                                ISSUER),
                        audienceValidator));

        return decoder;
    }
}
~~~

**Safety and testing significance:**
- Public/private keys are generated at runtime per Spring test context; no private key is committed in the repo.
- `NimbusJwtEncoder` signs with the **test private key**.
- `NimbusJwtDecoder.withPublicKey(...)` verifies signatures with the **test public key** and defaults to trusting RS256 in this setup.
- The validator combines issuer, default timestamps, and required audience. Tests with wrong `iss`, `aud`, `exp`, or `nbf` must fail.
- This is a **real decoder**, not a Mockito stub, yet it **does not test JWKS over HTTP** because the key is injected directly. JWKS discovery/key rotation requires a separate suite.
- `@TestConfiguration` under `src/test/java` should never ship in production artifacts; it is only activated when tests explicitly `@Import` it.
- For multi-key rotation tests, work with `NimbusJwtDecoder.withJwkSetUri(...)` and a JWKS server stub; never infer a single keypair tested rotation.

### 7.9. MockAuthenticationMvcTest.java — authorization with fake identities

`src/test/java/com/example/authlab/MockAuthenticationMvcTest.java`:

~~~java
package com.example.authlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrdersController.class)
@Import(ApiSecurityConfig.class)
class MockAuthenticationMvcTest {

    @Autowired
    MockMvc mvc;

    // Bean needed to configure the Resource Server filter chain
    // in the MVC slice; this test does NOT verify signatures.
    @MockitoBean
    JwtDecoder decoder;

    @Test
    @WithMockUser(
            username = "alice",
            authorities = "SCOPE_orders:read")
    void mockUserPassesAuthorizationWithoutAnyJwt()
            throws Exception {

        mvc.perform(get("/api/orders/me"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.principal")
                        .value("alice"))
                .andExpect(jsonPath("$.authenticationType")
                        .value(
                                "UsernamePasswordAuthenticationToken"));
    }

    @Test
    void jwtPostProcessorPassesWithoutSignedBearerToken()
            throws Exception {

        mvc.perform(get("/api/orders/me")
                .with(jwt()
                        .jwt(jwt -> jwt
                                .claim("sub", "alice")
                                .claim("iss",
                                        "https://untrusted.example.test"))
                        .authorities(
                                new SimpleGrantedAuthority(
                                        "SCOPE_orders:read"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.principal")
                        .value("alice"))
                .andExpect(jsonPath("$.authenticationType")
                        .value("JwtAuthenticationToken"));
    }

    @Test
    void mockJwtMissingRequiredAuthorityGetsForbidden()
            throws Exception {

        mvc.perform(get("/api/orders/me")
                .with(jwt()
                        .jwt(jwt -> jwt.claim("sub", "alice"))
                        .authorities(
                                new SimpleGrantedAuthority(
                                        "SCOPE_orders:write"))))
                .andExpect(status().isForbidden());
    }
}
~~~

**Interpreting results properly:**
- Test 1 uses `@WithMockUser`; no Bearer token exists yet policy permits it.
- Test 2 uses `jwt()`, assigning an **untrusted** `iss` alongside the test-set read authority. It can still PASS because the helper constructs `JwtAuthenticationToken` without invoking a real decoder. This clearly illustrates the helper's **boundary**, not a production bug when the HTTP Bearer filter is active.
- Test 3 verifies negative authorization: mocked authenticated principal missing scope -> 403.
- `@MockitoBean JwtDecoder` is strictly a collaborator so the MVC slice can build the filter chain. Requests using `jwt()`/`@WithMockUser` never prove `decoder.decode(...)` verifies signatures.
- Replacing `@WebMvcTest` with `MockMvcBuilders.standaloneSetup(...)` without applying Spring Security bypasses filters and policies altogether; never treat that as a security integration test.

### 7.10. SignedJwtResourceServerTest.java — RSA-signed JWT through real decoder

`src/test/java/com/example/authlab/SignedJwtResourceServerTest.java`:

~~~java
package com.example.authlab;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Import(TestJwtSupportConfig.class)
class SignedJwtResourceServerTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    JwtEncoder encoder;

    @Autowired
    JwtDecoder decoder;

    @Test
    void authenticSignedTokenCanReadOrders()
            throws Exception {
        String bearer = sign(claims(
                TestJwtSupportConfig.ISSUER,
                TestJwtSupportConfig.AUDIENCE,
                "orders:read",
                Instant.now().minusSeconds(30),
                Instant.now().plusSeconds(300)));

        mvc.perform(get("/api/orders/me")
                .header(HttpHeaders.AUTHORIZATION,
                        "Bearer " + bearer))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.principal")
                        .value("alice"))
                .andExpect(jsonPath("$.authenticationType")
                        .value("JwtAuthenticationToken"));
    }

    @Test
    void missingBearerCredentialIsUnauthorized()
            throws Exception {
        mvc.perform(get("/api/orders/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void malformedBearerTokenIsUnauthorized()
            throws Exception {
        mvc.perform(get("/api/orders/me")
                .header(HttpHeaders.AUTHORIZATION,
                        "Bearer not-a-jwt"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void sameClaimsSignedByWrongPrivateKeyAreRejected()
            throws Exception {

        JwtClaimsSet identicalClaims = claims(
                TestJwtSupportConfig.ISSUER,
                TestJwtSupportConfig.AUDIENCE,
                "orders:read",
                Instant.now().minusSeconds(30),
                Instant.now().plusSeconds(300));

        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair attackerKey = generator.generateKeyPair();

        RSAKey attackerJwk = new RSAKey.Builder(
                (RSAPublicKey) attackerKey.getPublic())
                .privateKey(
                        (RSAPrivateKey) attackerKey.getPrivate())
                // Intentionally same key ID: kid does not make a key trusted.
                .keyID(TestJwtSupportConfig.KEY_ID)
                .build();

        JwtEncoder attackerEncoder = new NimbusJwtEncoder(
                new ImmutableJWKSet<>(
                        new JWKSet(attackerJwk)));

        String forged = encode(
                attackerEncoder, identicalClaims);

        // Real decoder path verifies signature, not just claims.
        assertThatThrownBy(() -> decoder.decode(forged))
                .isInstanceOf(JwtException.class);

        mvc.perform(get("/api/orders/me")
                .header(HttpHeaders.AUTHORIZATION,
                        "Bearer " + forged))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongIssuerIsUnauthorizedEvenWhenSignatureIsValid()
            throws Exception {
        String token = sign(claims(
                "https://other-issuer.example.test",
                TestJwtSupportConfig.AUDIENCE,
                "orders:read",
                Instant.now().minusSeconds(30),
                Instant.now().plusSeconds(300)));

        mvc.perform(get("/api/orders/me")
                .header(HttpHeaders.AUTHORIZATION,
                        "Bearer " + token))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongAudienceIsUnauthorized()
            throws Exception {
        String token = sign(claims(
                TestJwtSupportConfig.ISSUER,
                "different-resource-api",
                "orders:read",
                Instant.now().minusSeconds(30),
                Instant.now().plusSeconds(300)));

        mvc.perform(get("/api/orders/me")
                .header(HttpHeaders.AUTHORIZATION,
                        "Bearer " + token))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void expiredSignedJwtIsUnauthorized()
            throws Exception {
        String token = sign(claims(
                TestJwtSupportConfig.ISSUER,
                TestJwtSupportConfig.AUDIENCE,
                "orders:read",
                Instant.now().minusSeconds(600),
                Instant.now().minusSeconds(180)));

        mvc.perform(get("/api/orders/me")
                .header(HttpHeaders.AUTHORIZATION,
                        "Bearer " + token))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void jwtNotYetValidIsUnauthorized()
            throws Exception {
        String token = sign(claims(
                TestJwtSupportConfig.ISSUER,
                TestJwtSupportConfig.AUDIENCE,
                "orders:read",
                Instant.now().plusSeconds(300),
                Instant.now().plusSeconds(900)));

        mvc.perform(get("/api/orders/me")
                .header(HttpHeaders.AUTHORIZATION,
                        "Bearer " + token))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void validJwtWithInsufficientScopeIsForbidden()
            throws Exception {
        String token = sign(claims(
                TestJwtSupportConfig.ISSUER,
                TestJwtSupportConfig.AUDIENCE,
                "orders:write",
                Instant.now().minusSeconds(30),
                Instant.now().plusSeconds(300)));

        mvc.perform(get("/api/orders/me")
                .header(HttpHeaders.AUTHORIZATION,
                        "Bearer " + token))
                .andExpect(status().isForbidden());
    }

    private String sign(JwtClaimsSet claims) {
        return encode(encoder, claims);
    }

    private static String encode(
            JwtEncoder signer, JwtClaimsSet claims) {
        JwsHeader header = JwsHeader
                .with(SignatureAlgorithm.RS256)
                .keyId(TestJwtSupportConfig.KEY_ID)
                .build();

        return signer.encode(
                JwtEncoderParameters.from(header, claims))
                .getTokenValue();
    }

    private static JwtClaimsSet claims(
            String issuer,
            String audience,
            String scope,
            Instant notBefore,
            Instant expiresAt) {

        return JwtClaimsSet.builder()
                .issuer(issuer)
                .subject("alice")
                .audience(List.of(audience))
                .issuedAt(Instant.now().minusSeconds(900))
                .notBefore(notBefore)
                .expiresAt(expiresAt)
                .id(UUID.randomUUID().toString())
                .claim("scope", scope)
                .build();
    }
}
~~~

### 7.11. Analysis of each test

**Valid token test:** `JwtEncoder` builds an RSA-signed compact JWS, and the test passes it in a real header. `BearerTokenAuthenticationFilter` extracts the token; `JwtDecoder` verifies signature and issuer/audience/timestamps; `JwtAuthenticationConverter` produces `SCOPE_orders:read`; policy returns 200. This is genuine JWT authentication verification inside the app, even without network calls to an IdP.

**No token test:** No `Authorization` header on a protected endpoint -> 401; unlike `MockUser`, the test does not pre-populate an authenticated principal.

**Malformed token test:** Header carries a Bearer value that is not a compact JWT -> decoder rejects with 401.

**Wrong private key test:** The token has identical claims to the valid token, `alg=RS256`, and the **same `kid`**, yet the signing private key does not match the server's trusted public key. The real decoder throws `JwtException`; HTTP returns 401. This is the single most important negative signature test.

**Wrong issuer test:** Signature is valid, yet `iss` differs from expected -> 401. This proves a valid signature alone is insufficient when issuer trust mismatches.

**Wrong audience test:** Signature and issuer match, yet `aud` lacks `orders-api` -> custom audience validator rejects with 401. Removing the validator or Boot `audiences` property causes this test to catch the configuration bug.

**Expired test:** `exp` is 180 seconds in the past, well past typical clock skew tolerance to avoid ± few-second boundary flakiness.

**Not-yet-valid test:** `nbf` is 300 seconds in the future, exceeding clock skew. Even a properly signed token is rejected.

**Insufficient scope test:** Signature/`iss`/`aud`/time are valid, yet only `orders:write` scope is present -> authenticated but lacking `SCOPE_orders:read` -> 403 (distinct from 401).

### 7.12. Why not test expiry with a token expired 1 second ago?

`JwtTimestampValidator` applies clock skew tolerance to absorb clock drift between systems. A token expired 1 second ago may still be considered valid under policy and cause flaky failures. In this lab, negative samples stay several minutes away from now. When exact boundary testing is needed, configure an explicit `Clock`/`JwtTimestampValidator` and skew instead of relying on wall-clock races.

### 7.13. Running Maven

From `auth-mock-vs-real-lab`, with JDK 17+ and Maven:

~~~bash
mvn -q clean test

mvn -q -Dtest=MockAuthenticationMvcTest test
mvn -q -Dtest=SignedJwtResourceServerTest test
~~~

Expected design outcomes:
- Mock suite: 3 tests PASS, including one where an untrusted issuer is allowed due to the **pre-built authority**.
- Real signed-token suite: 9 tests PASS, covering valid 200; missing/invalid/wrong-signature/wrong-issuer/wrong-audience/expired/future-nbf -> 401; insufficient scope -> 403.
- Total 12 test methods.
- Maven exit code `0` on success; reports located in `target/surefire-reports`.

**Practical QA note:** Java files and Maven declarations in this lesson were reviewed for structure/API accuracy, with **no claim that Maven/JUnit was executed** during authoring. The results above are expected behaviors to be confirmed in your project/CI.

### 7.14. Do not run the bare application with test keys

`TestJwtSupportConfig` lives in `src/test/java` and is only imported in tests. That is a safe boundary. Never copy test RSA private keys into `application.properties`, `src/main/resources`, or production sources.

To run the app standalone, configure the resource server against an approved production or test-authority issuer, such as `issuer-uri` and `audiences` in Section 5.2; never hardcode a private key in `main` just to avoid context startup errors.

## 8. Proving “mock does not prove signature” with a direct contrast

Two distinct requests:

### 8.1. Request A: building an Authentication

~~~java
mvc.perform(get("/api/orders/me")
        .with(jwt()
                .jwt(jwt -> jwt
                        .claim("sub", "alice")
                        .claim("iss",
                                "https://attacker.example.test"))
                .authorities(
                        new SimpleGrantedAuthority(
                                "SCOPE_orders:read"))))
        .andExpect(status().isOk());
~~~

In a security MockMvc test with the filter chain enabled, this request injects a `JwtAuthenticationToken` into context. No signed compact JWS or Bearer header exists. The fake issuer does not fail the test because the decoder validator **never runs**.

### 8.2. Request B: supplying a real Bearer token

~~~java
mvc.perform(get("/api/orders/me")
        .header(HttpHeaders.AUTHORIZATION,
                "Bearer " + signedJwt))
        .andExpect(status().isOk());
~~~

With a real `JwtDecoder`, Request B passes through filter/provider/verification. If `signedJwt` has a bad signature, different issuer, wrong audience, expired `exp`, or future `nbf`, the response is 401 instead of 200.

**Never write Test A and name it `validatesJwtSignature()`.** A proper name is `allowsScopeReadForMockJwtPrincipal()`. Test B named `rejectsTokenSignedByUntrustedKey()` accurately reflects what ran.

## 9. 401 vs 403 and reasoning about errors

### 9.1. Invalid tokens must never become an authenticated principal

When signature/issuer/audience/expiry is invalid, the resource server must **never build a trusted `JwtAuthenticationToken`** for the request. Returning 401 is the standard contract.

If custom code Base64URL-decodes the payload and sets `Authentication` without verifying the signature, callers can pick arbitrary scopes/roles. Never parse JWTs with `split("\\.")` + Base64 decode and trust `sub` or `role`. Only Base64-decode untrusted tokens for non-sensitive diagnostics, never for authentication.

### 9.2. Valid token yet insufficient permissions

A valid Bearer token might contain only `scope=orders:write`. Signature verification succeeding is **authentication**, yet the `hasAuthority("SCOPE_orders:read")` policy still denies -> 403.

If all negative tests only assert “not 200”, you can miss bugs between invalid credentials vs insufficient authorization. Assert exact 401/403 statuses and the matching error contract.

### 9.3. WWW-Authenticate

OAuth2 Bearer Resource Servers typically return a `WWW-Authenticate` header on 401, potentially including error codes like `invalid_token`. Header details can vary across Spring Security versions and policies; tests should assert fields mandated by the API contract without hardcoding implementation-detail messages unless strictly required.

### 9.4. Method security and URL security

`@PreAuthorize("hasAuthority('SCOPE_orders:read')")` is a method-level rule; it needs `@EnableMethodSecurity` and calls passing through a Spring-managed proxy. `@WithMockUser` helps test these policies yet still skips JWT signature checks. To test token validity and method-level rules together, write signed Bearer token integration tests invoking the service through its Spring proxy.

## 10. Comparing signature, issuer, audience, expiry, and nbf

### 10.1. Signature

Testing “same claims, different private key” isolates signature verification better than a random broken JWT string, because malformed strings can fail during parsing before reaching cryptographic verification.

In the lab, the forged private key even reuses `kid=test-key`. If signatures were accepted based on `kid` alone, the test would catch it. `kid` is a key selector, not proof of trust.

### 10.2. Issuer

When issuer configuration is fixed, a signed token with a different `iss` must be rejected. This protects against scenarios where multiple authorization servers use different keys or algorithms. A resource server must bind to an explicit trust configuration per tenant/issuer; never trust an issuer merely because the token mentions a JWKS endpoint.

### 10.3. Audience

An access token issued for API A must not work against API B merely because the issuer and signature match. Validate `aud` against your resource server identifier. Missing audience validation is a significant policy gap worth testing. The sample validator uses `OAuth2TokenValidatorResult` alongside issuer/timestamp validators.

### 10.4. exp and nbf

Timestamp validation must verify:
- Expired tokens -> invalid.
- Tokens before `nbf` -> invalid.
- Missing/invalid required timestamps -> per resource policy.
- Clock skew tolerance -> explicit policy and matching tests.

Do not confuse JWT `exp` with server-side session expiration. Self-contained JWTs remain cryptographically valid even after user logout unless a revocation/session-binding strategy exists.

### 10.5. Scopes and authorities

Spring Security maps `scope`/`scp` to `SCOPE_...` by default. Real projects may configure a custom `JwtGrantedAuthoritiesConverter` reading `roles` or `permissions`. Tests must confirm:
- Claims used as authorities come from a **validated JWT**.
- Scopes obey least-privilege semantics.
- User-controlled headers/query parameters cannot override authorities.
- `roles=["ADMIN"]` in an untrusted payload is never treated as an authorized admin.

## 11. JWKS, key rotation, and algorithm trust

### 11.1. What is JWKS?

JWKS (JSON Web Key Set) is the set of public keys published by an issuer for resource servers to verify signatures. A JWT header may include `kid` to select the matching key. When the issuer rotates keys, JWKS updates and decoders/caches must refresh per policy.

The sample lab injects a public key directly **without calling an HTTP JWKS endpoint**. It tests cryptographic verification with that key, not caching, rotation, or networking.

### 11.2. What JWKS integration tests should cover

1. Issuer metadata endpoint returns the expected `jwks_uri`.
2. JWKS contains Key A with `kid=k1`.
3. Token signed with private Key A succeeds.
4. Token signed with private Key B while JWKS only has A -> rejected.
5. JWKS updates to include public Key B; decoder refreshes cache per allowed policy -> Token B succeeds.
6. Token A after issuer retires Key A -> rejected once cache refreshes and policy dictates.
7. JWKS server timeout/500 -> verify error handling, never silently trust tokens.
8. JWKS `alg`/key type mismatch -> rejected.
9. Issuer/audience are still validated after signature passes.
10. Logs never contain Bearer tokens or private keys.

This layer requires a local HTTP stub (WireMock/MockWebServer) or a test IdP. Never hit production endpoints from unit suites.

### 11.3. Algorithms must be trusted via configuration

A Resource Server must never switch algorithms just because an attacker put a different `alg` in the JWT header. With `NimbusJwtDecoder.withPublicKey`, the lab uses an RSA public key and RS256; production can allowlist RS256/RS512/ES256... per issuer contract.

Never widen the algorithm allowlist to fix a failing test without reviewing key types and trust boundaries. A mismatch revealed by an invalid-token test signals a config fix, not turning verification off.

### 11.4. Never fetch JWKS URLs from an unverified token

Header fields like `jku` or `x5u` can carry caller-controlled URLs. Automatically fetching URLs from untrusted tokens invites SSRF or trust confusion. JWKS URIs must be bound to approved issuer/trust configs using HTTPS and proper network controls. Never let a JWT header pick the trusted signer.

### 11.5. “Key rotation” and “token revocation” are two separate things

Rotating keys does not automatically revoke existing JWTs immediately; issuers often retain old public keys until outstanding tokens expire. Token revocation (logout, disabled accounts, incidents) requires a dedicated strategy: short TTLs, revocation stores/introspection, session versions, or event-driven policies. Mock JWT tests prove no revocation mechanism whatsoever.

## 12. Full OAuth2/OIDC flow vs JWT Resource Server

### 12.1. Authorization Code + PKCE

A Browser/OAuth2 Login test must verify:
- Client generates random `state`; callback matches `state` to stop login CSRF.
- PKCE `code_verifier` stays private; `code_challenge` is sent upfront.
- Authorization code is single-use, bound to client/`redirect_uri`/verifier.
- Browser redirect/cookie/session security is enforced.
- Token endpoint issues tokens for the authorized account/client only.
- Resource Server consumes the access token with proper audience/scope.
- Users cannot bypass login/MFA by hitting a forged callback.

Putting `@WithMockUser` on a method checks none of these steps.

### 12.2. OIDC ID tokens are not access tokens

An OIDC ID token proves identity to the **client** and carries checks like issuer, client-ID audience, and flow nonce. An access token authorizes resource-server calls. A validly signed ID token **must not automatically call APIs**; resource servers must validate the intended token type/audience and policy.

### 12.3. Opaque tokens

Opaque tokens contain no JWT payload for a resource server to verify locally. They typically require an introspection endpoint or token store/trust mechanism. In Spring Security, the `opaqueToken()` test postprocessor simulates a principal without calling introspection. Integration tests use a real `OpaqueTokenIntrospector` or test identity server stub, testing active/inactive/expired/insufficient-scope paths.

### 12.4. Username/password with AuthenticationManager

If an application uses form login:
- `@WithMockUser` tests bypass `UsernamePasswordAuthenticationFilter`, `AuthenticationManager`, `DaoAuthenticationProvider`, and `PasswordEncoder`.
- Unit testing `PasswordEncoder.matches` checks only one component.
- Integration tests posting to `/login` with real credentials in a test DB must check handlers, failure responses, sessions/cookies/CSRF, session fixation protection, and lockouts/rate limits where part of the contract.
- Full E2E also requires browser flows, redirects, MFA, and external IdPs where used.

Never relabel a URL-policy test as “authentication tested” merely because it uses a mock user annotation.

### 12.5. MFA and step-up authentication

Even a real token might not prove MFA took place. When business policy mandates MFA/step-up, check `amr`/`acr` claims under issuer trust, freshness (`auth_time`), and policy, while also testing that the IdP enforces MFA. Never treat a manually set `amr` claim inside `jwt()` as proof the user completed MFA.

## 13. Notes on test configuration and Spring filter chain

### 13.1. Never disable filters and call it a security test

~~~java
@AutoConfigureMockMvc(addFilters = false)
~~~

This strips the filter chain from MockMvc, letting requests reach controllers without passing through Spring Security. It helps pure business controller tests, yet **is unsuitable** for proving JWT verification, CSRF, security headers, or authorization filters.

In the signed-token lab, `@AutoConfigureMockMvc` keeps default filters enabled; Bearer requests travel through the full authentication pipeline.

### 13.2. Never mock the component you want to test

If the goal is verifying signatures, do not `@MockitoBean JwtDecoder`. If the goal is authorization policy, mocking the decoder or using `jwt()` can make sense. Test designs must state *which boundary is real*.

### 13.3. @WebMvcTest does not auto-load all business @Services

`@WebMvcTest` is an MVC slice; it may omit custom services/decoders/configs outside its scope. Use `@Import(ApiSecurityConfig.class)` and `@MockitoBean JwtDecoder` when testing policy slices. If the controller depends on another business service, mock that collaborator. To verify JWT signatures with real beans, use full context or import full test config and the real decoder.

### 13.4. @SpringBootTest does not guarantee real authentication

`@SpringBootTest` boots the full context, yet if a test still calls `with(jwt())` or `@WithMockUser`, it **still skips signature verification**. The full-context annotation does not change how a request is built. Draw conclusions from the actual execution path, not the annotation name.

### 13.5. SecurityContext in unit tests

Pure unit tests may set `SecurityContextHolder.getContext().setAuthentication(...)` and clear it in `finally`/`@AfterEach` to avoid `ThreadLocal` leaks. That is a fixture, not end-to-end authentication. Spring Security Test helpers are generally safer inside Spring `TestContext`.

### 13.6. Testing method-security proxies

If `@PreAuthorize` sits on a service:
- The Spring bean must be wrapped by an appropriate AOP proxy.
- Self-invocation can bypass the method interceptor.
- `@EnableMethodSecurity` must be active.
- `@WithMockUser` can test the policy at the proxy.
- Signed JWT integration tests can verify token authorities -> method policy when invoked through the proxy.

## 14. Security bugs that mock tests can miss

### 14.1. Disabled JWT signature verification

An app might Base64-decode the payload directly and trust `scope=admin`. A `jwt().authorities("admin")` test still PASSES because policy checks the assigned authority. Only real signed Bearer token tests with forged/tampered tokens verify the verifier.

### 14.2. Missing audience validation

A validly signed JWT from the right issuer intended for another resource can be accepted if the app omits an `aud` validator. `@WithMockUser` and `jwt()` miss this because they skip the decoder. Negative audience tests with real signed tokens are critical.

### 14.3. Wrong issuer

A token from another authorization server may have matching claim names. Resource Servers must trust only the **expected issuer**, never accepting a token merely because it has `sub` and `scope`.

### 14.4. Accepting expired or not-yet-valid tokens

If the decoder validator is overridden incorrectly, `exp`/`nbf` enforcement may vanish. Mock principals cannot detect this. Test timestamps beyond skew and assert 401.

### 14.5. Broken scope converter mapping

An issuer might emit `scope=orders:read` while a custom converter mistakenly grants `ROLE_ADMIN` or drops `SCOPE_`. Hard-coding `jwt().authorities(...)` bypasses the converter, so real signed token tests with **real `scope` claims** catch mapping errors.

### 14.6. Missing security filter on an endpoint

If an endpoint matcher is wrong or a filter chain skips a path, fake security context tests can stay green or fail to catch the gap. Test unauthenticated requests return 401. With multiple `SecurityFilterChain`/`securityMatcher` beans, test each URL group, HTTP method, and dispatcher type.

### 14.7. ID token accepted in place of access token

Failing to check `aud`/token type lets a signed ID token pass as an access token. Add negative tests using client-ID audiences and non-access token types where required by contract.

### 14.8. Broken JWKS cache/key rotation

A JWT signed with a single local test key passes, yet production decoders fail to reload public keys after rotation. Integration tests with a JWKS server and rotating keys are needed rather than a static single-key fixture.

### 14.9. Authentication succeeds yet tenant/ownership is wrong

A valid token only supplies identity; it does not grant access to every order. Enforce per-resource business authorization: `ownerId==principalId`, tenant binding, data scoping, and object-level checks. A signed JWT returning 200 on a simple endpoint does not prove IDOR/BOLA protection.

### 14.10. Passwords/MFA/sessions untested

When a system uses browser/IdP logins, fake authenticated users bypass credentials, MFA, and redirects. Run E2E login tests in an isolated sandbox/tenant. Never expose real employee credentials in CI logs.

## 15. Testing JWT tampering and signatures: detailed guidelines

### 15.1. Designing unambiguous negative samples

Include at least three groups:
1. **Malformed**: unparseable as a JWT, e.g., `not-a-jwt`.
2. **Well-formed but untrusted signature**: valid claims and matching `kid`, signed by a different key.
3. **Valid signature, failed claim/business validation**: wrong issuer, audience, timestamp, or scope.

Testing only a malformed string and calling it a “signature test” lets the parser reject **before** RSA verification runs. The lab adds Group 2 specifically to prove real signature verification.

### 15.2. Never equate signature checks with authorization

A token signed by the trusted private key can still lack the required scope. The response should be 403, not 401. This shows authentication succeeded while authorization failed. Test names should reflect that distinction.

### 15.3. Negative algorithm header tests

When the app expects RS256, tests should reject `alg=none` or algorithms outside the allowlist. You may craft unsigned tokens **strictly inside tests** to assert the decoder rejects them; never reuse such tokens as credentials in production. Crafting insecure tokens in negative tests is never a reason to weaken production security.

### 15.4. Tampered payloads

If you take a validly signed JWT and alter `sub`/`scope` in the payload while keeping the original signature, the signature becomes invalid. Tests can assert 401. Ensure the edited payload remains well-formed JSON/base64url so execution genuinely reaches signature verification; the key-forgery group in the lab is even clearer to reason about.

### 15.5. RSA/ECDSA/HMAC trade-offs

The lab uses RSA 2048 for broad compatibility, not as a recommendation to write custom crypto. In real systems, rely on audited libraries, proper key management/KMS/trusted issuers, and algorithms/key lengths compliant with security policy. Never assemble JWTs via string concatenation or roll custom RSA signing unless specifically testing a crypto library.

## 16. Production-like test design without depending on a production IdP

### 16.1. Test-only issuers

Use a dedicated test realm/tenant of an identity provider or a fake JWKS server. Never place production users, tokens, OAuth client secrets, or refresh tokens in source code or test reports. All test identities must be synthetic.

### 16.2. Deterministic time

When tests require millisecond-accurate expiry, inject a `Clock` and fixed validator clock skew. The sample uses multi-minute offsets to avoid flakiness under real wall clocks. Check NTP synchronization across services in CI security integration environments.

### 16.3. Isolated keypair per test context

Generating keypairs at test context startup avoids committing private keys to the repo. When tests run in parallel sharing a context, signer and verifier share the same keypair bean. If separate classes generate independent keys with misconfigured context caching, valid tokens can fail verification against the wrong key; keep config explicit and isolated.

### 16.4. Verify the real HTTP token path

Include requests with:
- `Authorization: Bearer <token>` generated by the test signer.
- Spring Security filters enabled.
- Real decoder bean.
- Negative signature/claim cases.
- Assertions on status and business authorities.

Replacing the header with `with(jwt())` skips the verification path even though the test still uses MockMvc.

### 16.5. JWKS stubs and network tests

To verify key discovery:
- Start WireMock/MockWebServer on a test port.
- Expose metadata `/.well-known/openid-configuration` or the configured JWK Set URI.
- Serve JWKS public keys.
- Point the Resource Server issuer URI and JWKS URI to the local server.
- Send signed tokens to the resource server.
- Verify JWKS requests and behavior on 404/503/timeout/rotation.
- Ensure the local stub and decoder cache lifecycle align.
- Never fake the decoder when the JWKS client is the component under test.

This layer extends the runnable project rather than being part of `TestJwtSupportConfig` in the lab.

## 17. Security details beyond JWT that tests can overlook

### 17.1. CSRF

If an app uses session cookies, CSRF protection matters for state-changing methods. `@WithMockUser` does not prove CSRF tokens are issued and validated properly. In MockMvc, use `csrf()` to test policy behavior, plus browser/session integration for real flows. Stateless Bearer-only APIs have a different threat model; never disable CSRF by rote.

### 17.2. CORS

CORS is browser enforcement over Origins/preflight, unrelated to JWT signatures. Mock principal tests can miss browser Origin handling. Test `OPTIONS` preflight, allowed origins, credential/cookie rules, and reverse proxy headers per contract.

### 17.3. Session fixation and cookie flags

When form/OIDC logins create sessions, test `Secure`, `HttpOnly`, `SameSite`, session ID rotation, logout invalidation, and redirects. Resource-server unit tests using `jwt()` do not touch these components.

### 17.4. Redirects and open-redirect validation

OAuth2 authorization flows involve `redirect_uri`/state and must defend against callback injection/open redirects. Mocked `Authentication` bypasses this completely. Use browser/test-IdP integration or protocol-level tests with negative inputs.

### 17.5. MFA step-up and token freshness

When sensitive APIs require MFA, checking `SCOPE_...` alone is insufficient. Validate `amr`/`acr`/`auth_time` claims per issuer trust and policy, while also verifying the issuer enforces MFA in the login flow. An `amr=["mfa"]` claim set manually via `jwt()` is only a test assumption.

### 17.6. Revocation and logout

A JWT remains cryptographically valid until `exp` even after user logout. When business rules require immediate revocation, implement and test a real revocation mechanism (events/denylist/session-token introspection). Never treat 401 for an expired token as proof of logout.

### 17.7. Rate limiting and brute-force mitigation

Mock logins skip real credential verification and cannot prove lockouts or rate limits. Use a test identity provider or authentication-endpoint integration with synthetic users and proper isolation, never sending load traffic to a production IdP.

## 18. Troubleshooting

| Symptom | Common cause | Fix |
| --- | --- | --- |
| `jwt()` test PASSES yet real Bearer gets 401 | Wrong decoder/issuer/audience/signature/time config | Send signed token and inspect validator errors |
| `@WithMockUser` PASSES for nonexistent user | Mock user is a fixture, skips repository | Add authentication integration test |
| `@WebMvcTest` fails to start | Missing `JwtDecoder` or collaborator | Add `@MockitoBean`/`@Import` for slice |
| Valid Bearer yet returns 403 | Scope mapping missing `SCOPE_` or wrong policy | Inspect actual granted authorities |
| JWT signed with right key still gets 401 | Issuer/audience/time mismatch | Check validators and expected claims |
| Attacker key with same `kid` still PASSES | Signature check bypassed/broken trust | Inspect real decoder, algorithm/key selection |
| HTTP no-token returns 200 | Missing endpoint matcher/filter chain | Ensure filters enabled, test no-auth 401 |
| `@AutoConfigureMockMvc(addFilters=false)` PASSES | Security filters stripped | Keep filters enabled in security tests |
| `jwt()` with wrong issuer claim still gets 200 | Mock postprocessor skips validation | Expected for policy mock; add signed test |
| Wrong audience still gets 200 | Audience validator unconfigured | Configure Boot `audiences` or custom validator |
| Token expired 1 second ago still gets 200 | Clock skew tolerance | Move test timestamps clear of boundary or set clock/skew |
| JWT has scope claim yet authorities empty | Converter expects different claim name/schema | Inspect `JwtGrantedAuthoritiesConverter` |
| `@PreAuthorize` does not execute | Method security disabled or self-invocation | Enable `@EnableMethodSecurity`, use Spring proxy |
| Token issuer metadata/JWKS unreachable | Wrong network/HTTPS/metadata URL | Local JWKS stub/logs/timeout/truststore |
| New token after key rotation gets 401 | Cache/JWKS not refreshed/key missing | Test key rotation integration |
| ID token calls API and gets 200 | Missing audience/type policy | Validate intended token use |
| JWT still usable after logout | Stateless token not revoked | Design revocation/short TTL |
| Mock principal type differs from expected | `@WithMockUser` vs `jwt()` use different auth classes | Assert `Authentication` type and boundary |
| Tests pass yet production login fails | Only downstream policy was tested | Add full-flow IdP/browser tests |
| Bearer token leaked in logs | Debug headers unscrubbed | Redact `Authorization`/cookies/secrets |

Debug in order: **is the test constructing `Authentication` or sending a real Bearer?** Are filters enabled? Is the decoder mocked or real? Which trust keys/allowed algorithms/issuer/audience validators are configured? Did it return 401 or 403? Did it reach the business method? Only after confirming the right boundary should you adjust expectations.

## 19. Exercises

1. Run a `@WithMockUser` test with a nonexistent user and explain why 200 is still valid within that test's scope.
2. Add `jwt().authorities("SCOPE_orders:read")` with an invalid `iss`; observe the policy test PASSES yet does not verify issuer.
3. Supply a properly RSA-signed Bearer token and verify 200 with principal `alice`.
4. Sign identical claims with another RSA private key keeping the same `kid`; verify decoder throws `JwtException` and HTTP returns 401.
5. Sign a valid token with a wrong `iss`; assert 401.
6. Sign a valid token whose `aud` lacks `orders-api`; assert 401.
7. Temporarily remove the audience validator in a controlled branch to watch wrong audience slip through; restore the validator.
8. Create a token whose `exp` passed 3 minutes ago; verify expired 401 and explain clock skew.
9. Create a token with `nbf` 5 minutes in the future; assert 401.
10. Create a valid token with scope `orders:write`; verify 403 rather than 401.
11. Swap in a `JwtGrantedAuthoritiesConverter` reading a `permissions` claim and write a matching real signed-token test.
12. Try `@AutoConfigureMockMvc(addFilters=false)` on a no-token test and explain why security assertions become meaningless.
13. Write a `@WebMvcTest` covering controller routing only, paired with a separate full-context signed-token test.
14. Configure a local JWKS stub with two keys A/B; test key rotation and cache semantics.
15. Configure production-like `issuer-uri` and `audiences` in an integration profile and test metadata/JWKS discovery.
16. Craft a validly signed ID token whose audience is a client ID rather than the API; verify the Resource Server rejects it.
17. Add `@PreAuthorize` on a business service and test method-level policy with mock users.
18. Add a real-JWT test where another user accesses an order they do not own; test object-level authorization.
19. Design a browser OAuth2 Authorization Code + PKCE test with negative `state`/`nonce`/`redirect_uri` cases.
20. Design an MFA/step-up test using a test IdP, distinguishing a mocked `amr` claim from real MFA enforcement.
21. Design a logout/revocation test for an unexpired JWT, distinguishing token validity from session state.
22. Add security logging checks ensuring `Authorization` headers/secrets never appear in test reports.
23. Simulate an unavailable JWKS endpoint and evaluate fail-closed/error policy.
24. Assert 401 vs 403 alongside the matching error response contract and `WWW-Authenticate` header.
25. Build a “which test proves what” mapping table as a QA checklist for the authentication module.

## 20. Authentication test review checklist

- [ ] Is the goal authentication, token validation, or authorization?
- [ ] Does the test name reflect the boundary actually tested?
- [ ] Is `@WithMockUser` interpreted strictly as a mocked principal?
- [ ] Is `jwt()` interpreted strictly as a mocked `JwtAuthenticationToken`?
- [ ] Is `@MockitoBean JwtDecoder` not mistaken for cryptographic verification?
- [ ] Are there tests sending real HTTP `Authorization: Bearer` tokens?
- [ ] Is the Spring Security filter chain enabled in the test?
- [ ] Is `addFilters=false` avoided in JWT/security tests?
- [ ] Is the decoder a real implementation when testing signatures?
- [ ] Are valid RSA signatures and untrusted private keys both tested?
- [ ] Are wrong issuers rejected?
- [ ] Are wrong audiences rejected?
- [ ] Are expired and future-`nbf` tokens rejected accounting for clock skew?
- [ ] Does missing scope return 403 when credentials are valid?
- [ ] Do missing/malformed/invalid-signature tokens return 401?
- [ ] Are authority converters tested using claims from validated tokens?
- [ ] Does the algorithm allowlist refuse trusting arbitrary token headers?
- [ ] Does the decoder never fetch untrusted JWKS URLs from tokens?
- [ ] Do test keys live strictly under `src/test` without production secrets?
- [ ] Do JWKS discovery/key rotation have dedicated tests where the system relies on them?
- [ ] Does full OAuth2/OIDC login/PKCE have dedicated tests when required by business flows?
- [ ] Are OIDC ID tokens and API access tokens kept strictly separate?
- [ ] Are MFA, session, logout, revocation, CSRF, and CORS tested at their proper boundaries?
- [ ] Is object/tenant-level authorization tested beyond token scopes?
- [ ] Are Bearer tokens, private keys, cookies, and PII kept out of logs?
- [ ] Do test timestamps/clock skew and key caches avoid flaky suites?
- [ ] Do Maven/JUnit and CI reports confirm tests actually executed?

**Conclusion:** A mocked `Authentication` helps verify permissions, yet never tells you whether the caller passed login or whether a JWT signature was verified. `@WithMockUser` and MockMvc `jwt()` intentionally bypass credential checks so policy tests stay fast. When you need to prove a Resource Server accepts valid JWTs and rejects forged ones, send **real Bearer JWS tokens signed with a test key**, keep the real filter chain/decoder, and test signatures, issuer, audience, timestamps, and scopes. When you need to prove **the entire authentication flow** — PKCE, redirects, IdP credentials, MFA, sessions — write integration/E2E tests at the matching authorization server/browser boundary. Never stretch conclusions beyond the steps your test actually executed.

## 21. Official documentation

- Spring Security 6.5 — Testing OAuth 2.0 (MockMvc jwt()/oauth2Login()/oidcLogin()): https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/oauth2.html
- Spring Security 6.5 — @WithMockUser and Method Security Testing: https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html
- Spring Security 6.5 — SecurityMockMvcRequestPostProcessors.jwt() Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/test/web/servlet/request/SecurityMockMvcRequestPostProcessors.html
- Spring Security 6.5 — OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html
- Spring Security 6.5 — OAuth2 Resource Server Bearer Token: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/bearer-tokens.html
- Spring Security 6.5 — OAuth2 Login: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/index.html
- Spring Security 6.5 — Authorization and Method Security: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 — NimbusJwtDecoder Javadoc: https://docs.spring.io/spring-security/site/docs/6.5.0/api/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html
- Spring Security 6.5 — NimbusJwtEncoder Javadoc: https://docs.spring.io/spring-security/site/docs/6.5.0/api/org/springframework/security/oauth2/jwt/NimbusJwtEncoder.html
- Spring Boot 3.5 — OAuth2 Resource Server auto-configuration: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Framework 6.2 — MockitoBean test overriding: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html
- RFC 7519 — JSON Web Token (JWT): https://www.rfc-editor.org/rfc/rfc7519
- RFC 7515 — JSON Web Signature (JWS): https://www.rfc-editor.org/rfc/rfc7515
- RFC 7517 — JSON Web Key (JWK): https://www.rfc-editor.org/rfc/rfc7517
- RFC 8725 — JSON Web Token Best Current Practices: https://www.rfc-editor.org/rfc/rfc8725
- RFC 7636 — PKCE: https://www.rfc-editor.org/rfc/rfc7636
- OpenID Connect Core 1.0: https://openid.net/specs/openid-connect-core-1_0.html

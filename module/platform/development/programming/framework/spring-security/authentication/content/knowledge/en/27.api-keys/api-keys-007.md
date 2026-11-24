# Preventing API Keys from Becoming a Bypass Around Stronger Authentication

## 1. Problem and goal

A Spring Security application may already protect critical APIs using OAuth2 JWT, OIDC, MFA, or re-authentication before sensitive operations. To support a background job or partner system, the engineering team adds API keys. Without clear boundaries, a valid API key can become an **alternative authentication path** that bypasses the stronger original policy.

Typical failure scenario: endpoint `POST /api/payments/approve` should only accept an access token from an MFA-authenticated user with approval rights. A new filter inspects `X-API-Key`, sees a valid key, assigns `ROLE_ADMIN`, and lets it access all URLs. Anyone holding the key needs no JWT, MFA, or active user account. This is an **authentication downgrade / bypass**.

This lesson belongs to the **API keys** section of the Spring Security Authentication module. Afterward, you will know how to define which APIs may use keys, separate filter chains, restrict machine principals, prevent credential fallback, enforce JWT/MFA on sensitive endpoints, build negative tests, and manage key lifecycles.

**Principle:** the resource dictates the required authentication evidence. Any single verified credential does not automatically satisfy a resource's stronger requirements.

## 2. What does an API key prove?

A sufficiently strong random API key can identify a registered **client application** or partner, such as `partner-reports-reader`. It does not by itself prove which employee logged in, whether MFA occurred, whether the user is authorized to approve transactions, which tenant is owned, or whether a user session remains active.

| Credential | Typical subject | What must be checked |
| --- | --- | --- |
| API key | Machine/service/partner | Valid secret, active client, scopes, tenant, expiry/revocation |
| OAuth2 access token | User or service principal per grant | Signature/introspection, issuer, audience, lifetime, scopes |
| OIDC ID token | User authenticated at relying party | Used at the client for login; does not replace API access tokens |
| Web session | User session in the application | Session, CSRF when applicable, user status, authentication time |
| mTLS | Workload possessing a private key | CA, client certificate, trust domain, key rotation |
| MFA/step-up | User who completed strong authentication | Proof from trusted IdP/AS, assurance level, and recency |

There is no absolute strength ranking for every scenario: a high-entropy key + mTLS can be valid for a narrow service. Yet if an operation **requires a human user to complete MFA**, a key alone is insufficient user evidence. A dedicated delegated machine workflow or a verified multi-credential policy is needed rather than impersonating a user.

## 3. Threat model: how do keys become a bypass?

Bypass paths typically emerge when:

1. **Filter runs too broadly:** the API key filter is registered globally and grants authentication even on admin endpoints.
2. **Unconstrained OR logic:** `jwtValid || apiKeyValid`, while the resource requires JWT and MFA.
3. **Fallback from strong to weak on failure:** invalid issuer / expired JWT / missing MFA falls back to trying an API key; if the key matches, the request succeeds.
4. **Identical authorities:** a job key is granted `ROLE_ADMIN` or `SCOPE_admin.write` equivalent to an MFA-verified user.
5. **Confused principal:** code treats a machine identity as an employee, using `getName()` as a user ID without checking token type.
6. **Unmatched routes:** certain URLs fall outside every `SecurityFilterChain` and go unprotected by Spring Security.
7. **Trusting forged headers:** clients send `X-Authenticated-User`, `X-MFA: true`, `X-Role: ADMIN`, and the backend trusts them as authentication results.
8. **Copied/leaked keys:** long-lived keys sit in logs, frontend apps, or repos with overly broad permissions and no revocation.

Do not just block invalid keys. **Test that valid keys are still rejected on high-assurance endpoints.**

## 4. Designing per-route authentication contracts

Define a protection matrix before writing filters:

| Route | Expected principal | Accepted credential | Policy |
| --- | --- | --- | --- |
| `GET /partner/status` | Partner service | Partner API key only | `PARTNER_READ` + quota |
| `GET /api/reports` | OAuth2 subject per AS contract | Bearer access token only | `SCOPE_reports.read` + tenant/ownership check |
| `GET /api/high-assurance` | Step-up user | User bearer JWT only | `SCOPE_admin.write` and trusted MFA assurance |
| `/internal/**` | Internal infrastructure | Not public in example | Deny in app and protect at network |
| Other URLs | Undefined | None | Deny by default |

Separating `/partner/**` and `/api/**` into two namespaces clarifies policy. Never choose mechanisms based on client-controlled headers. Anti-pattern:

```java
// DO NOT implement: client decides which protection level to use
if (request.getHeader("X-API-Key") != null) {
    return useApiKeyForAnyPath(request);
}
return useJwtAndMfa(request);
```

This is **pseudocode** illustrating a flaw; it is not a standalone Java method. The resource path is predetermined by the application, while headers are simply credentials processed **within the selected chain**.

If an endpoint genuinely requires both a machine identity and an MFA-verified user, the rule must be **A AND B**, with two independent verification steps and a policy enforcing both identities. Do not simply register two providers and hope `authenticated()` implies both succeeded.

## 5. Spring Security: securityMatcher vs. requestMatchers

With multiple `SecurityFilterChain` beans, Spring Security Servlet picks the **first matching chain** in `@Order` sequence. `securityMatcher` selects a chain; `requestMatchers` inside `authorizeHttpRequests` are authorization rules **only within that chain**.

Core example:

```text
@Order(1): securityMatcher("/partner/**")
  API key filter + API key provider
  anyRequest().hasAuthority("PARTNER_READ")

@Order(2): securityMatcher("/api/**")
  oauth2ResourceServer().jwt()
  "/api/reports" → SCOPE_reports.read
  "/api/high-assurance" → SCOPE_admin.write AND verified MFA assurance
  other /api/** → denyAll

@Order(3): chain WITHOUT securityMatcher
  anyRequest().denyAll()
```

Key points to remember:

- Adding `anyRequest().denyAll()` only to the `/api/**` chain does **not** protect URLs outside `/api/**`.
- Without a catch-all chain, requests matching no chain can bypass all Spring Security filters.
- Inside `authorizeHttpRequests`, the first matching rule wins. Place specific patterns before `anyRequest()`.
- Never turn a custom API key filter into a Servlet `Filter` running outside `FilterChainProxy`. Once added to a security chain, avoid Spring Boot auto-registering it a second time.
- Test HTTP methods, trailing slashes, percent-encoding, reverse proxy rewrites, context paths, and other servlets; matchers must align with requests after Servlet container processing.

This lab uses Servlet/Spring MVC, Java 17+, Spring Boot 3.x, and Spring Security 6.x. WebFlux has its own `ServerHttpSecurity` and `SecurityWebFilterChain`; do not copy Servlet configurations to reactive apps.

## 6. Generating and storing API keys securely

A machine API key should be generated with a CSPRNG and high entropy. 32 random bytes (256 bits) encoded as unpadded Base64URL yield a 43-character string. Never use emails, guessable passwords, sequential IDs, timestamps, or hardcoded strings committed in source.

**KeyGenerator.java** – standalone Java 17 program:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.HexFormat;

public class KeyGenerator {
    public static void main(String[] args) throws Exception {
        byte[] secret = new byte[32];
        new SecureRandom().nextBytes(secret);

        String key = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(secret);
        byte[] sha = MessageDigest.getInstance("SHA-256")
                .digest(key.getBytes(StandardCharsets.UTF_8));

        System.out.println("Key: " + key);
        System.out.println("SHA256: " + HexFormat.of().formatHex(sha));
    }
}
```

Run:

```bash
javac KeyGenerator.java
java KeyGenerator
```

The `Key` line has a different random value each run; the SHA-256 hex is 64 characters long. There is no fixed stdout to copy verbatim. Run the tool in a trusted environment and deliver the secret to the client via a secret manager/secure channel; never put either line into CI logs, tickets, or repos.

For genuinely high-entropy keys, storing a SHA-256 digest instead of plaintext can be reasonable; this is **not** how user passwords are hashed. User passwords require slow password hashing like Argon2/bcrypt under a dedicated policy. In multi-key systems, add a public key ID, scopes, client, tenant, expiration date, and revocation status; HMAC/pepper can be used per threat model.

**Never grant user authorities to a key.** The system may name a machine authority like `PARTNER_READ`, scoped strictly to a specific API group. Every key must support rotation/revocation and appropriate rate limiting.

## 7. Sample project: Spring Boot 3 + Resource Server JWT + isolated API key

The example defines three chains: `/partner/**` uses keys, `/api/**` uses JWT and step-up endpoints, and everything else is denied. Code is split into Java 17 files under package `com.example.boundary`.

### 7.1. Gradle dependencies and configuration

In a Spring Boot project with plugin/dependency management, add:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Create `src/main/resources/application.yml`:

```yaml
security:
  partner:
    api-key-sha256: ${PARTNER_API_KEY_SHA256}
  jwt:
    issuer: ${JWT_ISSUER}
    jwk-set-uri: ${JWT_JWK_SET_URI}
    audience: ${JWT_AUDIENCE}
```

These are custom properties for the example. The digest comes from the key issuance process; issuer/JWKS/audience come from a trusted AS. The JWT in this example must be an **API access token**, not an OIDC ID token. Never take the JWKS URL from a client-supplied token.

### 7.2. Unauthenticated request token, authenticated result token

**ApiKeyAuthenticationToken.java**

```java
package com.example.boundary;

import java.util.Collection;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;

public final class ApiKeyAuthenticationToken extends AbstractAuthenticationToken {

    private final Object principal;
    private Object credentials;

    public ApiKeyAuthenticationToken(String rawKey) {
        super(null);
        this.principal = null;
        this.credentials = rawKey;
        super.setAuthenticated(false);
    }

    private ApiKeyAuthenticationToken(
            String clientId,
            Collection<? extends GrantedAuthority> authorities) {
        super(authorities);
        this.principal = clientId;
        this.credentials = null;
        super.setAuthenticated(true);
    }

    static ApiKeyAuthenticationToken verified(
            String clientId,
            Collection<? extends GrantedAuthority> authorities) {
        return new ApiKeyAuthenticationToken(clientId, authorities);
    }

    @Override
    public Object getPrincipal() {
        return principal;
    }

    @Override
    public Object getCredentials() {
        return credentials;
    }

    @Override
    public void eraseCredentials() {
        super.eraseCredentials();
        credentials = null;
    }

    @Override
    public void setAuthenticated(boolean value) {
        if (value) {
            throw new IllegalArgumentException(
                    "Only a trusted provider may authenticate");
        }
        super.setAuthenticated(false);
    }
}
```

The filter creates a single-argument token with `isAuthenticated=false`. The provider returns a token marked authenticated **only after** verifying the credential. Never provide a public constructor taking client name + authorities and setting `authenticated=true` from an unverified header.

### 7.3. Provider checking the secret and issuing only machine authority

**PartnerApiKeyProvider.java**

```java
package com.example.boundary;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.List;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public final class PartnerApiKeyProvider implements AuthenticationProvider {

    private final byte[] expectedDigest;

    public PartnerApiKeyProvider(String hex) {
        if (hex == null || !hex.matches("[0-9a-fA-F]{64}")) {
            throw new IllegalArgumentException("Invalid SHA-256 digest");
        }
        this.expectedDigest = HexFormat.of().parseHex(hex);
    }

    @Override
    public Authentication authenticate(Authentication request) {
        if (!(request instanceof ApiKeyAuthenticationToken token)) {
            return null;
        }

        Object value = token.getCredentials();
        if (!(value instanceof String raw)
                || !raw.matches("[A-Za-z0-9_-]{43,128}")) {
            throw new BadCredentialsException("Invalid key");
        }

        byte[] actual;
        try {
            actual = MessageDigest.getInstance("SHA-256")
                    .digest(raw.getBytes(StandardCharsets.UTF_8));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(ex);
        }

        if (!MessageDigest.isEqual(expectedDigest, actual)) {
            throw new BadCredentialsException("Invalid key");
        }

        return ApiKeyAuthenticationToken.verified(
                "partner-report-client",
                List.of(new SimpleGrantedAuthority("PARTNER_READ")));
    }

    @Override
    public boolean supports(Class<?> type) {
        return ApiKeyAuthenticationToken.class.isAssignableFrom(type);
    }
}
```

The example uses a single configured digest to clarify the mechanism. Production should query a key registry by key ID and verify scopes, tenant, client status, and expiration/revocation rather than just the hash. `MessageDigest.isEqual` compares two equal-length digests; high-entropy key generation is required to prevent offline brute force. Never log raw keys.

### 7.4. Filter scoped to the partner chain and forbidding credential mixing

**PartnerApiKeyFilter.java**

```java
package com.example.boundary;

import java.io.IOException;
import java.util.Enumeration;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public final class PartnerApiKeyFilter extends OncePerRequestFilter {

    private final AuthenticationManager manager;

    public PartnerApiKeyFilter(AuthenticationManager manager) {
        this.manager = manager;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        if (request.getHeader("Authorization") != null) {
            response.sendError(HttpServletResponse.SC_BAD_REQUEST);
            return;
        }

        Enumeration<String> values = request.getHeaders("X-Partner-Key");
        if (!values.hasMoreElements()) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        String key = values.nextElement();
        if (values.hasMoreElements() || key == null
                || key.isBlank() || key.indexOf(',') >= 0) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        ApiKeyAuthenticationToken input = new ApiKeyAuthenticationToken(key);
        Authentication result;
        try {
            result = manager.authenticate(input);
        } catch (AuthenticationException rejected) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        } finally {
            input.eraseCredentials();
        }

        if (result == null || !result.isAuthenticated()) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(result);
        SecurityContextHolder.setContext(context);
        try {
            chain.doFilter(request, response);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
```

This filter **must not be created as a global Servlet filter**; SecurityConfig instantiates it inline inside the partner chain. When the key is missing/invalid, it immediately returns 401 without trying weaker/other mechanisms. Within the partner namespace, requests carrying both an API key and an Authorization header are rejected with 400 to avoid ambiguity. Checking duplicate headers and commas is a basic safeguard; gateways must still normalize, strip spoofed headers, and limit sizes. Use TLS and never pass keys in query strings.

### 7.5. Configuring multiple SecurityFilterChains

**SecurityConfig.java**

```java
package com.example.boundary;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.context.NullSecurityContextRepository;

@Configuration
public class SecurityConfig {

    @Bean
    PartnerApiKeyProvider provider(
            @Value("${security.partner.api-key-sha256}") String digest) {
        return new PartnerApiKeyProvider(digest);
    }

    @Bean
    @Order(1)
    SecurityFilterChain partner(
            HttpSecurity http, PartnerApiKeyProvider provider) throws Exception {
        AuthenticationManager manager = new ProviderManager(provider);
        PartnerApiKeyFilter filter = new PartnerApiKeyFilter(manager);

        return http
                .securityMatcher("/partner/**")
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .securityContext(context -> context
                        .securityContextRepository(
                                new NullSecurityContextRepository()))
                .csrf(AbstractHttpConfigurer::disable)
                .authenticationManager(manager)
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().hasAuthority("PARTNER_READ"))
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint(
                                new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)))
                .addFilterBefore(filter, UsernamePasswordAuthenticationFilter.class)
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain userJwt(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .csrf(AbstractHttpConfigurer::disable)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/reports")
                        .hasAuthority("SCOPE_reports.read")
                        .requestMatchers("/api/high-assurance")
                        .access(highAssurance())
                        .anyRequest().denyAll())
                .oauth2ResourceServer(resource -> resource
                        .jwt(Customizer.withDefaults()))
                .build();
    }

    private static AuthorizationManager<RequestAuthorizationContext> highAssurance() {
        return (authentication, context) -> {
            Authentication candidate = authentication.get();
            boolean allowed =
                    candidate instanceof JwtAuthenticationToken jwt
                    && jwt.isAuthenticated()
                    && "urn:example:acr:mfa".equals(
                            jwt.getToken().getClaimAsString("acr"))
                    && jwt.getAuthorities().stream()
                            .anyMatch(a -> "SCOPE_admin.write".equals(
                                    a.getAuthority()));
            return new AuthorizationDecision(allowed);
        };
    }

    @Bean
    @Order(3)
    SecurityFilterChain catchAll(HttpSecurity http) throws Exception {
        return http.authorizeHttpRequests(auth -> auth
                .anyRequest().denyAll()).build();
    }

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${security.jwt.jwk-set-uri}") String jwkSetUri,
            @Value("${security.jwt.issuer}") String issuer,
            @Value("${security.jwt.audience}") String audience) {

        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withJwkSetUri(jwkSetUri).build();

        OAuth2TokenValidator<Jwt> standard =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> correctAudience = jwt ->
                jwt.getAudience().contains(audience)
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                                new OAuth2Error(
                                        "invalid_token", "Wrong audience", null));

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
                standard, correctAudience));
        return decoder;
    }
}
```

**Explanation of design decisions:**

1. `@Order(1)` selects the partner chain **only** for `/partner/**`, using `PartnerApiKeyFilter` and the `PARTNER_READ` authority. Instantiating the filter inside the method avoids Spring Boot auto-registering it once in the Servlet container outside the chain.
2. `@Order(2)` matches only `/api/**`. This chain enables the JWT resource server and **contains no API key filter**. Thus an API key can never become a `JwtAuthenticationToken` on user endpoints.
3. `@Order(3)` is the catch-all chain with no `securityMatcher` and `denyAll()`. No endpoints outside the defined namespaces are left exposed.
4. `highAssurance()` requires `JwtAuthenticationToken`, exact `SCOPE_admin.write`, and an `acr` meaning MFA per the AS contract. If the authentication is a machine-key token, it is rejected.
5. `NimbusJwtDecoder` verifies the signature against the trusted JWKS; `JwtValidators.createDefaultWithIssuer` checks issuer and timestamps, while `correctAudience` adds the API's audience check. Validly signed tokens meant for another resource are rejected.
6. `csrf(...disable)` fits only **these two stateless header-authenticated APIs without cookies/sessions**. Websites with sessions must have separate chains and CSRF policies; never copy global CSRF disabling across the whole application.

**Note:** claim `acr=urn:example:acr:mfa` is an **illustrative** value, not an MFA code supported by every IdP. To prove MFA, the AS must genuinely perform strong authentication and sign the assurance into the **API access token**; the RS verifies the token and claims per contract. If MFA within the last 5 minutes is required, an additional `auth_time`/step-up policy is needed, which the current example does not check for recency.

### 7.6. Main and illustrative controller

**BoundaryApplication.java**

```java
package com.example.boundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(BoundaryApplication.class, args);
    }
}
```

**DemoController.java**

```java
package com.example.boundary;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/partner/status")
    public String partner() {
        return "partner: permitted";
    }

    @GetMapping("/api/reports")
    public String report() {
        return "report: permitted";
    }

    @GetMapping("/api/high-assurance")
    public String strong() {
        return "high assurance: permitted";
    }
}
```

When dependencies and configuration are placed in an appropriate Boot 3.x project, these classes live as separate Java files in one package. Token/JWKS issuance belongs to an external AS; the sample code **does not** issue access tokens itself. In production, endpoints must separately check object permissions, tenants, account status, rate limits, and gateway policies.

## 8. Anti-bypass test matrix

Testing only a valid key on the partner endpoint is **insufficient**. The most important test suite is **valid key + endpoint requiring JWT/MFA = rejected**.

| Request | Credential | Expectation |
| --- | --- | --- |
| `GET /partner/status` | Valid API key | 200 |
| `GET /partner/status` | Missing API key | 401 |
| `GET /partner/status` | Wrong API key | 401 |
| `GET /partner/status` | JWT without API key | 401 |
| `GET /partner/status` | API key + Bearer header | 400 in example |
| `GET /api/reports` | Valid API key only | 401 |
| `GET /api/high-assurance` | Valid API key only | 401 |
| `GET /api/high-assurance` | JWT with admin scope but no MFA assurance | 403 |
| `GET /api/high-assurance` | JWT with MFA assurance but missing scope | 403 |
| `GET /api/high-assurance` | JWT with right scope + MFA assurance | 200 |
| `GET /api/reports` | JWT with `reports.read` | 200 |
| URL outside namespaces | Any | Blocked by catch-all |

### 8.1. Spring Security Test with MockMvc

**src/test/java/com/example/boundary/AuthBoundaryTest.java**

```java
package com.example.boundary;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthBoundaryTest {

    private static final String TEST_KEY =
            "test_only_key_abcdefghijklmnopqrstuvwxyz0123456789ABCD";

    @DynamicPropertySource
    static void props(DynamicPropertyRegistry registry) {
        registry.add("security.partner.api-key-sha256",
                () -> sha256Hex(TEST_KEY));
        registry.add("security.jwt.issuer",
                () -> "https://idp.example.test/realm/training");
        registry.add("security.jwt.jwk-set-uri",
                () -> "https://idp.example.test/jwks");
        registry.add("security.jwt.audience",
                () -> "protected-api");
    }

    private static String sha256Hex(String raw) {
        try {
            return HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256").digest(
                            raw.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(ex);
        }
    }

    @Autowired
    MockMvc mvc;

    @Test
    void keyWorksOnlyForPartnerEndpoint() throws Exception {
        mvc.perform(get("/partner/status").header("X-Partner-Key", TEST_KEY))
                .andExpect(status().isOk())
                .andExpect(content().string("partner: permitted"));

        mvc.perform(get("/api/reports").header("X-Partner-Key", TEST_KEY))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/high-assurance")
                        .header("X-Partner-Key", TEST_KEY))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void invalidAndMixedPartnerCredentialsFail() throws Exception {
        mvc.perform(get("/partner/status"))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/partner/status")
                        .header("X-Partner-Key", "wrong"))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/partner/status")
                        .header("X-Partner-Key", TEST_KEY)
                        .header(HttpHeaders.AUTHORIZATION, "Bearer anything"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void mfaAndScopeAreBothRequired() throws Exception {
        mvc.perform(get("/api/high-assurance").with(jwt()
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_admin.write"))))
                .andExpect(status().isForbidden());

        mvc.perform(get("/api/high-assurance").with(jwt()
                        .jwt(token -> token.claim(
                                "acr", "urn:example:acr:mfa"))
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_other"))))
                .andExpect(status().isForbidden());

        mvc.perform(get("/api/high-assurance").with(jwt()
                        .jwt(token -> token.claim(
                                "acr", "urn:example:acr:mfa"))
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_admin.write"))))
                .andExpect(status().isOk())
                .andExpect(content().string("high assurance: permitted"));
    }

    @Test
    void jwtCanReadReportsWithScope() throws Exception {
        mvc.perform(get("/api/reports").with(jwt()
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_reports.read"))))
                .andExpect(status().isOk())
                .andExpect(content().string("report: permitted"));
    }
}
```

Run with the Gradle wrapper:

```bash
./gradlew test
```

Windows PowerShell: `.\gradlew.bat test`. These are **expected test results for the sample code**, not tests already run in a real system. The test key uses an explicit string solely for tests; production must use a CSPRNG key and never commit secrets.

### 8.2. Why is this not enough to prove real JWT/MFA?

Spring Security Test's `jwt()` helper constructs a mock `Authentication` for MockMvc without checking signatures, JWKS, issuer, audience, or expiration. Therefore it tests only **authorization and chain isolation**, not whether an AS genuinely performed MFA.

Add integration tests sending HTTP Bearer JWTs signed with a test private key to the API, using a test JWKS endpoint and verifying:

- Invalid signature, disallowed `alg`, non-existent `kid`.
- Wrong issuer, different audience, expired, before `nbf`.
- Valid token lacking MFA assurance (or too old if policy requires recency).
- Client credentials token instead of a user token when a user is required.
- Invalid JWT + valid API key on a JWT endpoint: **never falls back to the API key**.
- Revoked/expired keys and clients/keys from another tenant.
- URLs after gateway rewrites, servlet context paths, trailing slashes, path encoding, and other HTTP methods.

Never use production signing keys in tests. The test suite must prove sensitive controllers **do not execute** in rejected scenarios, rather than merely matching an HTTP status code.

## 9. Controlling MFA, step-up, and human-in-the-loop

An API key proves possession of a **service** secret; MFA proves a human user completed strong authentication under IdP policy. Never assign `ROLE_USER` to a key or add an `X-MFA:true` header to pretend an authenticated user is present.

If business logic requires human approval:

1. Require the user to perform step-up via the IdP or internal authentication platform.
2. The AS issues an API access token carrying trusted assurance evidence and an appropriate lifetime.
3. The RS verifies signature, issuer, audience, scopes, assurance claim, and authentication time when policy demands it.
4. The service enforces object-level permissions and separation of duties; audit logs record the real human user.
5. Jobs or partners still use separate keys for permitted machine tasks, never acting as the approver.

If the AS does not include an assurance claim in access tokens, the RS **cannot infer MFA** merely from user login. A re-authentication/token-exchange step or other trusted-system proof must be designed.

For high-risk actions, also enforce replay protection, limits, and business transaction checks, because an MFA-backed JWT can still be stolen or over-scoped. Strong authentication is one layer, not a replacement for data authorization.

## 10. API key lifecycle and permissions in production

A key record might contain:

```sql
CREATE TABLE api_client_key (
    key_id VARCHAR(80) PRIMARY KEY,
    client_id VARCHAR(120) NOT NULL,
    sha256_hex CHAR(64) NOT NULL,
    scope VARCHAR(255) NOT NULL,
    tenant_id VARCHAR(80),
    expires_at TIMESTAMP WITH TIME ZONE,
    revoked_at TIMESTAMP WITH TIME ZONE
);
```

This schema only illustrates metadata storage, not a complete DB design. Real deployments should include public key IDs and separate secrets, client status, rotation, auditing, key-count limits, transactions/locking, and policy caching. Never return full hashes/tokens in error messages.

**Issuance/rotation/revocation workflow:**

- Generate keys with a CSPRNG, issuing to the right client and environment. Default to least privilege.
- Look up by key ID and compare digest/HMAC in a timing-leak-resistant manner; check scope, tenant, `expiresAt`, and `revokedAt`.
- New and old keys may run in parallel during a controlled transition window, then revoke the old key.
- When a key leaks, revoke quickly, investigate by key ID, and never record keys in tickets/logs. If keys are cached, set an appropriate TTL so revocation takes effect.
- Enforce rate limits, anomaly detection, alerts on failed key attempts, and per-client/tenant quotas; never use IP allowlists as the sole authentication method.

Partner keys have access only to that partner's data. Prevent object-level authorization bypass by checking tenant/owner in the service or database. A `PARTNER_READ` authority must never grant access to every report across the entire system.

## 11. Combining OAuth2 JWT, sessions, Basic, or gateways

- `oauth2ResourceServer().jwt()` validates **bearer access tokens** for APIs. `oauth2Login()` serves web logins; `oauth2Client()` helps clients call external APIs with tokens. Never confuse their roles.
- An application with a UI using cookie sessions needs CSRF, session fixation/logout protection, and its own security chain. Never disable CSRF globally just because a partner API uses keys.
- A route requiring JWT/MFA must never accept an API key due to a filter placed in the wrong chain/position or an entry point fallback.
- With gateways, ensure real paths, forwarded headers, and security matchers align; backends must never trust client-supplied `X-User`, `X-Role`, or `X-MFA`.
- mTLS adds trusted machine binding for services; if the gateway authenticates on behalf of the backend, establish a trust contract, network isolation, and anti-header-spoofing controls.
- `CORS` only regulates browsers; it does not stop `curl` or other clients from using a key.
- Never place API keys in frontend JavaScript or public mobile apps and treat them as server secrets.

## 12. Handling errors under fail-closed principles

| Case | Recommended behavior |
| --- | --- |
| Missing key on partner route | 401, no fallback |
| Wrong/expired/revoked key | 401, no principal granted |
| Valid key on JWT route | Still requires a valid Bearer JWT |
| JWT with wrong issuer/audience/signature/time | Reject, do not try key |
| Valid JWT missing scope/MFA | Typically 403 |
| Key store/JWKS/AS unresponsive | Do not permit without verification; track infrastructure errors separately |
| Request carries two conflicting credential types | Reject or follow explicit policy, never pick the weakest path |
| URL outside expected routes | Catch-all deny |

Specifically avoid patterns like:

```java
// DO NOT implement: all failures of the stronger step fall back to key
try {
    return verifyJwtAndMfa(request);
} catch (Exception failure) {
    return verifyApiKey(request);
}
```

This is pseudocode highlighting an anti-pattern. Never swallow `AuthenticationException`, JWK/introspection errors, or DB failures into `permitAll()`. Depending on configuration, 401 usually indicates missing/wrong credentials and 403 indicates authenticated but unauthorized; never rely solely on status codes to conclude there is no bypass—verify that policies and sensitive operations are genuinely blocked.

## 13. Pull request review checklist

When reviewing a change that adds API keys, check:

- [ ] Is there an endpoint-and-allowed-credential matrix? Do sensitive MFA routes still accept only the strong method?
- [ ] Is the key chain's `securityMatcher` overly broad? Is there a catch-all `denyAll()`?
- [ ] Does the custom key filter run twice or run outside Spring Security?
- [ ] Does the key provider distinguish unauthenticated request tokens from authenticated result tokens?
- [ ] Is the key principal a machine/service, with narrow authorities distinct from user roles?
- [ ] Does the JWT decoder verify signature, issuer, audience, and expiration; does the MFA policy come from a trusted source?
- [ ] Do requests with key + JWT, wrong key, expired JWT, and JWT without MFA fail closed per route?
- [ ] Does every key have key ID, owner, scopes, tenant, expiry, revocation, rotation, rate limits, and safe auditing?
- [ ] Are full keys, bearer tokens, secrets, and potentially sensitive hashes excluded from logs?
- [ ] Have paths behind proxies, HTTP methods, trailing slashes, encoded paths, and object-level authorization been tested?
- [ ] Have real JWTs been tested through the decoder, beyond MockMvc's simulated `jwt()`?

The checklist's goal is verifying the **entire path from request to data**, including infrastructure, filter selection, principal types, claims, and domain authorization.

## 14. Exercises and common pitfalls

**Exercise 1:** Add `POST /api/approve` requiring `SCOPE_approval.write` and user MFA assurance. Write tests verifying a valid API key still gets 401 and a JWT lacking MFA gets 403. Never grant `ROLE_ADMIN` to the key.

**Exercise 2:** Create a key registry for two partners in different tenants. Test that key A cannot view B's data, even though both have `PARTNER_READ`.

**Exercise 3:** Remove the catch-all chain in a test environment. Call a URL outside `/api/**` and `/partner/**`; explain the risk and restore deny-all.

**Exercise 4:** Write a JWT integration test signed with a test key containing issuer, audience, exp, and acr. Add cases for a validly signed JWT with wrong audience, valid key alone, and key + JWT simultaneously.

**Exercise 5:** Design a workflow requiring both service mTLS identity and user step-up. Specify both proofs, the AND policy, verification recency, and how to prevent credential confusion.

Common pitfalls to spot: global key filters; `jwtValid || keyValid`; granting admin roles to keys; skipping audience checks; trusting `X-MFA` headers; failing to distinguish service/user principals; missing revocation; and writing only happy-path tests.

## 15. Conclusion

**API keys fit machine-to-machine use cases with well-bounded scopes, but are never an alternative login path for resources requiring JWT/OIDC/MFA.** In Spring Security, isolate routes via `securityMatcher`, use an `AuthenticationProvider` to validate keys before granting authorities, restrict client-side authorities, and enforce a catch-all deny-all chain. Sensitive endpoints must verify the right token type, issuer/audience, scopes, and trusted issuer-confirmed assurance. Reinforce with rotation, rate limits, tenant/object authorization, gateway rules, and negative tests proving a valid key still **cannot** bypass stronger requirements.

**Official references:**

- [Spring Security 6.5 – Java Configuration (multiple SecurityFilterChains)](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security 6.5 – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security 6.5 – OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
- [OWASP API Security Top 10 (Broken Authentication and Object-level Authorization)](https://owasp.org/API-Security/editions/2023/en/0x11-t10/)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
# Combining a Session-Based UI with a Resource Server Using Two Independent Chains

> **Integrated practice — Spring Security Servlet.** This practice builds a Spring Boot 3.x, Java 17+ application with a **web UI using form login and HTTP sessions** and a **REST API using OAuth2 Resource Server, Bearer JWT, and stateless handling**. The two paths use **two `SecurityFilterChain`s independent in matcher, authentication mechanism, session policy, CSRF, entry point, and authorization rules**, while living inside the same Servlet application. Examples and tests use only test accounts, tokens, and URLs; never use production credentials or keys.

## 1. Goals and Real-World Problem

Suppose a single Spring Boot app serves two groups of clients:

1. **Staff browsers:** access `/ui/**`, log in via `/login`, and maintain login state with the `JSESSIONID` cookie; POST forms require a CSRF token. Users with the `USER` role can access the profile page.
2. **Partners or API clients:** access `/api/**` with `Authorization: Bearer <access-token>`; the JWT is verified against trusted public keys, issuer, audience, and expiration. Every request must carry a bearer token; the API does not use web sessions for authentication.

If all URLs are placed in a single shared filter chain, common failures include: the API returning **302 to the login page** instead of **401 Bearer**, the API accidentally trusting a session cookie to bypass JWT verification, UI POSTs without CSRF being permitted, or an API client token acting as a staff browser session login.

**Expected outcome:** a working application that never mixes the two mechanisms, with tests proving that disallowed access paths **are rejected**.

```text
                   Single Spring Boot Servlet app
                               |
                    FilterChainProxy selects
                    FIRST MATCHING CHAIN
                               |
             +-----------------+------------------+
             |                                    |
      /api/**                                     /** (fallback)
      @Order(1)                                   @Order(2)
             |                                    |
    JWT Bearer token                       Form login / JSESSIONID
    OAuth2 Resource Server                 UserDetailsService
    STATELESS                              IF_REQUIRED session
    Ignores UI session                     SecurityContext in session
    CSRF off ONLY on /api/**               CSRF on for forms/POST
    API 401/403 per Bearer                 302 /login or 403
             |                                    |
       /api/me, /api/actions                /ui/me, /ui/change
```

Two separate application contexts or two HTTP ports are not required. These are **two `SecurityFilterChain`s inside the same `FilterChainProxy`**, selected per request. Each chain's configuration takes effect only when a request **matches that chain**.

## 2. Separating Boundaries Properly: securityMatcher vs. requestMatchers

This is the most critical distinction.

- `http.securityMatcher("/api/**")` decides whether **the entire chain** applies to a request.
- `authorizeHttpRequests(...requestMatchers(...))` defines **authorization rules inside the already-selected chain**. It does not restrict the chain itself to running only on those URLs.
- `@Order(1)` ensures the API chain is evaluated **before** the UI chain.
- `@Order(2)` acts as the `securityMatcher("/**")` fallback so non-API paths remain protected. If no chain matches, a URL could be **unprotected by Spring Security**; avoid defining only two narrow `securityMatcher`s and leaving new endpoints exposed.

Correct example:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        // API-specific configuration here.
        .build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/**")
        // UI-specific configuration here.
        .build();
}
```

The snippet above only illustrates ordering/matchers; **it is not a complete secure program**. Subsequent sections provide full authorization rules, authentication, CSRF, and session management.

A common mistake is placing the catch-all `securityMatcher("/**")` at `@Order(1)`. Every API request is then intercepted by the UI chain first; you may get a 302 login redirect and never reach the API's Bearer filter. Never fix this by deleting the API `securityMatcher` or disabling UI security; fix the **matcher/order** and test it.

Having independent `SecurityFilterChain`s does not mean beans in the application context are isolated. Both can still share a `UserDetailsService`, `AuthenticationManager`, or logging if configured to do so. Separation must be **enforced through matchers and each chain's security configuration**.

## 3. Explicit Policy Before Writing Code

| Requirement | Session-based UI | Resource Server API |
|---|---|---|
| URL paths | `/ui/**`, `/login`, `/logout` | `/api/**` |
| Chain priority | Fallback `@Order(2)` | `@Order(1)` |
| Identity | Form username/password, then `Authentication` stored via HTTP session | Bearer JWT verified on **every request** |
| Credential transport | Session cookie auto-sent by browser | `Authorization: Bearer ...` header set by client |
| Session policy | `SessionCreationPolicy.IF_REQUIRED` | `SessionCreationPolicy.STATELESS` |
| SecurityContext persistence | Default session-based context for web login | Never read/write context from HTTP session |
| CSRF | **Enabled** for browser/cookie state changes | Can be disabled **only in pure bearer API** |
| Request cache | May save pre-login URL | Disable browser redirect/saved request |
| Unauthenticated | Redirect `/login` (browser) | 401 with Bearer challenge |
| Authenticated but lacking permission | 403 | 403 |
| Logout | POST `/logout` with CSRF, invalidate web session | No automatic "JWT logout"; use TTL/revocation separately |
| Authorities | `ROLE_USER` | `SCOPE_api.read`, `SCOPE_api.write` |
| Default for unmatched URLs | Deny by default | API chain does not apply outside `/api/**` |

**Important boundary rule:** Browsers may still **send the `JSESSIONID` cookie to `/api/**`** if the cookie path/domain covers the API. That does not mean the API accepts sessions: the API chain must **ignore the session context**. Tests must prove "session-only API request → 401". Matcher separation alone does not govern browser cookie paths.

### 3.1. When Is the API Allowed to Disable CSRF?

CSRF is a risk when a browser **automatically attaches credentials** to a cross-site request (typically session cookies). For an API that only authenticates **bearer tokens explicitly placed in the Authorization header by the client** and rejects cookies or browser-cached Basic auto-credentials, CSRF can be disabled in the **API chain**. However, if the API also accepts session cookies, automatic HTTP Basic, or ambient browser credentials, **never assume CSRF is harmless** just because the URL starts with `/api`.

In the design below, the API is explicitly configured as **stateless JWT Bearer only**; `csrf.disable()` is called only inside the API chain. The UI chain keeps default CSRF protection. `SameSite` cookies and CORS **do not replace** CSRF protection for the UI.

## 4. Tools and Practice Project Structure

Uses Java 17, Spring Boot **3.3.5**, the matching Spring Security version managed by Spring Boot dependency management, Gradle, and JUnit 5. These are **specific versions for the sample project**, not claims about the latest release. Use the project's Gradle Wrapper.

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Directory tree to create:

```text
src/
  main/
    java/demo/dualchain/
      DualChainApplication.java
      SecurityConfig.java
      ApiOperations.java
      DemoController.java
    resources/
      application.yml
  test/
    java/demo/dualchain/
      DualChainSecurityTest.java
      ApiOperationsTest.java
```

The sample provides one **in-memory web user for learning only**, with its password supplied via the runtime property `DEMO_WEB_PASSWORD` instead of hardcoding production credentials. The JWT verifier uses an intentionally non-routable JWKS URL (`.invalid`) to avoid calling a real IdP; **MockMvc stubs JwtDecoder to test mapping/authorization**, without verifying signatures. In real deployments, replace issuer/JWKS/audience with environment values and add signed-token integration tests.

## 5. application.yml and Spring Boot Entry Point

`src/main/resources/application.yml`:

```yaml
demo:
  jwt:
    issuer: "https://id.example.invalid/"
    audience: "demo-api"
    jwks-uri: "https://id.example.invalid/jwks.json"

server:
  servlet:
    session:
      timeout: 30m
```

`demo.jwt.issuer` and `demo.jwt.jwks-uri` are **non-functional** placeholders for configuration learning. Do not craft a fake JWT and expect this resource server to accept it outside tests. The application starts cleanly, but with this JWKS URL, real Bearer token requests cannot be verified.

`src/main/java/demo/dualchain/DualChainApplication.java`:

```java
package demo.dualchain;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DualChainApplication {
    public static void main(String[] args) {
        SpringApplication.run(DualChainApplication.class, args);
    }
}
```

The example URLs use local HTTP. When deploying web login on a real network, require HTTPS, proper `Secure`/`HttpOnly`/`SameSite` session cookies, proxy awareness, and monitoring. Do not enable `Secure` cookies in an HTTP-only localhost test environment and assume browsers will send them normally; configure production separately and verify over real TLS.

## 6. Two SecurityFilterChains: Full Configuration, Proper Scope

`src/main/java/demo/dualchain/SecurityConfig.java`:

```java
package demo.dualchain;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.NullSecurityContextRepository;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    // Demo web account ONLY. Production must use a dedicated user store/IdP.
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService webUsers(
            PasswordEncoder encoder,
            @Value("${DEMO_WEB_PASSWORD}") String password) {
        if (password.isBlank() || password.length() < 12) {
            throw new IllegalStateException(
                "Local web demo credential is missing or invalid");
        }

        UserDetails user = User.withUsername("webuser")
            .password(encoder.encode(password))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(user);
    }

    // Real Resource Server token validation when JwtDecoder is not mocked.
    @Bean
    JwtDecoder jwtDecoder(
            @Value("${demo.jwt.jwks-uri}") String jwksUri,
            @Value("${demo.jwt.issuer}") String issuer,
            @Value("${demo.jwt.audience}") String audience) {

        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(jwksUri).build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audienceRule = token ->
            token.getAudience().contains(audience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token", "Required API audience missing", null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime, audienceRule));
        return decoder;
    }

    // CHAIN 1: /api/** accepts only Bearer tokens, never web sessions.
    @Bean
    @Order(1)
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .requestMatchers(HttpMethod.POST, "/api/actions")
                    .authenticated()
                .anyRequest().denyAll())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .securityContext(context -> context
                .securityContextRepository(new NullSecurityContextRepository()))
            .requestCache(cache -> cache.disable())
            .csrf(csrf -> csrf.disable())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }

    // CHAIN 2: Web UI fallback; form login + cookie-backed session + CSRF.
    @Bean
    @Order(2)
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .requestMatchers("/ui/**").hasRole("USER")
                .anyRequest().denyAll())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .csrf(Customizer.withDefaults())
            .formLogin(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/login?logout")
                .invalidateHttpSession(true))
            .build();
    }
}
```

### 6.1. Why Does the API Chain Reject Sessions?

`SessionCreationPolicy.STATELESS` tells Spring Security not to create or use an `HttpSession` to obtain `SecurityContext` for the API. `NullSecurityContextRepository` in the demo makes explicit that bearer request contexts are **never saved to or loaded from the web session**. `requestCache.disable()` prevents browser saved-request/redirect handling in the API.

The Bearer token is read on every request by `BearerTokenAuthenticationFilter` and passed to `JwtAuthenticationProvider`/`JwtDecoder`. For a self-contained JWT, a valid token creates a `JwtAuthenticationToken` for that single request; the next request **never inherits authentication from the UI session**.

Note: **stateless** does not mean "the server has zero caches": decoder/JWKS caches, connection pools, application business caches, or policy stores may still exist. It specifically states that **API request authentication state does not rely on HTTP sessions** in this chain.

### 6.2. Why Does the UI Chain Keep Sessions and CSRF?

The UI uses `UsernamePasswordAuthenticationFilter` (form login); after verifying the password with `PasswordEncoder`/`UserDetailsService`, the context can be persisted in the HTTP session. Subsequent requests carry the `JSESSIONID` cookie to be recognized as the same web user.

`SessionCreationPolicy.IF_REQUIRED` allows creating a session when needed; `formLogin()` provides a default login page so the demo needs no HTML template. `csrf(Customizer.withDefaults())` preserves CSRF protection for state-changing requests, including `POST /ui/change` and `POST /logout`; **GET** requests should not mutate state.

`logout()` primarily clears the **web session** login. It **does not revoke API clients' access JWTs**; self-contained JWTs remain valid until expiration or revocation via a separate mechanism.

### 6.3. Why Is Method Security Still Needed?

`@EnableMethodSecurity` ensures `@PreAuthorize` annotations on business services are enforced when invoked through Spring-managed beans. The URL chain requires `authenticated()` for the API, while the service layer can demand a **narrower scope**. Calling a service via `new` or self-invocation bypasses the proxy and skips method authorization. Tests inject Spring-managed beans rather than manually instantiated objects.

If a system shares service methods between UI and API, do not casually put `hasRole('USER')` to satisfy all clients; design a coherent authorization model, accurate scope/role mapping, and resource-level checks.

## 7. Building the Business Service and Controller Separating UI/API

`src/main/java/demo/dualchain/ApiOperations.java`:

```java
package demo.dualchain;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ApiOperations {
    @PreAuthorize("hasAuthority('SCOPE_api.read')")
    public String read() {
        return "api-read-ok";
    }

    @PreAuthorize("hasAuthority('SCOPE_api.write')")
    public String write() {
        return "api-write-ok";
    }
}
```

`SCOPE_api.read` and `SCOPE_api.write` are produced by the default `JwtGrantedAuthoritiesConverter` when a verified JWT contains `scope: "api.read"` or `scope: "api.write"`. The UI session only has `ROLE_USER`; it has no `SCOPE_api.read` unless intentionally granted by another policy.

`src/main/java/demo/dualchain/DemoController.java`:

```java
package demo.dualchain;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    private final ApiOperations api;

    public DemoController(ApiOperations api) {
        this.api = api;
    }

    @GetMapping("/")
    public String home() {
        return "Two security chains: /ui/** and /api/**";
    }

    @GetMapping("/ui/me")
    public Map<String, String> webMe(Authentication authentication) {
        return Map.of(
            "mode", "session",
            "user", authentication.getName());
    }

    // Exercise simulates state mutation; performs no real write.
    @PostMapping("/ui/change")
    public String changeWebSettings() {
        return "ui-change-ok";
    }

    @GetMapping("/api/me")
    public Map<String, String> apiMe(Authentication authentication) {
        return Map.of(
            "mode", "bearer",
            "subject", authentication.getName(),
            "result", api.read());
    }

    @PostMapping("/api/actions")
    public String writeApi() {
        return api.write();
    }
}
```

This is a functional demo; real products need DTOs, validation, error responses, auditing, and object-level authorization. `user`/`subject` may be personal data; avoid exposing unnecessary principal attributes in production responses.

### 7.1. Why Can an Authenticated GET API Endpoint Still Return 403?

At the URL layer, the API chain only checks `authenticated()`. However, `api.read()` is guarded by the method-security proxy checking `SCOPE_api.read`. A successfully verified token that only holds `SCOPE_api.write` receives **403 Forbidden** at the method-security layer on GET; that is the intended behavior. Always distinguish **token authentication failure (401)** from **authenticated with insufficient scope (403)**.

Conversely, `/ui/me` requires `hasRole("USER")` in the web chain, backed by `ROLE_USER` issued during form login. A bearer token with API scopes is not automatically treated as a web user.

## 8. MockMvc Tests: Proving the Two Chains Do Not "Borrow" Each Other's Identity

For trustworthy tests, verify both **allow** and **deny** paths for both mechanisms. `@AutoConfigureMockMvc` keeps Spring Security filters active; do not use `addFilters=false` or `MockMvcBuilders.standaloneSetup(...)` without `springSecurity()` when testing filter chains.

**Important scope note:** the tests below use `@MockBean JwtDecoder` to simulate decoding so they focus on **chain selection, Bearer authentication plumbing, authority mapping, UI sessions, and CSRF**. Because the decoder is mocked, **JWT/JWKS signature checks and issuer/audience validators are not exercised** in those test requests. Section 11 describes real issuer/JWKS tests.

`src/test/java/demo/dualchain/DualChainSecurityTest.java`:

```java
package demo.dualchain;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "DEMO_WEB_PASSWORD=local-test-browser-password"
})
@AutoConfigureMockMvc
class DualChainSecurityTest {
    @Autowired MockMvc mvc;

    // This class mocks the decoder only to verify routing + authority mapping.
    @MockBean JwtDecoder jwtDecoder;

    private Jwt fixture(String value, String subject, String scope) {
        return Jwt.withTokenValue(value)
            .header("alg", "RS256")
            .subject(subject)
            .claim("iss", "https://id.example.invalid/")
            .claim("aud", List.of("demo-api"))
            .claim("scope", scope)
            .issuedAt(Instant.now().minusSeconds(60))
            .expiresAt(Instant.now().plusSeconds(600))
            .build();
    }

    @BeforeEach
    void stubJwtDecoder() {
        when(jwtDecoder.decode("read-token")).thenReturn(
            fixture("read-token", "api-reader", "api.read"));
        when(jwtDecoder.decode("write-token")).thenReturn(
            fixture("write-token", "api-writer", "api.write"));
        when(jwtDecoder.decode("other-token")).thenReturn(
            fixture("other-token", "api-other", "api.other"));
    }

    private MockHttpSession loggedInWebSession() throws Exception {
        MvcResult result = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "webuser")
                .param("password", "local-test-browser-password"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);
        assertNotNull(session);
        return session;
    }

    @Test
    void webWithoutSessionRedirectsToLogin() throws Exception {
        mvc.perform(get("/ui/me"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void formLoginSessionCanAccessUi() throws Exception {
        MockHttpSession session = loggedInWebSession();
        mvc.perform(get("/ui/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.mode").value("session"))
            .andExpect(jsonPath("$.user").value("webuser"));
    }

    @Test
    void webSessionAloneCannotAuthenticateApi() throws Exception {
        MockHttpSession session = loggedInWebSession();
        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void apiWithoutBearerReturns401NotLoginRedirect() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void bearerReadTokenCanReadApi() throws Exception {
        mvc.perform(get("/api/me")
                .header("Authorization", "Bearer read-token"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.mode").value("bearer"))
            .andExpect(jsonPath("$.subject").value("api-reader"))
            .andExpect(jsonPath("$.result").value("api-read-ok"));
    }

    @Test
    void bearerTokenWithoutReadScopeGets403() throws Exception {
        mvc.perform(get("/api/me")
                .header("Authorization", "Bearer other-token"))
            .andExpect(status().isForbidden());
    }

    @Test
    void bearerTokenAloneCannotOpenSessionUi() throws Exception {
        mvc.perform(get("/ui/me")
                .header("Authorization", "Bearer read-token"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void webPostWithoutCsrfIsRejected() throws Exception {
        MockHttpSession session = loggedInWebSession();
        mvc.perform(post("/ui/change").session(session))
            .andExpect(status().isForbidden());
    }

    @Test
    void webPostWithCsrfIsAllowed() throws Exception {
        MockHttpSession session = loggedInWebSession();
        mvc.perform(post("/ui/change")
                .session(session).with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("ui-change-ok"));
    }

    @Test
    void apiPostWithBearerNeedsNoCookieCsrfToken()
            throws Exception {
        mvc.perform(post("/api/actions")
                .header("Authorization", "Bearer write-token"))
            .andExpect(status().isOk())
            .andExpect(content().string("api-write-ok"));
    }

    @Test
    void bearerWithoutWriteScopeCannotPost() throws Exception {
        mvc.perform(post("/api/actions")
                .header("Authorization", "Bearer read-token"))
            .andExpect(status().isForbidden());
    }

    @Test
    void webLogoutIsProtectedByCsrf() throws Exception {
        MockHttpSession session = loggedInWebSession();
        mvc.perform(post("/logout").session(session))
            .andExpect(status().isForbidden());
        mvc.perform(post("/logout").session(session).with(csrf()))
            .andExpect(status().is3xxRedirection());
    }
}
```

**Reading each test group:**

- `webWithoutSessionRedirectsToLogin` shows the UI uses the browser authentication entry point rather than returning a Bearer 401 JSON error.
- `formLoginSessionCanAccessUi` proves that after form login, `SecurityContext` is persisted in the web session and subsequent requests can use it.
- `webSessionAloneCannotAuthenticateApi` is a critical test: even when sending the `MockHttpSession` to `/api/me`, the API chain **still requires a JWT** and returns 401.
- `apiWithoutBearerReturns401NotLoginRedirect` catches misrouted chains: if it returns 302, inspect `@Order` and `securityMatcher`.
- `bearerReadTokenCanReadApi`/`bearerTokenWithoutReadScopeGets403` show the JWT is decoded by the stub, scopes become `SCOPE_api.read`, and method security enforces permissions.
- `bearerTokenAloneCannotOpenSessionUi` proves an API token does not establish a browser session on the web chain.
- `webPostWithoutCsrfIsRejected` and `webPostWithCsrfIsAllowed` confirm CSRF is enforced specifically on the web chain.
- `apiPostWithBearerNeedsNoCookieCsrfToken` is acceptable **strictly under the assumption that the API uses only bearer headers** and rejects browser-cookie authentication.
- `webLogoutIsProtectedByCsrf` ensures POST logout is also protected by CSRF.

A `403` from missing CSRF can fire before method security. To test scope/role on a web POST, the test must include a valid `with(csrf())` before checking permissions; meanwhile, the pure bearer API POST uses no cookies, so the demo disables CSRF on the API chain.

## 9. Testing Method Security Independently to Avoid Filter or JWT Confusion

`src/test/java/demo/dualchain/ApiOperationsTest.java`:

```java
package demo.dualchain;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(properties = {
    "DEMO_WEB_PASSWORD=local-test-browser-password"
})
class ApiOperationsTest {
    @Autowired ApiOperations api;

    @Test
    @WithMockUser(authorities = "SCOPE_api.read")
    void matchingScopeAllowsRead() {
        assertEquals("api-read-ok", api.read());
    }

    @Test
    @WithMockUser(roles = "USER")
    void webUserRoleDoesNotImplyApiScope() {
        assertThrows(AccessDeniedException.class, api::read);
    }

    @Test
    @WithMockUser(authorities = "SCOPE_api.write")
    void writeScopeAllowsWrite() {
        assertEquals("api-write-ok", api.write());
    }

    @Test
    @WithMockUser(authorities = "SCOPE_api.read")
    void readScopeDoesNotAllowWrite() {
        assertThrows(AccessDeniedException.class, api::write);
    }
}
```

`@WithMockUser` only populates a test `Authentication` in the context; it **does not** send an HTTP request, **does not** run the API chain, and **does not** decode/verify a JWT. This is an isolated test for `@PreAuthorize`. When method tests pass while HTTP API tests fail, inspect the bearer filter, decoder, scope converter, or chain routing rather than disabling method security.

Commands to run in a project with the Gradle Wrapper:

```bash
./gradlew test
./gradlew test --tests demo.dualchain.DualChainSecurityTest
./gradlew test --tests demo.dualchain.ApiOperationsTest
```

Do not assume fixed Gradle stdout because wrappers, JDKs, caches, and runners vary. A test expecting 401/403 **PASSES** when the request is rejected at the right layer.

## 10. Running Locally and Understanding the Demo JWT Limits

In Bash, supply a password **for localhost only**:

```bash
export DEMO_WEB_PASSWORD='local-test-browser-password'
./gradlew bootRun
```

On PowerShell, use the corresponding environment variable syntax. Without `DEMO_WEB_PASSWORD`, the application must fail on startup due to the missing required property; **there is no default production password**.

Observable requests **requiring no secrets**:

```bash
curl -i http://localhost:8080/
curl -i http://localhost:8080/ui/me
curl -i http://localhost:8080/api/me
```

Expectations with the default demo configuration:

- `GET /` → 200, message introducing the two chains.
- `GET /ui/me` unauthenticated → 302 redirecting to `/login`.
- `GET /api/me` without Bearer → 401, not a redirect to web login.

To test form login in a browser, open `http://localhost:8080/ui/me`, get redirected to the default `/login` page, and enter username `webuser` with your configured local password. After logging in, the browser receives a session cookie and accesses the UI. Never send credentials over plain HTTP on a real network; deployed environments use TLS.

The `read-token`/`write-token` strings in the tests **are not real JWTs**. Because the configured issuer/JWKS uses the `.invalid` domain, sending:

```bash
curl -i -H 'Authorization: Bearer read-token' \
  http://localhost:8080/api/me
```

will **not** be accepted by the real decoder; it will normally not return 200 (likely resulting in a decode or JWKS connection error depending on setup). This is intentional so dummy tokens are never mistaken for signed access tokens. Only after configuring a **trusted test authorization server/JWKS** and issuing a real signed token for audience `demo-api` can a Bearer request succeed.

**Never place real access tokens on the command line**, in terminal history, CI logs, or documentation. Use your test environment's secure credential injection mechanisms.

## 11. Testing JWT Signatures, Issuer, Audience, and Claims Beyond MockMvc Stubs

Mocking `JwtDecoder` is valuable for **chain selection + converter + authorization**, but it does not test cryptography. Add integration tests with JWTs **signed by a test private key**, a test JWKS endpoint, and the **real decoder** (without `@MockBean JwtDecoder`).

Recommended test matrix:

| Scenario | Expected Outcome |
|---|---|
| Test JWT signed by trusted JWKS, matching issuer and audience, `scope=api.read` | GET `/api/me` returns 200 |
| JWT missing or invalid signature | 401 |
| JWT issuer does not match configured issuer | 401 |
| JWT has audience for another API | 401 |
| JWT expired or before `nbf` outside clock skew | 401 |
| Valid JWT with only `api.other` | 403 on `/api/me` |
| Valid JWT with `api.read` but missing `api.write` | 403 on `POST /api/actions` |
| Valid JWT with right scope but resource belongs to another tenant | Denied per additional business rule |
| Browser session with `ROLE_USER` calling API without bearer | 401 regardless of cookie |

With signed JWTs, `JwtDecoder` must verify the signature, allowed algorithm, issuer, timestamps, and audience. In `SecurityConfig`, `JwtValidators.createDefaultWithIssuer` and the audience validator protect the required claims; the JWKS source must still belong to your trusted configuration. Reading `scope` from an unverified JWT is **unsafe**.

Furthermore, a self-contained JWT can retain old scopes/roles until expiration even if the user's permissions were revoked at the IdP. For sensitive permissions, use short token TTLs, revocation, introspection, or policy lookups per security requirements. UI sessions and API JWTs have **different revocation lifecycles**; invalidating the session does not invalidate issued JWTs.

## 12. If the UI Uses OIDC Login Instead of Form Login

The demo uses form login to run offline without an IdP. In production, the UI often uses `oauth2Login()`/OIDC for browsers; **the two-chain architecture stays the same**:

- The API chain `securityMatcher("/api/**")` continues running `oauth2ResourceServer().jwt()`, `STATELESS`, and ignoring UI sessions.
- The UI chain `securityMatcher("/**")` switches `formLogin(...)` to `oauth2Login(...)`, keeping sessions and CSRF; configure OAuth2 Client Registration, authorization code flow, redirect URI/callback, and server-side client secret for confidential clients.
- The UI creates `OAuth2AuthenticationToken`/`OidcUser` in the session, while the API creates `JwtAuthenticationToken` from bearer tokens. The authorities/claims mappers for the two flows **are distinct**; do not blindly share `JwtAuthenticationConverter`.
- Callback endpoints such as `/login/oauth2/code/{registrationId}` and `/oauth2/authorization/{registrationId}` must fall into the **UI chain**, not be intercepted early by the API chain.
- The API must never accept an **OIDC ID token** in place of an API access token; validate the access token's `aud`/issuer/scopes.
- UI session logout may also require OIDC RP-Initiated Logout or back-channel logout per the IdP contract; this does not revoke bearer access tokens.

**Illustrative** client configuration when `spring-boot-starter-oauth2-client` and an IdP are registered:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          staff:
            provider: staff
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile,email
        provider:
          staff:
            issuer-uri: ${OIDC_ISSUER_URI}
```

This YAML snippet is a **directional replacement for an IdP-backed deployment**, not a drop-in file for the form-login demo expecting all tests to keep passing. You must update dependencies, the UI chain, tests, and authority mapping accordingly. Never put `OIDC_CLIENT_SECRET` in JavaScript/SPAs, logs, or source control. Public clients require Authorization Code + PKCE, never an embedded browser client secret.

## 13. CSRF, CORS, Cookies, and Headers: Do Not Confuse Their Roles

### 13.1. CSRF

CSRF protects requests when a browser automatically attaches a session cookie or similar credential. The UI chain keeps CSRF enabled, so `POST /ui/change` requires a valid token. For server-rendered apps, embed the CSRF token into forms using Spring MVC / template engine integration. A `403` on a tokenless POST **does not prove** the wrong role was checked.

A pure stateless API using explicit bearer headers can disable CSRF within the API chain alone. If the API switches to cookies or browser-auto-sent credentials, **re-evaluate**; never copy `csrf.disable()` into the web chain.

### 13.2. CORS

CORS controls which browser JavaScript origins may read responses and issue certain cross-origin requests; it is **not authentication or authorization**. CORS will not make an invalidly signed token valid. If a cross-origin SPA calls the API, configure allowed origins/methods/headers for trusted clients and test `OPTIONS` preflight; never leave `*` wide open when using credentials. The demo omits CORS because learning requests use same-origin/MockMvc.

### 13.3. Cookies and SameSite

`JSESSIONID` is the **web session** credential and needs `HttpOnly`, `Secure` over HTTPS, and `SameSite` aligned with the real login flow. Depending on path/domain, the cookie may still be sent to `/api/**`, yet the API chain must **never authenticate from the session**. If stronger isolation is needed per threat model, consider separate origins/subdomains or deployments while still guarding reverse proxies, path rewrites, and cookie scopes.

### 13.4. CSP and UI Protection

Session-based UIs also need XSS protection, output encoding, an appropriate Content Security Policy, clickjacking defense, and session fixation protection. Same-origin XSS can execute user actions even with CSRF tokens present; CSRF does not replace XSS defense. Bearer tokens stored in JS are also exposed to XSS risks, so token storage and frontend architecture must be carefully designed.

## 14. Common Configuration Mistakes

**Mistake 1 — Catch-all at @Order(1).** `/**` intercepts API routes before `/api/**`, yielding 302 login redirects instead of 401 bearer challenges. Put the API chain first and fallback second.

**Mistake 2 — Using only requestMatchers("/api/**") without securityMatcher.** Rules only inspect URLs within one chain containing both formLogin and resource server; filters can still run on unintended requests. Separate chains properly with `securityMatcher`.

**Mistake 3 — Creating chains for UI and API without a fallback.** New endpoints matching neither chain may remain unprotected. Use a `/**` fallback with `denyAll` for unintended URLs.

**Mistake 4 — Letting the API use HttpSession.** A UI cookie can accidentally grant identity on the API in violation of the contract. Use `STATELESS` and a repository that neither loads nor saves context in the API, backed by a "session-only → 401" test.

**Mistake 5 — Disabling CSRF application-wide.** Cookie-authenticated UI POSTs lose protection. Disable only in a pure bearer API if the threat model justifies it, while keeping web CSRF enabled.

**Mistake 6 — Removing sessions from the UI for "everything stateless".** Form login can no longer persist state between requests, causing login loops. The UI needs `IF_REQUIRED` and proper session context persistence.

**Mistake 7 — Resource Server returning 302 login.** Chains/entry points are mixed; the API should return 401 when unauthenticated via bearer.

**Mistake 8 — Treating JWT scopes as roles.** `hasRole('api.read')` normally expects `ROLE_api.read`; the default converter produces `SCOPE_api.read`. Use `hasAuthority('SCOPE_api.read')` or a consistent mapping contract.

**Mistake 9 — Testing the API with @WithMockUser and assuming JWTs are verified.** That annotation bypasses the JWT decoder. Test converters/filters and signed-token validation separately.

**Mistake 10 — Using the UI login's OIDC ID token as an API access token.** Validate token type, audience, issuer, and scopes per the Resource Server contract.

**Mistake 11 — Missing the method-security proxy.** Forgetting `@EnableMethodSecurity` or calling a service with `new` prevents `@PreAuthorize` from running. Inject the Spring bean and write deny tests.

**Mistake 12 — API POST without CSRF still gets 403.** This may come from missing `SCOPE_api.write`, an invalid JWT, or hitting the wrong chain. Identify which layer returned 403 before changing CSRF policy.

**Mistake 13 — Assuming UI logout expires all JWTs.** `/logout` only manages the demo's web session, not stateless tokens. Implement TTL/revocation separately.

**Mistake 14 — Putting the JWT private key on the Resource Server.** Resource Servers verify asymmetric JWTs via public JWKS; they never need the IdP's signing private key.

**Mistake 15 — Missing an audience validator.** A validly signed token issued for another API could be accepted erroneously. Check `aud` for your specific API.

**Mistake 16 — Ignoring CORS/preflight for cross-origin SPAs.** HTTP OPTIONS may get 401 from the API chain, but never disable authentication on all methods to fix it. Configure CORS in scope while keeping bearer authorization on real requests.

**Mistake 17 — Overlooking proxy-rewritten paths.** Gateways adding or stripping an `/api` prefix can alter chain selection. Test the exact path/servletPath actually seen by the Spring app.

**Mistake 18 — Reusing one JWT/SecurityContext across requests after logout.** Self-contained issued JWTs can stay valid; web session logout and JWT revocation have separate scopes.

## 15. Pre-Deployment Acceptance Matrix

| Test Case | Input | Expected Outcome |
|---|---|---|
| UI anonymous | GET `/ui/me` without session | 302 redirect to login |
| UI login | POST `/login` valid credentials + CSRF | 302 and session created |
| UI authenticated | GET `/ui/me` with session | 200 |
| UI POST missing CSRF | POST `/ui/change` with session, no token | 403 |
| UI POST with CSRF | Valid session + CSRF | 200 |
| UI logout missing CSRF | POST `/logout` with session | 403 |
| API anonymous | GET `/api/me` without bearer | 401, **no** redirect |
| API with UI session, no bearer | GET `/api/me` with JSESSIONID | 401 |
| API valid bearer + read scope | GET `/api/me` | 200 |
| API bearer missing read scope | GET `/api/me` | 403 |
| API bearer + write scope | POST `/api/actions`, no session | 200 in bearer-only API model |
| API bearer missing write scope | POST `/api/actions` | 403 |
| Bearer token sent to UI without session | GET `/ui/me` | 302 login |
| JWT wrong issuer/audience | Validly signed token with wrong claims | 401 in real signed-token test |
| JWT bad signature/expired | Invalid Bearer token | 401 |
| Undeclared URL | GET `/internal/unlisted` | Denied per fallback policy |
| Permission change | Old JWT/session after revocation | Enforced per defined TTL/revocation SLA |
| Multi-tenant system | Valid scope token for wrong tenant resource | 403 per business authorization |

MockMvc cases using `@MockBean JwtDecoder` prove routing/authorization, whereas JWT signature cases require a real decoder and test keys. Do not treat a green test suite as proof of SSL, proxy behavior, or token revocation outside what was actually executed.

### Final Checklist

- [ ] API chain has `@Order(1)`, `securityMatcher("/api/**")`, and Bearer JWT.
- [ ] UI fallback has `@Order(2)`, `securityMatcher("/**")`, form login/session, and CSRF.
- [ ] No route falls outside all security chains; fallback is deny-by-default.
- [ ] API uses `STATELESS` and neither reads nor writes `SecurityContext` in web `HttpSession`.
- [ ] Sending a web cookie to the API **does not** authenticate the API request.
- [ ] CSRF is disabled for the API only if it truly accepts no browser-auto credentials.
- [ ] UI POSTs and logout require a valid CSRF token.
- [ ] API returns 401 on missing/invalid bearer; anonymous UI requests redirect to the proper login entry point.
- [ ] `SCOPE_` is checked with `hasAuthority`; `ROLE_` is used consistently for UI roles.
- [ ] `@EnableMethodSecurity` is active on Spring-managed business beans.
- [ ] JWT verifies signature, issuer, audience, and timestamps; tests include invalid signatures with a real decoder.
- [ ] Client secrets, signing keys, session cookies, and credentials are environment-managed and never logged.
- [ ] Allow/deny tests exist for UI, API, CSRF, chain ordering, and session isolation.
- [ ] Team understands web session logout **does not revoke** access JWTs.
- [ ] CORS, headers, cookie flags, TLS, proxy rewrites, IdP integration, and revocation are tested in the appropriate environments.

## 16. Conclusion

Two `SecurityFilterChain`s solve the challenge of **applying the right security mechanism per request type**. The `/api/**` chain evaluates first, enforces **stateless Bearer JWT** authentication without web sessions, and disables CSRF only when justified by the threat model. The `/**` fallback chain handles **session-backed form-login UI**, protects state-changing requests with CSRF, and provides browser login redirects.

The strongest proof is not just **UI login works** and **API bearer returns 200**, but also that **a UI session cannot call the API**, **a Bearer JWT cannot act as a browser login**, **unauthenticated API calls are not redirected**, **UI POSTs without CSRF are blocked**, and **wrong scopes/roles are denied**. Once verified through both MockMvc and appropriate signed-token integration tests, the hybrid session + Resource Server architecture maintains clear boundaries and safe operations.
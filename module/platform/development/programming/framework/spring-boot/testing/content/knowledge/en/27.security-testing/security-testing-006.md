# JWT, Opaque Token, OAuth2 Login, and Their Corresponding Simulation Tools

## 1. The security testing problem

A Spring Boot application may simultaneously expose REST APIs protected by Bearer access tokens and a web UI protected by OAuth 2.0 Login. On the surface, every request appears to have an “authenticated user”, yet **the mechanism, `Authentication` object, scope mapping, and trust boundary** differ significantly:

- **JWT Resource Server**: receives `Authorization: Bearer ...`, decodes/validates the JWT (signature, expiration, issuer, audience if configured), and converts claims/scopes into a `JwtAuthenticationToken` and authorities.
- **Opaque Token Resource Server**: receives an opaque Bearer string; invokes `OpaqueTokenIntrospector` to verify the token and retrieve attributes/authorities. Typically no local JWT signature check occurs in this branch.
- **OAuth2 Login**: the application acts as an OAuth2 client, redirects the browser to an Identity Provider, receives an authorization code, exchanges the code for tokens, and establishes a login session (`OAuth2AuthenticationToken`, `OAuth2User`); with OpenID Connect, there is an `OidcUser` and ID token.

Writing one test using `@WithMockUser` for all scenarios is the **wrong level of abstraction** when real controllers expect `Jwt`, `BearerTokenAuthentication`, `OAuth2User`, or `OidcUser`. `@WithMockUser` creates a `UsernamePasswordAuthenticationToken` and a fake Spring Security `User` principal; it does not produce OAuth2 authentication types automatically.

This lesson belongs to the **Security** group and directly addresses **“JWT, opaque token, OAuth2 Login, and their corresponding simulation tools”**. We learn two distinct test tiers:

1. **Mocking `SecurityContext`**: use `jwt()`, `opaqueToken()`, `oauth2Login()`, or `oidcLogin()` from `spring-security-test` to test authorization, controllers, and principal mapping **without actually verifying tokens or authorization codes**.
2. **Traversing the authentication filter**: send an `Authorization: Bearer ...` header to MockMvc, using Mockito `@MockBean JwtDecoder` or `@MockBean OpaqueTokenIntrospector` to verify the filter calls the decoder/introspector and handles success/failure. Even this is not cryptographic validation or a live Identity Provider call.

### Objectives

After this lesson, you will be able to:

- Choose the right testing tool for JWT, opaque tokens, OAuth2 Login, and OIDC Login.
- Distinguish `Authentication`, principal, `GrantedAuthority`, claims, attributes, scopes, roles, and token types.
- Write tests with `MockMvc`, `jwt()`, `opaqueToken()`, `oauth2Login()`, and `oidcLogin()`.
- Distinguish unauthenticated requests (401/redirect), authenticated requests lacking scopes (403), and valid requests (200).
- Simulate tokens with `sub`, `scope`, and authority `SCOPE_reports.read`.
- Use Spring Boot 3.3's `@MockBean` to replace `JwtDecoder`/`OpaqueTokenIntrospector` in a test application context.
- Keep the real `SecurityFilterChain`, route JWT/opaque/login via `securityMatcher`, and test the right filters.
- Understand mock boundaries: `jwt()` does not check signatures/`exp`/`iss`/`aud`, and `oauth2Login()` does not perform OAuth2 authorization-code exchange.
- Select WireMock/Testcontainers/IdP sandbox integration tests when you need to verify what mocks cannot protect.

**Illustrative versions:** Java 17+, Spring Boot **3.3.5**, and Spring Security **6.3.x** managed by Boot dependency management. Annotations/imports in Boot 4/Spring Security 7 may differ; do not treat the example versions as the latest releases.

## 2. Tool selection table by mechanism

| Scenario | Expected Authentication/principal | Corresponding test tool | Limitation |
| --- | --- | --- | --- |
| General username/roles, OAuth2-independent | `UsernamePasswordAuthenticationToken`, `UserDetails` | `@WithMockUser` or `user()` | Does not create JWT/OAuth2 principals |
| JWT Resource Server | `JwtAuthenticationToken` / `Jwt` | `jwt()` | Skips decoding/signature/claim validation |
| JWT through Bearer filter | `JwtAuthenticationToken` | Mock `JwtDecoder` + Bearer header | Tests filter wiring, not real JWK verification |
| Opaque Resource Server | `BearerTokenAuthentication` / `OAuth2AuthenticatedPrincipal` | `opaqueToken()` | Skips introspection endpoint |
| Opaque through Bearer filter | `BearerTokenAuthentication` | Mock `OpaqueTokenIntrospector` + Bearer | Tests filter/introspection collaboration |
| OAuth2 Login (non-OIDC) | `OAuth2AuthenticationToken` / `OAuth2User` | `oauth2Login()` | Does not execute redirect/code/token exchange |
| OpenID Connect Login | `OAuth2AuthenticationToken` / `OidcUser` | `oidcLogin()` | Does not validate signature/nonce/ID token itself |
| Any manually constructed Authentication | Depends on instance | `authentication(authentication)` | Very flexible, yet easy to bypass the layer you meant to test |
| Real provider discovery, JWKS, introspection, redirects | HTTP/TLS/OAuth2 protocol | Local fake IdP, WireMock, sandbox integration | Slower, requires lifecycle/secrets |

**Both belong to OAuth 2.0, yet OAuth2 Login is not Resource Server.** `oauth2Login()` simulates a user logged in via browser session; `jwt()` and `opaqueToken()` simulate bearer authentication against an API. Never use `oauth2Login()` in place of a JWT Resource Server test merely because both may carry scopes.

## 3. How a JWT request travels through the application

```text
HTTP GET /api/jwt/report
Authorization: Bearer eyJ...
         |
BearerTokenAuthenticationFilter
         |
JwtAuthenticationProvider
         |
JwtDecoder.decode(token)
    - signature/JWK (real configuration)
    - exp, nbf, iss, aud (matching validators)
         |
JwtAuthenticationToken
    principal = Jwt
    authorities = SCOPE_...
         |
AuthorizationFilter checks hasAuthority(...)
         |
Controller @AuthenticationPrincipal Jwt
```

In a `.with(jwt())` test, we **inject an equivalent authentication result** into the request context to test authorization and the controller. `JwtDecoder.decode` **does not run** unless a Bearer header is sent into the filter. Thus a passing `jwt()` test cannot prove a token was signed properly by the IdP, is unexpired, or has a valid issuer.

A JWT can carry claims like `sub` (subject), `iss` (issuer), `aud` (audience), `exp` (expiry), `nbf`, and `scope`/`scp`. By default, Spring Security converts scopes into authorities prefixed with `SCOPE_`, e.g., claim `scope: "reports.read"` becomes `SCOPE_reports.read`. Mapping can be customized with a converter; if production has a custom converter, test the real converter at an appropriate layer.

### Do not confuse JWT payload with authority

A test containing:

```java
.with(jwt().jwt(jwt ->
    jwt.subject("alice")
       .claim("scope", "reports.read")))
```

simulates a JWT with `sub` and `scope`; the test utility can derive `SCOPE_reports.read`. Another test:

```java
.with(jwt().authorities(
    new SimpleGrantedAuthority("SCOPE_reports.read")))
```

specifies authorities **directly**, which is handy when focusing on authorization, yet can bypass a custom claims-to-authorities converter. When specifically testing a claim-to-scope converter, do not just hardcode authorities and claim the converter was tested.

## 4. How an opaque token travels

```text
HTTP GET /api/opaque/report
Authorization: Bearer opaque-string
         |
BearerTokenAuthenticationFilter
         |
OpaqueTokenAuthenticationProvider
         |
OpaqueTokenIntrospector.introspect(token)
    -> OAuth2AuthenticatedPrincipal
    -> attributes (sub, scope, ...)
    -> granted authorities
         |
BearerTokenAuthentication
         |
AuthorizationFilter
         |
Controller @AuthenticationPrincipal OAuth2AuthenticatedPrincipal
```

An opaque token need not be in JWT format and does not carry self-trusted claims on the resource server. The resource server typically queries the authorization server's **introspection endpoint** (RFC 7662), checks the active response, and retrieves additional attributes. An `opaqueToken()` test places a pre-built `BearerTokenAuthentication` in `SecurityContext` without opening HTTP to an introspection server or checking `active=false` / revocation.

Even if an opaque token string happens to look like a JWT, **the configured verification mechanism is what decides**. A resource server can introspect a token that happens to have JWT structure; never classify the flow solely by whether the token string contains dots.

## 5. OAuth2 Login and OIDC Login differ from Bearer Resource Server

For browser login:

```text
Browser GET /web/profile
       |
Spring Security has no user yet
       |
Redirect /oauth2/authorization/test-idp
       |
Authorization Server login/consent
       |
Redirect /login/oauth2/code/test-idp?code=...&state=...
       |
Application exchanges code and fetches user info / ID token
       |
Session SecurityContext holds OAuth2AuthenticationToken
       |
Controller @AuthenticationPrincipal OAuth2User or OidcUser
```

`SecurityMockMvcRequestPostProcessors.oauth2Login()` **skips the redirect/code-exchange flow** and attaches an authenticated OAuth2 user to the MockMvc request. It fits testing controllers that display user attributes and authorization once **already logged in**.

`oidcLogin()` works similarly, except the principal is `OidcUser` with an `OidcIdToken`; suitable when code calls `user.getIdToken()` or `user.getSubject()`.

**Access tokens** are for calling Resource Servers, whereas **ID tokens** in OIDC prove the login event to the client. Never substitute an ID token for a JWT access token in unit tests or production just because both can be JWTs.

## 6. Expected HTTP statuses

| Request | REST JWT/opaque | Web OAuth2 Login |
| --- | --- | --- |
| Unauthenticated | Usually 401 with Bearer challenge | Usually 302 redirect to login/authorization endpoint |
| Principal present, missing permission | 403 Forbidden | 403 if authorization rule requires specific permission |
| Valid principal and sufficient authority | 200 (depends on controller) | 200 (depends on controller) |
| Bearer token fails signature/introspection | 401 in filter-authentication path | Not a login-code flow |
| Mock `jwt()` token with fake expired claim | Can still be 200 if authority matches | Unrelated |

**Do not force every anonymous request to return 401.** On a web chain using `oauth2Login`, unauthenticated browsers typically receive a redirect. On a stateless Resource Server, unauthenticated requests typically return 401; authenticated requests lacking `SCOPE_...` return 403. Statuses can differ with custom `AuthenticationEntryPoint`, `AccessDeniedHandler`, or gateway configurations.

## 7. Demonstration project: three security chains and one MockMvc test suite

To exercise each tool properly, we build a Spring Boot MVC app with three independent branches. Each chain applies strictly to its own path:

- `/api/jwt/**`: JWT Resource Server, requires `SCOPE_reports.read`.
- `/api/opaque/**`: Opaque Resource Server, also requires `SCOPE_reports.read`.
- `/web/**`: OAuth2 Login/OIDC Login, requires an authenticated user.
- Other paths are denied by a fallback chain; never let “outside any matcher” turn into an unintended public route.

Directory tree:

```text
security-auth-modes/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/security/
│   ├── SecurityModesApplication.java
│   ├── SecurityModesController.java
│   └── SecurityModesConfiguration.java
└── src/test/java/com/example/security/
    └── SecurityModesMvcTest.java
```

In tests, `JwtDecoder` and `OpaqueTokenIntrospector` are Mockito mocks, and a fake `ClientRegistrationRepository` provides dummy URLs/credentials solely to build the OAuth2 Login filter. **No real Identity Provider is contacted.** The app is only intended to run tests with test beans; to run `bootRun` outside tests, you must configure a real decoder/introspector/client registration for your environment.

## 8. Gradle dependencies

### settings.gradle

```groovy
rootProject.name = 'security-auth-modes'
```

### build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

### Role of dependencies

- `spring-boot-starter-security`: `SecurityFilterChain`, filters, authorization.
- `spring-boot-starter-oauth2-resource-server`: JWT/opaque resource server support; JWT verification also requires the JOSE module brought in by the starter.
- `spring-boot-starter-oauth2-client`: OAuth2 Login and `ClientRegistration`.
- `spring-security-test`: `jwt()`, `opaqueToken()`, `oauth2Login()`, `oidcLogin()`, `@WithMockUser`, and MockMvc integration.
- `spring-boot-starter-test`: JUnit Jupiter, Mockito, MockMvc test support.
- `junit-platform-launcher`: launches the JUnit Platform in Gradle when needed.

Never mix a much newer `spring-security-test` version with Boot 3.3's `spring-security-*` runtime. Use Boot's dependency management to avoid class/method version mismatches.

## 9. Application root

`src/main/java/com/example/security/SecurityModesApplication.java`:

```java
package com.example.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityModesApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityModesApplication.class, args);
    }
}
```

There is no `@EnableMethodSecurity` in the demo because authorization policies live right in the filter chains. If a real project uses `@PreAuthorize`, enable method security and test method invocations at the appropriate layer.

## 10. Controller demonstrating four principal types

`src/main/java/com/example/security/SecurityModesController.java`:

```java
package com.example.security;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SecurityModesController {

    @GetMapping("/api/jwt/report")
    public Map<String, String> jwt(
            @AuthenticationPrincipal Jwt principal) {
        return Map.of(
                "mode", "jwt",
                "subject", principal.getSubject());
    }

    @GetMapping("/api/opaque/report")
    public Map<String, String> opaque(
            @AuthenticationPrincipal
            OAuth2AuthenticatedPrincipal principal) {
        return Map.of(
                "mode", "opaque",
                "subject",
                String.valueOf(principal.getAttribute("sub")));
    }

    @GetMapping("/web/profile")
    public Map<String, String> oauth2(
            @AuthenticationPrincipal OAuth2User user) {
        return Map.of(
                "mode", "login",
                "subject", String.valueOf(user.getAttribute("sub")));
    }

    @GetMapping("/web/oidc")
    public Map<String, String> oidc(
            @AuthenticationPrincipal OidcUser user) {
        return Map.of(
                "mode", "oidc",
                "subject", user.getSubject());
    }
}
```

Four endpoints intentionally expect the **exact principal type**. Passing `@WithMockUser` into `/api/jwt/report` does not give Spring a `Jwt` from `UserDetails`; the method may not receive the expected principal. That is why one annotation cannot cover every flow.

Responses return only non-sensitive fields `subject` and `mode`. In real applications, never return raw JWT claims, ID tokens, access tokens, or secrets in API responses for “debugging”.

## 11. SecurityFilterChain separating JWT, opaque, and login

`src/main/java/com/example/security/SecurityModesConfiguration.java`:

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class SecurityModesConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain jwtApi(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/jwt/**")
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/api/jwt/report")
                        .hasAuthority("SCOPE_reports.read")
                        .anyRequest().denyAll())
                .oauth2ResourceServer(resourceServer ->
                        resourceServer.jwt(withDefaults()))
                .sessionManagement(sessions ->
                        sessions.sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                .csrf(AbstractHttpConfigurer::disable)
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain opaqueApi(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/opaque/**")
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/api/opaque/report")
                        .hasAuthority("SCOPE_reports.read")
                        .anyRequest().denyAll())
                .oauth2ResourceServer(resourceServer ->
                        resourceServer.opaqueToken(withDefaults()))
                .sessionManagement(sessions ->
                        sessions.sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                .csrf(AbstractHttpConfigurer::disable)
                .build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain browserLogin(HttpSecurity http)
            throws Exception {
        return http
                .securityMatcher(
                        "/web/**", "/login/**", "/oauth2/**")
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/web/**")
                        .authenticated()
                        .anyRequest().permitAll())
                .oauth2Login(withDefaults())
                .build();
    }

    @Bean
    @Order(4)
    SecurityFilterChain otherRequests(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .anyRequest().denyAll())
                .build();
    }
}
```

### Configuration analysis

1. `@Order` sets chain selection priority; Spring Security uses the **first matching chain**, rather than running every chain sequentially on one request.
2. `jwtApi` applies only to `/api/jwt/**`, installs the JWT authentication filter, and requires `SCOPE_reports.read`.
3. `opaqueApi` applies only to `/api/opaque/**`, installs the opaque-token filter, and requires the same scope.
4. `browserLogin` applies only to web/login/authorization paths; enables `oauth2Login` and keeps the login flow's default session/CSRF settings.
5. `otherRequests` blocks remaining paths. There is no intent to expose arbitrary endpoints in the demo.
6. `csrf(AbstractHttpConfigurer::disable)` is applied strictly to the two **stateless bearer API chains**. Never disable CSRF app-wide just to make GET tests easier.

**Note:** supporting both JWT and opaque tokens in one application should not be stacked arbitrarily inside one chain; the demo separates them by path matchers so learners see clearly which filter executes. A real system might distinguish by host, tenant, or service boundary, requiring explicit security design and tests for every matcher.

### Why mock decoder/introspector even when using jwt()/opaqueToken()?

When constructing a `SecurityFilterChain` with `oauth2ResourceServer().jwt()`, the filter requires a valid `JwtDecoder` bean to build the provider. Likewise, opaque needs an `OpaqueTokenIntrospector`. The test creates both mocks as beans so the Spring context can start **without contacting an IdP**. Tests using `jwt()` and `opaqueToken()` do not invoke these mocks, while tests sending real Bearer headers stub and verify interactions.

### @SpringBootTest instead of @WebMvcTest?

The example suite uses `@SpringBootTest + @AutoConfigureMockMvc` to keep the full **production `SecurityFilterChain`** and all four real endpoints in one context. `@WebMvcTest` works well for testing a small controller slice, though it requires intentionally importing the chain, decoder, introspector, and `ClientRegistrationRepository`. Full context is used here to run all three auth flows side by side, not because every security test must run full context.

## 12. Complete MockMvc test suite

`src/test/java/com/example/security/SecurityModesMvcTest.java`:

```java
package com.example.security;

import java.util.Map;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.opaqueToken;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.oauth2Login;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityModesMvcTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ClientRegistrationRepository registrations;

    @MockBean
    JwtDecoder jwtDecoder;

    @MockBean
    OpaqueTokenIntrospector introspector;

    @TestConfiguration(proxyBeanMethods = false)
    static class FakeIdentityProvider {

        @Bean
        ClientRegistrationRepository fakeRegistrations() {
            ClientRegistration fake = ClientRegistration
                    .withRegistrationId("test-idp")
                    .clientId("fake-client")
                    .clientSecret("not-a-real-secret")
                    .authorizationGrantType(
                            AuthorizationGrantType.AUTHORIZATION_CODE)
                    .redirectUri(
                            "{baseUrl}/login/oauth2/code/{registrationId}")
                    .authorizationUri(
                            "https://idp.example.invalid/authorize")
                    .tokenUri(
                            "https://idp.example.invalid/token")
                    .userInfoUri(
                            "https://idp.example.invalid/userinfo")
                    .userNameAttributeName("sub")
                    .scope("profile")
                    .clientName("Fake IdP")
                    .build();
            return new InMemoryClientRegistrationRepository(fake);
        }
    }

    @Test
    void jwtPostProcessorProvidesJwtPrincipalAndScope()
            throws Exception {
        mvc.perform(get("/api/jwt/report")
                .with(jwt().jwt(builder -> builder
                        .subject("alice")
                        .claim("scope", "reports.read"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.mode").value("jwt"))
                .andExpect(jsonPath("$.subject").value("alice"));
    }

    @Test
    void jwtPrincipalWithoutRequiredScopeIsForbidden()
            throws Exception {
        mvc.perform(get("/api/jwt/report")
                .with(jwt().jwt(builder -> builder
                        .subject("alice")
                        .claim("scope", "profile"))))
                .andExpect(status().isForbidden());
    }

    @Test
    void missingJwtAuthenticationIsUnauthorized()
            throws Exception {
        mvc.perform(get("/api/jwt/report"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void opaquePostProcessorProvidesPrincipalAndAuthorities()
            throws Exception {
        mvc.perform(get("/api/opaque/report")
                .with(opaqueToken()
                        .attributes(attributes ->
                                attributes.put("sub", "bob"))
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_reports.read"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.mode").value("opaque"))
                .andExpect(jsonPath("$.subject").value("bob"));
    }

    @Test
    void opaquePrincipalWithoutScopeIsForbidden()
            throws Exception {
        mvc.perform(get("/api/opaque/report")
                .with(opaqueToken()
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_profile"))))
                .andExpect(status().isForbidden());
    }

    @Test
    void missingOpaqueAuthenticationIsUnauthorized()
            throws Exception {
        mvc.perform(get("/api/opaque/report"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void oauth2LoginProvidesOAuth2UserAttributes()
            throws Exception {
        ClientRegistration registration = registrations
                .findByRegistrationId("test-idp");

        mvc.perform(get("/web/profile")
                .with(oauth2Login()
                        .clientRegistration(registration)
                        .attributes(attributes ->
                                attributes.put("sub", "carol"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.mode").value("login"))
                .andExpect(jsonPath("$.subject").value("carol"));
    }

    @Test
    void anonymousBrowserRequestRedirectsToLogin()
            throws Exception {
        mvc.perform(get("/web/profile"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void oidcLoginProvidesIdTokenPrincipal()
            throws Exception {
        mvc.perform(get("/web/oidc")
                .with(oidcLogin()
                        .idToken(token -> token.subject("dana"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.mode").value("oidc"))
                .andExpect(jsonPath("$.subject").value("dana"));
    }

    @Test
    void realBearerJwtHeaderCallsJwtDecoder()
            throws Exception {
        Jwt decoded = Jwt.withTokenValue("valid-test-jwt")
                .header("alg", "RS256")
                .subject("decoded-alice")
                .claim("scope", "reports.read")
                .build();

        given(jwtDecoder.decode("valid-test-jwt"))
                .willReturn(decoded);

        mvc.perform(get("/api/jwt/report")
                .header(
                        HttpHeaders.AUTHORIZATION,
                        "Bearer valid-test-jwt"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.subject")
                        .value("decoded-alice"));

        verify(jwtDecoder).decode("valid-test-jwt");
    }

    @Test
    void badJwtHeaderIsRejectedByAuthenticationFilter()
            throws Exception {
        given(jwtDecoder.decode("bad-jwt"))
                .willThrow(
                        new BadJwtException("invalid test JWT"));

        mvc.perform(get("/api/jwt/report")
                .header(
                        HttpHeaders.AUTHORIZATION,
                        "Bearer bad-jwt"))
                .andExpect(status().isUnauthorized());

        verify(jwtDecoder).decode("bad-jwt");
    }

    @Test
    void realOpaqueBearerHeaderCallsIntrospector()
            throws Exception {
        OAuth2AuthenticatedPrincipal principal =
                new DefaultOAuth2AuthenticatedPrincipal(
                        "introspected-bob",
                        Map.of("sub", "introspected-bob"),
                        AuthorityUtils.createAuthorityList(
                                "SCOPE_reports.read"));

        given(introspector.introspect("valid-opaque"))
                .willReturn(principal);

        mvc.perform(get("/api/opaque/report")
                .header(
                        HttpHeaders.AUTHORIZATION,
                        "Bearer valid-opaque"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.subject")
                        .value("introspected-bob"));

        verify(introspector).introspect("valid-opaque");
    }

    @Test
    void introspectedOpaqueTokenWithoutScopeIsForbidden()
            throws Exception {
        OAuth2AuthenticatedPrincipal principal =
                new DefaultOAuth2AuthenticatedPrincipal(
                        "limited-bob",
                        Map.of("sub", "limited-bob"),
                        AuthorityUtils.createAuthorityList(
                                "SCOPE_profile"));

        given(introspector.introspect("limited-opaque"))
                .willReturn(principal);

        mvc.perform(get("/api/opaque/report")
                .header(
                        HttpHeaders.AUTHORIZATION,
                        "Bearer limited-opaque"))
                .andExpect(status().isForbidden());

        verify(introspector).introspect("limited-opaque");
    }
}
```

**There are 13 `@Test` methods** in `SecurityModesMvcTest`, grouped into 4 JWT cases (3 injected + 1 valid decoder + 1 invalid decoder: actually 5), 4 opaque cases (3 injected + 2 introspection: actually 4? see group table below), 3 login/OIDC cases, and 1 anonymous redirect. No real Identity Provider is required to run these requests since only fake registration and mocks are used.

**Important when reading the source:** the test suite exercises two very different paths:

- `get(...).with(jwt())`/`with(opaqueToken())`/`with(oauth2Login())` builds the authentication context before the authorization filter runs. **No** Bearer header needs decoding.
- `get(...).header(AUTHORIZATION, "Bearer ...")` passes through the resource-server filter; the mocked `JwtDecoder`/`OpaqueTokenIntrospector` is invoked. This tests the wiring of the actual filter chain, though still without cryptographic verification or introspection HTTP calls.

### Test-only registration and mock infrastructure

The nested `@TestConfiguration` class supplies a `ClientRegistrationRepository` with a non-routable URL (`example.invalid`) and dummy credentials. It gives `oauth2Login()` valid OAuth2 client settings **without contacting an IdP**. In production, `ClientRegistration` must load from environment-appropriate provider config and secrets.

Spring Boot 3.3's `@MockBean` replaces the decoder/introspector beans in the test context with Mockito mocks. It prevents application startup from depending on JWKS or introspection endpoints. Never place these mock beans into `src/main/java` or production profiles. Newer Boot versions may use a different annotation for Mockito test beans, so always verify against your active version.

## 13. Mapping test counts and behaviors

| Group | Test methods | Expected outcome |
| --- | --- | --- |
| JWT postprocessor | `jwtPostProcessorProvidesJwtPrincipalAndScope` | 200 + subject alice |
| JWT negative scope | `jwtPrincipalWithoutRequiredScopeIsForbidden` | 403 |
| JWT anonymous | `missingJwtAuthenticationIsUnauthorized` | 401 |
| Opaque postprocessor | `opaquePostProcessorProvidesPrincipalAndAuthorities` | 200 + subject bob |
| Opaque negative scope | `opaquePrincipalWithoutScopeIsForbidden` | 403 |
| Opaque anonymous | `missingOpaqueAuthenticationIsUnauthorized` | 401 |
| OAuth2 Login | `oauth2LoginProvidesOAuth2UserAttributes` | 200 + subject carol |
| Browser anonymous | `anonymousBrowserRequestRedirectsToLogin` | 3xx redirect |
| OIDC Login | `oidcLoginProvidesIdTokenPrincipal` | 200 + subject dana |
| Bearer JWT decoder mock | `realBearerJwtHeaderCallsJwtDecoder` | 200, decoder called |
| Bearer JWT error | `badJwtHeaderIsRejectedByAuthenticationFilter` | 401 |
| Bearer opaque introspector mock | `realOpaqueBearerHeaderCallsIntrospector` | 200, introspector called |
| Bearer opaque lacking permission | `introspectedOpaqueTokenWithoutScopeIsForbidden` | 403 |

Total is **13** methods (5 JWT, 5 opaque, 3 login/OIDC counting the anonymous browser case). These are **expectations derived from source**, not confirmation that Gradle ran and passed.

### Explaining 401 and 403

On REST chains, absent or invalid credentials fail to establish an authenticated principal, so `AuthenticationEntryPoint` typically returns **401**. When an authenticated principal exists yet lacks `SCOPE_reports.read`, `AuthorizationFilter` denies with **403**.

This matters for security regressions: an API returning 200 for a principal lacking a scope is an authorization flaw; an API returning 403 for an unauthenticated request may violate expectations, though exact statuses depend on the application's own security policy.

### Explaining OAuth2 Login redirects

On `/web/profile`, the chain enables `oauth2Login` rather than JWT bearer authentication. Anonymous requests typically trigger a redirect to the login/authorization flow. Because the demo route may pick a login page per client registration, the test asserts `is3xxRedirection()` generally rather than hardcoding a redirect URI when protecting a specific path is not required.

## 14. jwt(): what is tested and what is skipped?

`jwt()` from Spring Security Test builds a mock `Jwt` and attaches it to the test request under a `JwtAuthenticationToken`. If you only want to test scope authorization:

```java
mvc.perform(get("/api/jwt/report")
        .with(jwt().authorities(
                new SimpleGrantedAuthority(
                        "SCOPE_reports.read"))))
        .andExpect(status().isOk());
```

This snippet is not standalone since it needs `MockMvc mvc` and the project's config. It works for verifying `hasAuthority` rules, yet **does not invoke `JwtGrantedAuthoritiesConverter` the way a real JWT does** when you override authorities directly.

If you want to test claim mapping at the mock level:

```java
mvc.perform(get("/api/jwt/report")
        .with(jwt().jwt(builder -> builder
                .subject("scope-user")
                .claim("scope", "reports.read"))))
        .andExpect(status().isOk());
```

Spring Security Test supports deriving `SCOPE_...` from scopes. Still, this remains a test authentication postprocessor; it **does not** prove a real `NimbusJwtDecoder` accepts tokens with valid signatures, issuers, and audiences.

### Are exp/iss/aud claims validated?

Do not assume so. You can build a mock JWT with a past `exp`, wrong `iss`, or missing `aud` and still inject the principal successfully with `jwt()`, because JWT validation was bypassed. Separate:

- **Authorization tests**: `jwt()` with mock claims/authorities to test controllers/rules.
- **Decoder validator tests**: test real `JwtDecoder` with signed test tokens/JWKS and issuer/audience/timestamp validators under an explicit clock/skew policy.
- **IdP integration**: when key rotation, metadata discovery, redirect flows, token issuance, and revocation are needed.

**Never treat `alg=none` from a test JWT builder as proof of a valid production JWT.** Mock defaults are conveniences, not production signing policies.

## 15. Mocking JwtDecoder: when does it matter?

With a real header:

```java
given(jwtDecoder.decode("valid-test-jwt"))
        .willReturn(Jwt.withTokenValue("valid-test-jwt")
                .header("alg", "RS256")
                .subject("decoded-alice")
                .claim("scope", "reports.read")
                .build());

mvc.perform(get("/api/jwt/report")
        .header(
                HttpHeaders.AUTHORIZATION,
                "Bearer valid-test-jwt"))
        .andExpect(status().isOk());

verify(jwtDecoder).decode("valid-test-jwt");
```

This verifies that:

1. `BearerTokenAuthenticationFilter` picks up the Bearer header.
2. The JWT authentication provider calls `JwtDecoder.decode`.
3. Spring turns the returned `Jwt` into an `Authentication`.
4. Standard authority mapping passes the scope rule.
5. The controller receives the corresponding `Jwt` principal.

However, the decoder is a **Mockito stub**; no signature/`kid`/JWKS verification happens here. To test a custom converter, you can return a `Jwt` with specific scopes/claims and assert the security rules, while still keeping separate tests for the real validators.

### JWT errors must use the right exception

`BadJwtException` simulates an invalid JWT inside the decoder. When thrown from `decode`, the provider turns it into an authentication error and the filter typically returns 401. Never throw an arbitrary `RuntimeException` to “simulate an invalid token”: it may be handled as an internal server error instead of invalid credentials.

## 16. opaqueToken(): principal and authorities

`opaqueToken()` builds an authenticated `BearerTokenAuthentication`. It accepts attributes:

```java
.with(opaqueToken()
    .attributes(attributes -> {
        attributes.put("sub", "bob");
        attributes.put("department", "operations");
    })
    .authorities(new SimpleGrantedAuthority(
            "SCOPE_reports.read")))
```

In the controller, `@AuthenticationPrincipal OAuth2AuthenticatedPrincipal` can access the attributes; `Authentication#getAuthorities` governs authorization. With real opaque introspection, scopes are typically returned by the authorization server and converted to `SCOPE_`-prefixed authorities by a converter. Supplying authorities manually in the postprocessor **skips converting scopes from an introspection response**.

**Do not infer that `opaqueToken()` checks `active=true`, expiry, revocation, or introspection client credentials.** It only equips a request with a valid `BearerTokenAuthentication` to test downstream application logic.

## 17. Mocking OpaqueTokenIntrospector: simulating IdP responses

With a real Bearer header:

```java
OAuth2AuthenticatedPrincipal principal =
    new DefaultOAuth2AuthenticatedPrincipal(
        "introspected-bob",
        Map.of("sub", "introspected-bob"),
        AuthorityUtils.createAuthorityList(
            "SCOPE_reports.read"));

given(introspector.introspect("valid-opaque"))
    .willReturn(principal);

mvc.perform(get("/api/opaque/report")
        .header(
            HttpHeaders.AUTHORIZATION,
            "Bearer valid-opaque"))
    .andExpect(status().isOk());

verify(introspector).introspect("valid-opaque");
```

This tests that the resource-server filter **invokes the right introspector bean** and uses the returned `OAuth2AuthenticatedPrincipal`. It does not HTTP POST to an introspection endpoint because it is a mock. When an IdP returns “inactive” in production, the real introspector must reject it; testing that inactive handling requires testing the introspection client against a mock HTTP response containing `active:false` or using an OAuth2 server stub library.

### Risk of an overly broad introspector mock

A Mockito stub like `when(introspect(anyString())).thenReturn(principalAdmin)` turns every string, even bad tokens, into a privileged user. In integration tests, stub **exact tokens** and test negative branches separately. Never mock an introspector to return an admin principal for every request and then conclude security is enforced.

If introspection exceptions have distinct semantics (inactive vs endpoint unavailable), test the mapping per policy; never let introspection failures turn into 200 or silently grant access.

## 18. oauth2Login() and oidcLogin(): when to use which?

When a controller needs `OAuth2User` and attributes from a user-info endpoint, use:

```java
mvc.perform(get("/web/profile")
        .with(oauth2Login()
                .attributes(attrs ->
                        attrs.put("sub", "carol"))))
        .andExpect(status().isOk());
```

When a controller uses OpenID Connect `OidcUser`/`OidcIdToken`:

```java
mvc.perform(get("/web/oidc")
        .with(oidcLogin()
                .idToken(id -> id.subject("dana"))))
        .andExpect(status().isOk());
```

These snippets require `MockMvc` and the project's matching security chains. On the MockMvc request, the test utility inserts the principal into the security context so `@AuthenticationPrincipal` receives it. No real browser redirect to an IdP or authorization code exchange occurs.

### Do OAuth2 Login tests need real or fake registrations?

If code uses `@RegisteredOAuth2AuthorizedClient` or `ClientRegistration`/authorized clients, the test postprocessor can accept `clientRegistration(...)`, and the application context can supply a `ClientRegistrationRepository`. In the example suite, the nested `@TestConfiguration` builds a fake `ClientRegistration` and the test passes it into `oauth2Login()`. Tests do not use production client secrets.

### OIDC ID tokens differ from JWT Resource Server access tokens

`oidcLogin()` sets up an `OidcUser` with an ID token representing login identity. `jwt()` sets up a `JwtAuthenticationToken` with access token claims under resource-server semantics. A controller expecting `@AuthenticationPrincipal OidcUser` should not be tested with `jwt()`, and vice versa. Both may contain a `sub` claim, yet their authentication types and trust boundaries differ.

### OAuth2 Login does not automatically persist sessions across MockMvc requests

`oauth2Login()` gives **one request** a logged-in user. To test session persistence, redirect cookies, or CSRF across multiple requests, preserve `MockHttpSession`/cookies properly or use browser integration tests. Never assume two independent `mvc.perform(...)` calls automatically share a session because the first used `oauth2Login()`.

## 19. @WithMockUser: use properly without overusing

`@WithMockUser(username="alice", roles="ADMIN")` is great for controller/service tests where code only inspects the name, roles, or generic `Authentication`. It builds a `UsernamePasswordAuthenticationToken` with a `UserDetails` principal and authorities like `ROLE_ADMIN`.

However, for code relying on:

- `@AuthenticationPrincipal Jwt`;
- `BearerTokenAuthentication.getTokenAttributes()`;
- `@AuthenticationPrincipal OAuth2User`;
- `@AuthenticationPrincipal OidcUser`;

...`@WithMockUser` does not construct the right object. With `@PreAuthorize("hasAuthority('SCOPE_reports.read')")`, you can use `@WithMockUser(authorities="SCOPE_reports.read")` to test **the authorization expression itself**. Still, that test does not verify resource-server JWT/opaque authentication.

Comparison:

| Annotation/postprocessor | Principal/Auth | Best suited when |
| --- | --- | --- |
| `@WithMockUser` | Spring `User`, `UsernamePasswordAuthenticationToken` | Testing token-independent roles/usernames |
| `user("alice")` | `UserDetails` | Needing username/roles for one MockMvc request |
| `jwt()` | `Jwt`, `JwtAuthenticationToken` | JWT APIs and scope rules |
| `opaqueToken()` | `OAuth2AuthenticatedPrincipal`, `BearerTokenAuthentication` | Introspection APIs and attributes |
| `oauth2Login()` | `OAuth2User`, `OAuth2AuthenticationToken` | OAuth2 browser-login controllers |
| `oidcLogin()` | `OidcUser`, `OAuth2AuthenticationToken` | OpenID Connect user/ID tokens |
| `authentication(token)` | Arbitrary type | Custom `Authentication` or manual setup |

**Never place `@WithMockUser` at class level** and forget requests that must remain anonymous. It can cause negative authentication tests meant to verify missing tokens to run as an authenticated user. For unauthenticated tests, omit user postprocessors and class-level authentication annotations.

## 20. Permission mapping: SCOPE_ and ROLE_ are not the same

Spring Security manages authorities as strings; by convention:

- `hasRole("ADMIN")` usually looks up `ROLE_ADMIN`.
- `hasAuthority("ROLE_ADMIN")` matches the exact string `ROLE_ADMIN`.
- `hasAuthority("SCOPE_reports.read")` matches the OAuth2 authority prefixed with `SCOPE_`.
- JWT/opaque scopes are normally converted from token data into `SCOPE_*` authorities, though converters can be reconfigured.

**Do not turn every scope into an admin role.** Scopes like `reports.read` are delegated permissions granted by the authorization server; internal roles like ADMIN may come from separate policies, claims, or DB records. When mapping external claims to internal roles, verify issuer/tenant, allowlists, and the real authority converter to avoid privilege escalation.

Negative tests `jwtPrincipalWithoutRequiredScopeIsForbidden` and `opaquePrincipalWithoutScopeIsForbidden` are high-value because they prove **authenticated callers missing the required permission cannot access the resource**.

## 21. Request matching and default-deny

With multiple filter chains, subtle bugs often hide in matchers:

```text
/api/jwt/report      -> jwtApi chain
/api/opaque/report   -> opaqueApi chain
/web/profile         -> browserLogin chain
/web/oidc            -> browserLogin chain
/unknown             -> fallback denyAll chain
```

If a security matcher is accidentally written `/api/jwt/*` instead of `/api/jwt/**`, nested API routes may miss the intended filter. Without a fallback chain, requests can slip outside all chains or hit a different default chain; therefore **testing path mismatches and deny-by-default** is essential in real deployments.

**Do not configure both JWT and opaque providers on the same path without a clear disambiguation rule.** For bearer tokens, a filter cannot safely pick a provider merely by checking whether the token has three dot-separated segments when trust policies differ.

## 22. Failure scenarios worth adding tests for

### JWT

- Missing `Authorization` header -> 401.
- Malformed Bearer header -> 401 per entry point and resolver.
- Decoder detects invalid signature/expired/issuer/audience -> 401.
- Decoder returns valid `Jwt` missing scope -> 403.
- Scope present yet tenant ID mismatches resource ownership -> 403 per business policy.
- Varying list/string claim shapes for `scope`/`scp` -> converter test.
- Token expiring right around the current instant -> validator test with clock/skew.
- JWKS rotation/changing `kid` -> integration test with fake JWKS server.

### Opaque token

- Missing Bearer -> 401.
- Introspector returns principal with matching scope -> 200.
- Introspector returns principal missing scope -> 403.
- IdP returns `active:false` -> 401 when the real introspector rejects.
- Introspection endpoint timeout/5xx -> handle per policy, **never fall open to allow access**.
- Token revoked while cached by introspection -> verify TTL/revocation window.
- Introspection client uses wrong secret -> authentication fails without logging secrets.

### OAuth2 Login/OIDC

- Anonymous visits protected page -> redirect.
- After successful login with user attributes -> controller returns right profile.
- Missing email/subject/roles -> valid mapping behavior.
- OIDC ID token has wrong nonce/issuer/audience -> integration validation test.
- Callback state mismatch/CSRF -> reject.
- Session fixation/session expiry/logout -> per policy.
- Multiple client registrations -> picks right provider/redirect URI.
- User has external role not trusted by app -> 403.

Test the scenarios that matter to your real product; you do not need a live IdP for every unit/controller test.

## 23. Security of test fixtures themselves

- Use dummy tokens like `valid-test-jwt` or `valid-opaque`; **never** copy production access tokens into source code.
- Use reserved domains like `idp.example.invalid` for fake `ClientRegistration` entries; never accidentally call external domains.
- Never put production client secrets, refresh tokens, cookies, or `Authorization` headers in logs or snapshots.
- When testing actual JWKS signatures, use test-generated keys/certificates with protected test private keys, never committing production secrets.
- For expired/`nbf` tests, use fixed times or skew-aware clocks; avoid assertions near the exact expiration second that cause flakiness.
- For OAuth2 login redirects, test state/nonce/PKCE at the protocol level where appropriate; never disable them to make tests easier.
- Avoid custom `JwtDecoder` configurations that accept `alg=none` in production; mock JWT defaults are not production tokens.
- Never let `OpaqueTokenIntrospector` grant admin authority by default when a token fails introspection.
- With multi-tenant issuers, verify tenant identity and the requested resource, not just `SCOPE_read`.
- Protect test endpoints and profiles: never export fake-idp registrations or mocked decoders into production.

## 24. Running the project and reading real results

Assuming you have created a compatible Gradle Wrapper, run:

```bash
./gradlew test --tests 'com.example.security.SecurityModesMvcTest'
./gradlew test
```

On Windows PowerShell:

```powershell
.\gradlew.bat test
```

If the project lacks a Wrapper yet has a compatible Gradle installed:

```bash
gradle test
```

The sample source has **13 `@Test` methods**. There is no fixed business stdout: logs depend on Spring/Gradle versions and environment. Inspect reports after running:

```text
build/reports/tests/test/index.html
build/test-results/test/
```

**The 200/401/403/3xx outcomes in the table are expectations from test source. No Gradle execution report was produced while authoring this lesson, so do not claim “13 tests PASSED”.** If tests fail during Spring context startup, check for missing `JwtDecoder`, introspector, or `ClientRegistrationRepository` before editing assertions.

### Diagnostic order when context fails

1. Confirm Spring Boot 3.3.5, Java 17, dependencies, and class imports.
2. Confirm all four `SecurityFilterChain` beans are created, along with matchers and `@Order`.
3. Confirm `@MockBean JwtDecoder` and `@MockBean OpaqueTokenIntrospector` are registered in the test context.
4. Confirm the nested `@TestConfiguration` creates the fake `ClientRegistrationRepository`.
5. Check anonymous status and the first matching request matcher.
6. Check that `jwt()`/`opaqueToken()` supply the expected authorities.
7. For Bearer headers, check Mockito stub token strings and `verify(decoder).decode(...)` or `verify(introspector).introspect(...)`.
8. Read the full root cause and actual `MockMvc` response instead of disabling security filters to make the suite green.

## 25. Common mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| `@WithMockUser` leaves `@AuthenticationPrincipal Jwt` null | Wrong principal type | Use `jwt()` or real Bearer + decoder |
| Opaque controller lacks token attributes | Used `jwt()` or `@WithMockUser` | Use `opaqueToken()` |
| OIDC controller does not receive `OidcUser` | Used plain `oauth2Login()` | Use `oidcLogin()` |
| JWT test returns 200 even with past `exp` | `jwt()` bypasses validator | Test real `JwtDecoder` |
| Introspection revoked yet test returns 200 | `opaqueToken()` bypasses IdP | Mock real introspection HTTP/validator |
| Test gets 403 when expecting 401 | Authenticated but missing scope | Distinguish authn and authz |
| Anonymous browser receives redirect, not 401 | OAuth2 Login entry point | Assert 3xx per chain |
| Authority `reports.read` fails to match | Security rule requires `SCOPE_reports.read` | Map authorities with proper prefix |
| Method guarded by `@PreAuthorize` does not run in test | Method security not enabled | Add `@EnableMethodSecurity` and test right context |
| JWT bearer header never calls decoder | Used `with(jwt())` instead of header | Send Bearer header and mock decoder |
| JWT bearer failure becomes internal error | Mock threw arbitrary `RuntimeException` | Throw proper authentication/`BadJwt` exception |
| Opaque bearer mock still makes network calls to IdP | Mock bean did not replace right introspector | Check bean type and chain |
| OAuth2 login missing `ClientRegistrationRepository` | OAuth2 client config not provided | Provide test-only registration |
| Mock login has user yet session test fails | Mock only sets context for one request | Preserve session/cookie or test login flow separately |
| CSRF error on browser POST test | Missing CSRF token | Supply `csrf()` for state-changing requests |
| Path left unprotected | Wrong `securityMatcher` or missing fallback | Test route matrix/`denyAll` |
| Unit tests PASS yet production JWKS rotation fails | Mock decoder skips JWKs | Add integration test with fake JWKS server |
| Mockito scope mock grants access for any bearer | Stub too broad | Use exact tokens + negative tests |

## 26. JWT signing, issuer, audience, and clock skew

### Requirements of a real JWT Resource Server

Depending on application policy, a real JWT Resource Server should validate:
- Valid signature using trusted keys/JWKS.
- Accepted algorithm (never accidentally trusting `alg=none`).
- `exp` and `nbf` with appropriate clock skew.
- `iss` matching the configured authorization server/tenant.
- `aud` containing the right API recipient, when required.
- Scope/role claims mapped and validated accurately.
- Token not misused across purposes (ID token used as access token).

`jwt()` in MockMvc bypasses these checks. To verify validators, generate a signed test JWT with a test key and local JWK Set endpoint, configure a real `NimbusJwtDecoder`/validators, and test invalid issuer/audience/expired/signature scenarios. That is **a separate test suite**, not an extension of principal mocking.

### Boundaries of a Mockito JwtDecoder

Tests with `given(jwtDecoder.decode("valid-test-jwt")).willReturn(jwt)` verify filter -> provider -> converter -> controller, yet **Mockito decides the token is valid**. It will not detect JWK endpoint changes or key rotation bugs. Never report “JWT signature verified” from a test using only a mocked decoder.

## 27. Opaque introspection and token revocation

An opaque token can be revoked quickly because the Resource Server consults the IdP, yet latency and caching policies can leave a revoked token valid briefly. Policy tests should verify:

- Introspection endpoint authenticates with the right client ID/secret.
- `active` true/false responses are interpreted accurately.
- `exp`, `scope`, `sub`, and custom attributes have clear semantics.
- Introspection cache, if any, obeys TTL and invalidation/revocation SLAs.
- On IdP timeout, the system fails closed or applies configured fallback (never silently granting access).
- Logs never leak access tokens or introspection client secrets.

`opaqueToken()` provides a fake authenticated principal; `@MockBean OpaqueTokenIntrospector` returns a fake principal from the filter; neither makes an HTTP call. Testing `active:false` parsing and client credentials requires mocking the HTTP endpoint or using a dedicated IdP sandbox, not just constructing `DefaultOAuth2AuthenticatedPrincipal` manually.

## 28. At what level should OAuth2 browser login be tested?

There are at least three tiers:

1. **Logged-in controller:** `oauth2Login()`/`oidcLogin()`, no redirects/code exchange.
2. **Spring Security flow:** MockMvc/HTTP server tests for redirects, state, session, callback, and login success handlers; token/user-info endpoints can be mocked.
3. **End-to-end IdP:** browser or protocol tests against a provider sandbox, checking PKCE/nonce, cookies, TLS, and cross-origin behavior under real configuration.

Use the lightest tier that protects the behavior you care about. If a controller merely displays the username, `oauth2Login()` suffices; if verifying callback URL configuration, tier two is needed; if proving the production IdP supports PKCE/token mapping, tier three.

### CSRF in browser flows

CSRF still matters for session-authenticated browser requests. If you extend the project with `POST /web/settings`, a MockMvc test sending POST with OAuth2 login requires a CSRF token when Spring Security enables CSRF:

```java
mvc.perform(post("/web/settings")
        .with(oauth2Login())
        .with(csrf()))
        .andExpect(status().isOk());
```

This is a **snippet**, not independently runnable because the project lacks a `POST /web/settings` endpoint. It needs static imports `post` and `csrf`, plus the corresponding controller/state. Never disable CSRF on the browser chain just to avoid writing `.with(csrf())`.

## 29. Testing method security

If an application guards a service method with:

```java
@PreAuthorize("hasAuthority('SCOPE_reports.read')")
public Report readReport(String id) {
    // ...
}
```

this is a **snippet**, not part of the runnable project. It requires `@EnableMethodSecurity` and keeping the real proxy/bean. `@WithMockUser(authorities="SCOPE_reports.read")` can test the method's permission check without creating JWT claims; tests using `jwt()`/`opaqueToken()` can pair with MockMvc to inject the right principal into an HTTP request and verify method security runs through the service.

If the service itself is completely mocked via `@MockBean`, `@PreAuthorize` on the real service will not be exercised either. Distinguish testing authorization expressions from testing filter authentication.

## 30. WebFlux/reactive does not use the same MockMvc postprocessors

This project uses servlet MVC. For WebFlux applications, use `WebTestClient` and its own postprocessors like `SecurityMockServerConfigurers.mockJwt()`, `mockOpaqueToken()`, `mockOAuth2Login()`, or `mockOidcLogin()` depending on Spring Security version. Never copy `SecurityMockMvcRequestPostProcessors.jwt()` directly into WebFlux assuming it is the same abstraction.

**Both approaches must ensure security filter integration is actually wired into the test client.** With `MockMvcBuilders.standaloneSetup(...)`, omitting `.apply(springSecurity())` or a proper `SecurityFilterChain` stops postprocessors from acting as a real security test. `@SpringBootTest + @AutoConfigureMockMvc` in the sample project automatically attaches security filter chains to MockMvc.

## 31. Practice exercises

1. Send three unauthenticated requests to `/api/jwt/report`, `/api/opaque/report`, and `/web/profile`; explain 401 vs redirect.
2. Replace `.with(jwt())` with `@WithMockUser` on the JWT endpoint and observe the principal type mismatch.
3. Drop the `reports.read` scope from the JWT and verify status 403.
4. Try `jwt().authorities(...)` instead of claim mapping and explain which converter step is bypassed.
5. Build a mock JWT with wrong `iss` or expired `exp`; explain why `jwt()` does not reject it automatically.
6. Write a real `JwtDecoder` test with a signed test JWT and an audience validator.
7. Have `jwtDecoder.decode(...)` throw `BadJwtException` and assert 401.
8. Add custom attribute `department` via `opaqueToken()` and assert it in a new controller endpoint.
9. Have the introspector return a principal with `SCOPE_profile` and assert the opaque endpoint returns 403.
10. Build a stub introspection endpoint returning `active:false` to test the real HTTP introspector.
11. For OAuth2 Login, change `sub` to another user and verify the profile response.
12. Use `oidcLogin()` with a custom ID token `sub` and verify `OidcUser`.
13. Test an OAuth2 callback state mismatch using MockMvc/protocol-level IdP stubs.
14. Add a CSRF-protected `POST /web/settings`, testing both missing and valid `csrf()`.
15. Try adding a custom `JwtGrantedAuthoritiesConverter` mapping a custom claim and verify behavior without overriding it in the postprocessor.
16. Test fail-closed behavior when the introspection endpoint times out.
17. Add a deny-by-default matcher for new endpoints and confirm no public API leakage.
18. Write a `@PreAuthorize` method security test with the appropriate principal and verify the real service.
19. Run a single test and the full class, then read the actual Gradle report.
20. Place dummy tokens/secrets in fixtures and confirm no production tokens appear in Git/CI logs.

## 32. QA checklist

- [ ] Distinguished JWT Resource Server, opaque Resource Server, and OAuth2/OIDC Login?
- [ ] Used `jwt()`, `opaqueToken()`, `oauth2Login()`, `oidcLogin()` matching each principal type?
- [ ] Avoided using `@WithMockUser` as a JWT/opaque replacement when code needs the token type?
- [ ] `@MockBean JwtDecoder` and `@MockBean OpaqueTokenIntrospector` exist only in test contexts?
- [ ] Separated mock `SecurityContext` tests from Bearer filter tests?
- [ ] Asserted 200, 401, and 403 matching routes/policies?
- [ ] Browser anonymous requests expect redirects per OAuth2 Login?
- [ ] Distinguished and tested `SCOPE_` vs `ROLE_` properly?
- [ ] Important JWT claims are mapped to authorities by the real converter?
- [ ] Avoided claiming `jwt()` validated signatures/`exp`/`iss`/`aud`?
- [ ] Avoided claiming `opaqueToken()` called introspection or checked revocation?
- [ ] OAuth2 login tests have proper user attributes and client registration?
- [ ] OIDC tests use `OidcUser`/ID token without confusing them with access tokens?
- [ ] `SecurityFilterChain` matchers and ordering are protected by tests?
- [ ] Stateless API CSRF policy is separated from browser CSRF policy?
- [ ] No trust-all `JwtDecoder`/introspector exists in production?
- [ ] API bearer tokens and OAuth2 login sessions are not confused?
- [ ] Demo tokens/credentials are dummy values, with no real secrets in logs?
- [ ] For multi-tenant setups, issuer/audience/tenant ownership have dedicated tests?
- [ ] For revocation/ID token validation, appropriate integration/IdP tests exist?
- [ ] For reactive WebFlux, corresponding `WebTestClient` APIs were chosen?
- [ ] Read the real Gradle/CI report before claiming tests PASSED?

## 33. Official documentation

- [Spring Security — Testing OAuth 2.0 with MockMvc](https://docs.spring.io/spring-security/reference/6.3/servlet/test/mockmvc/oauth2.html): `jwt()`, `opaqueToken()`, `oauth2Login()`, `oidcLogin()`, mocking decoder/introspector.
- [Spring Security — Running a Test as a User](https://docs.spring.io/spring-security/reference/6.3/servlet/test/mockmvc/authentication.html): `user()` and `@WithMockUser`.
- [Spring Security — MockMvc Setup](https://docs.spring.io/spring-security/reference/6.3/servlet/test/mockmvc/setup.html): `springSecurity()` MockMvc configurer.
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/6.3/servlet/oauth2/resource-server/jwt.html): `JwtDecoder`, issuer/audience, scope authority mapping.
- [Spring Security — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/6.3/servlet/oauth2/resource-server/opaque-token.html): introspection and `BearerTokenAuthentication`.
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/6.3/servlet/oauth2/login/core.html): `ClientRegistration`, `SecurityFilterChain`, `OAuth2AuthenticationToken`.
- [Spring Boot 3.3 — Spring Security](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html): Spring Boot auto-configuration and custom security chains.
- [Spring Boot 3.3 — OAuth2](https://docs.spring.io/spring-boot/3.3/reference/security/oauth2.html): resource server/client registrations and configuration properties.
- [Spring Boot 3.3 — @MockBean API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/mock/mockito/MockBean.html): test-only bean replacement.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): JUnit Jupiter test methods.

## 34. Conclusion

**JWT**, **opaque tokens**, and **OAuth2 Login** all use Spring Security, yet cannot be collapsed into a single mock user type. For a JWT Resource Server, use **`jwt()`** to test principals/scopes/authorization, or mock **`JwtDecoder`** and send a Bearer header to test the authentication filter. For an opaque Resource Server, use **`opaqueToken()`** or mock **`OpaqueTokenIntrospector`** accordingly. For browser OAuth2/OIDC Login, use **`oauth2Login()`** or **`oidcLogin()`** to simulate a logged-in user; testing full redirects/code exchange/JWKS/nonce/PKCE requires integration tests at a deeper layer.

A useful security suite must test allowed/forbidden/unauthorized access, authority mapping, and principal types, while **never claiming JWT signatures, revocation, or OAuth2 redirect flows were verified merely because a MockMvc postprocessor PASSED**. The Java 17+/Spring Boot 3.3.5 sample project uses three filter chains, controllers, and 13 test methods to draw these boundaries clearly.

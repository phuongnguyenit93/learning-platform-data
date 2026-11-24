# oauth2Login, oidcLogin, jwt, and opaqueToken: Scope of Simulation in HTTP Testing

**Context:** Spring Security **Servlet/Spring MVC**, Java 17+, Spring Boot 3.x, Spring Security 6.x, JUnit 5, and MockMvc. The four functions `oauth2Login()`, `oidcLogin()`, `jwt()`, and `opaqueToken()` in **`spring-security-test`** are *request post-processors* that construct a **simulated `Authentication`** for a test HTTP request. Understanding their exact scope is essential so you do not write a "green" test suite that misses real bugs in OAuth2/OIDC login, JWT validation, or opaque-token introspection.

## 1. Learning Objectives and Big Picture

After this lesson, you will be able to:

1. Distinguish **OAuth2 Login / OIDC login** (user logging into a web app) from **OAuth2 Resource Server** (verifying bearer access tokens for an API).
2. Choose the right `oauth2Login()`, `oidcLogin()`, `jwt()`, or `opaqueToken()` according to the **principal/`Authentication` type** the endpoint actually needs.
3. Use MockMvc to test **controllers, method security, authorities, and route authorization**, for both permitted and denied cases.
4. Recognize what the four post-processors **do not** verify: redirects, `state`, `nonce`, JWT signatures, issuer/audience/time, token introspection, provider availability, and token revocation.
5. Design additional integration tests that truly run through Spring Security authentication filters/decoders or a reliable mock IdP when that boundary must be verified.

### 1.1 Four Ways to Simulate — Four Different Meanings

| MockMvc post-processor | Simulated Authentication/principal | Best used when testing | Does not verify on its own |
| --- | --- | --- | --- |
| `oauth2Login()` | `OAuth2AuthenticationToken` with `OAuth2User` | MVC web app already logged in via an OAuth2 provider; controller reads user attributes/authorities. | Authorization redirect, consent, code exchange, user-info HTTP call. |
| `oidcLogin()` | OAuth2 login authentication with `OidcUser` and simulated ID token/user-info | MVC app using OIDC; controller needs `@AuthenticationPrincipal OidcUser` or OIDC claims. | Signature/issuer/audience/nonce/expiry of a **real ID token**, OIDC discovery, JWKS, token endpoint. |
| `jwt()` | `JwtAuthenticationToken` holding a simulated `Jwt` | API relying on a JWT principal and authorities. | `BearerTokenAuthenticationFilter` handling real tokens, `JwtDecoder`, signature, issuer/audience, token expiry, real claim conversion if authorities are set directly. |
| `opaqueToken()` | `BearerTokenAuthentication` with a simulated `OAuth2AuthenticatedPrincipal` | API using opaque bearer access tokens, needing principal attributes/scopes. | Calling `OpaqueTokenIntrospector` against an authorization server, active/revoked/expired status, network issues, HTTP introspection auth. |

All four create an "**assume the request is already authenticated**" state. They are very helpful for **testing authorization and post-authentication behavior**, yet are **not** tools for proving security filters read and validated real-world credentials.

### 1.2 Do Not Confuse OAuth2 Client, OAuth2 Login, OIDC, and Resource Server

- **OAuth2 Client:** an application managing access permissions and access tokens to call an external resource server. It can run on behalf of a user or via the `client_credentials` grant.
- **OAuth2 Login:** a Spring MVC application letting users log in through an external provider, then storing `Authentication` in `SecurityContext` and typically maintaining a session via cookies.
- **OpenID Connect (OIDC):** an identity layer on top of OAuth 2.0, using an ID token subject to standard constraints such as `iss`, `sub`, `aud`, `exp`, and `nonce` (when applicable).
- **OAuth2 Resource Server:** an API protecting endpoints with bearer **access tokens**, verifying JWTs locally or introspecting opaque tokens and checking permissions.

A user logging in via OIDC does not mean an API automatically accepts every bearer token. A `JwtAuthenticationToken` in a test also does not prove a web app supports OIDC login. **Inspect the `Authentication` the endpoint expects before choosing a post-processor.**

## 2. Which Layer Do Request Post-Processors Operate On?

With MockMvc, you can write:

```java
mvc.perform(get("/api/report").with(jwt()));
```

`with(...)` modifies **`MockHttpServletRequest`** for testing. Security post-processors can create and attach a `SecurityContext`/`Authentication` to the request for Spring Security filters and controllers to use while MockMvc processes it. This **differs** from sending raw HTTP `Authorization: Bearer ...` and letting the resource server decode the token itself.

In this lesson, "simulate" means **replacing the input at the authentication boundary with a pre-built principal**, not simulating all underlying protocols.

```text
A. Test using a post-processor (identity pre-populated)
JUnit + MockMvc
  └─ get("/api/report").with(jwt())
       └─ request has mock SecurityContext/JwtAuthenticationToken
            └─ SecurityFilterChain / AuthorizationFilter
                 └─ Controller + service / method security
                    [No real JWT signature or network JwtDecoder needed]

B. Test passing through the real bearer token filter
JUnit + MockMvc
  └─ get("/api/report")
       .header("Authorization", "Bearer eyJ...")
       └─ BearerTokenAuthenticationFilter
            └─ JwtDecoder or OpaqueTokenIntrospector
                 └─ Authentication if token is valid
                      └─ AuthorizationFilter
                           └─ Controller
```

Likewise, `oauth2Login()` **does not** cause MockMvc to redirect a browser to the IdP, log in, receive an authorization code, or verify `state`; it creates the resulting authentication object to test **everything after login**.

**Important condition:** the examples use MockMvc **integrated with the Spring Security filter chain**. With Spring Boot, `@SpringBootTest` + `@AutoConfigureMockMvc` is a convenient way. If you build `MockMvcBuilders.standaloneSetup(...)` manually without integrating Spring Security via `springSecurity()`, post-processors may not work as expected. Never conclude "the test checked security" when filters were accidentally omitted from requests.

## 3. Choosing a Post-Processor Based on the Endpoint

Suppose a project has:

- `GET /web/identity`: returns the identity type after login (`OAuth2User` or `OidcUser`).
- `GET /web/subject`: requires `OidcUser` and returns `sub`.
- `GET /api/report`: only allows callers with `SCOPE_reports.read`.
- `GET /api/admin`: only allows callers with `SCOPE_admin`.
- `POST /web/update`: updates information in a web session, still requiring a CSRF token.

At the **controller/authorization** layer, the four request post-processors reproduce these cases:

| Need to verify | Choose | Why |
| --- | --- | --- |
| Controller using `OAuth2User` after OAuth2 Login | `oauth2Login()` | Mocks an OAuth2 user principal. |
| Controller reading `OidcUser.getIdToken()` or `getSubject()` | `oidcLogin()` | Supplies a mock OIDC ID token/principal. |
| API authorizing via `SCOPE_reports.read` with a JWT-backed principal | `jwt().authorities(...)` | Specifies exact authorities for the test case. |
| API authorizing via scope from an opaque token | `opaqueToken().authorities(...)` | Builds a bearer principal and authorities. |
| Returning 403 when lacking authority | Same processor with missing authorities | Tests the `hasAuthority` policy. |
| Testing only "logged-in user" without needing OAuth2 types | `user(...)` or `@WithMockUser` may suffice | No need to fake OAuth/OIDC to test every route. |
| Verifying JWT signature, `aud`, `iss`, `exp` | **Do not use `jwt()` as sole proof** | Send a bearer header through the resource server + real decoder, or test the decoder directly. |
| Verifying opaque token active/revoked/introspection | **Do not use only `opaqueToken()`** | Needs an introspector/stub server or test IdP. |
| Verifying authorization code, `state`, redirect URI | **Do not use only `oauth2Login()/oidcLogin()`** | Needs flow tests with OAuth2/OIDC client filters and a simulated/controlled provider. |

Multiple tests can hit **the same endpoint** with two different processors. That is fine for verifying authorization works across principal types, **yet does not make the two production authentication mechanisms equivalent**.

## 4. Runnable Example: Spring Boot Configuration, Controller, and MockMvc

The minimal example below intentionally **does not configure real OAuth2 Login or Resource Server authentication flows**. We configure only **authorization** and an HTTP Basic entry point to keep the focus on the scope of request post-processors. That is the educational point: tests can PASS with mock principals even when the app **does not yet have** a real IdP, JWT decoder, or opaque-token introspection.

Create a Gradle project from Spring Initializr with **Java 17+, Spring Boot 3.x, Spring Web, Spring Security, Spring Boot Starter Test** and add `spring-security-test`. All Java files are in package `com.example.authmock`.

### 4.1 Dependencies

Illustrative `build.gradle` dependencies snippet, keeping the standard plugins and repositories of a Spring Boot project generated by Initializr:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

You do not need to run a real IdP or introspection server to execute this **simulated MockMvc test suite**. When moving to real OAuth2/OIDC/resource-server integration tests, add the corresponding modules and configuration.

### 4.2 SecurityConfig.java

**`src/main/java/com/example/authmock/SecurityConfig.java`**

```java
package com.example.authmock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET,
                    "/web/identity",
                    "/web/subject"
                ).authenticated()
                .requestMatchers(
                    HttpMethod.POST, "/web/update"
                ).authenticated()
                .requestMatchers(
                    HttpMethod.GET, "/api/report"
                ).hasAuthority("SCOPE_reports.read")
                .requestMatchers(
                    HttpMethod.GET, "/api/admin"
                ).hasAuthority("SCOPE_admin")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        // Neither oauth2Login nor oauth2ResourceServer is enabled in this demo.
        // Default CSRF protection still applies to POST.
        return http.build();
    }
}
```

**Key points to note:**

1. `/web/identity` only requires a valid `Authentication`.
2. `/api/report` and `/api/admin` require **exact authorities**. In Spring, `hasAuthority("SCOPE_reports.read")` does not automatically turn into `ROLE_reports.read`; scopes and roles are two separate conventions.
3. `httpBasic(...)` merely provides an easy-to-test authentication entry point for unauthenticated requests; it **does not** turn the application into an OAuth2 Resource Server.
4. `POST /web/update` still has to pass CSRF protection under Spring Security's default policy.
5. Using `jwt()`/`opaqueToken()` in MockMvc to reach `/api/report` **does not prove** the production endpoint knows how to parse bearer tokens. It tests authorization given a pre-built mock `Authentication`.

### 4.3 AuthController.java

**`src/main/java/com/example/authmock/AuthController.java`**

```java
package com.example.authmock;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.stream.Collectors;

@RestController
public class AuthController {

    @GetMapping("/web/identity")
    public String webIdentity(Authentication auth) {
        Object principal = auth.getPrincipal();

        if (principal instanceof OidcUser) {
            return "oidc";
        }
        if (principal instanceof OAuth2User) {
            return "oauth2";
        }
        return "other";
    }

    @GetMapping("/web/subject")
    public String oidcSubject(@AuthenticationPrincipal OidcUser user) {
        return user.getSubject();
    }

    @GetMapping("/api/report")
    public String report(Authentication auth) {
        return auth.getAuthorities()
            .stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .collect(Collectors.joining(","));
    }

    @GetMapping("/api/admin")
    public String admin() {
        return "admin";
    }

    @PostMapping("/web/update")
    public String update() {
        return "updated";
    }
}
```

The controller inspects the principal by the **actual type** supplied by the post-processor: `OidcUser` is an `OAuth2User` with ID token information and OIDC claims, so `instanceof OidcUser` must be checked **before** `instanceof OAuth2User` to distinguish them. `/api/report` returns authorities so test cases can compare easily; production endpoints should return business data instead of exposing full permission lists.

### 4.4 Application.java

**`src/main/java/com/example/authmock/Application.java`**

```java
package com.example.authmock;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

This is a Spring Boot project and will not compile standalone with `javac` without the Spring classpath. Use the Gradle wrapper:

```bash
./gradlew test
```

On Windows PowerShell:

```powershell
.\gradlew.bat test
```

The expected result is **JUnit tests PASS** when the project and dependencies are configured properly; do not fabricate a `BUILD SUCCESSFUL` transcript or test count from an unexecuted environment.

## 5. MockMvc Tests Using All Four Post-Processors

**`src/test/java/com/example/authmock/AuthRequestPostProcessorTest.java`**

```java
package com.example.authmock;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.*;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class AuthRequestPostProcessorTest {

    @Autowired
    MockMvc mvc;

    @Test
    void oauth2LoginGivesOAuth2Principal() throws Exception {
        mvc.perform(get("/web/identity").with(oauth2Login()))
            .andExpect(status().isOk())
            .andExpect(content().string("oauth2"));
    }

    @Test
    void oidcLoginGivesOidcUserAndMockIdTokenClaims()
            throws Exception {

        mvc.perform(
            get("/web/identity").with(oidcLogin())
        )
            .andExpect(status().isOk())
            .andExpect(content().string("oidc"));

        mvc.perform(
            get("/web/subject").with(
                oidcLogin().idToken(
                    token -> token.claim("sub", "oidc-account-17")
                )
            )
        )
            .andExpect(status().isOk())
            .andExpect(content().string("oidc-account-17"));
    }

    @Test
    void jwtAllowsRequiredAuthority() throws Exception {
        mvc.perform(
            get("/api/report").with(
                jwt()
                    .jwt(token -> token.claim("sub", "jwt-account"))
                    .authorities(
                        new SimpleGrantedAuthority("SCOPE_reports.read")
                    )
            )
        )
            .andExpect(status().isOk())
            .andExpect(content().string("SCOPE_reports.read"));
    }

    @Test
    void opaqueTokenAllowsRequiredAuthority() throws Exception {
        mvc.perform(
            get("/api/report").with(
                opaqueToken()
                    .attributes(
                        attrs -> attrs.put("sub", "opaque-account")
                    )
                    .authorities(
                        new SimpleGrantedAuthority("SCOPE_reports.read")
                    )
            )
        )
            .andExpect(status().isOk())
            .andExpect(content().string("SCOPE_reports.read"));
    }

    @Test
    void jwtWithWrongAuthorityIsForbidden() throws Exception {
        mvc.perform(
            get("/api/report").with(
                jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_other")
                )
            )
        )
            .andExpect(status().isForbidden());
    }

    @Test
    void opaqueTokenCannotAccessAdminWithoutAdminScope()
            throws Exception {

        mvc.perform(
            get("/api/admin").with(
                opaqueToken().authorities(
                    new SimpleGrantedAuthority("SCOPE_reports.read")
                )
            )
        )
            .andExpect(status().isForbidden());
    }

    @Test
    void unauthenticatedRequestIsRejected() throws Exception {
        mvc.perform(get("/api/report"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void fakeLoginDoesNotAutomaticallySupplyCsrfToken()
            throws Exception {

        mvc.perform(
            post("/web/update").with(oauth2Login())
        )
            .andExpect(status().isForbidden());

        mvc.perform(
            post("/web/update")
                .with(oauth2Login())
                .with(csrf())
        )
            .andExpect(status().isOk())
            .andExpect(content().string("updated"));
    }
}
```

**Explanation:**

- `oauth2Login()` creates an OAuth2 principal, so the endpoint classifies it as `oauth2`.
- `oidcLogin()` creates an `OidcUser` principal, and `idToken(token -> ...)` customizes a claim in the **simulated ID token**. The endpoint reads `sub` from the mock user; no OIDC signature verification takes place.
- `jwt()` and `opaqueToken()` let you attach authorities explicitly, then test `hasAuthority(...)`. Two positive tests prove the policy accepts the constructed authority; two negative tests prove lacking permission is denied.
- Unauthenticated requests return 401 due to the demo's HTTP Basic entry point configuration.
- `oauth2Login()` **does not bypass CSRF** on POST. `csrf()` is a separate test request post-processor simulating a valid token for the test; it does not prove a production browser bootstrapped the CSRF token properly.
- None of the tests above prove the endpoint handles real bearer tokens: in `SecurityConfig` we **intentionally did not enable `oauth2ResourceServer()`**. This clearly illustrates the scope covered by mock tests.

**About imports:** the `static import` statements are split across lines using valid Java syntax (never ending a line with a dot; continuing on the next line), though if your IDE uses another formatter, you can write them on one line like `import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.*;`. Keep full imports per your actual build tooling.

### 5.1 Authorization Tests Can Be "Falsely Green"

A test snippet using only:

```java
mvc.perform(get("/api/report").with(jwt()
    .authorities(new SimpleGrantedAuthority("SCOPE_reports.read"))))
   .andExpect(status().isOk());
```

proves that **the controller/authorization handles a simulated `JwtAuthenticationToken`** carrying that authority. It **does not** prove a bearer token containing scope `reports.read` will be decoded properly, have its claim converted into `SCOPE_reports.read`, or be rejected if the signature is invalid.

Similarly, an `oidcLogin().idToken(...).andExpect(status().isOk())` test does not prove the provider issues ID tokens with valid issuer/audience/nonce, because the test already supplied a pre-built `OidcUser`.

## 6. Customizing Principal, Claims, and Authorities for Focused Tests

### 6.1 oauth2Login(): Testing OAuth2 User Attributes and Authorities

You can configure mock attributes and authorities:

```java
mvc.perform(
    get("/web/identity").with(
        oauth2Login()
            .attributes(attrs -> attrs.put("department", "engineering"))
            .authorities(
                new SimpleGrantedAuthority("ROLE_EDITOR")
            )
    )
);
```

The snippet above is a **request fragment** inside a test with `mvc` and matching imports, not a standalone class. It lets you test controllers or method security handling an OAuth2 user with hypothetical attributes/authorities.

**Do not treat test-supplied attributes as verified claims from a provider.** In a real application, you need reliable profile/claim mapping, account/tenant checks, and role-assignment policies. `ROLE_EDITOR` assigned by the test is an input condition, not proof the app can automatically derive that role from an external provider.

### 6.2 oidcLogin(): Testing ID Token/UserInfo Without Checking Signatures

You can construct the OIDC claims needed by the controller:

```java
mvc.perform(
    get("/web/subject").with(
        oidcLogin()
            .idToken(token -> token
                .claim("sub", "employee-42")
                .claim("email", "employee@example.test")
            )
    )
);
```

In the test, `OidcUser.getSubject()`, `getIdToken()`, and the corresponding claims can be read. However, **no ID token decoder, issuer validation, audience validation, JWKS fetch, or nonce correlation runs** merely from using `oidcLogin()`. Adding `email` also does not guarantee the production provider includes `email_verified=true` or supplies email according to policy.

When you need to test controller behavior driven by OIDC claims, use the post-processor. When you need to test the **OIDC login security protocol**, use integration tests covering OAuth2 Login/OIDC filters and an appropriate provider.

### 6.3 jwt(): Separating JWT Claims from Authorities

Example:

```java
mvc.perform(
    get("/api/report").with(
        jwt()
            .jwt(token -> token
                .claim("sub", "user-7")
                .claim("scope", "reports.read")
            )
            .authorities(
                new SimpleGrantedAuthority("SCOPE_other")
            )
    )
).andExpect(status().isForbidden());
```

**Even though the mock JWT has `scope=reports.read`, the test must still return 403** because authorities were **deliberately overridden** to `SCOPE_other`. This proves authorization relies on **`Authentication.getAuthorities()` after authentication**, rather than inferring permissions from a raw JSON claim inside the controller.

In production, `JwtAuthenticationConverter` or a custom converter is responsible for turning JWT claims into authorities. `jwt().authorities(...)` **skips testing that converter**. To test the converter, invoke the converter directly in a unit test or send a bearer token through the configured resource-server path so the real converter executes.

You can pass a `Converter<Jwt, Collection<GrantedAuthority>>` to the test post-processor if your Spring Security version's API supports it; even then, that remains **unit-level converter behavior on a mock JWT**, not signature/token decoder verification.

### 6.4 opaqueToken(): Pre-Built Attributes and Authorities from Introspection

`opaqueToken()` lets you specify attributes and authorities on a simulated principal:

```java
mvc.perform(
    get("/api/report").with(
        opaqueToken()
            .attributes(attrs -> {
                attrs.put("sub", "service-account-17");
                attrs.put("client_id", "reporting-app");
            })
            .authorities(
                new SimpleGrantedAuthority("SCOPE_reports.read")
            )
    )
).andExpect(status().isOk());
```

This is useful when a resource controller reads `OAuth2AuthenticatedPrincipal`, `sub`, `client_id`, or authorities. Yet it **does not invoke `OpaqueTokenIntrospector.introspect(token)`**, so it will not catch cases where the IdP returns `active:false`, introspection returns 401/500, scopes are missing, or a token was revoked.

For a real opaque-token resource server, the authorization server returns attributes and scopes via introspection; Spring Security must map them to principal/authorities. The test post-processor pre-populates the result, so no network communication happens.

### 6.5 Distinguishing Roles and Scopes in Tests

- `hasRole("ADMIN")` normally requires authority `ROLE_ADMIN`.
- `hasAuthority("SCOPE_reports.read")` requires the **exact** authority `SCOPE_reports.read`.
- `jwt().authorities(new SimpleGrantedAuthority("ROLE_ADMIN"))` does not automatically imply `SCOPE_reports.read`.
- `jwt().jwt(token -> token.claim("scope", "reports.read"))` does not replace testing the real converter when the converter is customized.
- A principal with `isAuthenticated()==true` is not automatically allowed on every route; you must enforce authorities, object-level permissions, and tenant checks on the backend.

Always state the **expected authority** explicitly in tests so tests never pass due to unsuitable defaults.

## 7. The Four Post-Processors Do NOT Cover Real Authentication Paths

### 7.1 OAuth2 Login and OIDC

A real login flow in a Servlet application typically includes:

```text
Browser
   └── GET /oauth2/authorization/{registrationId}
           └── OAuth2AuthorizationRequestRedirectFilter
                   └── redirect to authorization endpoint
                           └── user login / consent
                                   └── callback /login/oauth2/code/{registrationId}
                                           └── verify state/authorization response
                                           └── exchange code at token endpoint
                                           └── OIDC ID token validation if applicable
                                           └── OAuth2AuthenticationToken/SecurityContext
                                                   └── browser session
```

`oauth2Login()` and `oidcLogin()` **jump straight to the final state**. They do not verify:

- Whether `ClientRegistration`, registration ID, and callback URI match the provider allowlist.
- Whether `state` matches the authorization request or was replayed/missing a session.
- PKCE `code_challenge` / `code_verifier` per client and provider policies.
- Whether the authorization code is exchanged at the token endpoint with proper client authentication.
- Whether the UserInfo endpoint errors or returns unexpected attributes.
- Whether the ID token has a valid signature, right issuer, matching audience, unexpired `exp`, and matching `nonce` (per flow).
- Whether session cookies/SameSite/redirects/proxies preserve login across multiple real HTTP requests.

**When you need to test these:** use a test environment with an appropriate OAuth2/OIDC provider (such as an authorization server for integration tests or a protocol-faithful HTTP stub), wire `spring-boot-starter-oauth2-client`, and verify redirects/callbacks and token/JWKS/UserInfo stubs just like production. MockMvc can start by asserting 302 and `Location`; traversing the full flow with code exchange/JWKS requires a simulated provider or multi-step integration test.

Do not conclude OAuth2 Login is "safe against login CSRF" just because `oauth2Login()` builds a principal. `state`/`nonce`/PKCE and real callbacks must be verified at the actual boundary.

### 7.2 JWT Resource Server

Real bearer JWT flow:

```text
HTTP Authorization: Bearer <token>
      └── BearerTokenAuthenticationFilter
             └── JwtAuthenticationProvider
                    └── JwtDecoder
                          └── verify signature/key
                          └── issuer, exp/nbf, audience per policy
                    └── JwtAuthenticationConverter
                          └── authorities
             └── AuthorizationFilter
                    └── endpoint
```

`jwt()` **does not call `JwtDecoder.decode(token)`**, so it cannot prove:

- The JWT has a valid signature, allowed algorithm, and policy-compliant `kid`.
- The JWT is not expired (`exp`), not used before `nbf`, and carries the expected issuer (`iss`).
- Audience (`aud`) targets this exact API; audience validation often needs explicit configuration rather than assuming defaults cover it.
- JWK rotation and JWKS endpoint errors are handled properly.
- Missing/tampered tokens are rejected as expected.
- Mapping `scope`/`scp`/role claims to authorities matches the production converter.

**Next steps:** write dedicated tests for `JwtDecoder`/`JwtAuthenticationConverter` and integration tests sending a **real bearer header** when the resource-server filter chain is active. Decoder unit tests can use signed JWT fixtures with test keys; integration tests may mock `JwtDecoder` to verify filter orchestration, though **a mocked decoder does not prove real signatures**.

### 7.3 Opaque Token Resource Server

Real opaque bearer token flow:

```text
HTTP Authorization: Bearer <opaque-token>
      └── BearerTokenAuthenticationFilter
             └── OpaqueTokenAuthenticationProvider
                    └── OpaqueTokenIntrospector
                         └── authorization server introspection endpoint
                              └── active, scope, sub, client_id, exp...
                    └── principal/authorities
             └── AuthorizationFilter
                    └── endpoint
```

`opaqueToken()` **does not call introspection**. A mock principal with `SCOPE_admin` authorities will still make an authorization test "green" even if a real token was revoked. To verify revoked tokens are rejected, test `OpaqueTokenIntrospector` or the real resource-server path against a stub introspection endpoint.

**Note:** JWTs can also be revoked according to system policy, yet a JWT Resource Server by default verifies tokens locally via trust/JWKS rather than performing per-request introspection. Do not apply opaque-token revocation assumptions blindly to every JWT decoder.

## 8. Example: Adding a Test Through a Real JwtDecoder in the Filter Chain

This section is a **separate test configuration**—do not drop it straight into the minimal `SecurityConfig` in section 4 and assume everything runs together. In a Resource Server project needing the `spring-boot-starter-oauth2-resource-server` dependency, enable:

```java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/report")
            .hasAuthority("SCOPE_reports.read")
        .anyRequest().authenticated()
    )
    .oauth2ResourceServer(oauth2 -> oauth2
        .jwt(Customizer.withDefaults())
    );
```

This is a **DSL snippet** inside `SecurityFilterChain`. A `JwtDecoder` bean must exist; production decoders usually fetch JWKs from the configured issuer/JWK Set URI. For instance, an integration test may **mock `JwtDecoder`** to check that the filter calls the decoder and handles errors, even though that test still **does not verify real signatures**.

Snippet of a Spring Boot 3.x test class with `@SpringBootTest`, `@AutoConfigureMockMvc`, and the resource-server config above:

```java
@Autowired
MockMvc mvc;

@MockBean
JwtDecoder jwtDecoder;

@Test
void badBearerTokenIsRejectedByResourceServerFilter() throws Exception {
    Mockito.when(jwtDecoder.decode("bad-token"))
        .thenThrow(new BadJwtException("invalid signature"));

    mvc.perform(
        get("/api/report")
            .header("Authorization", "Bearer bad-token")
    ).andExpect(status().isUnauthorized());

    Mockito.verify(jwtDecoder).decode("bad-token");
}
```

This is a **non-standalone test snippet**: it requires imports such as `JwtDecoder`, `BadJwtException`, `Mockito`, `MockBean`, `MockMvc`, `@Test`, plus a real Resource Server configuration and controller. `@MockBean` is the familiar Spring Boot 3.x API (deprecated in some newer versions; replace with `@MockitoBean` where supported by your project). Pick the mock-bean annotation matching your environment rather than mixing both.

This test is useful because the request carries a **real `Authorization: Bearer bad-token` header** and filter/decoder interaction is observed. Still, `Mockito.when(...)` simulates the decode failure; the test only proves the error path/401 and filter wiring, **not real RSA/ECDSA/JWK cryptography**. To verify crypto, add decoder tests using tokens signed with test keys plus invalid-signature, expired, and wrong-issuer/audience fixtures.

A happy-path test can stub the decoder to return:

```java
Jwt jwt = Jwt.withTokenValue("good-token")
    .header("alg", "RS256")
    .claim("sub", "user-17")
    .claim("scope", "reports.read")
    .build();

Mockito.when(jwtDecoder.decode("good-token")).thenReturn(jwt);
```

When sending `Bearer good-token` through the real resource server, the default converter can map `scope` to `SCOPE_reports.read`, letting you verify the filter + converter path. Still, **signature verification remains mocked** because the decoder was stubbed. Clearly separate this assurance level in test names and docs.

## 9. Example: Testing the Opaque-Token Introspection Path

In a **separate opaque-token resource server configuration**, enable:

```java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/report")
            .hasAuthority("SCOPE_reports.read")
        .anyRequest().authenticated()
    )
    .oauth2ResourceServer(oauth2 -> oauth2
        .opaqueToken(Customizer.withDefaults())
    );
```

The configuration requires an `OpaqueTokenIntrospector` bean or matching `spring.security.oauth2.resourceserver.opaquetoken` properties. To test the error path when a token is inactive, a separate test can mock the introspector:

```java
@MockBean
OpaqueTokenIntrospector introspector;

@Test
void inactiveOpaqueBearerTokenIsRejected() throws Exception {
    Mockito.when(introspector.introspect("revoked-token"))
        .thenThrow(new OAuth2IntrospectionException("inactive"));

    mvc.perform(
        get("/api/report")
            .header("Authorization", "Bearer revoked-token")
    ).andExpect(status().isUnauthorized());

    Mockito.verify(introspector).introspect("revoked-token");
}
```

This is also a **non-standalone test snippet**, using the resource-server filter path and needing imports/fixtures like the previous section; **do not combine it with JWT-only config in one default filter chain** unless the application architecture deliberately chooses that design. Mocking the introspector lets you test how the app handles a simulated `inactive` result, yet **makes no real HTTP request** to an authorization server.

When you want to test real introspection integration, use a controlled **HTTP stub server** returning cases such as: `active=true` with scopes, `active=false`, 401 from wrong client credentials, 500/service unavailable, timeouts, and missing/malformed fields. Also verify that introspection client secrets are never logged.

### 9.1 Stratifying Assurance Levels

| Test | What it verifies more strongly | What remains unproven |
| --- | --- | --- |
| `opaqueToken()` | Controller/authorization with a mock Bearer principal. | Whether introspection is called at all. |
| Bearer header + **mock** `OpaqueTokenIntrospector` | Filter wiring, 401/403, mapping from stubbed return. | Real HTTP requests, credentials, and introspection responses. |
| Bearer header + introspector calling a **stub HTTP server** | HTTP request, response parsing, network/error behavior. | Whether the real production authorization server is accurate/uncompromised. |
| Staging/contract test against a controlled IdP | Real protocol/scope/metadata compatibility. | Does not replace all production threat/operational monitoring. |

## 10. Testing Authorities and Claims Without Confusion

A common mistake is writing:

```java
mvc.perform(
    get("/api/admin").with(jwt())
).andExpect(status().isOk());
```

and concluding "an admin's JWT token can enter the endpoint". In fact, `jwt()` constructs a default principal **that is not an admin token**; if the endpoint was misconfigured to allow any authenticated user, the test passes due to an overly permissive policy rather than proving role mapping.

Write **contrasting cases** with explicit authorities:

```java
mvc.perform(
    get("/api/admin").with(jwt()
        .authorities(new SimpleGrantedAuthority("SCOPE_reports.read")))
).andExpect(status().isForbidden());

mvc.perform(
    get("/api/admin").with(jwt()
        .authorities(new SimpleGrantedAuthority("SCOPE_admin")))
).andExpect(status().isOk());
```

This test ensures the authorization policy enforces the intended authority. If the service also restricts resources by owner/tenant, test identity/tenant-specific authorization in service or integration tests: `ROLE_ADMIN` does not automatically prove permission to view every object.

**Avoid the claim ≠ authority trap:** JWT `scope`/`scp` claims and OAuth2 attributes may pass through a custom converter/mapping. When using `.authorities(...)` in a post-processor, you **specify the final outcome** without testing the converter. To guard the converter, add direct tests:

```java
JwtAuthenticationConverter converter =
    new JwtAuthenticationConverter();

// Unit-test the converter with an appropriate Jwt fixture,
// then assert authorities, principal name, and project policy.
```

This is an illustrative snippet, not a complete test case; if the project customizes the converter (for instance reading roles from `realm_access.roles`), test **the exact converter in use** rather than the default one.

## 11. CSRF, Sessions, Headers, and @WithMockUser: Different Boundaries

### 11.1 Fake OAuth2 Login Does Not Bypass CSRF

In Spring Security Servlet, state-changing requests backed by session cookies usually require a CSRF token. `oauth2Login()` and `oidcLogin()` build an identity **without automatically making a POST valid for CSRF**. In tests:

```java
mvc.perform(
    post("/web/update").with(oidcLogin())
).andExpect(status().isForbidden());

mvc.perform(
    post("/web/update").with(oidcLogin()).with(csrf())
).andExpect(status().isOk());
```

`with(csrf())` is also a Spring Security Test mock valid token. It helps focus on the POST's business behavior, yet **does not prove** the production browser fetched/stored/submitted the token properly (`CookieCsrfTokenRepository`, deferred tokens, BREACH masking, headers, SPA bootstrapping).

### 11.2 MockMvc Sessions Do Not Prove the OIDC Cookie Lifecycle

`oidcLogin()` does not exercise multi-request login across real redirects/session fixation protection. A single-request test with a post-processor injects a mock identity on each `perform` call. It does not ensure browser session cookies carry proper `Secure`/`HttpOnly`/`SameSite` flags or login persistence after callbacks; supplement with corresponding end-to-end/integration tests.

### 11.3 @WithMockUser Is Not Equivalent to OAuth2/OIDC

`@WithMockUser(username="alice", roles="USER")` creates a mock security context with a Spring Security `User`-style principal, helpful for `hasRole("USER")` rules and controllers needing only `Authentication.getName()`. However, a controller expecting `OidcUser.getSubject()` or `Jwt.getClaim(...)` may fail because **the principal type is different**.

Choose the helper matching the domain contract:

- `@WithMockUser` for methods/controllers independent of OAuth2 principal types.
- `oauth2Login()` when the controller expects `OAuth2User`.
- `oidcLogin()` when the controller expects `OidcUser`.
- `jwt()` when the API/controller expects `Jwt`/`JwtAuthenticationToken`.
- `opaqueToken()` when the API expects `OAuth2AuthenticatedPrincipal` from opaque-token auth.

Do not use a heavier helper when only `ROLE_USER` is needed; conversely, do not use `@WithMockUser` and accidentally hide type-casting bugs in an OIDC controller.

## 12. Slice Tests vs. Integration Tests

### 12.1 @WebMvcTest

`@WebMvcTest(MyController.class)` loads **a Spring MVC slice**: controllers, MVC infrastructure, and partial filter/test support. It is fast, though many service/security beans are missing or mocked. When using `spring-security-test`, ensure `MockMvc` has Spring Security integrated; `@Import` the appropriate security config and `@MockBean` controller dependencies as needed.

Use it to verify: serialization, route mapping, controller principal extraction, response status, and `hasAuthority` on the configured slice filter chain. Never use it to claim production IdP/`JwtDecoder`/introspection works.

### 12.2 @SpringBootTest + @AutoConfigureMockMvc

Loads a broader application context with real filter chains, yet **request post-processors still simulate `Authentication`**. Therefore "integration test" does not automatically mean "cryptographic authentication integration test".

Example:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ReportAuthorizationTest {
    @Autowired MockMvc mvc;

    @Test
    void allowsMockJwtWithReportScope() throws Exception {
        mvc.perform(get("/api/report")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_reports.read"))))
            .andExpect(status().isOk());
    }
}
```

Even though `@SpringBootTest` may load a real `JwtDecoder` bean and resource server config, the request above **does not invoke the decoder**. To test the decoder/filter, send a bearer header into MockMvc and assert the corresponding interactions/validations.

### 12.3 When Real Container HTTP Tests Are Required

MockMvc does not spin up a browser or a real HTTPS/TLS socket. If security depends on reverse proxies, `SameSite`/`Secure` cookies, TLS client certificates, browser redirects/SSO, or web frontend CORS/CSRF, add integration/E2E tests against an actual test server and browser. Keep a clear boundary between **MockMvc unit/slice tests** and **HTTP/browser/TLS protocols**.

## 13. Recommended Testing Matrix for Real Projects

| Boundary | Positive test | Negative test | Tool / component |
| --- | --- | --- | --- |
| OAuth2 controller | `oauth2Login()` sees expected user attrs | Missing authority → 403 | MockMvc post-processor. |
| OIDC controller | `oidcLogin()` supplies `OidcUser` and subject | Missing role/account mapping → 403 | MockMvc post-processor. |
| OAuth2 redirect/callback | Valid `state`/code exchange succeeds | Wrong `state`/redirect/session/code → fails | OIDC provider fixture/stub + login filters. |
| ID token validation | Signed token with right issuer/aud/expiry | Bad signature, expired, wrong issuer/aud/nonce | OIDC decoder/verification flow integration. |
| JWT authorization | `jwt().authorities(SCOPE_x)` → 200 | Wrong authority → 403 | MockMvc post-processor. |
| JWT decoder/filter | Valid bearer token decoded | Bad signature/exp/iss/aud/missing token → 401 | JWT Resource Server + decoder/test keys. |
| JWT converter | Claims produce expected authorities | Unrecognized role/scope claim → denied | Converter unit/integration test. |
| Opaque authorization | `opaqueToken().authorities(SCOPE_x)` → 200 | Missing scope → 403 | MockMvc post-processor. |
| Opaque introspection | `active=true` → principal/scopes | `active=false`/revoked/timeout/401/500 | Introspector + HTTP IdP stub. |
| CSRF for cookie-session POST | Identity + valid CSRF → processed | Identity without CSRF → 403 | MockMvc `csrf()` + browser contract test. |
| Service authorization | User allowed to read own resource | User A reading B's resource → 403 | Service security/integration test. |
| Session/OIDC persistence | After login, next request retains session | Logout/expired session → access denied | Real multi-request/session/browser test. |

**Two statuses with distinct meanings:**

- **401 Unauthorized:** usually unauthenticated or invalid credentials. On bearer JWT/opaque token APIs, 401 may occur when signature verification or introspection fails. For web login, unauthenticated requests may receive a **302 redirect** to the login page instead of 401.
- **403 Forbidden:** request is authenticated yet lacks permission, **or** a filter such as CSRF blocked it. Hence 403 alone does not prove a missing scope; inspect filter logs, responses, and the exact flow.

## 14. Common Mistakes When Writing Tests

| Symptom | Cause | Fix |
| --- | --- | --- |
| `jwt()` test is green yet live API returns 401 | Mock JWT skips decoder; real token has wrong issuer/signature/audience or filter is disabled. | Write a bearer-header integration test for JWT Resource Server. |
| `opaqueToken()` test is green despite revoked token | Mock skips introspection and still grants authorities. | Test introspector `active=false`/revoked and network errors. |
| `oidcLogin()` test is green despite callback state bug | Mock bypasses all redirects/callbacks. | Test OAuth2 Login filter/provider flow; verify `state`/`nonce`. |
| `@WithMockUser` makes `@AuthenticationPrincipal OidcUser` null | Principal is `User`, not `OidcUser`. | Use `oidcLogin()`. |
| Test uses `jwt().authorities(...)` while production converter is broken | Test overrode final authorities. | Unit/integration test the converter and real claims. |
| Test gets 200 even with Resource Server unconfigured | Mock already created `Authentication`; authorization still allows it. | Enable real Resource Server and test bearer headers separately. |
| MockMvc returns 403 instead of 401 | Missing HTTP Basic/Bearer entry point or blocked by CSRF. | Check `SecurityFilterChain`, entry point, request method, and CSRF policy. |
| Test runs bypassing `SecurityFilterChain` | `standaloneSetup` lacks `springSecurity()` or filters are disabled. | Use `@AutoConfigureMockMvc`/`springSecurity()` and verify filters. |
| Test fakes admin role yet real users lack permission | Assigned `ROLE_ADMIN` directly in test, missing IdP mapping. | Test authority mapper from provider claims/groups. |
| Mock login passes on one request, next request is anonymous | Post-processor only sets identity on that single test request. | Test real HTTP session/login persistence. |
| `oauth2Login` POST test returns 403 | Missing CSRF token or another blocking rule. | Add `with(csrf())` if not testing CSRF; test missing CSRF separately. |
| Mock JWT has claim yet authorities differ from expectation | Claims and authorities go through a converter; mock can override. | Assert final authorities and test the converter separately. |

## 15. Checklist When Choosing Simulation Scope

1. Read the production **`SecurityFilterChain`**: web login app or bearer API? JWT or opaque token? Multiple filter chains per route?
2. Pick the post-processor matching the actual principal type the controller expects, not the login provider's brand name.
3. Test **both positive and negative authority cases**; never only test that an authenticated request returns 200.
4. State clearly in test names whether it is "mock principal authorization" or "real bearer decoder/introspector"; avoid misleading names like `validJwtSignatureIsAccepted` when using `jwt()`.
5. Never treat `oidcLogin().idToken(...)` as a signature/nonce test, and never treat `opaqueToken().attributes(...)` as a revoked-token test.
6. When testing a converter, **do not override authorities** and claim the converter works.
7. When testing real HTTP authentication, send bearer headers through the Resource Server filter chain, or run redirect/callback through an OIDC provider fixture.
8. Ensure MockMvc integrates Spring Security, filters are not disabled, and tests hit the right `SecurityFilterChain`.
9. Separate **401 from authentication**, **403 from authorization**, and **403 from CSRF**; test all negative branches.
10. Add tests for session persistence, CSRF, claim mapping, tenant/resource ownership, and network failures per architecture.

**Takeaway:** `oauth2Login()`, `oidcLogin()`, `jwt()`, and `opaqueToken()` are tools for **constructing an authenticated identity** to test **HTTP request behavior and authorization** in Spring Security Servlet. They do not execute the OAuth2/OIDC protocol, do not verify JWT signatures, and do not call opaque-token introspection. A trustworthy security suite combines a **mock layer for business authorization** with an **integration layer for the authentication boundaries** the real application relies on.

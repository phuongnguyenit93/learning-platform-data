# Distinguishing Interactive Users from Service Accounts

## 1. Why does security design need to distinguish these two identity types?

A Spring Security application often serves two groups of actors simultaneously:

- **Interactive user:** a real person signing in and interacting via a browser or mobile app, potentially needing MFA, confirmation prompts, sessions, redirects, logout, and per-user permission management.
- **Service account / workload identity:** an identity issued to a process, job, container, microservice, or integration system to call APIs automatically; it has no human sitting in front of a screen to enter a password, solve a CAPTCHA, confirm MFA, or open a login page.

For example, in an order management system:

```text
Operations staff
   -> Browser -> /ui/orders
   -> Interactive login; cookie/session; employee-level permissions

Inventory sync worker
   -> HTTP API -> /api/m2m/inventory-sync
   -> Workload identity; short-lived access token; service-level permissions

Payment service
   -> HTTP API -> /api/m2m/payment-events
   -> Separate service identity; dedicated scope and audience
```

If every process uses a human account like `admin@example.com` or a shared username/password, the system runs into multiple problems: it is hard to trace who acted, hard to revoke a single integration independently, MFA gets bypassed easily, passwords must be stored in configs or pipelines, and services may be granted broader human permissions than needed.

**Principle:** *Identity reflects the principal performing the action.* An interactive user is a human; a service account is a workload. Permissions are granted according to actual duties and **never automatically carry over from one identity type to the other**.

This lesson belongs to **Spring Security – fundamentals / Application Design** and explains how to distinguish models, authentication/authorization mechanisms, endpoint design, credential lifecycle management, and testing. Examples are based on **Java 17+, Spring Boot 3.x, Spring Security 6.x Servlet**. For WebFlux, use `SecurityWebFilterChain` and the corresponding reactive APIs.

## 2. Comparing interactive users and service accounts

| Criterion | Interactive user | Service account |
| --- | --- | --- |
| Principal | A person, with onboarding/offboarding processes and verifiable human identity. | An app, worker, deployment, job, or integration with an operational owner. |
| Active time | When the user opens a page, signs in, or clicks a button. | On a schedule, queue, event, or automated 24/7 calls. |
| Common authentication methods | Form login + session, passkeys, federated OIDC Authorization Code + PKCE. | OAuth 2.0 Client Credentials, mTLS/workload identity, platform-issued tokens. |
| Credential provider | The user and a trusted device/browser per the model. | The workload's runtime/secret manager/identity provider. |
| MFA | Can be enforced based on risk and human policies. | Does not require a human to enter an OTP on every job run; uses workload identity security. |
| Session | Typically has session cookies, CSRF, logout, and timeouts. | Typically calls APIs with short-lived Bearer tokens in headers, without browser sessions. |
| Permissions | Roles/permissions per user and business context. | Scopes/permissions per service, API, environment, and task. |
| Revocation | Lock account, reset password, revoke user sessions/tokens. | Disable client/workload, rotate secret/certificate, revoke tokens, and replace deployment. |
| Auditability | Who performed the action, on which object, under which session context. | Which workload/client called, from which deployment, for which task. |
| Browser | Can render UI, redirects, CORS, cookies, SameSite, CSRF. | Does not need login pages, browser cookies, or redirects to an IdP to obtain tokens. |
| Testing | Login, MFA/session, CSRF, user permissions, logout. | Token issuance, issuer/audience/scope/client identity, rotation, access denied. |

Not every system fits strictly into those two shapes: a mobile app has an interactive user yet may still call APIs with Bearer access tokens; a service account can use certificates instead of JWTs; a user may trigger a job carrying delegated permissions. Therefore, **principal type and token transport are two distinct dimensions**. Never conclude "JWT always means service" or "cookie always means human" solely from how credentials are transmitted.

## 3. Distinguishing authentication, principal, authorities, and authorization

Spring Security builds its security context around the `Authentication` object:

- `principal` represents the authenticated identity. With form login it may be `UserDetails`; with a JWT Resource Server it is typically `Jwt` via `JwtAuthenticationToken`.
- `credentials` represents the input authentication material. The application should never log or display this value.
- `authorities` is the mapped set of permissions, such as `ROLE_USER` or `SCOPE_jobs.write`.
- `Authentication.isAuthenticated()` represents the authentication state of that token; it is **not sufficient on its own** to decide authorization. Anonymous authentication has its own characteristics and must not be treated as a signed-in user just because of a flag.
- `AuthorizationManager` or authorization expressions evaluate **principal, authorities, request, and policy** to allow or deny operations.

For example, a user and a service might both carry a generic `read` permission, but that does not mean both may call the same endpoint. Many applications require **two conditions simultaneously**:

1. **The right identity kind** (human or service) attested by a trusted issuer.
2. **The right permissions and resource scope** (scope, role, audience, tenant, object) permitted.

A service token with `SCOPE_jobs.write` must not substitute for a user session to access an admin page; a user with `ROLE_USER` is likewise not automatically permitted to submit automated jobs to an M2M endpoint.

### 3.1. Claim names are not a universal standard

In JWT tokens, `sub` (subject) is a standard claim, but **it is not enough to infer whether the principal is a human or a machine**. One provider may set `sub` to a user ID, while another sets it to a client ID or service principal ID. Claims like `client_id`, `azp`, `scp`, `scope`, and `grant_type` follow conventions that depend on the issuer and protocol; **never assume every access token contains all of those fields**.

If the system needs to check the principal kind directly, agree with the Identity Provider/Authorization Server on a trusted claim, for example **`principal_kind: "service"` or `"human"`**, and ensure the issuer **only issues each value to the corresponding principal type**. This claim is an **example convention**, not a mandatory OAuth2/OIDC claim.

**Never trust arbitrary client-sent headers or bodies** such as `X-Principal-Type: service` or `{"isService": true}` to grant access. The principal kind must come from authentication whose signature, issuer, audience, and issuance policy have been verified.

## 4. Two authentication flows suited to the two actor types

### 4.1. Interactive user: browser and session

```text
Browser -> GET /login
Browser -> fill form or redirect to IdP/OIDC
Server/IdP -> authenticate user, possibly MFA
Browser -> receive protected session cookie
Browser -> GET /ui/home
Spring Security -> read session, check ROLE_USER and fine-grained permissions
```

When using form login/`HttpSession`, applications typically need:

- `Secure`, `HttpOnly`, appropriate `SameSite` session cookies, and HTTPS.
- CSRF protection for state-changing actions using browser auto-sent credentials.
- Session fixation protection, timeouts, logout, and concurrent session management when needed.
- Login throttling, MFA, or step-up authentication for risky operations.
- Authorization checks by user and business object, not merely "logged in."
- Never placing usernames/passwords, session IDs, or tokens in URLs or logs.

If integrating OIDC, **Authorization Code + PKCE** is the appropriate flow for supported client types; the IdP authenticates the human user, and the app creates a local session or uses tokens per its architecture. In a modern SPA, tokens may live in the frontend layer or in a Backend-for-Frontend (BFF) architecture; evaluate XSS, CSRF, cookies, CORS, and token storage according to the design.

### 4.2. Workload: OAuth 2.0 Client Credentials

```text
Worker (client_id + secret/certificate/workload identity)
      |
      | POST /oauth2/token, grant_type=client_credentials
      v
Authorization Server
      | Authenticate client, issue access token with audience/scope/TTL
      v
Worker
      |
      | POST /api/m2m/jobs
      | Authorization: Bearer <access_token>
      v
Spring Security Resource Server
      | Verify signature, timestamps, issuer, audience
      | Map scope to authority, check principal/client type
      v
API allows or denies
```

In the `client_credentials` grant, **the client acts on its own behalf**, not representing a recently logged-in user. There is no human password entry or mandatory browser redirect on each run. M2M tokens must have **minimal scopes and audience**, a short lifetime, and be issued by a trusted issuer.

Illustrative HTTP example (all values are fake):

```http
POST /oauth2/token HTTP/1.1
Host: identity.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64_FAKE_CLIENT_AUTH

grant_type=client_credentials&scope=jobs.write
```

A successful response typically returns `access_token` and `expires_in` per the protocol; never put real tokens into logs, URLs, or documentation. When using a client secret, protect it with a secret manager and TLS. Stronger mechanisms such as `private_key_jwt`, mTLS, or workload federation can reduce reliance on static secrets.

**Do not create a "technical employee" in the user table and have jobs log in via a form password** just to reuse the same controller. Human passwords, browser sessions, MFA, and offboarding processes are fundamentally different from workload identities.

### 4.3. Two scenarios that must not be conflated

- **Microservice A calls Microservice B to sync data on its own:** use A's service principal and permissions, without inventing an end user.
- **User Alice clicks "export report," and the backend calls service B:** you may need both to record Alice as the requesting principal and to authenticate backend A as the workload. If B's policy needs to know about Alice, use a **controlled delegation model** (delegation, on-behalf-of, or token exchange as supported by the IdP), rather than faking a `user_id` in JSON and treating it as an authenticated identity.

A "service account" does not automatically gain the right to act **as every user**. Delegation must have bounded scope, verifiable proof of authority, and dedicated auditing.

## 5. Designing APIs with clear human and machine boundaries

An auditable way to organize endpoints:

| URL group | Who may access | Recommended Authn/Authz |
| --- | --- | --- |
| `/ui/**` | Employees in browsers | Form/session or OIDC login; user roles and permissions. |
| `/api/user/**` | Users via frontend apps | Token/session per architecture; authorize by user subject. |
| `/api/m2m/**` | Workers, integrations, microservices | OAuth2 Bearer Resource Server; check client/workload identity, audience, and scope. |
| `/admin/**` | Privileged users with MFA/step-up | Stricter rules; do not treat service credentials as admins. |
| `/actuator/**` | Authorized operations systems | Separate access path/auth method, never arbitrarily public. |

What matters is not the **URL name** `/api/m2m` magically making an endpoint secure. You must define the `SecurityFilterChain`, accepted authentication types, and backend policies. You can use **one chain** with per-endpoint `AuthorizationManager`s, or **multiple chains** when browser/session and stateless Bearer mechanics differ significantly.

**Common multi-chain trap:** `FilterChainProxy` selects **the first `SecurityFilterChain`** matching the request. The chain for `/api/m2m/**` must take precedence before the fallback chain, and the fallback chain must cover remaining paths. If an endpoint matches no chain, it may bypass security filters altogether.

Do not just write `hasAuthority("SCOPE_jobs.write")` for both human and service flows if policy also requires **the right principal kind**. Combine principal type, client identity, and appropriate permissions to prevent confused-deputy vulnerabilities.

## 6. Spring Boot 3.x example: separating browser and service APIs with two filter chains

This example illustrates an application that serves both a user UI and automated calls from services. The focus is on **authorizing the right identity type**, not building a new Identity Provider.

**Service token verification contract for this example:**

- A trusted token issuer issues JWTs with `principal_kind = "service"` for client credentials, and never issues that claim to human users.
- The allowed service client in the example has `client_id = "batch-worker"`.
- Access tokens targeting the API must contain `inventory-api` in `aud`.
- The minimum permission is `scope = "jobs.write"`, which Spring Security converts into `SCOPE_jobs.write`.
- JWTs must be verified for signature via the issuer's JWKs, timestamps, issuer, and audience.
- These claim names and values **are a custom contract chosen for the demo app**, not a guarantee that every OAuth provider produces identical tokens. In production, configure your IdP to uphold the contract and verify issuer metadata.

The browser UI still uses form login with `HttpSession`. The machine API does not accept user cookies as login credentials, does not create sessions, and never returns login redirects.

### 6.1. Dependencies and project layout

A Spring Boot 3.x, Java 17+ Gradle project needs these starters:

```groovy
// Excerpt in build.gradle (Groovy DSL) of a project that already has the Boot plugin.
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

The Java files share package `demo.identityboundary`. This code compiles in a compatible Spring Boot project; **to call it for real with a Bearer token requires an IdP issuing tokens with matching issuer/JWK configuration**. The test suite mocks JWTs at the test boundary without calling an external IdP.

### 6.2. Main class

`src/main/java/demo/identityboundary/IdentityBoundaryApplication.java`:

```java
package demo.identityboundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class IdentityBoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(IdentityBoundaryApplication.class, args);
    }
}
```

### 6.3. Issuer/JWK configuration

`src/main/resources/application.yml`:

```yaml
app:
  security:
    issuer-uri: "${M2M_ISSUER_URI:https://idp.example.invalid/realms/demo}"
    jwk-set-uri: "${M2M_JWK_SET_URI:https://idp.example.invalid/realms/demo/protocol/openid-connect/certs}"
```

**Replace the two placeholder URLs with the official issuer and JWK Set URI provided by your IdP** before running end-to-end tests. The `.invalid` domain is used as an illustrative placeholder so it never accidentally points to a real system. When running Gradle tests in this guide, the tests use `spring-security-test` and make no network calls to these URLs.

### 6.4. Spring Security configuration

`src/main/java/demo/identityboundary/SecurityConfig.java`:

```java
package demo.identityboundary;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain machineApi(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/m2m/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            // Only the M2M chain uses a Bearer token in the header and does not
            // use cookies as an automatic authentication mechanism.
            .csrf(csrf -> csrf.disable())
            .authorizeHttpRequests(auth -> auth
                .anyRequest().access((authentication, request) -> {
                    Authentication current = authentication.get();

                    if (!(current instanceof JwtAuthenticationToken jwtAuth)) {
                        return new AuthorizationDecision(false);
                    }

                    Jwt jwt = jwtAuth.getToken();
                    boolean serviceIdentity =
                        "service".equals(jwt.getClaimAsString("principal_kind"))
                        && "batch-worker".equals(jwt.getClaimAsString("client_id"));

                    boolean correctAudience =
                        jwt.getAudience().contains("inventory-api");

                    boolean correctPermission = jwtAuth.getAuthorities()
                        .stream()
                        .anyMatch(authority ->
                            "SCOPE_jobs.write".equals(authority.getAuthority())
                        );

                    return new AuthorizationDecision(
                        serviceIdentity && correctAudience && correctPermission
                    );
                })
            )
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browser(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/logout", "/error").permitAll()
                .requestMatchers("/ui/**").hasRole("USER")
                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                .defaultSuccessUrl("/ui/home", true)
            )
            .logout(Customizer.withDefaults());

        // Do not disable CSRF on the browser chain.
        return http.build();
    }

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.issuer-uri}") String issuer,
            @Value("${app.security.jwk-set-uri}") String jwkSetUri
    ) {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(jwkSetUri).build();

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains("inventory-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Token audience is not accepted",
                        null
                    )
                );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                audience
            )
        );
        return decoder;
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build()
        );
    }
}
```

**Key explanatory points:**

1. `machineApi` has `@Order(1)` and `securityMatcher("/api/m2m/**")`, so M2M requests are routed into this chain and do not fall through to the browser chain. `browser` serves as the fallback so remaining URLs still have protective policies.
2. `SessionCreationPolicy.STATELESS` prevents using sessions to maintain `SecurityContext` on the M2M chain. There is no form login or HTTP Basic on the M2M chain.
3. CSRF is disabled **only on the M2M chain**, assuming this API authenticates solely via Bearer tokens explicitly placed in `Authorization`, **not** via auto-sent cookies. If an M2M endpoint ever accepts browser cookies or another auto-sent credential, CSRF must be re-evaluated.
4. The browser chain retains default CSRF, form login, and `HttpSession`, suited for interactive users.
5. `JwtDecoder` uses JWKs from the issuer to verify signatures and validators to check issuer/timestamps/audience. Only accept tokens from a trusted IdP; never Base64-decode a JWT yourself and treat claims as verified.
6. `JwtAuthenticationToken` and service claims are checked during authorization. A human user token carrying `SCOPE_jobs.write` with `principal_kind="human"` will be rejected.
7. `client_id="batch-worker"` is an allowlist demonstrating one workload. Real apps can use rules configured per client, scope, object, tenant, and operation; do not hardcode every client in one giant function.
8. `SCOPE_jobs.write` appears when the default `JwtGrantedAuthoritiesConverter` reads matching `scope`/`scp` claims. If the IdP uses a different claim, configure a controlled converter without arbitrarily elevating privileges.
9. The `principal_kind` claim is a **custom claim** trustworthy only when the issuer guarantees human tokens cannot spoof the service value. If your IdP does not support this, choose another issuer-attested service identification mechanism and test the constraint.
10. Browser `Logout` only ends the user's configured session. It **does not automatically revoke M2M access tokens** held by another worker.

**Important scope warning:** Real production Bearer tokens also need signing algorithm policies, key checks, issuer checks, and other environment-specific controls. This lesson illustrates verification principles at the Resource Server; it does not build an Authorization Server or claim that placeholder JWK URLs issue real tokens.

### 6.5. Illustrative data-separating controller

`src/main/java/demo/identityboundary/DemoController.java`:

```java
package demo.identityboundary;

import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
public class DemoController {

    @GetMapping("/ui/home")
    public Map<String, String> home(Authentication authentication) {
        return Map.of("interactiveUser", authentication.getName());
    }

    @PostMapping("/api/m2m/jobs")
    public Map<String, Object> submitJob(Authentication authentication) {
        JwtAuthenticationToken service = (JwtAuthenticationToken) authentication;
        return Map.of(
            "accepted", true,
            "clientId", service.getToken().getClaimAsString("client_id")
        );
    }
}
```

The controller never reads `client_id` or `principal_kind` from the request body, query string, or an arbitrary caller-supplied header. The service identity comes from the `Authentication` verified by the Bearer chain, and the request has already passed the `AuthorizationManager` before reaching the controller.

In real systems, **never** rely solely on URL/role checks while skipping per-object permission checks; if a service is allowed to modify a tenant's data, the backend must enforce tenant/ownership policies and resource scope where the operation runs.

## 7. MockMvc tests: right permissions with the wrong identity kind still fail

The testing goal is to prove **the human–machine separation boundary**, not merely test a successful service token. `spring-security-test` provides `jwt()` and `user()` to construct test `Authentication` objects. These helpers **do not verify JWT signatures**; they are suitable for testing authorization and filter chains, while integration tests with real tokens are still needed to verify decoders, issuers, audiences, and key rotation.

File `src/test/java/demo/identityboundary/IdentityBoundaryTests.java`:

```java
package demo.identityboundary;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.RequestPostProcessor;

import java.util.List;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.redirectedUrlPattern;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class IdentityBoundaryTests {

    @Autowired
    MockMvc mvc;

    @Test
    void browserWithoutLoginMustRedirectToLogin() throws Exception {
        mvc.perform(get("/ui/home"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void browserHumanUserCanAccessUi() throws Exception {
        mvc.perform(get("/ui/home").with(user("reader").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.interactiveUser").value("reader"));
    }

    @Test
    void realFormLoginFlowIsAvailableForHumanUser() throws Exception {
        mvc.perform(formLogin().user("reader").password("demo-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/ui/home"));
    }

    @Test
    void machineEndpointWithoutBearerIs401() throws Exception {
        mvc.perform(post("/api/m2m/jobs"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validServiceIdentityAndScopeCanSubmitJob() throws Exception {
        mvc.perform(post("/api/m2m/jobs")
                .with(token("service", "batch-worker",
                            "jobs.write", "inventory-api")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.accepted").value(true))
            .andExpect(jsonPath("$.clientId").value("batch-worker"));
    }

    @Test
    void humanJwtIsNotAcceptedAsServiceEvenWithSameScope()
            throws Exception {
        mvc.perform(post("/api/m2m/jobs")
                .with(token("human", "batch-worker",
                            "jobs.write", "inventory-api")))
            .andExpect(status().isForbidden());
    }

    @Test
    void serviceWithoutRequiredScopeIsDenied() throws Exception {
        mvc.perform(post("/api/m2m/jobs")
                .with(token("service", "batch-worker",
                            "jobs.read", "inventory-api")))
            .andExpect(status().isForbidden());
    }

    @Test
    void differentServiceClientIsDenied() throws Exception {
        mvc.perform(post("/api/m2m/jobs")
                .with(token("service", "unknown-worker",
                            "jobs.write", "inventory-api")))
            .andExpect(status().isForbidden());
    }

    @Test
    void wrongAudienceIsDenied() throws Exception {
        mvc.perform(post("/api/m2m/jobs")
                .with(token("service", "batch-worker",
                            "jobs.write", "other-api")))
            .andExpect(status().isForbidden());
    }

    @Test
    void BrowserSessionIdentityCannotBecomeServiceIdentity()
            throws Exception {
        mvc.perform(post("/api/m2m/jobs")
                .with(user("reader").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void machineTokenDoesNotGrantHumanUiRole() throws Exception {
        mvc.perform(get("/ui/home")
                .with(token("service", "batch-worker",
                            "jobs.write", "inventory-api")))
            .andExpect(status().isForbidden());
    }

    @Test
    void unknownUrlIsDeniedByFallbackChain() throws Exception {
        mvc.perform(get("/not-an-api"))
            .andExpect(status().isForbidden());
    }

    private RequestPostProcessor token(
            String kind,
            String clientId,
            String scope,
            String audience
    ) {
        return jwt().jwt(builder -> builder
            .claim("principal_kind", kind)
            .claim("client_id", clientId)
            .claim("scope", scope)
            .claim("aud", List.of(audience))
        );
    }
}
```

Run:

```bash
./gradlew test --tests demo.identityboundary.IdentityBoundaryTests
```

**Expected outcome:** All 12 tests PASS in a compatible Spring Boot project when classes and dependencies are set up properly. This document **does not claim to have executed the tests**. Certain status/redirect policies may differ if extra configuration is added; in that case keep the testing goal while updating assertions to match the real contract.

| Test group | What it proves |
| --- | --- |
| Unauthenticated browser | Interactive user flow redirects to login; never silently grants access. |
| Browser with `ROLE_USER` | User with the right role accesses the UI without needing a machine Bearer token. |
| Real form login | Login with CSRF/test helper works on the browser chain. |
| M2M without Bearer | Cannot "borrow" service permissions using a browser session; returns 401. |
| M2M token with right claim/client/aud/scope | Request is accepted and bound to the right service client. |
| Human JWT carrying service scope | Returns 403, proving both permission and identity kind matter. |
| Service missing scope | Returns 403; access is not granted merely for being a service. |
| Service with different client ID | Returns 403; prevents every workload with the same scope from sharing privileges. |
| Service with wrong audience | Returns 403; tokens meant for another API are rejected. |
| Mock user session calling M2M | Rejected because the `Authentication` type is not a service JWT. |
| Mock service JWT calling UI | Rejected because it lacks the browser role. |
| Undeclared URL | Fallback chain denies rather than accidentally exposing it publicly. |

**Core limitation of `jwt()` in MockMvc:** the helper can build an `Authentication` with any claims the test supplies. Thus, these cases verify **authorization logic and chain separation**, not whether an attacker can forge a JWT signature. In staging, add tests with real issuer-signed tokens, invalid signatures, expired tokens, wrong issuers, wrong audiences, key rotation, and cases where the IdP emits invalid claims; invalid tokens must fail in `JwtDecoder`.

**Distinguish authorization testing from token-issuance testing.** The Resource Server only receives and verifies tokens. Whether a service actually receives the right `client_credentials` token with an unforgeable `principal_kind` claim and minimal scopes must be verified at the Authorization Server and in IdP integration tests.

## 8. When a service needs to obtain tokens itself: outbound OAuth2 client

The application in section 6 is a **Resource Server receiving tokens**. A worker calling an API acts as an **OAuth2 Client requesting tokens**, which requires different configuration. Do not mix these two responsibilities:

```text
[Worker: OAuth2 Client]   -- request token --> [Authorization Server]
[Worker: OAuth2 Client]   -- Bearer ---------> [API: Resource Server]
```

In the separate worker application, use `spring-boot-starter-oauth2-client` and configure a client registration:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
```

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory-worker:
            provider: company-idp
            client-id: "${M2M_CLIENT_ID}"
            client-secret: "${M2M_CLIENT_SECRET}"
            authorization-grant-type: client_credentials
            scope: jobs.write
        provider:
          company-idp:
            token-uri: "${M2M_TOKEN_URI}"
```

Never hardcode a real `client-secret` in the repository. For a worker running outside an HTTP request, you can use `AuthorizedClientServiceOAuth2AuthorizedClientManager` instead of a manager that depends on `HttpServletRequest`/`HttpServletResponse`:

```java
// Configuration excerpt in a separate worker app (does not replace SecurityConfig).
@Bean
OAuth2AuthorizedClientManager authorizedClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientService clients
) {
    AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
        new AuthorizedClientServiceOAuth2AuthorizedClientManager(
            registrations, clients
        );
    manager.setAuthorizedClientProvider(
        OAuth2AuthorizedClientProviderBuilder.builder()
            .clientCredentials()
            .build()
    );
    return manager;
}
```

Corresponding imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
```

A worker can request a token from the manager:

```java
OAuth2AuthorizeRequest request = OAuth2AuthorizeRequest
    .withClientRegistrationId("inventory-worker")
    .principal("inventory-worker")
    .build();

OAuth2AuthorizedClient authorized = manager.authorize(request);
if (authorized == null) {
    throw new IllegalStateException("Unable to authorize worker client");
}
String token = authorized.getAccessToken().getTokenValue();
// Send token in Authorization: Bearer ... over HTTPS to the target API.
// Do not log this token or put it in URLs.
```

This is a **usage excerpt inside a worker app with a configured manager and client registration**, not a standalone `javac` program. The manager manages access tokens and renews them per the configured provider; the obtained token must be sent via the HTTP client header, with controlled TTL and never written to logs.

**Practical note:** `client_credentials` typically does not provide refresh tokens the way user flows do; the worker requests a new access token when needed. Token caching, retry, and rate-limiting mechanisms must align with the Authorization Server. When using workload federation or mTLS instead of a secret, client authentication configuration changes accordingly, while the human–machine separation principle remains unchanged.

## 9. Authorization policy: identity kind, scope, and resources

A sound authorization decision does not merely ask "is the token valid?" It may include:

1. **Issuer**: who issued the token? Is it on the trusted IdP allowlist?
2. **Audience**: which API is the token meant for? A token for API A must not work by default on API B.
3. **Principal kind**: human or workload, attested by the issuer under the contract?
4. **Client ID/workload ID**: which exact service is this? Is it allowed to invoke this function?
5. **Authority/scope**: permission for the specific endpoint, method, and action.
6. **Target resource**: is the service allowed to act on this tenant/project/order?
7. **Status**: is the account locked, credential revoked, deployment retired, or token expired?
8. **Risk context**: environment, mTLS connection, policy-trusted IP/network, or step-up user authentication requirements.

For example, the `jobs.write` scope should only grant job creation within defined boundaries, never letting the worker read all user profiles or administer accounts. If an action must run on behalf of user Alice, attach attested delegation context rather than arbitrarily swapping `sub` in the request body.

**Least privilege** applies to both sides: employees only get necessary roles; services only get necessary APIs/scopes, short TTLs, and distinct credentials per app/environment. Separate `inventory-worker-dev` and `inventory-worker-prod` service identities; never share the same secret across environments.

## 10. Service account lifecycle and secret management

Service accounts also need owners, issuance dates, scopes, revocation policies, and auditing. A sample audit table:

| Attribute | What must be defined |
| --- | --- |
| Owner | Team owning the workload and approver of permissions. |
| Purpose | Which job/integration and which endpoints are genuinely needed. |
| Issuer and audience | Which Authorization Server, and which API the token targets. |
| Scopes | Minimal list; never share default admin scopes. |
| Authentication method | Workload identity, mTLS, `private_key_jwt`, or a protected secret. |
| Secret storage | Secret manager, vault, or identity platform; never committed to repos. |
| Lifecycle | Provisioning, rotation, revocation, and decommissioning once unused. |
| Audit | Client ID, workload/deployment, trace ID, operation, result; never log raw tokens. |
| Incident response | Disable client, revoke tokens if supported, rotate secret, review activity logs. |

Never use `Authorization: Basic` with a real human user's password for a cron job. If temporarily inheriting a legacy system without OAuth2, use a dedicated system account with restricted permissions, secure secret storage, TLS transport, and a migration path to standard workload identity.

If a service secret leaks, "logging out of the browser" does not revoke it. You must disable or rotate the credential at the issuer, handle still-valid access tokens per committed revocation capabilities, and deploy the new secret/certificate.

### 10.1. Service accounts are not "unowned" by default

Every service account must have an **owner** and a chain of accountability. "Non-interactive" means the process runs automatically, **not** that it needs no approval, audit, or periodic review. When an owner leaves the project, ownership must be transferred. If no workload uses a credential anymore, disable it instead of leaving the account around forever.

### 10.2. Application secrets and user tokens must not be mixed

Do not hand a user's refresh token to a long-running job unless the design includes proper delegation and revocation. Do not use a service API key as a user session ID. Different credential types have different lifetimes and revocation semantics; sharing one value across roles widens the blast radius on compromise.

## 11. Logging and observability: record the right actor, never the secret

A system with both users and services must distinguish **who initiated the request**, **which service handled it**, and **whether another user is being represented**.

An audit record might store:

```json
{
  "actorType": "service",
  "clientId": "batch-worker",
  "operation": "jobs.create",
  "resource": "inventory",
  "decision": "ALLOW",
  "correlationId": "sample-correlation-id",
  "environment": "test"
}
```

This is illustrative data; in production, minimize PII and enforce appropriate retention windows. For user actions, `actorType` may be `human`, along with a log-safe user identifier. For delegation, you may need **both** the user subject and the calling service alongside the verified delegation relationship.

**Never log** `Authorization`, raw JWTs, `Cookie`, `Set-Cookie`, client secrets, private keys, or raw bodies containing credentials. JWT claims may contain PII; extract only minimal vetted fields. A correlation ID used for log tracing must never carry a token or session ID value.

On 401/403 errors, responses should use public status codes and error codes without leaking internal details like secret role names, issuer key paths, or unverified tokens. For a Bearer Resource Server, keep `WWW-Authenticate` compliant with the protocol; never replace a 401 with 200 just to stop a frontend warning.

## 12. Common mistakes

1. **Using a real person's account as a service account.** Giving a password to a cron job or webhook leaves credentials outside user lifecycle processes and breaks MFA and auditing.
2. **Sharing one client ID/secret across all services.** When a secret leaks or needs revocation, you cannot isolate the incident or tell which job made a call.
3. **Granting the ADMIN role to a service because "the job needs to run."** Replace with minimal scope/resource permissions and separate privileged endpoints.
4. **Confusing `sub` with principal kind.** A JWT subject can represent a human or a client depending on the issuer. Require an attested claim/metadata contract.
5. **Trusting a client-supplied `principal_kind`.** Trust only claims signed by an authoritative issuer protected against self-assertion.
6. **Checking only `SCOPE_jobs.write` while ignoring actor/client/audience.** Tokens meant for another API or principal can be abused out of context.
7. **Using a user token for a service without delegation.** The service may inherit improper privileges or lose audit traceability to the delegating source.
8. **Disabling browser CSRF just because M2M APIs use Bearer tokens.** Each chain has its own credential model; never disable CSRF application-wide.
9. **Enabling form login on an M2M API and returning 302 HTML login.** Workers expect an HTTP/token contract, not an interactive human flow.
10. **Confusing Spring OAuth2 Client with Resource Server.** The Client requests and sends tokens; the Resource Server receives and verifies tokens.
11. **Assuming MockMvc `jwt()` proves real signatures/tokens are valid.** The helper injects a mock authentication at the test boundary; test decoders and IdPs separately.
12. **Having no fallback `SecurityFilterChain`.** URLs that match no chain may bypass Spring Security protection.
13. **Never rotating or disabling old service accounts.** Unused credentials remain an attack vector.
14. **Logging tokens "for easier debugging."** Tokens and secrets must be redacted at collection time, not merely hidden in a dashboard UI.
15. **Equating logout with revocation.** Logging out a user's `HttpSession` does not invalidate a worker's `client_credentials` access token.

## 13. Design and acceptance testing checklist

| Check | Interactive user | Service account |
| --- | --- | --- |
| Identity kind | User identity verified via login/IdP. | Workload/client identity attested by issuer. |
| Right auth channel | Form/session, OIDC code flow, cookies, and proper CSRF. | Token header or certificate/workload identity; no form login. |
| Endpoint scope | Users cannot "borrow" service APIs via generic roles alone. | Services cannot enter human UI/admin routes with a valid token. |
| Least privilege | Role/resource ownership, MFA/step-up when needed. | Scope, client allowlist, audience, and tenant per workload. |
| Lifecycle | Logout, session timeout, lock/reset, offboarding. | Expire/rotate/revoke tokens/secrets; disable unused workloads. |
| Log data | Human actor, resource, outcome; no session/cookie values. | Client/workload ID, operation, trace; no raw tokens/secrets. |
| Negative cases | Anonymous, missing role, bad CSRF, locked user. | Missing/invalid Bearer, missing scope, wrong client, wrong audience, expired token. |
| Real integration | Real browser, cookies, IdP, OAuth redirects. | Client credentials grant, IdP/JWK, key rotation, mTLS/secret store. |

**Pre-acceptance design questions:**

- If an employee leaves, can their account be locked **without** stopping legitimate workers?
- If a worker is compromised, can that worker's credential be revoked **without** locking out all users?
- Can a valid service token automatically enter the human admin UI? **Expected answer: no.**
- Can a human access token whose scope happens to match a service scope perform a worker's job? **No, if policy requires principal separation and it is implemented properly.**
- Without an IdP in tests, are MockMvc tests verifying **authorization rules** or mistakenly claiming JWTs were cryptographically verified?
- Do audit events capture the actual user or client actor, distinct from caller-supplied `userId`/`clientId` values?

## 14. Practice exercise

A system has three tasks:

1. **Alice opens the order statistics page.** Bind a user identity, check Alice's roles and data/tenant permissions. Consider requiring MFA for sensitive statistics.
2. **A job runs every 15 minutes to import inventory.** Provision a dedicated service principal with only the `inventory.write` scope, `inventory-api` audience, and a short-lived token. Never use Alice's account or an admin password.
3. **Alice clicks approve on a transaction, and the backend dispatches a command to a third service.** The backend authenticates as a workload when calling the service, while business logic retains an audit trail showing Alice made the decision. If the target service must check Alice's permissions, use an issuer-supported delegation/on-behalf-of mechanism rather than placing `userId=alice` in the body and trusting it blindly.

Write minimal tests for each case: valid principal and permissions succeed; wrong principal kind is rejected; missing permissions are rejected; wrong audience/issuer tokens are rejected; audit logs contain no secrets; disabling one service does not affect users or other services.

**Conclusion:** interactive users and service accounts are **two distinct principal types** with different authentication methods, authorities, lifecycles, and audit trails. Spring Security lets you combine form/session and Resource Server on separate `SecurityFilterChain` beans, yet the boundary is only truly secure when the backend verifies **the right principal, right kind, right audience, right permissions, and right resources**.

## References

- Spring Security — [Java Configuration and multiple SecurityFilterChain](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html).
- Spring Security — [OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- Spring Security — [OAuth 2.0 Client Credentials](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html).
- Spring Security — [Spring Security Test: OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html).
- Spring Security — [Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html).
- OAuth 2.0 — [RFC 6749, Client Credentials Grant](https://www.rfc-editor.org/rfc/rfc6749#section-4.4).
- OAuth 2.0 Security Best Current Practice — [RFC 9700](https://www.rfc-editor.org/rfc/rfc9700).
- OAuth 2.0 JWT Access Token Profile — [RFC 9068](https://www.rfc-editor.org/rfc/rfc9068).
- OWASP — [Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html).
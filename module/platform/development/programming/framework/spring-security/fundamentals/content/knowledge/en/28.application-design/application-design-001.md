# Choosing an Authentication Model by Client Type and Product Requirements

> **Scope:** Designing authentication mechanisms in Spring Security applications using Java 17+ and Spring Boot 3.x. Decisions should be based on client type, where secrets can be kept, product experience, permission granting/revocation capabilities, and operational needs. The session, OIDC, BFF, Resource Server, and machine-to-machine options below are **models to choose from**, not configurations that must all be enabled at once.

## 1. The problem: multiple clients, multiple trust boundaries

A system has an employee portal, a customer SPA, iOS/Android apps, and a midnight batch job. If all of them are forced to use the same long-lived JWT or a shared username/password, the system runs into different problems: browsers risk token exposure during XSS; mobile apps cannot keep a shared client secret; batch jobs have no end-user identity; and logout and permission revocation become unpredictable.

Before choosing technology, you must answer:

1. **Who sends the request?** An interactive user, an application/partner, or an automated task?
2. **Where does the client run?** Server-rendered web, SPA in a browser, native mobile, desktop, CLI, keyboard-less device, server, or webhook?
3. **Who can hold secrets?** Only a backend controlled by the team can protect a client secret/private key. JavaScript in a browser and mobile binaries distributed to users are both **public client** environments.
4. **Who manages identities?** Local accounts or an IdP with OIDC, SSO, MFA, passkeys, account recovery, and deprovisioning?
5. **Where is the API called from?** Same-origin/browser cookie, browser calling API directly, mobile Bearer token, or server-to-server?
6. **Is the data sensitive?** Are there roles, owner/tenant rules, audit requirements, financial operations, step-up MFA checks, or very short permission revocation windows?
7. **What does operations require?** Session store, SSO logout, revocation, rotation, token introspection, IdP outage handling, scale, and latency?

**Well-grounded decision:** "Internal web portal running on the same origin, requiring SSO/MFA, chooses OIDC Login + server-side session, secure cookies, CSRF, and data authorization checks." **Ungrounded decision:** "REST APIs must definitely use JWT."

## 2. Terminology you must distinguish

| Concept | Purpose | Do not confuse with |
| --- | --- | --- |
| Authentication | Verifies who the principal is. | Permission to view all resources. |
| Authorization | Decides which actions/resources are allowed. | Only checking `authenticated()`. |
| HTTP session | Server-side login state; browsers typically send the session ID in a cookie. | A self-contained JWT with claims. |
| Cookie | Data the browser automatically sends per domain/site/path policy. | Verified access permissions. |
| OAuth 2.0 | An **authorization** framework for clients to obtain an access token to call a protected resource. | A complete user-identity login standard. |
| OpenID Connect (OIDC) | An identity/login layer on top of OAuth2 with an ID token and identity claims. | An access token for calling APIs. |
| Access token | A credential for calling a Resource Server with the right audience/scope. | An ID token issued to an OAuth client. |
| ID token | OIDC proof of identity authentication for the client to handle sign-in. | A credential replacing an access token sent to every API. |
| Refresh token | A credential exchanged for a new access token per grant policy. | Data allowed to be stored arbitrarily in JavaScript/`localStorage`. |
| JWT | A token format carrying claims, typically digitally signed for resource server verification. | A standalone login model or revocation solution. |
| Opaque token | A token the API does not need to inspect directly, typically verified via introspection. | Inherently less secure than JWT by default. |
| Role / authority / scope | Ways of representing functional permissions. | Record ownership or organization membership. |

Example: a user is authenticated and has `SCOPE_orders.read`, but order ID 42 belongs to another tenant. That scope **does not by itself** prove the user may view order 42. The backend must check membership/owner and use queries filtered by `owner_user_id` or `authorized_org_id`.

An application acts as an **OAuth2 Client** when sending users to an IdP or requesting tokens; it acts as a **Resource Server** when receiving and verifying Bearer tokens for APIs. Spring Security Resource Server does not create a login screen on its own, and merely adding OAuth2 Client does not make the backend issue tokens itself.

## 3. Quick selection matrix

| Client type | First model to consider | Credential held by client | Security conditions |
| --- | --- | --- | --- |
| Same-origin server-rendered web | Session cookie + form login or OIDC Login. | Session ID in cookie. | HttpOnly, Secure, SameSite, CSRF, session timeout, logout, session fixation protection. |
| SPA with its own team-controlled backend | **Backend for Frontend (BFF)** + OIDC. | Browser only holds session cookie; BFF holds tokens server-side. | CSRF, XSS, server-side token storage, authorized proxy, and session lifecycle. |
| Pure browser SPA calling APIs directly | OAuth/OIDC **Authorization Code + PKCE**. | Bearer access token per short-lived storage policy. | Public client, PKCE S256, state/nonce, redirect URI, XSS, CORS. |
| Native iOS/Android | Authorization Code + PKCE via **system browser**. | Access/refresh tokens in OS secure storage. | No embedded client secret, token rotation/revocation, redirect protection. |
| Desktop/CLI with browser | Authorization Code + PKCE via browser/loopback. | Platform-protected token cache. | Redirect, PKCE, local storage, and logout. |
| TV/input-constrained device | Device Authorization Grant if supported by IdP. | Temporary device code, token after confirmation. | Code expiration, polling/rate limits, anti-phishing. |
| Job/service without an end user | Client Credentials or workload identity. | Secret/private key/mTLS on server only. | Least privilege, scope, audience, rotation, audit. |
| Partner/mobile API receiving Bearer tokens | OAuth2 Resource Server with JWT or opaque token. | `Authorization: Bearer` over HTTPS. | Issuer/audience/expiry/signature or introspection, permissions, tenant. |
| Inbound webhook | HMAC/public-key signature/mTLS per contract. | Request signature, not a browser session. | Timestamp/nonce, replay defense, idempotency. |

This is a **starting point**, not an absolute rule. A single product can use sessions for a portal, OIDC + PKCE for mobile, Bearer tokens for APIs, and Client Credentials for backend jobs. Each path must have its own `SecurityFilterChain` policy, data checks, and tests.

## 4. Step one: identify the actor and public vs. confidential client

**End users** need a login flow (local, SSO, or OIDC), session lifetime, MFA/recovery policy, and per-resource permissions. **Machines** need a dedicated workload identity; never borrow an employee account password and run a job as a "user."

A **public client** (SPA/native app) cannot protect a shared client secret. Compiling an APK or minifying JS does not turn that code into a trusted secret store. A **confidential client** is a team-managed server that can use a secret manager, private key, mTLS, and reliable client authentication.

For the OAuth2 Authorization Code Grant, public clients use **PKCE S256**. Do not use Implicit Grant or Resource Owner Password Credentials Grant for new designs: OAuth2 Security Best Current Practice RFC 9700 highlights token/credential leakage risks and requires protecting the authorization code. For OIDC, handle `state`, `nonce`, issuer, audience, and redirect URI according to your provider/library.

## 5. Step two: choose where to store login state and access tokens

### 5.1. Session + cookie for same-origin web

Basic flow:

```text
Browser                    Spring Boot server
  | GET /me                       |
  |------------------------------>|
  |<---------- 302 /login --------|
  | POST /login + CSRF token      |
  |------------------------------>|
  |   verify username/password    |
  |<---- Set-Cookie: JSESSIONID --|
  | GET /me + session cookie      |
  |------------------------------>|
  |<------------- 200 ------------|
```

The session ID **only references** server-side state and does not contain a password. Advantages: simple for a single-backend product, logout and invalidation are easy to model, and browser JS does not need to hold a Bearer token. Trade-offs: you must manage the session store, idle timeout, clustering, cookie policy, and CSRF.

**Production cookies:** `HttpOnly` prevents JS from reading the cookie directly, though XSS can still invoke APIs using the session; `Secure` requires TLS; `SameSite` controls browser cross-site behavior and must be compatible with OIDC redirects. `SameSite` **does not completely replace** CSRF protection. For cookie-authenticated POST/PUT/PATCH/DELETE requests, you must have a CSRF token or appropriate CSRF defense.

**When to choose:** server-rendered web, same-origin portals, or apps with a trusted backend where the browser does not need an access token. If SSO is needed, the backend can use OIDC Login while still managing the browser session.

### 5.2. SPA + BFF keeping tokens server-side

A BFF is a server serving the SPA that performs OAuth/OIDC login and stores access/refresh tokens **outside browser JavaScript**. The browser sends a session cookie to the BFF; the BFF calls downstream APIs with an access token scoped to the right audience.

```text
Browser SPA             BFF backend              OIDC IdP       Downstream API
  | start login              |                        |              |
  |------------------------->|--- Authorization Code ->|              |
  |                          |<---- callback code -----|              |
  |                          |---- token request ----->|              |
  |                          |<---- access token ------|              |
  |<--- session cookie ------|                        |              |
  | GET /bff/orders + cookie |                        |              |
  |------------------------->|------ Bearer token ------------------->|
  |                          |<------- JSON -------------------------|
  |<---------- JSON ---------|                        |              |
```

Advantages: tokens do not have to be stored in `localStorage` or JS memory; refresh, session handling, and multiple APIs are centralized. Trade-offs: the BFF is a critical operational component that requires CSRF/XSS hardening, a session store, token storage, a least-privilege proxy, origin checks, and auditing.

**Warning:** `oauth2Login()` enables OIDC login but does not by itself build a complete BFF. A real BFF also needs an API proxy layer, OAuth2 authorized client/token lifecycle management, session-to-user mapping, logout, CSRF, and downstream error handling. Do not return the access token in JSON "for frontend convenience" if your goal is to keep tokens on the server.

### 5.3. Pure browser SPA that must call APIs directly

When a BFF is not feasible, the SPA is an OAuth2 public client, typically using Authorization Code + PKCE:

```text
SPA            Authorization Server             Resource API
 | code_challenge S256 + state |                      |
 |---------------------------->|                      |
 | user logs in at IdP         |                      |
 |<-------- code --------------|                      |
 | code_verifier to token      |                      |
 |---------------------------->|                      |
 |<-------- access token ------|                      |
 | Authorization: Bearer <access_token>               |
 |--------------------------------------------------->|
 |<------------------- response ----------------------|
```

PKCE protects the code from being used by someone who only intercepts the authorization code. Do not put a client secret in JS, do not use the implicit flow, and do not collect user passwords directly to call the password grant. Register exact redirect URIs; implement `state` and OIDC `nonce` per your SDK.

**Tokens in the browser:** XSS can steal tokens from `localStorage` or execute actions using the active session; storing in memory reduces certain persistent storage risks but **does not eliminate XSS**. Only accept refresh tokens if the IdP allows them for that client type, with rotation/TTL/reuse detection. Use CSP, prevent injection, audit dependencies, and never place tokens in URLs, logs, or query parameters.

**CORS is not authorization.** CORS only restricts browsers from reading cross-origin responses; the backend must still verify tokens and authorize every request. If the API also accepts automatically sent cookies, CSRF policy must still be evaluated independently.

## 6. Step three: mobile, desktop, and constrained devices

iOS/Android, desktop, and CLI apps distributed to user devices cannot keep a long-lived shared client secret. User login flows typically use Authorization Code + PKCE via the **system browser** (external user-agent), not an embedded webview asking for passwords directly inside the app.

Practical requirements include:

- PKCE `S256`, exact redirect URI, proper `state`/`nonce`; protection against code interception.
- OAuth client registered properly as a public client, without attaching a secret like a confidential web server.
- Access/refresh tokens stored in OS secure storage (Keychain/Keystore or equivalent), never in logs or plaintext configuration.
- Short-lived access tokens, refresh token rotation/revocation per provider, and a plan for logout or lost devices.
- Offline mode must have data limits, cache encryption, and re-authorization checkpoints; offline does not mean perpetual tokens.
- The API always validates the Bearer token and owner/tenant, never trusting roles self-reported by mobile clients.

For CLIs with a browser, loopback redirect with PKCE can be used. TVs/browser-less devices can use the **Device Authorization Grant (RFC 8628)** if the provider supports it: the user confirms on another device, with a short-lived device code, rate-limited polling, and anti-phishing protections.

## 7. Step four: machine-to-machine without an end user

Scheduled jobs, microservices, or integration servers can use **OAuth2 Client Credentials** or workload identity. This grant represents a **client/service**, not an impersonated employee.

```text
Scheduled job           Authorization Server          Resource API
     | authenticate client + scope |                       |
     |----------------------------->|                       |
     |<----- access token ----------|                       |
     | Authorization: Bearer token                          |
     |----------------------------------------------------->|
     |<---------------- response ---------------------------|
```

Only use client secrets/private keys on servers with a secret manager and rotation; consider mTLS or `private_key_jwt` when supported by the IdP. Token audience and scopes must target the exact API, e.g., `reports.export` instead of `admin:*`. Audit workload identities separately.

**Never** use Client Credentials for SPAs/mobile apps just to avoid a login screen: they cannot protect the client secret, and this grant does not authenticate an end user. If a job acts **on behalf of a user**, use an appropriate delegation/token exchange model rather than arbitrarily granting user roles to a service account.

## 8. Step five: JWT, opaque tokens, revocation, and data authorization

| Factor | JWT access token | Opaque access token |
| --- | --- | --- |
| Verification | Resource Server typically verifies signature and claims locally using trusted keys. | API calls an introspection endpoint or uses a TTL-cached result. |
| Performance | Can reduce introspection round-trips; requires key fetching/rotation. | Depends on network/IdP; caching requires evaluating stale-data risk. |
| Revocation | Unexpired tokens remain valid if the API only checks signature/`exp`; requires an extra strategy if immediate revocation is needed. | Introspection can reflect inactive tokens, though caching delays enforcement. |
| Data | The JWT payload is typically readable by anyone holding the token even when the signature is valid. | Clients typically cannot read metadata directly from an opaque string. |
| Best fit | Distributed systems that accept TTL/rotation and local API verification. | Centralized token state/permission checks or avoiding exposing token claims. |

Both JWT and opaque tokens require valid issuer/audience/scope/expiry, HTTPS, and authorization. **Do not choose JWT merely because it is "stateless."** If the product requires locking out an admin within 1 minute, a 1-hour access token validated only by signature will not meet the SLA without revocation or online permission checks.

**Owner/tenant:** `ROLE_USER` and `SCOPE_orders.read` usually only grant action-level permission. For private records you must verify `owner_user_id`; for organizations you must check membership and constrain queries with `authorized_organization_id`. Never trust a `userId`/`organizationId` sent in a request body or custom header as a granted permission.

## 9. Mapping to Spring Security

| Capability | Spring Security component |
| --- | --- |
| Local username/password | `UserDetailsService`, `PasswordEncoder`, `formLogin`, session management. |
| Web OIDC/SSO or BFF | `spring-boot-starter-oauth2-client`, `oauth2Login`, and `oauth2Client`. |
| API receiving JWT | `spring-boot-starter-oauth2-resource-server`, `oauth2ResourceServer(...jwt...)`, `JwtDecoder`. |
| API receiving opaque token | `oauth2ResourceServer(...opaqueToken...)`, `OpaqueTokenIntrospector`. |
| Service OAuth2 client | Client registration for `client_credentials` and authorized client manager. |
| HTTP/method authorization | `authorizeHttpRequests`, `hasRole`, `hasAuthority`, `@EnableMethodSecurity`, `@PreAuthorize`. |
| Data protection | Repository queries scoped by owner/tenant, server-verified membership/ACL. |

**Version note:** The runnable example below pins Spring Boot **3.5.16** for Java 17/Spring Security 6.x. That is the final OSS-supported release of the 3.5.x branch; for new production systems in 2026, use a branch still receiving patches and plan upgrades accordingly. The OIDC and Resource Server snippets are **separate options**, not pieces to mix randomly into the form-login demo project.

## 10. Runnable Java 17+ example: web application choosing sessions

Suppose the product is a same-origin portal that does not yet need SSO or third-party APIs. We choose form login, session cookies, and CSRF. The example below includes Gradle, the Java application, tests, and expected HTTP outcomes.

### 10.1. Gradle configuration

`settings.gradle`:

```groovy
rootProject.name = 'auth-choice-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`src/main/resources/application.properties`:

```properties
spring.application.name=auth-choice-demo
server.servlet.session.timeout=20m
server.servlet.session.cookie.http-only=true
```

For production over HTTPS, configure `Secure` and `SameSite` cookies, reverse proxy headers, and a multi-instance session store. Never use sample accounts in a real product.

### 10.2. Spring Boot application

Create `src/main/java/demo/authchoice/SessionAuthApplication.java`:

```java
package demo.authchoice;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SessionAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionAuthApplication.class, args);
    }
}

@RestController
class BrowserApi {
    @GetMapping("/public")
    String publicEndpoint() {
        return "public";
    }

    @GetMapping("/me")
    String me(Authentication authentication) {
        return authentication.getName();
    }

    @PostMapping("/actions")
    String saveAction(Authentication authentication) {
        return "saved-for-" + authentication.getName();
    }
}

@Configuration
class BrowserSecurity {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice123"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form.permitAll())
            .logout(Customizer.withDefaults());

        // CSRF remains enabled by default. Do not switch to STATELESS.
        return http.build();
    }
}
```

**How it works:** Spring Security handles login and stores login state via a session; the browser keeps the session ID in a cookie. GET `/me` requires login; POST `/actions` requires login **and** a valid CSRF token. The demo defines one user `alice` with a BCrypt hash. `authenticated()` does not automatically enforce owner/tenant protection on private data APIs.

### 10.3. Testing real Spring Security and sessions with MockMvc

Create `src/test/java/demo/authchoice/SessionAuthTest.java`:

```java
package demo.authchoice;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.redirectedUrlPattern;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SessionAuthTest {
    @Autowired MockMvc mvc;

    private MockHttpSession signedIn() throws Exception {
        var result = mvc.perform(post("/login")
                .param("username", "alice")
                .param("password", "alice123")
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        var session =
            (MockHttpSession) result.getRequest().getSession(false);
        assertThat(session).isNotNull();
        return session;
    }

    @Test
    void publicPageIsAccessible() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void anonymousIsRedirectedToLogin() throws Exception {
        mvc.perform(get("/me"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void wrongPasswordIsRejected() throws Exception {
        mvc.perform(post("/login")
                .param("username", "alice")
                .param("password", "wrong")
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void signedInSessionWorks() throws Exception {
        mvc.perform(get("/me").session(signedIn()))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    void postWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/actions").session(signedIn()))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithCsrfWorks() throws Exception {
        mvc.perform(post("/actions")
                .session(signedIn())
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("saved-for-alice"));
    }
}
```

`@SpringBootTest` loads the application configuration and `@AutoConfigureMockMvc` keeps the security filters active. Test login using a real `POST /login` request with CSRF and real credentials, then **reuse the session** for subsequent requests. Do not use `@WithMockUser` to fake the login flow.

Expected results:

| Request | Result |
| --- | --- |
| Anonymous GET `/public` | 200, body `public`. |
| Anonymous GET `/me` | 302 redirect to `/login`. |
| Wrong password at POST `/login` with CSRF | 302 redirect to `/login?error`. |
| Valid login and GET `/me` with same session | 200, body `alice`. |
| Valid login, POST `/actions` missing CSRF | 403. |
| Valid login, POST `/actions` with CSRF | 200, body `saved-for-alice`. |

Run in the project directory if a Gradle Wrapper is present:

```bash
./gradlew test
./gradlew bootRun
```

Windows: `gradlew.bat test` and `gradlew.bat bootRun`. If there is no wrapper, use `gradle test` / `gradle bootRun` with a compatible Gradle 8.x version. Open `http://localhost:8080/me` in a browser and log in with `alice / alice123` in a learning environment. Remember this is a localhost demo, **not a production TLS/cookie/secrets configuration**.

## 11. OIDC Login/BFF option when SSO is needed

If the product serves enterprises using SSO/MFA or an SPA needs to call downstream APIs, you can replace local form login with OIDC. **This is a configuration blueprint**, not standalone runnable code without a real IdP, client registration, secret manager, BFF proxy, and CSRF integration.

Dependency:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
```

Example `application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: your-client-id-from-secret-store
            client-secret: your-secret-from-secret-store
            authorization-grant-type: authorization_code
            scope: openid,profile,email
        provider:
          company:
            issuer-uri: https://identity.example.com/issuer
```

Choose real client/issuer details per your IdP; **never commit secrets** in YAML source files. Illustrative configuration bean:

```java
@Bean
SecurityFilterChain bffChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/assets/**", "/error").permitAll()
            .anyRequest().authenticated()
        )
        .oauth2Login(Customizer.withDefaults())
        .oauth2Client(Customizer.withDefaults());

    // Browser session still requires CSRF.
    return http.build();
}
```

The snippets above require imports for `@Bean`, `HttpSecurity`, `SecurityFilterChain`, `Customizer`, and a real BFF application. A BFF must also manage `OAuth2AuthorizedClient` and server-side token storage, call downstream APIs with an access token matching the right audience, handle refresh/revoke, build the frontend CSRF flow, implement logout, and support multiple instances.

**Rules:** Redirect URIs must match the IdP configuration; `state`/OIDC `nonce`, PKCE, and issuer binding must be validated properly by the client library. Do not send ID tokens as API access tokens, and do not return access/refresh tokens to the browser when the BFF's purpose is to hide tokens.

## 12. OAuth2 Resource Server option for Bearer token APIs

APIs receiving Bearer tokens from mobile apps, direct SPAs, or partners must verify tokens at the **Resource Server**. This is a **separate integration snippet**, not standalone runnable code without a trusted issuer/route and real access tokens.

Dependency:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
```

`application.yml`:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/issuer
          audiences: https://api.example.com
```

Example chain dedicated solely to APIs accepting **Bearer headers**, without relying on automatically sent browser cookies:

```java
@Bean
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/health").permitAll()
            .requestMatchers(HttpMethod.GET, "/api/reports/**")
                .hasAuthority("SCOPE_reports.read")
            .anyRequest().authenticated()
        )
        .sessionManagement(s -> s
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
        )
        .csrf(AbstractHttpConfigurer::disable)
        .oauth2ResourceServer(o -> o.jwt(Customizer.withDefaults()));

    return http.build();
}
```

Requires imports for `@Bean`, `HttpSecurity`, `HttpMethod`, `SecurityFilterChain`, `SessionCreationPolicy`, `AbstractHttpConfigurer`, `Customizer`. **Disabling CSRF is strictly conditional** on the entire chain truly accepting only the Authorization Bearer header and never session cookies. If there are cookie-authenticated endpoints, do not copy this configuration into web/BFF without separating chains.

Resource Server validates signatures/keys, issuer, audience, expiry, not-before timestamps, and scopes. Scope claims typically become authorities like `SCOPE_reports.read`. Invalid tokens usually return 401; valid tokens lacking required scopes usually return 403. Even with sufficient scopes, ownership/tenant checks on data are still required.

If using opaque tokens, choose `opaqueToken` instead of `jwt` along with the IdP's introspection endpoint/credentials, weighing latency and revocation timing. Local-only JWT verification trades off immediate revocation; cached opaque introspection also carries stale-state risk.

## 13. Client Credentials option for service-to-service

This configuration is intended for jobs, **not as a mobile/browser login method**. It requires `spring-boot-starter-oauth2-client`, an appropriate OAuth2 client manager, and a real IdP:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          report-job:
            provider: company
            client-id: workload-client-id
            client-secret: secret-from-manager
            authorization-grant-type: client_credentials
            scope: reports.export
        provider:
          company:
            token-uri: https://identity.example.com/oauth2/token
```

Use workload identity/secret managers, narrow scopes, short-lived tokens, key rotation, and per-service auditing. If a task runs on behalf of a specific user, use a different delegation model rather than granting broad global scopes to a service.

## 14. Product requirements that change the decision

### 14.1. Enterprise SSO and MFA

B2B portals requiring SSO, MFA, passkeys, or deprovisioning policies usually point toward a dedicated IdP. Web/BFF uses OIDC Login and sessions; mobile uses Authorization Code + PKCE; services use separate client authentication. Some enterprises require SAML2 federation, in which case a SAML service provider can be integrated rather than assuming every IdP uses OIDC.

### 14.2. Immediate revocation and logout

- Server-side sessions can be invalidated, but multi-node/device synchronization and caches must be handled.
- Unexpired JWTs may continue to be accepted if the resource server only checks signature/expiry.
- Opaque token introspection can reflect revocation sooner, though caching introduces delay.
- Refresh token rotation/revocation protects token renewal, not already-issued unexpired access tokens.
- Logging out of an app does not necessarily log out of the entire IdP session or other products.

The product must define an SLA, such as "account lockout takes effect within at most N minutes," before choosing TTLs, introspection, token revocation, and session policies.

### 14.3. Multi-tenant, owner, and data permissions

Having `ROLE_USER` or `SCOPE_reports.read` alone does not prove a user may read every report. You must verify membership/ownership and place predicates like `organization_id = :authorizedOrgId` or `owner_user_id = :currentUserId` directly in queries. Test user A and user B with the same role accessing private resources across list/detail/count/export/write APIs.

### 14.4. Operations and complexity

Sessions require a store/replication and timeouts; BFF requires a proxy/token store, scaling, and CSRF; JWT requires JWK rotation, clock skew handling, and a revocation plan; opaque introspection requires latency/availability SLOs; Client Credentials require key/secret rotation and service account governance. Choose a model your team can maintain, not solely based on requests per second.

## 15. Three sample design scenarios

**Internal portal:** browser, same-origin backend, enterprise requires SSO/MFA and audit → server-side OIDC Login, HttpOnly/Secure/SameSite session cookie, CSRF; backend checks role/owner and organization permissions. Do not force the browser to hold JWTs when all APIs go through the backend/BFF.

**Consumer mobile app:** iOS/Android, user login, direct APIs, lost-device/offline considerations → Authorization Code + PKCE via system browser; tokens in OS secure storage; API Resource Server validates audience/scope and owner; refresh rotation and revocation policy.

**Report export job:** runs automatically without a user, read/export dataset permissions → workload identity/Client Credentials, server-side protected secret/private key, short-lived access token and narrow scope; API audits by workload. Never store employee passwords in cron jobs.

## 16. Common design mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Forcing every client to use JWT. | Mixes login/user/machine concerns, hard to revoke. | Choose by actor and trust boundary. |
| Calling Resource Server with an ID token. | Wrong audience/token semantics. | Use a dedicated access token for APIs. |
| Embedding a client secret in SPA/mobile. | The secret is not confidential. | Public client + PKCE or BFF. |
| Using Implicit or Password Grant in new systems. | Increases risk of code/token/password leakage. | Authorization Code + PKCE. |
| Returning tokens from BFF to JS. | Loses the benefit of server-side token storage. | Browser receives only a session cookie. |
| Disabling CSRF with cookie sessions. | Cross-site requests can exploit auto-sent cookies. | Proper CSRF protection and SameSite/Origin policy. |
| Trusting CORS instead of token validation. | APIs can still be called by non-browser clients. | Backend verifies authentication/authorization. |
| Decoding JWT without verifying. | Claims can be forged. | Validate signature, issuer, audience, expiry. |
| Long-lived JWTs without revocation. | Revoked permissions may remain active. | TTL/revocation/introspection aligned with SLA. |
| Using user passwords in jobs. | Wrong audit trail, overly broad scopes, hard to rotate. | Workload identity/Client Credentials. |
| Checking scopes only, ignoring owner/tenant. | BOLA/IDOR and data leaks. | Scoped DB queries and membership checks. |
| Mixing cookies and bearer tokens arbitrarily on one chain. | Inconsistent CSRF/authorization behavior. | `securityMatcher`, `@Order`, and per-client tests. |

## 17. Architecture testing and checklist

| Test category | Minimum test cases |
| --- | --- |
| Session web | Anonymous redirect; valid/invalid login; session reuse; logout; POST with/without CSRF. |
| OIDC/BFF | Redirect URI, state/nonce/PKCE, tokens not exposed to browser, session/CSRF, IdP logout policy. |
| SPA/mobile | PKCE, token expiry/refresh, redirect validation, CORS does not replace authz, OS storage. |
| Resource Server | Missing token, invalid signature/issuer/audience/expiry, missing scope 403, sufficient scope 200. |
| M2M | Client auth failure, missing scope, wrong audience, rotation, and workload audit. |
| Data authorization | Wrong owner/tenant blocked; list/count/export and updates cannot exceed scope. |
| Operations | IdP down, session store down, logout/revoke SLA, log redaction, and alerting. |

Pre-release checklist:

- [ ] Listed every client, separating human vs. machine identities.
- [ ] Distinguished public and confidential clients; no leaked client secrets.
- [ ] Selected session, BFF, direct OAuth, or Client Credentials based on requirements.
- [ ] Public OAuth clients use Authorization Code + PKCE with exact redirects.
- [ ] SSO/MFA/passkey/step-up aligned with product requirements.
- [ ] APIs use access tokens with the right audience, never ID tokens.
- [ ] HttpOnly/Secure/SameSite cookies and CSRF designed for browser flows.
- [ ] Bearer tokens verified and role/scope/owner checked server-side.
- [ ] TTL, logout/revocation, key rotation, and incident plans aligned with SLA.
- [ ] SecurityFilterChain/matchers and method security are consistent.
- [ ] Both allow/deny tests, cross-user, and cross-tenant tests exist.
- [ ] Secrets, tokens, passwords, and session IDs are never written to logs.
- [ ] An ADR documents choices, trade-offs, and rejected alternatives.

## 18. Self-check

**Q1.** Does a same-origin Spring MVC web app strictly need to use JWT?  
**A1.** No. Session cookies + CSRF can be simpler and more appropriate; use OIDC Login if SSO is needed.

**Q2.** An SPA has its own backend and you do not want tokens in JS—what should you consider?  
**A2.** BFF + OIDC; the BFF keeps downstream tokens server-side while the browser holds a session cookie, still requiring CSRF/XSS protections.

**Q3.** Does a mobile app embedding a client secret in its APK become a confidential client?  
**A3.** No. Binaries can be extracted; use Authorization Code + PKCE via the system browser.

**Q4.** Does `oauth2ResourceServer().jwt()` automatically provide a login page?  
**A4.** No. It only verifies Bearer tokens for APIs; login belongs to the OAuth/OIDC Client and IdP.

**Q5.** Can an API use a validly signed ID token as an access token?  
**A5.** It should not. APIs need an access token with the proper audience and permissions; a valid signature alone is not enough.

**Q6.** What grant should a nightly batch job without a user use?  
**A6.** Workload identity/Client Credentials with narrow scopes and server-side secrets/keys.

**Q7.** If a user has the scope to read orders, can they view an order belonging to another tenant?  
**A7.** No, if the policy requires tenant isolation; owner/membership checks are still required.

**Q8.** If CORS is configured for the right origin, can the API skip token validation?  
**A8.** No. CORS is a browser mechanism, not authorization.

**Q9.** A JWT lives for one hour, but admin revocation is required within one minute. What is missing from the design?  
**A9.** A token/permission revocation strategy and TTL that meet the SLA; online checks, revocation, or shorter lifetimes are needed.

**Q10.** A POST using a session cookie returns 403—should you disable CSRF?  
**A10.** Not just because of the 403 status. Check the CSRF token, cookie, and exact flow; preserve protection suited to the credential model.

## 19. Takeaways and official documentation

**Selection formula:** client type and trust boundary → human or workload → login/IdP → session or Bearer token → API and data permissions → logout/revocation/tests. Same-origin web apps can use sessions; SPAs with a backend should evaluate a BFF; direct SPAs/mobile apps use Authorization Code + PKCE; APIs receiving tokens use Resource Server; backend-to-backend uses Client Credentials. There is no single best mechanism for every client type.

- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/index.html)
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/client/index.html)
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html)
- [RFC 9700 — OAuth2 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700)
- [RFC 7636 — PKCE](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 8252 — OAuth2 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252)
- [RFC 8628 — Device Authorization](https://www.rfc-editor.org/rfc/rfc8628)
- [OWASP — Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP — CSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)

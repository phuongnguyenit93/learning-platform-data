# Session Lifetimes, Token Lifetimes, and Access Revocation Workflows

## 1. The deployment problem: do logout or expiration actually cut off access?

A Spring Security system may let users sign in via a browser while also letting other services call APIs with access tokens. A user clicks **Log out**, an admin locks an account, or a leaked token is discovered. The critical question is not just whether the UI displays "Logged out", but:

> **From the moment revocation is requested, do previously issued credentials still allow API calls, for how long, and across which components?**

If the browser deletes a cookie yet the server still accepts the old `JSESSIONID`, logout has failed its goal. If the Authorization Server revokes a refresh token yet an unexpired JWT access token is still accepted by the Resource Server, the user can keep calling APIs for some time. If a microservice caches authorization decisions too long, role changes in the database may not take effect immediately.

This lesson is part of the **Deployment** section of **Spring Security – fundamentals**. It focuses on designing and operating **session/token lifetimes and access revocation workflows** on Java 17+, Spring Boot 3.x, and Spring Security 6.x Servlet, while distinguishing OAuth2/OIDC and multi-node scenarios.

After completing this lesson, you should be able to:

1. Distinguish cookies, HTTP sessions, access tokens, refresh tokens, remember-me tokens, and Identity Provider SSO sessions.
2. Define **idle timeout**, **absolute lifetime**, token `exp`, refresh token TTL, and the window during which stale privileges remain active.
3. Explain why **logging out one session does not automatically revoke all JWTs**, and **revoking a refresh token does not automatically revoke issued access tokens**.
4. Choose revocation mechanisms: session invalidation, token introspection, denylists, token versions, short-lived tokens, refresh token rotation, and family revocation.
5. Configure sessions appropriately in Spring Boot/Spring Security and write tests verifying logout, CSRF, and session state.
6. Establish response procedures when an account, token, or service credential is compromised.

There is no single TTL that fits every system. Policies must reflect risk, client type, data sensitivity, privileges, user experience, compliance requirements, and actual revocation capabilities.

## 2. Accurately distinguishing state and credential types

| Component | Who issues and stores state? | How it is used | Expiration / revocation |
| --- | --- | --- | --- |
| **HTTP session** | Servlet container or Spring Session stores session state on server/repository. | Browser sends session ID, typically via `JSESSIONID` cookie. | Invalidate session or expire in session store; old ID is rejected. |
| **Session cookie** | Server sends `Set-Cookie`; browser holds the session ID string. | Auto-sent via `Cookie` when domain/path/SameSite/Secure match. | Browser deletes/expires cookie; **does not replace** server invalidation. |
| **OAuth2 access token** | Authorization Server issues; Resource Server validates. | Typically sent as `Authorization: Bearer ...`. | `exp`, introspection, or revocation checks supported by the Resource Server. |
| **Refresh token** | Authorization Server issues and manages the grant/token family. | Client sends to the token endpoint to obtain a new access token. | Expiration, rotation/reuse detection, revoking grant or token family. |
| **OIDC ID token** | OpenID Provider issues to the client to convey authentication event claims. | Client verifies identity in the OIDC protocol. | Has `exp`, but **must not be used by default as an access token** to call Resource Servers. |
| **Remember-me token** | Application issues cookie/record for persistent login convenience. | Can restore authentication after the session expires. | Revoke both cookie and server-side records depending on remember-me type. |
| **CSRF token** | Spring Security or app generates to block forged requests. | Form/header sent on state-changing requests using browser credentials. | Lifecycle tied to session/repository; **grants no login privileges**. |
| **API key / client secret** | Integration owner / Identity Provider issues. | Authenticates a client or service per protocol. | Rotate, disable/revoke at issuer; do not confuse with JWT TTL. |
| **IdP/SSO session** | Identity Provider separately stores federated login state. | Can issue new app sessions without prompting for the password again. | Local logout does not necessarily log out the IdP; requires dedicated SSO/logout design. |

### 2.1. A session cookie is not the server-side session

Example:

```http
HTTP/1.1 200 OK
Set-Cookie: JSESSIONID=DEMO_SESSION_ID; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
```

The cookie carries a **session reference identifier**, not the full session state managed by the Servlet container. When the user sends the cookie:

```http
GET /private/home HTTP/1.1
Cookie: JSESSIONID=DEMO_SESSION_ID
```

the container looks up the corresponding session. If the session has expired or been deleted, the old cookie no longer carries authentication. Therefore, "deleting the cookie from the browser" and "invalidating the server session" are **two distinct tasks**. Security tests must deliberately replay the pre-logout cookie.

### 2.2. One user can hold multiple credentials simultaneously

A user accessing an app via OIDC may simultaneously hold:

- An active IdP session.
- An application-internal session (`JSESSIONID` cookie).
- An API access token.
- A refresh token held by the client/BFF or authorization server.
- A remember-me token, if the app implements that feature.

Logging out of the app may invalidate only the internal session. If the IdP still has an active SSO session, the next navigation may silently sign the user back in. If a resource server still accepts an unexpired JWT, APIs can still be called with that token. **Never claim "signed out everywhere" unless you have proven revocation across every credential involved.**

## 3. Time concepts: idle, absolute, rolling, and token expiry

### 3.1. Idle timeout — inactivity limit

**Idle timeout** is the maximum period without qualifying activity before a session expires. For example, a session with `maxInactiveInterval = 20 minutes`:

```text
09:00  Login -> session S created
09:10  Valid request with S -> updates last-access
09:25  Valid request with S -> session still alive since idle <= 20 minutes
09:46  Next request with S -> may be rejected since idle > 20 minutes
```

Every request touching the session can update its last-accessed timestamp. Consequently, background polling or heartbeats can keep a session alive longer than intended. Agree on **which requests count as activity** rather than assuming "user isn't touching the keyboard."

In Servlets, `HttpSession#setMaxInactiveInterval(int seconds)` sets the inactivity limit on a session. Cleanup mechanics and timing depend on the container or session repository, but requests presenting an expired session **must not reuse that session's authentication state**.

### 3.2. Absolute lifetime — hard cap

**Absolute lifetime** is measured from when the session began or from the last sufficiently strong authentication, and cannot be extended indefinitely by continuous requests.

Example application policy:

- Idle timeout: 20 minutes.
- Absolute lifetime: 8 hours from login.
- Sensitive operation reauthentication: require re-login/MFA if more than 15 minutes have passed since the last strong authentication.

These numbers are **design examples**, not Spring Security defaults or fixed recommendations. `server.servlet.session.timeout` configures Servlet idle policy; **it does not enforce an absolute lifetime**. To enforce an absolute cap or step-up auth, store the origin timestamp in trusted state, check it on requests/operations, and revoke or demand reauthentication once the threshold is crossed.

### 3.3. Sliding/rolling expiry

Sessions with an idle timeout are typically **sliding**: valid activity pushes the idle expiration forward. Refresh tokens may also have sliding lifetimes if allowed by the Authorization Server, though secure systems usually pair them with an **absolute expiry** on the refresh token family so continuous refreshing cannot extend access forever.

**Do not confuse rolling expiry with mutating a token's `exp`.** A signed JWT access token normally carries a fixed `exp`; using it on a request does not alter `exp`. The client must obtain a new token through an authorized flow.

### 3.4. Timestamps inside JWTs

A JWT may contain:

- `iat` (issued at): issuance time.
- `nbf` (not before): not accepted before this instant.
- `exp` (expiration time): no longer accepted at or after this instant, subject to any **clock skew/leeway** permitted by the validator.
- `jti`: unique token identifier if emitted by the issuer, useful for certain anti-replay/revocation designs.

In JWTs, `NumericDate` values are typically measured in **seconds since the Unix epoch**. When comparing them, match timezones and units accurately and synchronize server clocks. The example below uses fixed UTC timestamps:

```text
issuedAt  = 2026-01-01T00:00:00Z
expiresAt = 2026-01-01T00:05:00Z
current   = 2026-01-01T00:04:59Z -> not yet at exp
current   = 2026-01-01T00:05:00Z -> reached exp
```

Spring Security's validator may apply clock skew to tolerate minor drift between machines. Verify the actual leeway when testing boundaries: a token "right at the `exp` second" may still pass if tolerance is configured. **Never set an arbitrarily large clock skew**, as it extends token validity past its nominal expiration.

## 4. Boundaries between Spring Security, Servlet container, and Identity Provider

### 4.1. Who expires the session?

Spring Security manages authentication/authorization and binds `SecurityContext` to requests/sessions per configuration. **The Servlet container or Spring Session repository** owns HTTP session existence and idle expiration. Spring Security reacts when a client presents an expired session ID, but does not turn session timeout config into a "logout hook that fires automatically everywhere."

Common Spring Boot properties:

```yaml
# application-prod.yml: example configuration, not a universal default
server:
  servlet:
    session:
      timeout: 20m
      cookie:
        secure: true
        http-only: true
        same-site: lax
```

Explanation:

- `timeout: 20m` sets the Servlet session idle timeout; depending on the container, very small values or granularity may be rounded.
- `secure: true` requires sending the cookie over a secure channel, appropriate for HTTPS production.
- `http-only: true` restricts JavaScript from reading the cookie; does not prevent all XSS or CSRF.
- `same-site: lax` is an illustrative choice; apps with SSO, cross-site iframes, or special callbacks must evaluate `SameSite` and `Secure` specifically.
- This is **not** an absolute session lifetime, an OAuth token TTL, or an IdP session lifetime.

In dev/test environments running plain HTTP on localhost, setting `Secure` on cookies while expecting browsers to send them over HTTP varies by browser and loopback rules. Prefer production-like HTTPS testing rather than silently disabling cookie protections in production.

### 4.2. What does Servlet logout do?

When Spring Security logout is enabled, `POST /logout` with a valid CSRF token (when CSRF is enabled) typically:

- Invalidates the current `HttpSession`.
- Clears `SecurityContextHolder` and the configured repository.
- Removes the current CSRF token.
- Cleans up configured remember-me mechanisms, if enabled.
- Sends a redirect or success response via the configured `LogoutSuccessHandler`.

`GET /logout` under default CSRF configuration normally displays a confirmation page and **does not destroy the session**. Switching logout to GET "for convenience" exposes the system to forced logout triggered by external websites.

**Do not check only that the page redirected to `/login`.** A meaningful test keeps a copy of the pre-logout cookie and replays it against a protected endpoint; the server must reject it.

### 4.3. Where are access tokens validated?

Spring Security OAuth2 Resource Server accepts a bearer token, verifies its signature and required claims per token type and configuration (issuer, expiration, and audience if required by the app), and derives privileges from authorities/scopes. However, **a Resource Server does not automatically know that a refresh token was just revoked at the Authorization Server**.

With self-contained JWTs checked only for signature/`exp`, already-issued tokens remain usable until expiry. If "immediate revocation" is required, add real revocation-state checks at Resource Servers, or use opaque tokens with introspection.

## 5. A lifetime matrix worth documenting

A system needs a **lifetime blueprint** rather than a single "session timeout" number.

| Component | TTL to decide | Extends on use? | Revocation mechanism |
| --- | --- | --- | --- |
| Browser session | Idle timeout and (if any) absolute lifetime | Idle can slide; absolute usually does not. | Invalidate session, delete store record, lock account, force re-login. |
| Session cookie | Session cookie or `Max-Age`/`Expires` | Handled by browser per cookie attributes. | Send expired cookie; **must still revoke server session**. |
| Access token | `exp - iat`, perhaps minutes by risk | Old token's `exp` never changes; fetch a new one. | Expiry, introspection, denylist, token version, or equivalent. |
| Refresh token | Idle, absolute, family lifetime at Authorization Server | Bounded rotation/sliding possible. | Revoke token/family/grant, reuse detection. |
| API key/client secret | Expiration, rotation, and per-workload scope | Does not expire per request by default. | Disable, rotate, swap credentials in dependent services. |
| Role cache | Cache TTL and permission version | Refreshable on demand. | Cache invalidation, token/session version, token expiry, or reauthentication. |
| IdP SSO session | Identity Provider session policy | Sliding or absolute per IdP. | Appropriate back-channel/front-channel logout; distinct from local logout. |

**Discussion-only policy example (not prescriptive):**

```text
Internal application:
- HttpSession idle: 20 minutes
- HttpSession absolute: 8 hours if implemented
- Access JWT: 5 minutes
- Refresh token: rotation enabled, with absolute lifetime
- Elevated privileges: step-up if strong auth is older than 15 minutes
- Revocation on account lock: near-instant enforcement required
```

If business rules tolerate **at most 5 minutes** of stale privilege, a 5-minute JWT TTL plus clock skew, caching, and propagation time still needs evaluation. If rules mandate revocation **within seconds**, a short `exp` alone is usually insufficient when valid tokens are verified offline by Resource Servers.

### 5.1. Defining "revocation latency"

**Revocation latency** is the interval between the moment the system records a revocation event and the moment **every policy enforcement point within the committed boundary** begins rejecting the revoked credential.

Sources of latency:

- Events have not reached all Resource Servers yet.
- Introspection/authorization caches still hold stale entries.
- Database/Redis replication has not converged.
- Offline token validation checks only `exp`.
- API gateways, service meshes, and applications enforce privileges at different layers.
- In-flight requests already admitted before revocation.

Operational docs must distinguish "revocation written to the database" from "every new request is rejected." For sensitive actions, also evaluate in-flight requests and previously authorized side effects.

## 6. Revocation strategies by credential type

### 6.1. Server-side sessions

On logout:

1. Invalidate the current device's session.
2. Clear security context/CSRF/remember-me per configuration.
3. Instruct the browser to delete the session cookie.
4. Test that replaying the **old cookie** is rejected.
5. With multiple nodes, ensure the shared session store reflects deletion across all nodes.

If an administrator wants to **log out all devices**, track all sessions belonging to that user and delete/invalidate each one. `HttpSession.invalidate()` inside one request **does not automatically revoke sessions everywhere**.

When using Spring Session with Redis/JDBC, monitor repository/namespace, TTL, replication, and deletion lag. With sticky sessions, test across multiple nodes so one node cannot retain a copy of a session invalidated elsewhere.

### 6.2. Opaque access tokens and introspection

A Resource Server receiving an opaque bearer token can query the Authorization Server via **token introspection** to check whether the token is still `active`. Once revoked and marked inactive, the API rejects it. The trade-off is extra latency and dependency on introspection service availability; caching must align with your revocation SLA.

**Never assume** opaque tokens automatically mean "instant revocation" if the Resource Server or gateway caches `active=true` for too long. Revocation SLO calculations must include cache TTL.

### 6.3. Self-contained JWT access tokens

A JWT with a valid signature and unexpired `exp` can be accepted **offline** by Resource Servers. Deleting a refresh token record at the Authorization Server **does not change the signature or `exp` of already-issued JWTs**.

Design options:

- **Short-lived access tokens:** shrink the exposure window, though they do not guarantee immediate revocation.
- **Denylist by `jti`/token digest:** on critical requests, the Resource Server checks whether the token was revoked; revocation entries must be retained at least until the token definitely expires, accounting for clock skew and caches.
- **Token version / user security epoch:** store a server-side version / "tokens valid after" timestamp and embed it in JWTs. On lock or privilege changes, increment the version. Resource Servers must **reliably query/sync** the version when needed.
- **Opaque token introspection:** offload status checks to a server capable of immediate rejection.
- **Sensitive privilege checks:** verify account/tenant status in the service right before sensitive operations, or require reauthentication/step-up.

**Never think of a self-contained JWT as "deletable" from the client.** Deleting the local copy does not revoke a stolen copy. Rotating signing keys is a heavy hammer invalidating many tokens; useful in emergencies, not for routine logouts.

### 6.4. Refresh tokens and token families

Refresh tokens allow clients to mint new access tokens, so losing a refresh token can sustain access longer than losing an access token. Controls:

- Issue only to clients/flows that need them and are allowed by policy.
- Protect storage; never put them in URLs, `localStorage`, or logs without a risk review.
- Apply **refresh token rotation** or sender-constrained refresh tokens per security requirements and client type.
- Bind tokens to the appropriate client, grant, device/session, or token family.
- Enforce idle and absolute lifetimes; revoke on logout, password change, or suspected compromise per policy.
- Detect reuse of spent tokens (**reuse detection**) and revoke the family/grant when unauthorized replay is detected.

**Revoking a refresh token does not automatically make old access tokens disappear.** If immediate cut-off is required, combine it with access-token revocation at Resource Servers.

### 6.5. Service accounts and client credentials

A worker using OAuth `client_credentials` typically **has no human browser session**. When a service secret leaks:

1. Disable/rotate the credential at the Identity Provider.
2. Revoke grants/tokens if supported by the provider, and assess remaining unexpired access tokens.
3. Issue new credentials, updating the secret manager or workload identity.
4. Deploy safely, verifying the old client is rejected and the new client works.
5. Audit APIs called during the suspected exposure window.

Never "log out a browser" to fix a leaked client secret. Never use a human user account as a service account just to share sessions/passwords.

## 7. Refresh token rotation and transactional reuse detection

Suppose a client holds refresh token `R1`:

```text
Valid refresh:
Client -> POST /token with R1
Authorization Server:
  - Authenticates client and R1
  - Marks R1 as spent
  - Issues access token A2 and refresh token R2
Client <- A2, R2

Later, someone reuses R1:
Authorization Server -> detects R1 was already rotated
                      -> applies replay/compromise policy
                      -> may revoke token family/grant containing R2
```

Refresh token records should store a **hash or verification material**, not necessarily the plaintext token. Token replacement must be **atomic**, typically via transactions or compare-and-swap, so two concurrent refresh requests cannot both succeed as legitimate holders.

Illustrative business algorithm:

```text
refresh(client, presentedRefreshToken):
    record = lookupBySecureTokenDigest(...)
    begin atomic transaction / lock relevant token family

    if record missing, expired, revoked or client mismatch:
        reject without disclosing token details

    if record already spent:
        evaluate reuse policy for the family
        revoke affected grant/family if compromise is suspected
        commit and reject

    mark record spent
    issue new refresh token within permitted absolute lifetime
    associate replacement with same family, bind to client
    issue new access token with bounded scope/audience/exp
    commit

    return access token + replacement refresh token
```

**Never copy pseudocode directly into a production implementation.** Production must solve hashing/entropy, race conditions, rollbacks, token-family ownership, legitimate retries, distributed storage, idempotency, and network failures. For instance, if a client sends a valid refresh request yet misses the response due to a network drop, retrying `R1` can look like replay. Designs need an appropriate **grace/client-side synchronization/race-resolution** policy without sacrificing stolen-token detection.

In many architectures, **refresh token rotation + reuse detection** matters more than trying to stretch a single access token's lifetime. However, it still does not replace access-token checks when instant privilege revocation is required.

## 8. Standalone Java 17 example: expiration vs. revocation list

To make clear that "not expired" and "not revoked" are distinct conditions, here is a **standalone JDK 17** program requiring no Spring Boot.

File `TokenLifetimeDemo.java`:

```java
import java.time.Instant;
import java.util.HashSet;
import java.util.Set;

public final class TokenLifetimeDemo {

    record AccessToken(String id, Instant expiresAt) {}

    static boolean accepted(
            AccessToken token,
            Instant at,
            Set<String> revokedIds
    ) {
        boolean notExpired = at.isBefore(token.expiresAt());
        boolean notRevoked = !revokedIds.contains(token.id());
        return notExpired && notRevoked;
    }

    public static void main(String[] args) {
        Instant issuedAt = Instant.parse("2026-01-01T00:00:00Z");
        AccessToken token = new AccessToken(
            "demo-token-id",
            issuedAt.plusSeconds(300)
        );

        Set<String> revoked = new HashSet<>();

        System.out.println(
            "before_expiry=" +
            accepted(token, issuedAt.plusSeconds(299), revoked)
        );
        System.out.println(
            "at_expiry=" +
            accepted(token, issuedAt.plusSeconds(300), revoked)
        );

        // Revoke before nominal expiration.
        revoked.add(token.id());
        System.out.println(
            "after_revoke=" +
            accepted(token, issuedAt.plusSeconds(30), revoked)
        );
    }
}
```

Compile and run:

```bash
javac TokenLifetimeDemo.java
java TokenLifetimeDemo
```

**Exact stdout output:**

```text
before_expiry=true
at_expiry=false
after_revoke=false
```

Explanation:

- At 299 seconds, `at < exp`, so the token is not expired.
- At exactly 300 seconds, `at` is no longer before `exp`, so it is expired in this model.
- Revoking `demo-token-id` causes the token to be rejected **even well before `exp`**.

**This is a timing-decision model, not a JWT validation system.** It verifies neither signatures, issuers, audiences, algorithms, token binding, nor shared state. `HashSet` lives strictly in process memory, losing state on restarts and never syncing across instances. In production, token identities/`jti` must be sufficiently unpredictable, checked only after token validation succeeds, and revocation state must be shared across enforcement points. Clock skew must reflect the real validator.

## 9. Spring Boot 3.x: a session-cookie app with logout and CSRF

This example focuses on an interactive user's **local HTTP session**, without pretending it automatically revokes OAuth JWTs. Uses Java 17+, Spring Boot 3.x, and Spring Security 6.x Servlet. Illustrative policy:

- Users can log in via form at `/login`.
- `GET /private/home` is allowed only for authenticated users.
- `POST /private/save` requires authentication **and** a valid CSRF token.
- `POST /logout` with valid CSRF invalidates the session and returns 204 No Content.
- Undeclared endpoints are not publicly exposed.
- Idle timeout is configured via the Servlet container; real testing requires a container/session store to verify expiration after timeout.

### 9.1. Dependencies

In `build.gradle` (Groovy DSL) of a Spring Boot project with plugins already configured, declare:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

This is a **dependencies snippet**, not a complete build script. All Java classes below use package `demo.lifetime`.

### 9.2. Main class

File `src/main/java/demo/lifetime/LifetimeApplication.java`:

```java
package demo.lifetime;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LifetimeApplication {
    public static void main(String[] args) {
        SpringApplication.run(LifetimeApplication.class, args);
    }
}
```

### 9.3. Security configuration

File `src/main/java/demo/lifetime/SecurityConfig.java`:

```java
package demo.lifetime;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/csrf", "/error").permitAll()
                .requestMatchers("/private/**").authenticated()
                .anyRequest().denyAll()
            )
            .csrf(Customizer.withDefaults())
            .formLogin(form -> form
                .defaultSuccessUrl("/private/home", true)
                .permitAll()
            )
            .logout(logout -> logout
                .logoutUrl("/logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID")
                .logoutSuccessHandler((request, response, authentication) ->
                    response.setStatus(HttpServletResponse.SC_NO_CONTENT)
                )
                .permitAll()
            );

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("operator")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build()
        );
    }
}
```

Analysis:

1. `.formLogin(...)` uses Spring Security's login page/form filter and sessions. Login's `permitAll()` opens only the auth endpoints without opening `/private/**`.
2. `.csrf(Customizer.withDefaults())` preserves CSRF, requiring valid tokens on `POST /logout` and `POST /private/save`.
3. `invalidateHttpSession(true)` destroys the current server session; `clearAuthentication(true)` clears the context; `deleteCookies("JSESSIONID")` asks the client to delete the cookie. **The decisive test remains verifying that the server rejects the old session ID.**
4. `204` is merely this lesson's custom success contract. By default, Spring Security redirects to `/login?logout` after logout. When integrating a real UI, choose redirect/JSON/status per requirements.
5. `anyRequest().denyAll()` prevents new endpoints from becoming public accidentally. On anonymous requests to denied routes, Spring Security may redirect to login; test per form-login contract rather than assuming 403.
6. This example does not enable remember-me, OAuth2 login, or JWTs; if added, add dedicated revocation policies and tests.
7. The password in source is strictly for learning/testing. Production requires secure user/secret management, HTTPS, brute-force protection, MFA for risky actions, and explicit session policies.

### 9.4. Controller

File `src/main/java/demo/lifetime/LifetimeController.java`:

```java
package demo.lifetime;

import org.springframework.security.core.Authentication;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
public class LifetimeController {

    @GetMapping("/api/public/csrf")
    public Map<String, String> csrf(CsrfToken csrfToken) {
        // When getToken() is called, the deferred token is resolved.
        return Map.of(
            "headerName", csrfToken.getHeaderName(),
            "token", csrfToken.getToken()
        );
    }

    @GetMapping("/private/home")
    public Map<String, String> home(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @PostMapping("/private/save")
    public Map<String, Boolean> save() {
        return Map.of("saved", true);
    }
}
```

The `/api/public/csrf` endpoint aids learning/testing CSRF with browsers/HTTP clients. After login or logout, Spring Security may rotate/clear the old CSRF token so the client must fetch a fresh token before the next POST. In production, never expose CSRF tokens to untrusted origins; govern CORS, cookies, and token retrieval per real application architecture.

### 9.5. Configuring idle timeout

For the demo app, you can set:

```yaml
# src/main/resources/application.yml
server:
  servlet:
    session:
      timeout: 20m
```

For production, add cookie/TLS settings as in section 4.1. **Do not add `SessionCreationPolicy.STATELESS`** to a form-login chain that relies on sessions; that conflicts with the goal of this example.

Apps enforcing an absolute lifetime need additional logic—such as storing the original authentication timestamp in trusted server state and checking it before critical actions rather than relying only on cookie expiration. High-privilege actions may demand step-up authentication even before the session expires.

## 10. Testing logout, CSRF, and session access with MockMvc

A Spring Security unit/integration test suite catches configuration errors early. It **does not replace** Servlet container session-timeout tests or real HTTP cookie replay tests, yet verifies core logout behavior.

File `src/test/java/demo/lifetime/LifetimeSecurityTests.java`:

```java
package demo.lifetime;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LifetimeSecurityTests {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousRequestRequiresLogin() throws Exception {
        mvc.perform(get("/private/home"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void authenticatedUserCanReadPrivatePage() throws Exception {
        mvc.perform(get("/private/home")
                .with(user("operator").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("operator"));
    }

    @Test
    void validFormLoginCreatesServerSession() throws Exception {
        MvcResult result = login();

        MockHttpSession session = (MockHttpSession)
            result.getRequest().getSession(false);

        assertNotNull(session);
        assertFalse(session.isInvalid());
    }

    @Test
    void unsafeRequestWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/private/save")
                .with(user("operator").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void unsafeRequestWithCsrfAndAuthenticationWorks()
            throws Exception {
        mvc.perform(post("/private/save")
                .with(user("operator").roles("USER"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.saved").value(true));
    }

    @Test
    void logoutWithoutCsrfDoesNotInvalidateSession()
            throws Exception {
        MockHttpSession session = sessionFromLogin();

        mvc.perform(post("/logout").session(session))
            .andExpect(status().isForbidden());

        assertFalse(session.isInvalid());
    }

    @Test
    void logoutWithCsrfInvalidatesSession() throws Exception {
        MockHttpSession session = sessionFromLogin();

        mvc.perform(post("/logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().isNoContent());

        assertTrue(session.isInvalid());
    }

    @Test
    void getLogoutMustNotInvalidateSession() throws Exception {
        MockHttpSession session = sessionFromLogin();

        mvc.perform(get("/logout").session(session));

        // Status may be the confirmation page generated by Spring Security.
        // GET must not trigger the logout action.
        assertFalse(session.isInvalid());
    }

    private MvcResult login() throws Exception {
        return mvc.perform(
                formLogin()
                    .user("operator")
                    .password("demo-password")
            )
            .andExpect(status().is3xxRedirection())
            .andReturn();
    }

    private MockHttpSession sessionFromLogin() throws Exception {
        MockHttpSession session = (MockHttpSession)
            login().getRequest().getSession(false);
        assertNotNull(session);
        return session;
    }
}
```

Run using the configured project's Gradle wrapper:

```bash
./gradlew test --tests demo.lifetime.LifetimeSecurityTests
```

**Expected results:** all 8 tests PASS when these classes/configurations run in a compatible Spring Boot setup. This document does not claim to have executed the program. The assertions verify:

| Test | Expected result | What it proves |
| --- | --- | --- |
| Anonymous GET private | Redirect to login | Form-login auth barrier is active. |
| Mock user GET private | 200, matching username | Private access rule works. |
| Form login | 3xx, non-invalid session exists | Form login creates a state-holding session. |
| POST without CSRF | 403 | CSRF protection blocks unsafe requests. |
| POST with user + CSRF | 200 | Valid requests are not falsely blocked. |
| Logout missing CSRF | 403, session stays valid | No forced logout via tokenless POST. |
| Logout with CSRF | 204, session invalidated | Logout handler invalidates server session. |
| GET logout | Session remains valid | GET does not destroy sessions in this config. |

**MockMvc limitations:** `MockHttpSession` is a mock object. Checking `isInvalid()` proves the logout handler called invalidate in the test context, **but does not prove** that an old cookie replayed over the network is rejected by the Servlet container or that session-store idle timeouts fire. Those require HTTP integration tests.

### 10.1. How to test real cookie replay

In a `@SpringBootTest(webEnvironment = RANDOM_PORT)` or staging environment using an HTTP client with manual cookie tracking:

1. GET the CSRF-token endpoint and record the anonymous `Set-Cookie: JSESSIONID=...`.
2. POST `/login` with valid username/password and CSRF token, saving the **post-login JSESSIONID** (session ID may change for fixation protection).
3. GET `/private/home` with the post-login cookie: expect 200.
4. Fetch the valid CSRF token for the logged-in session and POST `/logout` with that cookie: expect 204.
5. **Ignore the cookie-deletion header** and deliberately replay the **exact pre-logout JSESSIONID**: GET `/private/home` must be denied per contract (typically redirect to login).
6. Log in again to create a new session: the new session works, while the logged-out session **never comes back to life**.

Do not simply delete the cookie on the client and retry access; that proves nothing about server-side invalidation. Nor should you call `MockHttpSession.invalidate()` and call it an idle-timeout test.

### 10.2. How to test real idle timeout

In an isolated test environment:

1. Create a session via a real login against the container.
2. Set a short timeout via a test-only mechanism, e.g., `session.setMaxInactiveInterval(2)` on the **test session**; never expose a public endpoint allowing callers to alter timeouts.
3. Stop all polling/heartbeats using that session.
4. After exceeding the idle limit plus buffer for container granularity, replay the old cookie against a private endpoint.
5. Verify rejection and ensure a newly created session is not confused with the old one.
6. Repeat with Spring Session/Redis and across multiple nodes if that matches your real architecture.

With containers using minute-level granularity or distributed session repositories, do not assume `server.servlet.session.timeout: 1s` always expires precisely at one second. Increase wait margins or use appropriate test hooks and observe request acceptance directly.

## 11. Spring Security OAuth2 Resource Server: expiry does not mean revocation

To accept bearer JWTs instead of form sessions, the backend needs:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
```

Illustrative configuration:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.invalid/realm/demo
```

and in a stateless API chain:

```java
// Configuration snippet for a bearer-only API, not a direct
// replacement for the form-login SecurityConfig in section 9.
http
    .securityMatcher("/api/**")
    .sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
    )
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public/**").permitAll()
        .requestMatchers("/api/private/**").authenticated()
        .anyRequest().denyAll()
    )
    .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()));
```

**Additional checks required before production:**

- `issuer-uri` must point to a real, trusted issuer with proper JWT/JWK discovery configured; the `.invalid` URL above is illustrative only.
- Validate `aud` (audience) for your API, not just signature/issuer, whenever required by provider profile or app policy.
- Verify `exp`/`nbf`/`iat` and real clock skew.
- Map scopes/roles per contract with the Authorization Server; never trust claims sent by the caller in a request body.
- Distinguish user JWTs from service tokens where endpoints/permissions require.
- Choose a revocation mechanism if contracts require cutting off access before `exp`.
- Return proper 401/403 and `WWW-Authenticate` headers without leaking token values into URLs or error logs.

**Important:** the snippet above does not automatically add a denylist, introspection, token versioning, or instant revocation guarantees. Nor does it issue or rotate refresh tokens; token issuance belongs to the Authorization Server/OAuth2 Client, not the Resource Server.

### 11.1. When to switch from offline JWT to opaque introspection?

When fast revocation is required, systems can pick opaque tokens with Authorization Server introspection, or JWTs where the Resource Server checks additional trusted state. Trade-offs:

| Model | Advantages | Limitations |
| --- | --- | --- |
| Offline JWT, short access TTL | Minimal network dependency per check; high throughput. | Hard to revoke immediately if checking only signature/`exp`. |
| JWT + distributed denylist/version | Supports early revocation before `exp`. | Depends on store/synchronization; per-request lookup adds cost. |
| Opaque + introspection | Authorization Server centrally controls `active` state. | Depends on introspection endpoint; caching adds revocation lag. |
| Server-side session | Session record can be deleted immediately from store. | Depends on session store and multi-node sync. |
| Centralized gateway token check | Standardizes ingress validation in one place. | Internal services still need a threat model/authorization; avoid trusting gateway bypasses. |

Neither "JWT is always insecure" nor "opaque is always instant" holds universally. What decides is whether **your implementation of lifetimes, validation, revocation, and caching** satisfies policy.

## 12. Revocation workflows during security incidents

A playbook should define **trigger event, scope, actions, verification, and owner**. Four common scenarios:

### 12.1. User initiates logout on one device

- Invalidate the current local session.
- Clear security context/CSRF and remember-me if policy dictates.
- Delete client-side cookies and sensitive frontend state.
- If the app holds a client refresh token, send a revocation request via the supported mechanism.
- If IdP logout is required, execute the proper OIDC logout flow; never claim local logout logged out every RP.
- Replay old cookies/tokens to verify what is actually rejected.

### 12.2. User selects "log out all devices"

- Identify all sessions, refresh grants, and devices belonging to the user.
- Delete or invalidate all related sessions in the shared session store.
- Revoke corresponding refresh token families/grants; for unexpired access JWTs, trigger denylist/token-version policy or accept the documented TTL bound.
- Avoid mistakenly revoking sessions/services belonging to other users.
- Test across multiple devices, browsers, and APIs; measure revocation latency.

### 12.3. Account lock or password change due to suspected compromise

- Halt new authentications using old credentials; lock/reset credentials.
- Revoke sessions and refresh tokens per policy.
- Determine whether old access tokens can still call APIs until `exp`; under high risk, enforce immediate rejection at Resource Servers.
- Revoke privileges / update role caches, and evaluate in-flight requests or background jobs.
- Create audit records and safe correlation IDs; alert/investigate per incident workflow.
- Require reauthentication over a trusted channel after remediation.

### 12.4. Leaked service credential or machine-to-machine token

- Identify the client ID, secret/certificate, issuer, audience, scopes, and affected environments.
- Disable or rotate the credential at the issuing provider.
- Revoke grants/tokens and block unexpired access tokens within infrastructure capabilities.
- Issue new credentials via secret manager/workload identity and deploy safely without logging secrets.
- Verify the old client is rejected and the new client works; monitor for anomalous access.
- Never try to resolve this by clearing an employee's browser cookie.

### 12.5. Revocation requires evidence and reporting

Example incident timeline:

```text
10:00:00 Replay suspected on refresh token family F
10:00:02 Authorization Server marks F revoked
10:00:03 Clients can no longer refresh from F
10:00:07 Resource Servers receive event / update denylist cache
10:00:08 New requests with access tokens in F are rejected
10:00:09 Verification across all zones/instances completes
```

These timestamps **only illustrate how to report**, not a default SLA. To back a "revoked within 10 seconds" commitment, measure end-to-end with probe requests across all enforcement points, not merely by reading "revoke succeeded" in Authorization Server logs.

## 13. Distributed design: never let one node honor revoked access

### 13.1. Spring Session and session stores

Across multiple Spring Boot instances:

```text
Browser -> Load Balancer
              |-> App A
              |-> App B
              |-> App C
                     |
                 Shared Session Store (Redis/JDBC...)
```

If sessions live in per-node memory without a proper strategy, requests lose login when hitting another node. With a shared session store, logging out on node A must cause requests presenting the old session ID to B or C to fail. Still check local caches, TTLs, replication, sticky routing, and in-flight requests.

**Distributed tests must traverse the load balancer or target each node explicitly.** Testing `HttpSession.invalidate()` on a single JVM does not prove the cluster rejects old session IDs.

### 13.2. Shared denylist or token version

A `HashSet` inside one instance cannot protect the entire system. When choosing a JWT denylist:

- Use a shared store with suitable durability and consistency (e.g., Redis engineered and monitored for this role).
- Store `jti` or an appropriate identifying digest, never logging full tokens; set TTL long enough to cover `exp` plus clock skew.
- Define store-unavailability behavior: **fail-open or fail-closed**? For sensitive privileges, fail-open may violate revocation commitments; fail-closed increases outage risk.
- Monitor cache invalidation, event lag, cross-region replication, and restart recovery.
- Never mark "revoked" solely in an admin database if Resource Servers never read that state.

### 13.3. Role changes and still-valid tokens

When roles are embedded in a JWT, changing roles in the database **does not rewrite already-signed JWTs**. Options include short access-token TTLs, revoking token versions, dynamic authorization checks in services, or issuing fresh tokens after privilege changes. Distinguish **revoking authentication** from **revoking a single authority**: the user may remain signed in while losing permission for a specific action.

## 14. Common security and operational pitfalls

1. **Deleting only the cookie and declaring logout secure.** If the server did not destroy the session, a copied cookie still works.
2. **Invalidating only the current session while promising "log out all devices".** Other devices have separate sessions, plus refresh grants and IdP sessions.
3. **Confusing `server.servlet.session.timeout` with JWT `exp`.** They are two separate mechanisms in two different systems.
4. **Assuming JWTs automatically expire when a user logs out.** `exp` does not change because of a local logout.
5. **Revoking a refresh token and thinking the access token is immediately dead.** Issued access tokens still work unless Resource Servers check revocation state.
6. **Giving access tokens huge lifetimes "to avoid refreshing".** Widens the abuse window if a token leaks.
7. **Letting refresh tokens slide forever with no absolute TTL.** Creates "never-ending sessions" and weakens control over compromised clients.
8. **Handling refresh rotation non-atomically.** Two concurrent requests can both spend the same old token, breaking accurate replay detection.
9. **Automatically locking the whole token family on legitimate network-error retries.** Design proper transactions, retries, and grace handling.
10. **Using a local `HashSet` as a production denylist.** Other nodes keep accepting the JWT.
11. **Configuring huge clock skew.** Extends token validity beyond requirements.
12. **Forgetting introspection response caches.** The AS says revoked while the gateway still serves a cached `active` entry.
13. **Setting TTL via cookie `Max-Age` while forgetting the server session.** Client cookies and server session stores have separate lifecycles.
14. **Forgetting CSRF when adding logout or cookie-authenticated POSTs.** `POST /logout` requires CSRF by default; never switch it to GET casually.
15. **Ignoring remember-me or SSO.** A brand-new session may be auto-restored after local expiry; distinguish that from an old session resurrecting.
16. **Extending sessions inadvertently via background polling.** Idle timeouts lose meaning for "user inactivity" if background polls refresh them.
17. **Testing with real production tokens.** Never put production credentials in URLs, shell history, tickets, or test logs.
18. **Printing full JWTs/refresh tokens in logs to debug revocation.** Log validated minimal IDs/claims, avoiding raw secrets.
19. **Having no fallback when the denylist/repository fails.** Fail-open vs. fail-closed behavior must be defined, monitored, and tested.
20. **Testing only happy-path requests.** Test stale credentials after logout/timeout/role revocation, across nodes and under load.
21. **Thinking the browser Back button showing an old page means the session is alive.** That can be browser cache or SPA state; issue a real request to the server.
22. **Revoking credentials while ignoring in-flight jobs.** Requests admitted prior to revocation may still finish; enforce checks at critical side-effect boundaries.

## 15. Deployment acceptance test matrix

| Scenario | Test performed | Expected outcome |
| --- | --- | --- |
| Session login | Valid login then GET private | Allowed; session ID never leaked in URL/logs. |
| Inactive session | Send no requests past idle timeout, then replay cookie | Old session is rejected. |
| Active session | Send requests before idle expires | Extended only if policy permits. |
| Absolute session lifetime | Keep session active past absolute cap | Reauthentication/revocation enforced per policy. |
| Logout without CSRF | POST logout without token | Rejected; no unintended logout. |
| Logout with CSRF | POST logout with valid session and CSRF | Session invalidated; replayed old cookie rejected. |
| Log out all devices | Create two sessions then revoke all | Both sessions rejected, not just current browser. |
| JWT before exp | Valid token with right issuer/audience/signature | Allowed per permissions if unrevoked. |
| JWT at/past exp | Send token past boundary accounting for clock skew | Rejected past actual validator limit. |
| JWT wrong issuer/audience/signature | Send malformed/invalid test token | 401; untrusted claims ignored. |
| JWT revoked before exp | Revoke via `jti`/version/introspection then retry | Rejected within committed revocation SLO. |
| Refresh rotation | Use R1 → R2, then reuse R1 | Reuse handled per family policy; no unintended R3 issued. |
| Revoked refresh token | Client sends old refresh token for new access token | No new token issued. |
| Revoked privilege | Remove role then call endpoint with old token/session | Privilege revoked within policy timeframe. |
| Multi-node | Logout/revoke on A; send old credential to B/C | All enforcement points reject within consistency bounds. |
| SSO/remember-me | Local logout then revisit in browser | Re-login behavior matches policy, distinct from old session reuse. |
| Infrastructure failure | Denylist/introspection/session store temporarily unreachable | Fail-open/fail-closed matches threat model; alerts fire. |
| Logs and observability | Test using `FAKE_TOKEN_TEST_ONLY` sentinel | No tokens/secrets leaked; safe correlation IDs present. |

### 15.1. Testing TTL with a controllable clock

For pure Java time-issuing/checking logic, inject `Clock` (or a replaceable time source) and use `Clock.fixed(...)` in unit tests instead of unnecessary `Thread.sleep(...)`. This lets you test right before, at, and right after `exp` deterministically.

For Servlet containers, real JWT decoders, Redis/Spring Session, and external IdPs, faking a clock in one service **does not necessarily shift time in other components**. Use integration tests tailored to each: test-issuer tokens with short `exp`, real session timeouts, or environments with controlled clocks/TTLs. Never claim a fixed-clock unit test proves all nodes agree on time.

### 15.2. Measuring revocation SLO

In a test environment:

1. Issue a fake/test token with a known TTL; record issuance time, `exp`, issuer, and sanitized token ID.
2. Confirm requests before revocation succeed.
3. Submit the revocation request and record when the system **commits** processing.
4. Continuously probe through every Resource Server/gateway; record the last accepted timestamp and first time all nodes reject.
5. Reconcile results against cache TTLs, replication lag, and clock skew.
6. Confirm newly issued valid accounts/tokens still work—avoid "block everything" shortcuts to fake 100% revocation.
7. Never put raw tokens in reports; use token IDs, digests, or correlation IDs.

## 16. Deployment checklist and scenario exercises

Before deploying session/token changes:

- **Document** idle/absolute/expiry lifetimes and maximum acceptable stale-privilege windows.
- **Classify credentials**: browser sessions, access JWT/opaque tokens, refresh grants, remember-me, IdP SSO, and service secrets.
- **Map enforcement points**: app, gateway, Resource Server, business services, session stores, caches.
- **Select revocation mechanisms** actually enforced at those points; never update only the UI or Authorization Server.
- **Protect tokens**: TLS, proper cookie attributes, `Authorization` headers; keep out of URLs/logs/analytics and source code.
- **Preserve CSRF** on requests carrying auto-sent cookies/credentials; test `POST /logout` and state-changing POSTs.
- **Replay stale credentials** after revocation: cookies, access tokens, refresh tokens, permission caches.
- **Test multi-device and multi-node**, including SSO, browser Back button, and apps with background polling.
- **Measure actual revocation latency**, not just revocation event emission.
- **Define failure playbooks** when IdP, session store, introspection, or denylist is unavailable.
- **Enforce controlled logging**, keeping session IDs, tokens, and secrets out of tickets and traces.
- **Rehearse rollbacks and key/secret rotation**, distinguishing single-client revocation from full signing-key rotation.

### Scenario exercises

A system defines these policies:

```text
Session idle timeout: 20 minutes
JWT access token: 10 minutes
Refresh token: rotation, 30-day absolute lifetime
Resource Server: verifies signature/exp only, no denylist
```

At **10:00**, a user account is locked and all refresh tokens are revoked. A JWT was issued at **09:58** and expires at **10:08**.

**Question A:** Are requests using that JWT at 10:02 guaranteed to be rejected?

**No.** Because the Resource Server checks only signature/`exp` and ignores lock status, that JWT can still be accepted until expiry (subject to clock skew). Revoking refresh tokens blocks minting new tokens; it does not invalidate already-issued JWTs.

**Question B:** What is needed if policy demands cutting off access before 10:01?

Add a near-instant access-token rejection check consulted by all enforcement points (introspection, denylist, token version/security epoch, or trusted account-status lookup), ensuring propagation and cache TTLs stay under the threshold. Then measure with real requests across nodes.

**Question C:** If the user can immediately sign back in via SSO after local logout, does that prove the old session was not deleted?

No. The IdP session may still be active and issue a **brand-new session**. Compare session IDs, grants, and audit logs to distinguish a fresh login from old-session replay.

**Question D:** If a worker resends refresh token `R1` after a lost network response, should the system automatically lock the entire account?

There is no single answer. Design **rotation, retries, race handling, and reuse detection** per policy, evaluating whether token theft is likely and which grant/family scope is affected. Locking an entire account on any network glitch causes avoidable disruption; ignoring all replays weakens security.

## 17. Conclusion and official references

**Lifetime** bounds how long credentials remain valid over time; **revocation** cuts off access at or before a controlled point. They complement each other without replacing one another. Session stores allow immediate server-side session deletion; self-contained access JWTs require short `exp` plus state checks for early revocation; refresh tokens need bounded lifetimes, rotation, and replay detection; app logout does not automatically log out every IdP, device, or service.

A well-deployed system knows **which credentials exist, who can revoke them, what every server checks, the maximum revocation lag, and which tests prove it**.

Official documentation:

- Spring Security 6.5 — [Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html).
- Spring Security 6.5 — [Handling Logouts](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html).
- Spring Security 6.5 — [CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html).
- Spring Security 6.5 — [OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html).
- Spring Security 6.5 — [OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html).
- Spring Security 6.5 — [MockMvc Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/).
- Spring Session — [Integration with Spring Security](https://docs.spring.io/spring-session/reference/spring-security.html).
- OAuth 2.0 Token Revocation — [RFC 7009](https://www.rfc-editor.org/rfc/rfc7009).
- OAuth 2.0 Token Introspection — [RFC 7662](https://www.rfc-editor.org/rfc/rfc7662).
- OAuth 2.0 Security Best Current Practice — [RFC 9700](https://www.rfc-editor.org/rfc/rfc9700).
- JWT claims `exp`, `nbf`, `iat`, `jti` — [RFC 7519](https://www.rfc-editor.org/rfc/rfc7519).
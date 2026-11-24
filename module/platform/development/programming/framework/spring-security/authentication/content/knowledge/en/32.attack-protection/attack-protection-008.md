# Session fixation, token replay, and the boundaries of each mitigation in Spring Security

## 1. Two similarly named attacks with different starting points

**Session fixation** occurs when an attacker **knows or forces a session ID before the victim logs in**, hoping the application keeps that same session identifier after elevating trust from anonymous to authenticated. The attacker does not necessarily steal the cookie **after** login: they can obtain a server-issued anonymous session, plant that ID into the victim's browser, wait for the victim to sign in, and then try using the known ID.

**Token replay** occurs when a party reuses a **credential/proof value that was observed or stolen**, often at another time or from another actor, to continue accessing or authenticating. The token may be a session cookie, Bearer OAuth access token, refresh token, remember-me cookie, authorization code, OTT/magic link, or challenge response. Each has a different lifecycle: some tokens are **designed for repeated use** until expiration (session cookies and most access tokens), while others **must be consumed once** (authorization codes, OTP/OTT per policy, refresh tokens under rotation).

**Core conclusion:** changing the session ID on login solves the risk of **knowing beforehand the ID of a session about to be elevated**; it does not automatically invalidate the current session cookie if that cookie **is stolen after login**. Conversely, OAuth PKCE or refresh-token anti-replay does not replace HTTP session fixation protection.

| Question | Session fixation | Cookie/token replay |
| --- | --- | --- |
| What does the attacker need? | An ID known/planted into the browser **before login** | A copy of an active or previously valid cookie/token |
| Critical moment | Trust transition **pre → post authentication**, privilege elevation, principal switch | **After** the token is issued or observed |
| Exploitation condition | Post-login session continues accepting the **old ID** | Verifier still trusts that credential or lacks single-use enforcement |
| Direct barrier | **Rotate/change session ID** at login/privilege-change boundaries | Protect token from leaks, TTL, revoke, replay detection, sender-constraining, or one-time consumption per type |
| What it does not solve alone | A **new** session cookie stolen afterward | A session fixed before login; missing issuer/audience/CSRF/authorization |
| Mandatory tests | Old ID cannot access the authenticated session after login | Reusing the same token/credential in another session or actor per policy fails or triggers proper handling |

Do not equate replay with "re-sending an HTTP GET": a user hitting page refresh within the same session is normally legitimate. Replay is **reusing a credential/proof** against security intent. A typical Bearer token **can legitimately be sent many times** to APIs until expiration. The problem is **stopping others from using a stolen token**, not assuming "every access token is single-use".

## 2. Drawing the boundaries: anonymous session, authenticated session, Bearer token

### 2.1. Session fixation from before login

```text
Attacker                   Victim's browser                Spring MVC app
   |                            |                              |
   |-- opens page -> gets SID=X ------------------------------>|
   |<---------------------- Cookie SID=X ----------------------|
   |
   | (via another flaw, tries to set SID=X in victim's browser)
   |--------------------------->|                              |
   |                            | GET /login; cookie SID=X     |
   |                            |----------------------------->|
   |                            | POST /login; right password  |
   |                            |----------------------------->|
   |                            |                         authenticated
   |                            |                         rotate X -> Y
   |                            |<--- Set-Cookie SID=Y --------|
   |                            |                              |
   |-- GET /account; SID=X ----------------------------------->|
   |<------------ NOT authenticated ---------------------------|
   |                            |                              |
   |                            | GET /account; SID=Y          |
   |                            |----------------------------->|
   |                            |<----- authenticated ---------|
```

**Required invariant:** the victim's authentication binds to **Y**, never the previously known ID **X**. The old session ID cannot retrieve the victim's principal. If the user owns session Y and Y is later stolen by an attacker, session fixation protection **is no longer sufficient**.

On modern Servlets, Spring Security enables session fixation protection by default; the common strategy is `HttpServletRequest.changeSessionId()`. It changes the ID of **the same session**, so it **does not wipe all session attributes**. Applications must separately govern pre-authentication attributes such as checkout data, redirect targets, pending MFA, or custom "verified" flags.

### 2.2. Replaying cookies after login is a different scenario

```text
Browser A logs in successfully: cookie SID=Y
    |
    | (XSS, malware, proxy/log leak, malicious browser extension,
    |  session store compromise, or another flaw leaks Y)
    v
Attacker sends Cookie: SID=Y to /account

If the server still holds session Y and has no other binding:
    -> RISK of session hijacking / replaying Y
    -> Prior rotation at login does NOT immediately invalidate Y
```

A session cookie is effectively a **bearer credential**: the server trusts whoever holds a valid ID. `HttpOnly`, `Secure`, `SameSite`, HTTPS, and XSS defenses reduce certain **leak/use vectors**, yet do not cryptographically bind the cookie to a device. With XSS, `HttpOnly` blocks JavaScript from reading cookies, yet malicious scripts can still fire **same-origin requests** using the cookie automatically sent by the browser.

### 2.3. JWT access tokens are not session IDs

A Resource Server using `oauth2ResourceServer().jwt()` validates Bearer JWTs on each request. It **does not use an HTTP session by default** to know whether a JWT was used before. A JWT valid in signature, `iss`, `aud`, `exp`, and scopes can be reused repeatedly. Stopping **theft + replay of access tokens** requires other layers such as sender-constrained tokens (DPoP/mTLS, if issuer/client/resource server all support them), lifecycle controls, and leak prevention. Creating a new session on web login does not expire an independent JWT access token.

## 3. Session fixation: origins, scenarios, and exploitation conditions

### 3.1. How can an ID be "fixed"?

The attacker must get the victim's browser to use a session ID the attacker already knows or controls. Paths commonly analyzed in threat models:

- The app accepts session IDs in URLs or query parameters (URL rewriting/`:jsessionid=...`), causing shared links to carry session identity or attacker-prepared IDs.
- Flawed cookie scope/domain/path or untrusted subdomains let browsers accept a cookie with a session ID set by another origin (**cookie tossing/cookie injection**).
- HTTP without TLS, misconfigured proxies/edges, or mixed content allow tampering with cookies/tokens in transit.
- Custom app-generated session IDs have low entropy, are predictable, or accept values never issued by the server.
- The app keeps the pre-login session ID after authentication/role elevation, turning a previously known ID into an authenticated user's ID.

Not every `JSESSIONID` typed by an attacker becomes an accepted server session. Servlet containers/frameworks typically generate random IDs and only trust IDs belonging to issued sessions. Fixation attacks depend on a **real ID injection/synchronization vector**; tests should specify the tested mechanism rather than claiming every app is vulnerable to fixation merely for using session cookies.

### 3.2. Core countermeasure: rotate at boundaries

Per the OWASP Session Management Cheat Sheet, whenever **privilege level changes**, the app must **renew the session ID**, especially anonymous → authenticated, user role elevation, or switching principals. In Spring Security, session fixation protection primarily applies on **successful interactive authentication**. If a project elevates privileges in a controller or uses a custom login filter, ensure the strategy runs along that exact path; never assume every request mutating `SecurityContext` automatically triggers all session strategies.

Timeline:

| Milestone | Browser holds cookie | Server knows session | Expected |
| --- | --- | --- | --- |
| Before login | SID_A | Anonymous session SID_A | Public permissions only |
| Login succeeds | New SID_B | Authenticated session SID_B | SID_B bound to principal; SID_A loses access |
| Attacker tries SID_A | SID_A | Does not resolve authenticated SID_B | Rejected/anonymous |
| Victim uses SID_B | SID_B | Valid session | Accesses routes matching role |
| After logout | Cookie cleared/expired; session invalidated | SID_B invalidated server-side | SID_B cannot access again |
| Re-login | New SID_C | New session | SID_B is not reused |

Switching principal Alice → Bob in the same browser requires a policy resetting **Alice-bound proofs and permissions**, not merely changing `Authentication.getName()` while retaining Alice's cached permissions/MFA state. Session ID rotation is one lifecycle step; authorization, pending factors, and account bindings must be re-evaluated.

## 4. Spring Security 6.x Servlet: three fixation protection strategies

Spring Security offers `http.sessionManagement(session -> session.sessionFixation(...))`. Common strategies documented officially:

| Strategy | Behavior | When to use / limitations |
| --- | --- | --- |
| `changeSessionId()` | Calls Servlet container's `HttpServletRequest.changeSessionId()`; **changes ID while keeping session object/attributes** | **Default** on Servlet 3.1+; standard choice with Spring Boot 3 / modern Tomcat |
| `migrateSession()` | Creates a new session and **copies all session attributes** to the new session | Default on older Servlet <= 3.0 containers; does not "clean" pre-auth data |
| `newSession()` | Creates a "clean" new session, though Spring Security still carries over certain security-related attributes | Use to limit carry-over; still test flash messages/CSRF/shopping carts and integration |
| `none()` | Disables session fixation protection | **Do not use** for cookie-based interactive login; increases fixation risk |

**Scope of `changeSessionId()`:** it changes the ID of the session—it does not **invalidate all other sessions**, does not "rotate all remember-me tokens", and does not revoke OAuth/JWT access tokens. Calling Java Servlet API `changeSessionId()` can emit `HttpSessionIdListener`; Spring Security also emits `SessionFixationProtectionEvent`. If listening to both, avoid double-counting.

### Minimal, clear-intent configuration

In a Spring Boot 3.x, Java 17+, Servlet/Spring MVC app, create `SecurityConfig.java`:

```java
package com.example.session;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/public/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionFixation(fix -> fix.changeSessionId()))
            .logout(logout -> logout
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID"));
        // Do not disable CSRF in cookie-based web apps.
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build());
    }
}
```

This example uses only a demo Alice account and password `demo-password` BCrypt-hashed at startup. **Never use static passwords and `InMemoryUserDetailsManager` in real systems**: use a database, password hashes, and proper account lock/MFA/rate-limit policies.

With modern Spring Security/Servlet configs, `changeSessionId()` is the default, so this DSL **makes intent explicit**, not an independent extra patch. If an app disabled session fixation protection or implements custom login/elevation, inspect the exact authentication path and test it.

### Controller creating an anonymous session and viewing identity

Create `SessionController.java` in the same package. Return only a message, **never return the session ID in responses**:

```java
package com.example.session;

import java.security.Principal;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SessionController {

    @GetMapping("/public/session")
    public String createPreLoginSession(HttpServletRequest request) {
        request.getSession(true); // for testing pre-login ID
        return "anonymous session initialized";
    }

    @GetMapping("/me")
    public String me(Principal principal) {
        return "Hello " + principal.getName();
    }
}
```

This example is a Spring application config and will not run standalone with `javac` without dependencies and a `@SpringBootApplication` class. To test end-to-end, generate a Boot 3 project from Spring Initializr with `spring-boot-starter-web`, `spring-boot-starter-security`, `spring-boot-starter-test`, and `spring-security-test`, put the classes in the scanned package, run `./gradlew bootRun` (Windows: `gradlew.bat bootRun`), and test in a browser over HTTPS/local test.

## 5. Testing session fixation: do not confuse rotation with logout

### 5.1. Real testing sequence

1. Browser A loads `GET /public/session`, records cookie `JSESSIONID=SID_A` **strictly in the test environment**, not logged in yet.
2. Browser A submits `POST /login` with valid password and valid CSRF. Observe browser receives `JSESSIONID=SID_B`, **SID_B differs from SID_A**.
3. Browser A sends `GET /me` with SID_B and receives `Hello alice`.
4. Browser B / an independent curl cookie jar holding only **SID_A** calls `GET /me`. Expected: cannot enter authenticated resources—typically login redirect or HTTP 401 depending on entry point.
5. Browser B sends SID_B leaked in the **test fixture**, which may still be accepted without extra binding. This tests the **protection boundary**: session rotation does not block replay of the current cookie.
6. Browser A logs out per the app's HTTP method/CSRF; the server must invalidate SID_B. Verify old SID_B loses access, not merely checking `Set-Cookie: JSESSIONID=;...` in the browser.

**Never put real production session IDs in logs, public request inspectors, or tickets.** In internal automated tests, compare IDs in memory; log only a `rotated` boolean, never dump cookies.

### 5.2. MockMvc test verifying ID rotation at login

Create `src/test/java/com/example/session/SessionFixationTest.java` in the Spring Boot project from section 4:

```java
package com.example.session;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class SessionFixationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void rotatesSessionIdWhenUserLogsIn() throws Exception {
        MvcResult initialized = mvc.perform(get("/public/session"))
                .andExpect(status().isOk())
                .andReturn();
        MockHttpSession beforeSession =
                (MockHttpSession) initialized.getRequest().getSession(false);

        assertThat(beforeSession).isNotNull();
        String oldId = beforeSession.getId();

        MvcResult login = mvc.perform(post("/login")
                    .session(beforeSession)
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "demo-password"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        MockHttpSession afterSession =
                (MockHttpSession) login.getRequest().getSession(false);
        assertThat(afterSession).isNotNull();
        assertThat(afterSession.getId()).isNotEqualTo(oldId);

        mvc.perform(get("/me").session(afterSession))
                .andExpect(status().isOk());
    }
}
```

Points to watch:

- Capture the ID **before** POST; if you merely keep a reference to the same `MockHttpSession` and check `beforeSession.getId()` after login, you may compare the very same mutated object to itself and invalidate the test.
- `MockMvc` tests filters/sessions in the test harness, yet **does not prove production Servlet container + cookie jar + reverse proxy** eliminate all paths accepting old IDs. Add browser/E2E tests with **two cookie jars** and HTTPS.
- Testing with `@WithMockUser` or `.with(user("alice"))` mocks an authenticated user and may **skip login authentication success/session fixation strategies**. Submit the real login form as shown above.
- When a wrong password still redirects to an error page, checking status 302 alone is insufficient. Also assert `GET /me` returns the right principal and cookies/sessions changed as expected.
- If configuring a custom `AuthenticationFilter` or custom login controller, invoke `SessionAuthenticationStrategy` at the right moment and persist `SecurityContext` via `SecurityContextRepository`; merely setting `SecurityContextHolder` does not guarantee persistence or proper rotation in Spring Security 6+.

## 6. Token replay: identify the **token type** before picking a countermeasure

"Token replay" is not one single attack with one single fix. Ask four questions: is this token generated for **single-use or multi-use**, who may hold it, how is it bound to the sender, and what invalidates it?

| Token/credential | Intended usage | What does replay mean? | Direct countermeasure | Limitations |
| --- | --- | --- | --- | --- |
| **`JSESSIONID` cookie** | Multi-use across HTTP requests in a session | Someone else uses a stolen active cookie | `HttpOnly`/`Secure`/`SameSite`, TLS, XSS defense, login rotation, server-side invalidate/timeout, reauth | Login rotation does not stop theft of the new cookie; cookies are not proof-of-possession |
| **Simple remember-me cookie** | Auto-relogin across sessions | Captured cookie can auto-login from another user agent | Expiration, secret key, password change, cookie flags; consider disabling on sensitive routes | Spring docs warn captured hash-based remember-me cookies work from other user agents until expiry |
| **Persistent remember-me series/token** | Token series in persistent store, rotated on use | Old cookie appears after rotation or token theft | Rotate token in persistent repo, detect mismatch, revoke series/credential, protect storage | Race/false-positive risk requires testing; not equivalent to session fixation protection |
| **OAuth Bearer access token** | Multi-use until expiry/scope/resource | Stolen token used on API by another actor | HTTPS, short TTL, audience/scope, leak prevention, DPoP/mTLS sender constraint if supported | Valid JWT signature does not prove sender is rightful owner; `jti` alone does not reject replay |
| **Refresh token** | Exchanged for new access tokens | Both attacker and client reuse one refresh token | **Rotation + reuse detection + family revocation** or sender-constrained tokens | Rotating without reuse detection/family revocation leaves gaps; concurrency must be handled |
| **Authorization code** | **Single-use** at token endpoint | Thief exchanges code for token or resends code | One-time code, short TTL, client/redirect binding, **PKCE S256** | PKCE protects exchange when attacker lacks verifier; does not protect issued access tokens |
| **OAuth state / OIDC nonce** | Binds request/response or ID Token to login transaction | Old callback/ID Token injected into another flow | Randomness, transaction/session binding, comparison, one-time lifecycle | Does not replace TLS/PKCE; does not stop API Bearer access token replay |
| **OTT/magic link** | Issued once, consumed strictly once | Resubmitting link/code after consumption | TTL, **atomic consume**, account binding, prevent email scanners consuming GET | A link stolen **before first use** can still be used first by an attacker |
| **TOTP/HOTP** | Code per time window/counter, not single-use unless server stores state | Resubmitting code inside window or reusing old counter | Prevent reuse via last-used step/counter, atomic update, rate limits | Clock skew/retry policy impacts; do not reuse OTT DB logic unthinkingly |
| **WebAuthn response** | Signed assertion for a specific challenge/request | Submitting assertion for a used challenge or wrong origin/RP | Random challenge, TTL, one-use, origin/RP ID, signature, credential binding | Sign counter is not strictly reliable across all authenticators |
| **CSRF token** | Proves form request originated within issued security context/browser | Reusing a form token may be valid per policy | Check CSRF on state-changing requests, SameSite support | Spring's CSRF token is **not one-time by default**; does not prevent access token theft |
| **Business idempotency key** | Identifies an operation to avoid duplicate payments | Resubmitting the same payment request | Dedupe/idempotency at DB/payment layer | Does not prove identity/token ownership; does not replace authentication |

**A valid Bearer access token may legitimately be used 100 times** in a session, so a replay detector that "rejects any JWT seen twice" breaks the protocol. True anti-replay for access tokens needs sender constraints or explicit stateful designs with clear cost/behavior rules.

## 7. JWT and Bearer access tokens: valid signatures do not stop token theft

### 7.1. Resource Server model

When an API configures Spring Security:

```java
http.oauth2ResourceServer(oauth2 -> oauth2.jwt());
```

the library verifies JWT signatures per your trust/key config and validators. To protect an API properly, restrict `issuer-uri` (trusted issuer), `aud` (intended API), `exp`/`nbf`, allowed algorithms, and scopes/roles/tenant. A validly signed JWT issued for **another API** must not be accepted.

**However:** checking signature, issuer, audience, and expiry **cannot distinguish** the real owner from an attacker holding the exact same Bearer token string. On an API accepting `Authorization: Bearer T`, any attacker holding unexpired `T` can use `T` without additional binding/denial. `jti` is a token ID; unless the server stores/queries used/revoked state, `jti` **does not create replay detection on its own**.

For OAuth2 JWT access tokens, session fixation settings on a form-login web chain **also do not revoke already-issued JWTs**; the two token systems have distinct trust stores and lifecycles.

### 7.2. Short-lived access tokens and revocation

Short TTLs bound **how long** a stolen token works, yet do not block replay **within the valid window**. For self-contained JWTs, browser logout does not automatically invalidate tokens across Resource Servers that only check signatures/expiry. Revoking before expiry requires stateful checks: `jti` denylists, introspection/opaque tokens, event-driven revocation, sender constraints, or suitable auth strategies.

**Denylists** carry cache/database costs, multi-node synchronization, TTL cleanup, and fail-open risks during store outages. **Introspection** gives centralized state control at the cost of network dependencies. There is no "one-line logout" that instantly invalidates every JWT across all services.

### 7.3. Sender-constrained access tokens: DPoP and mTLS

Per **OAuth 2.0 Security BCP RFC 9700**, Authorization Servers/Resource Servers should consider sender-constrained access tokens, such as:

- **Mutual TLS (mTLS, RFC 8705):** tokens bound to the client's certificate/key; Resource Servers verify proof on matching connections.
- **DPoP (RFC 9449):** clients hold a private key and sign a fresh DPoP proof JWT per HTTP request containing method `htm`, target URI `htu`, time `iat`, unique `jti`, and access token hash `ath` when presenting a token. Servers validate signatures, proof binding, and anti-replay windows. A stolen Bearer token **without the private key** is insufficient.

**Limitations:** sender constraints cannot save you if the attacker steals both the access token **and the private key**, or executes requests inside the browser/process holding the key (e.g., XSS). DPoP only helps when the Authorization Server **issues bound tokens** and the Resource Server **actually validates proofs**, not merely adding a `DPoP` header. Nonces, TTLs, `jti` replay caches, canonical target URIs behind reverse proxies, and key lifecycles must be managed. Spring Security resource servers may require custom config/extensions to enforce DPoP; **never claim default `.jwt()` checks DPoP automatically**.

## 8. Refresh token rotation: replay detection differs from session ID rotation

Refresh tokens are exchanged for new access tokens, so they typically outlive access tokens. For OAuth public clients, RFC 9700 requires refresh tokens to be **sender-constrained or use refresh token rotation**.

A refresh token family:

```text
Client receives RT1
    |
    | POST /token grant_type=refresh_token, refresh_token=RT1
    v
Authorization Server (atomic)
    -> invalidates RT1
    -> issues RT2 + new access token
    -> remembers RT1 belongs to RT-family-F

Client uses RT2 -> issues RT3, RT2 becomes invalid

Attacker replays RT1:
    -> RT1 already invalid => detect potential reuse/compromise
    -> revoke active token/family or apply policy response
    -> force client to log in again when needed
```

**Boundary:** rotation **detects** reuse of an old token, yet cannot tell with certainty which actor is the attacker. The server cannot determine "client vs attacker" from the stale `RT1` token alone. On reuse, respond defensively by revoking the active refresh token/family. Atomicity at the token endpoint is critical: two concurrent refresh requests with the same `RT1` **must not both succeed**. Define grace policies carefully for network retries to avoid false positives, keeping grace bounded so old tokens never become endlessly reusable.

**Do not confuse:**

- `sessionFixation().changeSessionId()` rotates the **HTTP session ID** after interactive login.
- **Refresh token rotation** rotates the **OAuth refresh credential** when clients request new tokens.
- **Signing-key rotation** rotates JWT signing keys and affects signature verification without revoking unexpired JWTs while old keys remain trusted.
- **CSRF token rotation** (when policy rotates it) protects browser request contexts, not replacing the three above.

## 9. Browser/cookie: protective attributes and practical limits

### 9.1. Secure, HttpOnly, and SameSite

For session cookies:

| Attribute | Reduces risk of | Does not solve alone |
| --- | --- | --- |
| `Secure` | Browser sends cookie only over HTTPS, preventing HTTP exposure | XSS, malware, other token theft vectors |
| `HttpOnly` | Ordinary JavaScript cannot read cookies via `document.cookie` | XSS can still send same-origin requests using the cookie |
| `SameSite=Lax/Strict` | Reduces cross-site cookie inclusion in many CSRF scenarios | XSS, same-site cross-origin attacks, special cross-site flows |
| Narrow `Path` and `Domain` | Limits where cookies are sent/received; avoids leaking to untrusted subdomains | Cookie theft within the allowed scope |
| `__Host-` prefix when applicable | Enforces `Secure`, `Path=/`, and no `Domain` per browser rules | Does not turn cookies into proof-of-possession |
| Server-side TTL/idle/absolute timeout | Bounds how long a session stays valid | Replay within the active validity window |

In Spring Boot 3 web apps, configure cookie attributes via server properties and Spring Session if used; inspect `Set-Cookie` in real browsers/proxies because behavior depends on deployment:

```yaml
server:
  servlet:
    session:
      cookie:
        http-only: true
        secure: true
        same-site: lax
      timeout: 30m
```

This is an **illustrative config** for HTTPS production; on HTTP localhost, `Secure` cookies may not be sent by browsers, making logins look like they "lose session". When apps use IdP/OIDC callbacks across sites, `SameSite=Strict` or misaligned `Lax` configs with redirect/POST bindings can break flows; design and test cookie policies against real flows and CSRF defenses instead of assuming one universal setting.

**`timeout: 30m`** is usually a servlet session idle timeout; OWASP also recommends considering an independent **absolute timeout**. Never assume `server.servlet.session.timeout: 30m` creates a hard 30-minute cap from login time, because activity extends idle sessions.

### 9.2. HTTPS and HSTS

HTTPS prevents in-transit eavesdropping/tampering when TLS terminates at trusted endpoints. HSTS helps browsers resist HTTP downgrades for domains that received the policy. Yet reverse-proxy TLS termination, logged headers, client JS, session store databases, email magic links, and malware remain possible credential leak paths. TLS **does not** replace session rotation or replay detection.

### 9.3. CSRF is not Bearer token replay

- **CSRF:** the victim's browser auto-attaches a login cookie to the real site when tricked from another site. Attackers typically **never know the cookie**. Spring Security CSRF tokens verify the **source/context of state-changing requests**.
- **Session hijack/replay:** the attacker holds a copy of the cookie and sends it directly. The victim's CSRF token may not stop them if they compromised the browser or stole cookies alongside other data.
- **Bearer JWT in Authorization header:** browsers do not auto-attach `Authorization: Bearer ...` headers from other sites like session cookies. CSRF risk depends on how clients store/send tokens. If cookies carry tokens or auto-authenticate requests, CSRF analysis is still required.

Spring Security enables CSRF by default for web apps using cookies and form login. **Never disable CSRF just to test `POST /login` or `/logout` quickly.** Tests must submit valid hidden CSRF tokens/cookies.

## 10. Remember-me and logout: session cookies are not persistent login cookies

Spring Security offers two main remember-me styles:

1. `TokenBasedRememberMeServices` builds a hashed/signed cookie from username, expiry, password, and key. Spring docs warn a stolen cookie can be used from **another user agent** until it expires (or password/key changes).
2. `PersistentTokenBasedRememberMeServices` uses a `PersistentTokenRepository` storing series/tokens, e.g., JDBC. It can rotate tokens on auto-login and detect certain mismatches. Test concurrency, persistence, logout/revocation, and token theft; do not treat persistent remember-me tokens as identical to session IDs.

Typical logout:

- Invalidate the **HTTP session** server-side and delete the `JSESSIONID` cookie client-side; deleting the cookie alone is insufficient if the server session remains alive.
- When remember-me is enabled, invoke proper logout handlers/revoke persistent remember-me state, not just clearing `JSESSIONID`.
- If the web app also issues **OAuth access/refresh tokens**, logging out an MVC session does not automatically revoke tokens at the Authorization Server/Resource Server.
- Changing passwords or locking accounts may require invalidating active sessions and remember-me credentials per policy; never rotate one session's ID and assume every other session is safe.

A distinguishing example: user A logs out, while B holds an independent unexpired JWT access token. If an API only verifies JWTs, B can keep using the token until expiry or revocation enforcement. The failure here is **revocation design**, not a session fixation bug.

## 11. Matrix testing: which barrier must block?

| ID | Threat/test | Precondition | Action | Expected outcome |
| --- | --- | --- | --- | --- |
| F01 | Pre-login session fixation | Anonymous SID_A, login succeeds | Compare ID before/after | SID_B differs from SID_A |
| F02 | Reusing old ID | SID_A already rotated | Second browser sends SID_A to `/me` | Not authenticated |
| F03 | New session | SID_B after login | Real browser sends SID_B | Authenticated as right user |
| F04 | Post-login cookie theft | SID_B leaked in controlled test | Second browser sends SID_B | May still work without extra binding; proves **limit of fixation protection** |
| F05 | Logout invalidation | SID_B active | `POST /logout` with CSRF, then retry SID_B | Not authenticated |
| F06 | Switch user | Alice session, switch to Bob | Reuse pre-switch ID/attributes | No leaked Alice factors/roles; rotate/recheck on privilege change |
| F07 | Missing CSRF | Browser cookie session | State-changing POST without CSRF | Blocked by CSRF, no side effects |
| R01 | Valid access JWT | Token issued for API A | Send multiple valid GETs | Allows **repeated use** per Bearer token design |
| R02 | Stolen Bearer | API A token copied | Another actor replays token | May succeed if Bearer-only; prevent theft/add sender constraint/revoke |
| R03 | Wrong audience | Validly signed JWT, aud=API B | Send to API A | 401 `invalid_token` |
| R04 | Expired JWT | JWT past `exp` | Send to API A | 401 |
| R05 | Revoked JWT | `jti` in synced denylist | Replay JWT even before `exp` | 401 if Resource Server enforces denylist |
| R06 | Refresh replay | RT1 already rotated to RT2 | Resend RT1 | Detects reuse, revokes active family per policy |
| R07 | Concurrent refresh | Two simultaneous RT1 calls | Race two token exchanges | At most one RT1 succeeds |
| R08 | OTT replay | OTT T already consumed | POST T in another session | Fails |
| R09 | Concurrent OTT | Two POSTs with same T from two sessions | Race in DB | At most one consume succeeds |
| R10 | Authorization code replay | Code K already exchanged | POST K a second time | Token endpoint rejects |
| R11 | Code interception | Attacker has K, lacks PKCE verifier V | Exchange K for token | Rejected when S256 enforced |
| R12 | Wrong OIDC nonce | ID Token belongs to another login | Submit token | OIDC client rejects |
| R13 | WebAuthn replay | Assertion for an old challenge | Resubmit | Fails challenge verification |
| R14 | Business duplicate payment | Idempotency key already used | POST identical payment | No duplicate payment created per policy |

**How to read results:** Tests F04/R02 may show credentials still accepted—**not a recommendation to let attackers use them**. They are **negative demonstrations** proving a single layer's limits so additional requirements are added. Tests should never dump cookies/secrets and must use isolated test accounts. Never replay other users' credentials on real systems.

**Anti-replay tests require two actors/sessions.** Resending `GET /me` 200 inside the same authenticated session does not prove OTT replay; it just shows the session works. Place each credential in its proper lifecycle and check how many consumptions the backend actually permits.

## 12. Standalone Java 17: pre/post rotation model and one-time tokens

`SessionReplayLab.java` below runs on **pure JDK 17+** without Spring. It demonstrates:

- Before login, an anonymous session has ID A.
- Login swaps A for B; ID A can no longer access as Alice.
- If ID B leaks **after login**, a bearer session model still accepts B (the limit of anti-fixation).
- Single-use tickets/OTTs with TTL, owner binding, replay, and concurrent consumption.
- Bob's token cannot verify as Alice.

This is an **educational model**, not a servlet container or production authentication server. Real IDs are generated via CSPRNG, yet the demo does not build browser cookies, verify passwords, provide distributed storage, or implement JWTs.

```java
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public final class SessionReplayLab {

    record Session(String principal) {}
    record Ticket(String owner, Instant expiresAt) {}

    private static final SecureRandom RANDOM = new SecureRandom();
    private final ConcurrentHashMap<String, Session> sessions =
            new ConcurrentHashMap<>();
    private final ConcurrentHashMap<String, Ticket> tickets =
            new ConcurrentHashMap<>();

    static String randomSecret() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(bytes);
    }

    String createAnonymousSession() {
        String id = randomSecret();
        sessions.put(id, new Session(null));
        return id;
    }

    String loginAndRotate(String anonymousId, String principal) {
        // Simulates succeeded password/interactive authentication.
        Session old = sessions.remove(anonymousId);
        if (old == null || old.principal() != null) {
            return null;
        }
        String newId = randomSecret();
        sessions.put(newId, new Session(principal));
        return newId;
    }

    boolean canRead(String sessionId, String user) {
        Session s = sessions.get(sessionId);
        return s != null && Objects.equals(user, s.principal());
    }

    String issueTicket(String user, Instant expiry) {
        String code = randomSecret();
        tickets.put(code, new Ticket(user, expiry));
        return code;
    }

    boolean consumeTicket(String code, String expectedUser, Instant now) {
        Ticket t = tickets.get(code);
        if (t == null || !Objects.equals(t.owner(), expectedUser)) {
            return false;
        }
        if (!now.isBefore(t.expiresAt())) {
            tickets.remove(code, t);
            return false;
        }
        // remove(key, value) guarantees at most one success in a single JVM.
        return tickets.remove(code, t);
    }

    public static void main(String[] args) throws InterruptedException {
        SessionReplayLab lab = new SessionReplayLab();
        Instant now = Instant.parse("2026-11-06T00:00:00Z");

        String before = lab.createAnonymousSession();
        System.out.println("anonymousAsAlice=" +
                lab.canRead(before, "alice"));

        String after = lab.loginAndRotate(before, "alice");
        System.out.println("rotated=" + !before.equals(after));
        System.out.println("oldIdAsAlice=" +
                lab.canRead(before, "alice"));
        System.out.println("newIdAsAlice=" +
                lab.canRead(after, "alice"));

        // An attacker who knows the NEW ID can replay it without another layer.
        System.out.println("stolenNewIdStillWorks=" +
                lab.canRead(after, "alice"));

        String ticket = lab.issueTicket("alice", now.plusSeconds(60));
        System.out.println("ticketFirst=" +
                lab.consumeTicket(ticket, "alice", now));
        System.out.println("ticketReplay=" +
                lab.consumeTicket(ticket, "alice", now));

        String expired = lab.issueTicket("alice", now.plusSeconds(5));
        System.out.println("ticketExpired=" +
                lab.consumeTicket(expired, "alice", now.plusSeconds(6)));

        String bobCode = lab.issueTicket("bob", now.plusSeconds(60));
        System.out.println("otherPrincipal=" +
                lab.consumeTicket(bobCode, "alice", now));

        String shared = lab.issueTicket("alice", now.plusSeconds(60));
        CountDownLatch gate = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(2);
        AtomicInteger accepted = new AtomicInteger();

        Runnable attempt = () -> {
            try {
                gate.await();
                if (lab.consumeTicket(shared, "alice", now)) {
                    accepted.incrementAndGet();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                done.countDown();
            }
        };
        new Thread(attempt).start();
        new Thread(attempt).start();
        gate.countDown();
        done.await();
        System.out.println("concurrentTicketSuccess=" + accepted.get());
    }
}
```

Run inside the directory containing the file:

```bash
javac SessionReplayLab.java
java SessionReplayLab
```

**Deterministic** stdout:

```text
anonymousAsAlice=false
rotated=true
oldIdAsAlice=false
newIdAsAlice=true
stolenNewIdStillWorks=true
ticketFirst=true
ticketReplay=false
ticketExpired=false
otherPrincipal=false
concurrentTicketSuccess=1
```

Meaning: `rotated=true` and `oldIdAsAlice=false` illustrate session fixation protection. `stolenNewIdStillWorks=true` **is not a bug in the demo to "fix" by keeping the old ID**: it shows a valid bearer session ID can still be abused if stolen. `ticketReplay=false` and `concurrentTicketSuccess=1` demonstrate **atomic consume** for credentials designed for one-time use. They protect different targets.

**Lab limitations:** `SessionReplayLab` does not use `HttpServletRequest.changeSessionId()`, CSRF, HTTP cookies, session TTLs, or multi-node DBs. The map **delete/put** rotation pattern in the lab is purely explanatory; never copy it as a production `SessionAuthenticationStrategy`. Use Spring Security's built-in mechanisms.

## 13. Testing refresh token rotation with server state

Implementing OAuth refresh token rotation requires an **Authorization Server** capable of storing token families and states, not merely a Resource Server decoding JWTs. Transaction invariant:

```text
Initial:
  family=F, active=RT1, revoked=false

POST refresh RT1:
  atomic check RT1 is active and family F not revoked
  invalidate RT1, issue RT2, mark RT2 active
  response access_token + refresh_token RT2

POST refresh RT1 again:
  detect reuse of inactive RT1
  flag family F compromised, revoke active RT2 or apply
  documented incident policy; audit without raw token

POST refresh RT2 after family was revoked:
  reject
```

Minimum tests:

1. First use of RT1 succeeds and returns RT2; access token still carries valid issuer/audience/scopes.
2. Reusing RT1 fails and triggers compromise response/family revocation (per policy).
3. Two concurrent RT1 requests allow only one transaction to transition active from RT1 to RT2. Never run sequential tests and claim concurrency safety.
4. Delayed requests or retries can cause false positives; collision/grace policies must be evaluated separately without letting RT1 be reused infinitely.
5. When theft is suspected, revoking a family can force legitimate clients to re-login; provide UX messaging and auditing.
6. If tokens are sender-constrained, verify proof keys/certificates on both issuance and reuse paths; do not assume having a token in the DB suffices.

Never store plaintext refresh tokens in logs or instrumentation. Store appropriate hashes/token family IDs, expiries, client identities, and revocation reasons; atomicity must be guaranteed by DB transactions/locking or conditional updates **across all nodes**.

## 14. Attack-mitigation matrix: choosing the right defensive layer

| Control | **Pre-login** session fixation | **Post-login** stolen cookie | Copied access JWT | Refresh token replay | One-time token replay |
| --- | --- | --- | --- | --- | --- |
| Rotate `JSESSIONID` on login | **Directly blocks** pre-login ID elevation | Not directly | No | No | No |
| `HttpOnly` cookie | Reduces JS cookie reading | Reduces one theft vector | Only if JWT is in cookie and fitting | Depends on storage | Not directly |
| `Secure` cookie + HTTPS | Reduces network session hijack/injection | Reduces network theft | Reduces in-transit token leaks | Reduces in-transit token leaks | Reduces link/code sniffing |
| `SameSite` + CSRF protection | Does not replace rotation | Does not help if attacker already holds cookie | Depends on how client sends token | No | Can block CSRF on submission forms |
| Idle/absolute session timeout | Shortens attack window | **Limits exposure duration** | No | No | No |
| JWT signature + issuer + `aud` + `exp` | No | Not for session cookies | **Mandatory validity** yet cannot tell thief from owner | Does not replace rotation | No |
| Short-lived access JWT | No | No | Shrinks replay window | Not directly | No |
| `jti` denylist / introspection | No | No | Can revoke/check state if enforced | Can apply state | Depends on design |
| DPoP/mTLS sender constraint | No | Not unless specially designed | **Reduces replay by keyless actors** | Can reduce via binding | Not by default |
| Refresh token rotation + reuse detect | No | No | No directly | **Direct** | No |
| Atomic consume + token expiry | No | No (sessions need multi-use) | Not fitting for Bearer JWTs by default | Direct if rotating credentials are designed | **Direct** |
| PKCE S256 | No | No | Not for already-issued access tokens | No | Direct for code exchange (not magic links) |
| Business idempotency | No | No | No | No | Prevents duplicate side effects, does not prove identity |

**Severe mistake:** enabling one control and claiming "anti-replay for all token types." Every layer has its own **target, enforcement point, and preconditions**. Some reduce *theft likelihood*, some bound *abuse duration*, some *detect reuse*, and some *bind to the sender*. State exact objectives when assessing security posture.

## 15. Common Spring configuration and testing mistakes

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| SID stays unchanged after login | Fixation protection disabled, custom login skips strategy, test checks wrong object | Enable `changeSessionId`; snapshot ID before/after |
| Old SID still logs in as user | Server still accepts pre-login ID, buggy session store mapping, proxy/cookie scope | Inspect Servlet session mapping and security chain |
| Rotation test fails despite right config | Comparing `MockHttpSession` reference after its ID mutated | Save `oldId` string **before** login |
| Old SID still works after logout | Only deleted client cookie, did not invalidate session server-side | Configure logout handlers, server session invalidation, integration tests |
| `HttpOnly` cookie still abused by XSS | `HttpOnly` blocks reading, not same-origin requests | Fix XSS, CSP, CSRF, and authorization |
| Disabled CSRF because API uses JWT | Same app still has cookie-based form login, CSRF still applies | Split filter chains (API vs web), keep CSRF where needed |
| Validly signed JWT usable by another actor | Bearer token stolen, lacks sender-constraint/revocation | Reduce leaks, shorten TTL, use DPoP/mTLS if feasible, revoke |
| JWT has `jti` yet still replayable | `jti` state not checked | Use denylist/replay store when use case fits |
| Refresh RT1 usable multiple times | Not rotating/atomic or reuse detection disabled | Implement rotation + family compromise or sender constraint |
| `SameSite=Strict` breaks OIDC callback session | Cookie omitted in matching cross-site flow | Evaluate `Lax`/`None+Secure` and CSRF/OAuth state per flow |
| Signing key rotated yet old JWTs still work | Old public key remains in JWKS and JWT is unexpired | That is key-rotation overlap, not token revocation |
| Persistent remember-me still auto-logins after logout | Token repository/cookie not properly revoked | Check remember-me logout service and persistent tokens |
| Pre-auth session attributes persist | `changeSessionId`/`migrateSession` keeps attributes | Clear/stamp pending state and privileges per principal |
| Concurrent OTT requests both succeed | Store lacks atomic consume | DB transaction/conditional update, concurrency tests |
| Two pods accept/deny differently | Desynchronized token/session caches or revocation policies | Shared store, atomic updates, refresh/invalidation strategy |
| HTTP 302 treated as pass | Redirects to login/challenge, not authenticated 200 | Assert principal, state changes, side effects, final destination |
| JWT in logs or session ID in URL | Sensitive logging/URL rewriting | Masking, HTTPS, cookie-only session transport |
| Resubmitted CSRF token still passes | CSRF tokens are not necessarily single-use | Evaluate CSRF's true goal; never use it as an OTT |
| Browser A accesses using cookie B | Broken identity / account-binding boundary | Test two browser jars, principals, tenants, session ownership |

## 16. Implementation and negative-testing checklist

1. **Sessions:** session IDs issued by Servlet container/Spring, random; reject unissued IDs; disable URL rewriting; align `Secure`/`HttpOnly`/`SameSite`/`Domain`/`Path` cookies with flows.
2. **Authentication:** session fixation protection enabled on all interactive logins/privilege elevations; ID rotates at boundary and old ID never becomes authenticated.
3. **Attributes:** pre-auth state, pending MFA, session carts, and caches evaluated/migrated/cleared per current privilege; user switching carries over no old roles/factors.
4. **Logout/revocation:** invalidate HTTP sessions server-side, clear properly scoped cookies, handle remember-me and OAuth tokens **separately**.
5. **CSRF:** keep CSRF on cookie-based state-changing browser endpoints; test with real forms/MockMvc CSRF.
6. **Bearer JWTs:** validate signature, issuer, audience, expiry, and scopes; accept that valid Bearer tokens are multi-use; minimize leaks, shorten TTLs, add sender constraints or revocation as needed.
7. **Refresh tokens:** public clients use sender-constrained refresh tokens or rotation per RFC 9700; test reuse detection, family revocation, atomicity, and concurrency.
8. **One-time credentials:** OTP/OTT/codes/challenges consumed strictly once per protocol, expiry, owner/transaction binding, and atomic consumption.
9. **Business logic:** payments/transfers have separate authorization and idempotency; MFA/CSRF/anti-replay do not replace permissions.
10. **Observability:** audit session-ID-changed, logout/invalidation, invalid token/reuse/refresh-family-revocation events; log appropriate hashes/correlation IDs, **never log secrets**.
11. **Negative tests:** old → new, replay from another browser, replay after logout, wrong callback state, wrong JWT audience, refresh reuse, concurrent consume, and key theft.
12. **Scope clarity:** in test reports, state precisely "which layer blocks what" rather than generically claiming "anti-replay enabled".

**Summary:** `changeSessionId()` prevents a session ID known **before login** from becoming an authenticated privileged session ID after login. It does not protect a new session cookie stolen afterward. Valid Bearer access JWTs are multi-use, so minimize exposure and add sender constraints/revocation when needed; refresh token rotation and one-time consumption detect **reuse of credentials designed for single use**. CSRF, PKCE, OAuth state/nonce, TTLs, HTTPS, and authorization are all valuable, yet **never interchangeable**.

### Primary references

- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — Remember-Me Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/rememberme.html)
- [Spring Security — Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html)
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — MockMvc Authentication](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 8705 — OAuth 2.0 Mutual TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)

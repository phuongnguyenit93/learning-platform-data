# Cookie Lifetime, Signing Keys, and Storage Protection Policies — Remember-me in Spring Security Servlet

In a web application with **“Remember me”** functionality, a browser can return after an HTTP session expires and still be recognized without re-entering a password. That convenience creates **a credential that outlives a normal login session**. If the cookie is stolen, the signing key leaks, or the token database is accessed without authorization, a remember-me session can become a way back into a user's account.

Therefore, when designing remember-me with **Spring Security Servlet**, three questions must be decided together:

1. **Lifetime:** how long are cookies and tokens accepted? Is that lifetime absolute or extended on use? What happens when the browser closes, the session expires, the user changes password, or the account is locked?
2. **Signing keys and secrets:** which mechanism uses signing keys/HMAC or random values to prevent forgery? Where are keys stored, how are they shared across nodes, how are they rotated, and can issued cookies be invalidated?
3. **Storage and revocation:** how are tokens/keys stored in the browser, server, or DB? Who is allowed to read them? How effective are logout, “log out of all devices”, and incident response?

This lesson clarifies the two remember-me models Spring Security commonly provides: **token-based remember-me** using a signed cookie verified with a server-side key and user data; and **persistent-token remember-me** using a random series/token pair and a server-side repository. Examples use Spring Security 6.x, Java 17+, Spring Boot 3.3.5, and Servlet-based form login. The Java/Gradle code in the hands-on section is designed for local learning environments and does not replace production session and secret management systems.

## 1. Identifying Remember-me Accurately

An account can be accessed through several mechanisms:

| Mechanism | Primary credential | Typical lifecycle | Meaning |
| --- | --- | --- | --- |
| Standard form login | Username/password on login request | Server authenticates and may create an HTTP session | User actively authenticates in full |
| HTTP session after login | Session cookie, usually `JSESSIONID` | Governed by session policy, timeout, invalidation | Reuses an established SecurityContext |
| Remember-me | Separate cookie, usually named `remember-me` | Usually longer than a session; e.g., days/weeks | Restores Authentication when a full session is absent |
| OAuth2 access token | Bearer token or sender-constrained token | Governed by issuer/authorization policy | Used for API access; not automatically synonymous with remember-me |
| Refresh token | Token to reissue access tokens per issuer policy | Governed by OAuth2 lifecycle | Not a form-login remember-me cookie |

**A remember-me cookie is not a session cookie.** You can delete or expire an HTTP session while the remember-me cookie persists, causing Spring Security to auto-authenticate when a subsequent request passes through the security filter chain.

Nor should remember-me be treated as having the same assurance as a fresh password login. Spring Security can distinguish **remember-me authentication** from **fully authenticated** in authorization rules, letting you require users to re-authenticate before sensitive actions.

### 1.1. Core Security Boundaries

- Anyone holding a valid remember-me cookie can use it to attempt account recovery if no other anti-replay binding exists.
- The `HttpOnly` attribute reduces JavaScript's ability to read the cookie directly, yet does not stop same-origin XSS from issuing requests on the user's behalf.
- `Secure` requires the cookie to be sent only over HTTPS; it does not prevent browser malware or secrets leaking in backups.
- `SameSite` can restrict certain CSRF vectors, without replacing CSRF protection for state-changing requests.
- Token-based remember-me has no per-device list of valid tokens on the server; persistent-token stores server-side data supporting finer management and revocation, at the cost of increased DB protection duties.

## 2. Remember-me Flow in the Servlet Filter Chain

When a user actively logs in via a form and selects the “Remember me” checkbox, Spring Security can issue an extra remember-me cookie alongside the current session. Later, when no authentication exists from a session, remember-me can read the cookie and construct a new `Authentication` if verification passes.

~~~text
First time the user logs in:
Browser -> GET /login -> HTML form with CSRF token
Browser -> POST /login
  username + password + _csrf + remember-me=on
      |
      v
CsrfFilter -> UsernamePasswordAuthenticationFilter
      |
AuthenticationManager verifies password successfully
      |
RememberMeServices.loginSuccess(...)
      |
Create remember-me cookie and/or persistent token record
      |
Send Set-Cookie to browser

Later, when the session is gone:
Browser -> GET /account
  Cookie: remember-me=<issued value>
      |
      v
SecurityContext has no fully authenticated principal
      |
RememberMeAuthenticationFilter
      |
RememberMeServices.autoLogin(...)
      |
Verify cookie/signature or repository series+token
      |
RememberMeAuthenticationToken -> SecurityContext
      |
Authorization rule:
  authenticated()       -> usually allowed
  fullyAuthenticated()  -> requires full authentication
~~~

This is a conceptual diagram, not a fixed class chain across every version. `RememberMeServices` also integrates with logout and can clear cookies on authentication failure. If the cookie is expired, invalid, or the user is rejected, the browser must log in again per the app flow.

**Checkbox choice must actually mean something**: do not enable `alwaysRemember(true)` on sensitive apps just to avoid users forgetting to tick the box. If a product requires remember-me by default, that must be a deliberate decision with a threat model, consent policy, and clear disable/revoke controls.

## 3. Cookie Lifetime: Three Distinct Clocks

Saying “the cookie lives 14 days” is incomplete. At minimum, distinguish:

1. **Browser cookie Max-Age/Expires:** how long the browser is instructed to retain the cookie. This is a client-side mechanism and cannot be the server's sole source of truth.
2. **Server-verified validity window:** does the server still accept the credential at request time, even if the browser sends an old cookie?
3. **Session and access policy:** is re-login required after an absolute duration, after a password change, when a device is marked untrusted, or before sensitive transactions?

When a browser cookie expires, normal browsers stop sending it. However, an attacker who copied the cookie value can craft an HTTP request carrying it. **The server must still verify expiration** instead of trusting that browsers will never send expired values.

### 3.1. What Is tokenValiditySeconds?

In Spring Security remember-me configuration, `tokenValiditySeconds(int)` sets the lifetime in **seconds**, for example:

~~~java
.rememberMe(remember -> remember
    .tokenValiditySeconds(7 * 24 * 60 * 60))
~~~

The example sets 604,800 seconds, equal to **7 days**, and is a configuration fragment inside `HttpSecurity`. Seven days is an educational example; there is no “7 days is always safe” or “14 days is always standard” for every system.

The ideal lifetime depends on:

- Data sensitivity: banking, healthcare, admin panels, password changes, funds transfers.
- Whether the device is personal or shared.
- Whether MFA/step-up authentication is in place.
- Cookie theft risk, monitoring capability, and revocation support.
- User UX expectations and support costs.
- Whether a separate absolute lifetime or idle timeout applies per policy.

### 3.2. Absolute Lifetime vs. Sliding Extension

Two easily confused concepts:

| Type | Example | Meaning |
| --- | --- | --- |
| Absolute lifetime | Credential issued on day 1 expires on day 8 even with frequent use | Caps maximum exposure window |
| Sliding/idle lifetime | Each valid use can extend validity per policy | Better UX, yet the credential can stay alive a long time |
| Session inactivity timeout | Session ends after 30 minutes of inactivity | Does not mean remember-me expired |
| Browser session cookie | Cookie without long-lived Max-Age | Insufficient to define server-side validity |

Token-based remember-me normally embeds an expiration timestamp inside the signed payload; the server checks that timestamp and does not automatically reissue the cookie on every request in a way that slides the absolute deadline forward forever.

Persistent-token remember-me maintains state in a repository with `last_used`, token rotation on auto-login, and service-enforced validity. How “extension” behaves in practice must therefore be verified against the implementation, cookie policy, and server data. **Do not assume setting Max-Age to 7 days automatically creates a 7-day absolute cap across devices if the server rotates/extends tokens.** If the product requires an absolute maximum lifetime, design and store reliable `created_at / expires_at` timestamps separately or use an appropriate mechanism.

### 3.3. Designing Lifetimes by Action

An illustrative policy:

- Routine dashboard reads: remember-me may be acceptable for 7 days on personal devices, depending on the threat model.
- Changing passwords, adding payment methods, exporting confidential data, changing admin roles: **require fully authenticated**, re-authentication, or step-up MFA.
- Locked/suspected compromised account: stop accepting remember-me per server state.
- User selects “do not remember”: do not issue a remember-me cookie.
- User selects “log out of all devices”: invalidate remembered credentials per design; stateless token-based mode does not provide this per device without added state.

Do not rely on `authentication.isAuthenticated()` alone to decide “recently entered password”. Remember-me authentication also sets the authenticated flag, whereas the framework distinguishes them via `fullyAuthenticated()` and trust resolvers.

## 4. Token-Based Remember-me: How Is the Cookie Signed?

Spring Security provides `TokenBasedRememberMeServices`. It issues a cookie containing information the server can **verify using a signing key**, without requiring a per-device token table for every cookie.

A token-based remember-me structure (after base64 decoding) typically represents fields such as:

~~~text
username : expiryTime : algorithmName : signature
~~~

The signature is computed from user info, expiration, password hash, and the **application key** according to Spring Security's specific mechanism. Do not copy a formula or “re-implement Spring Security signing” in another app: formats, algorithms, and migration details can depend on the version.

### 4.1. Signatures Protect Integrity, Not Confidentiality

In a token-based design:

- **Signature/MAC** lets the server detect tampering with username/expiry without knowing the key.
- **Base64 is not encryption**; data like username or expiration time is readable.
- A **stolen** bearer cookie can still be replayed before expiration; the attacker does not need to forge the signature.
- An exposed secret key can enable token forgery depending on the algorithm/key mechanics and related data, impacting many accounts.
- Changing a password hash can invalidate old token-based remember-me cookies because the hash contributes to the signature.

Never store passwords or signing keys in cookies. Never log intact tokens. When correlation is needed, log an approved non-secret identifier rather than arbitrarily hashing the entire cookie into logs where it becomes a tracking identifier.

### 4.2. Signing Keys Must Be Stable and Strong

In the Spring Security DSL, `.key(...)` configures a secret used by token-based remember-me services and the corresponding remember-me authentication component.

**Operational requirements:**

1. Generate keys from a cryptographic random source; never use `"mySecret"` or guessable strings.
2. Store keys in a secret manager/KMS or protected environment, **never commit them to repositories**.
3. Separate keys across dev/staging/prod environments, applications, and trust domains.
4. All nodes serving the corresponding remember-me cookie must share a consistent key during operation; if node A and node B differ, a browser may log in on A and get rejected on B.
5. Enforce least-privilege access, auditing, and an emergency rotation procedure.
6. Prevent logging, health endpoints, startup exceptions, or debug configs from printing the secret.
7. Track blast radius if a key leaks: you may need to rotate keys, force re-authentication, and investigate potential token forgery.

**Signing keys differ from password encoders.** Spring Security may use BCrypt/Argon2 for storing passwords, while token-based remember-me uses an application key to prevent cookie tampering. Changing `PasswordEncoder` can also affect token-based signatures if stored password hashes change; do not treat that as a substitute for a proper revocation system.

### 4.3. Does Key Rotation Invalidate Old Remember-me Cookies?

In a simple token-based model accepting only one active key, **changing the key normally makes cookies signed with the old key unverifiable**. This can act as a “bulk remember-me logout” during a key-leak incident, though it impacts UX for all users.

If an overlap period accepting both old and new keys is desired, design a **version/key-id** and a compatibility verifier with a short expiry, auditing, and a removal deadline for the old key. The basic Spring Security DSL does not build a multi-key ring/rollover system for you automatically.

Do not rotate keys daily and unexpectedly break a “remember for 7 days” expectation without notice and multi-node testing. Conversely, when a key leak is suspected, **do not keep accepting the old key too long merely to preserve UX**.

### 4.4. Per-Device Revocation Is Harder Than With Persistent Tokens

A token-based cookie verified by signature/expiry can be accepted without the server tracking a list of “which devices A, B, C hold which tokens”. Therefore:

- Current logout clears the cookie **in the browser sending the logout**, yet a copy held earlier by an attacker may remain accepted until expiry unless another revocation condition applies.
- Changing the password can invalidate tokens tied to the old password hash, though you must test how the app stores `UserDetails` and resets passwords.
- Locking an account can reject auto-login if `UserDetailsService` and account-status checks are enforced properly.
- Per-device revocation or “log out all sessions” may require server-side state/denylists/credential versions or switching to a persistent-token model.

**Never advertise “logout revoked all tokens” solely because the HTTP response returned Set-Cookie clearing the remember-me cookie on one browser.**

## 5. Persistent-Token Remember-me: Series + Token in the Database

Spring Security includes `PersistentTokenBasedRememberMeServices` and `PersistentTokenRepository`. When a user opts into remember-me, the server issues a random pair:

- **series**: token-chain identifier, used to locate the record for the remembered device/session.
- **token**: current secret that must match the record in the repository.
- **username/last_used** and other metadata managed per implementation/DB policy.

The cookie usually carries the series/token pair in an encoded representation (e.g., base64), **not encrypted storage**. When a valid request arrives, the server looks up the series, checks the token, and normally **rotates the token** in the record, issuing a new cookie to reduce reuse of previously spent tokens.

~~~text
Browser:
  Cookie: remember-me = encode(series_A, token_1)
                |
                v
PersistentTokenBasedRememberMeServices
                |
                v
PersistentTokenRepository:
  lookup series_A -> username, current token_1, last_used
                |
      +---------+----------+
      |                    |
token mismatch           token match
      |                    |
reject + handle         load user, expiry/status checks
suspected reuse            |
                           v
                     rotate token_1 -> token_2
                     UPDATE repository
                           |
                           v
                     Authentication
                     Set-Cookie(new token_2)
~~~

This is a conceptual model, not a contract that every failure yields the same HTTP status or response. The implementation treats a token mismatch as a possible cookie-theft signal and can delete the user's tokens; concurrent requests/multiple tabs must be tested to avoid false positives from token-rotation races.

### 5.1. Why Are Persistent Tokens Advantageous for Revocation?

Because the server keeps records, you can:

- Delete an account's remember-me tokens after a password change or suspected incident.
- Delete a specific series/device token if the repository and device-management service are extended appropriately.
- Enforce account-lock, expiration, idle-lifetime, and per-device/session audit policies.
- Analyze anomalous token reuse to raise security alerts.
- Apply targeted revocation without rotating a global signing key for all users.

**However:** the default SQL schema does not store full device details, absolute expiration, or custom policy fields. To provide a “view all remembered devices” UI with active/revoked states and reliable audits, extend the schema and service intentionally.

### 5.2. PersistentTokenRepository Does Not Automatically Make Tokens Safe in the DB

A common SQL schema Spring Security uses for its JDBC repository:

~~~sql
CREATE TABLE persistent_logins (
    username VARCHAR(64) NOT NULL,
    series VARCHAR(64) PRIMARY KEY,
    token VARCHAR(64) NOT NULL,
    last_used TIMESTAMP NOT NULL
);
~~~

`JdbcTokenRepositoryImpl` uses similar fields for series/token by default. **The token value stored in the table is a sensitive credential by design**; in the default implementation, do not assume tokens are one-way hashed. If the DB, SQL logs, dumps, or backups are read without authorization, replay and remember-me session hijacking risks must be assessed.

To protect stored data:

- Encrypt database disks/volumes/backups **at rest**, and encrypt connections in transit to the DB.
- Restrict `SELECT`, especially on the token table, using a least-privilege service account; do not use admin DB credentials in the app.
- Never return `series/token` in admin API responses, exports, or support tooling.
- Never print table rows in access logs, query logs, traces, exception output, or backup samples.
- Secure backups and retention/restore workflows, limiting how long expired/revoked data is kept.
- If your threat model forbids **plaintext tokens in the DB**, design a custom repository/service supporting hash/HMAC verification **and rotation**, and test it with the framework; do not merely replace the `token` column with a hash while keeping default `JdbcTokenRepositoryImpl`, as the service's comparison logic will no longer match.
- Consider external encryption keys in KMS/secret manager if storing encrypted tokens; manage recovery/rotation and backup keys.

### 5.3. Token Mismatch and Concurrent Requests

Persistent-token rotation carries an important trade-off:

1. Request 1 and request 2 arrive almost simultaneously carrying `token_1`.
2. Request 1 runs first: `token_1` is valid → DB updates to `token_2`.
3. Request 2 arrives afterward with `token_1`: the repository now stores `token_2` → mismatch.
4. The framework may treat the mismatch as cookie theft/replay and wipe the user's tokens to protect the account.

Therefore, do not build logic to **ignore token mismatches** just so tabs do not get logged out; doing so weakens replay detection. Instead, test request concurrency, retry/UX strategies, and evaluate implementations/policies against real requirements. In high-sensitivity apps, accept occasional safe re-logins rather than failing open.

### 5.4. The Key Parameter in Persistent Services Can Be Misleading

In some constructors/configurations, persistent remember-me also takes a `key` to create/verify `RememberMeAuthenticationToken` alongside the remember-me authentication provider. Yet **the random series/token pair and repository are the primary mechanism verifying persistent cookies**; do not assume every persistent cookie is MAC-signed with the key the way token-based mode works.

Consequence: rotating the signing key **does not automatically replace deleting persistent token records**. To guarantee revocation of persistent remembered clients, act on the repository/session lifecycle. Never treat key rotation as a promise that “all cookies on a lost device were invalidated” if the DB still accepts old series/tokens.

## 6. Comparing Token-Based and Persistent-Token

| Criterion | Token-based (stateless signature) | Persistent-token (stateful series/token) |
| --- | --- | --- |
| What does the cookie carry? | Self-verifiable auth info + expiry + signature | Random series and secret token |
| Per-cookie DB record? | Not required | Yes |
| Verification basis | Key + user data + expiry/signature | Repository record + token match + user status |
| Lifetime | Usually signed expiry in cookie | Token validity + last-used/rotation per service |
| Revoke a single device | Difficult without adding state | Feasible when extending repository/device records |
| Log out all devices | Requires broad invalidation or added state | Can delete all persistent tokens for the user |
| Impact of leaked signing key | Very severe for token-based forgery | Key still needs protection; token records/repository are the main boundary |
| DB token leak | No separate token table by default | Must be treated as a sensitive credential leak |
| Concurrent requests | Usually no DB rotation per request | Can hit token-rotation races |
| Multi-node | Must share consistent key/password user store | Must share consistent DB/repository and config |
| Operational footprint | Simpler storage, harder individual revocation | Requires DB/cleanup/caching, offering better lifecycle control |
| Best suited for | Small web apps, acceptable risk, short TTL, no per-device revoke needed | Apps needing remembered session management and per-device/account revocation |

**Do not pick token-based merely to “avoid a DB” if the product requires logging out all devices, immediate revocation, or per-device audits.** Conversely, do not pick persistent-token and forget to secure the DB, because you have just created a new store of bearer credentials.

## 7. Cookie Policy: Secure, HttpOnly, SameSite, Path, Domain

A remember-me cookie is a credential. Cookie attributes reduce attack surface, yet **no single flag makes a cookie unstealable**.

| Attribute | Meaning | Implementation note |
| --- | --- | --- |
| `Secure` | Browser sends cookie only over HTTPS | Mandatory in HTTPS production; verify reverse proxy/TLS termination |
| `HttpOnly` | Normal JavaScript cannot read cookie directly | XSS can still issue same-origin requests; does not replace XSS defense |
| `SameSite=Lax/Strict/None` | Restricts certain cross-site cookie sending | Choose per login/SSO/navigation flows; `None` usually requires `Secure` |
| `Path` | Restricts URL paths receiving the cookie | Limit unnecessary scope; not an independent application security boundary |
| `Domain` | Defines cookie host/subdomain scope | Avoid sharing across all subdomains without a reason |
| `Max-Age/Expires` | Browser retains cookie until instructed time | Server must still reject expired/revoked tokens |
| Cookie name | Distinguishes remember-me from session/other cookies | Coordinate logout cleanup, proxies, and apps sharing a domain |

### 7.1. HTTPS Behind a Reverse Proxy

A common pitfall: TLS terminates at a load balancer, the Spring app receives internal HTTP requests, and fails to recognize the original HTTPS scheme. If the framework relies on request secure status to set the `Secure` cookie flag, cookies may be misconfigured.

Control trusted forwarded headers/proxy configuration per Spring Boot infrastructure policy and inspect the **actual `Set-Cookie` header** in the browser over HTTPS. Never blindly trust forwarded headers sent by public clients; the gateway must strip/overwrite headers before forwarding internally.

### 7.2. Session Cookie Settings Do Not Necessarily Apply to Remember-me Cookies

Properties like:

~~~properties
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
~~~

typically control the **session cookie** managed by the servlet container. **Do not assume they fully configure the `remember-me` cookie** issued by `RememberMeServices`. Inspect the cookie API/settings of your Spring Security version and verify the actual `Set-Cookie` response header.

When using custom `RememberMeServices`, explicitly control flags, maxAge, path, domain, and SameSite per policy; avoid emitting a second `Set-Cookie` header with the same name and conflicting attributes that causes shadowing.

### 7.3. SameSite and CSRF

Remember-me cookies can be sent automatically by browsers just like session cookies, so a cookie-backed form-login app must still evaluate CSRF. `SameSite` helps restrict some cross-site interactions yet does not replace CSRF tokens for state-changing endpoints.

In particular, remember-me can restore Authentication from a cookie on a request where the user has not re-entered a password. If a POST API accepts cookie auth without proper CSRF protection, attackers can attempt to trigger unintended actions in the browser's context.

## 8. Spring Boot 3.3.5 Example: Token-Based Remember-me for Form Login

The hands-on example builds a web app featuring:

- `GET /login`: HTML/Thymeleaf page with a `remember-me` checkbox.
- `POST /login`: Spring Security handles password, CSRF, and remember-me choice.
- `GET /account`: allows fully authenticated **or** remember-me authenticated users to view normal info.
- `GET /sensitive`: requires `fullyAuthenticated()`, not remember-me alone.
- `POST /logout`: CSRF-compliant logout clearing the browser cookie.
- An in-memory user `learner/demo-pass` for local testing only.

**Important prerequisite:** the in-memory demo user generates a fresh BCrypt hash on every application restart, so the hash changes and old token-based cookies may stop validating after a restart. That is a property of demo data, **not a bug to fix by disabling key signing**. Production must use a persistent user store with stable password hashes paired with a stable signing key across instances.

### 8.1. Project Structure

~~~text
remember-me-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/remember/
    │   │   ├── RememberMeApplication.java
    │   │   ├── SecurityConfiguration.java
    │   │   └── PageController.java
    │   └── resources/
    │       ├── application.properties
    │       └── templates/login.html
    └── test/java/example/remember/
        └── RememberMeTests.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'remember-me-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
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
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/main/resources/application.properties`:

~~~properties
# The application fails to start if APP_REMEMBER_ME_KEY is missing.
# The secret must be supplied by the environment, never committed to Git.
app.remember-me.key=${APP_REMEMBER_ME_KEY}
~~~

To run locally, set a sufficiently long, random signing key in the environment. For example on Linux/macOS with OpenSSL:

~~~bash
export APP_REMEMBER_ME_KEY="$(openssl rand -hex 32)"
gradle test
gradle bootRun
~~~

In PowerShell on Windows, you can generate 32 bytes from .NET's CSPRNG:

~~~powershell
$bytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes)
$rng.Dispose()
$env:APP_REMEMBER_ME_KEY = [System.BitConverter]::ToString($bytes).Replace("-", "")
gradle test
gradle bootRun
~~~

The examples above generate a key in the **current run's** environment; never write keys into the source repo. In real deployments, use a secret manager and rotate under access-controlled procedures. The test suite below also configures a dedicated test-only key.

### 8.2. Main Class

`src/main/java/example/remember/RememberMeApplication.java`:

~~~java
package example.remember;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RememberMeApplication {
    public static void main(String[] args) {
        SpringApplication.run(RememberMeApplication.class, args);
    }
}
~~~

### 8.3. SecurityConfiguration

`src/main/java/example/remember/SecurityConfiguration.java`:

~~~java
package example.remember;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    private static final int REMEMBER_FOR_SECONDS = 7 * 24 * 60 * 60;

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            UserDetailsService users,
            @Value("${app.remember-me.key}") String signingKey)
            throws Exception {

        if (signingKey.length() < 32) {
            throw new IllegalStateException(
                "Remember-me signing key is too short");
        }

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login").permitAll()
                .requestMatchers("/sensitive").fullyAuthenticated()
                .requestMatchers("/account").authenticated()
                .anyRequest().denyAll())

            .formLogin(form -> form
                .loginPage("/login")
                .defaultSuccessUrl("/account", true)
                .permitAll())

            .rememberMe(remember -> remember
                .rememberMeParameter("remember-me")
                .userDetailsService(users)
                .key(signingKey)
                .tokenValiditySeconds(REMEMBER_FOR_SECONDS))

            .logout(logout -> logout
                .logoutSuccessUrl("/login?logout"))

            // Do not disable CSRF: POST /login and POST /logout require a token.
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(learner);
    }
}
~~~

**Explanation of configuration policy:**

- `tokenValiditySeconds(REMEMBER_FOR_SECONDS)` sets the remembered duration to 7 days in the demo. The browser cookie is not the sole authority; the remember-me service also verifies the token.
- `.key(signingKey)` injects the key from the environment; do not generate a random new key on each startup if you want cookies to survive restarts/multi-node routing.
- `userDetailsService(users)` lets remember-me look up the user and verify required status/details.
- The `remember-me` checkbox must submit the matching parameter. Do not use `alwaysRemember(true)`, avoiding issuing remember-me cookies when users did not opt in.
- `/account` requires only `authenticated()`, so it can accept a `RememberMeAuthenticationToken`.
- `/sensitive` requires `fullyAuthenticated()`, so remember-me-only is insufficient; full authentication is required per policy.
- `csrf().disable()` is not called, so form login/logout remain protected.

**Note when running the demo on HTTP localhost:** production must run over HTTPS and ensure the remember-me cookie sets Secure/HttpOnly/SameSite per policy. Never let a localhost example become an excuse to issue non-Secure cookies on the internet. You may need `useSecureCookie`/cookie settings on `RememberMeServices` and proper reverse proxy forwarded headers depending on version.

### 8.4. MVC Controller

`src/main/java/example/remember/PageController.java`:

~~~java
package example.remember;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
public class PageController {

    @GetMapping("/login")
    public String login() {
        return "login";
    }

    @GetMapping("/account")
    @ResponseBody
    public String account(Authentication authentication) {
        return authentication.getName()
            + ":" + authentication.getClass().getSimpleName();
    }

    @GetMapping("/sensitive")
    @ResponseBody
    public String sensitive() {
        return "fully-authenticated-only";
    }
}
~~~

In `/account`, printing the `Authentication` class is for **learning**, not a production API response exposing internal security implementation details. Showing the class name highlights the difference between full login and remembered login; real apps should return only the minimum authorized data.

### 8.5. Thymeleaf login.html

`src/main/resources/templates/login.html`:

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Sign In</title>
</head>
<body>
    <h1>Sign In</h1>

    <p th:if="${param.error}">Login failed.</p>
    <p th:if="${param.logout}">Logged out.</p>

    <form th:action="@{/login}" method="post">
        <label>
            Username:
            <input type="text" name="username" required>
        </label>
        <label>
            Password:
            <input type="password" name="password" required>
        </label>
        <label>
            <input type="checkbox" name="remember-me" value="on">
            Remember me on this device
        </label>
        <button type="submit">Sign in</button>
    </form>
</body>
</html>
~~~

Thymeleaf + Spring MVC integration normally injects a hidden CSRF field for forms using `th:action`. Inspect the **actually rendered HTML** in the browser; do not look only at the template source. A POST missing a CSRF token can return 403 even when the password is correct. The checkbox is opt-in: if left unchecked, the request omits `remember-me=on`.

Logout in the demo uses Spring Security's `POST /logout` (rather than a custom GET endpoint). If you need a logout button on the account page, add a `POST /logout` form with a properly rendered CSRF token; do not switch logout to GET just to avoid 403 errors.

## 9. MockMvc: Proving “Remembered” Differs From “Active Session”

`src/test/java/example/remember/RememberMeTests.java`:

~~~java
package example.remember;

import jakarta.servlet.http.Cookie;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties =
    "app.remember-me.key=test-only-long-remember-me-key-not-for-prod-2026")
@AutoConfigureMockMvc
class RememberMeTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void loginWithoutCheckboxDoesNotIssueRememberMeCookie()
            throws Exception {
        MvcResult result = mockMvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "demo-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/account"))
            .andReturn();

        assertNull(result.getResponse().getCookie("remember-me"));
    }

    @Test
    void checkboxIssuesCookieWithConfiguredMaxAge() throws Exception {
        MvcResult result = rememberedLogin();

        Cookie cookie = result.getResponse().getCookie("remember-me");
        assertNotNull(cookie);
        assertEquals(7 * 24 * 60 * 60, cookie.getMaxAge());
    }

    @Test
    void rememberMeCookieAloneRestoresIdentityWithoutSession()
            throws Exception {
        MvcResult login = rememberedLogin();
        Cookie rememberCookie =
            login.getResponse().getCookie("remember-me");
        assertNotNull(rememberCookie);

        // Send ONLY the remember-me cookie, do NOT send MockHttpSession.
        mockMvc.perform(get("/account").cookie(rememberCookie))
            .andExpect(status().isOk())
            .andExpect(content().string(
                "learner:RememberMeAuthenticationToken"));
    }

    @Test
    void sensitiveEndpointRejectsRememberedIdentity()
            throws Exception {
        MvcResult login = rememberedLogin();
        Cookie rememberCookie =
            login.getResponse().getCookie("remember-me");
        assertNotNull(rememberCookie);

        mockMvc.perform(get("/sensitive").cookie(rememberCookie))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void missingCookieCannotAccessAccount() throws Exception {
        mockMvc.perform(get("/account"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void forgedCookieDoesNotAuthenticate() throws Exception {
        Cookie forged = new Cookie("remember-me", "not-a-valid-token");

        mockMvc.perform(get("/account").cookie(forged))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void badPasswordDoesNotIssueRememberMeCookie()
            throws Exception {
        MvcResult result = mockMvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "bad-pass")
                .param("remember-me", "on"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"))
            .andReturn();

        assertNull(result.getResponse().getCookie("remember-me"));
    }

    @Test
    void loginWithoutCsrfIsDenied() throws Exception {
        mockMvc.perform(post("/login")
                .param("username", "learner")
                .param("password", "demo-pass")
                .param("remember-me", "on"))
            .andExpect(status().isForbidden());
    }

    private MvcResult rememberedLogin() throws Exception {
        return mockMvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "demo-pass")
                .param("remember-me", "on"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/account"))
            .andReturn();
    }
}
~~~

**What the tests prove:**

- Unchecked checkbox → no remember-me cookie is issued on successful login.
- Checked checkbox → response includes cookie with expected Max-Age of 604,800 seconds.
- Sending only the remember-me cookie, **without carrying the session from login**, still restores identity when the token is valid.
- `fullyAuthenticated()` does not treat remembered-only authentication as sufficient for sensitive endpoints.
- Wrong/forged cookies and wrong passwords grant no access.
- CSRF remains enforced on `POST /login`.

**What the tests do not yet prove:** multi-node key rotation, cookie theft/replay in a real browser, long-wall-clock expiration, how `Secure`/`SameSite` are applied behind a reverse proxy, persistent-token database behavior, or KMS-managed signing keys. Those aspects require dedicated deployment testing.

### 9.1. Running the Demo

On Linux/macOS, after exporting the key environment variable:

~~~bash
gradle test
gradle bootRun
~~~

If a wrapper is present, use `./gradlew test` / `./gradlew bootRun`. On Windows use `gradlew.bat test` / `gradlew.bat bootRun`. The sample code depends on Spring Boot JARs and cannot be compiled/run simply with `javac`/`java` without a classpath.

Open `http://localhost:8080/login` in a browser, enter `learner / demo-pass`, tick the checkbox, and sign in. Open DevTools → Application/Cookies to inspect the `remember-me` cookie. In a learning environment you can delete only `JSESSIONID` and visit `/account` to observe remember-me restoring identity.

Never send real tokens/cookies in screenshots or chat. In HTTPS production, inspect `Set-Cookie` to confirm flags meet policy—especially `Secure`, `HttpOnly`, `SameSite`, domain/path, and max-age.

## 10. Integrating Persistent Tokens When a Database Is Available

If the product needs to revoke remembered devices, you can use `PersistentTokenRepository` and `JdbcTokenRepositoryImpl`. This is a **configuration variant**, not something to paste blindly into the token-based demo in Section 8. It requires a datasource, schema migrations, and DB access controls.

### 10.1. Repository Bean

~~~java
@Bean
PersistentTokenRepository persistentTokenRepository(
        DataSource dataSource) {

    JdbcTokenRepositoryImpl repository =
        new JdbcTokenRepositoryImpl();
    repository.setDataSource(dataSource);
    return repository;
}
~~~

This snippet requires importing `javax.sql.DataSource`, `PersistentTokenRepository`, `JdbcTokenRepositoryImpl`, and `@Bean`. Never enable automatic table creation on production startup if the database is managed by Flyway/Liquibase or DBAs.

### 10.2. Updating the Remember-me DSL

~~~java
.rememberMe(remember -> remember
    .rememberMeParameter("remember-me")
    .userDetailsService(users)
    .tokenRepository(persistentTokenRepository)
    .key(signingKey)
    .tokenValiditySeconds(14 * 24 * 60 * 60))
~~~

This configuration fragment belongs inside a `SecurityFilterChain` with a `PersistentTokenRepository` bean and a suitable user source. When `tokenRepository(...)` is provided, Spring Security uses persistent-token services rather than token-based services, though you should verify the active filters/services in your deployed version.

**Important:** the `key` parameter does not turn the series/token cookie into a stateless MAC like token-based mode. To revoke specific tokens, manage the repository; **changing `key` alone is not an API to revoke all series**.

### 10.3. Database Migration

A minimal schema:

~~~sql
CREATE TABLE persistent_logins (
    username VARCHAR(64) NOT NULL,
    series VARCHAR(64) PRIMARY KEY,
    token VARCHAR(64) NOT NULL,
    last_used TIMESTAMP NOT NULL
);
~~~

Use versioned migrations, indexes/constraints, and DB permission policies. Never expose this table directly to application users through generic APIs/ORMs. The table holds credentials and authentication trails; apply retention/data deletion policies matching product and legal requirements.

### 10.4. Do Logout and Revocation Actually Happen?

- **Logout in the current browser:** the service can clear the cookie and persistent records per Spring Security logic, depending on configuration. Test the actual logout handler.
- **Log out of all devices:** generally requires deleting all persistent-token records for the username/account or applying server-side credential versioning/revocation state, not merely clearing the current browser's cookie.
- **Password change:** enforce a policy to delete/rotate remember-me records on password change if old cookies must be blocked.
- **Account lock / suspected compromise:** block auto-login, delete token records, and notify the user.
- **Account deletion:** delete records and handle backups/retention per policy; never leave orphaned tokens.

Never rely solely on `Cookie Max-Age=0` to claim the server revoked all stolen copies of a cookie. A browser receiving a delete-cookie header cannot erase a token an attacker already saved elsewhere.

## 11. Storage Protection Controls

A complete policy must cover **client-side storage**, **server-side persistent tokens**, and **signing keys**.

### 11.1. Browser and Device

- Prefer server-issued remember-me cookies with proper flags; never move the secret into `localStorage` just so frontend code can read it easily.
- `HttpOnly` makes direct JS reading harder, though XSS defenses remain necessary.
- `Secure` and HSTS/TLS reduce token exposure over HTTP; verify trusted reverse proxies.
- Choose `SameSite` appropriately for UX/SSO and your CSRF threat model.
- Avoid enabling remember-me on shared devices when policy and consent disallow it.
- Design UI with a clear checkbox, a way to view/remove remembered devices, and warnings on public browsers when appropriate.
- Cookie lifetime and retention must be transparently explained to users and aligned with privacy policies.

### 11.2. Server-Side Token Store

- Least-privilege DB role; use a dedicated account for the authentication component when feasible.
- Partition the token table logically by tenant or enforce strict access rules to avoid cross-tenant queries.
- Protect backup snapshots, restore copies, and staging/test clones; never copy production persistent tokens into staging.
- Enable encryption at rest, database transport encryption, and secret rotation.
- Never log tokens, `series/token` values, or sensitive SQL bind parameters.
- Run a cleanup job for expired/revoked tokens with bounded retention and proper auditing.
- If adding custom token hashing/encryption, verify compatibility with comparison, rotation, and reuse detection rather than simply “hashing one column” and stopping there.
- If caching token state, configure TTL/invalidation so revocations take effect properly.
- Have investigation and handling procedures for token reuse caused by theft or suspicious concurrent requests.

### 11.3. Signing Keys and Secrets

- Store secrets in a secret manager/KMS or protected environment; never hardcode them in Git or container images.
- Scope permissions: the app can read only the keys it needs; unrelated users and services cannot.
- Rotation needs a runbook, canary, rollback window, and a plan for forced re-logins if required.
- Never leak keys into logs/stack traces/dumps, config dashboards, or metric labels.
- Ensure all nodes share the right key; roll out new keys in a controlled sequence so cookies do not suddenly break on some nodes.
- Never confuse the remember-me signing key with a JWT signing key, CSRF token, session ID, password pepper, or database encryption key: **each secret has a different scope and blast radius**.
- If a key leaks, investigate possible forgery of previously issued cookies and consider broad revocation/reset rather than merely “swapping the key and moving on” while other accounts/tokens remain at risk.

### 11.4. Privacy and Retention Policy

Series/token records usually tie to a username, timestamp, and possibly extra device metadata. When collecting such data:

1. Define the fraud-prevention/account-protection purpose and retention window.
2. Avoid storing unnecessary fingerprints or overly identifying metadata.
3. Provide revocation/deletion of remembered devices per product requirements.
4. Restrict admin/support visibility to **safe metadata**, never raw tokens.
5. Ensure account deletion and backup retention workflows comply with organizational and legal requirements.
6. Audit settings/rotation/revocation changes without recording the secrets themselves.

## 12. Operational Scenarios to Resolve Before Production

### 12.1. App Restart Invalidates Remember-me

**Token-based + new key on every boot:** old cookies fail verification → users must log in again. Solution: stable key supplied by a secret manager, consistent across nodes.

**Token-based + in-memory BCrypt regenerated:** password hash changes despite the same raw password → old cookies can fail. The demo does this intentionally; production requires a durable user store.

**Persistent-token + database wiped on every restart:** series/token records vanish → old cookies are no longer valid. Solution: durable DB and migrations, never in-memory H2 in production.

### 12.2. User Changes Password

If policy requires logging out remembered clients, ensure:

- Token-based: verify that password hash changes and validation checks truly invalidate the required cookies; test rather than assume.
- Persistent: explicitly revoke the account's records; do not expect password changes to auto-delete every record.
- Existing sessions and refresh tokens in other systems may require separate revocation; remember-me does not cover every auth mechanism.
- Password changes are sensitive actions, typically requiring `fullyAuthenticated()` or recent login/step-up MFA.

### 12.3. User Loses Phone or Laptop

If using persistent tokens, users should be able to revoke a device/series or all remembered devices. With stateless token-based signatures lacking per-device state, broad invalidation via key/password change or added server-side state is usually needed.

Never turn “clearing the cookie on user logout” into a claim that you invalidated **the cookie copy on a lost device**.

### 12.4. Opening Multiple Tabs Triggers Persistent Token Mismatch

Because series/token rotates, concurrent requests can submit the same old token simultaneously. One request refreshes the cookie while another reads the updated record. This can look like replay. Test concurrency on the backend, understand `PersistentTokenBasedRememberMeServices` behavior, and design the re-login UX; **never fail open** just to avoid races.

### 12.5. User Is Remembered, Yet Sensitive Transactions Are Protected

Apply the rule:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/account").authenticated()
    .requestMatchers("/sensitive").fullyAuthenticated()
    .anyRequest().denyAll())
~~~

This is a code fragment. A remembered user can view normal content on `/account` yet must re-enter password/elevate to full authentication to call `/sensitive`. Never use `isAuthenticated()` alone as a proxy for “user just re-entered password”.

## 13. Common Mistakes and How to Diagnose Them

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| No `remember-me` cookie after login | Checkbox unchecked, wrong field name, login failed, handler/config not invoked | Network POST login, form parameter, success handler, `RememberMeServices` |
| Cookie issued yet browser does not store it | Secure/HTTPS mismatch, Domain/Path/SameSite, browser privacy policy | `Set-Cookie` response and browser storage |
| Remember-me lost right after app restart | Signing key or password hash changed, DB tokens lost | Secret source, user store, persistent repository |
| One node accepts, another rejects | Inconsistent key/config or user store | Multi-node secrets, shared DB, routing |
| Cookie Max-Age still valid yet server rejects | Server expiry, account status, invalid signature, revoked record | Inspect status safely, never log tokens |
| Logged out in browser yet stolen cookie still works | Stateless token-based lacks per-token revocation | Design revocation/credential version/persistent token |
| User changed password yet persistent cookie still works | Token records were not deleted | Revoke on password change |
| Remembered user redirected on sensitive endpoint | `fullyAuthenticated()` requires full login | Distinguish authenticated vs. remembered |
| Persistent cookie frequently fails across multiple tabs | Token rotation race or reuse detection | Concurrency tests, re-login policy |
| Remember-me token leaked via support logs | Raw `Cookie`/`Set-Cookie` or DB dumps logged | Redaction and read permissions |
| Session cookie Secure works, remember-me cookie wrong | Session cookie settings do not apply to remember-me service | Inspect remember-me `Set-Cookie` separately |
| DB encrypted yet tokens still leaked in SQL logs | At-rest encryption does not protect logging/dumps | Secret redaction and log policy |
| Rotating key forces all users to re-login at once | Old token-based signatures rejected | Rotation plan and UX |
| Rotated persistent key yet records remain | Key is not the revocation tool for series/token | Delete repository records |
| User unchecked remember yet cookie still issued | `alwaysRemember` configured or reused cookie | Opt-in/opt-out policy and cookie issuance test |

### 13.1. Step-by-Step Debugging

1. Did the `POST` login request include a valid CSRF token, correct username/password, and proper checkbox value?
2. Did Spring Security invoke remember-me login success? Does the response include `Set-Cookie` with the right name?
3. Are `Max-Age/Expires`, `Secure`, `HttpOnly`, `SameSite`, `Path`, and `Domain` right in the real environment?
4. Did the browser store and send the cookie on the next request, or did privacy settings block it?
5. Is an active session already present, causing the remember-me filter to skip running?
6. When sending only the remember-me cookie, does the service successfully verify the signature or repository record?
7. For token-based, are the key and user password hash consistent across nodes/restarts?
8. For persistent, do repository/`series`/`token`/`last_used` follow the expected lifecycle and avoid unintended rotation/revocation?
9. Is the authorization rule `authenticated()` or `fullyAuthenticated()`?
10. Did user status/tenant/permissions/reauth policy change?
11. Is any log/telemetry accidentally capturing raw tokens, headers, or secrets?
12. If cookie theft is suspected, is an appropriate invalidation, notification, and audit playbook in place?

In learning environments, you can enable Spring Security DEBUG logs under strict control, yet **never** enable body/header/token dumps. Never print full `Authentication` or `Cookie` objects into logs because implementations/metadata can hold sensitive data.

## 14. Hands-on Exercises

1. Why is a remember-me cookie a distinct credential and riskier if leaked than a very short-lived session cookie?
2. Explain the difference between `JSESSIONID` and the `remember-me` cookie. What happens if only the session cookie is deleted?
3. When configured for 7 days, why is setting `Set-Cookie: Max-Age=604800` without a server-side expiration check insufficient?
4. Compare absolute lifetime vs. sliding/idle lifetime when a user visits every day.
5. Describe the data typically stored in a token-based cookie, and why a signature protects integrity but not confidentiality.
6. Explain the role of `rememberMe().key(...)` and the risks of hardcoding the key in Git.
7. If the key changes after a deploy, how are already-issued token-based cookies affected?
8. Why does token-based logout clearing only the current cookie not necessarily invalidate a copy stolen by an attacker?
9. In persistent-token mode, what is `series` for, what is `token` for, and why can `token` be rotated?
10. Why must the `persistent_logins` table be protected like a credential store rather than an ordinary audit table?
11. Why can you not simply replace the `token` column with a SHA-256 digest while keeping `JdbcTokenRepositoryImpl` unchanged and expect rotation/lookup to work?
12. Two tabs submit `token_1` simultaneously, and Tab A rotates it to `token_2`. What will Tab B experience and how should the system respond?
13. Write a MockMvc test proving an unchecked checkbox issues no remember-me cookie.
14. Write a test proving a request with only a remember-me cookie (no session) can access an `authenticated()` endpoint yet cannot pass a `fullyAuthenticated()` endpoint.
15. Why does a test using `@WithMockUser` fail to prove remember-me cookies are actually signed or verified?
16. Compare the impact of a password change on token-based vs. persistent tokens, stating assumptions and required revocation actions.
17. Put a remember-me cookie behind an HTTPS reverse proxy. Which forwarded header settings and `Secure` flag checks are needed?
18. Why is setting `server.servlet.session.cookie.same-site` insufficient to conclude the remember-me cookie has the desired `SameSite` policy?
19. When a user wants to “log out all devices”, design the UI + repository + server revocation, distinguishing it from current-browser logout.
20. Draft policies for a news site vs. a financial portal covering TTL, consent, sensitive re-auth, max devices, rotation, and incident handling.

## 15. Production Readiness Checklist for Remember-me

- [ ] Clearly state that remember-me differs from a full session and has weaker assurance than re-login.
- [ ] Issue remember-me cookies only when the user explicitly opted in or an approved policy applies.
- [ ] Enforce server-side TTL rather than relying solely on browser Max-Age; define absolute vs. idle policy clearly.
- [ ] Protect sensitive endpoints with `fullyAuthenticated()` or step-up/recent-auth policies.
- [ ] Configure appropriate `Secure`/`HttpOnly`/`SameSite`/`Path`/`Domain` attributes; inspect `Set-Cookie` behind a real reverse proxy.
- [ ] Enforce HTTPS, XSS/CSRF defenses, and logging redaction for `Cookie`/`Set-Cookie`.
- [ ] High-entropy signing key stored in a secret manager, separated per environment, consistent across nodes.
- [ ] Key rotation/revocation incident playbook ready; accept or handle impact on old cookies.
- [ ] If token-based, enforce cookie invalidation policies after password change/account compromise.
- [ ] If persistent, use a durable repository, schema migrations, DB permissions, encrypted backups, and retention.
- [ ] Ensure persistent tokens cannot leak through SQL logs/dumps/support screens.
- [ ] Design remembered-device revocation, all-device logout, and revocation on password reset if required.
- [ ] Test concurrent rotation/reuse detection; never convert errors into allow.
- [ ] Test multi-node/shared secrets/repository and deployment rollbacks.
- [ ] Test cookie issuance, unchecked box, malformed cookie, sessionless restore, TTL, fully-auth restriction, and logout.
- [ ] Monitor anomalous auto-logins, run incident response, and notify users appropriately.
- [ ] Never use hardcoded demo keys/passwords in real environments.

## 16. Conclusion

**Cookie Max-Age is not the whole expiration policy; a signing key does not replace revocation; and persistent token records are not harmless DB rows.** Token-based remember-me keeps operations lighter yet makes per-device cookie invalidation hard, whereas persistent-token improves state management and revocation at the cost of securing a bearer-credential store and handling token rotation.

Before enabling “Remember me” in Spring Security Servlet, decide **browser and server TTLs, renewal rules, access allowed when remembered-only, signing key storage/rotation, token store security, revocation on logout/password change, and response when cookies or DB are compromised**. Only when those pieces align does remember-me deliver good UX without creating an uncontrolled long-lived authentication bypass.

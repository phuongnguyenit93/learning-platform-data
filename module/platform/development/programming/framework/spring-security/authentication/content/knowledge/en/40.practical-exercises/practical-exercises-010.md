# Implementing OTT, Passkeys, or MFA on the Right Spring Security Version

## 1. Capstone Practical Objectives

This exercise builds a **deployable and testable authentication architecture** aligned with the exact Spring Security version, rather than copying a 7.x snippet into a 6.x project and disabling security controls when compilation or login errors appear.

Distinguish three options:

1. **OTT (One-Time Token) login**: signing in with a server-issued token, typically sent via an email magic link. The token is single-use, time-limited, and bound to an account/purpose. It can serve as a **standalone login mechanism** and does not automatically constitute MFA.
2. **Passkey / WebAuthn**: registering a public-key credential and authenticating via a challenge signed by an authenticator. The server verifies the signature, challenge, origin, RP ID, user handle, and user presence/verification per policy; **it never stores private keys**.
3. **MFA (Multi-Factor Authentication)**: a policy requiring **multiple authentication factors**, either app-wide or on sensitive actions. Adding an OTT/passkey form alone is not enough: authorization rules must **enforce** the required factors.

The goal is **"Implement OTT, passkeys, or MFA on the right version"**, so we will structure separate practice branches, choose version-appropriate capabilities, combine them when needed, and verify outcomes across Servlet filters, server-side storage, browsers, and authorization.

Primary scope: Spring MVC/Servlet applications with Java 17+, Spring Boot 3.x / Spring Security 6.5, or compatible Spring Boot 4.x / Spring Security 7.x. WebFlux requires dedicated reactive APIs; never reuse Servlet `HttpSecurity` or Servlet repositories unchanged.

## 2. Choose Your Version Before Choosing APIs

The table below reflects documentation branches released as of **November 2026**; when applying them, always inspect your actual dependency tree and security advisories.

| Platform | OTT Login | Passkeys | MFA Framework |
| --- | --- | --- | --- |
| Spring Security 5.x / Boot 2.x | No new OTT DSL; requires a custom audited implementation | WebAuthn needs separate library/flow integration; do not copy 6.5/7 DSL | Policy/step-up via custom authorization |
| Spring Security 6.4/6.5 / compatible Boot 3.x | `oneTimeTokenLogin(...)`, `OneTimeTokenService` | `webAuthn(...)`; 6.5 docs require `webauthn4j-core` | No 7.x `@EnableMultiFactorAuthentication`; implement custom policy or upgrade |
| Spring Security 7.0+ / compatible Boot 4.x | Still provides `oneTimeTokenLogin(...)` | Dedicated `spring-security-webauthn` module | `FactorGrantedAuthority`, `@EnableMultiFactorAuthentication`, `AuthorizationManagerFactories.multiFactor()` |
| Spring Security 7.1.x | Same OTT and WebAuthn capabilities as 7.x | Persistence/serialization and operational refinements per release | Adds conditional MFA support, including when WebAuthn is enrolled |
| Spring Security 7.2 prerelease/snapshot | Evolving APIs | Do not treat milestones/RCs as production defaults | Experiment only in tested sandboxes |

**Never mix 6.5 and 7.x code in one `build.gradle`.** In Spring Security 6.5, WebAuthn docs use `spring-security-web` and `com.webauthn4j:webauthn4j-core`; in 7.x, docs require adding `org.springframework.security:spring-security-webauthn`. Let your Boot major's BOM manage dependencies.

**Verified release note:** Spring Security 7.1.2 and 7.0.8 were released on **2026-10-23**. New projects can adopt stable 7.1.x if Boot 4 infrastructure is compatible. Never force Security 7 into Boot 3 just to get MFA APIs, and never ship unpatched 6.5 builds for passkey deployments using shared sessions.

### Version-Specific Security Advisories: Mandatory Checks

**CVE-2026-22751 — JDBC OTT TOCTOU/replay** (disclosed 2026-04-21):

- Certain versions of `JdbcOneTimeTokenService` allowed two concurrent requests using **the same one-time token** to establish multiple sessions.
- Affected versions: 6.4.0–6.4.15, 6.5.0–6.5.9, 7.0.0–7.0.4.
- Official fixes: **6.5.10+**, **7.0.5+**; 6.4.16 is under enterprise support.
- Concurrency/replay tests are mandatory. If using `JdbcOneTimeTokenService`, run a patched version rather than assuming the "OneTime" name guarantees atomicity.

**CVE-2026-47841 — WebAuthn User Verification bypass with distributed sessions** (disclosed 2026-08-20):

- Affects Spring Security WebAuthn when **`userVerification = REQUIRED`** and WebAuthn ceremony data is serialized/deserialized through a distributed `HttpSession` store such as Redis/JDBC.
- Affected versions: 6.5.0–6.5.11, 7.0.0–7.0.6, 7.1.0.
- Patched versions: **7.0.7+**, **7.1.1+**; **6.5.12** is listed in the advisory under Enterprise Support.
- Caused by identity comparison on user-verification values after serialization, not a weakness in WebAuthn signatures themselves.
- If a project must stay on 6.5 and needs `UV REQUIRED` with distributed sessions, **do not treat 6.5.11 OSS as patched**. Check supported patch availability or plan an upgrade.

Check the official advisories at https://spring.io/security/cve-2026-22751/ and https://spring.io/security/cve-2026-47841/ before releasing.

## 3. Three Easily Confused Terms: OTT, OTP/TOTP, Passkeys

| Mechanism | Proof | Origin | When to Use |
| --- | --- | --- | --- |
| OTT / magic link | Random server-issued token with expiry, single-use | Email / SMS / chosen channel | Passwordless login, recovery, or one MFA factor per policy |
| TOTP | Short code computed from shared secret + clock | Enrolled authenticator app | MFA/step-up; carries phishing-relay risk |
| HOTP | Code computed from shared secret + counter | Enrolled device/app | MFA in supported environments |
| Passkey / WebAuthn | Authenticator private-key signature over RP/origin-bound challenge | Platform / synced / cross-device security key | Phishing-resistant auth, optionally passwordless |
| Password | User knowledge; server checks `PasswordEncoder.matches` | User input | A "something you know" factor |
| Recovery code | Single-use backup code generated/stored per policy | Stored separately by user | Account recovery, not equivalent to WebAuthn |

**OTT is not TOTP**: OTT is **generated and delivered by the server**, whereas TOTP is generated locally by an authenticator app from a shared secret. Never confuse Spring Security's `oneTimeTokenLogin()` with verifying 6-digit authenticator app codes.

**Passkey does not mean "password plus OTP"**: WebAuthn is a public-key authentication ceremony; the authenticator itself can enforce PIN/biometric/user verification. A properly configured passkey with user verification can achieve high assurance without forcing users to type a password too. Policy must decide **which factors suffice for which actions** based on the threat model, not blindly force "two forms everywhere".

**MFA is not a UI screen**: if after entering a password the funds-transfer endpoint still accepts a password-only session, having an OTT entry page somewhere **provides zero MFA protection**.

## 4. Choosing an Exercise Branch for Your Requirements

**Branch A — Standalone OTT login**: fits systems wanting email magic-link login, optionally alongside `formLogin`. Works in Spring Security 6.5 and 7.x. Requires mitigating user enumeration, rate limiting, single-use consumption, expiration, link scanners, and mailbox compromise risks.

**Branch B — Passkey registration and login**: fits systems using WebAuthn on HTTPS browsers with a stable RP ID, origin, and persistent credential storage. Available in 6.4/6.5 with matching dependencies or 7.x via its dedicated module. Test registration, challenge replay, signatures, origin/RP ID, user verification, and account recovery.

**Branch C — MFA / step-up**: fits apps with sensitive actions like changing email, disabling MFA, or updating payment methods. In 7.x, use native factor authorities and authorization factories; in 6.x, build server-side factor evidence, issuance timestamps, and matching authorization rules. Accept factor authorities **created solely by the server/framework after verification**—never trust `FACTOR_OTT` or `mfa=true` from client requests.

**Recommended practice sequence:** run A on patched 6.5 → run B over HTTPS with a real browser → if C is needed, prefer stable 7.x or explicit custom authorization in 6.x. Never combine all three at once before having independent tests for each path.

## 5. Common Setup: Security and Project Structure

Illustrative functional layout:

```text
src/main/java/demo/auth/
  SecurityConfig.java
  AccountDirectory.java
  MagicLinkDeliveryHandler.java
  ... repositories if choosing JDBC OTT or JDBC WebAuthn
src/main/resources/
  application.yml
src/test/java/demo/auth/
  OttFlowIT.java
  WebAuthnFlowIT.java
  MfaAuthorizationIT.java
```

Application-specific classes such as `AccountDirectory`, email delivery, and auditing must be implemented by your project. This is a layout outline, **not a claim that those files already exist**.

### Minimum Baseline

- Pick compatible, patched Spring Boot / Security / Java versions.
- Use **HTTPS** on public browser origins; set session cookies `Secure`, `HttpOnly`, and appropriate `SameSite`.
- Configure trusted reverse proxy headers properly; WebAuthn RP ID and OAuth/OTT public links must never be built from attacker-supplied `Host` headers.
- For Spring MVC, include `spring-boot-starter-web`, `spring-boot-starter-security`, `spring-boot-starter-test`, and `spring-security-test`.
- Store immutable account IDs, enabled/locked status, verified emails, roles/tenants, and audits.
- Across multiple pods, use shared stores for sessions, OTT, and WebAuthn challenge/credential repositories as needed.
- A request enters only the first matching `SecurityFilterChain`. Verify `securityMatcher` does not exclude `/ott/generate`, `/login/ott`, or `/webauthn/*` from the intended chain.
- Keep CSRF enabled for browser sessions; never disable CSRF merely because custom login endpoints return JSON.
- Never log passwords, raw tokens, magic-link URLs, WebAuthn private material, session cookies, or recovery codes.

### Example Servlet Cookie Configuration

```yaml
server:
  servlet:
    session:
      timeout: 20m
      tracking-modes: cookie
      cookie:
        secure: true
        http-only: true
        same-site: lax
        path: /

# Consider only behind a trusted, sanitized ingress/proxy:
# server:
#   forward-headers-strategy: framework
```

`SameSite=Lax` works for most top-level GET redirects; it may not fit every iframe or cross-site POST flow. Enable HSTS at the edge once HTTPS covers the entire host.

## 6. Branch A — OTT Login in Spring Security 6.5

### 6.1. Dependencies and SecurityFilterChain

Gradle dependencies for a Spring Boot **3.x project managing compatible versions**:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

If using a JDBC store, add the JDBC starter and DataSource/DB migrations. Never pin `spring-security-web`/`spring-security-config` versions separately against Boot's BOM.

Minimal security chain combining form login and OTT:

```java
package demo.auth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                "/login",
                                "/login/ott",
                                "/ott/**",
                                "/assets/**"
                        ).permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .oneTimeTokenLogin(Customizer.withDefaults())
                .build();
    }
}
```

This is a **Servlet 6.5-compatible `SecurityConfig` class**; it does not supply an account directory, email sender, or `/ott/sent` view. With `oneTimeTokenLogin`, Spring Security provides default request/submit pages for demos, yet **cannot choose your delivery channel**: you must provide a `OneTimeTokenGenerationSuccessHandler`.

**Default flow to keep in mind:**

```text
Browser -> GET /login
  -> user selects OTT, enters username/email
Browser -> POST /ott/generate + CSRF token
  -> GenerateOneTimeTokenFilter
  -> OneTimeTokenService.generate(...)
  -> OneTimeTokenGenerationSuccessHandler
  -> email / SMS / delivery per app
Browser -> GET /login/ott?token=... (submit page)
Browser -> POST /login/ott + token + CSRF token
  -> OneTimeTokenAuthenticationFilter / AuthenticationProvider
  -> consume token (if valid)
  -> success: SecurityContext/Session + redirect
```

**GET on the magic link should only render the confirmation form**, never authenticate or consume the token immediately on GET. That limits disruption from email security scanners prefetching links. Verify exact submission endpoints against your deployed version.

### 6.2. Email Token Delivery Handler

Spring Security defines `OneTimeTokenGenerationSuccessHandler` so apps choose **how to deliver tokens** without baking mail logic into filters. Example using an application email service:

```java
package demo.auth;

import java.io.IOException;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.util.UriComponentsBuilder;
import org.springframework.security.authentication.ott.OneTimeToken;
import org.springframework.security.web.authentication.ott
        .OneTimeTokenGenerationSuccessHandler;
import org.springframework.security.web.authentication.ott
        .RedirectOneTimeTokenGenerationSuccessHandler;

@Component
public final class MagicLinkDeliveryHandler
        implements OneTimeTokenGenerationSuccessHandler {

    private final AccountDirectory accounts;
    private final MagicLinkSender mailer;

    // Illustrative domain; real deployments read a verified public
    // origin config, NEVER trusting arbitrary Host headers from requests.
    private static final String PUBLIC_ORIGIN =
            "https://login.example.test";

    private final OneTimeTokenGenerationSuccessHandler completed =
            new RedirectOneTimeTokenGenerationSuccessHandler("/ott/sent");

    public MagicLinkDeliveryHandler(
            AccountDirectory accounts, MagicLinkSender mailer) {
        this.accounts = accounts;
        this.mailer = mailer;
    }

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            OneTimeToken token) throws IOException, ServletException {

        String verifiedEmail =
                accounts.verifiedEmailFor(token.getUsername());
        String link = UriComponentsBuilder
                .fromUriString(PUBLIC_ORIGIN)
                .path("/login/ott")
                .queryParam("token", token.getTokenValue())
                .build().encode().toUriString();

        // Never log raw tokens, magic links, auth codes, or sensitive emails.
        mailer.send(verifiedEmail,
                "Secure sign-in",
                "Open the link to continue: " + link);

        completed.handle(request, response, token);
    }
}
```

`AccountDirectory` and `MagicLinkSender` are **application interfaces you must define**, e.g., `verifiedEmailFor(String username)` and `send(String to,String subject,String message)`. This class works inside Spring when those interfaces are implemented and imports match your version; **it is not a standalone Java SE class**. In production, configure `PUBLIC_ORIGIN` via an allowlist, enforce TLS, and verify account/channel ownership.

**Risks to handle inside the delivery handler:**

- Deliver only to an address verified and bound to the account **server-side**, never an arbitrary address from query parameters.
- Never leak user existence via noticeably different statuses, bodies, or response timings.
- Rate-limit per IP/account/destination and throttle the mail service; prevent mailbox flooding.
- Never reflect tokens in redirects or logs. Putting tokens in query links is convenient yet risks browser history, proxy logs, and `Referer`; set `Referrer-Policy: no-referrer`, use HTTPS, keep TTL short, and avoid third-party scripts.
- If mail delivery fails, never falsely report "sent"; design retries/outbox per policy without minting unlimited tokens.
- Attach safe correlation IDs for audits without logging secrets; generated links must target a fixed, trusted public host.

### 6.3. OneTimeTokenService and Persistent Storage

Without a custom `OneTimeTokenService` bean, Spring Security defaults to `InMemoryOneTimeTokenService`, which works for single-process demos but is unsuitable for multi-pod clusters.

For production, docs introduce `JdbcOneTimeTokenService`:

- Ships an SQL schema at `org/springframework/security/core/ott/jdbc/one-time-tokens-schema.sql`; create/migrate the table beforehand.
- Requires configured `JdbcOperations`/DataSource and DB hardening.
- All pods must share the store with matching TTL/semantics.
- **Must run a version patched for CVE-2026-22751** before relying on single-use under concurrency.
- If building a custom store, atomic consumption must happen in one transactional/conditional DELETE/UPDATE—never a separate "SELECT then DELETE" where two requests both read the token.

Illustrative SQL showing a **custom schema example**, not `JdbcOneTimeTokenService`'s official table:

```sql
-- CUSTOM TABLE, NOT Spring Security's built-in table names.
CREATE TABLE app_ott (
    digest VARCHAR(64) PRIMARY KEY,
    subject_id VARCHAR(100) NOT NULL,
    purpose VARCHAR(40) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL
);

-- In PostgreSQL, a conditional DELETE returning one row
-- ensures only one request consumes the token successfully.
DELETE FROM app_ott
 WHERE digest = :digest
   AND subject_id = :subject_id
   AND purpose = :purpose
   AND expires_at > CURRENT_TIMESTAMP
RETURNING subject_id;
```

Store SHA-256 digests of high-entropy tokens to reduce DB leak exposure; design DB schema, retention, and rate limits deliberately. For low-entropy tokens like 6-digit codes, **hashing does not prevent offline brute force**; enforce attempt counters, throttling, and strict TTLs.

**Never treat a successful DELETE alone as sufficient to grant access** if the user was disabled/locked/removed or the token purpose mismatches. Verify account status and policy at consumption time.

### 6.4. OTT Is Not Automatically a Second Factor

An email magic link can be used **instead of a password**. In that flow OTT is a **single login factor**, not "password + OTT". To achieve **MFA**, you need:

1. The user already verified their password in the current session.
2. An OTT is issued for **the same account** with purpose **step-up**, never reusing password-recovery tokens.
3. The token is consumed once and records factor evidence onto the current session upon verification.
4. Authorization on sensitive endpoints checks **both factors, freshness, and business permissions**.
5. Password resets, logouts, device changes, or suspected session compromise invalidate factor evidence per policy.

Email OTT is also not a truly independent channel in every threat model: if email opens in the same compromised browser/session, an attacker may access the link too. For high-risk actions, prefer passkeys/WebAuthn or stronger phishing-resistant factors.

## 7. Branch B — Passkey/WebAuthn on Spring Security 6.5

Spring Security 6.5 includes the `webAuthn(...)` Servlet DSL, though its dependencies **differ** from 7.x. Per the 6.5 guide:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    // For WebAuthn when using Spring Security 6.5.
    // Verify the version supported by your actual patch release docs:
    implementation 'com.webauthn4j:webauthn4j-core:0.29.7.RELEASE'
}
```

The Boot security starter already includes `spring-security-web`; Spring Security 6.5 docs also show `spring-security-web` alongside `webauthn4j-core`. Never drop 7.x's `spring-security-webauthn` module onto a 6.5 classpath assuming compatibility.

MVC configuration:

```java
@Bean
SecurityFilterChain passkeyChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/login", "/assets/**").permitAll()
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .webAuthn(webAuthn -> webAuthn
                    .rpId("example.test")
                    .allowedOrigins("https://login.example.test"))
            .build();
}
```

This snippet belongs in `@Configuration` with imports for `HttpSecurity`, `SecurityFilterChain`, and `Customizer`. Never run this bean alongside a second fallback `SecurityFilterChain` without configuring `@Order`/`securityMatcher`. Also provide a `UserDetailsService`/account source so authenticated users can register credentials.

**RP ID and origin are distinct concepts:**

- `rpId` is the relying party identifier, typically a valid domain of the RP **without scheme or port**. Browsers/authenticators scope credentials to the RP ID.
- `allowedOrigins` are **full origins** including scheme + host + non-default port, e.g., `https://login.example.test`.
- If browsers connect via an HTTPS reverse proxy while Spring sees `http://app:8080` or a mismatched allowed origin, the ceremony fails.
- CORS headers must never be used to mask RP ID/signature errors, and never set `allowedOrigins("*")`.

### Passkeys Must Be Registered Before Login

An already signed-in user (authenticated via password or a sufficiently strong flow) runs:

```text
GET /settings/passkeys  (requires authenticated)
  -> choose "Add passkey"
POST /webauthn/register/options + CSRF
  -> Spring generates registration challenge/options
  -> challenge state stored server-side
Browser -> navigator.credentials.create({ publicKey: decodedOptions })
  -> authenticator creates credential/private key
  -> browser returns attestation response (not private key)
POST /webauthn/register + CSRF + credential response
  -> Spring verifies challenge, origin, RP ID, attestation policy
  -> UserCredentialRepository stores credential PUBLIC KEY
  -> user sees passkey in list
```

Specifically across 6.5/7.x docs:

- `POST /webauthn/register/options` returns creation options/challenge.
- `POST /webauthn/register` accepts the credential from the browser.
- Only authorized users may register credentials onto their own accounts; never accept arbitrary client `userId` values to bind keys to other accounts.
- Adding a passkey is a **high-risk action**: require recent authentication/step-up per policy and notify the user.
- Challenges must be single-use, never shared across sessions, and have bounded TTL/transaction state.
- When calling `navigator.credentials.create`/`get`, binary fields like `challenge`, `rawId`, and `authenticatorData` must be base64url encoded/decoded per the WebAuthn JSON spec; never send raw JS `ArrayBuffer` objects expecting Spring to guess them.

### Credential Repositories

Spring Security defines two abstractions:

- `PublicKeyCredentialUserEntityRepository` maps RP user entities / user handles to accounts.
- `UserCredentialRepository` persists credential IDs, public keys, and metadata/counters per implementation.

6.5 provides JDBC implementations:

```java
@Bean
JdbcPublicKeyCredentialUserEntityRepository credentialUsers(
        JdbcOperations jdbc) {
    return new JdbcPublicKeyCredentialUserEntityRepository(jdbc);
}

@Bean
JdbcUserCredentialRepository userCredentials(JdbcOperations jdbc) {
    return new JdbcUserCredentialRepository(jdbc);
}
```

Put this in `@Configuration` and import the repository classes from the matching Spring Security version's package. Verify exact schema/class names in your chosen patch release's Javadocs, create tables via migrations, and enforce foreign keys and unique credential IDs. Default in-memory persistence loses passkeys on restart; persistent JDBC/repositories are required for production.

## 8. Branch B on Security 7.x: Dedicated Passkey Module

In Spring Security 7.0+, documentation requires:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-webauthn'
}
```

The compatible Boot BOM manages versions. Example config:

```java
@Bean
SecurityFilterChain passkeyChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/login", "/assets/**").permitAll()
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .webAuthn(webAuthn -> webAuthn
                    .rpId("example.test")
                    .allowedOrigins("https://login.example.test"))
            .build();
}
```

Requires HTTPS, a WebAuthn-capable browser, and an account with a registered credential. `formLogin` here supports initial onboarding/recovery; passkeys do not require entering a password on **every** login.

### WebAuthn Assertion Flow at Login

```text
Browser -> GET /login
  -> choose "Use passkey"
POST /webauthn/authenticate/options + CSRF
  -> server generates challenge and stores state
Browser -> navigator.credentials.get({ publicKey: decodedOptions })
  -> authenticator enforces user presence / verification per policy
  -> private key signs challenge (private key never leaves authenticator)
POST /login/webauthn + CSRF + assertion JSON
  -> Spring verifies server-side:
        - credential ID, public key, RP ID hash
        - clientDataJSON.type, challenge, origin
        - authenticatorData flags, user presence/verification
        - signature and counter/replay policy
  -> Authentication succeeds
  -> SecurityContext, session, and authorization
```

WebAuthn is phishing-resistant because credentials bind cryptographically to origin/RP ID and challenge. **Biometrics/PINs are verified locally on the authenticator**; the server never receives fingerprints or PINs. Never parse assertions manually and `return true` just because a client sent `userVerified=true`.

### Choosing userVerification

WebAuthn defines `required`, `preferred`, and `discouraged`; requiring user verification carries **assurance** implications:

- If the app requires authenticator PIN/biometrics, set **REQUIRED** and verify the UV flag server-side rather than just showing UI prompts.
- Default `preferred` does not guarantee every assertion performed user verification; define an explicit policy.
- **CVE-2026-47841** is critical for `REQUIRED` + distributed sessions: run patched builds like 7.0.7+/7.1.1+ and test over Redis/JDBC, not a single node alone.
- `signCount`/counters vary across authenticators (synced passkeys, counter=0); monitor anomalies per spec and library behavior rather than inventing rules that break valid credentials.

### Non-Negotiable Constraints

1. Never trust a challenge echoed by the client without matching it against server-side issuance.
2. Challenges need high entropy, short TTLs, single-use semantics, and ceremony/session binding.
3. RP ID must match the public domain—never an internal backend hostname like `app:8080`.
4. Origin in `clientDataJSON` must match the exact allowlisted scheme/host/port.
5. Never accept a credential registered under another account or tenant.
6. Look up `userHandle`/credential ID solely through a controlled repository.
7. Never expose WebAuthn registration unauthenticated so attackers can attach keys to victims' accounts.
8. Never drop CSRF on registration/options endpoints or cookie session logins.
9. Never create weak backup/recovery schemes that undermine private-key security.
10. Audit and notify users when removing/changing passkeys, revoking sessions per policy.

## 9. Branch C — Native MFA in Spring Security 7.x

In **Spring Security 7.0+**, `FactorGrantedAuthority` represents a verified factor along with its `issuedAt` timestamp. Each authentication mechanism supplies its factor authority upon verification; authorization rules decide which factors are required.

### 9.1. App-Wide MFA with Password + OTT

```java
package demo.auth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.authorization
        .EnableMultiFactorAuthentication;
import org.springframework.security.core.authority.FactorGrantedAuthority;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMultiFactorAuthentication(authorities = {
        FactorGrantedAuthority.PASSWORD_AUTHORITY,
        FactorGrantedAuthority.OTT_AUTHORITY
})
public class GlobalMfaSecurityConfig {

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/assets/**").permitAll()
                        .requestMatchers("/admin/**").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .oneTimeTokenLogin(Customizer.withDefaults())
                .build();
    }
}
```

This applies to **Security 7.x**, **not** 6.5. Crucially, the annotation injects factor requirements into authorization rules: if a user only verified a password, even `authenticated()` endpoints can still demand OTT. Per 7.0 docs, the framework can route users to the login mechanism for the missing factor.

**This class alone is not runnable**: it needs users, an OTT delivery handler, and an appropriate store. Never ship before testing email OTP delivery, CSRF, required factors, enrollment/recovery, public endpoints, API clients, and admin accounts.

### 9.2. Selective MFA: Requiring Extra Factors Only on Sensitive Routes

To require password + OTT only on `/admin/**` and `/settings/security/**`, Spring Security 7.x provides a **local** factory:

```java
@Configuration
@EnableMultiFactorAuthentication(authorities = {})
public class SelectiveMfaSecurityConfig {

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {

        var mfa = AuthorizationManagerFactories.multiFactor()
                .requireFactors(
                        FactorGrantedAuthority.PASSWORD_AUTHORITY,
                        FactorGrantedAuthority.OTT_AUTHORITY)
                .build();

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/assets/**", "/login")
                            .permitAll()
                        .requestMatchers("/admin/**")
                            .access(mfa.hasRole("ADMIN"))
                        .requestMatchers("/settings/security/**")
                            .access(mfa.authenticated())
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .oneTimeTokenLogin(Customizer.withDefaults())
                .build();
    }
}
```

Add imports for `org.springframework.security.authorization.AuthorizationManagerFactories` and the classes above. This is an **alternative configuration** to global MFA—never enable both `GlobalMfaSecurityConfig` and `SelectiveMfaSecurityConfig` together unless managing separate `SecurityFilterChain` beans. Code shape follows Spring Security 7.0 guidance.

**Why `@EnableMultiFactorAuthentication(authorities = {})`?** It activates MFA infrastructure without forcing factors onto **every** authorization rule automatically. We apply `mfa.hasRole`/`mfa.authenticated` strictly where needed, fitting step-up flows better than forcing two forms on every route.

**Detail not to miss:** `permitAll` on `/login`/`/ott/**` never disables CSRF. Ensure generated filter endpoints remain reachable and are not blocked by chain matchers.

### 9.3. Factor Freshness: Step-Up with validDuration

A user who entered a password or passkey 8 hours ago may still hold a session, yet changing an email or MFA settings requires fresher proof. In Security 7.x:

```java
var recentPassword = AuthorizationManagerFactories.multiFactor()
        .requireFactor(factor -> factor
                .passwordAuthority()
                .validDuration(Duration.ofMinutes(10)))
        .build();
```

This **snippet** imports `java.time.Duration` and `AuthorizationManagerFactories`. Applied as:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/settings/change-email")
            .access(recentPassword.authenticated())
        .anyRequest().authenticated());
```

This enforces **a password verified within 10 minutes**, not password **and** OTT. When business rules require two fresh factors, combine `requireFactor(...)`/`requireFactors(...)` accordingly and test per-factor expiration. A session-stored factor must never be treated as "fresh" simply because normal requests slide session cookie expiry.

**Version note:** `FactorGrantedAuthority` and `AuthorizationManagerFactories` are 7.0+ APIs. Never try importing them into 6.5.

## 10. MFA in Spring Security 6.5 When Major Upgrades Are Not Yet Possible

If a project is on Security 6.5 and needs MFA before upgrading to 7.x, `@EnableMultiFactorAuthentication` **does not exist**. A safe architectural approach:

1. Authenticate the first factor (password/provider) via Spring Security, establishing the session cleanly.
2. Issue a second challenge bound to **the same user, same session, and exact purpose**.
3. Only after the server verifies the token or WebAuthn assertion, record proof inside a **server-side** session/store: subject, factor type, `issuedAt`, assurance, and transaction/action binding.
4. Enforce a custom `AuthorizationManager<RequestAuthorizationContext>` or method-security guard verifying proof matches **subject, freshness, and action** before executing.
5. Clear proofs on TTL expiry, account switch, logout, or password reset.
6. Never fabricate `GrantedAuthority("FACTOR_OTT")` from query params or unverified form POSTs.

Example authorization pseudocode (not a full Spring class):

```java
boolean authorizeChangeEmail(
        Authentication currentUser,
        StepUpEvidence evidence,
        Instant now,
        String actionId) {

    return currentUser != null
        && currentUser.isAuthenticated()
        && evidence != null
        && evidence.subjectId().equals(currentUser.getName())
        && evidence.actionId().equals(actionId)
        && evidence.hasVerifiedPassword()
        && evidence.hasVerifiedSecondFactor()
        && now.isBefore(evidence.expiresAt());
}
```

`StepUpEvidence` is an **application-defined type**. Real implementations must handle atomicity, persistence, replays, and concurrency. Setting a bare `session.setAttribute("mfa", true)` after a GET link without action/TTL/subject binding can easily be abused.

### Never Conflate Verification with Authorization

Even when factors verify cleanly, domain authorization must still check:

- Is this user allowed to modify this email?
- Has the account been locked/disabled or the session revoked?
- Do amount/currency/recipient match what the user actually confirmed?
- Is step-up evidence bound to the exact payload/action?
- Is there an idempotency key preventing double-clicks from issuing duplicate transfers?

MFA solves **authentication assurance**, not ownership, RBAC/ABAC, CSRF, input validation, or transaction idempotency.

## 11. OTT + Passkeys Is Not Simply Adding Mechanism Names

At least three valid policies exist, each with distinct trade-offs:

| Policy | Example | Trade-Off |
| --- | --- | --- |
| `password OR passkey` for login | User picks method | Smooth UX, yet recovery must be strongly protected |
| `password AND OTT` for sensitive actions | Change email / transfer after password login | Two steps, though email channel remains phishable |
| `recent verified WebAuthn` **or** `password+OTT` | Approve transaction by passkey with fallback | Needs consistent assurance/freshness and fallback controls |

**Never claim WebAuthn "is already MFA" simply because the browser showed a fingerprint prompt.** The server must enforce WebAuthn user verification when policy demands it. With synced passkeys and UV, assurance can satisfy strong policies, though organizations must assess risks explicitly.

**Never turn fallback into a bypass:** if passkey login enforces user verification yet users can reset all passkeys via an unprotected email link, attackers will take the weaker recovery route. Recovery codes should be CSPRNG-generated, single-use, hashed/encrypted appropriately, and audited.

## 12. Sessions, CSRF, Proxies, and Real-World Pitfalls

### 12.1. Session Lifecycle

- Form login, OTT login, and WebAuthn login create or update `HttpSession`/`SecurityContext` per filter strategy; never mutate contexts haphazardly.
- Spring Security 6 uses explicit save semantics in custom flows; custom login controllers must call `SecurityContextRepository.saveContext(...)`, whereas built-in login filters handle it automatically.
- Session ID rotation after authentication prevents fixation; verify browsers send the **new** cookie.
- A pod holding a challenge in RAM will lose state if the callback lands on another pod; use shared session/challenge repositories in multi-instance setups.
- Invalidate/revoke sessions per policy on password resets, account disablement, or suspected device theft.

### 12.2. CSRF and Endpoints

- `POST /ott/generate` and `POST /login/ott` require CSRF protection when browsers use session cookies.
- `POST /webauthn/register/options`, `POST /webauthn/register`, `POST /webauthn/authenticate/options`, and `POST /login/webauthn` all require proper CSRF/nonce/challenge handling.
- A `GET` magic link with a URL token must restrict referrers/logging and **must have zero authentication side effects** when email clients preview links.
- Never disable CSRF globally just because WebAuthn calls send JSON. Configure SPA CSRF token transport/repositories properly.

### 12.3. Public Origin Behind Reverse Proxies

WebAuthn RP ID/allowed origins, OTT magic-link base URLs, and OAuth2 redirect URIs depend on accurate public scheme/host/path values. If clients see `https://login.example.test` while the backend thinks `http://app:8080`:

- `Secure` cookies may be misconfigured unless set explicitly.
- Magic links can point to internal hosts or plain HTTP.
- WebAuthn origin validation will fail.
- Callbacks/challenges can lose sessions due to host/path mismatches.

Trust `Forwarded`/`X-Forwarded-*` headers only from proxies that strip client-supplied headers. Prefer allowlisted public origins for magic links and fixed `rpId`/`allowedOrigins` configs. Never set `Domain=.example.test` carelessly so every subdomain shares sessions uncontrollably.

## 13. Standalone Java 17: Simulating Single-Use OTT and Factor Policies

This program **runs on Java SE 17 with zero Spring dependencies** to demonstrate semantics clearly. It implements:

- `SecureRandom` generating 32 bytes, `Base64URL` tokens, and SHA-256 digests as in-memory keys.
- Server checks of **subject + purpose + expiry** before consuming an OTT.
- `ConcurrentHashMap.computeIfPresent` so at most one concurrent request consumes successfully.
- "Factor evidence" bound to **the same subject** with a freshness window.
- A passkey branch marked **only after a real server-side WebAuthn verifier proves validity**; the program does not verify WebAuthn signatures itself.

Create **`OttPasskeyMfaPolicyDemo.java`**:

```java
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.security.*;
import java.nio.charset.StandardCharsets;

public class OttPasskeyMfaPolicyDemo {
    enum Factor { PASSWORD, OTT, PASSKEY }

    record Token(String user, String purpose, Instant expiresAt) {}

    static final class ManualClock extends Clock {
        private final AtomicReference<Instant> now;

        ManualClock(Instant initial) {
            now = new AtomicReference<>(initial);
        }

        @Override public Instant instant() {
            return now.get();
        }

        @Override public ZoneId getZone() {
            return ZoneOffset.UTC;
        }

        @Override public Clock withZone(ZoneId zone) {
            return Clock.fixed(instant(), zone);
        }

        void forward(Duration amount) {
            now.updateAndGet(t -> t.plus(amount));
        }
    }

    static final class OneTimeTokens {
        private final Clock clock;
        private final SecureRandom random = new SecureRandom();
        private final ConcurrentHashMap<String, Token> tokens =
                new ConcurrentHashMap<>();

        OneTimeTokens(Clock clock) {
            this.clock = clock;
        }

        String issue(String user, String purpose, Duration lifetime) {
            if (user == null || user.isBlank()
                    || purpose == null || purpose.isBlank()
                    || lifetime.isNegative() || lifetime.isZero()) {
                throw new IllegalArgumentException("Invalid request");
            }

            while (true) {
                byte[] randomBytes = new byte[32];
                random.nextBytes(randomBytes);
                String raw = Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(randomBytes);
                String key = digest(raw);

                Token newToken = new Token(
                        user, purpose,
                        clock.instant().plus(lifetime));

                if (tokens.putIfAbsent(key, newToken) == null) {
                    return raw;
                }
            }
        }

        boolean consume(String raw, String user, String purpose) {
            if (raw == null || raw.isBlank()
                    || user == null || purpose == null) {
                return false;
            }

            AtomicBoolean used = new AtomicBoolean(false);

            tokens.computeIfPresent(digest(raw), (key, token) -> {
                if (!clock.instant().isBefore(token.expiresAt())) {
                    return null; // expired
                }
                if (!token.user().equals(user)
                        || !token.purpose().equals(purpose)) {
                    return token; // do not consume on wrong user/purpose
                }
                used.set(true);
                return null; // single successful consumption
            });
            return used.get();
        }

        private static String digest(String raw) {
            try {
                byte[] bytes = MessageDigest.getInstance("SHA-256")
                        .digest(raw.getBytes(StandardCharsets.UTF_8));
                return HexFormat.of().formatHex(bytes);
            } catch (NoSuchAlgorithmException ex) {
                throw new IllegalStateException(ex);
            }
        }
    }

    static final class Session {
        private final String subject;
        private final Clock clock;

        private final EnumMap<Factor, Instant> verifiedAt =
                new EnumMap<>(Factor.class);

        Session(String subject, Clock clock) {
            this.subject = subject;
            this.clock = clock;
        }

        // TEST STUB: only SERVER-verified authenticators
        // may invoke this in real implementations.
        void markVerified(String verifiedSubject, Factor factor) {
            if (!subject.equals(verifiedSubject)) {
                throw new SecurityException("Different identity");
            }
            verifiedAt.put(factor, clock.instant());
        }

        boolean hasFresh(Factor factor, Duration maxAge) {
            Instant time = verifiedAt.get(factor);
            Instant now = clock.instant();
            return time != null && !now.isBefore(time)
                    && now.isBefore(time.plus(maxAge));
        }

        boolean signedIn() {
            return hasFresh(Factor.PASSWORD, Duration.ofHours(8))
                    || hasFresh(Factor.PASSKEY, Duration.ofHours(8));
        }

        boolean canChangeEmail() {
            return hasFresh(Factor.PASSWORD, Duration.ofHours(8))
                    && hasFresh(Factor.OTT, Duration.ofMinutes(5));
        }

        boolean canApproveByPasskey() {
            return hasFresh(Factor.PASSKEY, Duration.ofMinutes(2));
        }
    }

    public static void main(String[] args) throws Exception {
        ManualClock clock = new ManualClock(
                Instant.parse("2026-01-01T00:00:00Z"));
        OneTimeTokens tokens = new OneTimeTokens(clock);

        String token = tokens.issue(
                "alice", "step-up", Duration.ofMinutes(5));

        System.out.println("wrongSubjectConsumes="
                + tokens.consume(token, "bob", "step-up"));
        System.out.println("wrongPurposeConsumes="
                + tokens.consume(token, "alice", "login"));
        System.out.println("firstUseAccepted="
                + tokens.consume(token, "alice", "step-up"));
        System.out.println("replayAccepted="
                + tokens.consume(token, "alice", "step-up"));

        String expiring = tokens.issue(
                "alice", "step-up", Duration.ofMinutes(1));
        clock.forward(Duration.ofMinutes(1));

        System.out.println("atExpiryAccepted="
                + tokens.consume(expiring, "alice", "step-up"));

        OneTimeTokens race = new OneTimeTokens(clock);
        String raceToken = race.issue(
                "alice", "step-up", Duration.ofMinutes(5));

        ExecutorService pool = Executors.newFixedThreadPool(12);
        try {
            CountDownLatch gate = new CountDownLatch(1);
            List<Future<Boolean>> results = new ArrayList<>();

            for (int i = 0; i < 12; i++) {
                results.add(pool.submit(() -> {
                    gate.await();
                    return race.consume(
                            raceToken, "alice", "step-up");
                }));
            }

            gate.countDown();
            int accepted = 0;
            for (Future<Boolean> result : results) {
                if (result.get()) {
                    accepted++;
                }
            }

            System.out.println("concurrentAccepted=" + accepted);
        } finally {
            pool.shutdownNow();
        }

        Session session = new Session("alice", clock);
        session.markVerified("alice", Factor.PASSWORD);

        System.out.println("signedInWithPassword="
                + session.signedIn());
        System.out.println("emailBeforeSecondFactor="
                + session.canChangeEmail());

        session.markVerified("alice", Factor.OTT);
        System.out.println("emailAfterSecondFactor="
                + session.canChangeEmail());

        clock.forward(Duration.ofMinutes(5));
        System.out.println("emailAtFreshnessExpiry="
                + session.canChangeEmail());

        boolean otherIdentityRejected = false;
        try {
            session.markVerified("bob", Factor.PASSKEY);
        } catch (SecurityException expected) {
            otherIdentityRejected = true;
        }

        System.out.println("wrongPasskeySubjectRejected="
                + otherIdentityRejected);

        // Simulating the RESULT of a server-side WebAuthn verifier.
        // Never accept a "webauthnVerified" boolean from the client.
        session.markVerified("alice", Factor.PASSKEY);
        System.out.println("passkeyApproval="
                + session.canApproveByPasskey());

        clock.forward(Duration.ofMinutes(2));
        System.out.println("passkeyApprovalExpired="
                + session.canApproveByPasskey());
    }
}
```

Run with JDK 17+:

```bash
javac OttPasskeyMfaPolicyDemo.java
java OttPasskeyMfaPolicyDemo
```

**Expected output verified under Java 17/JShell:**

```text
wrongSubjectConsumes=false
wrongPurposeConsumes=false
firstUseAccepted=true
replayAccepted=false
atExpiryAccepted=false
concurrentAccepted=1
signedInWithPassword=true
emailBeforeSecondFactor=false
emailAfterSecondFactor=true
emailAtFreshnessExpiry=false
wrongPasskeySubjectRejected=true
passkeyApproval=true
passkeyApprovalExpired=false
```

### Limitations of the Example

1. `OneTimeTokens` is a single-JVM store. `computeIfPresent` provides **in-process** atomicity, not multi-pod DB transactions/CAS.
2. `Session.markVerified(...)` is a **test stub**. Never expose it from a controller in real apps; factors must be recorded only after an `AuthenticationProvider` or WebAuthn verifier **validates cryptographic proof**.
3. No real password or WebAuthn signature verification is performed; this tests **policy/lifecycle**, not WebAuthn cryptography.
4. `canChangeEmail` checks only recent password and OTT, without binding the token to the **target email**; production should bind token/action and confirm in UI against transaction swapping.
5. `canApproveByPasskey` illustrates recent passkeys, without implying every passkey assertion meets product `UV REQUIRED` assurance.
6. Omits CSRF, browsers, email delivery, rate limits, distributed sessions, account status, recovery, and auditing.
7. Raw tokens must never be logged; SHA-256 digests fit **high-entropy** tokens, not 6-digit codes.
8. Time uses a fixed `ManualClock` for exact expiry testing; production needs managed clocks and clock-skew policies.
9. `concurrentAccepted=1` shows one token can be consumed only once; it does not limit how many distinct logins succeed.
10. Does not cover real-world WebAuthn `signCount`, origin, RP ID, or attestation policies—rely on a vetted library.

## 14. Integration Tests: Proving OTT Is Single-Use

Priority tests when wiring real Spring Security:

| Scenario | Test Layer | Expected Outcome |
| --- | --- | --- |
| POST generate with valid CSRF | MockMvc + fake email sender | Delivery handler called, raw token not logged |
| POST generate missing CSRF | MockMvc | Rejected per CSRF policy |
| Nonexistent username/email | MockMvc | Does not disclose account existence; avoids sending unsolicited mail |
| Valid unexpired token | Full chain + store | Login succeeds once |
| Consumed token | Store/HTTP | Replay fails; no second session created |
| Token at exact `expiresAt` | Clock test | Rejected |
| Another user's token | Store + auth provider | Cannot sign into wrong account |
| Wrong-purpose token | Store | Cannot use recovery token for login |
| 12–50 concurrent requests with same token | DB/cluster integration | **Exactly one authentication succeeds** |
| InMemory store + two pods | Distributed deployment test | Exposes lost tokens when routed to another node |
| Unpatched JDBC store | Version audit | **Block release** if affected by CVE-2026-22751 |
| Scanner GETs email link | Browser/E2E | GET does not consume the token |
| Email delivery fails | Service/integration | Does not falsely claim "sent"; preserves audit |
| Token leaked in logs/Referer | Security audit | Zero raw tokens/queries in access logs |
| Logout after OTT login | MockMvc/browser | Session invalidated |
| User disabled before consume | Auth provider test | Access denied per policy |

**Important:** MockMvc does not simulate browser email-link scanners, `SameSite` cookies, or real proxies. Concurrency tests must hit a **real** DB/store with concurrent transactions/requests, never mocking `OneTimeTokenService.consume` to `thenReturn(true)`.

Example `MockMvc` fragment:

```java
// Inside @SpringBootTest + @AutoConfigureMockMvc with the real
// SecurityFilterChain (spring-security-test imports).
mvc.perform(post("/ott/generate")
        .param("username", "alice")
        .with(csrf()))
    .andExpect(status().is3xxRedirection());

// Then verify FakeMailSender was invoked, read the token
// in test memory only, and POST /login/ott with CSRF.
```

This is a **fixture-based fragment**; exact status codes vary with custom success handlers. Never claim a 302 redirect alone proves the email was sent or the store consumed atomically.

## 15. WebAuthn Integration Tests Need Real Browsers and Verifiers

| Test | Expected |
| --- | --- |
| Registration options without session/CSRF | Rejected per policy |
| User A tries registering credential onto user B | Rejected |
| Expired WebAuthn registration challenge | Rejected |
| Replayed WebAuthn registration challenge | Rejected |
| Origin is `https://evil.test` | Rejected |
| RP ID hash mismatch | Rejected |
| 1-byte tampered WebAuthn assertion signature | 401 / failed authentication |
| Wrong credential ID or user handle | Never maps to another account |
| User presence required yet UP missing | Rejected per policy |
| User verification REQUIRED yet UV missing | Rejected per policy |
| Valid passkey assertion for registered credential | Authentication succeeds |
| Reused auth challenge | Replay fails |
| User-revoked credential | Cannot log in |
| Anomalous counter | Handled per policy/library with monitoring/risk response |
| Reverse proxy sets wrong public origin | Fails until corrected |
| 2 pods + shared session store | Consistent challenge/session |
| Distributed session + UV REQUIRED | Patched for CVE-2026-47841, serialization tested |
| Browser lacking passkey | Safe recovery path with no bypass |
| Synced / cross-device passkeys | Appropriate `signCount`/UV policy |
| Registering new passkey on old session | Requires recent authentication / step-up |
| CSRF on WebAuthn APIs | Still enforced |

In browser tests, use a **real WebAuthn environment** or Playwright/Selenium virtual authenticators where feasible. Never stub `navigator.credentials.get` to return fabricated signatures and declare passkeys working; real cryptographic verification must execute.

A Spring MockMvc integration test can assert endpoint statuses, CSRF, and authorization, yet **cannot prove the browser completed a WebAuthn ceremony**. Combine both layers.

## 16. Testing MFA/Step-Up and Application Authorization

### User / Factor Matrix

| Session State | Read Personal Profile | Change Email (Requires Password+OTT) | Approve via Recent Passkey |
| --- | --- | --- | --- |
| Anonymous | Deny/redirect | Deny | Deny |
| Valid password only | Allow | Deny; require OTT | Deny if policy accepts passkeys only |
| OTT used solely for login | Allow if OTT login permitted | Deny if password missing | Deny |
| Fresh password + OTT | Allow | Allow if ownership also holds | Per separate passkey policy |
| Password + expired OTT | Allow while session active | Deny; re-run step-up | Per policy |
| Verified, fresh passkey for right subject | Allow | Per policy; does not equal password+OTT | Allow if business approves |
| Verified passkey with insufficient UV | Per assurance policy | Never inflate assurance falsely | Deny if `UV REQUIRED` |
| Right factors yet wrong role/tenant | May read own profile | **Deny** unauthorized action | Deny |
| Logged-out / revoked session | Deny | Deny | Deny |
| User switches accounts in browser | Per new session | Never reuse old account's factor | Never reuse old account's proof |

### Freshness and Transaction Binding

For **changing email**:

```text
GET /settings/email
    -> authenticated session
POST /settings/email/challenge
    -> verify right account, CSRF, and action id
    -> issue OTT purpose=change-email, subject=alice, short TTL
    -> send over verified channel
POST /settings/email/confirm
    -> CSRF + token + action id + bound new email
    -> atomic consume
    -> verify session/user, recent factors, authorization, ownership
    -> transactional email update + audit + idempotency
    -> revoke challenge/session per policy
```

If a token binds only `subject` without binding **the new email or a transaction digest**, an attacker can swap the payload after the user confirms the factor. Sensitive actions need transaction binding and clear UI confirmation of what is being approved.

**Replay protection is not idempotency:** single-use tokens block repeated verification, whereas financial requests can still be retried by networks and need dedicated idempotency keys so funds are not debited twice. Never rely on token TTL in place of transaction locking.

## 17. Common Vulnerabilities and Anti-Patterns

**1. Copying `@EnableMultiFactorAuthentication` into Security 6.5.** That class does not exist in 6.x; use custom policies or a tested major upgrade.

**2. Adding `spring-security-webauthn` 7.x onto a 6.5 classpath.** Causes API mismatches; use `webauthn4j-core` per 6.5 docs.

**3. Enabling `oneTimeTokenLogin` alone and calling it "MFA".** Standalone OTT login is not password+OTT; authorization rules must enforce both factors.

**4. Treating email OTP as an isolated channel when the mailbox sits in the same compromised browser.** Evaluate phishing and account takeover; prefer passkeys where appropriate.

**5. Running default in-memory OTT across multiple pods.** Tokens created on pod A are missing on pod B; use a shared store.

**6. Failing to patch CVE-2026-22751.** Older JDBC OTT implementations allow multiple sessions from one token.

**7. Failing to patch CVE-2026-47841 with WebAuthn `UV REQUIRED` + distributed sessions.** UV requirements can be bypassed after session serialization.

**8. Generating low-entropy tokens without rate limiting.** Tokens become guessable or brute-forceable; enforce CSPRNG, TTLs, and attempt limits.

**9. Storing raw OTTs in logs/DB/analytics.** If leaked, tokens can be replayed while valid. Hash high-entropy tokens and redact logs.

**10. Sending email links over HTTP or internal hosts.** Leaks or breaks tokens; use an HTTPS public-origin allowlist and HSTS.

**11. Consuming tokens on GET when link scanners prefetch.** Users get burned before clicking; GET shows the submit page, POST with CSRF consumes.

**12. Disabling single-use to dodge link scanners.** Destroys core protection; fix the flow design instead.

**13. Using SELECT then DELETE for tokens assuming atomicity.** TOCTOU race condition; use patched JDBC or transactional conditional consume.

**14. Skipping disabled/locked checks at consumption time.** Tokens issued before account lock still mint sessions; verify account state per policy.

**15. Using backend hostname `localhost` as Passkey RP ID behind a public domain.** Ceremonies fail; RP ID must align with the public origin.

**16. Setting `allowedOrigins("*")` to "fix passkey errors".** Destroys origin boundaries; use an exact allowlist.

**17. Writing manual string comparisons for WebAuthn signatures.** Non-compliant and bypassable; use vetted libraries.

**18. Trusting a frontend-sent `userVerified` flag.** UV is protocol data inside authenticator output verified server-side, never a client boolean.

**19. Dropping CSRF on JSON WebAuthn/OTT endpoints.** Session cookies still carry CSRF risk; keep CSRF tokens active.

**20. Enabling global MFA without enrollment/recovery for all users.** Locks out users and admins; plan staged rollouts and recovery.

**21. Making `permitAll` too broad across sensitive endpoints.** Exposes registration or factor verification endpoints.

**22. Failing to bind factors to account/session.** Lets user A's OTP elevate user B's assurance.

**23. Omitting factor freshness.** A 3-month-old OTT still satisfies step-up; enforce validity windows.

**24. Checking URL roles while skipping ownership.** `ROLE_USER` still edits someone else's account; verify subject/tenant.

**25. Designing recovery weaker than primary auth.** Resetting passkeys via a plain email link nullifies WebAuthn's phishing resistance.

**26. Skipping real browser tests.** MockMvc simulates neither `navigator.credentials`/CTAP nor origin/`SameSite`/virtual authenticators.

**27. Skipping patch audits after minor upgrades.** Features work while remaining exposed to known CVEs.

**28. Mixing custom factor stores with `FactorGrantedAuthority` without one source of truth.** State drifts and opens bypasses; pick a single authoritative policy source.

**29. Putting raw factors/device fingerprints into metric labels.** Leaks PII and explodes cardinality; scrub audit events.

**30. Letting clients pass `purpose=admin` to mint privileged tokens.** The server must derive purpose from routes/authorization, never raw input.

## 18. Phased Implementation Plan

**Phase 1 — Baseline and dependency audit**

- Inventory exact Boot, Security, Java, Servlet container, browser, proxy, session store, and DB versions.
- Lock in branch A/B/C and assurance policies per user/action tier.
- Check relevant CVEs, upgrade to patched versions, and archive dependency resolution evidence.
- Draft positive/negative authorization matrices, rollout, and rollback plans.

**Phase 2 — Standalone OTT**

- Wire `oneTimeTokenLogin` and a test email delivery handler.
- Configure safe public URLs, account lookup, rate limits, and generic responses.
- Run single-use/replay/expiry/cross-user/concurrency tests.
- Switch from in-memory to patched JDBC/shared storage when running multiple pods.
- Verify mail scanners, redirects/cookies, logs, and session fixation.

**Phase 3 — Passkey onboarding**

- Configure `webAuthn` with matching version/dependencies, RP ID, and allowed origins.
- Persist user entities and credentials with schema migrations.
- Require reauth to register new credentials and verify account binding.
- Browser-test registration/assertion, new devices, and platform vs. cross-device authenticators.
- Verify `UV REQUIRED` + distributed sessions on patched builds.
- Build passkey management/removal pages and secure recovery.

**Phase 4 — Enforce MFA / step-up**

- 7.x: global or selective `AuthorizationManagerFactories`/`FactorGrantedAuthority`.
- 6.x: server-side verified factor evidence + dedicated `AuthorizationManager`.
- At minimum distinguish anonymous, one factor, both factors, expired factor, and revoked session.
- Add transaction binding, CSRF, auditing, and idempotency for sensitive commands.
- Smooth out UX for missing factors without creating redirect loops.

**Phase 5 — Canary and observability**

- Enable for internal/test cohorts first, then ramp gradually.
- Monitor login successes/failures by **mechanism** (password/OTT/WebAuthn), challenge/state errors, support tickets, and session failures.
- Dashboard separating password login, OTT login, passkey login, and MFA step-up.
- Keep raw tokens, secrets, and sensitive credential assertions out of logs.
- Maintain controlled fallback recovery, admin runbooks, and audits.

## 19. Pre-Production Checklist

- [ ] Exact Spring Boot / Security / Java versions verified compatible?
- [ ] Checked CVE-2026-22751 for JDBC OTT and CVE-2026-47841 for WebAuthn `UV REQUIRED`/distributed sessions?
- [ ] OTT uses `oneTimeTokenLogin` with a real delivery handler rather than default mail placeholders?
- [ ] Tokens have high entropy, short TTLs, account/purpose binding, and atomic single-use across all nodes?
- [ ] Concurrent requests with one token cannot create two sessions?
- [ ] Email sender targets only verified destinations without revealing username existence?
- [ ] Magic links use HTTPS public origins and never leak into logs, `Referer`, or analytics?
- [ ] GET links do not consume tokens; POST verification keeps CSRF?
- [ ] Passkey dependencies match Security 6.5 vs. 7.x without mixing modules?
- [ ] WebAuthn RP ID and `allowedOrigins` match public sites rather than backend hosts?
- [ ] Registration runs only for authenticated/stepped-up users?
- [ ] Credential repositories use persistent storage, migrations, and account foreign keys?
- [ ] Challenges/tokens persist and consume safely across multiple instances?
- [ ] Signatures, `clientDataJSON` challenge/origin, RP hash, and UP/UV are verified by the library?
- [ ] `userVerification = REQUIRED` enforced and tested with patched distributed sessions?
- [ ] Credential removal/recovery does not drop assurance below the threat model?
- [ ] Where MFA is required, authorization rules strictly enforce factors on the right URLs/actions?
- [ ] Factor evidence is server-generated, bound to subject/session/action, and tracks `issuedAt`/`validDuration`?
- [ ] Roles, resource ownership, and idempotency are checked **after** MFA?
- [ ] Sessions/cookies/CSRF/logout/proxy headers are verified in real browsers?
- [ ] MockMvc, DB concurrency, and WebAuthn browser tests all run together?
- [ ] Rollout, monitoring, support playbooks, and rollback plans exist for user lockouts?
- [ ] Zero secrets/PII/tokens/passkey assertions appear in logs or metric labels?

### Official Documentation and Security Advisories

- Spring Security 6.5 — One-Time Token Login: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/onetimetoken.html
- Spring Security 6.5 — Passkeys / WebAuthn: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passkeys.html
- Spring Security 7.0 — Passkeys dependencies and JDBC: https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/passkeys.html
- Spring Security 7.0 — MFA, FactorGrantedAuthority and authorization factory: https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/mfa.html
- Spring Security 7.1 — MFA conditional updates: https://docs.spring.io/spring-security/reference/7.1/servlet/authentication/mfa.html
- Spring Security 6.5 — Session Management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security — latest release documentation: https://docs.spring.io/spring-security/reference/
- Release on 2026-10-23 — Spring Security 7.0.8/7.1.2: https://spring.io/blog/2026/10/23/spring-security-maintenance-releases/
- Spring Security advisory **CVE-2026-22751** (JDBC OTT concurrent replay): https://spring.io/security/cve-2026-22751/
- Spring Security advisory **CVE-2026-47841** (WebAuthn UV + session serialization): https://spring.io/security/cve-2026-47841/
- OWASP Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP Multifactor Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html
- OWASP Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- W3C Web Authentication Level 3: https://www.w3.org/TR/webauthn-3/

**Conclusion:** "Implementing OTT, passkeys, or MFA" spans three overlapping yet distinct problems. On Spring Security 6.5, you can use `oneTimeTokenLogin` and `webAuthn` with matching dependencies/patches without copying 7.x MFA APIs. On Spring Security 7.x, use `FactorGrantedAuthority`/`AuthorizationManagerFactories` to **enforce** factors on sensitive routes rather than just adding UI forms. Make OTT replay and WebAuthn UV patches release gates, and declare success only once single-use, WebAuthn cryptographic verification, factor freshness, multi-node state, and authorization tests all pass.

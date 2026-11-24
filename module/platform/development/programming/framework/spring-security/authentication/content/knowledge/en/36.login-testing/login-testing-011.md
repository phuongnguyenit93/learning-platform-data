# OTT, Passkeys, and MFA: Expiration, Replay, Missing Factors, and Recovery

> **Lesson scope:** Spring Security – authentication, **Login Testing** group. Focuses on **designing, executing, and interpreting security tests** for One-Time Tokens (OTT/magic links), WebAuthn/passkeys, multi-factor MFA, and recovery when an authenticator is lost. Examples use Java 17+, Spring Boot 3.x / Spring Security **6.5** on the Servlet stack; built-in MFA APIs `FactorGrantedAuthority`/`@EnableMultiFactorAuthentication` belong to **Spring Security 7.x** and must not be mixed unverified into a Security 6.5 project.

## 1. Learning objectives

After completing this lesson, you can:

1. Distinguish **server-issued OTT**, **authenticator-generated TOTP/HOTP**, **signed WebAuthn/passkeys**, and **MFA policy**: all can appear in login yet have different testing methods.
2. Design **expiration** tests with a controllable clock: before expiry, at the exact `expiresAt` boundary, after expiry, and under clock/cluster drift.
3. Test **replay** after single use, two concurrent requests, two nodes, tokens with the same purpose for different users/tenants, and stale links after credential changes.
4. Test WebAuthn **challenge, origin, RP ID, credential ownership, signature, UP/UV, counter, and registration**; never call a mocked assertion cryptographic proof.
5. Test MFA **missing factor, wrong factor type, wrong account, stale factor, revoked factor, step-up, fallback**, and independence per threat model.
6. Design **account recovery** when losing keys/passkeys/TOTP devices: one-time backup codes, second devices, support workflows, re-enrollment, notifications, and session invalidation.
7. Layer unit, component, integration, and E2E tests without mistaking `@WithMockUser`/`jwt()`/Mockito mocks for real proof.
8. Write a standalone Java 17 program demonstrating TTL, one-use, challenge/UV, MFA, and recovery rules with deterministic stdout.

## 2. First, understand four terms clearly

### 2.1. What is OTT?

**One-Time Token (OTT)** in Spring Security's `oneTimeTokenLogin()` is a server-issued secret for an identity, delivered over a channel such as email or SMS, and submitted back to authenticate under the designed flow. No enrolled authenticator app is required. Tokens must be **unpredictable, time-limited, single-use**, and never conflated with password-reset or access tokens.

Do not confuse Spring Security's **One-Time Token** with TOTP/HOTP **One-Time Passwords**. A TOTP app holds an enrolled secret and computes time-based codes locally; an OTT is typically generated and distributed by the server.

### 2.2. What is a Passkey/WebAuthn?

A passkey is a WebAuthn credential using public-key cryptography. The authenticator holds the private key; the server holds the public key, credential ID, and owner info. On login:

```text
Server generates random challenge and saves flow state
     │
     ▼
Browser navigator.credentials.get(...) for RP ID
     │
     ▼
Authenticator signs assertion data, including UP/UV flags
     │
     ▼
Server verifies signature + challenge + origin + RP ID +
credential ownership + policy flags + flow/session
     │
     ▼
Create Authentication when all conditions hold
```

**A passkey is not an OTT**, even though both involve a one-time value (challenge/nonce). OTT uses a bearer secret presented to the server; WebAuthn sends a **signed assertion over a challenge** bound to origin and relying party.

### 2.3. MFA and "two steps" are different

MFA requires multiple independent **factor types** or a multi-factor authenticator meeting standards and policy. Two steps do not equal two factors: password + PIN are still two knowledge factors of the same type. Password + passkey possessing a key can satisfy two types; a passkey with **user verification (UV)** via local PIN/biometric can serve as a multi-factor authenticator depending on assurance/policy. Password + email OTT looks like two steps yet cannot automatically be treated as strong MFA; NIST SP 800-63B-4 **disallows email as an out-of-band authenticator** under that standard's assurance rules.

**Caution with Spring Security 7:** having `FACTOR_PASSWORD` and `FACTOR_OTT` in `Authentication` enforces mechanism requirements, yet **does not prove** the OTT was sent over a sufficiently independent channel or meets a specific NIST AAL level.

### 2.4. Recovery does not mean "skipping MFA"

Recovery is the path for someone who lost control of an authenticator; it can become **an easier attack path than normal login**. A strong policy defines who may recover, what evidence is required, who approves, which factors can be re-enrolled, whether a session is created, whether delays or temporary privilege restrictions apply, and how old devices are revoked.

The testing goal is not "always let the user in", but **legitimate recovery without letting an attacker bypass MFA**.

## 3. Overview matrix: what must be proven?

| Mechanism | Time-limited data | Single-use required? | Core verification | Recovery |
|---|---|---|---|---|
| OTT/magic link | Token with `expiresAt`/TTL | Yes: one secret must not log in twice | Token matches owner, purpose, TTL, atomic consume, email delivery | Issue new OTT per rate limit; never revive old tokens |
| TOTP/HOTP | TOTP time step / HOTP counter | Anti-replay per accepted step/counter | Account-bound seed, window, attempt limit, reject reused codes | Backup codes, second authenticator, recovery policy |
| WebAuthn/passkey | Challenge + options with timeout | Assertion must bind to fresh challenge; old challenge replay blocked | Public key signature, challenge, origin, RP ID, userHandle/credential, UP/UV | Backup passkey/policy-governed synced credential, recovery |
| MFA policy | Freshness of proofs | Non-replayable challenge/step-up | Enough factors of right types, user, session, purpose, and freshness; missing factor blocked | Recovery does not silently grant "MFA complete" |
| Backup/recovery code | TTL if policy requires | One time per code | Hash/entropy, owner, rate limit, atomic consume | After success force re-enrollment, notify, and revoke appropriately |

**Do not confuse "assert 200 OK" with complete proof**. A 200 response is only meaningful when the test genuinely passes through the corresponding verifier, authorization policy, and persistence. A test injecting a pre-authenticated principal can pass without checking secrets/signatures/second factors.

## 4. Layered testing workflow

```text
                    E2E / browser / virtual authenticator
                                   ▲
                 HTTP integration: filters + DB + CSRF +
                 authenticators/IdP + session + proxy
                                   ▲
                 Component: OTT store, WebAuthn verifier,
                 MFA policy, recovery service
                                   ▲
                 Unit: Clock, expiry, state machine,
                 race-safe compare-and-set, authorization
```

Each layer answers its own questions:

- **Unit**: is `now == expiresAt` rejected? Are consumed tokens blocked? Is having only `PASSWORD` without `PASSKEY` denied? Are backup codes for the same user without recovery assurance blocked?
- **Component**: does the service use a shared DB transaction/Redis atomic op? Does the OTP verifier track time-steps against replay? Is recovery bound to the right account?
- **HTTP integration**: do `POST /ott/generate`, `GET /login/ott`, `POST /login/ott`, and WebAuthn endpoints actually go through Spring filters, CSRF, handlers, and session strategies?
- **Crypto integration**: sign real WebAuthn assertions with a test/virtual authenticator; verify origin/RP/challenge/signature/flags and real registration data.
- **E2E**: browser/WebAuthn platform APIs, email scanners/link rewriting, cross-device flows, cookies, TLS/proxies, account recovery, and notifications.

Do not use `@WithMockUser`, `user()`, `jwt()`, or a test-set `signatureValid=true` flag to conclude **production cryptographic verification is secure**. Mock fixtures fit isolated policy tests; real tests must exist in the other layers.

## 5. Testing expiration: never use Thread.sleep()

### 5.1. Designing time boundaries

For a standard secret TTL rule:

```text
issuedAt = 2026-11-01T09:00:00Z
expiresAt = 2026-11-01T09:05:00Z
```

Assuming the system defines **`now.isBefore(expiresAt)` as valid**, tests must include:

| Check time | Expectation |
|---|---|
| `09:00:00Z` | Valid if issuance completed |
| `09:04:59.999Z` | Valid |
| `09:05:00Z` | **Expired** right at the boundary |
| `09:05:00.001Z` | Expired |
| Before `issuedAt` due to backward clock jump | Handled consistently per policy and issuance data |
| Machine A issues, machine B verifies (clock drift) | Never accidentally accept expired tokens or reject too early beyond drift budget |

If a framework/store uses a different comparison, **test per that implementation's exact contract** rather than assuming one time rule for every authenticator.

### 5.2. Injecting Clock in business logic

In Java:

```java
Clock fixed = Clock.fixed(
    Instant.parse("2026-11-01T09:05:00Z"), ZoneOffset.UTC);
Instant now = fixed.instant();
boolean valid = now.isBefore(expiresAt);
```

`Clock.fixed` tests boundaries instantly without waiting minutes or depending on CPU/CI speed. When production code calls `Instant.now()` directly in many places, deterministic tests are hard and races can occur from reading the clock multiple times.

In a Spring service, you can declare:

```java
@Bean
Clock clock() {
    return Clock.systemUTC();
}
```

Tests can supply a `Clock.fixed(...)` bean via `@TestConfiguration` or constructor injection. Never replace the production clock with a fixed clock in normal runtime.

### 5.3. Where expiration is enforced

- OTT: inside **server-side `OneTimeTokenService.consume`** or the store it calls, not just disabling a login button in the frontend.
- TOTP: during time-step/window verification and replay state checks; the server never trusts client-reported time.
- WebAuthn: challenge/options state has a server/RP-managed TTL; client UI timeouts do not prove the challenge is rejected on the backend.
- MFA: `verifiedAt`/`auth_time`/`issuedAt` of a factor from a trusted verifier must be fresh per endpoint policy; never use a browser-supplied `now`.
- Backup codes: codes may live long-term until used, yet must be **single-use** with protected enrollment/rotation; do not invent a fixed TTL if the product has none.

### 5.4. Do not just assert "expires after 6 minutes"

This test:

```java
Thread.sleep(360_000);
assertThat(service.consume(token)).isFalse();
```

is problematic: slow, flaky, dependent on scheduler and clock, misses the boundary, and drags out CI runs. Replace it with a fake clock or token/store fixture with exact `expiresAt` and **check 3 timestamps**: before, at, and after expiry. If a service lacks controllable time, add a test seam rather than sleeping.

## 6. OTT: Spring Security 6.5 flow and test points

Spring Security 6.5 documentation covers `oneTimeTokenLogin()`. Basic flow:

```text
POST /ott/generate     username, CSRF, and appropriate rate limit
     │
     ├── OneTimeTokenService.generate(...)
     ├── OneTimeTokenGenerationSuccessHandler sends link via email/SMS
     └── neutral UI response
              │
              ▼
GET /login/ott?token=...     OTT submission page
              │             must NOT auto-consume on GET
              ▼
POST /login/ott              token + CSRF
     │
     └── OneTimeTokenService.consume(...)
               ├── invalid/expired/used -> failure
               └── valid -> Authentication/session per config
```

Default `OneTimeTokenService` is `InMemoryOneTimeTokenService`; multi-node production needs a shared store, such as `JdbcOneTimeTokenService` or a custom implementation. Default TTL from `GenerateOneTimeTokenRequestResolver` in Spring Security 6.5 is roughly **5 minutes**, configurable.

**Version note:** Spring Security 6.5 passkeys use `webauthn4j-core` alongside `spring-security-web`; the Spring Security 7.x line has a separate `spring-security-webauthn` artifact. Never mix dependency coordinates across versions.

### 6.1. Spring Security configuration

File `src/main/java/example/security/OttAndPasskeySecurity.java` in a Spring Boot 3.x/Spring Security 6.5 project:

```java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OttAndPasskeySecurity {

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            MagicLinkDeliveryHandler handler)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/login/ott",
                    "/ott/sent", "/error").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .oneTimeTokenLogin(ott -> ott
                .tokenGenerationSuccessHandler(handler))
            .webAuthn(wa -> wa
                .rpId("example.org")
                .allowedOrigins("https://login.example.org"));

        return http.build();
    }
}
```

`MagicLinkDeliveryHandler` in the code is an **application-implemented bean** implementing `OneTimeTokenGenerationSuccessHandler`; this snippet is not a complete project without a handler/email service, `UserDetailsService`/account store, WebAuthn repositories, and the WebAuthn4J dependency. It illustrates configuration for testing all three login methods; do not use a config class missing dependencies and claim E2E tests work.

In production, the public magic-link origin must come from **trusted configuration** (canonical HTTPS), never assembled from inbound `Host`/`X-Forwarded-Host`; email goes to a verified recovery contact, never reflecting an arbitrary email/redirect sent by the requester.

### 6.2. Configuring TTL with a resolver (6.5)

To test a 10-minute TTL instead of the default, Spring Security 6.5 allows defining a `GenerateOneTimeTokenRequestResolver` bean:

```java
@Bean
GenerateOneTimeTokenRequestResolver ottRequestResolver() {
    DefaultGenerateOneTimeTokenRequestResolver delegate =
        new DefaultGenerateOneTimeTokenRequestResolver();

    return request -> {
        GenerateOneTimeTokenRequest req = delegate.resolve(request);
        return new GenerateOneTimeTokenRequest(
            req.getUsername(), Duration.ofMinutes(10));
    };
}
```

**This is a snippet inside a Spring `@Configuration` class**, requiring imports for `org.springframework.security.authentication.ott.GenerateOneTimeTokenRequest`, `org.springframework.security.web.authentication.ott.GenerateOneTimeTokenRequestResolver`, `DefaultGenerateOneTimeTokenRequestResolver`, and `java.time.Duration`; verify packages/APIs against the Javadoc of the exact Spring Security version in use. The testing principle stays the same: expiration is enforced at **the token service**, not the client.

### 6.3. OTT expiration matrix

| Case | Setup | Expectation |
|---|---|---|
| Valid unexpired token | `now < expiresAt`, unconsumed, right user | Accepted once |
| Token right at `expiresAt` | Clock right on boundary | Rejected per `now < expiresAt` policy |
| Token after `expiresAt` | Clock past limit | No login, no session created |
| Wrong token | Alter 1 character | No login; neutral response |
| Non-existent token | Store lookup miss | No login/never disclose username |
| Already-used token | Reused after success | No second login |
| Revoked token | Account locked, revoke/reset | Not accepted |
| Valid token yet different owner | Attempt to attach another request's user | Never transfer Authentication to someone else |
| Valid token yet wrong purpose | `PASSWORD_RESET` token submitted to OTT login | Rejected |
| Token issued for tenant A | Submitted at tenant B | Rejected per tenant binding |
| 2 tokens issued before credential change | Password/MFA enrollment changed | Old tokens revoked per version policy |
| GET opened by mail scanner before user | No POST/no consume | Real user can still submit token |
| Missing CSRF on form POST | Spring session CSRF enabled | Request blocked per config |

**Never mutate account state on GET** just because an email scanner visits the magic link. If a custom UI auto-submits a POST on page load, scanners/bots can consume the OTT. On token-bearing pages, minimize referrer leaks, redact logs, load no third-party analytics, and strip the token from the URL after completion.

### 6.4. OTT replay: two concurrent requests

**Wrong:**

```text
SELECT token WHERE used=false
if found:
    grantSession()
    UPDATE token SET used=true
```

Two requests on two nodes can both observe `used=false` before either updates. In PostgreSQL, use an atomic consume statement:

```sql
UPDATE ott_tokens
SET consumed_at = now()
WHERE token_hash = :digest
  AND purpose = 'LOGIN_OTT'
  AND consumed_at IS NULL
  AND expires_at > now()
RETURNING user_id;
```

This is an **illustrative schema/SQL for a custom store**; Spring's `JdbcOneTimeTokenService` has its own schema/queries, so do not copy this table and assume Spring uses it automatically. Still verify the user remains active, account/tenant policies, sessions, and transaction semantics. Tests must prove **the number of accepted requests is <= 1** when the same credential is sent concurrently.

A single-JVM test using `AtomicBoolean.compareAndSet(false,true)` only proves in-memory concurrency; production clusters require testing against shared database/Redis atomic operations. Never conclude an entire cluster is safe from an in-memory unit test.

### 6.5. Testing real Spring OTT over HTTP

With `@SpringBootTest` + `@AutoConfigureMockMvc(addFilters=true)`, a real flow test must:

1. Issue an OTT via `POST /ott/generate` with CSRF per config.
2. Use a test mail sink or a `OneTimeTokenGenerationSuccessHandler` spy/controlled sink to capture the **raw token** in the test environment; never write tokens to CI logs.
3. Verify `GET /login/ott?token=...` does not succeed login or consume the token.
4. Send `POST /login/ott` with token and CSRF, asserting Authentication/session succeeds when the token is valid.
5. Resend the same token with a **fresh session** or second client, asserting no Authentication; never let the first login's session skew the replay test result.
6. Issue another token whose `expiresAt` is set prior to the check timestamp via test clock/store; assert failure.
7. Try a token for a disabled user, password reset, or removed factor; verify account lifecycle policies.
8. Re-inspect storage to confirm consumed status, not just HTTP status.

### 6.6. MockMvc snippets do not replace expiration tests

The lines below are **a code fragment inside a Spring Boot test that already has `MockMvc mvc`, a real token, and CSRF enabled**:

```java
mvc.perform(get("/login/ott").param("token", issuedToken))
   .andExpect(status().isOk());

// Single-use token must hit the login endpoint handled via POST.
mvc.perform(post("/login/ott")
        .param("token", issuedToken)
        .with(csrf()))
   .andExpect(authenticated().withUsername("lan"));
```

Corresponding static imports to add in the test class:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
```

**Warning:** this snippet is not meant to run standalone. Depending on view/default handler, `GET /login/ott` may return a 200 template or another status; tests must match custom submit page configs. It **does not** create `issuedToken`, a mail sink, `OneTimeTokenService`, or `UserDetailsService`. And if a test uses only `@WithMockUser`, it **does not verify the token was consumed**.

## 7. Passkeys/WebAuthn: do not just test "login button succeeds"

WebAuthn has two distinct ceremony groups:

1. **Registration**: the app builds credential creation options/challenge; the authenticator creates a credential; the server verifies attestation/registration policy and binds the credential to the user.
2. **Authentication**: the app issues assertion request options/challenge; the authenticator signs the assertion; the server verifies and completes login.

In Spring Security 6.5, the sample endpoints in the documentation are:

```text
POST /webauthn/register/options     (+ CSRF; logged-in user)
POST /webauthn/register             (+ CSRF; credential result)
POST /webauthn/authenticate/options (+ CSRF; creates challenge)
POST /login/webauthn                (+ CSRF; submits assertion)
```

These are **default paths per Spring Security 6.5 docs**, customizable by app and version. They are not "token login" APIs like OTT.

### 7.1. What must be verified in an assertion?

| Property | Why it matters | Negative test |
|---|---|---|
| Challenge | Prevents replay; binds assertion to the current auth attempt | Use old challenge, another session's challenge, expired, already consumed |
| `clientDataJSON.type` | Must be `webauthn.get` for authentication | Replace with `webauthn.create` |
| `clientDataJSON.origin` | Prevents phishing from another origin | `https://evil.example` instead of allowed origin |
| RP ID hash in `authenticatorData` | Binds credential to relying party ID | Assertion created for another RP |
| Credential ID | Selects registered public key, matching user/tenant | User B's credential submitted for user A |
| Signature | Proves corresponding private key | Flip 1 byte in `signature` or `clientDataJSON` |
| UP flag | Authenticator observed user presence per policy | UP=false |
| UV flag | User verification when policy requires it | UV=false even though request required UV=required |
| `userHandle` | Associates resident/discoverable credential with right account | Mismatched user handle |
| Signature counter | Anomaly/clone signal on counter-supporting devices | Counter regression per policy, see nuance below |
| Challenge TTL/one-use | Eliminates stale assertions and races | Replay assertion after success, concurrent submits |
| Attestation/trust policy (registration) | Binds device hardware when enterprise requires it | Untrusted attestation, invalid format |

**Never take `origin` or `rpId` from an attacker-supplied request body as an allowlist**. Both values must be defined by trusted relying-party/server configuration; the browser and authenticator supply values for **the server to compare against**, not to define expected values.

### 7.2. UP vs UV and multi-factor passkeys

- **UP** = user presence, e.g., interacting with the authenticator.
- **UV** = user verification, e.g., PIN/biometric performed by the authenticator and attested inside signed authenticator data.
- If endpoint policy requires user verification via passkey, an assertion test with UP=true yet UV=false **must be rejected per policy**, even when the signature is valid.
- A passkey can be a **multi-factor cryptographic authenticator** when user verification is required/satisfied per assurance; never assume every WebAuthn response needs only a signature to meet the desired MFA level.

**Note:** `navigator.credentials.get()` can return a rejected promise when the user cancels, the device lacks credentials, the platform is unsupported, it times out, or browser policy blocks it. The UI must handle those cases **without auto-enabling weak fallbacks** or sending credentials to the server with "skip verification".

### 7.3. Sign counter: do not bake wrong rules into tests

Some authenticators report an incrementing `signCount`; a counter decreasing or failing to increment after previously incrementing can be a **signal** of a cloned credential or anomaly. However, **synced passkeys**/multi-device passkeys may report a counter of 0 or differ in behavior; never add a test asserting "every `counter = 0` is rejected" and conclude WebAuthn is secure. Per WebAuthn and verifier libraries, counter policies must suit the authenticator/credential type, persist state properly, and handle risks with explanation/auditing. Primary replay protection must still rely on **fresh challenges and signatures**, not counters alone.

### 7.4. Challenge expiry and replay

If challenge `c1` is issued for session A:

```text
POST /webauthn/authenticate/options
 → challenge=c1, session=A, expiresAt=t1
 → navigator.credentials.get(...) produces assertion S1
 → POST /login/webauthn S1 (valid signature/challenge) → success
 → POST /login/webauthn S1 again → reject replay
 → POST /login/webauthn S1 in session B → reject binding
 → POST /login/webauthn with S1 after t1 → reject expired
```

Test at boundaries `now < t1` and `now == t1` if the application publishes that policy. Options/challenges are stored in the HTTP session or shared store depending on configuration; test multi-node with real session replication/load balancers if production runs multiple nodes.

**Never generate duplicate challenges** or reuse an old challenge from another ceremony. And when issuing a new challenge, never make any old assertion valid merely because the user is still logged in.

### 7.5. Dedicated registration tests

- Anonymous or insufficiently assured user calling `POST /webauthn/register/options`: denied per policy.
- User A trying to register a credential for user B: must be rejected, even if `user.name` in JSON was altered.
- Two users trying to bind the same credential ID: must prevent cross-account takeover.
- If a security key was revoked, disallow assertion logins with that key; check the real credential repository.
- Creating a new credential while a user claims "lost key" must follow the recovery policy, not rely solely on a weak old session.
- Under an enterprise attestation policy, tests with valid signatures yet untrusted attestation are also rejected if policy requires.
- Duplicate registrations, concurrent enrollments, and persistence error rollbacks must never leave "half-saved" credentials or shift ownership to another account.
- Audit credential changes and notify old registered channels.

### 7.6. Testing real signed WebAuthn needs the right tools

A mocked assertion with `signatureValid=true` only tests business gating. Real signature testing must use a browser **virtual authenticator** (e.g., WebDriver/Chrome DevTools WebAuthn domain), a hardware authenticator in a lab, or a fixture library signing test assertions with fake keys and running **the real WebAuthn verifier**.

Tests must tamper byte-by-byte across failure classes:
- Public key does not match signature;
- Well-formed challenge not belonging to the session;
- Valid signature for a different RP;
- Origin is a different subdomain or unauthorized HTTP origin;
- Missing UP/UV flags;
- UserHandle mismatches owner;
- Authenticator credential was revoked;
- Attestation rejected per enterprise policy.

**Never mock `UserCredentialRepository` to return any arbitrary user's key when trying to prove ownership.** You can unit-test mappers with mocks, yet integration with a real/fixture repository is needed to test cross-user safety.

## 8. MFA: testing missing factors, wrong factors, and step-up

### 8.1. Two logins do not automatically make MFA

Examples of proofs:

```text
Password             → KNOWLEDGE
Server-submitted PIN → KNOWLEDGE
TOTP app secret      → POSSESSION (depends on policy and storage)
FIDO2 security key   → POSSESSION, phishing-resistant WebAuthn
WebAuthn UV          → activation/user verification inside authenticator
Email link OTT       → channel-based proof, not automatically AAL2
CAPTCHA/IP/location  → risk signals, not an independent factor
```

Tests must distinguish **number of verifications** from **factor types/independence**. Password + PIN: both steps succeed yet **fail** a policy requiring knowledge + possession. With an OTT sent to a mailbox opened by the same password, assess simultaneous compromise risk; NIST 800-63B-4 does not accept email as an OOB authenticator for that standard's assurance.

### 8.2. MFA requirement state machine

```text
ANONYMOUS
    │ proves password
    ▼
PRIMARY_VERIFIED / MFA_PENDING
    │ pending session + challenge bound to user/session/purpose
    │ no sensitive privileges yet
    ├─ timeout/attempts exhausted/revoked → FAIL
    ├─ wrong account/other session/other factor → FAIL
    └─ independent factor verified and fresh
            ▼
       MFA_COMPLETE
            │  rotate session ID/update real assurance
            ▼
       AUTHORIZATION for resource/tenant/role
```

**Important:** `Authentication.isAuthenticated() == true` after password does not prove MFA is complete. High-risk routes must also check factor requirements/freshness, not just `authenticated()`. Even after MFA passes, `ROLE_ADMIN`/scopes/tenant/ownership still must be checked.

### 8.3. Missing-factor matrix

| Verified factor(s) | Endpoint requires | Expectation |
|---|---|---|
| Nothing | Password + passkey | Requires authentication, blocks resource |
| Password only | Password + passkey | Blocks/routes to appropriate passkey challenge |
| Passkey only (when policy demands both specific factors) | Password + passkey | Blocks/routes to password step |
| Password + PIN | Knowledge + possession | Fails due to missing possession |
| Password + another user's valid TOTP | Same user must complete 2 factors | Rejected |
| Password + passkey UV=false | Policy requires passkey UV | Rejected |
| Password + passkey UV=true, right user, fresh | Password + WebAuthn (per policy) | Can pass, then check role/resource |
| Password + revoked passkey | Requires active passkey | Fails |
| Password verified yesterday + fresh passkey | Policy "both factors fresh" within 5 min | Fails due to stale password |
| Two factors of right user yet in unbound separate sessions | Single login flow | Must not be combined |
| Two valid factors yet suspended account | Account must be active | Still denies access |
| Already-used single-use recovery code | New step-up | Not treated as a new primary factor |

### 8.4. Framework MFA support by version

- **Spring Security 6.x:** includes form login, OTT, and WebAuthn/passkeys; to enforce **both mechanisms** per policy, the app must design this with a state machine, custom authorization manager, IdP/SSO assurance, or another MFA solution. Never assume enabling `formLogin()` + `oneTimeTokenLogin()` + `webAuthn()` together **automatically requires all three steps**: they can act as **alternative login methods**.
- **Spring Security 7.x:** adds `FactorGrantedAuthority` and `@EnableMultiFactorAuthentication` to require authorities like `FACTOR_PASSWORD`, `FACTOR_OTT`, `FACTOR_WEBAUTHN`. This enforces the mechanism policy, yet channel/binding, independence, and recovery still need separate review.

Illustrative **Spring Security 7.x** example (do not copy into 6.x):

```java
@EnableMultiFactorAuthentication(authorities = {
    FactorGrantedAuthority.PASSWORD_AUTHORITY,
    FactorGrantedAuthority.WEBAUTHN_AUTHORITY
})
public class StrongMfaConfig {
    // SecurityFilterChain configuring formLogin and webAuthn
    // along with repositories, challenges, and account policies.
}
```

This is an **API snippet** requiring imports for `org.springframework.security.config.annotation.authorization.EnableMultiFactorAuthentication` and `org.springframework.security.core.authority.FactorGrantedAuthority` in Spring Security 7.x. It is not a full app. Tests must confirm missing `FACTOR_WEBAUTHN` is blocked, passing password does not auto-grant other factors, and client-supplied authorities are never trusted.

### 8.5. Action-based freshness and step-up

For `POST /payment/transfer` or `POST /account/security/webauthn/register`, policy may require MFA freshly verified within **5 minutes** (an illustrative product-defined duration, not a NIST default). Test:

- MFA completed 8 hours ago with session still alive → requires step-up.
- Step-up right before the transaction with a session-bound challenge → allowed when permissions hold.
- Password in session A and passkey in session B → must not combine.
- Admin role revoked after step-up → authorization still blocks.
- Transaction amount/recipient modified after confirmation step → rejected if transaction binding exists.
- Frontend-submitted `acr`/`amr`/`auth_time` claims → rejected; must come from signed/trusted claims per issuer contract.

## 9. Recovery: the weakest link determines account takeover risk

A user loses their security key/TOTP phone or cannot unlock their passkey. Recovery must establish **another trusted proof**, not simply grant `ROLE_USER` after clicking "I lost my key".

```text
Lost authenticator
    │
    ▼
Recovery request (rate-limited + generic response)
    │
    ▼
Check recovery eligibility, remaining live factors,
 backup codes, identity proofing/support per risk policy
    │
    ▼
Create recovery intent with TTL + owner/session/purpose
    │
    ├─ weak proof, wrong owner, replay → DENY
    │
    └─ sufficient proof and approval → RESTRICTED RECOVERY
                                  │
                           re-enroll authenticator
                                  │
                  invalidate lost factor + stale sessions
                                  │
                    notification, audit, delay policy
                                  │
                    login/step-up under new policy
```

### 9.1. Valid recovery proof does not mean automatic MFA complete

A single-use backup code can be a **recovery credential**, yet must not by default replace all factors or grant all privileges immediately upon submission. The workflow must define **which actions** the code may recover: binding a new authenticator, temporarily restricting privileges, changing password, or logging in; each step has explicit scope and freshness.

When high NIST assurance requires strong recovery, never use email OTP as a compliant OOB authenticator merely for convenience. Email can serve for **notifications, contact verification, or one workflow step** under a different policy, without proving AAL-compliant MFA on its own.

### 9.2. Backup codes: mandatory cases

| Scenario | Expectation |
|---|---|
| Issuing backup codes | CSPRNG with sufficient entropy, shown once, stored hashed, bound to account |
| Valid unused code | Can complete only the permitted recovery action |
| Wrong code | Does not alter account state; attempt-limited |
| Already-used code | Rejected on second attempt |
| Two concurrent requests with same code | At most one succeeds on shared store |
| User B's backup code submitted for user A | Rejected |
| Password-reset code submitted to disable MFA | Rejected for wrong purpose |
| Old codes after reset/code rotation | Revoked |
| Actor lacks session/identity proof per policy | No recovery granted from a client flag alone |
| Disabled/admin-locked account | Never auto-unlocked by a recovery code |
| Successful recovery | Audited, notified, lost device revoked/marked, clear lifecycle |
| Lost all codes | Enters support/identity-proofing workflow; never skips MFA |

**Atomic single use:** database query similar to OTT yet with `purpose=ACCOUNT_RECOVERY`, `account_id`, and `consumed_at IS NULL`. Each code is verified for the right owner; changing/re-enrolling authenticators must sit inside an appropriate transaction or rollback/idempotent workflow so codes are not burned when recovery fails partway.

### 9.3. Re-enrollment and account takeover

Common attack: attacker knows the password or hijacks an old session, opens "Add passkey", and registers their own authenticator. Therefore:

1. Require reauthentication/step-up of matching assurance for **enrollment/replace/remove**.
2. Bind new WebAuthn registration challenges to **the exact local account ID, session, RP ID, and purpose**; never allow an attacker to alter `user.id` or `user.name` to hijack another account.
3. Reject credentials already bound to another user if product policy forbids sharing.
4. If a real user lost their last factor, apply a bounded recovery intent—neither demanding the impossible old key nor "skipping" verification.
5. After recovery, notify old contacts, log audits, and consider cooling-off periods/financial action limits for high-risk accounts.
6. Revoke/mark lost credentials, rotate credential/session versions, and enforce stale-session checks across all nodes.
7. Never let helpdesk reset MFA solely from an unverified email/request without proof or approvals.
8. Test idempotency: retrying the same event must not register duplicate credentials or undo revocation policies.

### 9.4. Synced passkey recovery

Synced passkeys can be restored via platform/provider sync mechanisms. That is an **ecosystem-managed authenticator lifecycle**, distinct from server-side account recovery. When a user has a synced passkey on another device, a valid WebAuthn login still requires challenge/origin/RP ID/signature/UV matching policy. Never "recover" by issuing an API token to someone claiming "my passkey synced".

Cross-device tests should cover real UI/hybrid transport, timing, user presence/verification, and no-device fallback instead of merely mocking a user principal.

## 10. Standalone Java 17: reproducing expiry, replay, missing factor, and recovery

This program uses JDK 17 with no Spring dependency. It models **policy decisions** with an in-memory token store using `AtomicBoolean`, WebAuthn assertions **already checked by another verifier**, and a recovery gate. The focus is deterministic test output using a fixed `Instant`; it does not simulate real WebAuthn signatures, send emails, or issue sessions.

**Safety boundary:** `signatureVerified`/`originValid`/`rpIdValid` in the example are **test-set assumptions only**; never accept such booleans from a browser as production verification results. Fixed secret strings are stdout fixtures **with zero entropy**; production uses CSPRNG, hashed storage, TTLs, and transactions.

Save file `AuthExpiryReplayRecoveryDemo.java`:

```java
import java.time.Instant;
import java.util.EnumSet;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;

public class AuthExpiryReplayRecoveryDemo {

    enum Factor { PASSWORD, PASSKEY, OTT }

    record Ticket(
        String owner, String purpose,
        Instant expiresAt, AtomicBoolean used) {}

    static final class OneTimeStore {
        private final Map<String, Ticket> tickets =
            new ConcurrentHashMap<>();

        void issue(String key, String owner,
                   String purpose, Instant expiry) {
            tickets.put(key, new Ticket(
                owner, purpose, expiry, new AtomicBoolean(false)));
        }

        boolean consume(String key, String owner,
                        String purpose, Instant now) {
            Ticket t = tickets.get(key);
            return t != null
                && t.owner().equals(owner)
                && t.purpose().equals(purpose)
                && now.isBefore(t.expiresAt())
                && t.used().compareAndSet(false, true);
        }
    }

    record Assertion(
        String owner, String challenge,
        boolean signatureVerified,
        boolean originValid,
        boolean rpIdValid,
        boolean userVerified) {}

    static boolean acceptPasskey(
            OneTimeStore store, Assertion assertion,
            String expectedUser, String expectedChallenge,
            Instant now) {

        return assertion.owner().equals(expectedUser)
            && assertion.challenge().equals(expectedChallenge)
            && assertion.signatureVerified()
            && assertion.originValid()
            && assertion.rpIdValid()
            && assertion.userVerified()
            && store.consume(
                expectedChallenge, expectedUser,
                "WEBAUTHN_CHALLENGE", now);
    }

    record Proof(
        String owner, Factor factor,
        Instant verifiedAt, boolean trustedVerifier) {}

    static boolean hasFreshMfa(
            String owner, Instant now,
            List<Proof> proofs) {

        EnumSet<Factor> valid = EnumSet.noneOf(Factor.class);
        for (Proof p : proofs) {
            if (!p.trustedVerifier()
                    || !p.owner().equals(owner)
                    || p.verifiedAt().isAfter(now)
                    || p.verifiedAt().isBefore(
                        now.minusSeconds(300))) {
                continue;
            }
            valid.add(p.factor());
        }
        return valid.contains(Factor.PASSWORD)
            && valid.contains(Factor.PASSKEY);
    }

    static boolean recover(
            OneTimeStore store, String code,
            String user, Instant now,
            boolean additionalRecoveryProofVerified) {

        return additionalRecoveryProofVerified
            && store.consume(code, user, "RECOVERY", now);
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-01T09:00:00Z");
        OneTimeStore store = new OneTimeStore();

        store.issue("ott-valid", "user-42",
            "LOGIN_OTT", now.plusSeconds(120));
        store.issue("ott-expired", "user-42",
            "LOGIN_OTT", now);

        System.out.println("OTT first: " +
            store.consume("ott-valid", "user-42", "LOGIN_OTT", now));
        System.out.println("OTT replay: " +
            store.consume("ott-valid", "user-42", "LOGIN_OTT", now));
        System.out.println("OTT expired: " +
            store.consume("ott-expired", "user-42", "LOGIN_OTT", now));
        System.out.println("OTT wrong purpose: " +
            store.consume("ott-valid", "user-42", "RECOVERY", now));

        store.issue("challenge-1", "user-42",
            "WEBAUTHN_CHALLENGE", now.plusSeconds(60));
        store.issue("challenge-2", "user-42",
            "WEBAUTHN_CHALLENGE", now.plusSeconds(60));
        Assertion wrongOrigin = new Assertion(
            "user-42", "challenge-1",
            true, false, true, true);
        Assertion valid = new Assertion(
            "user-42", "challenge-1",
            true, true, true, true);
        Assertion noUv = new Assertion(
            "user-42", "challenge-2",
            true, true, true, false);

        System.out.println("Passkey wrong origin: " +
            acceptPasskey(store, wrongOrigin,
                "user-42", "challenge-1", now));
        System.out.println("Passkey valid: " +
            acceptPasskey(store, valid,
                "user-42", "challenge-1", now));
        System.out.println("Passkey replay: " +
            acceptPasskey(store, valid,
                "user-42", "challenge-1", now));
        System.out.println("Passkey without UV: " +
            acceptPasskey(store, noUv,
                "user-42", "challenge-2", now));

        Proof password = new Proof(
            "user-42", Factor.PASSWORD, now, true);
        Proof passkey = new Proof(
            "user-42", Factor.PASSKEY, now, true);
        Proof stalePasskey = new Proof(
            "user-42", Factor.PASSKEY,
            now.minusSeconds(360), true);

        System.out.println("MFA password only: " +
            hasFreshMfa("user-42", now, List.of(password)));
        System.out.println("MFA password + passkey: " +
            hasFreshMfa("user-42", now, List.of(password, passkey)));
        System.out.println("MFA stale passkey: " +
            hasFreshMfa("user-42", now,
                List.of(password, stalePasskey)));

        store.issue("backup-A", "user-42",
            "RECOVERY", now.plusSeconds(600));
        System.out.println("Recovery weak: " +
            recover(store, "backup-A", "user-42", now, false));
        System.out.println("Recovery controlled: " +
            recover(store, "backup-A", "user-42", now, true));
        System.out.println("Recovery replay: " +
            recover(store, "backup-A", "user-42", now, true));
    }
}
```

Compile and run:

```bash
javac AuthExpiryReplayRecoveryDemo.java
java AuthExpiryReplayRecoveryDemo
```

**Exact** stdout:

```text
OTT first: true
OTT replay: false
OTT expired: false
OTT wrong purpose: false
Passkey wrong origin: false
Passkey valid: true
Passkey replay: false
Passkey without UV: false
MFA password only: false
MFA password + passkey: true
MFA stale passkey: false
Recovery weak: false
Recovery controlled: true
Recovery replay: false
```

**Why does it output this?**

- `OTT first` is true because the token matches user/purpose, `now < expiresAt`, and CAS flips `used=false → true`.
- `OTT replay` is false because the same `AtomicBoolean` is already true.
- `OTT expired` is false because `now==expiresAt`, failing the `isBefore` check.
- `OTT wrong purpose` is false even though the secret string exists; the `LOGIN_OTT` namespace is not accepted as `RECOVERY`.
- `Passkey wrong origin` is false because the verifier-reported origin is wrong; the test has not consumed the challenge.
- `Passkey valid` is true because all mocked flags hold and the challenge is consumed once.
- `Passkey replay` is false because the challenge is already consumed.
- `Passkey without UV` is false because policy requires user verification; the challenge is unconsumed, though if locking after failures is desired, add attempts/rate limiting.
- `MFA password only` is false because policy requires both `PASSWORD` and `PASSKEY`.
- `MFA password + passkey` is true under the **model of proofs from a trusted verifier**.
- `MFA stale passkey` is false because it exceeded the illustrative 300-second window.
- `Recovery weak` is false due to missing additional proof per simulated policy; the code remains unconsumed.
- `Recovery controlled` is true because the gate passes and the recovery secret is still valid.
- `Recovery replay` is false because the recovery code was already consumed.

### 10.1. Exact limitations of the demo

- `AtomicBoolean` is atomic only **within one JVM**; it does not prove safety across multiple replicas. Production uses database row updates/Redis Lua/transactions with shared state.
- `signatureVerified`, `originValid`, `rpIdValid`, and `userVerified` are **assumed** test inputs; they do not replace a WebAuthn library verifying real RP/challenge/origin signatures.
- `trustedVerifier` is also only a policy-test assumption and does not generate real proof from passwords/TOTP/ID Tokens.
- Session binding, password hashing, token hashing, rate limiting, CSRF, KeyStores, JWKS, and device lifecycles are absent from the example.
- `RECOVERY` is consumed only when additional mocked proof is present; a real system must select a concrete assurance/recovery workflow and limit post-recovery privileges.
- The 5-minute freshness duration is **an example**, not a Spring or NIST default constant.

## 11. Concurrency testing: catching bugs that appear only across multiple nodes

### 11.1. Do not test only two sequential calls

Two sequential `consume(token)` calls catch simple reuse bugs, yet miss races such as:

```text
Node A: SELECT used=false
Node B: SELECT used=false
Node A: grant session
Node B: grant session
Node A: UPDATE used=true
Node B: UPDATE used=true
```

A service using multiple replicas/caches must uphold the invariant **one token yields at most one authentication result** (per single-use policy). For WebAuthn, challenge/authentication state must also bind to a single ceremony and reject replayed old assertions.

### 11.2. Building a concurrency integration test

- Use **two separate clients/sessions** and the same OTT secret or backup code.
- Coordinate them at a barrier so both send POSTs simultaneously.
- Backend uses the **shared database** and transaction settings matching production.
- Count **successful** Authentication results produced and consumed rows after commit.
- Assert **at most one** (specifically one) request succeeds using the secret; the other is rejected.
- Repeat across multiple runs with fresh test fixtures; never let an already-authenticated session mask outcomes.
- Test network retries after commit, node death right before/after transaction commit, delayed cache invalidation, and clock skew.
- With multiple OTTs for the same user, test "newest only" policies or credential versions blocking old links after account changes.

A test using only an in-process `ConcurrentHashMap` proves only one kind of concurrency. If the product cluster has DB replication lag, session replication, and queues, integration tests are needed at those boundaries.

### 11.3. Atomic SQL consume for backup codes

PostgreSQL example, with a securely computed code hash:

```sql
UPDATE recovery_codes
SET consumed_at = now()
WHERE code_hash = :hash
  AND account_id = :accountId
  AND purpose = 'ACCOUNT_RECOVERY'
  AND consumed_at IS NULL
RETURNING id;
```

If the table has `expires_at`, add the time-window condition. This is an example for a custom recovery store; wrap state changes/authenticator registration in an appropriate transaction or explicit rollback/idempotency workflow so a code is not burned when recovery fails midway. Never create a full session from one successful SQL update while skipping remaining policy steps.

## 12. Testing anti-patterns

| Mistake | Why it causes a false positive | Fix |
|---|---|---|
| `@WithMockUser` then calling `/admin` and seeing 200 | Mock principal skips MFA/OTT/passkey verifiers | Use for authorization units; add real login integration |
| Mocking `OneTimeTokenService.consume` to always return user | Skips expiry/replay/DB checks | Test real service and negative cases |
| `with(jwt())` then concluding passkey login works | JWT fixture differs from WebAuthn ceremony | Test real signed assertions and WebAuthn flow |
| WebAuthn `signatureValid=true` from request body | Client self-attests signature | Real WebAuthn verifier, server-side expected RP config |
| Testing only unexpired OTT | Misses expiry boundary, replay, and wrong purpose | Test before/at/after expiry |
| `Thread.sleep(300_000)` to test TTL | Slow/flaky, imprecise at boundaries | Inject `Clock`/test seam |
| GET magic link also consumes | Email scanners drain tokens | GET landing does not consume; POST confirms |
| Passkey UV test checks only signature | A UP-only assertion could bypass step-up | Enforce UV per policy |
| Assuming passkey `signCount=0` is always forbidden | Synced passkeys vary in counter behavior | Risk-based counter policy and challenge replay protection |
| Treating Password + PIN as MFA | Same knowledge factor | Count verified independent factor types and provenance |
| Treating Password + email OTT as AAL2 automatically | Channel may depend on the same password | Review NIST/assurance; prefer phishing-resistant |
| Recovery requires only clicking "Skip MFA" | Attacker bypasses entire login | Account recovery policy with verified proof |
| Reusing backup codes | Allows repeated authenticator swaps | Atomic single-use + rate limit |
| Concurrency testing through one already-logged-in HTTP session | Session masks the second verifier path | Fresh sessions/cookies per request |
| Ignoring disabled accounts while token is unexpired | Valid token yet disallowed account | Check current account status at redemption |
| Mocking `AuthenticationManager` too | Filter runs without real verifiers | Include at least one test with real providers/keys/DB |
| Disabling CSRF to make tests easy | Fails to verify session POST security | Keep CSRF and write negative tests |
| Testing passkeys with another user's credentials | Ownership checks could be bypassed | DB credential→account mapping and tenant checks |
| Locking admin account while old sessions keep privileges | Revocation failed to propagate | Session/token versions/live checks and multi-node tests |

## 13. Ready-to-apply test coverage suite

### 13.1. OTT

```text
ottValidTokenAuthenticatesExactlyOnce()
ottTokenAtExpiryIsRejected()
ottTokenAfterExpiryIsRejected()
ottTokenWithWrongPurposeIsRejected()
ottTokenForDifferentAccountIsRejected()
ottTokenForDifferentTenantIsRejected()
ottReplayIsRejectedAfterSuccess()
ottParallelConsumeAcrossNodesAllowsAtMostOne()
ottGetLandingDoesNotConsumeToken()
ottLinkDoesNotUseUntrustedHostHeader()
ottWrongOrExpiredTokenDoesNotCreateSession()
ottAccountDisabledBetweenIssueAndConsumeIsRejected()
ottInvalidTokenCannotBeUsedAsPasswordResetToken()
```

### 13.2. WebAuthn/passkeys

```text
webauthnValidSignedAssertionAuthenticates()
webauthnWrongChallengeIsRejected()
webauthnExpiredChallengeIsRejected()
webauthnReplayedAssertionIsRejected()
webauthnWrongOriginIsRejected()
webauthnWrongRpIdIsRejected()
webauthnTamperedSignatureIsRejected()
webauthnWrongUserHandleIsRejected()
webauthnCredentialOwnerMismatchIsRejected()
webauthnUserPresenceRequiredIsEnforced()
webauthnUserVerificationRequiredIsEnforced()
webauthnRevokedCredentialCannotAuthenticate()
webauthnRegistrationRequiresStepUp()
webauthnDuplicateCredentialRegistrationIsRejected()
webauthnSyncedPasskeyCounterPolicyIsCorrect()
```

### 13.3. MFA and recovery

```text
passwordOnlyCannotAccessMfaProtectedResource()
twoKnowledgeFactorsDoNotSatisfyTwoFactorPolicy()
missingWebauthnFactorTriggersStepUp()
mfaFactorsFromDifferentUsersCannotBeCombined()
mfaFactorsFromDifferentSessionsCannotBeCombined()
mfaStaleFactorRequiresReauthentication()
passkeyUvMissingDoesNotSatisfyUvPolicy()
accountDisabledAfterMfaCannotAccessSensitiveResource()
oldRoleAfterRevocationDoesNotGrantPrivilege()
backupCodeCanBeRedeemedOnceOnly()
backupCodeWrongUserIsRejected()
backupCodeReplayedConcurrentIsRejected()
passwordResetCannotDisableMfaByItself()
lostAuthenticatorRequiresControlledRecovery()
recoveryCannotEnrollCredentialForDifferentAccount()
recoveryNotifiesAndInvalidatesLostCredential()
recoveryFailureDoesNotCreateAuthenticatedSession()
```

Every test must define **setup, real vs. fake evidence, action, assertions, and cleanup**. If using mocks only, test names should indicate *policy simulation* rather than claiming authentication integration certification.

## 14. Real-world operations: logging, UX, and security assurance

### 14.1. Logging enough to investigate without containing secrets

Log correlation IDs, verified user/tenant IDs, factor types, hashed challenge IDs or internal references, and reason codes such as `OTT_EXPIRED`, `WEBAUTHN_ORIGIN_MISMATCH`, `MFA_FACTOR_MISSING`, `RECOVERY_REPLAY`. Never log raw OTTs, recovery codes, WebAuthn private keys, TOTP seeds, bearer tokens, session cookies, enrollment QRs, or biometric data.

Clients need not see all internal reason codes; login errors should be clear enough for legitimate recovery without enumerating accounts or feeding attacker feedback. Apply audit access controls, retention, and privacy policies.

### 14.2. Friendly error UX that never fails open

- Expired OTT: inform the link is no longer usable; allow requesting a new link under rate limits.
- Already-used OTT: do not reveal where the user logged in; allow re-issuing links per policy.
- Passkey not found or user canceled: support retrying or using an enrolled backup authenticator.
- Passkey UV=false when UV is required: prompt the device to verify the user; **never** downgrade policy to UP-only.
- MFA missing factor: guide the next step without granting temporary sensitive access.
- Factor recovery: use a dedicated workflow, notify of changes, and allow reporting if unauthorized.
- Retries/network timeouts: maintain idempotency so one submission never becomes two authentication/registration grants.

### 14.3. Monitoring performance and preventing abuse

- OTT generation requests: rate-limit by IP/account/contact, preventing user enumeration and email flooding.
- OTT submission: limit secret guesses and detect anomalies; even with high token entropy, protect the endpoint.
- WebAuthn options: prevent challenge-generation floods, bound server-side challenge storage, and run TTL cleanup.
- WebAuthn verification: track signature failure rates and recovery policies without logging sensitive payloads.
- MFA push/TOTP: defend against push fatigue and brute force, keep time-drift windows tight, and block replay.
- Recovery/support: rate limits, risk scoring, workflow audits, approver controls, and notifications.
- Clock coordination: NTP/monotonic clocks/allowed skew rules per threat model; test drift across nodes.

## 15. Login QA completion checklist

1. **OTT:** right subject/purpose/TTL, CSPRNG, hashed store/atomic consume, replay, multi-node races, email scanners, and GET/POST.
2. **Passkeys:** real signed assertions, single-use/expiring/session-bound challenges, origin/RP ID, credential ownership, UP/UV, revoked credentials, and registration.
3. **MFA:** right count of independent factor **types**, freshness, user/session binding, step-up, resource authorization, and no fail-open.
4. **Recovery:** single-use backup codes, sufficiently assured enrollment, no MFA disablement from password reset, audited support workflows, and notifications.
5. **Sessions:** logout, session fixation, account disablement/role revocation, cookie protections, and session version checks.
6. **Do not mistake mocks:** `@WithMockUser`/`jwt()`/`signatureVerified=true` are not cryptographic integration tests.
7. **Clock tests:** before, at, and after expiry without `sleep`; check skew/network time across nodes.
8. **Concurrency tests:** two sessions/nodes submitting the same token/code simultaneously, asserting at most one succeeds.
9. **CSRF:** enforced on forms/registration options and session-based POSTs per config, never globally disabled.
10. **MFA versioning:** Spring Security 6.5 has OTT/WebAuthn; Spring Security 7 adds factor authorities/MFA DSL; verify matching dependencies/APIs.
11. **Fail closed:** database/verification service outages or queue downtime never auto-grant Authentication or skip factors.
12. **End-to-end:** with IdP, browser, and virtual/hardware authenticators under production-like proxy/cookie policies.
13. **Layered coverage reporting:** separate policy/unit, store/concurrency, Spring filters, cryptographic verification, and E2E.
14. **Preserving evidence:** redacted test artifacts, structured assertions, and audit/event IDs traceable without storing production secrets.

## 16. Self-check questions

**Q1.** OTT succeeded once yet the second attempt still returns 200 because the old HTTP session is logged in. Does the test prove replay safety?  
**A:** No. You must use a **fresh session**/second client, send the exact raw OTT, and verify the verifier/store rejects reuse without the prior logged-in session masking the outcome.

**Q2.** When `now == expiresAt`, is a token valid?  
**A:** Under `now < expiresAt` policy, **no**. Tests must match the contract and hit the exact boundary.

**Q3.** A WebAuthn assertion has a valid signature yet `origin` differs from the configured origin. Should login proceed?  
**A:** No. Verify origin/RP ID/challenge alongside the signature; a valid signature alone is insufficient.

**Q4.** WebAuthn has UP=true, UV=false, yet the endpoint requires user verification. Result?  
**A:** Rejected per policy; never silently downgrade assurance.

**Q5.** `@WithMockUser` lets a call to an MFA-protected endpoint return 200. Does this prove the user passed real MFA?  
**A:** No. That is a mocked principal; real factor issuance/verification must be tested at another layer.

**Q6.** Enabling `formLogin()`, `oneTimeTokenLogin()`, and `webAuthn()` together in Spring Security 6.5 automatically requires all three, right?  
**A:** No. They can act as separate login methods; policies requiring multiple factors must be configured/enforced separately. Spring Security 7 adds the MFA factor-authorities DSL.

**Q7.** Can a valid recovery code that was already used earlier enroll a new passkey?  
**A:** No. Backup codes are single-use; the store must block replays atomically and re-enrollment has its own conditions.

**Q8.** Why is `signCount=0` not proof of a cloned credential on its own?  
**A:** Authenticators and synced passkeys manage counters differently; apply risk policies and appropriate verifiers rather than a universal "zero = clone" rule.

**Q9.** Does someone with password + email OTT automatically reach AAL2?  
**A:** No. MFA assurance requires evaluating authenticator type/channel/independence and all NIST controls; NIST 800-63B-4 disallows email as an OOB authenticator.

**Q10.** What guarantees a token cannot be used twice across a three-node cluster?  
**A:** Shared token state, atomic consume in the database/Redis, transactions, and tests verified with concurrent distinct clients. `AtomicBoolean` in a single JVM is not enough.

## References

- [Spring Security 6.5 – One-Time Token Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/onetimetoken.html): DSL, generate/submit flow, token service, custom TTL, and delivery handler.
- [Spring Security 6.5 – Passkeys/WebAuthn](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passkeys.html): registration/options, authentication/options, credential repositories, RP ID, and allowed origins.
- [Spring Security 7 – Multi-Factor Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/mfa.html): `FactorGrantedAuthority`, `@EnableMultiFactorAuthentication`, conditional MFA, and required factors.
- [Spring Security – Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html): MockMvc, `@WithMockUser`, test configuration.
- [W3C WebAuthn Level 3](https://www.w3.org/TR/webauthn-3/): challenge, RP ID, origin, UP/UV, assertion verification, and signature counters.
- [NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b.html): replay, phishing resistance, recovery, and authenticator binding.
- [OWASP Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html): MFA independence, account recovery, resets, enrollment, and risk.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): login security, reauthentication, account enumeration, and lockout.

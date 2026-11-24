# Integrating TOTP or HOTP: What Libraries Support vs. What Your Application Must Build

> **Scope:** Building a second-factor authentication layer based on OTP codes from an authenticator app in a Spring Security system. The focus is distinguishing **the TOTP/HOTP algorithm a library can compute** from **the MFA lifecycle, account state, authorization decisions, anti-replay, and operational workflows the application must design**. Examples use Java 17+, Spring Boot 3.x / Spring Security 6.x for custom integration; Spring Security 7.x's MFA/one-time-token capabilities are also pointed out without confusing them with the TOTP/HOTP standards.

## 1. Why “Already Having an OTP Library” Does Not Give You Complete MFA

A TOTP/HOTP calculation library answers a narrow question:

> “Given secret K, time or counter C, and algorithm configuration, what is the expected 6–8 digit string?”

A real login system must answer many other questions:

- Who **already authenticated via the first factor**, and whose account's MFA challenge are they completing?
- Which exact **device/factor** does the secret belong to? Have enrollment and proof of possession been confirmed?
- Is the OTP **unexpired, within the allowed window, and not previously consumed successfully**?
- Have attempts been exceeded, is there a temporary lock, is MFA being reset, has the device been revoked, or is the account locked?
- Upon successful verification, how will Spring Security represent **both factors** in the session / security context?
- If the OTP is valid but the database or cache fails while committing anti-replay state, can login be considered successful? **No**.
- If the user requests a device change, loses their authenticator, loses their session, or logs in across multiple tabs, what is the safe workflow?

**Boundary of responsibility:** A correct algorithm is necessary but insufficient. The library handles *cryptography and code comparison*; Spring Security provides the *authentication and access-control framework*; the application must bridge the two with *state machines, persistence, transactions, policies, and testing*.

## 2. How Does TOTP Differ from HOTP?

| Characteristic | HOTP — RFC 4226 | TOTP — RFC 6238 |
| --- | --- | --- |
| Moving factor | Event counter C, incremented when generating/using codes | Time step T computed from Unix time |
| Formula | `HOTP(K,C) = Truncate(HMAC(K,C)) mod 10^Digits` | `TOTP(K,t) = HOTP(K,floor((t - T0)/X))` |
| Synchronization | Server must track next counter, may need look-ahead | Server and device need relatively synchronized clocks |
| Usage window | Does not expire by clock alone; valid within accepted counter sequence | Typically 30 seconds/step; small sliding window for clock drift |
| Anti-replay | Advance used counter with an **atomic** update | Store **last accepted time step** (or equivalent) with atomic update |
| Deployment capability | Hardware device or token increments counter on generation | Common in smartphone authenticator apps |
| Parameters to align | Secret, HMAC algorithm, digit count, initial counter | Secret, HMAC algorithm, digit count, period X, T0 |

Both use a **shared secret** between authenticator and server; neither is asymmetric cryptography. For most authenticator apps, the common configuration is **HMAC-SHA1, 6 digits, 30-second period**; however, RFC 6238 allows HMAC-SHA256/512 and other configurations. Never unilaterally change the algorithm or digit count if users' devices do not support it.

**Do not confuse the two:** “OTP” here means a numeric code computed by an authenticator from a secret. “One-Time Token Login” (OTT) provided by Spring Security is a server-issued token mechanism typically sent via magic link/email/SMS; **`oneTimeTokenLogin()` does not implement TOTP/HOTP or QR enrollment with an authenticator app**.

### Why Does a Six-Digit Code Require Attempt Controls?

A 6-digit code has roughly one million possibilities. If the server accepts 3 TOTP steps simultaneously, one random guess roughly has a chance of matching one of three codes. Widening steps, leaving attempts unlimited, and allowing multiple IPs to guess against the same account undermines MFA. Therefore, enforce rate limits per account/factor/challenge, backoff, telemetry, and recoverable lockout policies; **never rely solely on the 30-second window**.

## 3. What Libraries Support vs. What the Application Owns

| Task | What a Standard OTP Library Can Do | What the Application / Spring Security Owns |
| --- | --- | --- |
| Generate HOTP/TOTP codes | HMAC, dynamic truncation, zero-padding | Choosing compatible settings and test vectors |
| Verify code against moving factor | Compare code at given counter/step; may support validation window | Defining window bounds, rate limits, and anti-replay commit |
| Generate new secret | Some libraries include CSPRNG helpers | Per-factor secret, entropy, encrypted storage, and lifecycle |
| Base32, `otpauth://`, and QR | Libraries may support string/QR encoding | Enrollment UX, CSRF, secure one-time QR display, possession confirmation |
| OTP during device change | Only computes/verifies codes | Reauthentication, factor swap, revoking old secret, auditing |
| Retries, HOTP resync | Some libraries support look-ahead | Bounded look-ahead, counter transactions, and anti-manipulation |
| Accounts, sessions, authorization | **No** | Spring `Authentication`, filter chains, route policies, step-up |
| Recovery codes and lost-device support | Usually not | Random generation, hashing, consume once, recovery flows |
| TOTP replay across instances | Pure verify functions are insufficient | Shared store + atomic compare-and-set or row locks |
| Post-MFA session elevation | **No** | Upgrading SecurityContext/session or tokens with clear assurance |
| Secret encryption, KMS, key rotation | OTP libraries may not provide this | Encryption-at-rest, ACLs, auditing, secure backup/restore |
| Telemetry/incident response | **No** | Tracking failures, abuse, policy resets, recovery, and monitoring |

**Choose a library by its concrete contract**, not just the word “OTP”: does it support RFC standards and test vectors, SHA1/256/512 with proper config, 6/8 digits, Base32, provisioning URIs, windows, invalid input handling, clock injection, error handling, active maintenance/dependency hygiene, and security review? A library claiming “TOTP MFA” still will not store pending factors, manage sessions, or handle revocation for you.

## 4. What Does the Spring Security Library Do?

### Spring Security 6.x / Spring Boot 3.x

Spring Security provides key building blocks:

- `AuthenticationManager` and `AuthenticationProvider` for the authentication process.
- `Authentication`/`GrantedAuthority` to represent identity and granted access levels.
- `SecurityContextHolder` and `SecurityContextRepository` for Servlet/session authentication context.
- `SecurityFilterChain`, `AuthorizationManager`, `AuthenticationEntryPoint`, and success/failure handlers to build protection boundaries.
- `formLogin`, OAuth2 Login, LDAP, or other authentication mechanisms to handle the first factor.

**What Spring does not automatically do for custom TOTP/HOTP apps:** generate and store per-user secrets, output provisioning QR codes, confirm enrollment, check each time step/counter, block reused codes, apply per-factor rate limiting, handle recovery/reset, and upgrade the session after verification.

One integration pattern is a **custom authentication provider/filter/service** for OTP, keeping “password passed” and “MFA passed” as two distinct states. Never add a `FACTOR_TOTP` authority based on a request parameter, role name, or a “user has MFA enabled” column in the DB; this authority must only be granted **after the server genuinely verifies the OTP and commits anti-replay state**.

### Spring Security 7.x and Newer MFA Documentation

Spring Security 7.x introduces **`FactorGrantedAuthority`**, multi-factor requirement policies, and `@EnableMultiFactorAuthentication`. This is a mechanism for **coordinating already-authenticated factors**—it does not mean Spring ships a default TOTP authenticator-app verifier. Documentation samples typically pair password with **OTT** (`FACTOR_OTT`); the framework's OTT differs from RFC TOTP/HOTP. When using custom TOTP, integrate verified factor evidence into the authentication/authorization mechanism of your exact Spring version. **Do not** copy `FACTOR_OTT` to mark TOTP if you are not using the framework's expected OTT mechanism.

Spring Security 6.x and 7.x differ in APIs/DSL. Before copying snippets from the internet, check the exact dependency version managed by your BOM. The Java examples below use general Spring Security 6 Servlet APIs, keeping OTP verification separated from the authentication framework.

### Authentication Differs from MFA Authorization

- **Authentication (factor 1):** the user entered a valid password or holds an IdP-verified OIDC session. This does not automatically satisfy the application's MFA policy.
- **MFA challenge:** grants minimal access to enrollment/challenge screens; must not access resources requiring two factors.
- **MFA success:** the OTP for the right factor is verified and anti-replay committed atomically; only then is evidence recorded into the session/security context.
- **Authorization:** every sensitive URL/API must verify sufficient factors. Checking only on the login page or only in frontend menus is insufficient.

If login went through an OIDC IdP that already performed MFA, the application should prefer relying on **`acr`/`amr` or an IdP-verified authentication assurance contract** rather than needlessly forcing the user to enter TOTP a second time. Never trust a browser-sent `amr` string or unverified claims.

## 5. Formulas and Verification Windows

Given secret `K` and counter `C`:

~~~text
H = HMAC-SHA1(K, big_endian_8_byte(C))
offset = H[last_byte] & 0x0F
binary = DT(H, offset) & 0x7FFFFFFF
HOTP = binary mod 10^digits
~~~

Dynamic truncation (DT) picks four consecutive bytes from the HMAC at `offset` and extracts 31 positive bits. When formatting as a string, **left zero-pad** to 6 or 8 digits; for example, `07081804` must preserve the leading zero—never store it as an integer that loses formatting.

For TOTP:

~~~text
timeStep = floor((UnixSeconds(now) - T0) / periodSeconds)
TOTP(K, now) = HOTP(K, timeStep)
T0 = 0, periodSeconds = 30 are common values per RFC 6238
~~~

With 30 seconds/step and a policy accepting current step ±1, verification checks **at most three steps**. The window only tolerates clock skew and transmission delay; never widen it arbitrarily. A larger time step keeps codes valid longer and increases the window in which an attacker can reuse a leaked code.

**Key requirement of RFC 6238:** Even if a TOTP code is still within the same step, the validator **must not accept it a second time after the first successful verification**. Simply comparing HMACs and returning true violates the “one-time” property on retries or concurrent requests hitting two nodes.

## 6. Standalone Java 17: HOTP/TOTP Matching RFC Test Vectors

This example computes only the **cryptographic algorithm**; it does not implement enrollment, secret storage, login, or MFA state. It uses JDK 17 `javax.crypto.Mac`, `ByteBuffer`, and `Instant`; the fixed test secret is **for testing only** and must never be used to issue keys for real users.

File `OtpRfcDemo.java`:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.time.Instant;
import java.util.Locale;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class OtpRfcDemo {
    private OtpRfcDemo() {
    }

    static String hotp(byte[] secret, long counter, int digits)
            throws GeneralSecurityException {
        if (secret == null || secret.length == 0 || counter < 0
                || digits < 6 || digits > 8) {
            throw new IllegalArgumentException("Invalid HOTP parameters");
        }

        byte[] message = ByteBuffer.allocate(Long.BYTES)
                .putLong(counter)
                .array();

        Mac mac = Mac.getInstance("HmacSHA1");
        mac.init(new SecretKeySpec(secret, "HmacSHA1"));
        byte[] hmac = mac.doFinal(message);

        int offset = hmac[hmac.length - 1] & 0x0f;
        int binary = ((hmac[offset] & 0x7f) << 24)
                | ((hmac[offset + 1] & 0xff) << 16)
                | ((hmac[offset + 2] & 0xff) << 8)
                | (hmac[offset + 3] & 0xff);

        int modulus = 1;
        for (int i = 0; i < digits; i++) {
            modulus *= 10;
        }
        return String.format(Locale.ROOT,
                "%0" + digits + "d", binary % modulus);
    }

    static String totp(byte[] secret, Instant time, int digits,
            int periodSeconds) throws GeneralSecurityException {
        if (periodSeconds <= 0 || time == null) {
            throw new IllegalArgumentException("Invalid TOTP parameters");
        }
        long step = Math.floorDiv(time.getEpochSecond(), periodSeconds);
        return hotp(secret, step, digits);
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        byte[] secret = "12345678901234567890"
                .getBytes(StandardCharsets.US_ASCII);

        System.out.println("HOTP C=0: " + hotp(secret, 0, 6));
        System.out.println("HOTP C=1: " + hotp(secret, 1, 6));
        System.out.println("HOTP C=2: " + hotp(secret, 2, 6));

        System.out.println("TOTP t=59: " +
                totp(secret, Instant.ofEpochSecond(59), 8, 30));
        System.out.println("TOTP t=1111111109: " +
                totp(secret, Instant.ofEpochSecond(1111111109L), 8, 30));
    }
}
~~~

Run with JDK 17+:

~~~bash
javac OtpRfcDemo.java
java OtpRfcDemo
~~~

Exact stdout matching RFC 4226 / RFC 6238 HMAC-SHA1 test vectors:

~~~text
HOTP C=0: 755224
HOTP C=1: 287082
HOTP C=2: 359152
TOTP t=59: 94287082
TOTP t=1111111109: 07081804
~~~

**Why use 8 digits in the TOTP test?** RFC 6238 publishes 8-digit test vectors to verify the algorithm; real authenticators may be configured for 6 digits. Choose digit count and HMAC matching the enrollment configuration.

**Code limitations:** `hotp/totp` does not check a user's candidate code, has no clock-skew window, counter commit, anti-replay, or account lockout. It is a **code generator for algorithm testing**, not a secure MFA verifier. The fixed RFC secret is **public test-vector data** and must never be used in production. When generating real secrets, use a dedicated CSPRNG per user/factor; when storing, use encryption with key management.

## 7. Factor State and Data Model the Application Must Build

Each user may have one or more factors. User records and factor records should be separated:

| Suggested Column | Purpose |
| --- | --- |
| `factor_id`, `user_id` | Factor belongs to the exact account verified in the previous step |
| `type` | `TOTP` or `HOTP`; never interchange arbitrarily |
| `status` | `PENDING`, `ACTIVE`, `DISABLED`/`REVOKED` |
| `secret_ciphertext` | **Encrypted secret**, never plaintext or hash-only |
| `secret_key_version` | KMS/KEK key version to read and rotate encryption |
| `algorithm`, `digits` | E.g., `HmacSHA1`, 6 or 8 digits |
| `period_seconds`/`t0` | TOTP only; e.g., 30 seconds / 0 |
| `last_accepted_step` | TOTP anti-replay, updated atomically |
| `next_counter` | HOTP tracking of consumed counters |
| `created_at`, `confirmed_at` | Enrollment audit |
| `revoked_at`, `revision` | Revocation, optimistic locking, and excluding stale requests |
| `failed_attempts`, `locked_until` | Rate-limiting rules (may live in a separate store) |
| `device_label` | User-chosen label, not security evidence |

**Why not hash the TOTP seed?** To verify TOTP/HOTP for a new counter/step, the server must compute HMAC using the **original secret** (or via a service that securely holds/decrypts the secret). A one-way hash like a password hash does not provide the input needed for OTP computation. You must **encrypt the seed at rest** (e.g., envelope encryption with KMS/HSM, AEAD such as AES-GCM), grant least-privilege decrypt access, audit/rotate/back up safely, and never log seeds.

Each factor needs its own secret from `SecureRandom`. For HMAC-SHA1, a 20-byte random seed (160 bits) is a common compatible choice; some authenticators have different rules. Never share a seed across multiple users, derive seeds from username/email, use `Random`, or hardcode seeds in config. Test actual provisioning across target authenticator apps.

### QR Codes Contain a Secret, Not a Harmless Image

A provisioning URI typically looks like:

~~~text
otpauth://totp/ExampleApp%3Auser%40example.test
  ?secret=BASE32_RANDOM_SECRET
  &issuer=ExampleApp
  &algorithm=SHA1
  &digits=6
  &period=30
~~~

The snippet above is **wrapped only for readability**; the real URI must be on a single line and properly URL-encoded. `BASE32_RANDOM_SECRET` is an illustrative placeholder. For HOTP, use `otpauth://hotp/...` with `counter=...` instead of `period`, and confirm target authenticator apps actually support HOTP.

Use a trusted Base32/QR library to build the URI, URL-encode labels/issuers, and render the QR code. **The QR code is a long-lived secret**: display it only inside the enrollment session over HTTPS with `Cache-Control: no-store`, and never place it in external URLs, logs, analytics, error reports, support ticket screenshots, or CDN logs. Never return the secret from a “view QR again” API once the factor is active. If the user needs a new device, run a secure factor add/change flow.

## 8. Two-Phase Enrollment: Do Not Activate Immediately When Showing QR

A minimal safe flow:

1. The user authenticated via the first factor and requests adding TOTP/HOTP. For changing security methods, require **fresh reauthentication** or an existing factor per policy; never rely solely on an old session cookie.
2. The server generates a random seed **per factor**, stores it encrypted in `PENDING` state, bound to `user_id` from the current authentication. Generate the corresponding QR/URI and return it over a TLS-protected, `no-store` session.
3. The user scans with their authenticator app; the app displays an OTP. The server **does not yet** consider this factor active and does not accept it to satisfy MFA requirements.
4. The user submits a confirmation code. The server verifies the OTP belongs to **that exact pending factor of the authenticated user**, enforces rate limits and session binding, and applies an enrollment expiration.
5. Only if code verification and transaction succeed does it transition `PENDING -> ACTIVE`, record `confirmed_at`, update `last_accepted_step`/`next_counter` (so the confirmation code cannot be reused either), and emit an audit event.
6. Allow the user to retrieve/save recovery codes over a secure channel if policy allows; store recovery codes hashed and show raw codes once.
7. Notify of the factor addition over a channel external to the modified session (e.g., notification email), while providing a reporting path not controlled by an attacker.

**Do not** treat opening the QR page as proof the user installed the app. Never let the user set `ACTIVE` status via request JSON. Never let user A confirm user B's secret by changing `userId`/`factorId` on the endpoint. Do not automatically grant a full-MFA session immediately upon enrollment if product rules require a fresh challenge; distinguish clearly between “added a factor” and “used a factor to upgrade the session”.

Example state transitions:

~~~text
NOT_ENROLLED
    |
    | start enrollment after first factor + fresh reauth
    v
PENDING --(valid OTP, transaction succeeds)--> ACTIVE
    |                                         |
    +-- timeout/cancel --> DELETED             +-- lost/replace --> REVOKED
                                              |
                                              +-- new factor -> PENDING -> ACTIVE
~~~

Deleting/changing a factor after MFA is enabled must have dedicated access control, history, and alerts. A pending factor may expire and be deleted without affecting login via another active factor.

## 9. Verifying TOTP and Anti-Replay — Not Just Comparing Codes

At the MFA challenge, the server already knows the user from the **first factor**; never take `userId` from an arbitrary parameter. After loading the user's `ACTIVE` factors, decrypt the seed in a restricted scope and select the policy window.

**Conceptual algorithm**:

~~~text
authenticatedUser = firstFactorContext.principal
factor = loadActiveFactorFor(authenticatedUser)
assert not locked + allowedAttempts

stepNow = floor(Clock.now().epochSeconds / periodSeconds)
candidates = [stepNow - 1, stepNow, stepNow + 1]   # small window example

for step in candidates:
    if step < 0: continue
    if constantTimeEqual(hotp(secret, step), submittedOtp):
        BEGIN TRANSACTION
        UPDATE factor
            SET last_accepted_step = step
            WHERE factor_id = expectedFactor
              AND user_id = authenticatedUser
              AND status = ACTIVE
              AND revision = expectedRevision
              AND (last_accepted_step IS NULL OR last_accepted_step < step)
        IF exactly one row changed:
            COMMIT
            record verified MFA for this session
            return SUCCESS
        ROLLBACK
        return REPLAY_OR_STALE
return INVALID_OTP
~~~

The pseudocode above is not complete Java/SQL. Because the same numeric value can occasionally repeat across multiple steps (rare but possible), the implementation must define **step-selection order and single-use rules**; never let the same OTP be reused by trying another step after one has already succeeded. For strict applications, additionally store a time-scoped fingerprint/consumed-code value per factor or an explicit step-selection policy to prevent collision edge cases. Transactions/locks must handle two concurrent requests across two instances.

**Time monotonicity:** `last_accepted_step` must increase monotonically; never accept a step earlier than or equal to an already-succeeded step. Handle clock skew with NTP sync and a small window, never opening ±10 steps arbitrarily. For 6-digit codes, preserve zero-padding; only accept strings with exact length/digit characters—never parse to an integer and lose leading zeros.

**Brute-force protection:** rate-limit by account + factor + challenge/session, plus IP/device signals and alerts. Never permanently lock an account just because an attacker spams 6-digit guesses; delay/lockout policies must consider both DoS and recovery. If the backend cannot read/write anti-replay state, **do not** mark MFA as succeeded.

## 10. HOTP Verification: Counters and Resynchronization

HOTP does not depend on Unix time. The server stores `next_counter` (the next accepted counter) and verifies within a bounded counter window, e.g., `[nextCounter, nextCounter+5]` per policy.

If the user presses generate multiple times on a hardware token before entering a code, the device counter can advance ahead of the server. Look-ahead enables resync, but a wide window expands guessing space and must be rate-limited.

~~~text
expectedStart = factor.next_counter

for counter in [expectedStart .. expectedStart + allowedLookAhead]:
    if constantTimeEqual(hotp(secret, counter), submittedOtp):
        BEGIN TRANSACTION
        UPDATE factor
          SET next_counter = counter + 1
          WHERE factor_id = thisFactor
            AND status = ACTIVE
            AND next_counter = expectedStart
        IF exactly one row:
            COMMIT
            return SUCCESS
        ROLLBACK
        return CONCURRENT_OR_REPLAY
return INVALID_OTP
~~~

**Never increment the counter unconditionally on a wrong code**; that can desynchronize device/server indefinitely or cause DoS. For large resynchronizations, apply a stronger process (some systems require two consecutive codes, possession verification, and auditing), never an unbounded window. Every counter update must commit atomically in a shared store; updating an in-memory variable on one pod is insufficient.

A valid HOTP at counter `C` ensures subsequent attempts may only use counters **greater than `C`**, preventing replay of old tokens. As with TOTP, if the code matches but committing `next_counter` fails, **do not** upgrade the session.

## 11. Binding MFA into Spring Security Servlet

The example below illustrates the **authorization boundary**: after username/password, the user can only access MFA screens; all other routes require a custom `FACTOR_TOTP` authority. This name is application-defined for **Spring Security 6.x**, not automatically issued by Spring. With HOTP, the factor name could be `FACTOR_HOTP` or a designed policy marker; never hardcode a marker requested by the user.

File `MfaBoundaryConfig.java` — a configuration snippet for a Spring Boot application that already has the required security dependencies:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MfaBoundaryConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/error", "/assets/**")
                        .permitAll()
                        .requestMatchers("/mfa/challenge",
                                "/mfa/verify",
                                "/mfa/enroll/**")
                        .authenticated()
                        .anyRequest()
                        .hasAuthority("FACTOR_TOTP"))
                .formLogin(form -> form
                        .successHandler((request, response, authentication) ->
                                response.sendRedirect(
                                        request.getContextPath() + "/mfa/challenge")))
                .build();
    }
}
~~~

With real HTTP requests, the filter chain must have a login form/user store and application-built MVC endpoints `/mfa/challenge`, `/mfa/verify`, and `/mfa/enroll/**`. They are **not** automatically provided by this snippet. The form success handler only sends the user to the challenge; it does not grant `FACTOR_TOTP`.

**Especially important:** `.authenticated()` on `/mfa/**` endpoints only proves the user passed the first factor under the current mechanism; operations to **register/change/revoke** factors require **fresh reauthentication and stronger policy**, verifying CSRF on POST and ownership—never letting any stale first-factor-only session swap the seed. If public endpoints must be reachable before MFA, list and risk-assess them explicitly rather than appending `.anyRequest().authenticated()` later, which could expose sensitive APIs behind password-only access.

Once the OTP is verified **and atomic anti-replay state has committed**, the application must:

1. Identify the user/factor from the first-factor context and trusted store, never from a `userId` submitted in the form.
2. Create or update MFA evidence for the **exact session** (e.g., a custom verified `Authentication` carrying `FACTOR_TOTP`); never fake `isAuthenticated=true` from an `otpVerified` parameter.
3. Persist `SecurityContext` using the proper persistence mechanism (such as `SecurityContextRepository.saveContext` on Servlet), ensuring session fixation protection and MFA proof expiration.
4. Safely redirect to the saved request **after** all factors are satisfied; never use an external client-supplied redirect URL.
5. Keep sufficient logs/audits to prove challenge completion without logging OTPs, seeds, or session tokens.

The OTP verification/authority-issuance code is not presented as a “paste and run” snippet: it necessarily depends on your transaction store, factor policy, challenge session, and application security. In Spring Security 7, when using `FactorGrantedAuthority` and built-in MFA policies, integrate verified TOTP/HOTP as a factor matching that version's contract rather than creating markers with mismatched semantics.

### Why Not Just Use a Session Variable `mfa=true`?

A manually set attribute can bypass Spring context, lack clear expiration/scope, and risk restoration from an old session. If using session state, verify it via authorization managers on every route, binding exact user, timestamp, factor type, challenge ID, session ID, and factor state revision; enforce invalidation on logout, password change, MFA reset, or factor revocation. Markers/authorities in Spring need those same controls, not just a boolean flag.

## 12. Error Classification and Avoiding Bypass Paths

| Scenario | Safe Decision | Notes |
| --- | --- | --- |
| First factor not completed | Deny MFA verify or protected resources | Route to appropriate login flow |
| Missing/malformed/wrong OTP | Do not elevate MFA; return generic error | Log error category, never log OTP |
| Valid TOTP already consumed in step | Reject replay | Never widen window to “fix” it |
| Valid HOTP but counter update lost race | Reject or re-challenge per policy | Never treat as success when transaction fails |
| User not enrolled or factor revoked | Do not elevate MFA | Dedicated setup/recovery flow |
| Rate limit exceeded | Return 429 or appropriate backoff | Mitigate brute force and DoS |
| DB/KMS/secret store unavailable | Service error, fail closed | Never treat outage as wrong OTP and never skip MFA |
| Right password, wrong OTP | Only first factor succeeded | Never grant access to protected resources |
| Right OTP, but first-factor session switched user/logged out | Reject; never mix evidence of two users | Bind challenge to session/principal/revision |
| Passed MFA, missing `ROLE_ADMIN` | 403, do not grant admin role | MFA != business authorization |

**Never add a fallback “if the MFA service errors, let users through to preserve uptime”.** When MFA is required, losing the ability to verify/record anti-replay means the requirement cannot be satisfied. Depending on the environment, infrastructure failures may return 503 while wrong codes get a generic error, yet neither yields a full session.

## 13. Recovery, Reset, and Device Replacement — What Your App Must Build

When a user loses their phone/HOTP token, they need a recovery workflow. This is attacked even more often than the OTP algorithm itself.

**Recovery codes** should be generated independently with a CSPRNG, with sufficient entropy, and displayed only once; store them in the DB with a **salted hash/KDF suitable for secrets** and an `unused/used` state. When a code is used, **consume it atomically** so it cannot be reused across two instances. Recovery codes often have lower entropy than 256-bit API tokens, so apply rate limits, proper hashing, password-grade secrecy, and never log them.

**Changing/adding factors:** Require recent reauthentication with an independent factor, or an already-enrolled factor per policy. When replacing a phone, do not immediately delete the old factor until the new device is verified if policy requires continuity; however, when a device compromise is reported, revoke immediately and recover via strong identity verification. Send notifications outside the modified session and consider delays/extra challenges under high risk.

**Forgot both password and MFA:** An improperly protected recovery email can become a single point of takeover; design a threat model, identity-verified support workflows, logging, alerts, and frequency limits. Never expose old seeds via a “view again” feature or allow support staff to read plaintext seeds.

**Existing sessions:** Resetting MFA may require invalidating prior full-MFA sessions or forcing re-step-up per policy. When removing a factor, every session holding evidence of that factor must be re-evaluated; if `FACTOR_TOTP` sits indefinitely in a session, a user could retain access after the device was revoked. Use factor revisions, auth-time/expiry, or event invalidation when fast revocation is required.

## 14. Threat Model: Does TOTP/HOTP Resist Phishing?

TOTP/HOTP raises the bar when an attacker **only** knows the password, yet remains vulnerable to:

- **Real-time phishing / reverse proxy:** an attacker tricks the user into entering the current OTP and uses it immediately within the validity window.
- **Malware / screen capture** stealing OTPs or enrollment QR codes containing the seed.
- **SIM/social recovery attacks** if recovery workflows are weak and rely on low-trust recovery channels.
- **Online brute force** if attempt limits are missing and the window is too wide.
- **Session hijacking** after the user completes MFA: the attacker reuses the cookie/session without needing any new OTP.
- **Multi-node replay/race** if code comparison happens without committing state.
- **Seed compromise** if the DB stores plaintext or KMS keys/secret management are breached.

**Do not treat TOTP as phishing-resistant.** When strong anti-phishing protection is required, consider FIDO2/WebAuthn/passkeys or origin-bound authentication methods per organizational policy. If the organization uses an OIDC IdP with MFA, evaluate using verified `acr`/`amr` claims rather than re-implementing an MFA flow inside every microservice.

## 15. Mandatory Testing: Algorithm vs. Transactions and Application

### A. Algorithm / Library Unit Tests

- RFC 4226 test vectors: C=0/1/2 for 6 digits return `755224`/`287082`/`359152`.
- RFC 6238 test vectors SHA1/30s/8 digits: t=59 returns `94287082`, t=1111111109 returns `07081804`.
- Values with leading zeros preserve 6/8 digits.
- Negative codes/empty strings/non-digit characters, wrong period/digits/algorithm are rejected; null seeds and out-of-range times never cause the app to grant access.
- Verify SHA256/512 if configured and supported by the actual library; test provisioning with real target authenticator apps.

### B. State and Concurrency

- Unconfirmed enrollment remains `PENDING`; valid OTP transitions to `ACTIVE` only after commit; confirmation code cannot be reused.
- Valid OTP for user A cannot verify a challenge belonging to user B, a switched session, or a stale factor revision.
- Two requests with the same TOTP/same step hitting two nodes: only **one** transaction updates `last_accepted_step` successfully.
- Successful HOTP look-ahead updates `next_counter=matched+1`; old codes are rejected; two requests for the same counter cannot both succeed.
- Clock skew ±1 step accepted per policy; outside window rejected; never default to ±10 steps.
- Rate limits per account/factor/challenge operate across instances; an account is not permanently locked out by one spamming IP.
- Seeds encrypted at rest; DB dumps expose no plaintext; QR codes never enter logs, caches, referrers, or analytics.
- KMS/DB outage: no false MFA success, no role or session granted; error category audited clearly.

### C. Spring Security Integration Tests

| Scenario | Expected Outcome |
| --- | --- |
| Unauthenticated, accesses protected resource | Requires first-factor authentication |
| Right password, no TOTP | Allowed only on challenge/enrollment routes; protected routes blocked |
| Right password, right TOTP, state commit succeeds | Session holds second-factor evidence and appropriate access |
| Wrong OTP or replay in same 30-second step | Session is not elevated |
| Valid OTP for different user or different challenge session | MFA is not elevated |
| User passed MFA but lacks business role | 403 on role-protected resource |
| Factor changed, logout, session expires | Old MFA state invalidated per policy |
| Factor reset/revoked while old session open | Session re-evaluated per revocation requirement |
| Failed attempts exceed threshold | Rate limit/backoff/lockout per policy |
| Store outage between OTP match and CAS update | No authenticated full-MFA state |
| Login via OIDC/passkey/remember-me outside password flow | Cannot bypass requirement; factor evidence comes from right source |

For Servlet apps, use `MockMvc` and test with real sessions/cookies where possible. For WebFlux, use `WebTestClient` and `ReactiveSecurityContextHolder`, avoiding blocking KMS/DB calls on the event loop. Test request/authorization state, not just unit-testing the `totp(...)` function.

## 16. Implementation Architecture Pattern

Four layers can be separated:

~~~text
HTTP Controller / Security FilterChain
         |
         v
MfaChallengeService  [bound principal, challenge, attempts]
         |
         +-- FactorRepository [owner, status, revision, lastStep/counter]
         |
         +-- SecretProtector   [KMS, AEAD decrypt/encrypt]
         |
         +-- OtpAlgorithm      [HOTP/TOTP generate/verify]
         |
         v
Transaction: compare-and-set anti-replay
         |
         v
MfaSessionUpgrader  [trusted factor proof + context persistence]
         |
         v
AuthorizationManager [require sufficient factors + business permission]
~~~

The `OtpAlgorithm` layer should be a **pure function** with an injectable clock for testing; all state mutations live in `FactorRepository` or a transaction service. `MfaChallengeService` enforces user/attempt policies; `MfaSessionUpgrader` is invoked only along the committed success path. The encryption layer ensures seeds never leak via DTOs, logs, `toString`, or exceptions.

A verification that succeeds cryptographically yet hits a network failure during commit leaves the client in an **unknown** state; the system must use idempotency/challenge IDs, re-read transaction state, or require the next code per policy—never “provisionally accept” because the previous code matched.

## 17. Common Mistakes and Fixes

| Mistake | Why It Is Wrong | Fix |
| --- | --- | --- |
| Calling `oneTimeTokenLogin()` and thinking you have Google Authenticator TOTP | Framework OTT differs from TOTP/HOTP | Use an OTP library + custom factor flow |
| Storing TOTP secret only as a one-way hash | Lacks original secret to compute HMAC for new counters | Encrypt the seed and manage keys |
| Marking factor active immediately when showing QR | User may not yet possess the authenticator | `PENDING` then confirm OTP and commit |
| Checking OTP and issuing full session without saving last step | Same OTP can be reused multiple times | Atomic CAS/transaction anti-replay |
| Verifying HOTP without advancing server counter | Old codes can be replayed | Commit `next_counter` atomically |
| Allowing ±10 steps to “reduce errors” | Expands brute-force surface | Synchronize time, keep a small window |
| 6-digit OTP without rate limiting | Easy to guess codes via spam | Combine account/factor/IP/session rate limits |
| Accepting `userId`/`otpVerified` from request to grant MFA | Privilege bypass or cross-user factor mixing | Bind challenge to first-factor principal |
| Checking MFA only on login page, not APIs | Other endpoints can be bypassed | Require factors at the authorization layer |
| Granting `FACTOR_TOTP` before anti-replay transaction commits | Replay/race can elevate session | Record trusted evidence only after commit |
| Treating recovery email as “skip all checks” | Account takeover path | Separate recovery, reauth, auditing, rate limits |
| Failing to invalidate sessions after reset/revoke factor | Stale MFA access persists | Factor revision, session invalidation/reauth |
| Logging raw OTPs, seeds, `otpauth://` URIs, or QR codes | Exposes secrets/codes | Redaction, `no-store`, least-privilege access |
| Thinking OTP stops real-time phishing | Attacker can relay OTP within seconds | Prefer WebAuthn/passkeys when appropriate |

## 18. Pre-Production Checklist

- [ ] Choose TOTP or HOTP based on device capabilities and needs; verify exact RFC/algorithm/digits/period.
- [ ] OTP library checked for dependencies, test vectors, windows, and invalid-input behavior; do not rely solely on demo code.
- [ ] Generate per-factor seeds via CSPRNG, encrypt at rest, and manage keys in KMS/HSM/secret manager with auditing.
- [ ] Enrollment requires first factor + fresh reauth; `PENDING -> ACTIVE` only after transactional OTP confirmation.
- [ ] QR/`otpauth://` containing secrets never leaks into logs, browser history, analytics, or caches.
- [ ] TOTP blocks replay via `last_accepted_step`/collision policy; HOTP uses `next_counter` and bounded look-ahead.
- [ ] Rate limits, anti-automation, and lockout/recovery are designed against both brute force and DoS.
- [ ] Spring Security grants `FACTOR_TOTP`/corresponding factor evidence only **after** verification and commit; all resources check requirements.
- [ ] Post-MFA sessions enforce lifetime/reauth policies, session fixation protection, logout, and proof invalidation on factor reset.
- [ ] Recovery codes are generated/stored/consumed safely; device changes enforce reauth, alerts, and auditing.
- [ ] Verify OIDC, password, remember-me, API token, and WebFlux flows cannot bypass MFA.
- [ ] Test two nodes confirming the same OTP, time windows, counters, DB/KMS outages, factor changes, and stale sessions.
- [ ] Distinguish authenticator OTP from Spring OTT/magic links; prefer phishing-resistant MFA for high-risk needs.

**Conclusion:** RFC algorithms give you **an OTP calculation**, Spring Security gives you the **authentication and authorization framework**, while your application must implement **enrollment, secret management, anti-replay, rate limiting, session elevation, recovery, and factor revocation**. TOTP/HOTP becomes a worthwhile MFA factor only when all of those parts are securely connected and tested end-to-end.

## Standards and References

- [RFC 4226 — HOTP: HMAC-Based One-Time Password Algorithm](https://www.rfc-editor.org/rfc/rfc4226)
- [RFC 6238 — TOTP: Time-Based One-Time Password Algorithm](https://www.rfc-editor.org/rfc/rfc6238)
- [OWASP — Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html)
- [Spring Security 7.x — Multi-Factor Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/mfa.html)
- [Spring Security — One-Time Token Login and OTP/OTT Distinction](https://docs.spring.io/spring-security/reference/servlet/authentication/onetimetoken.html)
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Java SE 17 — javax.crypto.Mac](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html)

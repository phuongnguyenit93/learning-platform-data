# Factor Enrollment, Recovery Codes, and Factor Change Policies

## 1. Why the MFA Factor Lifecycle Matters as Much as the Login Step

Multi-Factor Authentication (MFA) requires evidence from **at least two independent authentication factors**: something the user knows (password/PIN), something they have (security key, OTP-generating app), or biometric characteristics, depending on the mechanism. Two different passwords do not become two factors merely because they are entered twice.

A system with a very strict MFA login step can still be compromised if an attacker only needs to steal a live session, go to **“Add new device”**, enroll their own method, and delete the old factor. Therefore, **factor enrollment**, **recovery codes**, and **factor change/removal rules** are part of the security boundary—not merely CRUD forms on a Settings page.

Design questions:

1. Who is allowed to initiate enrollment of a new authenticator? Is re-authentication with an already-enrolled factor required?
2. How do we ensure the user **genuinely possesses** the new device/email/TOTP app before marking it `ACTIVE`?
3. When a user loses all factors, how is the account recovered without opening an MFA bypass?
4. How are recovery codes generated, displayed, stored, consumed once, rotated, and invalidated?
5. When changing a factor, are open sessions, long-lived login tokens, factor authorities, and security notifications updated?
6. What is the behavior when two concurrent requests complete enrollment, redeem the same code, or attempt to delete the last factor?

**Scope:** Spring Security **Servlet** and application-side MFA management service design. Programming examples include standalone Java 17 for recovery codes and a Spring Security **7.1.x** configuration snippet for factor policies; do not equate Spring Security 7.x APIs with projects still on 6.x.

### Four Concepts That Must Be Kept Separate

| Concept | Data | When Valid | What It Does NOT Prove |
| --- | --- | --- | --- |
| **Enrolled factor** | Authenticator record bound to the user, `ACTIVE` | After verifying possession of the new factor | Does not prove the factor was used in the current login |
| **Satisfied factor** | Evidence the user recently authenticated with a specific method, with timestamp | Upon successful authentication | Does not prove that authenticator is still `ACTIVE` in the repository |
| **Recovery code** | Backup secret, single-use only, held offline by the user | Once issued and not yet revoked/consumed | Not automatically equivalent to phishing-resistant MFA |
| **Local session** | Session cookie, `SecurityContext`/`Authentication` | After login per policy | Does not guarantee fresh re-authentication to alter factors |

A session created days ago may still be valid for viewing a profile, yet **must not qualify to delete a passkey, change a recovery phone number, or generate new recovery codes**.

## 2. Enrollable Methods and Their Specific Risks

| Factor | Enrollment/Binding | Proof of Possession | What Must Be Protected |
| --- | --- | --- | --- |
| **Passkey/WebAuthn** | Create public-key credential bound to RP ID, user, credential ID | Verify WebAuthn challenge/response, origin, RP ID, user verification policy | Phishing-resistant; store public key and metadata, enforce registration CSRF, reject arbitrary origins |
| **TOTP** | Generate random secret, present QR/provisioning URI in a secure session | Require entering a TOTP code from the app; unverified remains inactive | Time-based codes can be phished; protect secret server-side and prevent replay |
| **Hardware security key** | WebAuthn/FIDO2 or specialized protocol | Prove key possession during the registration ceremony | Lost device; requires backup authenticator and policy-controlled removal |
| **Email/SMS OTP or OTT** | Use only verified contact bound to the account | Out-of-band challenge sent and confirmed | Email/SMS can be compromised; SIM swap, forwarding, same channel as password reset |
| **Saved recovery code** | Randomly generated, shown only to account owner and stored offline | Verify secret in hashed store, single-use | If codes leak, recovery path can be hijacked; not a daily login factor |

**Phishing-resistant does not describe every MFA.** WebAuthn/passkeys bind RP ID/origin and thus defeat a class of phishing that TOTP/SMS cannot. Some passkeys with user verification at the authenticator can satisfy multi-factor properties within a single authenticator, yet actual assurance still follows NIST policy, device characteristics, and verification flows.

### Factor Name, Type, and ID

Do not store a single `mfaEnabled=true` field and treat every device as identical. Records can store:

- `factor_id`: immutable random ID, not email/phone number.
- `user_id`: stable principal from the account system; include tenant in multi-tenant setups.
- `type`: `WEBAUTHN`, `TOTP`, `HARDWARE_KEY`, `OUT_OF_BAND`...
- `state`: `PENDING` / `ACTIVE` / `REVOKED`, `created_at`, `verified_at`, `revoked_at`.
- `credential_id` / public key / algorithm / counter metadata for WebAuthn; **encrypted secret** for TOTP; never store plaintext recovery codes.
- `label`: user-defined label to distinguish devices, length-limited and output-escaped; never treat labels as security identifiers.
- `factor_version` or `security_stamp` on the user to invalidate old proofs/sessions when factors change.

An account can have multiple credentials of the same type (two security keys) to prevent lockout if one device is lost. Achieving two independent factors depends on the threat model, not mechanically counting devices.

## 3. Factor Enrollment: Two-Phase Transaction, Never Activate Before Verification

A simple state diagram:

```text
UNENROLLED
    |
    | User logged in and passed step-up check
    v
PENDING_ENROLLMENT  -- (expired/cancelled) --> EXPIRED/CANCELLED
    |
    | Generate challenge / TOTP secret / WebAuthn options
    | Store TTL-bounded state, bound to user + request + session
    |
    | User proves possession of new factor
    v
VERIFIED (inside transaction, not yet visible as ACTIVE to other requests)
    |
    | Atomic commit to factor store
    v
ACTIVE
    |
    | Step-up with existing factor or approved recovery
    | + notify + revoke old context
    v
REVOKED
```

**Preconditions before starting:** verify active account, owner identity, enrollment policy, current session risk, and sufficiently fresh re-authentication. Initial onboarding enrollment needs its own policy; never let an account that already has MFA use a weak password-only “bootstrap” route.

### 3.1. TOTP: Only ACTIVE After the User Enters a Valid Code

1. Backend uses `SecureRandom` (CSPRNG) to generate the TOTP secret, storing it in a short-lived `PENDING` state. Never write the secret to logs, analytics, unprotected session serialization, or exceptions.
2. Render the `otpauth://totp/...` provisioning URI/QR over HTTPS without caching; display only to the stepped-up user.
3. The user scans into an authenticator app and submits the displayed code; backend verifies HMAC/time-step per RFC 6238 with bounded clock drift, rate limiting, and anti-replay on the same time-step.
4. Upon successful verification, **atomically commit** the device to `ACTIVE` under that user ID. Never activate immediately when the QR is generated.
5. Show backup instructions and issue saved recovery codes per policy; notify of factor addition over a previously registered channel.

The TOTP secret must remain usable to compute/verify OTPs, so it cannot simply be one-way hashed like a password; it typically needs **encryption at rest**, with separated keys and decryption privileges. Do not roll TOTP from scratch in production when vetted libraries exist; Spring Security MFA does not ship a built-in “register TOTP + recovery codes” API for every version.

### 3.2. WebAuthn/Passkey: Using the Framework-Supported Ceremony

With Spring Security Servlet **7.1.x** and `spring-security-webauthn`, registration comprises two requests (default paths):

```http
POST /webauthn/register/options HTTP/1.1
Host: app.example.test
Cookie: JSESSIONID=<opaque-session-id>
X-CSRF-TOKEN: <csrf>

{}
```

The server creates a WebAuthn challenge and registration options, binding them to the request/session per policy. The browser calls `navigator.credentials.create(...)` with the Base64URL-decoded options, then submits the credential attestation:

```http
POST /webauthn/register HTTP/1.1
Host: app.example.test
Cookie: JSESSIONID=<opaque-session-id>
X-CSRF-TOKEN: <csrf>
Content-Type: application/json

{"publicKey":{"credential":{"id":"...","response":{"attestationObject":"...","clientDataJSON":"..."}}}}
```

The JSON above is **an illustrative schema only**, not a full runnable WebAuthn payload. The backend must use a standard verifier to check challenge, RP ID, origin, type, user verification/attestation policy, credential uniqueness, and state; **never blindly trust browser-submitted data**. Credential public key and ID are persisted bound to the right user. Spring Security provides `PublicKeyCredentialUserEntityRepository` and `UserCredentialRepository` with JDBC implementations; in-memory is suitable only for demos/tests without persistence needs.

**Caution when enrolling passkeys:** having logged in once is not enough to permit attaching a new passkey when the account already has MFA; require fresh step-up on the factor management page and CSRF protection. When revoking a credential, avoid deleting audit-needed metadata before committing audit/revocation records.

### 3.3. Email/SMS: Verifying a Contact Does Not Equal a Strong Factor

When allowing an email/SMS OTT receiving method to be added, the app must prove the new contact genuinely belongs to the user **and** only someone authorized to modify MFA can initiate the process. An OTP sent to **the new phone number/email** does not prove account ownership: an attacker could enter their own address and pass “contact verification”.

Protections include: re-authentication using a **previously registered** factor, verifying the new contact, risk review/delays when needed, notifying the **old** contact, and rate limiting by user/IP/tenant. SMS is vulnerable to SIM swap and phishing; when choices exist, prefer WebAuthn/passkeys for sensitive operations.

## 4. Recovery Codes: Backup Paths Must Have Clear Assurance

**Saved recovery codes** are secrets users receive **upon enrolling MFA** (or regenerating after re-auth), stored **offline** in a safe place. When losing the primary factor, they redeem one code to enter a controlled recovery flow. A saved code is a **credential**, not a security question, OAuth2 token, or TOTP OTP.

Under NIST SP 800-63B-4 (2025), saved recovery codes require **at least 64 bits of randomness** from a CSPRNG; examples in this article use **128 bits** to resist brute-force/offline attacks comfortably. Users must receive codes over a protected channel with sufficiently strong authentication and keep them offline. The server **stores hashes rather than plaintext**, throttles attempts, invalidates each code after use, and reissues saved recovery codes upon recovery completion per policy.

### 4.1. Secure Issuance Flow

1. The user is logged in and passes appropriate **fresh re-authentication**, e.g., an existing passkey or password plus second factor. An old session cookie alone is insufficient.
2. Generate a set of random codes with `SecureRandom`; e.g., 8–10 codes is *purely a UX decision*, not a standard-mandated count. Give each code sufficient entropy; never use `Random`, timestamps, usernames, or 6-digit numbers for saved codes.
3. For each code, store a **one-way hash** in a record bound to the account and code ID/version; never store plaintext. Consider HMAC/pepper in a key store to limit database-leak impact, with key rotation. If codes have lower entropy, apply a proper KDF and very strict rate limits.
4. Display codes **once** on the re-authenticated HTTPS screen, allowing download/print with warnings to keep them offline. Return `Cache-Control: no-store`; never place codes in URLs, logs, emails, traces, telemetry screenshots, or analytics.
5. The user confirms safe storage per UX flow. Notify of code generation/regeneration over a registered secure channel; audit metadata, **never log raw codes**.
6. When generating a **new set of codes**, invalidate **the entire old set** via transaction/versioning so old codes cannot remain a backdoor.

### 4.2. Code Consumption

```text
POST /account/recovery/verify
    |
    | identified account_id + raw recovery code + CSRF (if browser)
    v
Rate limit / anti-automation / risk check
    |
    v
Compute hash / compare against codes belonging to that account
    |
    | Atomic transaction: find ACTIVE -> mark USED and commit
    | Only one request wins the race
    v
Narrow recovery state, short-lived, not automatically full login
    |
    | Set up new factor per policy; notify + session review
    v
Finish recovery, revoke used code, issue replacement codes safely
```

Do not perform separate `SELECT` then `DELETE` without locking/transactions: two concurrent requests could both accept the same code. A production approach is a conditional update `UPDATE ... SET used_at=NOW() WHERE user_id=? AND hash=? AND used_at IS NULL`, succeeding **only when rows updated = 1**. Transactions/unique indexes and appropriate locking may also be used.

**Do not promote a recovery code into `FACTOR_WEBAUTHN` or `FACTOR_OTT` by manually adding a `GrantedAuthority`.** Recovery may allow a tightly scoped factor-replacement step if policy permits; it does not prove possession of the lost authenticator. Consider restricting capabilities, lowering trust, adding delays, and notifying before restoring full privileges.

### 4.3. Saved vs. Issued Recovery Codes

- **Saved:** a pre-generated set of secrets kept offline by the user, e.g., 128-bit codes printed on paper. Each code is single-use.
- **Issued:** a code issued fresh **at recovery time** over a previously established/verified recovery channel, such as email/phone. Ensure that channel remains trustworthy and block using newly attacker-altered contacts.

Never send saved codes in plaintext via email by default, and never treat “answering mother's birthplace” as sufficient proof. If a user **loses both all factors and all codes**, transition to a high-risk recovery process backed by independent evidence (identity-verification support, proofing, waiting periods, risk-based approval)—never drop MFA just because the user controls an email inbox.

## 5. Standalone Java 17: Generating, Hashing, Single-Use, and Rotating Recovery Codes

To observe the single-use mechanism, we write **a Java 17 program without Spring Boot**, runnable with `javac` and `java`. It uses only **single-JVM memory** and does not handle HTTP, databases, CSRF, rate limiting, re-auth, user sessions, or recovery authorization. It is **not production code**, yet helps verify hash-only storage and single-use redemption.

Assume 16 random bytes (**128 bits**); unpadded Base64URL produces a 22-character string. With entropy this high, SHA-256 serves as an illustrative one-way hash; for lower-entropy codes, a proper KDF and guessing controls are required. Even with random tokens, protect values displayed in the browser and held in process memory.

Create file `RecoveryCodeDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.Base64;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class RecoveryCodeDemo {
    private final SecureRandom random = new SecureRandom();
    private final Map<String, List<byte[]>> hashedByAccount =
            new HashMap<>();

    // synchronized only provides atomicity within a single demo JVM.
    // Production requires atomic consumption in a database/shared store.
    public synchronized List<String> issue(String accountId, int count) {
        Objects.requireNonNull(accountId, "accountId");
        if (count < 1 || count > 12) {
            throw new IllegalArgumentException("invalid count");
        }

        List<String> shownOnce = new ArrayList<>();
        List<byte[]> digests = new ArrayList<>();

        for (int i = 0; i < count; i++) {
            byte[] randomBytes = new byte[16]; // 128 bits
            random.nextBytes(randomBytes);
            String raw = Base64.getUrlEncoder()
                    .withoutPadding().encodeToString(randomBytes);
            shownOnce.add(raw);
            digests.add(sha256(raw));
        }

        // Rotate the entire set: all old codes are no longer accepted.
        hashedByAccount.put(accountId, digests);
        return List.copyOf(shownOnce);
    }

    public synchronized boolean consume(String accountId, String raw) {
        if (accountId == null || raw == null) {
            return false;
        }

        List<byte[]> digests = hashedByAccount.get(accountId);
        if (digests == null) {
            return false;
        }

        byte[] candidate = sha256(raw);
        Iterator<byte[]> iterator = digests.iterator();
        while (iterator.hasNext()) {
            byte[] stored = iterator.next();
            if (MessageDigest.isEqual(stored, candidate)) {
                iterator.remove(); // single-use within one JVM
                return true;
            }
        }
        return false;
    }

    private static byte[] sha256(String text) {
        try {
            return MessageDigest.getInstance("SHA-256")
                    .digest(text.getBytes(StandardCharsets.UTF_8));
        } catch (NoSuchAlgorithmException impossibleOnJava17) {
            throw new IllegalStateException(impossibleOnJava17);
        }
    }

    public static void main(String[] args) {
        RecoveryCodeDemo store = new RecoveryCodeDemo();
        List<String> original = store.issue("alice", 2);

        String first = original.get(0);
        String unused = original.get(1);

        System.out.println("firstUse=" + store.consume("alice", first));
        System.out.println("replay=" + store.consume("alice", first));
        System.out.println("wrongAccount=" + store.consume("bob", unused));

        List<String> rotated = store.issue("alice", 2);
        System.out.println("oldAfterRotation="
                + store.consume("alice", unused));
        System.out.println("newAfterRotation="
                + store.consume("alice", rotated.get(0)));
    }
}
```

Run with JDK 17+:

```bash
javac RecoveryCodeDemo.java
java RecoveryCodeDemo
```

**Exact stdout** (random codes are not printed):

```text
firstUse=true
replay=false
wrongAccount=false
oldAfterRotation=false
newAfterRotation=true
```

Correctness demonstrated:

- The first code is consumed once; retrying returns `false`.
- One of Alice's codes does not work for Bob's account.
- Issuing a new set invalidates the old set.
- Raw codes are never stored in the map; the map holds only SHA-256 digests.
- `MessageDigest.isEqual` compares hash bytes in constant time, yet the demo still lacks full timing side-channel hardening, rate limiting, and multi-node safety. Production needs transactions, error handling, and auditing.

**Do not use the demo's output as proof of production security.** NIST requires protecting codes during issuance, verification, and post-use; writing a Java hash snippet alone is not enough.

## 6. Factor Change/Removal Policies and Preventing Account Takeover

Modifying MFA methods is a **high-risk** operation. A previously logged-in session, even with a valid cookie, **is insufficient** evidence to allow swapping critical factors. OWASP recommends re-authentication with an existing factor before changes, risk checks, and out-of-band notifications.

### Policy Table by Operation

| Operation | Required Evidence (Policy Example) | Commit Condition | Post-Check |
| --- | --- | --- | --- |
| First-time second-factor enrollment | **Freshly performed** primary auth, onboarding risk checks, account lacks MFA | New factor proved possession | Issue recovery codes, notify, update `factor_version` |
| Adding a third passkey/TOTP | Fresh verification with **already-enrolled** factor and step-up rule | New credential verified, non-duplicate | Notify old channel, audit, review sessions |
| Replacing TOTP while keeping old TOTP | Fresh old MFA or sufficiently assured passkey | New TOTP verified; atomic swap | Revoke old secret, regenerate recovery codes per policy |
| Deleting a non-last factor | Strong fresh MFA/step-up | At least one factor meeting assurance and valid recovery remain | Revoke credential, notify, audit/session invalidation |
| Deleting the **last factor** | Strict dedicated policy; many apps **forbid it** | Must never silently downgrade whole-account MFA | Deny or route to recovery/administrative workflow |
| Regenerating recovery codes | Fresh MFA, not session alone | New set committed atomically, old set invalidated | Show once, notify, audit |
| Changing recovery email/phone | Fresh MFA with factor **prior to change**, verify new contact, risk/delay | New contact verified, possibly cooling period | Notify **old** contact, not only new contact |
| Lost all factors | Valid saved recovery code or independent proofing | Narrow-privilege recovery flow, approval, and accepted risk | Rebind factor, revoke old sessions/codes, notify |
| Suspected takeover | Incident/recovery process | Freeze sensitive changes when needed | Revoke suspicious tokens, sessions, devices, credentials |

**Example of a critical flaw:** a user changes their OTP phone number; the API sends a code only to the **new number** and then deletes the old number. An attacker who hijacked the session can enter their own number, verify the new number, and swap the factor. You must require independent proof from an **already-existing** factor or a strong recovery flow before accepting the change.

### Safe Replacement Flow (When Old Factor Exists)

1. User chooses **Add/Replace** from an authenticated session; server determines permitted operation type and factor; requires fresh step-up using an enrolled factor—not just “re-enter username”.
2. Server generates a random `pending_change_id`, binding `user_id`, `old_factor_id`, type, request/session, `factor_version`, and expiry; never trust client-submitted IDs alone.
3. User completes the ceremony on the new factor (WebAuthn registration or TOTP proof). Server verifies and marks `PENDING_VERIFIED`, without **yet revoking the old factor**.
4. Inside a transaction, re-verify operation permission, unchanged `factor_version`, old factor still owned by user, new factor verified, and policy does not inadvertently lock the user out. Commit new `ACTIVE`, old `REVOKED` if replacing, and increment `factor_version`.
5. Send notification to a **previously** verified channel, write audit metadata, and review/invalidate active sessions and refresh tokens per risk. User sees the updated factor list.
6. On timeout/race/disconnect, avoid leaving partial state where both factors are disabled. Implement retry/idempotency and pending cleanup.

**Session/step-up invalidation mechanism:** when `factor_version` increments, all “MFA completed” evidence from old sessions must be re-evaluated. For example, middleware compares `session.factorVersion` with `user.factorVersion`; mismatch → require fresh login/step-up. Never let a user replay an old `SecurityContext` from another node as if nothing changed.

### What If the Old Factor Is Lost?

That is **account recovery**, not a normal factor change. Do not let a user call the normal replace API with password alone if the account previously had MFA. Use a valid saved recovery code plus additional evidence if policy requires; or an independent proofing workflow, waiting period, old notification channel, audited support review, and anti-social-engineering checks. After recovery, **evaluate revoking all suspicious sessions/credentials**.

You cannot treat “the requester controls the email inbox” as sufficient proof to replace all factors if that same email can also be accessed from the compromised device.

## 7. Spring Security 7.1.x Integration: Factor Management Access Differs from Profile Viewing

Spring Security **7.x** provides `FactorGrantedAuthority` to represent the method just used in `Authentication`. Standard examples include `FactorGrantedAuthority.PASSWORD_AUTHORITY`, `OTT_AUTHORITY`, and `WEBAUTHN_AUTHORITY`. Use `AuthorizationManagerFactories.multiFactor()` to require multiple factors on selected routes rather than forcing MFA on every request.

> **Version boundary:** `FactorGrantedAuthority`, `AuthorizationManagerFactories.multiFactor()`, and `@EnableMultiFactorAuthentication` were introduced in **Spring Security 7.0**. **Do not copy this snippet into Spring Security 6.x**; 6.x projects must build step-up, `Authentication` assurance, and authorization using APIs actually available in that version or upgrade compatibly.

The example below is a **Servlet configuration to integrate into a Spring Security 7.1.x application**. It is not a standalone app (it requires a user service, OTT delivery, controllers, factor-management beans, CSRF, and proper state). Suppose the user has password + OTT and needs both when changing factors; initial bootstrap has its own strong verification method and strict service-layer policy.

```java
package example;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationManagerFactories;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.authorization.EnableMultiFactorAuthentication;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.authority.FactorGrantedAuthority;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMultiFactorAuthentication(authorities = {})
class FactorManagementSecurity {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        var mfaForChange =
            AuthorizationManagerFactories.multiFactor()
                .requireFactors(
                    FactorGrantedAuthority.PASSWORD_AUTHORITY,
                    FactorGrantedAuthority.OTT_AUTHORITY)
                .build();

        var recentPasswordForBootstrap =
            AuthorizationManagerFactories.multiFactor()
                .requireFactor(f -> f
                    .passwordAuthority()
                    .validDuration(Duration.ofMinutes(10)))
                .build();

        return http
            .authorizeHttpRequests(auth -> auth
                // Service MUST additionally verify:
                // - user currently has no enrolled 2nd factor,
                // - account/risk/bootstrap permission.
                .requestMatchers("/security/factors/bootstrap/**")
                    .access(recentPasswordForBootstrap.authenticated())

                // Change/delete/rotate after enrollment:
                // these routes require password + OTT.
                .requestMatchers("/security/factors/manage/**")
                    .access(mfaForChange.authenticated())

                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .oneTimeTokenLogin(Customizer.withDefaults())
            .build();
    }
}
```

Notes:

- `@EnableMultiFactorAuthentication(authorities = {})` enables MFA support without **forcing all routes** to require MFA, allowing per-route-group policies.
- `mfaForChange.authenticated()` requires `FACTOR_PASSWORD` and `FACTOR_OTT` from real login mechanisms. Never manually attach these authority strings to requests lacking completed factors.
- `recentPasswordForBootstrap` **only** illustrates checking the password factor within 10 minutes; for an account that already has MFA, bootstrap routes must be **denied at the service layer**. Otherwise, an attacker with password and session could still take the weak bootstrap path. High-risk apps may require proofing, an invitation/challenge, or another factor even before a second factor exists.
- Once enrolled, changing/removing factors should require **fresh step-up** per request, not merely the presence of an old authority. You can use `validDuration(...)` for specific factors and check `factor_version` / `reauth_at` at the application layer. Thus the snippet does not replace a full re-auth policy.
- Using email OTT as a second factor in a demo can be weaker than a passkey/hardware key and is **not phishing-resistant**. Choose factors matching real assurance and risk requirements.
- Recovery routes when a user loses a factor must never pretend `FACTOR_OTT` was completed; design a **separate, narrow-privilege security chain/recovery state**, preventing loops back into bootstrap.
- For WebAuthn, use `spring-security-webauthn` and store credentials in a production repository. Changing/removing keys still requires re-auth, CSRF, and account state updates.

**Route configuration cannot by itself prove the right account record.** The controller/service handling factor changes must still read `Authentication.getName()`/user ID server-side, verify ownership of `factorId`, current `factor_version`, and transactions. Never trust a `userId` in the JSON body to alter someone else's MFA.

### Service-Layer Pseudocode for Replace Operation

```text
replaceFactor(actorAuthentication, oldFactorId, pendingNewFactorId):
    account = resolveUserFromTrustedAuthentication(actorAuthentication)
    requireFreshExistingFactor(account, actorAuthentication)
    requireNotRecoveryLimitedSession(actorAuthentication)
    transaction:
        lock account and factor records
        require currentFactorVersion == pending.factorVersion
        require oldFactor.userId == account.id && oldFactor.ACTIVE
        require pending.userId == account.id && pending.VERIFIED
        require account policy allows removing this factor
        activate pending new factor
        revoke old factor
        bump account.factorVersion
        commit
    notify old verified channels, audit metadata without secrets
    revoke or re-evaluate existing sessions and long-lived tokens
```

Pseudocode **is not standalone runnable Java**; race handling and transaction structure depend on database/domain. Notifications/outbox should tie into the transaction to avoid “factor changed but alert failed to send”.

## 8. Testing: Do Not Just Look at a Success Screen

| Case | Input Setup | Expected Outcome |
| --- | --- | --- |
| Enroll new TOTP | Freshly verified password+old MFA; enter valid new TOTP | `PENDING -> ACTIVE`, secret never leaked outside ceremony response |
| Open QR and abandon | No verification code submitted | Factor stays `PENDING`, cannot log in with it |
| Enroll WebAuthn wrong origin | Valid challenge but wrong origin/RP ID | Rejected, credential not saved |
| Enroll duplicate credential | Credential ID already belongs to another account | Rejected or safe collision policy, no key hijacking |
| Change factor with stale cookie | Session authenticated but no fresh step-up | 403 / step-up redirect, data unchanged |
| Bootstrap when account already has MFA | Valid password, factor already enrolled | Reject bootstrap, no policy bypass |
| Replace TOTP successfully | Old factor verified, valid new proof | Atomic new `ACTIVE` + old `REVOKED`, `factor_version` incremented |
| Error before commit | Pending verified but DB fails | Old remains `ACTIVE`, account not locked out |
| Attempt to delete last factor | User has only one mandatory factor left | Rejected or routed to controlled recovery process |
| Two concurrent factor-change requests | Same `factor_version` / same `oldFactorId` | Both cannot commit; one hits conflict |
| Generate recovery codes | Fresh MFA | Shown once, DB holds only hashes, safe notification |
| Regenerate codes | Old set still has unused codes | All old codes revoked; new codes valid |
| Redeem same code twice | 2 concurrent POSTs to shared DB | Only one transaction succeeds |
| Alice's code used for Bob | Valid raw code, wrong user | Rejected |
| Rapid sequential code guesses | Multiple wrong tries in short window | Throttled/rate-limited and alerted per risk |
| User loses all factors | No backup codes | Goes only to recovery proofing; no bypass via new email |
| After factor change | Old session on another device/node | Invalidated / forced to re-step-up per policy |
| Notification to old contact | Attacker changes email/phone | Previously registered contact receives alert |
| Locked account user | Valid recovery code | Account/risk policy still applies; no unconditional unlock |

### JUnit Test for the Plain Java Program

You can turn the checks from `RecoveryCodeDemo.main` into JUnit assertions. With JUnit Jupiter and test sources in the same project:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class RecoveryCodeDemoTest {
    @Test
    void oneUseAndAccountBinding() {
        RecoveryCodeDemo store = new RecoveryCodeDemo();
        var codes = store.issue("alice", 2);
        assertTrue(store.consume("alice", codes.get(0)));
        assertFalse(store.consume("alice", codes.get(0)));
        assertFalse(store.consume("bob", codes.get(1)));
    }

    @Test
    void rotationInvalidatesUnusedOldCodes() {
        RecoveryCodeDemo store = new RecoveryCodeDemo();
        var old = store.issue("alice", 2);
        var fresh = store.issue("alice", 2);
        assertFalse(store.consume("alice", old.get(1)));
        assertTrue(store.consume("alice", fresh.get(0)));
    }
}
```

This is a JUnit test for the **in-memory demo** requiring JUnit 5, not a Spring Security or database test. It does not prove atomic consumption across nodes, CSRF, permission checks, or login recovery. Real tests need `MockMvc`/integration tests with sessions/cookies, database transactions, and a fake email sender, exercising race scenarios.

## 9. Common Mistakes to Avoid

1. **Treating MFA Settings as ordinary CRUD:** attackers reuse an old session to add a new factor. Require fresh re-auth with an existing factor.
2. **Marking TOTP ACTIVE merely on showing QR:** user has not yet proven possession; activate only after verification code succeeds.
3. **Allowing removal of the last factor without recovery:** silently lowers assurance and locks users out or opens bypasses.
4. **Using password+PIN as MFA:** both are “knowledge” factors, not independent.
5. **Treating OTP to a new email as sufficient to change MFA:** an attacker who swapped the email receives the OTP. Require proof from a factor/channel existing prior to the change.
6. **Storing recovery codes in plaintext or emailing them:** creates an easily leaked credential store. Use CSPRNG and hashes, deliver once over a protected channel, recommend offline storage.
7. **Codes too short, unthrottled:** vulnerable to brute force, especially if DB leaks. Use high entropy; lower-entropy codes need KDFs and rate limits.
8. **Non-atomic consumption:** two requests redeem the same code concurrently. Use DB transactions/conditional updates.
9. **Regenerating while keeping old code set active:** an attacker with a photo of old codes keeps a backdoor. Rotate the entire set.
10. **Failing to update sessions after factor changes:** old credentials or `SecurityContext` retain access. Increment `factor_version`, revoke, or require step-up.
11. **Adding `FACTOR_WEBAUTHN` to `Authentication` after recovery:** turns a recovery code into fake passkey proof. Keep recovery states narrow-privilege.
12. **Not sending notifications to known channels:** attackers can swap factors silently without the owner noticing.
13. **Equating passkeys with TOTP:** WebAuthn binds origin/RP ID while TOTP can be phished; assurance differs.
14. **Testing only with in-memory unit tests:** misses transaction bugs, multi-node rollout issues, stale sessions, or email delivery flaws.

## 10. Implementation Checklist

- [ ] Maintain a per-user factor inventory with `PENDING`/`ACTIVE`/`REVOKED` states, timestamps, stable IDs, and `factor_version`.
- [ ] Enrollment requires sufficiently fresh step-up; first-time onboarding differs from changing/removing after MFA is enabled.
- [ ] New factor verification completes before commit; WebAuthn uses a trusted verifier/library, TOTP keeps secrets encrypted.
- [ ] Recovery codes are generated via CSPRNG with sufficient entropy, shown once, hashed at rest, throttled, and consumed atomically.
- [ ] Regeneration/recovery invalidates old codes, sends notifications, and protects delivery channels.
- [ ] Changing/removing factors requires a fresh existing factor; never rely solely on session or a new email address.
- [ ] Losing all factors routes to proper recovery proofing and auditing; never silently downgrade assurance via bootstrap APIs.
- [ ] Factor changes use atomic transactions, prevent races, notify old contacts, and manage sessions and refresh tokens.
- [ ] CSRF, rate limiting, log redaction, and tenant/object ownership checks apply across all factor-management endpoints.
- [ ] Unit/integration/concurrency/security tests verify all of the above.

**Conclusion:** MFA protects accounts only when **creating and changing authenticators** also require trusted evidence. Saved recovery codes must be high-entropy secrets, single-use, and properly revoked; factor change flows must re-authenticate with an existing factor, verify the new factor, commit atomically, and handle old sessions. Spring Security provides authentication/authorization and WebAuthn building blocks, while **per-factor enrollment, recovery workflows, and factor change policies** remain the application's architectural responsibility.

## 11. References

- Spring Security 7.x — Multi-Factor Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/mfa.html
- Spring Security 7.x — Passkeys/WebAuthn registration: https://docs.spring.io/spring-security/reference/servlet/authentication/passkeys.html
- Spring Security — `FactorGrantedAuthority` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/authority/FactorGrantedAuthority.html
- Spring Security — `EnableMultiFactorAuthentication` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/authorization/EnableMultiFactorAuthentication.html
- NIST SP 800-63B-4 (2025) — Authenticator Binding & Account Recovery: https://pages.nist.gov/800-63-4/sp800-63b/events/
- NIST SP 800-63B-4 — Look-Up Secrets: https://pages.nist.gov/800-63-4/sp800-63b/authenticators/
- OWASP — Multifactor Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html
- OWASP — Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- RFC 6238 — TOTP: https://www.rfc-editor.org/rfc/rfc6238

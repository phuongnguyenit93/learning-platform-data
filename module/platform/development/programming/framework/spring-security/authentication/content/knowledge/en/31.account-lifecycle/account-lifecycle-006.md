# Changing Email, Phone Number, and Recovery Data with Reauthentication

## 1. Why Is This a Sensitive Operation in the Account Lifecycle?

Email addresses, phone numbers, and recovery data are used to receive security alerts, reset passwords, obtain verification codes, or recover access when a passkey/MFA device is lost. Therefore, changing them is not just a profile edit—it can **alter who controls the account**.

A hijacked login session must never grant permission to change the email address, attach someone else's phone number, remove an old passkey, or generate a new set of recovery codes. For operations that could lead to long-term takeover, design around this chain:

~~~text
Authenticated session
      |
      v
Recent reauthentication with a REGISTERED factor
      |
      v
Create PENDING request, bind account + version + TTL
      |
      +--> Notify old verified channel
      |
      +--> Verify ownership of new channel
      |    (and confirm old channel if policy requires)
      |
      v
Atomic commit, do not reuse old code
      |
      v
Audit + notify + handle session/token lifecycle
~~~

**Guiding principle:** a code received at the **new** email address or phone number proves only that the recipient controls the new channel. It does not replace proof that the requester is currently the account owner. Nor does holding a login cookie prove the account owner is actively present right now.

This lesson covers reauthentication, email/phone change workflows, recovery contacts/codes, session controls, Spring Security Servlet, a Java 17+ example, and race/replay testing.

## 2. Four Non-Interchangeable Layers of Protection

| Layer | Answers | Examples | Limitations |
| --- | --- | --- | --- |
| Authentication | Does the request belong to a valid login session? | `SecurityContext` holds `Authentication` | Session may have been hijacked |
| Recent reauthentication | Did the user just re-verify an **existing factor**? | Current password, passkey step-up, security key | Does not prove the new email belongs to them |
| New-channel verification | Is the new channel controlled by the requester? | One-time code sent to new email/SMS | Does not replace the current factor |
| Authorization and business policy | Is changing this value allowed right now? | User ID, tenant, normal account status, risk checks | Not automatically guaranteed by an OTP |

OWASP recommends reauthenticating before changing sensitive account details and notifying the current email address; verify the new email before activating it, and consider confirming both old and new emails in high-risk environments.

NIST SP 800-63B-4 (2025) likewise emphasizes governing authenticator binding, account recovery, and notifying previously recorded contacts.

## 3. Reauthentication Differs from "Already Signed In"

Reauthentication requires fresh proof of a **previously bound authenticator**.

- **Password accounts:** prompt for the current password and verify server-side with `PasswordEncoder.matches(raw, storedHash)` under rate limiting. Never compare plaintext and never send hashes to the client.
- **Passkey accounts:** require a fresh WebAuthn assertion, checking challenge, RP ID, origin, signature, UV, and credential mapping.
- **TOTP/security key accounts:** verify with an enrolled factor, enforcing replay protection, expiration, and attempt limits.
- **SSO/OIDC accounts:** perform protocol step-up/reauthentication with the IdP and verify results such as `auth_time`/`acr` when supported by the IdP and required by policy. Never treat an SSO redirect that succeeded silently via an old cookie as a fresh login.

One key rule: **never use the new phone number or new email as the existing factor to authorize replacing itself**.

### 3.1. Checking Freshness Window and Scope

A system might require reauthentication within the past **5 minutes** before changing a recovery contact. That duration is **illustrative** and must follow risk policy. The server must:

1. Record the reauthentication timestamp only after actually verifying the proof.
2. Bind it to the account/session, operation type, and assurance level.
3. Check the freshness TTL at initiation or commit per policy.
4. Clear or downgrade step-up elevation on logout, user switch, expiry, or session change.
5. Limit failed attempts to block credential stuffing and OTP brute-force.

`Authentication.isAuthenticated()` or `@PreAuthorize("isAuthenticated()")` alone never proves that a password or passkey was **just** re-verified.

## 4. State Machine for Contact and Recovery Changes

A common model:

~~~text
REAUTH_REQUIRED -> PENDING -> VERIFIED -> COMMITTED
                        |          |
                        +----------+----> CANCELLED
                        +---------------> EXPIRED
~~~

A `pending_account_change` record should capture:

~~~text
request_id
account_id
change_type                 EMAIL / PHONE / RECOVERY_CONTACT
proposed_value
old_value_reference
created_at / expires_at
reauth_method / reauth_at
account_version_at_request
verification_hash_new
verification_hash_old       (if dual-confirm policy)
new_verified / old_verified
status
risk_context
~~~

This is a **domain model**, not a default entity or schema created by Spring Security.

Invariants:

- **PENDING is not ACTIVE:** login and password reset continue using the **old verified** email/phone until commit.
- **One code serves one purpose + account + request**, has a TTL, and is consumed once.
- **New requests cancel old ones** if policy permits only one pending change at a time.
- **Account version must still match** at commit; if the account changed concurrently, old tokens must not overwrite it.
- **Atomic commit** via database transaction/compare-and-set. Single-JVM `synchronized` does not replace transactions across multiple replicas.
- **Notifications aid fraud detection**, not a substitute for reauthentication or verification.

## 5. Secure Email Change Workflow

Suppose an account uses `old@example.test` and wants to switch to `new@example.test`:

1. Verify the user is signed in, owns the account, and is authorized to change email.
2. Clearly display the current address and why reauthentication is needed.
3. Prompt for current password/WebAuthn/TOTP and verify it on the server.
4. Validate the proposed email: syntax, domain policy, uniqueness, tenant scope; do not normalize local parts arbitrarily.
5. Create a pending change and new CSPRNG token with TTL and account version.
6. Send an **alert to the old** verified email. Under high-risk policies, require confirmation from the old channel too.
7. Send a one-time code or link to the **new email**.
8. Only when all conditions pass (new confirmation, old confirmation if required, TTL, account version, risk checks), commit inside a transaction.
9. Audit and send a confirmation notice; update login identifiers/recovery channels post-commit, and handle sessions/refresh tokens per policy.
10. Give the user an independent channel to **report unauthorized changes**.

**Do not** switch the email immediately when the user types into the “New email” box. If email serves as a username, keep an **immutable internal account ID** and update the login/contact attribute only after verification completes.

### 5.1. Notification vs Dual Confirmation

| Policy | Workflow | Best suited for |
| --- | --- | --- |
| Reauth + verify new email + notify old email | Two independent checks, one fraud-detection channel | Most general applications |
| Reauth + confirm both old and new emails | Both channels must consent before commit | Sensitive, administrative, financial accounts |
| Old email is no longer accessible | Route through **separate account recovery** | Never silently drop reauth/dual-confirm |

Mailboxes can be forwarded, compromised, or left open on shared devices. Thus “verified the new email” never equates to “verified the original owner's identity.”

## 6. Tokens and Email Links: Required Properties

- Generate random codes with `SecureRandom`/CSPRNG; for links or copy-paste tokens, e.g., 32 random bytes Base64URL-encoded.
- Codes must be single-use and short-lived (e.g., 10 minutes per policy), never reusing the same code on resend.
- Store the **digest/hash** of the code (or an appropriately protected verifier) instead of long-lived plaintext; bind to account, request ID, purpose, and expiry.
- Compare safely and **consume the code in an atomic transaction** to defeat replays and races.
- Cap verification attempts, rate-limit resends, and never leak email existence in responses.
- Use HTTPS; never place codes or full confirmation URLs into logs, `Referer`, analytics, or exceptions.
- Email links **must not commit on GET**: mail filters may prefetch links automatically. Have GET render a confirmation page, then require POST with CSRF token and explicit user intent.
- If multiple pending requests occurred, bind the code strictly to the exact request/version that issued it and cancel older pending requests.

6-digit OTPs have far less entropy than 32-byte tokens: enforce tighter expiration, attempt caps, and strict rate limits. Never treat short OTP codes as long-lived recovery credentials.

## 7. Changing Phone Numbers: Extra Defenses Against SIM Swaps

Changing a phone number may be a routine contact update **or** replacing the SMS authenticator used for login/recovery. The second case carries much higher risk.

A solid workflow includes:

1. Reauthenticate with a **registered factor**, ideally independent of the phone number being replaced when risk is elevated.
2. Normalize the number to E.164 using a country/region-aware library; never prepend country codes blindly.
3. Save the proposed number in `PENDING` state.
4. Send a verification code to the **new number**, guarding against guessing/replay/rate abuse; this proves control over the new channel.
5. Send a warning to the **verified email or old phone number**, including a way to report fraud.
6. For sensitive accounts, evaluate SIM-swap/number-porting signals, unfamiliar devices, or rapid repeat changes; apply holds or stronger step-up checks.
7. Commit only once policy passes; afterward update MFA bindings, reset tokens, and notifications.

**SMS is not phishing-resistant** like WebAuthn. Attackers can hijack numbers via SIM swapping or telecom exploits, so receiving an SMS on the new number never justifies skipping reauthentication.

## 8. Recovery Data and Recovery Codes

“Recovery data” can include **backup emails, backup phone numbers, recovery codes, trusted devices, a second passkey/security key, or recovery contacts**.

### 8.1. Recovery Codes

Safe regeneration workflow:

1. Require recent reauthentication using an existing factor.
2. Warn clearly that **the old set of codes will be invalidated**.
3. Generate new codes with a CSPRNG and sufficient entropy.
4. Store hashes/digests bound to account, purpose, and unused state; display raw codes **only once** to the owner over HTTPS.
5. When a code is used, mark/consume it atomically so it cannot be reused.
6. Audit, alert via the old channel, rate-limit guesses, and prompt re-enrollment of a new authenticator after recovery.
7. Never send raw recovery codes over standard email, and never log or put them in tracking URLs.

### 8.2. Replacing Authenticators and Recovery Contacts

Adding a passkey, TOTP secret, or backup device is **binding a new authenticator**, not merely inserting a DB row. Require reauthentication, an enrollment verification ceremony for the new authenticator, uniqueness/account binding, out-of-band alerts, and a revocation flow if a device is lost. Never delete the last factor before the user has a valid remaining authentication/recovery path.

If the user **loses every authenticator**, route through **account recovery** with independent evidence and risk checks; never turn “I no longer have my old email/phone” into a button that bypasses all security. Knowledge-based security questions like “pet's name” are not trustworthy factors.

## 9. How Does Spring Security Help?

With **Spring Boot 3.5.x / Spring Security 6.5.x / Java 17+ (Servlet)**:

- `SecurityFilterChain` and `authorizeHttpRequests` protect all account management endpoints.
- `PasswordEncoder.matches(...)` verifies the current password against the server-stored hash.
- `@EnableMethodSecurity` and `@PreAuthorize` guard business services (not enabled automatically just by adding the starter).
- Default CSRF protection guards POST/PUT/PATCH/DELETE in session-cookie applications.
- Form login, session fixation protection, cookie policies, and logout provide the session-management foundation.

Spring Security **does not automatically** implement email/phone change workflows, pending state, OTP delivery, dual confirmation, uniqueness checks, risk/cooldowns, account-version transactions, or outbox notifications. Those remain application responsibilities.

### 9.1. Illustrative Configuration (Fragment)

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/health").permitAll()
            .requestMatchers("/account/security/**").authenticated()
            .anyRequest().denyAll())
        .formLogin(Customizer.withDefaults());
    return http.build();
}
~~~

This snippet sits inside a `@Configuration` class with appropriate Spring Security imports; it is **not a standalone program**. CSRF remains enabled by default. JSON POST requests must send the CSRF token header when using cookie-based login; never disable CSRF just to bypass HTTP 403 errors.

Illustrative service method:

~~~java
@PreAuthorize("isAuthenticated()")
public void requestEmailChange(
        String accountId, String proposedEmail, String currentPassword) {
    // 1. Verify principal from SecurityContext owns accountId.
    // 2. passwordEncoder.matches(currentPassword, storedHash).
    // 3. Rate limits, risk checks, email policy validation.
    // 4. Create pending request + CSPRNG code, TTL/version.
    // 5. Send alerts/confirmations via outbox.
}
~~~

**Key point:** `@PreAuthorize("isAuthenticated()")` only requires being logged in; it **does not automatically verify the current password**. Every step listed in the comments must be implemented in the domain service for production.

### 9.2. Accounts Using SSO/OIDC

If the application has no local password, do not invent a fake “current password” prompt. Instead, trigger step-up reauthentication with the IdP via the protocol, check `auth_time` or assurance claims on tokens signed by a **trusted issuer**, and bind the authentication response to the current request/session. An old JWT access token or a client-supplied `reauthenticated=true` field is not proof of fresh reauthentication.

## 10. Standalone Java 17: Simulating Confirmation of Old and New Channels

The following program illustrates a **pure Java state machine**, without Spring or real emails. It assumes the user has already passed reauthentication and has a `PENDING` request with two distinct codes. Codes exist only inside the test program and never traverse HTTP; each code must match and be accepted once. **This is not a production auth server**: it lacks persistence, CSRF, sessions, mailbox delivery, rate limiting, and auditing.

Create `AccountChangeRulesDemo.java`:

~~~java
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Instant;
import java.time.Duration;
import java.util.Base64;

public class AccountChangeRulesDemo {

    static final SecureRandom RANDOM = new SecureRandom();

    static String newCode() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder()
                .withoutPadding().encodeToString(bytes);
    }

    static byte[] digest(String input) throws Exception {
        return MessageDigest.getInstance("SHA-256")
                .digest(input.getBytes(java.nio.charset.StandardCharsets.UTF_8));
    }

    static final class Pending {
        final byte[] oldHash;
        final byte[] newHash;
        final String newEmail;
        final Instant expiresAt;
        final long expectedVersion;
        boolean oldConfirmed;
        boolean newConfirmed;

        Pending(String oldCode, String newCode,
                String newEmail, long version, Instant now)
                throws Exception {
            this.oldHash = digest(oldCode);
            this.newHash = digest(newCode);
            this.newEmail = newEmail;
            this.expectedVersion = version;
            this.expiresAt = now.plus(Duration.ofMinutes(10));
        }

        synchronized boolean confirmOld(String code, Instant now,
                long currentVersion) throws Exception {
            if (oldConfirmed || !valid(now, currentVersion)) return false;
            if (!MessageDigest.isEqual(oldHash, digest(code))) return false;
            oldConfirmed = true;
            return true;
        }

        synchronized boolean confirmNew(String code, Instant now,
                long currentVersion) throws Exception {
            if (newConfirmed || !valid(now, currentVersion)) return false;
            if (!MessageDigest.isEqual(newHash, digest(code))) return false;
            newConfirmed = true;
            return true;
        }

        boolean canCommit(Instant now, long currentVersion) {
            return valid(now, currentVersion)
                    && oldConfirmed && newConfirmed;
        }

        private boolean valid(Instant now, long version) {
            return now.isBefore(expiresAt)
                    && expectedVersion == version;
        }
    }

    public static void main(String[] args) throws Exception {
        Instant now = Instant.parse("2026-11-06T00:00:00Z");
        String oldCode = newCode();
        String newCode = newCode();

        Pending pending = new Pending(
                oldCode, newCode, "new@example.test", 3L, now);

        System.out.println("before=" + pending.canCommit(now, 3L));
        System.out.println("old=" +
                pending.confirmOld(oldCode, now, 3L));
        System.out.println("oldReplay=" +
                pending.confirmOld(oldCode, now, 3L));
        System.out.println("new=" +
                pending.confirmNew(newCode, now, 3L));
        System.out.println("ready=" +
                pending.canCommit(now, 3L));
        System.out.println("staleVersion=" +
                pending.canCommit(now, 4L));
        System.out.println("expired=" +
                pending.canCommit(now.plus(Duration.ofMinutes(11)), 3L));
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 AccountChangeRulesDemo.java
java AccountChangeRulesDemo
~~~

**Exact stdout:**

~~~text
before=false
old=true
oldReplay=false
new=true
ready=true
staleVersion=false
expired=false
~~~

Explanation: before both channels are confirmed, commit is forbidden; the old code is accepted exactly once, separate from the new code; even a request with both codes confirmed must be rejected if the account version changed or TTL expired. In a real app, consuming codes and committing must be one atomic transaction, not a separate `canCommit(...)` check.

## 11. Common Attacks and Implementation Bugs

| Scenario | Mistake | Control |
| --- | --- | --- |
| Hijacked session | Allowing email change based solely on `authenticated()` | Recent reauth with existing factor |
| CSRF | Cookie-backed POST API with CSRF disabled | CSRF tokens + SameSite/Origin policies |
| Forged token | Client submits `verified=true` | Server verifies code, account, and request ID |
| Attacker controls new email | Requiring only the new-email code to switch | Existing-factor reauth + old-channel notice/confirm |
| Expired code accepted | Missing TTL check | Compare against server time and expire |
| Replay | Code accepted more than once | Atomic consume, used marker, TTL |
| Two concurrent tabs | Stale pending overwrites newer pending | Account version, transactions/CAS |
| GET from email scanner | GET link commits immediately | POST with user intent and CSRF |
| SIM swap | Treating SMS as sole proof | Independent factor, risk/porting signals |
| Account enumeration | Response reveals email already has an account | Anti-disclosure, rate limiting, generic responses |
| Weak recovery | Support changes phone via security questions | Dedicated recovery policy, audit |
| IDOR/BOLA | Taking target `userId` from JSON body | Account ID from server-side `Authentication` |
| Stale sessions after change | Attacker keeps using old session | Session/token revocation per policy |
| OTP leaked in logs/URLs | Code exposed via proxies/analytics | Mask secrets and use protected channels |

### Races and Consistency

If old and new channel confirmations arrive concurrently on two replicas, the service must persist events in a durable store using transactions and unique constraints; `synchronized` protects only **one JVM process**. A `COMMITTED` request must never execute twice, and any older pending request must be invalidated when the account version changes.

### Alerts and Outbox

Send a security alert **to the previously verified channel** whenever email, phone, or recovery data changes, including a “This wasn't me” link to clear support actions. Production should use a transactional outbox with idempotent retries so audits and alerts are never lost if an SMTP/SMS gateway is slow or down.

## 12. Test Matrix

- [ ] Unauthenticated user: cannot create a pending change.
- [ ] Valid session with wrong current factor: cannot initiate change.
- [ ] Right current factor, unverified new email: old email remains active.
- [ ] Code sent to old channel **cannot** verify new channel, and vice versa.
- [ ] All conditions met, matching account/request/version: commits exactly once.
- [ ] Tampered, used, expired, or old-request code: rejected.
- [ ] Request from user A's session cannot alter user B's contact.
- [ ] Cross-origin POST missing CSRF token: blocked.
- [ ] Changing phone with new OTP but no reauth: blocked.
- [ ] Account under SIM-swap/takeover suspicion: enforces step-up/hold per policy.
- [ ] Regenerating recovery codes: old codes invalidated; used code cannot be reused.
- [ ] All factors lost: routed through separate recovery flow, never bypassed via new email.
- [ ] Two tabs/replicas changing contact concurrently: stale token cannot overwrite newer account state.
- [ ] Post-commit: notification, audit, and session/token handling triggered.

Do not rely solely on HTTP status codes in tests: form-login apps may return a `302` redirect instead of `401`. What must be verified is **that sensitive data did not change when proof was insufficient**.

## 13. Production Implementation Checklist

**Authentication and policy:** appropriate current factor/step-up, short reauth age, rate limiting, account ownership/tenant checks, CSRF, HTTPS, session fixation protection.

**State and persistence:** dedicated pending records, TTL, hashed tokens, request/account/version binding, atomic compare-and-set, unique contact constraints, outbox.

**Email/phone:** verify new channel, alert old channel, dual confirmation for high-risk flows, separate recovery for lost old channels, SMS/SIM-swap risk evaluation.

**Recovery:** CSPRNG single-use codes, raw codes shown once, protected passkey/TOTP enrollment/replacement, never delete the last factor without a valid recovery path.

**Operations:** secret-free audit logs, anomaly monitoring, user alerts, incident response, session/refresh revocation per policy, multi-replica testing.

## 14. Self-Check Questions

1. Why is `isAuthenticated()` insufficient for changing an email address?
2. What does a new-email code prove, and what does it **not** prove?
3. Why should pending changes be stored separately in `PENDING` state?
4. Which attributes must a verification code bind to prevent cross-use?
5. Why are account version checks and atomic commits necessary?
6. When should both the old and new emails confirm the change?
7. If a user loses access to their old email, can reauthentication simply be skipped?
8. Why is changing an SMS OTP phone number a change to authenticator binding?
9. How should recovery codes be stored and consumed?
10. What risk does a GET verification link face from email security scanners?
11. How can OIDC/passwordless users perform reauthentication?
12. Which responsibilities does Spring Security handle, and which must the application implement itself?

**Conclusion:** changing an email address, phone number, or recovery data is an operation that **alters an account's trust boundary**. The secure design is **reauth with an existing factor → pending state → verify new channel → check policy/version and commit atomically → alert old channel, audit, and manage session lifecycle**—never substituting a session cookie or new-channel code for missing steps.

## 15. Official References

- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP — Email Validation and Verification](https://cheatsheetseries.owasp.org/cheatsheets/Email_Validation_and_Verification_Cheat_Sheet.html)
- [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)
- [OWASP — MFA Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [NIST SP 800-63B-4 (2025) — Authenticator Lifecycle and Account Recovery](https://pages.nist.gov/800-63-4/sp800-63b.html)
- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)

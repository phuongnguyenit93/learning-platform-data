# Authentication Timestamp and Factor Acceptance Window

## 1. Why Does Successful Authentication Not Mean a Factor Is Always Accepted?

In multi-factor authentication (**MFA**), the fact that a user previously entered a password, verified a TOTP, or used a security key only proves **an authentication event at a point in time**. The system must also determine: **how long that evidence remains accepted, for which session, for which kinds of actions, and when step-up/re-authentication must be performed**.

Example:

~~~text
08:00   Password login
08:02   TOTP verification succeeds
08:05   Request to approve bank transfer
08:07   User still has a valid session
08:20   Request to change beneficiary account
~~~

If the bank-transfer approval policy requires **TOTP within 5 minutes**, evidence from 08:02 is only accepted **before 08:07** under the half-open time rule. At 08:20 the session may remain active for viewing normal pages, yet the sensitive transaction must require fresh evidence or a sufficiently strong method satisfying the policy.

These timestamps **cannot substitute** for one another:

1. **Challenge validity:** until when may an OTP code, nonce, or challenge be submitted for the verifier to check?
2. **Factor freshness:** when did the verifier last confirm the factor; has the evidence's age exceeded the policy limit?
3. **Session lifetime:** until when does the application session remain alive under idle/absolute timeouts?
4. **Token lifetime:** is a JWT/OIDC/access token still accepted per `exp`, `nbf`, and validators?
5. **Step-up privilege lifetime:** how long and for which actions may the elevated post-MFA state be retained?

**Key message:** an OTP's deadline for *submitting the code* differs from the window for *trusting that a factor was verified*, and both differ from the login session's lifetime.

## 2. Defining Factors, Methods, and Verification Results

MFA is built from independent factor categories such as:

- **Knowledge:** something the user knows, e.g., password/PIN.
- **Possession:** something the user owns, e.g., a device holding a TOTP secret, security key, or authenticator.
- **Inherence:** biometric characteristics, typically participating in verification on the device.

**Two steps are not automatically two factors.** A password and a secret question are both knowledge, while two OTPs over the same channel may fail to achieve the intended independence. A passkey/WebAuthn with **user verification (UV)** can supply multiple authentication properties under a profile, yet the authenticator and assurance contract must be evaluated—do not conclude merely because the UI says “Passkey succeeded”.

Distinguish:

| Concept | Meaning | Timing Information |
|---|---|---|
| **Challenge** | Verification request with ID, user/session, purpose, attempts, and verifier data. | `issuedAt`, `expiresAt`, `consumedAt`. |
| **Accepted factor event** | The verifier accepted a specific method/factor and recorded proof with provenance. | `verifiedAt`, `invalidatedAt`. |
| **Authentication session** | Authenticated principal and context maintained across requests. | `createdAt`, `lastAccessedAt`, `idleExpiresAt`, `absoluteExpiresAt`. |
| **Authorization decision** | Is the action allowed on this resource? | Evaluated at action time based on current freshness. |

Only record `verifiedAt` **after** the server successfully verifies the OTP, WebAuthn signature, or corresponding factor; never record it upon issuing the challenge, sending SMS, opening a form, or receiving a client-returned `mfa=true`.

## 3. Two Types of “Expiration” Commonly Confused

### 3.1. Challenge Submission Deadline

A code sent at 09:00 may be configured by the server to expire at 09:05:

~~~text
issuedAt    = 2026-11-06T09:00:00Z
expiresAt   = 2026-11-06T09:05:00Z
maxAttempts = 5
usedAt      = NULL

09:04:59.999   Can verify if unused and within maxAttempts.
09:05:00.000   Cannot verify; deadline reached.
~~~

Five minutes is only a **policy example**, not a mandatory TTL for every OTP. A correct code after expiry must still be rejected. Challenge expiration does not mean a verified-factor event previously created from that challenge becomes invalid immediately; that is governed by its own freshness policy.

### 3.2. Trust Window for an Already-Verified Factor

If an OTP was accepted at 09:04:30 and the action's policy requires **factor age under 3 minutes**:

~~~text
verifiedAt        = 09:04:30
maxFactorAge      = 00:03:00
freshUntil        = 09:07:30  (exclusive)

Action at 09:07:29.999  -> may still be fresh enough
Action at 09:07:30.000  -> no longer fresh enough
~~~

Thus **challenge TTL starts at issuance**, whereas **factor freshness starts when the verifier confirms success**. Session timeouts have their own starting points and renewal rules.

Never update `verifiedAt` upon browser refresh, minting a new access token via a refresh token, reloading `SecurityContext`, extending an idle timeout, opening a sensitive page, or clicking a non-authenticating button. Doing so turns ordinary activity into fresh MFA proof without any real authenticator.

## 4. Exact Formula and Trust Boundaries

Suppose the server stores an event:

~~~json
{
  "proofId": "pf-104",
  "subjectId": "usr-1042",
  "sessionId": "sid-A",
  "factorKind": "POSSESSION",
  "method": "TOTP",
  "verifiedAt": "2026-11-06T08:02:00Z",
  "invalidatedAt": null,
  "purpose": "PAYMENT_APPROVAL",
  "issuer": "trusted-internal-verifier"
}
~~~

This is a **server-side record**, not JSON that a client is permitted to send to mark MFA complete. A minimum rule:

~~~text
accept =
  proof exists and was issued by a trusted verifier
  AND proof.subjectId == currentAuthenticatedUserId
  AND proof.sessionId == currentSessionId
  AND proof.factorKind / method / assurance satisfy action policy
  AND proof.purpose/action binding satisfy current action
  AND proof.verifiedAt <= trustedServerNow
  AND trustedServerNow < proof.verifiedAt + policy.maxFactorAge
  AND proof has not been invalidated/revoked/consumed for this action
  AND session/account and all application permissions are still valid
~~~

For absolute time, use UTC `Instant`; store timestamps in UTC in the database and inject a `Clock` for testing. Never trust `now`, `verifiedAt`, or `sessionId` arbitrarily supplied by the browser as security ground truth. An event “from the future” must be blocked or handled under a very strict clock-sync policy; **never accept unconditionally**.

One critical anchor: **“MFA fresh” does not automatically grant business privileges**. A user without `PAYMENT_APPROVE` still cannot approve a transaction even right after passing TOTP. Conversely, a user with the role whose proof is stale still needs step-up.

## 5. TOTP: The 30-Second Step and Proof Lifetime Are Two Different Concepts

TOTP per RFC 6238 uses time to compute a counter and OTP value. A common configuration uses a **30-second time step**:

~~~text
counter = floor((unixTimeSeconds - T0) / stepSeconds)

Example policy:
  stepSeconds = 30
  tolerated steps = previous / current / next (if configured)
~~~

A ±1 step window helps tolerate clock skew, but increases the number of counters accepted; the effective acceptance duration of a code also depends on **position within the step, clock skew, and policy**—you cannot claim “exactly 30 seconds” across all deployments.

When a TOTP matches:

1. The verifier identifies the appropriate authenticator/user/challenge and counter.
2. Checks attempts, account status, and clock/skew policy.
3. Prevents replay: an already-accepted OTP/time step must not be reused as an independent verification when policy requires single-use (track state per authenticator/counter).
4. Records success **atomically** so two concurrent requests cannot both be accepted.
5. Creates a trusted event with `verifiedAt` set to the server's OTP acceptance time.
6. Enforces action freshness based on that event, **not** by continuing to accept the old OTP code.

For example, a user enters a valid TOTP at 08:02:00. That numeric code may no longer be reusable a second time even at 08:02:05; yet the action policy can still recognize the **proof** from 08:02 until before 08:07. The server does not need the client to re-submit the OTP to check an action while the proof remains valid.

**The TOTP seed must be protected so the verifier can recompute codes**, unlike random tokens where the server can store only a hash. A one-way HMAC/hash of the seed cannot recompute TOTP codes for new time steps. Seeds require a KMS/secret manager or proper key management, and must never be logged or exposed via telemetry.

Six-digit TOTP has a finite code space, so online guessing must be rate-limited per user/authenticator/challenge, protecting against brute force and replay. Never widen the clock-tolerance window excessively just to “reduce errors” without evaluating risk.

## 6. Email/SMS OTP, HOTP, and Push Approval

Not every OTP is generated on a TOTP step. For challenge-issued codes (email/SMS), the server typically stores:

~~~text
challengeId       = ch-811
subjectId         = usr-1042
sessionId         = sid-A
purpose           = CHANGE_PAYOUT
issuedAt          = 10:00:00
expiresAt         = 10:03:00
attemptCount      = 0
maxAttempts       = 5
consumedAt        = NULL
~~~

The code is checked against the appropriate verifier, unexpired, matching session/purpose, and unconsumed. If the code is a short PIN, strict rate limiting, online/offline guessing resistance, and verifier protection are required; never apply 256-bit token entropy assumptions to it.

**Email OTP is not automatically equivalent to a high-assurance out-of-band authenticator**: a mailbox may be controlled via the same session/password, and assurance standards restrict email out-of-band. SMS/voice carries SIM-swap/porting risks; trustworthiness depends on profile and policy. Never just write `mfa=true` and ignore method quality.

**HOTP** relies on an event counter rather than time. The challenge/OTP still requires attempt limits, counter synchronization, and anti-replay; `verifiedAt` remains the timestamp when **the server verified success** and must not be equated with the counter.

**Push approval** creates proof only when the server verifies a protected response from the authenticator, an unexpired challenge, matching user/device, and explicit user confirmation. Sending a push notification is not an authentication event. Mitigate MFA fatigue and request flooding, use number matching/transaction confirmation where supported, and never grant access when a notification was “seen” without approval.

## 7. WebAuthn/FIDO2: Challenge Expiry Differs from Authentication Timestamp

WebAuthn uses a random challenge and a signature from the authenticator's credential private key, while checking origin, RP ID, challenge, user presence (UP), user verification (UV) when required, and registration/assurance conditions.

~~~text
Server issues challenge with expiry
            |
Browser + authenticator signs an assertion
            |
Server validates challenge + origin + RP ID hash
            + signature + UP/UV + credential association
            |
Atomically marks challenge consumed
            |
Creates verified-factor event (verifiedAt = server time)
            |
Action may use proof until freshness deadline
~~~

Once a challenge expires, the assertion cannot be used; however, after successful verification, the app can retain proof to evaluate step-up within the policy window. Assertions **must not be replayed**, and `verifiedAt` must never come from the client.

WebAuthn resists phishing far better than OTP codes relayed through fake websites, yet factor evaluation and assurance depend on the authenticator, UV, credential registration, and policy. A passkey with UV does not automatically mean every transaction was approved with content binding.

If **transaction binding** is required, you need a design proving confirmation over the transaction data. Merely displaying an amount in the UI without binding cryptographic proof to the confirmed data does not by itself create transaction signing.

## 8. Timestamps That Must Never Be Used as `verifiedAt`

| Timestamp | Should Be Understood As | Why It Does Not Prove a Fresh Factor |
|---|---|---|
| `session.createdAt` | When the session was created. | Session may have been created before/after step-up. |
| `session.lastAccessedAt` | Recent session interaction. | Clicking/loading a page is not factor verification. |
| `accessToken.iat` | Access token was just issued. | May come from a refresh token, not new login/MFA. |
| `accessToken.exp` | Token expires at that time. | Does not guarantee the factor was verified recently. |
| `challenge.issuedAt` | OTP/challenge was created. | No proof yet that the user passed the check. |
| `message.sentAt` | Email/SMS was sent/queued. | Successful delivery is not successful verification. |
| `page.visitedAt` | User opened the page/form. | Could be triggered by a bot/link scanner. |
| `rememberDeviceAt` | Device was previously marked trusted. | Not a factor just proven now. |
| `auth_time` (OIDC) | User authentication event at IdP per provider semantics. | Does not itself contain the latest time of **each individual factor**. |

If an application holds only a boolean `mfaVerified` without timestamp, factor method, session binding, and invalidation, building an accurate freshness policy is difficult. A `remember-me` cookie or a token carrying `mfa=true` **must never extend proof validity indefinitely**.

## 9. Session Timeout and MFA Freshness Coexist

A session may use both an **idle timeout** and an **absolute timeout**:

- Idle timeout expires after no acceptable activity for a period of time.
- Absolute timeout terminates the session after a maximum duration from start, even if the user remains continuously active.

MFA proof has its own max age. For example:

~~~text
Session login:                 08:00
Session idle timeout:          30 min (can be extended by activity)
Session absolute timeout:       8 hours
Password verifiedAt:           08:00
TOTP verifiedAt:               08:02
Freshness for payment:          5 min
Payment proof deadline:        08:07 (exclusive)

At 08:20, normal session may remain active
but TOTP proof is stale for sensitive payment.
~~~

In Spring Security, `Authentication.isAuthenticated()` reflects the authentication object's state, not a “TOTP within 5 minutes” check. `SecurityContext` can be restored from the session across many requests without any new verifier event. Never use `HttpSession.getLastAccessedTime()` as a substitute for factor verification time.

**Session renewal** or access-token refresh can technically extend session continuity, yet does not “re-issue” MFA by default. If the system needs post-step-up assurance, store a separate proof with TTL/invalidation, or require re-authentication at the appropriate time.

On logout, account disablement, or session revocation, session-bound proofs must become invalid per policy even if `verifiedAt + maxAge` has not reached its deadline.

## 10. OIDC: `auth_time`, `max_age`, `acr`, and `amr`

In an **SSO via OpenID Connect** model, the application does not directly verify the user's password/TOTP; the OpenID Provider (IdP) does so. The application receives claims *validated by protocol and valid signature*.

Illustrative claim payload:

~~~json
{
  "iss": "https://idp.example.test",
  "sub": "subject-18",
  "aud": "finance-web",
  "iat": 1793944800,
  "exp": 1793948400,
  "auth_time": 1793941200,
  "amr": ["pwd", "otp"],
  "acr": "urn:example:assurance:mfa"
}
~~~

This is **not a real signed ID Token**. Before using any values, verify issuer, audience, signature, expiry, nonce/state/correlation, and OIDC flow requirements.

| Claim | May Indicate | Does Not Automatically Prove |
|---|---|---|
| `iat` | ID Token issuance time. | OTP/password was just entered at issuance time. |
| `exp` | Token becomes invalid after deadline. | MFA proof stays fresh until token deadline. |
| `auth_time` | Authentication event time at IdP per OIDC. | Timestamp of **each specific method** used. |
| `amr` | Methods confirmed by IdP per contract. | OTP was performed **within the last 5 minutes**. |
| `acr` | Authentication context class/level asserted by IdP. | Every issuer uses the same `acr` string with identical semantics. |

### `max_age` and Re-Login Requests

An OIDC client can send `max_age=300` to ask the IdP to ensure the end-user's authentication time is no older than 5 minutes under flow semantics; the result must be verified via `auth_time`. When specific assurance levels are desired, use mechanisms such as `acr_values`/`acr`/`amr` according to IdP capability and contract.

**However, `max_age` alone does not prove a TOTP was verified separately within 5 minutes.** An IdP might authenticate a password with a recent authentication time without the required assurance. Conversely, a refresh token yielding a new `iat` does not necessarily require the user to re-enter anything.

`prompt=login` can ask the IdP to display/run re-authentication per protocol, yet the client must still **inspect the response** and assurance signals. Never trust an `acr=mfa` string without confirming with that specific IdP what it means, and never treat claims crafted by frontend JavaScript as proof.

If policy requires recency of a very specific factor (such as TOTP or a phishing-resistant passkey), the IdP must provide a **re-authentication contract and accurate timestamp**, or the application must run a local step-up verifier. Do not guess from token issue time.

## 11. SAML and Other Identity Federation Systems

In SAML 2.0, an assertion can include `AuthnStatement` with `AuthnInstant` and `AuthnContext`. The Service Provider application must verify signature, issuer, audience, recipient, timestamps, correlation, and profile conditions before trusting it.

**`AuthnInstant` does not automatically equal the time a separate OTP was verified.** If re-authentication or an assurance level is required, negotiate policy with the IdP and verify the returned authentication context. Never turn “SAML assertion is still valid” into “MFA just completed”.

When a federation gateway translates Kerberos/LDAP login into an OIDC/SAML assertion, the application must still trust only evidence issued by the gateway/IdP **for the exact audience** and with confirmed semantics. A token or HTTP header carrying a timestamp without trusted provenance is **insufficient** to elevate privileges.

## 12. Step-Up Authentication Before Sensitive Actions

**Step-up** is the requirement for sufficiently fresh/strong evidence when a user **already has a session** but wants to perform a higher-risk operation.

~~~text
User authenticated, opens /payments/approve
             |
             v
Authorization gate checks:
  - authenticated principal/account active?
  - PAYMENT_APPROVE authority?
  - correct tenant/resource?
  - factor proof is trusted + fresh for this action?
             |
    +--------+---------+
    |                  |
    v                  v
  ALLOW              NEED STEP-UP
    |                  |
    |          issue purpose-bound challenge
    |                  |
    |          user solves factor
    |                  |
    |          verifier checks and consumes atomically
    |                  |
    |          store trusted verifiedAt event
    |                  |
    +<------ retry/confirm action
             |
          recheck authorization
             |
          commit business action
~~~

A specific policy might require a possession factor within 5 minutes, or a transaction-bound WebAuthn ceremony. A shorter window than the session allows the user to keep reading normal data while forcing step-up for approvals/MFA changes.

Never permanently elevate roles to `ROLE_ADMIN` when an MFA step succeeds. Step-up **does not replace authorization**; it adds a condition. For high-value actions, the proof result should carry a `purpose` or `actionId`, and may be restricted to **single-use** for that specific transaction rather than all actions within 5 minutes.

### Preventing Bypasses When a Page Stays Open Long

Checking freshness only when rendering the form is not enough:

~~~text
08:04 open payment form -> proof fresh
08:23 submit approval   -> proof no longer fresh
~~~

The application must **re-evaluate near the time of side effect/commit**. If approval is queued, attach an operation-bound proof/authorization grant and policy for the worker to enforce—never turn an old frontend decision into an unending privilege.

## 13. What MFA Event Data Should Be Recorded and Protected

A trusted proof may contain:

~~~json
{
  "proofId": "pf-5001",
  "subjectId": "usr-1042",
  "sessionId": "sid-A",
  "factorKind": "POSSESSION",
  "method": "TOTP",
  "authenticatorId": "auth-7",
  "verifiedAt": "2026-11-06T08:02:00Z",
  "invalidatedAt": null,
  "purpose": "PAYMENT_APPROVAL",
  "actionId": null,
  "assurancePolicyVersion": "payment-mfa-v2",
  "issuer": "internal-verifier"
}
~~~

This is a server-side record; the browser must never fill in `verifiedAt`, `factorKind`, `issuer`, or `userId` to escalate privileges. Store enough data to verify:

- **Provenance:** which verifier created the event; whether the authenticator was validated per policy.
- **Identity binding:** exact current principal/account/tenant; never map by arbitrary email.
- **Session binding:** proof in session A cannot automatically be used in session B when policy requires binding.
- **Factor strength:** password, TOTP, SMS, and phishing-resistant WebAuthn carry different risk profiles.
- **Purpose/transaction binding:** recovery proof cannot substitute for payment-approval proof.
- **Timing:** `verifiedAt`, expiry policy, invalidation/cancellation, and trusted timestamps.
- **Lifecycle:** if the authenticator is removed, account locked, or a security incident occurs, the proof can be invalidated before its deadline.

Never store raw OTPs, TOTP seeds, private keys, access tokens, session cookies, or raw WebAuthn challenge data indefinitely in access logs. Audits may record non-credential proof IDs, methods, user IDs per privacy policy, and allow/deny outcomes.

## 14. Standalone Java 17: Checking Exact Timestamps and Deadlines

The plain Java example below **runs on JDK 17+** without Spring. It only simulates **evaluating freshness of proofs previously created by a trusted verifier**; it does not verify OTPs, WebAuthn signatures, HTTP sessions, or databases. All timestamps are controlled so stdout is deterministically testable.

~~~java
import java.time.Duration;
import java.time.Instant;

public class MfaFreshnessExample {
    enum Factor { PASSWORD, TOTP }

    record Session(
            String userId, String sessionId,
            Instant issuedAt, Instant expiresAt) {}

    record Proof(
            String userId, String sessionId, Factor factor,
            Instant verifiedAt, Instant invalidatedAt) {}

    static boolean recent(
            Proof proof, Session session, Factor required,
            Instant now, Duration maxAge) {
        if (proof == null || session == null || now == null
                || maxAge.isZero() || maxAge.isNegative()) {
            return false;
        }
        return proof.userId().equals(session.userId())
            && proof.sessionId().equals(session.sessionId())
            && proof.factor() == required
            && !now.isBefore(session.issuedAt())
            && now.isBefore(session.expiresAt())
            && !proof.verifiedAt().isBefore(session.issuedAt())
            && !proof.verifiedAt().isAfter(now)
            && now.isBefore(proof.verifiedAt().plus(maxAge))
            && (proof.invalidatedAt() == null
                || now.isBefore(proof.invalidatedAt()));
    }

    static boolean approve(
            Session session, Proof password, Proof totp, Instant now) {
        return recent(password, session, Factor.PASSWORD,
                      now, Duration.ofMinutes(30))
            && recent(totp, session, Factor.TOTP,
                      now, Duration.ofMinutes(5));
    }

    public static void main(String[] args) {
        Instant start = Instant.parse("2026-11-06T08:00:00Z");
        Session session = new Session(
                "usr-1042", "sid-A", start, start.plusSeconds(7200));

        Proof password = new Proof(
                "usr-1042", "sid-A", Factor.PASSWORD, start, null);
        Proof totp = new Proof(
                "usr-1042", "sid-A", Factor.TOTP,
                start.plusSeconds(120), null);

        Instant first = start.plusSeconds(300);
        Instant deadline = start.plusSeconds(420);
        System.out.println("initial approval: "
                + approve(session, password, totp, first));
        System.out.println("session alive at deadline: "
                + deadline.isBefore(session.expiresAt()));
        System.out.println("approval at OTP deadline: "
                + approve(session, password, totp, deadline));

        Session other = new Session(
                "usr-1042", "sid-B", start, start.plusSeconds(7200));
        System.out.println("other session: "
                + recent(totp, other, Factor.TOTP,
                         first, Duration.ofMinutes(5)));
        System.out.println("proof from future: "
                + recent(totp, session, Factor.TOTP,
                         start.plusSeconds(60), Duration.ofMinutes(5)));

        Proof newTotp = new Proof(
                "usr-1042", "sid-A", Factor.TOTP,
                start.plusSeconds(430), null);
        System.out.println("after step-up: "
                + approve(session, password, newTotp,
                          start.plusSeconds(431)));

        Proof revoked = new Proof(
                "usr-1042", "sid-A", Factor.TOTP,
                start.plusSeconds(430), start.plusSeconds(432));
        System.out.println("revoked proof: "
                + approve(session, password, revoked,
                          start.plusSeconds(433)));
    }
}
~~~

Save as `MfaFreshnessExample.java` and run:

~~~bash
javac MfaFreshnessExample.java
java MfaFreshnessExample
~~~

Exact stdout:

~~~text
initial approval: true
session alive at deadline: true
approval at OTP deadline: false
other session: false
proof from future: false
after step-up: true
revoked proof: false
~~~

At 08:05, password is 5 minutes old and TOTP is 3 minutes old, so both qualify. At 08:07, TOTP is **exactly 5 minutes old**, failing `now < verifiedAt + maxAge`, even though the session remains valid until 10:00. Proof from session A does not apply to B; the 08:02 event is rejected at 08:01; after a fresh step-up at 08:07:10 the proof is fresh again, and then can be revoked at 08:07:12.

In production, `Proof`/`Session` must be built solely from **trusted server state**, never client-supplied JSON. You need an authenticator verifier, persistent store, concurrency control, clock synchronization, session/account status, and method-level authorization outside the demo.

## 15. Spring Security 6: Checking at the Right Authorization Boundary

In Spring Boot 3.x / Spring Security 6.x (Servlet), a request with an `Authentication` in `SecurityContext` only shows that the framework accepted an authenticated object. It does not automatically confirm that MFA evidence is still fresh.

Configuration:

~~~java
// Insufficient for actions requiring step-up:
.requestMatchers("/payments/approve")
    .hasAuthority("PAYMENT_APPROVE")
~~~

checks only the authority, ignoring `verifiedAt`.

### Integrating with Method Security

Spring Security provides `@EnableMethodSecurity` and `@PreAuthorize` to place conditions at the service boundary. The following example is **integration code requiring a Spring project**, not a standalone `javac` program; the `factorFreshnessPolicy` bean must be implemented by the application using a trusted repository/session/clock.

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class SecurityMethodConfig {}
~~~

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class PaymentApprovalService {
    private final PaymentRepository payments;

    public PaymentApprovalService(PaymentRepository payments) {
        this.payments = payments;
    }

    @PreAuthorize(
        "hasAuthority('PAYMENT_APPROVE') and " +
        "@factorFreshnessPolicy.recentForPayment(authentication)")
    public void approve(String paymentId) {
        // Service must verify tenant, resource, transaction status,
        // and recheck proof at commit time if needed.
        payments.approveWithPolicy(paymentId);
    }
}
~~~

This snippet **illustrates the extension point**: `PaymentRepository` and `factorFreshnessPolicy` are system-provided contracts. The policy bean must verify `userId`/`sessionId`/`factorKind`/`verifiedAt`/invalidation/`purpose` from trusted sources and server time. If the application invokes a protected method from inside the same object (self-invocation), Spring proxy method security may not intercept it; place proper service boundaries and write integration tests.

### Sketching a Policy Service

~~~java
// Java pseudocode, does not compile standalone:
boolean recentForPayment(Authentication authentication) {
    String userId = internalIdentityResolver.userId(authentication);
    String sessionId = trustedSessionResolver.sessionId();
    Instant now = clock.instant();
    Duration maxAge = Duration.ofMinutes(5);

    return factorProofStore.hasValidProof(
        userId, sessionId, "PAYMENT_APPROVAL",
        "APPROVED_POSSESSION_FACTOR",
        now.minus(maxAge), now);
}
~~~

**The `hasValidProof` method must enforce the entire contract**: provenance, assurance, exact deadline semantics, future events, invalidation, tenant/account, and factor/device status. Never trust a DB row newly posted by the client. If strict `now < verifiedAt + 5m` is required, a query checking only `verifiedAt >= now-5m` could include a proof right on the boundary; use the exact boundary predicate in your implementation.

### Issuing Proof After Successful Verification

~~~text
POST /mfa/challenges
  -> require existing authenticated session
  -> issue challenge bound user/session/purpose/expiry

POST /mfa/challenges/{id}/verify
  -> verify actual authenticator response
  -> enforce attempt limit, expiry and anti-replay atomically
  -> record trusted verifiedAt via server clock
  -> return only step-up outcome

POST /payments/{id}/approve
  -> authenticated principal, permission, tenant, resource
  -> factor-proof freshness, session status, risk
  -> commit action
~~~

With cookies/sessions, preserve CSRF protection on POSTs and cookie security (`Secure`, `HttpOnly`, `SameSite` as appropriate). Never disable CSRF app-wide just to get challenge verification endpoints working; and never grant access by toggling an easily forged client flag.

## 16. Atomic Verification, Replay, and Time-of-Check/Time-of-Use

An OTP/challenge can be submitted concurrently by two requests:

~~~text
A: SELECT consumed_at IS NULL -> true
B: SELECT consumed_at IS NULL -> true
A: mark consumed; create new MFA proof
B: mark consumed; create another MFA proof
~~~

If check and update are separated, both can be accepted. Use **compare-and-set/conditional update** in the DB or an appropriate atomic store, with unique constraints and transactions.

~~~sql
-- PostgreSQL example: only one request can claim the challenge.
-- Must verify cryptographic OTP/assertion before this step.
UPDATE mfa_challenges
   SET consumed_at = CURRENT_TIMESTAMP
 WHERE challenge_id = :challenge_id
   AND subject_id = :user_id
   AND session_id = :session_id
   AND consumed_at IS NULL
   AND revoked_at IS NULL
   AND expires_at > CURRENT_TIMESTAMP
RETURNING factor_kind, purpose;
~~~

The SQL snippet **does not verify the OTP or signature itself**; combine it with the verifier and proper transactions so no proof is recorded when verification fails, while avoiding races on the same authenticator counter.

If an elevated proof is **single-use for one transaction**, authorization/commit must also consume the proof or action grant atomically. A proof that is only 10 seconds old yet already used to approve transaction A must not necessarily be reusable for transaction B. If policy allows multiple actions within the freshness window, document that decision explicitly rather than leaving it to concurrency luck.

**TOCTOU:** checking MFA when opening a form and executing the change 20 minutes later is wrong if the policy is 5 minutes. Recheck at the service/transaction boundary close to applying the side effect. For queued systems, attach an expiring action-bound authorization grant or block execution if expired; never turn an old UI decision into an unexpiring privilege.

## 17. Invalidation and Revocation Before Expiration

A proof with a recent `verifiedAt` may still need to be rejected when:

- The user logs out or the session is terminated.
- The account is disabled, tenant changes, or privileges are revoked.
- The authenticator is removed, compromised, or reset.
- Password/MFA recovery occurs, or the security team flags high risk.
- SSO/IdP signals revocation under the corresponding contract.
- An action-bound proof has already been consumed for another transaction.
- The client/session is assessed as high risk: device compromise, suspicious session, hijacking signal.

Thus freshness is only **one condition in authorization**, not the sole decision.

**Caching pitfall:** you may cache an immutable `verifiedAt` event, but never cache a boolean `mfaFresh=true` past its deadline. If a cache holds an allow decision for 10 minutes while factor `maxAge` is 5 minutes, the system inadvertently extends privileges. Invalidations must propagate across all instances within SLA; session storage/DB transactions must stay consistent with policy.

Never use IP/geolocation as MFA evidence; they are only risk signals. Never let outsiders trigger resets/invalidations of another account's factors by flooding anonymous requests (enforce rate limits/cooldowns).

## 18. Choosing Windows by Action, Not a System-Wide Constant

| Action | Required Auth Level (Example) | Suggested Freshness to Discuss | When Not Met |
|---|---|---|---|
| View public content | No login needed. | Not applicable. | No MFA required. |
| View personal dashboard | Authenticated session + active account. | Per session policy. | Re-login if session expired. |
| Update personal info | Session and additional factor. | 5–10 minutes depending on risk. | Step-up. |
| Change password | Re-auth or strong recovery flow. | Short, at operation time. | Re-auth/recovery per policy. |
| Remove/replace MFA factor | High assurance + anti-account-takeover. | Short window, may require single transaction. | Step-up/special recovery. |
| Approve disbursement | Role + fresh possession/passkey + resource context. | 3–5 minutes or per-transaction bound proof. | Step-up before commit. |
| Export sensitive data | Authorization + fresh proof + audit. | Shorter than normal session. | Re-auth/deny. |
| Change admin policy | Admin role + high assurance + secure session. | Short elevation and limited scope. | Step-up/re-approval. |

Numbers are **illustrative only** and must be tuned to your threat model, assurance requirements, and internal policy. Short windows reduce the exposure window if a session is hijacked but increase MFA fatigue; friction can be reduced with phishing-resistant methods and proper transaction signing flows.

If your organization follows NIST or another formal standard, check the **exact standard version and assurance level**, rather than turning the illustrative table above into a rigid rule. A low-assurance factor must not be “upgraded” to high assurance merely by having a fresh timestamp.

## 19. Clock Operations and User Experience

- Use server/trusted-verifier UTC `Instant`; store timezone only for display.
- Synchronize clocks across IdP, application nodes, and DB, monitoring drift. Token/TOTP clock-skew policy may differ from proof `maxAge` policy.
- When a proof expires at the final form step, UX should prompt for step-up while **preserving non-sensitive input** through an appropriate mechanism. Never auto-extend the proof to avoid inconvenience.
- Challenge issuance needs quotas, timeouts, MFA push-fatigue controls, and anti-abuse protection; each resend request is not a verified event.
- If the proof store/IdP fails, fail closed for sensitive actions and show a recoverable error; never fall back to session alone or admin role.
- Emit separate success/failure audits with subject, method, policy version, timestamp, and request ID; never log OTP codes, TOTP seeds, challenge responses, or access tokens.
- On password reset, MFA removal, or login session regeneration, define explicitly which proofs remain valid; never accidentally carry old proofs into a new session.

**Client clocks are untrusted.** Changing browser timezone, rolling back the clock, or closing/reopening tabs does not extend evidence. Multi-instance testing must verify the exact boundary `now = verifiedAt + maxAge`.

## 20. Mandatory Test Suite

| Test Case | Expected Result |
|---|---|
| Challenge verified 1 ms before expiry. | Can succeed if code/attempts valid and unconsumed. |
| Challenge verified at exact expiry. | Rejected per boundary policy. |
| Wrong OTP, yet application records `verifiedAt`. | Must never happen. |
| Same OTP submitted twice concurrently. | One wins per replay policy; never record two independent proofs. |
| TOTP accepted 4m 59s ago, maxAge 5m. | May be considered fresh if all other conditions pass. |
| TOTP exactly 5m old. | Not fresh; require step-up. |
| Session alive, proof too old. | Normal actions may continue; sensitive actions blocked. |
| Session logged out, proof 1s old. | Denied; proof does not resurrect session. |
| Proof has future timestamp. | Denied or handled strictly under clock policy. |
| User A's proof used for User B. | Denied. |
| Session A's proof used for Session B. | Denied when session-bound. |
| Fresh password, stale TOTP. | Must not treat both factors as fresh. |
| OIDC access token fresh `iat`, stale `auth_time`. | Do not treat refresh token as re-auth/MFA. |
| IdP returns `amr` containing OTP without specific recency. | Do not infer OTP was verified within the policy window. |
| User has role, stale proof. | Deny / step-up. |
| Fresh proof, missing role. | Authorization deny. |
| Authenticator changed after proof. | Invalidation per lifecycle policy. |
| Form opened while proof fresh, submitted 20m later. | Recheck at commit; do not rely on old decision. |
| Proof from transaction A reused for transaction B. | Blocked if action-bound/single-use. |
| Redis/DB/IdP error. | Never bypass step-up. |
| Client sends `verifiedAt=now` in JSON. | Does not affect trusted proof. |
| Page reload / token refresh. | Must not alter factor `verifiedAt`. |
| Proof cached longer than `maxAge`. | Recalculate age on every decision; never allow past expiry. |
| Browser timezone changed. | Does not change server `Instant` comparison. |

Include **unit tests** for boundaries using `Clock.fixed(...)`, **integration tests** for Spring Security + persistent proof store, **concurrency tests** on challenge consumption, **SSO tests** confirming `auth_time`/`acr` truly satisfy policy, and **end-to-end tests** against TOCTOU. An HTTP 200 after a valid OTP does not prove the overall mechanism is secure.

## 21. Common Misconceptions and Corrections

**“TOTP is 30 seconds so MFA is only valid for 30 seconds.”** Thirty seconds is a time step; the acceptance window for a verified proof is a separate policy. Old TOTP codes still cannot be reused.

**“Refreshing a JWT refreshes MFA.”** A fresh `iat` does not imply a fresh `auth_time` or factor `verifiedAt`.

**“The session is active, so the factor was just verified.”** Session last access/creation is not an authentication event.

**“A boolean `mfa=true` is enough.”** You need `factorKind`/assurance, `verifiedAt`, subject, session, provenance, purpose, and invalidation.

**“MFA succeeded so allow all admin actions.”** Authorization by role, tenant, resource, and transaction is required independently of MFA.

**“SMS was delivered so the user owns the phone.”** Delivery is not verification; and the method has assurance limitations.

**“Add 5 minutes of clock skew to all MFA checks.”** TOTP/JWT tolerance differs from proof freshness; do not extend freshness without justification.

**“Check MFA on GET so POST doesn't need it.”** The real operation may happen after proof expires; recheck near commit.

**“Every passkey is automatically high-assurance two-factor.”** Verify UV/policy/credential rather than inferring from product marketing labels.

**“To shorten MFA windows, force TOTP on every click.”** Balance risk, phishing resistance, transaction binding, and UX; excessive prompts increase MFA fatigue.

## 22. Production Checklist

- [ ] Distinguish challenge `expiresAt`, factor `verifiedAt`, session expiration, and token `exp`.
- [ ] Emit events only after successful verification; provenance and timestamps come from a trusted server.
- [ ] TOTP checks step/drift, attempts, replay, and protects shared secrets.
- [ ] WebAuthn checks challenge, origin/RP ID, signature, UP/UV, and credential policy.
- [ ] Factor independence/assurance evaluated, not merely step count.
- [ ] Proof binds exact user/session/issuer/purpose and action when needed.
- [ ] Consistent time boundary used: `now < verifiedAt + maxAge`.
- [ ] Token `iat`/`exp` never used as fresh MFA timestamps; OIDC `auth_time`/`acr`/`amr` interpreted per IdP contract.
- [ ] Session idle/absolute timeouts kept separate from proof freshness.
- [ ] Authorization checks both role/resource and MFA freshness near commit time.
- [ ] Atomic challenge consumption with anti-replay; elevated single-use grants also consumed properly.
- [ ] Logout, account disablement, authenticator removal, recovery, and incidents invalidate proofs per policy.
- [ ] Caches do not retain freshness booleans past deadlines; multi-instance invalidation synchronized.
- [ ] CSRF, session fixation, cookie security, rate limiting, and MFA fatigue controlled.
- [ ] Server/IdP/DB clocks synchronized and boundary tests exact.
- [ ] Clear step-up UX with controlled recovery paths when factors expire.
- [ ] Audits include timestamp, factor method, policy version, and request/action ID; contain no secrets.

## 23. Conclusion

**A factor's authentication timestamp** must be when the verifier confirmed the evidence successfully. **Acceptance duration** must specify whether it refers to *when a code/challenge may be submitted*, *how long a verified proof stays fresh*, *how long the session stays alive*, or *how long a token stays valid*. Those four milestones can differ dramatically.

The safe model is: **issue time-bounded challenge → verify genuinely with anti-replay → record factor proof with trusted timestamp → bind exact user/session/action → evaluate freshness and permissions at execution time → expire or invalidate → require step-up when needed**.

By separating these concepts, a Spring Security application can keep a session valid for ordinary tasks while protecting sensitive operations with **sufficiently fresh and strong factor** requirements rather than an `mfa=true` flag recorded hours earlier.

## References

- [NIST SP 800-63B-4 — Authentication and Authenticator Management](https://pages.nist.gov/800-63-4/sp800-63b.html): assurance, authenticators, and reauthentication.
- [OWASP — Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html): MFA, step-up, recovery, and MFA fatigue.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session lifetime and timeouts.
- [RFC 6238 — TOTP](https://www.rfc-editor.org/rfc/rfc6238): TOTP time steps and verification windows.
- [RFC 4226 — HOTP](https://www.rfc-editor.org/rfc/rfc4226): HOTP counter, replay, and throttling.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0-final.html): `auth_time`, `max_age`, `acr`, and `amr`.
- [W3C Web Authentication](https://www.w3.org/TR/webauthn-3/): challenge, RP ID, origin, and authenticator assertions.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): method authorization, `@EnableMethodSecurity`, and `@PreAuthorize`.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): session lifecycle and SecurityContext.
- [Java 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): absolute time in Java Time.

# Requiring Additional Authentication for Sensitive Operations in Spring Security (Step-Up MFA)

## 1. Problem Statement: Successful Login Is Not Enough for Every Action

A logged-in user may read order lists, check balances, or edit low-risk profile details. However, actions such as **transferring funds**, **changing email/password**, **adding an MFA device**, **disabling MFA**, **issuing high-privilege API keys**, **changing beneficiaries**, or **bulk deleting data** require stronger or fresher authentication evidence.

**Step-up authentication** means requiring the user to authenticate additionally when approaching a high-risk operation, resource, or context. It does not necessarily force a full logout and re-login. A step-up policy can require:

1. **Strength**: using appropriate factors/methods, such as password combined with WebAuthn.
2. **Freshness**: proving the required factor within the last few minutes, not from yesterday morning's login session.
3. **Right principal and session**: the same account/session currently performing the operation.
4. **Right action or transaction**: the additional authentication step applies to the *specific beneficiary, amount, device, or change*.
5. **Active business permissions**: the account still holds authority to make the change, not merely MFA evidence.

For example: account `alice` logged in at 08:00 with a password and holds `ROLE_USER`. At 17:00, Alice wants to add a payout recipient. The application displays the recipient details, requests authentication via WebAuthn or a policy-compliant factor, and executes the action only when **fresh, appropriate, unconsumed evidence** is verified and Alice's permissions remain valid.

The goal is to counter risks such as unattended browsers, hijacked sessions, CSRF-triggered actions, or abuse of a long-lived login session. Step-up cannot by itself cure every XSS/CSRF flaw or a fully compromised device, yet it establishes an additional protective boundary.

## 2. Understanding “Factor”, “Re-Authentication”, and “Authorization”

| Concept | Question to Resolve | Examples |
| --- | --- | --- |
| **Authentication** | Is the communicating party the claimed principal? | Password, passkey, certificate... |
| **Multi-Factor Authentication (MFA)** | Are there enough independent factors for the required assurance level? | Password + possession factor |
| **Re-authentication** | Did the current session holder just re-prove control of the account? | Re-entering password, re-authenticating with IdP |
| **Step-up** | Requiring stronger/fresher assurance for a specific operation | Fresh passkey before changing email |
| **Authorization** | Once authenticated, what *may the user do and on which resources*? | May only transfer from own wallet |
| **Transaction authorization** | Did the user genuinely confirm this exact transaction? | Confirming the displayed recipient and amount |

Entering **the same password** twice does not create two factors. Login cookies, device fingerprints, IP addresses, geolocation, or recognizing a “trusted” machine **do not automatically become independent factors**; they can serve as risk-assessment signals.

Authentication choices example:

- **Password + TOTP** provides two factor categories under an appropriate model; requires protecting the TOTP secret, anti-replay within the window, rate limiting, and recovery controls.
- **Password + WebAuthn/passkey** can provide phishing-resistant authentication under a suitable policy; WebAuthn with user verification/passkey can act as a multi-factor authenticator in a single verification depending on device, policy, and assurance level.
- **Email OTP after password** may raise the bar for some apps, yet email is a channel that can be compromised simultaneously or forwarded; it does not by default satisfy high-assurance requirements.
- **SMS OTP** carries SIM-swap/phishing risks; if used, apply mitigations and understand its limits.
- **Re-entering password alone** is re-authentication, **not** automatically MFA.

Prefer **phishing-resistant** factors (such as WebAuthn/FIDO2 when appropriate) for high-sensitivity actions. The specific choice follows from the threat model, organizational requirements, and user supportability.

## 3. Policy Matrix by Operation Group

Policies should be expressed by action/resource, not solely by URL name or role:

| Action | Baseline Requirement | Example Additional Requirement | Critical Constraints |
| --- | --- | --- | --- |
| View basic profile | Logged in | Usually no step-up needed | Tenant and read permissions |
| Change display name | Logged in | May not be needed | CSRF protection |
| Change password | Valid login/recovery | Recent re-authentication or MFA per risk | Revoke old sessions/tokens if policy dictates |
| Change security notification email | Logged in | Step-up + verify new address | Block account takeover via email swap |
| Add/remove passkey, TOTP, recovery methods | Logged in | Strong, fresh authentication; protect recovery paths | Never let an unverified new factor approve itself |
| Issue admin-privileged API key | Admin privilege | Fresh MFA and confirmation | Scope limits, TTL, audit, and never expose key |
| Transfer funds / change beneficiary | Source account ownership | Fresh MFA; for high risk bind to transaction | Source account, recipient, amount, idempotency |
| Bulk delete data | `ROLE_ADMIN` + dataset permissions | Step-up and possibly second approval | Record scope, audit, rollback where applicable |
| Change organization-wide security settings | Corresponding privileges | Strong MFA, very fresh timestamp, possibly “four eyes” | Never self-approve one's own privileges |

**The 3–5 minute duration example** in this article is merely an illustrative policy suggestion for protecting risky operations; it is not a universal default mandated by Spring Security or NIST. It must be chosen based on hazard level, UX, and applicable standards.

The final allow condition typically takes the form:

```text
ALLOW if and only if:
  authenticatedCurrentSession
  AND correctAccount
  AND allowedBusinessRole
  AND allowedResourceOwnership
  AND requiredFactorSuccessfullyVerified
  AND factorEvidenceStillFresh
  AND correctOperationBound
  AND proofNotConsumedBefore
  AND accountNotLockedOrRevoked
  AND requestPassesCSRF/anti-replay/idempotencyControls
```

“Has `ROLE_ADMIN`” and “passed MFA” are **two different conditions**. A user without administrative privileges must never become an admin simply by entering an OTP code.

## 4. Secure Step-Up Flow from UI to Business Commit

```text
(1) Browser: POST /transfers/prepare with transaction payload
             |
             v
(2) Backend: authenticated? account/tenant/role/limit?
             |
             v
(3) Store pending action / challenge server-side:
    id, accountId, sessionId, actionFingerprint,
    requiredAssurance, createdAt, expiresAt
             |
             v
(4) UI displays exact amount, destination, change type
             |
             v
(5) User performs additional authentication:
    WebAuthn assertion or verified OTP provider
    (never treat a client-sent boolean as proof)
             |
             v
(6) Server records verifiedFactor + verifiedAt,
    binds account/session/challenge/action
             |
             v
(7) Browser: POST /transfers/confirm with challenge ID,
    resends signed/matched data or reference to
    immutable server-side pending action
             |
             v
(8) Backend: atomic proof claim
    + check freshness/ownership/role/account
    + verify action fingerprint is still exact
             |
             v
(9) Commit transfer or queue transactional outbox
    -> idempotent result, audit, notification
```

Separate **preparation**, **factor verification**, and **executing the change** so the user knows what they are approving. If the recipient or amount changes after authentication, the old evidence must **no longer be usable for the modified transaction**.

Never accept action ID, account ID, role, or `mfaPassed` status from client-supplied body/headers at face value. The browser may pass a reference ID, while the server must look up the linked trusted context, verify, and re-match it.

### Key Distinctions

- A **recently proven factor** may suffice to access a security settings page. This differs from **approving a specific money transfer**.
- When policy requires *transaction binding*, merely setting `mfaVerified=true` across the entire session is insufficient. Verification for transaction A must never authorize transaction B.
- **An MFA confirmation is not automatically single-use:** an application may choose “MFA valid for 5 minutes for a group of actions” or “each transaction requires single-use evidence”. State explicitly which mode is permitted and test against the policy.

## 5. Freshness: MFA Evidence Has Its Own Timestamp and Expiry

Distinguish these timestamps:

- `sessionCreatedAt`: when the application session began.
- `primaryAuthenticatedAt`: the last time the user proved their primary credential.
- `factorVerifiedAt`: when the server/IdP successfully verified the additional factor.
- `proofExpiresAt`: the deadline until which the proof is accepted for the protected action/route.
- `operationCreatedAt` / `operationVersion`: when the transaction payload was established.
- `accountRevokedAt` / `mfaFactorDisabledAt`: events that may force invalidation of old proofs.

Example:

```text
09:00  Login with password -> session A
12:40  Open normal page -> session A still valid
12:41  Prepare recipient X change -> challenge C1
12:42  WebAuthn verification succeeds for C1
12:43  POST confirm C1, exact recipient X -> allow if permitted
12:43  POST confirm C1 again -> reject replay
12:44  Change payload to recipient Y and reuse C1 -> reject
12:46  Use C1 first time (if unconsumed) -> expired if TTL is 3 min
```

**Perform exact time comparisons** using Java `Instant`/UTC and an injected `Clock` for testability: `now.isBefore(expiresAt)`. At `now == expiresAt`, it is **expired**; never trust the phone/browser clock. Across multiple nodes, consider the DB clock or synchronization; never let cached snapshots outlive the validity window.

For multi-use factors, **the factor evidence timestamp must be issued by trusted verification code** (or extracted from a verified IdP token); never let the client submit a fresh `verifiedAt` by editing JSON. On logout, account switch, factor disablement, or password reset, determine whether current proofs/sessions must be revoked per policy.

## 6. Spring Security 7.x: FactorGrantedAuthority and Per-URL MFA Requirements

**Critical version boundary:** `FactorGrantedAuthority`, `@EnableMultiFactorAuthentication`, and `AuthorizationManagerFactories` are APIs introduced in **Spring Security 7.0**. Do not copy the templates below into a Spring Security 6.x/Boot 3.x app and expect them to exist.

Spring Security 7.x can attach `FactorGrantedAuthority` when corresponding authentication mechanisms succeed. For example:

- `FactorGrantedAuthority.PASSWORD_AUTHORITY` — `FACTOR_PASSWORD`.
- `FactorGrantedAuthority.OTT_AUTHORITY` — `FACTOR_OTT`.
- `FactorGrantedAuthority.WEBAUTHN_AUTHORITY` — `FACTOR_WEBAUTHN`.

A factor authority contains `issuedAt` to support freshness policies. Requiring **“two factors”** in authorization does not automatically create login/enrollment pages; you must also configure authentication mechanisms to genuinely gather the corresponding evidence. `OTT` in the example is one-time token login, **not synonymous with every type of TOTP/passkey**.

### 6.1. Requiring MFA Only on Sensitive Endpoints (Servlet)

The example below follows the Spring Security **7.0** API, using form login + one-time-token login and requiring both on sensitive routes. Place it in a Spring Boot project using a compatible Spring Security 7.x (typically Boot 4.x; pick matching dependency versions).

```java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationManagerFactories;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.authorization.EnableMultiFactorAuthentication;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.authority.FactorGrantedAuthority;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

@Configuration
@EnableWebSecurity
@EnableMultiFactorAuthentication(authorities = {})
public class SensitiveMfaSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        var multiFactor = AuthorizationManagerFactories
                .<RequestAuthorizationContext>multiFactor()
                .requireFactors(
                        FactorGrantedAuthority.PASSWORD_AUTHORITY,
                        FactorGrantedAuthority.OTT_AUTHORITY)
                .build();

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/settings/security/**")
                            .access(multiFactor.authenticated())
                        .requestMatchers("/admin/keys/**")
                            .access(multiFactor.hasRole("ADMIN"))
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .oneTimeTokenLogin(Customizer.withDefaults())
                .build();
    }
}
```

**Meaning:**

1. `@EnableMultiFactorAuthentication(authorities = {})` enables MFA infrastructure without **imposing** the same factor requirement across all authorization rules.
2. The `multiFactor` factory requires both `FACTOR_PASSWORD` and `FACTOR_OTT` for matchers using `.access(multiFactor...)`.
3. `/admin/keys/**` requires both **ROLE_ADMIN** and both factors. Remaining routes only require authenticated.
4. You must provide a `UserDetailsService` or user store, configure one-time token delivery over a trusted channel, appropriate UI, and proper default CSRF/session/cookie settings. This is a **configuration class**, not a standalone Java program runnable with `javac`.
5. Route-factor configuration only enforces **factor requirements at access time**; it does not bind an `actionFingerprint` for a specific money transfer or prevent transaction replay. Business logic needs the next step.

Do not apply this example to WebFlux `ServerHttpSecurity`: `@EnableMultiFactorAuthentication` 7.0 API docs specify MFA support specifically for **Servlet**, with reactive support differing/not equivalent in that version. Verify the actual reactive version before implementing.

### 6.2. Requiring Factors to Be Fresh Within a Time Window

Spring Security 7.x provides `RequiredFactor` with `validDuration`. **Alternative** code snippet to require password authentication within 5 minutes and one-time token within 5 minutes (per illustrative policy):

```java
// Spring Security 7.x config snippet, inside a @Bean method
// SecurityFilterChain with HttpSecurity and corresponding imports.
var recentMfa = AuthorizationManagerFactories
        .<RequestAuthorizationContext>multiFactor()
        .requireFactor(factor -> factor
                .passwordAuthority()
                .validDuration(Duration.ofMinutes(5)))
        .requireFactor(factor -> factor
                .ottAuthority()
                .validDuration(Duration.ofMinutes(5)))
        .build();

// Inside authorizeHttpRequests:
// .requestMatchers("/settings/security/**")
//     .access(recentMfa.authenticated())
// .requestMatchers("/admin/keys/**")
//     .access(recentMfa.hasRole("ADMIN"))
```

Requires importing `java.time.Duration`. Never overwrite an old login timestamp with `issuedAt=now` just to pass the check. `validDuration` checks **factor freshness**, **not** replacing transaction binding, confirmation, and one-time proof if the business action requires them.

### 6.3. Choosing Factors by Risk Level

Spring Security 7.x also supports requiring multiple factor combinations and conditional policies, e.g., password + OTT or passkey/WebAuthn based on registration configuration. Do not treat `@EnableMultiFactorAuthentication(authorities = {...})` across every rule as the default solution: public pages, authentication callbacks, recovery, and endpoints not needing step-up can become inaccessible if policy is applied indiscriminately.

**Principle:** specify explicitly which endpoints/subjects require which assurance; ensure flows for supplying missing factors remain safely reachable without opening bypasses to protected resources.

## 7. Spring Security 6.x: Designing Step-Up at the Application Layer

With Spring Security 6.x (Boot 3.x), step-up can be implemented through **application-level policy** paired with trusted second-factor verification providers. Avoid confusing this with the 7.0 APIs in the previous section.

Suggested architecture:

```text
SecurityFilterChain / oauth2Login / formLogin
        |
        v
Authentication + Session (logged in)
        |
        v
Controller/service prepares sensitive action
        |
        v
StepUpChallengeService
  - issue challenge server-side
  - verify TOTP/WebAuthn/IdP re-auth per standard
  - record factor evidence (trusted server only)
  - bind to account + session + action + TTL
        |
        v
POST confirm -> @PreAuthorize(role/permission)
  -> StepUpApprovalService.atomicConsumeAndExecute(...)
        |
        v
DB transaction / transactional outbox -> success
```

Responsibilities to separate:

- **Authentication Provider**: verifies password, TOTP, or WebAuthn assertion. Never compare a browser-submitted OTP string against a code exposed in HTML/session without security policy.
- **Challenge Service**: stores random challenge ID, TTL, accountId, session binding, operation hash, and validity state. Enforces brute-force/replay protection and retry limits.
- **Step-Up Proof Store**: records evidence **only after the factor is genuinely verified**; supports atomic expiration/revocation/consumption.
- **Authorization service**: verifies roles/ownership and current account status, not relying solely on login-time state.
- **Business Service**: commits the action and updates the proof in the same transaction if sharing a DB, or uses outbox/idempotency when spanning external systems.

### Illustrative Controller Snippet in Spring MVC 6.x

```java
// Code snippet only; requires @RestController class, DTOs, service
// and HTTP session/CsrfConfig implemented accordingly.
@PreAuthorize("hasAuthority('TRANSFER_CREATE')")
@PostMapping("/api/transfers/{transferId}/confirm")
public ResponseEntity<Void> confirm(
        @PathVariable String transferId,
        @RequestBody ConfirmTransferRequest request,
        Authentication authentication,
        HttpSession session) {

    sensitiveTransferService.confirmAfterStepUp(
            authentication.getName(),
            session.getId(),
            transferId,
            request.approvalId());
    return ResponseEntity.noContent().build();
}
```

**Never conclude this snippet alone is sufficient to transfer funds safely**. Inside `confirmAfterStepUp`, you must fetch the immutable server-side transaction by `transferId`, verify account/tenant, role, beneficiary, amount, expiration, assurance, proof, and atomic consume/trx before modifying data. Imports/method body/DTOs belong to the application, so the snippet is not a standalone runnable file.

Spring Security method authorization requires enabling `@EnableMethodSecurity` and ensuring sensitive service paths are protected as well, even when invoked through another endpoint. Never put the check only on the frontend “Confirm” button: every API/CLI/batch path must enforce the same rules.

## 8. Standalone Java 17 Example: Proving Action, Session, TTL Binding, and Concurrency

This example runs on **Java SE 17**, requiring no Spring or IdP. It only models **server-verified evidence** and **does not verify TOTP/WebAuthn itself**. Create the file **`StepUpDecisionDemo.java`** with the following code:

```java
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

public class StepUpDecisionDemo {
    record Action(String kind, String destination, long amountCents) {
        Action {
            Objects.requireNonNull(kind);
            Objects.requireNonNull(destination);
            if (kind.isBlank() || destination.isBlank() || amountCents < 0) {
                throw new IllegalArgumentException("Invalid sensitive action");
            }
        }
    }

    record VerifiedPermit(
            String userId,
            String sessionId,
            Action action,
            String factor,
            Instant verifiedAt,
            Instant expiresAt) {}

    static final class AdjustableClock extends Clock {
        private volatile Instant current;
        AdjustableClock(Instant start) {
            current = Objects.requireNonNull(start);
        }
        @Override public Instant instant() { return current; }
        @Override public ZoneId getZone() { return ZoneOffset.UTC; }
        @Override public Clock withZone(ZoneId zone) {
            return Clock.fixed(current, zone);
        }
        void advance(Duration d) { current = current.plus(d); }
    }

    static final class StepUpProofStore {
        private final Clock clock;
        private final ConcurrentHashMap<UUID, VerifiedPermit> permits =
                new ConcurrentHashMap<>();

        StepUpProofStore(Clock clock) {
            this.clock = Objects.requireNonNull(clock);
        }

        // Called only by server AFTER authenticator genuinely verifies successfully.
        // Do not expose this method as a self-asserted "factorVerified=true" endpoint.
        UUID recordVerifiedFactor(
                String userId, String sessionId, Action action,
                String factor, Duration ttl) {
            Objects.requireNonNull(userId);
            Objects.requireNonNull(sessionId);
            Objects.requireNonNull(action);
            if (userId.isBlank() || sessionId.isBlank()
                    || !Set.of("WEBAUTHN", "TOTP").contains(factor)
                    || ttl == null || ttl.isZero() || ttl.isNegative()) {
                throw new IllegalArgumentException("Invalid verified proof");
            }

            Instant now = clock.instant();
            UUID permitId = UUID.randomUUID();
            permits.put(permitId, new VerifiedPermit(
                    userId, sessionId, action, factor,
                    now, now.plus(ttl)));
            return permitId;
        }

        boolean consume(
                UUID permitId, String userId,
                String sessionId, Action submitted) {
            if (permitId == null || userId == null
                    || sessionId == null || submitted == null) {
                return false;
            }

            AtomicBoolean accepted = new AtomicBoolean(false);
            permits.compute(permitId, (id, stored) -> {
                if (stored == null) return null;
                Instant now = clock.instant();
                if (!now.isBefore(stored.expiresAt())) return null;
                if (now.isBefore(stored.verifiedAt())) return stored;
                if (!stored.userId().equals(userId)
                        || !stored.sessionId().equals(sessionId)
                        || !stored.action().equals(submitted)) {
                    return stored;  // do not allow consumption in wrong context
                }
                accepted.set(true);
                return null;       // remove in the same atomic operation
            });
            return accepted.get();
        }
    }

    public static void main(String[] args) throws Exception {
        var clock = new AdjustableClock(
                Instant.parse("2026-01-01T00:00:00Z"));
        var store = new StepUpProofStore(clock);
        var transfer = new Action("TRANSFER", "partner-9", 125_000);
        UUID proof = store.recordVerifiedFactor(
                "alice", "session-A", transfer,
                "WEBAUTHN", Duration.ofMinutes(3));

        System.out.println("wrongSessionAccepted="
                + store.consume(proof, "alice", "session-B", transfer));
        System.out.println("changedActionAccepted="
                + store.consume(proof, "alice", "session-A",
                        new Action("TRANSFER", "attacker-1", 125_000)));
        System.out.println("firstUseAccepted="
                + store.consume(proof, "alice", "session-A", transfer));
        System.out.println("replayAccepted="
                + store.consume(proof, "alice", "session-A", transfer));

        UUID concurrentProof = store.recordVerifiedFactor(
                "alice", "session-A", transfer,
                "TOTP", Duration.ofMinutes(3));
        ExecutorService pool = Executors.newFixedThreadPool(12);
        try {
            CountDownLatch gate = new CountDownLatch(1);
            List<Future<Boolean>> attempts = new ArrayList<>();
            for (int i = 0; i < 12; i++) {
                attempts.add(pool.submit(() -> {
                    gate.await();
                    return store.consume(concurrentProof,
                            "alice", "session-A", transfer);
                }));
            }
            gate.countDown();
            int accepted = 0;
            for (Future<Boolean> attempt : attempts) {
                if (attempt.get()) accepted++;
            }
            System.out.println("concurrentAccepted=" + accepted);
        } finally {
            pool.shutdownNow();
        }

        UUID expiredProof = store.recordVerifiedFactor(
                "alice", "session-A", transfer,
                "WEBAUTHN", Duration.ofMinutes(3));
        clock.advance(Duration.ofMinutes(3));
        System.out.println("atExpiryAccepted="
                + store.consume(expiredProof, "alice", "session-A", transfer));
    }
}
```

Run with JDK 17+:

```bash
javac StepUpDecisionDemo.java
java StepUpDecisionDemo
```

Exact stdout (without printing random UUIDs):

```text
wrongSessionAccepted=false
changedActionAccepted=false
firstUseAccepted=true
replayAccepted=false
concurrentAccepted=1
atExpiryAccepted=false
```

### Explaining Why the Results Are Correct

- `VerifiedPermit` binds `userId`, `sessionId`, `Action`, `verifiedAt`, and `expiresAt`. `Action` is an immutable record; if `destination` or `amountCents` changes, `equals()` no longer matches.
- `recordVerifiedFactor(...)` **is called only along the server path after authenticator verification succeeds**. The demo lacks a WebAuthn/TOTP verifier, so calling the method from `main` only creates a trusted fixture rather than proving authenticator security.
- `consume(...)` uses `ConcurrentHashMap.compute(...)` to check and remove in **the same atomic per-key operation**. There is no separate `get` followed by `remove`.
- Wrong session/action inputs are rejected **without deleting** the valid permit; the legitimate principal can still use the right permit before expiration.
- The first winning request removes the permit; replay is rejected. Out of 12 requests racing on the same permit, exactly one receives `true`, independent of thread scheduling order.
- `now.isBefore(expiresAt)` makes the boundary `now == expiresAt` invalid.
- The program **does not execute transfers, create Spring Security Authentication, or persist data across JVMs**. `ConcurrentHashMap` only demonstrates concurrency within *one process*. Production must use a DB/shared store with system-wide atomicity, combined with business transactions/idempotency.

**Important:** this evidence record is **authorization for one action**, not a `GrantedAuthority` arbitrarily attached from a request. If you need a 5-minute scope covering multiple actions instead of single-use, explicitly design its limits and the consequences of proof reuse.

## 9. Ensuring One-Time / Transaction Binding in the Database

A conceptual database schema (PostgreSQL) for transaction-bound step-up:

```sql
CREATE TABLE step_up_approvals (
    approval_id UUID PRIMARY KEY,
    account_id VARCHAR(100) NOT NULL,
    session_binding VARCHAR(128) NOT NULL,
    action_hash VARCHAR(128) NOT NULL,
    factor_type VARCHAR(40) NOT NULL,
    verified_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ NULL,
    revoked_at TIMESTAMPTZ NULL,
    CHECK (expires_at > verified_at)
);
```

- `approval_id` is an unguessable random ID; it **is not itself an authentication factor**, because it is issued only after the factor is verified and bound to the session.
- `session_binding` can be an HMAC/protected session ID; never store raw session secrets in logs or URLs.
- `action_hash` must be computed from a canonical **server-side** representation of the action, including source/destination accounts, amount/currency, target recipient, action type, version, or nonce. Never use Java's `hashCode()` as a security fingerprint.
- `factor_type`/`verified_at` reflect the verified method and trusted timestamp; never take a client-supplied field.

An “atomic claim” pattern in PostgreSQL:

```sql
UPDATE step_up_approvals
SET consumed_at = clock_timestamp()
WHERE approval_id = :approval_id
  AND account_id = :account_id
  AND session_binding = :session_binding
  AND action_hash = :action_hash
  AND factor_type = :required_factor
  AND consumed_at IS NULL
  AND revoked_at IS NULL
  AND verified_at <= clock_timestamp()
  AND expires_at > clock_timestamp()
RETURNING approval_id;
```

If 1 row is returned: the request is entitled to use the proof once. If 0 rows: wrong account/session/action/factor, expired, revoked, already used, or nonexistent. The request **must not execute the action** if claiming fails.

**Transaction time note:** `clock_timestamp()` in PostgreSQL returns the wall-clock time at invocation, unlike `CURRENT_TIMESTAMP` which is usually fixed at transaction start. In the query above, individual evaluations could differ by microseconds; if strict single-timestamp consistency is needed, capture one timestamp in the same atomic step and apply that exact predicate. Never use browser-passed time or check expiry before waiting on a lock and ignore expiry afterward.

### A Successful Claim Does Not Alone Guarantee Exactly-Once Business Effects

Safe transaction pattern when approvals and business data share the same database:

```text
BEGIN TRANSACTION
  - read trusted transfer/account/tenant data
  - check permissions, ownership, limits, and account status
  - atomic claim approval (UPDATE ... RETURNING)
  - if no row -> ROLLBACK, reject
  - create business operation with UNIQUE idempotency key
  - update balance / transition state consistently
  - write audit/outbox event
COMMIT
```

If the operation calls a payment gateway or external service, a DB transaction cannot span the external network. When a request times out after commit, the client may retry. Use a **business operation idempotency key**, transactional outbox, and idempotent consumers, rather than relying solely on `approval.used=true`.

**Across multiple instances:** never use `synchronized` or `ConcurrentHashMap` as a shared authentication boundary. Depending on DB/Redis, use atomic compare-and-set, row locks, unique constraints, or transactions. Test concurrent requests across two pods, not only in one JVM.

## 10. SSO/OIDC: Step-Up via an Identity Provider Is a Different Flow

If the application uses `oauth2Login()`/OIDC, it can ask the **IdP to re-authenticate or raise assurance** for an operation. Relevant parameters:

- `prompt=login`: asks the IdP to re-authenticate the user (per IdP contract), yet **is not automatically synonymous with MFA**.
- `max_age`: requires authentication event age not to exceed a threshold, checking `auth_time` from the ID Token per OIDC requirements.
- `acr_values`: requests a specific `Authentication Context Class Reference` level, subject to IdP support and enforcement.
- `acr`: IdP-asserted assurance level; meaningful only under a **verified IdP agreement/metadata**.
- `amr`: authentication methods reported by the IdP; never treat arbitrary string arrays as sufficient evidence.

Flow:

```text
RP app with existing session
  -> identify action requiring high assurance
  -> create challenge (account/session/action), state + nonce
  -> redirect to IdP with max_age / acr_values per policy
  -> IdP gathers required evidence and redirects callback
  -> Spring Security validates OIDC: state, nonce, signature,
     iss, aud, exp plus authorization code flow bindings
  -> application VERIFIES acr/auth_time/amr per IdP contract
  -> match exact (iss, sub) to existing account/session
  -> record proof + timestamp server-side
  -> atomic confirm sensitive action
```

**Do not accept a step-up callback as a “log in as a different user” operation and switch owners of a pending transaction**. If the callback `(iss, sub)` does not match the local account bound to the initial action, reject/cancel the challenge; never replace the approver with whoever just logged in unless a permitted workflow exists.

An active IdP SSO cookie can let the redirect finish immediately; that **does not prove** the user actually performed fresh MFA. You must check assurance policy and event timestamps, not infer from callback success.

ID Tokens and Access Tokens have separate lifetimes from `HttpSession`; ID Token expiration **does not automatically** destroy the application session. Nor should a step-up proof be extended just because the session cookie has not expired.

## 11. Stateless APIs, JWTs, and WebFlux: Do Not Copy Servlet Patterns Verbatim

For stateless APIs using `Authorization: Bearer`:

- The resource server's `Authentication` is built from the access token on each request; there is no default app browser session.
- If signed token/claims carry `acr`/`amr`/`auth_time`, the application may inspect them **only after issuer/audience/signature/claims are verified** and the IdP clearly defines their meaning.
- An access token carrying scope `transfer:write` does not by itself prove the bearer **just** authenticated an additional factor.
- To step up, you can require the client to run a new authorization flow for a **new access token** with higher assurance and exact audience/scope, which the resource server then verifies. Or use a separate transaction-approval service binding proofs to operations.
- If the API uses long-lived JWTs, old tokens may remain valid for ordinary resources; sensitive endpoints must reject tokens lacking required assurance/freshness.
- Never trust a client-sent self-declared `X-MFA-Verified: true` header; if a gateway forwards authentication metadata, protect it with mTLS/signatures and an explicit trust boundary.

With **Spring WebFlux**, `SecurityWebFilterChain` and `ReactiveSecurityContextHolder` differ from Servlet's `HttpSecurity`/`SecurityContextHolder`. Do not drop Servlet `@EnableMultiFactorAuthentication` or HTTP servlet filters into a reactive pipeline and expect them to work. Pick APIs supported in your exact Spring Security version; the transaction-bound approval service must still be invoked and consumed atomically via a reactive database driver or properly isolated I/O.

## 12. CSRF, Session Fixation, Permissions, and Bugs That Bypass Step-Up

### 12.1. Separating MFA Steps from Improper Session Handling

Merely calling `session.setAttribute("mfa", true)` in an endpoint without checking who may invoke it and which factor was verified lets an attacker “unlock” the whole session. Safe step-up evidence needs at least:

```text
userId, sessionId, factorType,
verifiedAt, validUntil,
challengeId / approvalId,
intendedAction + immutable parameters,
state (issued / verified / consumed / revoked)
```

Clear/revoke related evidence on logout, policy-mandated session rotation, account switch, factor removal, or suspected compromise. If the design permits multiple tabs within one session, isolate challenges by ID so tab A never accidentally approves tab B's action.

### 12.2. CSRF and Replay Are Two Distinct Risks

- **CSRF protection** prevents another website from forcing a browser to submit requests while a session cookie is valid. Keep `CsrfFilter`/tokens active for state-changing requests, including enrolling/removing factors, issuing/verifying challenges, and confirming actions.
- **Step-up MFA** requires the principal to prove a factor. Never disable CSRF just because MFA exists; attackers can still manipulate flows, redirects, or transaction data in certain scenarios.
- **Replay protection** stops the same proof/transaction from being reused; requires atomic consumption/idempotency.
- **Transaction binding** prevents a user from confirming recipient A while the final payload executes recipient B.
- **Session fixation protection** on login/re-authentication per mechanism; never accept client-specified session IDs, and never carry old proofs unintentionally onto a new session.

### 12.3. Never Escalate Privileges Simply Because MFA Passed

Factor evidence must be combined with checks such as:

```text
hasAuthority("TRANSFER_CREATE")
AND ownerOfSourceAccount(currentUser, transfer.sourceAccount)
AND amountWithinLimits(transfer)
AND recipientAllowed(transfer.recipient)
AND hasRecentAppropriateFactor(currentSession, transfer)
AND atomicApprovalConsumed(transfer)
```

Never turn `FACTOR_WEBAUTHN` into `ROLE_ADMIN`, nor replace `tenantId`/ownership checks with “passed OTP”.

### 12.4. HTTP Errors and User Experience

- **401 Unauthorized**: missing required authentication or invalid resource server token, depending on application type.
- **403 Forbidden**: authenticated but lacking sufficient privileges/assurance or denied by policy; for browser apps, it may **redirect to the factor-prompt step** if the corresponding entry point is supported.
- **409 Conflict**: sometimes suitable when confirmation targets an outdated/modified transaction; avoid returning details that leak sensitive information.
- **429 Too Many Requests**: rate limiting code attempts/enrollment/recovery; never substitute 429 for authentication policy.
- Expired TTL: guide the user to perform a new additional authentication; never extend an old proof's timestamp automatically.

Good UX displays the reason and **the exact transaction details being approved**, while minimizing “MFA fatigue” from repeated prompts. Never authorize an action just because a user tapped “Approve” on a contextless push notification.

## 13. Common Mistakes

**Mistake 1 — Checking MFA only at login.** A user leaves a 12-hour session open while the transfer API only checks `authenticated()`. Enforce freshness/assurance policies at the operation.

**Mistake 2 — Checking role without checking factors.** `ROLE_ADMIN` does not mean the current user controls the account's authenticator. Require both conditions.

**Mistake 3 — Checking factors without checking permissions.** Any user who passes TOTP is allowed to call an admin API. Step-up does not grant roles.

**Mistake 4 — A global `mfa=true` flag on the session.** Every subsequent operation is “unlocked” indefinitely. Bound TTL/scope; use transaction binding and single-use when needed.

**Mistake 5 — Treating OIDC `prompt=login` as proof of MFA.** Prompt only requests re-login, not guaranteeing method/assurance; verify `acr`/`amr`/`auth_time` per contract.

**Mistake 6 — Trusting client-sent timestamps/booleans.** Browsers can tamper with JSON. Accept only evidence verified by the authenticator/IdP and timestamped server-side.

**Mistake 7 — Modifying the payload after MFA.** The user saw amount/destination A while the API executes B. Persist pending actions server-side and compare exact fingerprints/versions at commit.

**Mistake 8 — Race between two confirm requests.** Both requests read `approval.used=false` and execute the action. Use atomic compare-and-set/DB transactions and idempotent business operations.

**Mistake 9 — Using `synchronized` across a 5-pod deployment.** Locks only protect one process. Shared DB/Redis state and proper transactions are required cluster-wide.

**Mistake 10 — Confusing “has a passkey” with “just used a passkey”.** An enrollment record is not authentication proof; require a verified event at the proper time.

**Mistake 11 — Allowing MFA disablement via an unprotected recovery email.** An attacker who compromises email bypasses MFA; recovery paths need commensurate assurance, rate limits, auditing, and notifications.

**Mistake 12 — Factor-change requests self-issuing factor proofs.** E.g., an endpoint adding TOTP also sets `mfaVerified=true` from an unregistered user code. Separate enrollment from verification, and require existing factors/step-up before disabling.

**Mistake 13 — Skipping CSRF because “MFA is enabled”.** Session cookies can still be abused; protect all state-changing endpoints and login/linking flows.

**Mistake 14 — Failing to revoke proofs after password change/logout.** Old evidence may linger after account/session changes. Build event-driven invalidation per policy.

**Mistake 15 — Logging OTP codes, WebAuthn assertions, cookies, or approval secrets.** Log only minimal metadata and outcomes, masking user identifiers per retention; never log raw credentials.

**Mistake 16 — Testing only the happy path.** Neglecting cross-account/cross-session, expired, concurrent, wrong-operation, disabled-account, or low-assurance IdP cases. Run negative tests before production deployment.

## 14. Step-Up Testing Matrix

| Test Case | Expected Result |
| --- | --- |
| Logged-in user accesses regular page | Follows baseline permissions, no unnecessary step-up |
| Logged-in user without extra factor accesses sensitive endpoint | Redirects to challenge or denies per API style |
| Password + valid factor per Spring Security 7 route | Satisfies factor condition, still requires role/business permission |
| User missing `ROLE_ADMIN` yet passed MFA | Cannot access admin API |
| Proof expired exactly at `now == expiresAt` | Denied |
| Fresh proof but mismatched account or session | Denied, never authorizes another session |
| Proof for transfer A reused on transfer B | Rejected by transaction binding |
| Recipient or amount changed after challenge | Rejected or requires new challenge |
| Replaying the same proof after success | Rejected, business action does not re-run |
| 12 concurrent requests for the same approval in one JVM | At most one claims it |
| Confirm requests from multiple nodes against shared DB | At most one commits per shared-store concurrency policy |
| Factor just disabled or account locked | Old proof revoked/denied per policy |
| SSO login 8 hours ago with active IdP cookie | Not automatically treated as fresh step-up |
| OIDC callback missing assurance or `auth_time` too old | Rejected per IdP trust contract |
| Wrong authorization code/state/nonce | Rejected at OIDC callback, no proof issued |
| CSRF on transaction confirmation endpoint | Rejected per CSRF policy |
| DB error while claiming proof | Fail closed; action not executed |
| Commit succeeds but HTTP response is lost | Retry does not execute again thanks to idempotency |
| User needs recovery due to lost authenticator | Separate recovery workflow, never silent high-privilege bypass |

### Where Should You Test?

**Unit tests:** freshness calculation policies, action/session/account/state matching, and pure Java concurrency logic like `StepUpDecisionDemo`.

**Integration tests:** Spring Security filter chain + real form/OIDC/WebAuthn/OTT, CSRF, session rotation, request matchers, and authorization failures.

**Database concurrency tests:** multiple requests/processes claiming one approval concurrently using production PostgreSQL/Redis config; verify row counts/updates/business effects.

**End-to-end tests:** browser displays exact action, user authenticates the right factor, IdP guarantees `acr`/`amr`/`auth_time` per contract, application records transaction and audit properly; also test multiple tabs, timeouts, and rollbacks.

## 15. Monitoring, Auditing, and Recovery

Because step-up guards sensitive boundaries, monitor:

- Step-up request counts by action/risk level, and success/failure/cancellation rates.
- Actual verified factor method, `verifiedAt`, and elapsed time from challenge to confirmation (never log credentials).
- Rates of expired proofs, reuse/replay, wrong-action, or session mismatches.
- MFA method changes, account recoveries, factor disablements, and email/password changes.
- Successful business commits, idempotency retries, and outbox failures.
- IdP authentication outages, WebAuthn provider issues, DB errors, or rate-limiting triggers.

Audits must record accountId, operationId, factorMethod, request correlationId, timestamp, and outcome. Keep identities/PII minimal, redact raw tokens, OTP codes, cookies, and secrets, and enforce proper retention and access controls.

**Recovery is a critical attack path:** if a user loses their passkey, there must be a secure, audited recovery process that avoids allowing recovery via a weaker factor to bypass all constraints of sensitive actions. Recovery codes must be protected and consumed once per policy.

## 16. Final Pre-Production Checklist

1. Have sensitive endpoints/actions and their required assurance levels been classified?
2. Are **authentication**, **authorization**, **step-up**, and **transaction approval** clearly separated?
3. Are fresh factors verified by a server-side provider rather than self-reported by the client?
4. Where true MFA is required, are factors independent and aligned with the threat model?
5. Do proofs carry `verifiedAt`, TTL, userId, sessionId, actionId/hash, and unconsumed state?
6. Is freshness checked on **every sensitive decision** using trusted server/DB time?
7. Are role, account status, tenant, ownership, and business limits re-verified?
8. Are amount/recipient changes prevented after confirmation?
9. Are atomic consumption + transactions/idempotency enforced across nodes?
10. Have CSRF, OIDC state/nonce, session fixation, cookie attributes, and HTTPS been tested?
11. Do logout, password change, factor disablement, and account revocation invalidate required proofs?
12. Do SSO, WebFlux, and stateless API paths use the proper protocol/DSL for their versions?
13. Do tests cover wrong account/session/action, expiry boundaries, 12 concurrent requests, and lost responses?
14. Is the user shown the exact transaction they are approving, and is there a secure recovery path?

### References

- Spring Security 7.0 — Multi-Factor Authentication (`FactorGrantedAuthority`, selective MFA, `validDuration`): https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/mfa.html
- Spring Security 7.0 API — `FactorGrantedAuthority`: https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/core/authority/FactorGrantedAuthority.html
- Spring Security 7.0 API — `EnableMultiFactorAuthentication`: https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/config/annotation/authorization/EnableMultiFactorAuthentication.html
- Spring Security — Authentication Persistence & Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — One-Time Token Login (Servlet): https://docs.spring.io/spring-security/reference/servlet/authentication/onetimetoken.html
- OWASP — Authentication Cheat Sheet, re-authentication for sensitive features: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP — Multifactor Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html
- OWASP — Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- NIST SP 800-63B-4 — Session Management and Reauthentication: https://pages.nist.gov/800-63-4/sp800-63b/session/

**Conclusion:** sensitive operations must prove **the right account, right permissions, right factors, sufficient freshness, right session, and right action**. Spring Security 7.x can enforce factor authorities and valid duration at the authorization layer, while transaction binding, one-time approval, business permissions, and idempotency still require explicit design in the application and storage layers.

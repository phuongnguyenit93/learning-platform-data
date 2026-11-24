# Multi-Factor Authentication and Tracking Achieved Authentication Level in Spring Security Servlet

## 1. The Problem: Successful Login Is Not Always Enough for Every Action

A web application using **Spring Security Servlet** can have multiple risk levels. A user logged in with a password may view their profile page, yet when transferring money, changing a recovery email, or adding an API key, the application needs **step-up authentication**. Once the user proves a second factor, the system must know **which factors were verified, when, for which identity, and in which session**, granting elevated access only for a finite duration.

**Multi-factor authentication (MFA)** proves identity using **two or more factors from independent categories**. Common categories:

| Factor Category | Examples | Key Points to Remember |
| --- | --- | --- |
| Something you know | Password, independent PIN | Two passwords do not automatically become two factor categories |
| Something you have | FIDO2 security key, passkey-holding device, TOTP generator app | TOTP usually ties to a secret on a device; email OTP has different properties and risks |
| Something you are | Biometric traits when used in an appropriate auth mechanism | Local passkey biometrics typically verify the user before the device signs a challenge; the server does not necessarily receive biometric data |

**MFA differs from simply adding another screen.** If the second step only asks a security question stored alongside the password, or an OTP can be received via the very email account that was just compromised, independence may be low. Likewise, do not equate “OTP” with “phishing-resistant”: **TOTP and SMS OTP can be phished onto fake websites; WebAuthn/FIDO2 with origin binding typically resists phishing better** when configured properly.

**Authentication** answers “who/what has been proven?” **Authorization** answers “what are they allowed to do?” MFA raises authentication assurance, but does not replace role-based permissions, resource-level checks, ownership checks, CSRF defense, XSS prevention, or anomaly monitoring.

Example policy you can design:

- `GET /profile`: requires a regular login session.
- `POST /payments`: requires a logged-in session **and** recently verified MFA evidence, plus payment authorization.
- `POST /security/disable-mfa`: requires strong authentication and a dedicated recovery workflow; never turn off MFA merely because a session cookie exists.
- `GET /admin/audit`: beyond MFA, may require an admin role, device compliance, and time-window policies.

The goal of this article is to understand **tracking achieved authentication assurance** in Spring Security Servlet and using that state for step-up within proper trust boundaries.

## 2. Distinguishing “Logged In,” “Has MFA,” and “MFA Still Fresh”

A session can move through multiple states:

~~~text
Unauthenticated
    │
    └─ Password/passkey/SSO succeeds
              ▼
     Initially authenticated
     (access only low-risk resources)
              │
              ├─ User chooses a sensitive action
              ▼
     Additional authentication required
              │
              ├─ Valid factor proven → record evidence
              ▼
      Step-up requirement met
      (allowed to proceed if still authorized)
              │
              ├─ Step-up window expires
              ├─ Account switch / new login
              ├─ Factor revoked / compromise suspected
              └─ Logout or session invalidated
              ▼
     Back to pre-step-up level
~~~

Two timestamps must stay separate:

1. **Session age:** a session may last 8 hours for viewing routine information.
2. **MFA evidence freshness:** a money-transfer policy might only accept a second factor verified within the **last 10 minutes**. That number is a policy example, not a mandatory Spring Security default.

If the second step succeeded at 09:00 and the user transfers money at 09:05, it may be fresh enough; at 10:00, step-up is required again even though the session remains logged in. This property is called **reauthentication freshness**. High-risk scenarios sometimes demand full re-authentication or transaction-specific approval rather than just “recent MFA.”

An access token containing `amr`/`acr` claims or an `Authentication` holding an authority for some factor **does not automatically** guarantee all the policies above; you must know who issued it, when authentication occurred, whether the token is still valid, and what the target policy expects.

## 3. Modeling Authentication Assurance Evidence

A server-side record may contain:

| Field | Purpose |
| --- | --- |
| `subjectId` | Stable identifier of the authenticated account (never trust a request-sent username) |
| `loginEventId` | Random ID of the primary login; prevents reusing MFA from a prior login |
| `factorId` / `factorType` | Verified factor, e.g., TOTP or WebAuthn; never store OTP codes |
| `verifiedAt` | Timestamp when the server verified the factor |
| `expiresAt` or policy TTL | When the evidence stops being sufficiently fresh |
| `context` (if needed) | Action scope, transaction, risk level, or method used |
| `assurancePolicyVersion` (if needed) | Enables revocation/re-evaluation when policies change |

**The source of truth must be established by the server**, never read from request bodies, query parameters, arbitrary headers, localStorage, modifiable cookies, or unverified JWT claims. For instance, a client sending `mfa=true` is untrusted input.

Distinguish clearly:

- **Enrolled factor:** the account has a TOTP secret or passkey.
- **Factor verified in this login:** the user actually completed the challenge step.
- **Recently verified factor:** evidence is still within the action’s time window.
- **Achieved assurance level:** policy combining factor types, count, independence, freshness, authentication source, risk context, and phishing resistance.

Do not infer “MFA achieved” just because a user has `mfaEnabled=true` in the database, nor because an `/mfa/verify` endpoint once returned HTTP 200 to a different browser.

### Error-Prone Boundaries

- **Same user, different login:** a new token/session must not inherit MFA markers from an old session merely by sharing a username.
- **Switching accounts in the same browser:** Alice’s MFA marker is invalid for Bob.
- **Logging in via remember-me:** a remember-me cookie may not provide evidence equivalent to a freshly entered password; many operations require `fullyAuthenticated` or re-authentication.
- **Password change, MFA reset, recovery factor change:** consider revoking old sessions and step-up evidence.
- **Multi-node cluster:** if sessions are distributed across servers, evidence must be handled consistently with TTL and revocation; never rely on static variables in a single JVM.

## 4. Where Does Spring Security Servlet Inspect Authentication Level?

In Spring Security, requests pass through the filter chain, load `SecurityContext` from the configured repository, and place `Authentication` into `SecurityContextHolder`. `Authentication` carries the principal, authorities, and authentication method details supplied by the provider. **Having `Authentication.isAuthenticated() == true` does not mean all MFA factors were satisfied.**

Representing assurance can vary by version and architecture:

1. **Factor authorities / built-in MFA mechanisms of your Spring Security version:** versions with support can mark proven factors and enforce multi-factor rules via authorization. Only assign a factor authority **after server-side verifier success**—never let clients add it. Check the exact docs and APIs for your deployed version.
2. **Server-side session evidence + AuthorizationManager:** the Servlet application stores session/login-bound evidence itself, then requires that evidence when sensitive routes are accessed. The learning example below illustrates this approach with Spring Security 6.x APIs.
3. **External OIDC/OAuth2:** an IdP may pass `acr` (authentication context class reference), `amr` (authentication methods references), and `auth_time` in suitable tokens. A resource server/client uses these claims only after **verifying token signature, issuer, audience, freshness, trust contract, and the IdP’s claim semantics**. Never trust frontend-crafted claims.

**Important:** with standard form login alone, Spring Security authenticates and treats the request as authenticated after the password step. When an application requires MFA on sensitive routes, add a **dedicated authorization rule** to block access until the second step finishes. Being “pre-MFA” is not a reason to skip permission checks or allow bypassing straight into API routes.

### Where to Enforce Step-Up?

For URLs, use `authorizeHttpRequests(...)` and an `AuthorizationManager<RequestAuthorizationContext>` or matching access expression. For business operations, add method-level authorization (e.g., `@PreAuthorize` or service checks) if the same action has multiple entry points such as controllers, message consumers, and scheduled jobs.

**Never protect only the frontend button.** Clients can call APIs directly. **Never check only in the controller and forget the service** if another RPC/job invokes the same functionality. Policy must be enforced at boundaries matching the architecture.

## 5. Session-Managed Step-Up Implementation Pattern in Spring Boot 3 / Security 6

The following pattern targets **Java 17+, Spring Boot 3.x, Spring Security Servlet (Spring MVC + session/form login)**. It demonstrates **server-side** authentication markers and MFA-freshness access control, **without implementing TOTP or FIDO2 algorithms itself**. In production, you must integrate a secure second-factor verifier, rate limiting, and secure credential storage.

Minimal Gradle dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

### 5.1. Server-Side Evidence Bound to the Login Event

File `MfaAssuranceService.java`, package `com.example.demo.security`. The application stores both the **primary authentication event** and the **MFA verification event** in the session. This is a sample pattern for session-based apps; do not use it in stateless APIs without redesigning the architecture.

~~~java
package com.example.demo.security;

import java.io.Serializable;
import java.time.Duration;
import java.time.Instant;
import java.util.Set;
import java.util.UUID;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.RememberMeAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;

@Service
public class MfaAssuranceService {

    private static final String PRIMARY_KEY =
        MfaAssuranceService.class.getName() + ".PRIMARY";
    private static final String MFA_KEY =
        MfaAssuranceService.class.getName() + ".MFA";
    private static final Duration MAX_AGE = Duration.ofMinutes(10);

    public record PrimaryEvent(String subject, String loginId)
            implements Serializable {}

    public record MfaEvidence(String subject, String loginId,
                              String factor, Instant verifiedAt)
            implements Serializable {}

    private static boolean hasStrongPrimary(Authentication auth) {
        return auth != null
            && auth.isAuthenticated()
            && !(auth instanceof AnonymousAuthenticationToken)
            && !(auth instanceof RememberMeAuthenticationToken);
    }

    // Call only after initial authentication succeeds on the server.
    public void onPrimarySuccess(HttpServletRequest request,
                                 Authentication auth) {
        if (!hasStrongPrimary(auth)) {
            throw new IllegalStateException("Primary auth required");
        }
        HttpSession session = request.getSession(true);
        session.removeAttribute(MFA_KEY);
        session.setAttribute(PRIMARY_KEY,
            new PrimaryEvent(auth.getName(),
                             UUID.randomUUID().toString()));
    }

    // Call only after the second verifier actually succeeds.
    public void recordFactor(HttpServletRequest request,
                             Authentication auth, String factor) {
        if (!hasStrongPrimary(auth)
            || !Set.of("totp", "webauthn").contains(factor)) {
            throw new IllegalStateException("Invalid MFA context");
        }

        HttpSession session = request.getSession(false);
        if (session == null) {
            throw new IllegalStateException("No login session");
        }
        Object primary = session.getAttribute(PRIMARY_KEY);
        if (!(primary instanceof PrimaryEvent login)
            || !login.subject().equals(auth.getName())) {
            throw new IllegalStateException("Login event mismatch");
        }

        session.setAttribute(MFA_KEY,
            new MfaEvidence(login.subject(), login.loginId(),
                            factor, Instant.now()));
    }

    public boolean hasRecentMfa(HttpServletRequest request,
                                Authentication auth) {
        if (!hasStrongPrimary(auth)) {
            return false;
        }
        HttpSession session = request.getSession(false);
        if (session == null) {
            return false;
        }
        Object primary = session.getAttribute(PRIMARY_KEY);
        Object mfa = session.getAttribute(MFA_KEY);
        if (!(primary instanceof PrimaryEvent login)
            || !(mfa instanceof MfaEvidence proof)) {
            return false;
        }

        Instant now = Instant.now();
        Duration age = Duration.between(proof.verifiedAt(), now);
        return login.subject().equals(auth.getName())
            && proof.subject().equals(login.subject())
            && proof.loginId().equals(login.loginId())
            && !age.isNegative()
            && age.compareTo(MAX_AGE) < 0;
    }
}
~~~

**Demonstrated properties:**

- `onPrimarySuccess(...)` clears old MFA evidence **every time password authentication succeeds** and generates a new `loginId`; it prevents the same user from reusing MFA from a prior login just because the session still holds an old attribute.
- `recordFactor(...)` never takes identity from a request body. It uses the server’s `Authentication` and requires a matching primary event for the same user in the session. `factor` is not taken arbitrarily from the request; internal callers pass only the factor name just verified by the verifier.
- `hasRecentMfa(...)` requires **same subject, same `loginId`, within 10 minutes**, not in the future, and primary authentication that is neither anonymous nor remember-me.
- The record stores only **factor type and timestamp**, never TOTP codes, TOTP secrets, WebAuthn private keys, or access tokens.

**Additions needed for production:** use an **immutable user ID** instead of `auth.getName()` if usernames can change; store proofs with policy versions and action context where needed; mark revocation on MFA reset/disable; and also test OAuth2 Login, SSO, password change, or custom authentication flows since the next section’s handler only hooks `formLogin`. Sessions alone do not prove device security or prevent XSS/cookie theft.

### 5.2. SecurityFilterChain Requiring MFA for Sensitive URLs

File `SecurityConfig.java` in the same package:

~~~java
package com.example.demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.SavedRequestAwareAuthenticationSuccessHandler;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, MfaAssuranceService assurance)
            throws Exception {

        SavedRequestAwareAuthenticationSuccessHandler next =
            new SavedRequestAwareAuthenticationSuccessHandler();

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/error", "/login").permitAll()
                .requestMatchers("/mfa/**").fullyAuthenticated()
                .requestMatchers("/sensitive/**").access(
                    (authentication, context) ->
                        new AuthorizationDecision(
                            assurance.hasRecentMfa(
                                context.getRequest(),
                                authentication.get())))
                .anyRequest().authenticated())
            .formLogin(form -> form
                .successHandler((request, response, authentication) -> {
                    assurance.onPrimarySuccess(request, authentication);
                    next.onAuthenticationSuccess(
                        request, response, authentication);
                }))
            .logout(logout -> logout.invalidateHttpSession(true));

        return http.build();
    }
}
~~~

This is a class inside a Spring project, **not a standalone JDK program**. URIs are illustrative: `/sensitive/**` must be adapted to real sensitive APIs.

Control flow:

1. After form login, Spring Security verifies the password and creates the `SecurityContext`. The success handler clears old MFA, records the primary login event, and forwards to the standard form-login success handler.
2. `/mfa/**` is restricted to fully authenticated users, **excluding remember-me**; without an authenticated session, the system requires logging in first. For different apps or mechanisms, configure equivalent access rules.
3. Requests to `/sensitive/**` pass only when the server confirms recent valid MFA evidence; other routes still require login.
4. `AuthorizationDecision(false)` on sensitive URLs typically results in **403** for an already logged-in user. The frontend can direct the user to a step-up screen per application contract instead of treating it as a system error. Avoid creating MFA redirect loops.
5. Business policies such as `hasAuthority("PAYMENT_WRITE")` must still be combined with MFA, e.g., via method-level authorization or a combined manager; **MFA alone does not prove the user is authorized to perform an action**.
6. This is a **form login** example; if the system supports OAuth2 Login, SAML, or custom `AuthenticationProvider`s, hook primary-event refreshes into **every** login and principal change. Otherwise, MFA markers may become stale or valid requests may be blocked.

**CSRF remains enabled by default.** Never call `csrf().disable()` just because you added an MFA step: browsers using session cookies automatically send cookies in many contexts, so state-updating POST endpoints also require CSRF protection.

### 5.3. Verifying the Second Factor Before Recording the New Level

Example server-side contract for TOTP:

~~~java
package com.example.demo.security;

public interface TotpVerifier {
    // Returns true only after verifying the code is valid and not reused.
    // Real implementations must store secrets securely, rate-limit, and
    // prevent replay per time step.
    boolean verifyAndConsume(String subject, String code);
}
~~~

This is an interface for a **real TOTP verification implementation**, not a standalone runnable verifier. The application must supply a secure bean implementation; never “demo” by returning `true` for every code, hardcoding `123456`, or checking client-supplied values without a server-side secret.

The controller accepts POST and calls the verifier; only after verification succeeds does it elevate state:

~~~java
package com.example.demo.security;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class MfaController {

    private final TotpVerifier verifier;
    private final MfaAssuranceService assurance;

    public MfaController(TotpVerifier verifier,
                         MfaAssuranceService assurance) {
        this.verifier = verifier;
        this.assurance = assurance;
    }

    @PostMapping("/mfa/verify")
    public ResponseEntity<Void> verify(
            @RequestParam("code") String code,
            Authentication authentication,
            HttpServletRequest request) {

        if (code == null || !code.matches("[0-9]{6,8}")
            || !verifier.verifyAndConsume(
                authentication.getName(), code)) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Verification failed");
        }

        // After MFA succeeds, rotate session ID if a session already exists.
        // This is an additional defense layer; session cookies still need protection.
        request.changeSessionId();
        assurance.recordFactor(request, authentication, "totp");
        return ResponseEntity.noContent().build();
    }
}
~~~

In a real system, `TotpVerifier` must enforce attempt limits, prevent reusing the same code within the same time window, keep synchronized clocks, and protect secrets. Codes may be valid within ± one clock step, yet the verifier must **reject repeats** when policy forbids reuse; apply rate limiting by user, IP/risk signals, and device as appropriate. Public error messages should be generic; logs must not contain codes.

Since the request uses a form body, valid requests typically carry `Content-Type: application/x-www-form-urlencoded` and a CSRF token per Spring Security. **Clients must never set the MFA flag directly** by calling a “markSuccess” endpoint. Only a trusted controller calls `recordFactor(...)` after verifier success.

In multi-factor models, a WebAuthn verifier must check **challenge, origin, RP ID, signature, credential public key, user verification when policy requires it, and anti-replay** before recording `"webauthn"`. Never assign the WebAuthn label simply because the browser sent `factor=webauthn`.

### 5.4. Why Not Just Add ROLE_MFA to UserDetails?

A static `ROLE_MFA` in the account database may reflect **MFA enrollment**, but does not prove the **current login** passed a second factor. If the role is granted immediately after the password step, users can reach sensitive routes without stepping up.

If choosing a factor-authorities model in Spring Security, grant the authority only after **real evidence**, and ensure it is cleared/re-evaluated on expiration, logout, principal change, credential revocation, and policy rules. With session evidence as shown above, authorities do not need mutating on each step-up; `AuthorizationManager` checks evidence at request time.

## 6. Pure Java 17 Example on Freshness and Independent Factors

This example **runs on JDK 17+ without Spring** to teach the rule: *having two factor types does not mean they stay fresh forever*. It **does not perform authentication** and cannot replace a server-side verifier.

File `AssuranceDemo.java`:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.EnumSet;
import java.util.Set;

public class AssuranceDemo {
    enum Factor { PASSWORD, TOTP, WEBAUTHN }

    record Evidence(String user, Set<Factor> factors,
                    Instant lastStepUp) {
        boolean meetsPolicy(String currentUser, Instant now) {
            Duration age = Duration.between(lastStepUp, now);
            return user.equals(currentUser)
                && factors.contains(Factor.PASSWORD)
                && (factors.contains(Factor.TOTP)
                    || factors.contains(Factor.WEBAUTHN))
                && !age.isNegative()
                && age.compareTo(Duration.ofMinutes(10)) < 0;
        }
    }

    public static void main(String[] args) {
        Instant t = Instant.parse("2026-01-01T12:00:00Z");

        Evidence onlyPassword = new Evidence(
            "alice", EnumSet.of(Factor.PASSWORD), t);
        Evidence twoFactors = new Evidence(
            "alice",
            EnumSet.of(Factor.PASSWORD, Factor.TOTP), t);

        System.out.println(
            onlyPassword.meetsPolicy("alice", t.plusSeconds(30)));
        System.out.println(
            twoFactors.meetsPolicy("alice", t.plusSeconds(30)));
        System.out.println(
            twoFactors.meetsPolicy("alice", t.plusSeconds(601)));
        System.out.println(
            twoFactors.meetsPolicy("bob", t.plusSeconds(30)));
    }
}
~~~

Run:

~~~bash
javac AssuranceDemo.java
java AssuranceDemo
~~~

**Exact** stdout:

~~~text
false
true
false
false
~~~

The first line lacks an independent factor; the second has password + TOTP and is still fresh; the third exceeds 10 minutes; the fourth is a different user. In production, you also need to bind evidence to the **login event, session, issuer/trust context, policy, and actual factor verification**, as in Section 5’s sample configuration.

## 7. Common MFA Factors and Safe Handling

### 7.1. TOTP

TOTP (Time-based One-Time Password) usually produces a short code from a secret and time step. A proper implementation requires:

- A unique random secret per user/device, issued through a strongly authenticated enrollment flow and confirmed before activation.
- Server-side protection of the secret (encryption, restricted access); never log QR provisioning URIs or secrets.
- Standard TOTP algorithm and synchronized clocks; accept only a narrow clock-skew window when policy allows.
- **Brute-force and replay protection**: finite attempt limits, preventing reuse of consumed codes; concurrency control when two requests send the same code.
- Secure reset/recovery workflow, revoking enrollments on device replacement, alerts on factor changes.
- Prevent attackers from enrolling their own factor after compromising only a low-assurance session.

TOTP adds a secret-possession factor, but **is not completely phishing-resistant**. A spoofed website can capture the code while valid and use it immediately; high-risk transactions may therefore require WebAuthn or transaction-bound approval.

### 7.2. WebAuthn/FIDO2 and Passkeys

WebAuthn uses public-key cryptography, challenges, and binding to **relying party ID/origin**. When appropriate and properly configured, this factor reduces phishing risk compared to manually entered OTP codes. A passkey method can provide strong authentication with user verification; do not blindly infer “two factors” merely from a biometric prompt appearing.

Verify registration/assertion, one-time challenges, origin, RP ID, signature, credential ID, credential status, and user verification per policy, while protecting user data. **Never accept `"webauthn_success=true"` from the frontend.** Passkey syncing, shared devices, recovery, and the threat model affect actual assurance levels.

If primary authentication already used a strong passkey with user verification, policy may deem it sufficient for certain actions **without** requiring password + TOTP; that is a standards- and risk-based assurance choice, not a rigid “two screens = MFA” rule.

### 7.3. SMS, Email OTP, and Recovery Codes

SMS OTP faces SIM-swap, number-porting, interception, and phishing risks; email OTP depends on mailbox security and may not be independent of primary login. Never label every OTP method as having the same trust level.

**Recovery codes** must be generated with a secure random source, downloadable/storable once, stored hashed/appropriately protected, and consumed once; they are a **recovery mechanism** that can be weaker than standard MFA methods. After using recovery, apply additional verification steps, alerts, and require re-enrolling factors.

Never turn a “lost MFA device” flow into guessable security questions or unguarded email links. Changing/resetting MFA must defend against account takeover; it may require waiting periods, multi-channel notifications, identity verification, and risk-based session revocation.

## 8. Multi-Factor Authentication in OIDC and External Providers

In systems where an **Identity Provider** handles MFA (OIDC, SAML...), the Servlet application may not implement TOTP/WebAuthn itself. Instead, it reads results from a **trusted** provider under an authentication contract.

Common OIDC claims:

- `amr`: list of authentication methods used, per provider conventions.
- `acr`: authentication context class assured by the provider; **not a universal numeric scale** with identical meaning across all IdPs.
- `auth_time`: time of end-user authentication in the relevant token/context; distinct from `iat` (when the token was issued).

**Do not trust** JWTs without signature verification or browser-crafted headers like `X-AMR: mfa`. When receiving tokens, verify issuer, audience, expiry, nonce where applicable, signature, and the `acr/amr/auth_time` contract. If the provider supports step-up, the client can request re-authentication (e.g., via `max_age` or `acr_values` per the IdP contract), yet **never assume** every IdP enforces MFA or returns the same claims.

A newly issued token **does not mean the user just performed MFA**; a fresh `iat` can simply come from a refresh-token exchange while `auth_time` is old. For resource servers, distinguish verified authentication context claims from business permissions on endpoints.

You can reference **Authentication Assurance Level (AAL)** concepts like AAL1/AAL2/AAL3 from NIST standards when compliance requires it, but **do not mechanically map** `password+OTP = AAL2` or `passkey = AAL3`. Full authenticator properties, phishing resistance, verifier behavior, lifecycle, and standard requirements must be met.

## 9. When to Require Step-Up and Scope of Evidence

**Route-based step-up:** every request to `/sensitive/**` requires fresh MFA. Simple and easy to test, though it can prompt repeatedly if the TTL is too short.

**Action-based step-up:** e.g., changing payout accounts, exporting personal data, or disabling account protections. Can require MFA right before the action (transaction authorization), avoiding reusing one proof across a batch of high-risk operations.

**Risk-signal step-up:** unfamiliar devices, anomalous IPs, high-velocity behavior, admin privileges, or recent account recovery events. However, do not rely solely on fingerprints/IPs since they can change or be spoofed; policies must avoid excessive friction and protect privacy.

**Action-bound approval** ensures the user sees the exact amount/recipient/action and confirms via a transaction-bound challenge; a generic TOTP code does not automatically bind to transaction details. For financial/sensitive systems, consider cryptographic transaction-bound approvals, attempt limits, and anti-replay.

Recording MFA must occur **only after the verifier returns success**, never when displaying a QR code, when the user clicks “verified,” or when an invalid code is submitted.

## 10. Preventing MFA State Bugs in Sessions

| Design Bug | Consequence | Fix |
| --- | --- | --- |
| Storing `mfa=true` in localStorage or unsigned cookies | Client edits state to bypass step two | Store server-side evidence or strictly signed/verified tokens with proper bindings |
| Checking only `mfaEnabled` in DB | Password-only user reaches sensitive endpoints | Distinguish enrolled from verified in the current session |
| MFA evidence lacks `loginEventId` | MFA marker can be reused after another login in the same session | Clear after every primary login, bind to login event |
| Keeping evidence forever for the cookie’s lifetime | Stale step-up still permits sensitive actions | TTL/last verified, require re-auth per policy |
| Omitting MFA check when requests hit API directly | Frontend/UX bypass | Enforce server-side via `AuthorizationManager` or service layer |
| Recording MFA before verifier completes | Accepts bad factors or race conditions | Record only after verification and challenge consumption succeed |
| No anti-replay for TOTP codes | A stolen code works repeatedly within the time window | Track used codes/timesteps, handle concurrency and rate limiting |
| Treating remember-me as fresh primary auth | Bypasses current password requirement | Require `fullyAuthenticated`/reauthentication per policy |
| MFA proof not bound to subject | Alice’s MFA marker used for Bob | Bind subject + login + session |
| Using MFA in place of `hasAuthority` | Normal user with MFA performs admin actions | Combine MFA with role/ACL/tenant checks |
| Rotating session ID only on primary login without protecting cookies | Session theft or XSS can still hijack sessions | HTTPS, `Secure`/`HttpOnly`/`SameSite`, CSP, and XSS/CSRF defenses |
| MFA reset via compromised email | Attacker bypasses strong factor | Strict recovery workflow, alerts, and session revocation |
| Hiding policy while returning overly detailed errors | Leaks accounts, enrolled factors, MFA timing | Sufficiently generic messages; never leak secrets or enable enumeration |

### When a Session Is Lost or Revoked

From the server’s perspective, when `HttpSession` does not exist, `PRIMARY_KEY` or `MFA_KEY` is not reliably restored, or evidence mismatches the user/login, default to **fail closed**: treat step-up as unmet. The application can prompt the user to re-authenticate; never synthesize evidence from old frontend state.

When using `Spring Session` with Redis/JDBC, ensure proper serialization/versioning, TTL, session deletion on logout, and cluster-wide rule synchronization. Re-authentication triggers for password resets, admin revocations, and factor resets must propagate across all nodes rather than only a local cache.

## 11. Testing and Diagnostics

### 11.1. Acceptance Test Matrix

| Precondition | Path | Expected Outcome |
| --- | --- | --- |
| Not logged in | `GET /sensitive/summary` | Authentication required, no data returned |
| Password entered, no MFA yet | `GET /sensitive/summary` | Blocked / step-up required |
| Password entered, wrong TOTP | `POST /mfa/verify` | Generic error, no MFA evidence recorded |
| Password entered, valid unused TOTP | `POST /mfa/verify` | Verification succeeds, proof bound to current login saved |
| MFA just completed, user authorized | `GET /sensitive/summary` | Proceeds to controller/service |
| MFA TTL expired | `GET /sensitive/summary` | Step-up required again |
| Different user logs in within same browser | `GET /sensitive/summary` | Old evidence invalid |
| Logout or session expired | `GET /sensitive/summary` | Old evidence cannot be reused |
| Authenticated via remember-me | `GET /mfa/verify` or sensitive route | Stronger authentication required per policy |
| User lacks business permission despite MFA success | `POST /sensitive/payment` | Still denied by business authorization |
| MFA POST without CSRF token when using cookies | `POST /mfa/verify` | Blocked by CSRF protection |
| Two concurrent requests using same OTP | `POST /mfa/verify` | Verifier accepts only per anti-replay policy |

Do not test only HTTP 200/403. Verify **whether session evidence is actually created/cleared**, TTLs, resource permissions, post-login session state, and that MFA markers never cross user boundaries.

### 11.2. Unit Testing the Session Model and Clock

For the `MfaAssuranceService` pattern, unit tests should cover:

1. `onPrimarySuccess` creates a new `loginId` and clears proof from the previous login.
2. `recordFactor` rejects when there is no primary event or the principal mismatches.
3. `hasRecentMfa` returns false when session is null, remember-me, different subject, different `loginId`, future timestamp, or over 10 minutes elapsed.
4. Recording a factor is invoked only after the TOTP/WebAuthn code is accepted by the verifier.
5. Under concurrent requests, the verifier ensures a one-time code is not consumed twice.

To test TTL boundaries deterministically, in production inject `java.time.Clock` into services and use `Clock.fixed(...)` in tests rather than relying on wall-clock time. Section 5 uses `Instant.now()` for readability; for complex apps, extract clock and policy into dependencies.

### 11.3. MockMvc and Integration Testing

With Spring Security Test, `MockMvc` can verify routes and CSRF. Illustrative **snippet inside a test class with MockMvc configured and mocked principal**:

~~~java
mvc.perform(post("/mfa/verify")
        .with(user("alice"))
        .param("code", "123456"))
    .andExpect(status().isForbidden()); // Missing CSRF token
~~~

To use this snippet in a test, you need static imports `MockMvcRequestBuilders.post`, `SecurityMockMvcRequestPostProcessors.user`, and `MockMvcResultMatchers.status`, plus an injected `mvc`. If using `@WebMvcTest` or `@SpringBootTest @AutoConfigureMockMvc`, verify your `SecurityFilterChain` is actually active. `user("alice")` is a helper creating a **mock principal in tests** and does not prove password or MFA ran. Code `123456` is dummy data; it does not produce valid authentication unless the real verifier accepts it.

Then add tests with `.with(csrf())`, mocking verifier acceptance/rejection, preserving sessions across requests, checking 403 before step-up, and verifying expected outcomes after step-up. Real applications also need integration tests through browsers, proxies, HTTPS, CSRF cookies/sessions, and real MFA providers.

### 11.4. Logging and Error Messages

Logs should capture **events** (step-up started, succeeded/failed, expired, factor reset, session revoked) with protected subject ID, factor type, correlation ID, timestamp, and policy ID. Never log TOTP codes, QR secrets, WebAuthn private keys (never on the server anyway), recovery codes, session cookies, or access tokens.

For end users, reasonable messages are “Additional authentication required” or “Unable to verify code” without disclosing enrolled factors, expected digit counts unnecessarily, or sensitive account states. Rate limiting, temporary lockouts, and recovery support must avoid creating account enumeration channels.

## 12. Production Design Checklist

- [ ] Clearly distinguish **enrolled** factors from **proven** factors in the current login.
- [ ] Choose factor types independent and strong enough for action risk; prefer phishing-resistant MFA where appropriate.
- [ ] Mark MFA only after accurate backend verification and anti-replay checks.
- [ ] Evidence includes **subject, loginEventId, factor type, timestamp, TTL** and is checked server-side.
- [ ] On new primary login, account switch, logout, factor reset, or revocation events, old evidence is no longer accepted.
- [ ] Sensitive URLs, services, and actions are all server-protected; MFA is combined with role/ACL/tenant authorization.
- [ ] Never allow remember-me or stale sessions to automatically satisfy high reauthentication requirements.
- [ ] Session cookies use HTTPS, `Secure`, `HttpOnly`, appropriate `SameSite`; keep CSRF protection and XSS defenses.
- [ ] TOTP/OTP has rate limiting and brute-force/replay protection; WebAuthn verifies origin/RP ID/challenge/signature.
- [ ] OIDC `acr/amr/auth_time` are trusted only after verification and issuer contract checks; never confuse token `iat` with fresh MFA.
- [ ] MFA enrollment/recovery/reset/disable have dedicated security policies and user alerts.
- [ ] Test success paths, fail-closed paths, expired evidence, session rotation, account switching, CSRF, and proxies/clusters.
- [ ] Never log secrets, recovery codes, OTPs, JWTs/cookies, or sensitive evidence; restrict access to metrics/audit logs.

**Conclusion:** “Authenticated” is not a single binary state for every action. Spring Security Servlet can use authentication/factor authorities or **server-side MFA evidence bound to the login event** to know which authentication level a user achieved and whether it remains sufficiently fresh. Only when evidence is valid **and** business permissions match may sensitive APIs run; policies must fail closed when evidence is missing, stale, or revoked.

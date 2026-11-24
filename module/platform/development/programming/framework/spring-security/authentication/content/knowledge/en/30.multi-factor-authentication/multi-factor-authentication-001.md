# MFA, Two-Step Login, and Independence of Authentication Factors

> **Scope:** Spring Security – Authentication, **Multi-Factor** topic. This article focuses on the essence of multi-factor authentication (MFA), the difference between **two-step** verification and **two independent factors** verification, login/step-up flow design, implementation risks, and how to integrate in Spring Security. Examples target Java 17+, Spring Boot 3.x / Spring Security 6.x; built-in MFA support is explicitly noted as **Spring Security 7.x**, typically paired with Spring Boot 4.x.

## Learning Objectives

After this article, you can:

1. Distinguish **authentication**, **authorization**, **two-step verification (2SV)**, **two-factor authentication (2FA)**, and **MFA**.
2. Classify **knowledge**, **possession**, and **inherence** evidence; prove why two authentication prompts do not necessarily mean two factors.
3. Evaluate **practical independence**: whether factors belong to different categories, whether they can be compromised by the same incident, and whether they can be bypassed by recovery flows, devices, email, SMS, or sessions.
4. Design step one/step two with **session binding**, expiration, retry limits, one-time verification, proper state transitions, and without granting sensitive permissions before sufficient evidence is provided.
5. Understand the benefits of **FIDO2/WebAuthn** with origin/RP ID verification compared to manually entered OTPs that are vulnerable to phishing relay; choose risk-based step-up approaches.
6. Recognize Spring Security version differences: **6.x requires designing/wiring MFA appropriately**; **7.x** provides `FactorGrantedAuthority` and `@EnableMultiFactorAuthentication`.
7. Build tests that verify both **factor count** and **independence** and **evidence provenance**, not just valid/invalid OTP tests.

## 1. What Do Authentication and MFA Solve?

**Authentication** is the process of verifying evidence to conclude that a principal genuinely controls a registered identity or authenticator. **Authorization** decides what an authenticated identity is allowed to do on the current resource. MFA raises the confidence level of the authentication step; it does not automatically grant `ROLE_ADMIN` or bypass API permission rules.

For example: an application has an account `lan`, assigned `ROLE_ACCOUNTANT` and owning a TOTP authenticator. When logging in:

```text
lan's browser
    │ 1) Enter username + password (KNOWLEDGE factor)
    ▼
Spring Security / AuthenticationManager
    │ 2) Verify password, identify user lan
    │    DO NOT yet grant access to features requiring MFA
    ▼
Pending MFA challenge (server-side)
    │ 3) Request registered authenticator
    ▼
TOTP app / security key / passkey
    │ 4) Provide second-factor evidence
    ▼
MFA verifier
    │ 5) Verify, bind to the same lan and challenge
    │ 6) Prevent replay, check validity and attempt count
    ▼
Complete appropriate Authentication / elevate session assurance level
    │ 7) Session fixation protection and persist required state
    ▼
Authorization
    ├─ User has ROLE_ACCOUNTANT and MFA requirement is met → allow
    └─ Missing resource permission / session revoked → deny
```

Never use a browser-sent variable such as `mfaPassed=true` as the basis for completing step two. Evidence must be **verified by the server or a trusted verifier**, bound to the same user/session/request and time.

### Authentication Is Not Synonymous with “MFA Completed”

An `Authentication.isAuthenticated() == true` in Spring Security usually indicates that **the current authentication mechanism has succeeded**; that value does not by itself prove two independent factors were satisfied. In a password-only application, `UsernamePasswordAuthenticationToken` after password verification can also be authenticated. Therefore, APIs requiring MFA must have a specific **authorization rule** or MFA gate, not merely check `authenticated()`.

## 2. Two-Step Verification (2SV) Differs from Two-Factor Authentication (2FA/MFA)

**Two-step verification (2SV)** is a UX arrangement: the user performs **two actions / two inputs**. It does not by itself indicate how many factor categories the evidence belongs to.

**2FA** is the case of MFA with **two independent factor types**. MFA in general has **at least two factors from different categories**, or a multi-factor authenticator designed/validated to require multiple factors simultaneously. What matters is the **nature of the evidence**, not the number of screens, forms, OTPs, or button clicks.

| Flow | Steps | Is it MFA? | Why |
|---|---:|---|---|
| Password, then a pre-sent PIN that the user memorizes | 2 | **No** | Password and PIN are both knowledge |
| Password then security question (“first school?”) | 2 | **No** | Both are knowledge, and easy to guess/exploit |
| Password entered twice on two pages | 2 | **No** | Still only one knowledge factor |
| Password + TOTP from a registered authenticator | 2 | **Can be MFA** | Password is knowledge; registered TOTP key represents possession; depends on key storage/anti-compromise design |
| Password + FIDO2 security key | 2 | **Yes, when two separate factors are genuinely used** | Knowledge + proof of private key possession and origin/RP ID verification |
| Password + SMS OTP | 2 | **Can count as two factor types, but weaker** | Phone number/SIM channel has risks of SIM swap, interception, phishing; NIST classifies PSTN OOB as restricted |
| Password + email code/link | 2 | **Should not automatically be considered strong MFA** | Mailbox may be protected by the same password; NIST 800-63B-4 **forbids using email as an out-of-band authenticator** for standard compliance |
| Login with a passkey having user verification (PIN/biometric on authenticator) | Can be 1 interaction | **Can be a multi-factor authenticator** | Proof of key possession and user verification action at the authenticator; must check WebAuthn flags/policy |
| Password + corporate IP address | 2 conditions | **No** | IP is a contextual signal/network restriction, not an identity authentication factor |
| Password + CAPTCHA | 2 steps | **No** | CAPTCHA is an anti-bot measure, not evidence of possessing an authenticator |
| Two push approvals on an already-compromised app | 2 times | **Adds no independent factor** | Both actions merely reuse the same compromised surface |

**Be careful with the term “OTP”:** an OTP can be *a security number sent via SMS/email*, *TOTP based on an app secret*, or *hardware OTP*. They have different threat models. A six-digit number does not by itself mean an independent possession factor, does not inherently resist phishing, and does not prove a separate device.

## 3. Three Categories of Authentication Factors and Evidence Provenance

### 3.1. Something You Know — Knowledge

Examples: password, PIN used for remote login, passphrase.

- **Risks:** guessing, phishing, credential stuffing, keylogger, reuse, or social engineering.
- **Proper verification:** the server matches against an appropriate password hash (Argon2id/bcrypt/PBKDF2 per policy), with password guessing rate limits; never store plaintext.
- **Two different passwords are still only one category:** an attacker can obtain both from a password manager, phishing, or malware.

Distinguish between a PIN **sent to the server to log in** (knowledge factor) and a PIN **used only locally on the device to unlock a private key** (activation secret for a multi-factor cryptographic authenticator). The latter implementation can be part of a multi-factor authenticator; do not conclude based solely on the word “PIN”.

### 3.2. Something You Have — Possession

Examples: FIDO2 security key, protected private key/certificate, hardware OTP, authenticator app with a registered TOTP secret, verified OOB device.

- **Evidence:** proving authority to use a key/device already bound to the right account. Do not merely check a client-declared “deviceId” string.
- **Risks:** loss, malware control, SIM swap, TOTP seed theft, key cloning, push fatigue, weak recovery, relayed tokens.
- **Secure enrollment:** bind the authenticator to the local user after a session with appropriate assurance; protect factor enrollment/change/removal.

Typing a TOTP on the same phone used to log in **does not automatically invalidate MFA**: it can still provide a separate registered possession secret. However, if both the password and TOTP seed reside in the same place compromised by malware, **practical independence against attack drops significantly**. One must distinguish “different factor types” from “having no shared point of failure”.

### 3.3. Something You Are — Inherence

Examples: fingerprint, face recognition, or iris when verified by a trusted authenticator.

- **Subtlety:** a facial photo uploaded by the browser or a JavaScript event `"fingerprint passed"` **is not by itself secure evidence** for the server. One must rely on a trusted authenticator/API with challenge, signature, and bound verification results.
- In FIDO2/WebAuthn, biometrics are typically **verified locally** to unlock the key and do not require sending biometric data to the Spring backend.
- Difficult to revoke/change biometrics after a data leak; storage and privacy design must be careful.

### 3.4. Location, Risk Score, and Behavioral Signals

Geolocation, device fingerprint, IP allowlist, unusual access time, and behavioral history are useful **risk signals** to raise security requirements or reject requests. According to NIST 800-63B-4 and OWASP classification, these signals **do not replace separate authentication factor evidence**. “Password + being in the office” is not MFA.

## 4. What Layers Does “Independence” Have?

The design question is not just “are there two different factor labels?”, but whether **the same attacker can bypass both through a single compromise**.

### 4.1. Independence of **Evidence Type**

Password and PIN are both knowledge. Password and TOTP have two nominal factor types. Password with a security key has knowledge + cryptographic possession. For a multi-factor passkey, one must inspect the **user verification (UV)** mechanism (PIN/biometric) and private key authentication: not every WebAuthn assertion guarantees UV.

### 4.2. Independence of **Secrets and Storage Devices**

If the password and TOTP seed are exported together to an unencrypted backup, a backup breach breaks both. If a password manager and TOTP app sit on the same rooted/malware-infected phone, a device attack can extract both the password and the OTP. Categorizing knowledge/possession does not eliminate shared-surface risk.

A stronger option for admin accounts is a **hardware-backed WebAuthn credential** (non-exportable key, appropriate user verification) or a managed device with clear boundaries. Not every passkey is device-bound: **synced passkeys** have different backup/sync mechanisms; assurance requirements and enterprise policy must be checked.

### 4.3. Independence of **Transport Channel and Session**

An SMS OTP displayed in a notification on the same compromised phone is not independent of an attacker-controlled session. A phishing site can ask for both password and OTP, then forward both in real time to the real website (adversary-in-the-middle). Manually entered OTP can be MFA, yet it is **not phishing-resistant**.

Proper FIDO2/WebAuthn binds the authentication response to **origin and RP ID**, preventing an attacker from replaying an assertion from a fake domain on the real domain. Challenge, RP ID hash, origin, signature, and user presence/user verification flags must be verified according to policy. Do not treat those checks as optional.

### 4.4. Independence of **Account Recovery**

A system requiring password + security key at login, yet supporting “I lost my key” merely by answering a security question or receiving an email link to a mailbox sharing the same password — an attacker can take the bypass route. MFA is undermined by **reset, device replacement, factor addition, and helpdesk flows**. This is one of the most easily overlooked areas during testing.

### 4.5. Independence of **Identity**

Two pieces of evidence belonging to two different people do not form MFA for one user. For example, `lan`'s password with `minh`'s OTP seed. The server must match the **same local account ID**, the exact authenticator registered for that account, and the right challenge/session and timestamp.

## 5. Ranking Methods by Specific Risks

| Method | Benefits | Risks & Limitations | Typically Reasonable Choice |
|---|---|---|---|
| Password + WebAuthn security key | Two factor categories, origin binding/phishing resistance | Lost key, enrollment/recovery flow, unsupported devices | Administrators, high-impact operations |
| Multi-factor passkey with user verification | Convenient UX, cryptographic, origin bound | Passkey sync/recovery, device assurance level, UV verification | Passwordless with clear policy |
| Password + TOTP app | Widely deployed, offline after enrollment | OTP relay phishing, copied seed, replay, time drift | Chosen when WebAuthn cannot yet be deployed |
| Password + push app with number matching | Convenient and can bind to session | MFA fatigue, phone malware, push proxy | With rate limits and transaction confirmation |
| Password + SMS OTP | Available to many users | SIM swap, interception, roaming, phishing; PSTN OOB restricted | Fallback with risk assessment, without weakening the primary path |
| Password + email OTP | Simple operation | Mailbox may share password, forwarding, weak account recovery; NIST does not recognize email OOB | Do not treat as a NIST-compliant MFA method; typically used for email verification/recovery per policy |
| Password + second password | Easy to explain in UI | Not MFA, same knowledge category | Do not use to satisfy MFA requirements |
| Password + device cookie | Helps recognize known devices | Cookie can be copied, does not prove independent possession | Risk signal only, does not replace device proof |

**Do not infer AAL solely from factor count.** NIST SP 800-63B-4 also specifies authenticator types, secret protection, replay resistance, reauthentication, phishing resistance, and operational requirements. A website with two OTP boxes does not automatically achieve AAL2. In particular, email **is prohibited as out-of-band authentication under NIST 800-63B-4**, even though application implementation docs sometimes present an email code as a second step; UX must be distinguished from standard compliance.

## 6. State Model: Do Not Grant Full Privileges After Step One Alone

A web flow typically has these states:

```text
ANONYMOUS
    │ verify password
    ▼
PRIMARY_VERIFIED / MFA_PENDING
    │ temporary server-side challenge (short TTL)
    │ ├─ wrong OTP / replay / timeout → deny, throttling
    │ └─ verify registered second authenticator, same user
    ▼
MFA_COMPLETE
    │ rotate session ID / issue final Authentication
    │ authorization still checks roles and resources
    ▼
ACCESS_TO_ALLOWED_ENDPOINTS
```

**MFA_PENDING must not be treated as MFA completed.** There are two valid models, but they must be explicit:

1. **Do not create full SecurityContext yet:** After password verification, store a server-side challenge with TTL and a restricted intermediate session; only when step two succeeds create the full Authentication and rotate the session. Suitable when all endpoints require MFA.
2. **Allow a step-one authenticated session with restricted permissions:** The application has a Spring `Authentication` from password login, but sensitive endpoints require another **MFA-complete** condition. Basic pages may be served, yet `/admin/**` must never be opened with just `authenticated()`.

Do not create `ROLE_ADMIN` or copy all authorities onto a “partial principal” and then misconfigure rules. Once MFA completes, **authorization must still check role/tenant/ownership** at the endpoint.

### 6.1. What Should Challenge Data Contain?

An example server-side record:

```text
challenge_id       = random, unguessable
local_user_id      = immutable ID (not email)
session_binding    = server-generated session reference
primary_verified_at= ...
expected_method_id = authenticator already bound to user
purpose            = "LOGIN_MFA" / "STEP_UP_PAYMENT"
expires_at         = short, enforced on server
attempts_left      = bounded
consumed_at        = null until success
risk_context       = policy-derived, not client-supplied
```

Session/challenge IDs must also be protected against session fixation. Do not read `userId` from the request body to switch to someone else, have no `?mfaPassed=true` query parameter, and do not accept an OTP from an unregistered authenticator. If using Redis/DB across multiple nodes, update `consumed_at` or success state **atomically** so two requests cannot consume the same challenge simultaneously.

### 6.2. What Must Be Verified in Step Two

1. The challenge exists, is unexpired, unconsumed, and belongs to the **same user/same purpose** authenticated in step one.
2. The corresponding authenticator is registered for that user and has not been revoked.
3. The evidence is genuinely checked by the **verifier**: TOTP/HOTP secret, WebAuthn signature, or verified IdP `acr/amr` result; never trust client self-reported data.
4. Guess rate limiting and retries by user/challenge/IP and risk signals. Six-digit codes require brute-force protection.
5. Replay is blocked. With TOTP, never accept the same code/time step a second time while the code remains valid; enforce atomically across multiple nodes.
6. Preserve strict ordering: only upon success grant `mfa_complete` and persist the appropriate Authentication/session; emit an audit event.
7. On failure/timeout/logout/account switch, the old challenge is revoked. Never transition from MFA_PENDING to MFA_COMPLETE via an error/fallback path.

Do not **name** a custom header `X-MFA-Verified: true` and trust it from the browser. If an upstream IdP/gateway ensures MFA, establish an explicit trust boundary with anti-header-spoofing, verify signatures/policy, and correlate with the current subject.

## 7. TOTP: Example of a Possession Factor Vulnerable to Phishing

TOTP (RFC 6238) generates time-based codes from a **registered secret** and a time step (typically around 30 seconds). The client authenticator and server share the secret, compute an HMAC, and truncate it into a numeric OTP. The server must protect the seed, allow a small clock skew per policy, limit retries, prevent replay, and check user binding.

```text
Password verified on server      → KNOWLEDGE factor
TOTP app with registered secret  → POSSESSION evidence
Both results belong to local_user_id = 42
                       │
               MFA policy may be satisfied
```

However, TOTP codes **are not bound to the web origin**. A phishing site can harvest the password and code `123456`, then submit them to the real site while the code is still valid. Therefore, **Password + TOTP can be MFA, but is not inherently phishing-resistant**.

Do not do the following:

- Store TOTP seeds alongside plaintext passwords, return the seed to the client after enrollment, or log enrollment QR codes.
- Accept the same already-used OTP within its valid time step for multiple logins.
- Widen the time-drift window excessively just to “reduce friction”.
- Allow customers to change their phone number/TOTP secret using only a code sent to the very device suspected of being compromised.
- Treat entering a valid six-digit OTP as sufficient to change admin/tenant permissions if the transaction requires stronger evidence and consent.

For a TOTP authenticator whose seed was compromised, the security lifecycle is **revoking the binding and re-enrolling**, not merely changing the password.

### 7.1. SMS, Email, and Two Sensitive Caveats

NIST SP 800-63B-4 classifies **PSTN out-of-band** (SMS/voice) as a **restricted authenticator**, due to risks of SIM swapping, port-out, telecom network attacks, and social engineering; organizations need a risk assessment and unrestricted alternatives when required.

NIST SP 800-63B-4 specifies that **email must not be used as an out-of-band authenticator**, because a mailbox can often be opened with just a password and faces interception and forwarding risks. Email **still plays a role** in address verification, account event notifications, and certain recovery workflows; that does not make it valid as a high-assurance MFA factor.

This explains why **password + email OTP**, though looking like two steps, should not by default be marketed as strong two-factor authentication and does not satisfy NIST email-OOB requirements. If Spring Security supports password + email-delivered OTT, that is a **workflow** capability, not automatic certification of independence or AAL.

## 8. FIDO2/WebAuthn, Passkeys, and Phishing Resistance

WebAuthn/FIDO2 uses **public-key cryptography**: the authenticator holds the private key, while the server stores the public key/credential ID and verifies a signed assertion over a challenge. Origin and RP ID information are checked to prevent an attacker from using a fake website to obtain evidence usable on the real website.

Conceptual steps:

```text
Server issues random challenge for the account/same session
     ↓
Browser calls WebAuthn API for the exact RP ID
     ↓
Authenticator verifies user presence and/or user verification
     ↓
Private key signs data containing challenge + authenticator data
     ↓
Server verifies signature, challenge, origin, rpIdHash,
       UP/UV flags (per policy), and credential ownership
     ↓
Server completes factor, applies authorization and session policy
```

**UP** (user presence) and **UV** (user verification) are not the same thing. A passkey/authenticator can be used with only UP; when multi-factor cryptographic authenticator assurance is needed, policy must require appropriate UV. The browser **does not** send raw fingerprints to the Spring backend in a standard WebAuthn flow.

**Synced passkeys** often improve UX, but backup, synchronization, and recovery mechanisms must be understood when evaluating enterprise requirements. Do not assume “every passkey is hardware-bound”, nor call every WebAuthn assertion two-factor without checking UV and authenticator policy.

Most systems can choose phishing-resistant passkeys/WebAuthn as the default direction, then use TOTP or another method as a fallback with accepted risk. Protecting enrollment, recovery, and backup keys is just as important as verifying signatures at login.

## 9. Spring Security 7.x: Built-in MFA via FactorGrantedAuthority

**Version note:** `FactorGrantedAuthority` was introduced in **Spring Security 7.0**, not as a general API across all 6.x releases. This example targets Spring Security 7.x (typically Spring Boot 4.x), Servlet. Do not copy it into a Spring Boot 3.x/Spring Security 6.x project and expect the imported classes to exist.

### 9.1. Authority Model Representing Authentication Methods

Spring Security 7 documentation lists authorities such as:

- `FactorGrantedAuthority.PASSWORD_AUTHORITY` → string name `FACTOR_PASSWORD`.
- `FactorGrantedAuthority.OTT_AUTHORITY` → `FACTOR_OTT` (one-time-token mechanism).
- `FactorGrantedAuthority.WEBAUTHN_AUTHORITY` → `FACTOR_WEBAUTHN`.
- `FactorGrantedAuthority.X509_AUTHORITY` → `FACTOR_X509`.

The framework only knows **which mechanism was just executed** across the authentication flows. Having two authorities in `Authentication` is not sufficient to prove they are genuinely independent against a threat model. For example, `FACTOR_OTT` via email has the security limitations discussed in section 7.1. **Never let the client set any `FACTOR_*`** in headers, unverified JWT claims, or request bodies.

### 9.2. Example Application-Wide Configuration Requiring Password + OTT

The following components illustrate **Spring Security 7.x's built-in mechanism**:

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.authorization.EnableMultiFactorAuthentication;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.authority.FactorGrantedAuthority;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMultiFactorAuthentication(authorities = {
    FactorGrantedAuthority.PASSWORD_AUTHORITY,
    FactorGrantedAuthority.OTT_AUTHORITY
})
public class MfaSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .oneTimeTokenLogin(Customizer.withDefaults());

        return http.build();
    }
}
```

**Requirements for a complete application:** beyond the class above, Spring Boot must have a `UserDetailsService` / suitable credential store, a login page or default UI, a `OneTimeTokenService` backed by a shared store across multiple nodes, a **`OneTimeTokenGenerationSuccessHandler`** to actually deliver the token over a channel with a secure policy, and protected routes. A 25-line config **does not automatically configure mail, factor registration, or compliance**.

The example uses password + OTT to demonstrate the **Spring API**. It **does not claim** password + OTT via email satisfies NIST MFA requirements. For systems requiring phishing-resistant MFA, choose properly enrolled WebAuthn or a method meeting the target assurance level; switching from OTT to WebAuthn requires configuring credential repositories, relying-party/origin settings, and authenticator lifecycle.

The framework enforces factor authority checks in authorization rules: someone with `ROLE_ADMIN` who does not yet have both `FACTOR_PASSWORD` and `FACTOR_OTT` cannot enter `/admin/**` under the global policy above. How the framework guides the user to the missing mechanism does not replace permission checks; each route must be tested and UX customized.

### 9.3. When Only Certain Endpoints Require MFA

Not every application requires both factors on every page. Spring Security 7 supports creating an `AuthorizationManagerFactory` with per-route and time-based factor requirements. Example taken from official API samples (placed in an appropriate configuration class):

```java
var mfa = AuthorizationManagerFactories.multiFactor()
    .requireFactors(
        FactorGrantedAuthority.PASSWORD_AUTHORITY,
        FactorGrantedAuthority.OTT_AUTHORITY)
    .build();

http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/admin/**").access(mfa.hasRole("ADMIN"))
    .requestMatchers("/account/security/**").access(mfa.authenticated())
    .anyRequest().authenticated());
```

This is a **snippet** inside a `SecurityFilterChain`, not a standalone Java file. It requires importing `org.springframework.security.config.annotation.authorization.AuthorizationManagerFactories` along with `FactorGrantedAuthority`; configuring MFA support per the documentation (e.g., `@EnableMultiFactorAuthentication(authorities = {})`) and providing login mechanisms for the factors. Do not apply a global MFA requirement while expecting `/public` to skip factors if rules have already been elevated globally.

**UX rule:** `/admin/**` requires `ROLE_ADMIN` **and** the exact required factors; `/account/security/**` requires auth and MFA; ordinary pages can require basic authentication. Even after passing MFA, sensitive resources still need checks for role, owner, tenant, and active permissions.

### 9.4. Per-Factor Freshness and Step-Up

Spring Security 7 attaches a timestamp to `FactorGrantedAuthority` (`getIssuedAt()`), and the official documentation describes authorization rules requiring a factor to be **fresh**. A password entered at 08:00 should not automatically suffice for a money transfer at 17:00, even if the session is still alive.

Never hardcode an authority name `FACTOR_PASSWORD` in the database and treat it as proof of reauthentication. The authority must be produced by the proper authentication mechanism, bound to the session, from a trusted verifier, with an appropriate timestamp and policy.

## 10. Spring Security 6.x / Spring Boot 3.x: Designing a Proper MFA Gate

In systems running Spring Security **6.x**, do not rely on 7.x's `@EnableMultiFactorAuthentication`. You can integrate an Identity Provider that supports MFA and enforce an assurance policy on the login session, or design a **password → pending challenge → verify TOTP/WebAuthn → MFA complete** flow using Spring Security components.

### 10.1. Two Integration Approaches

**Approach A — Upstream IdP/SSO performs MFA:**

```text
Application → OIDC Login → IdP
      IdP verifies password + WebAuthn/TOTP per policy
        ↓
OIDC ID Token verified for issuer/audience/nonce/time
        ↓
Application checks acr/amr/auth_time per issuer contract
        ↓
Application establishes local session with appropriate assurance
        ↓
Authorization for sensitive endpoints
```

`amr` (Authentication Methods References) and `acr` (Authentication Context Class Reference) are not strings with universal assurance meaning across all providers. The application must **verify tokens from a trusted IdP**, understand exactly what the provider's `acr`/`amr` promises, and check `auth_time`/max-age when step-up is needed. Do not trust a self-declared `amr=["mfa"]` from a browser or email domain. Do not equate `email_verified` with MFA.

**Approach B — Local application performs step two:**

- `AuthenticationManager`/provider verifies password or first factor.
- Server creates a pending challenge for the **same user** (or a primary-authenticated session with restricted privileges).
- Endpoint `POST /mfa/verify` verifies the second factor against the registered secret/public key, with TTL, replay, and attempt controls.
- Only after success is the `mfaComplete` state / security context with appropriate assurance issued.
- `AuthorizationManager` / method security enforces the “requires fresh MFA” policy on `/admin/**` or financial transactions.
- When the user logs out, switches accounts, is locked, or has a factor removed, challenges/sessions must be revoked per policy.

**Do not enable `permitAll()` on sensitive APIs just so the step-two page can be accessed.** Only endpoints required for login/verification and static assets may be accessed in the pending state; all other routes must be properly blocked.

### 10.2. Example Spring Security 6.x Authorization Gate

This snippet illustrates **blocking sensitive routes**, not verifying OTPs. `MfaProofService` below is a business/security component **that the application must implement itself** and bind state to the server-verified user/session/method.

```java
package com.example.security;

import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.core.Authentication;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

@Configuration
class MfaGateConfig {

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            MfaProofService mfaProofs) throws Exception {

        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/admin/**").access(
                (Supplier<Authentication> getAuth,
                 RequestAuthorizationContext context) -> {
                    Authentication current = getAuth.get();
                    boolean allowed = current != null
                        && current.isAuthenticated()
                        && !(current instanceof AnonymousAuthenticationToken)
                        && current.getAuthorities().stream().anyMatch(
                            a -> "ROLE_ADMIN".equals(a.getAuthority()))
                        && mfaProofs.isFreshAndIndependent(
                            current.getName(),
                            context.getRequest());
                    return new AuthorizationDecision(allowed);
                })
            .anyRequest().authenticated());

        return http.build();
    }
}
```

Interface for the application service:

```java
package com.example.security;

import jakarta.servlet.http.HttpServletRequest;

public interface MfaProofService {
    // Only return true when the server has verified sufficient factors for the right account,
    // they are still fresh, and the proof is bound to the current session.
    boolean isFreshAndIndependent(
        String authenticatedLocalUsername,
        HttpServletRequest request);
}
```

**Reading the example in proper scope:** The configuration above is part of a Spring Boot 3/Spring Security 6 project with other authentication mechanisms and a bean implementing `MfaProofService`. It does not automatically create a login page, password verifier, TOTP store, or WebAuthn provider. Without a service implementation, the example will not run as a complete application. Do not copy this config verbatim to replace an entire existing security chain and drop other rules.

Avoid implementing `isFreshAndIndependent(...)` like this:

```java
// WRONG: client self-attests MFA completion
return "true".equals(request.getHeader("X-MFA-Completed"));
```

A proper implementation must look up **server-stored/trusted-upstream-verified** state keyed by session/user, checking freshness and the methods actually authenticated; in multi-node environments, a shared store or session replication/proper session binding is required. Additionally, when using cookie sessions, do not forget CSRF and session fixation protections.

### 10.3. Distinguishing Authenticated, MFA-Complete, and Business Permissions

In a Spring Security 6.x model that allows primary login, requests to `/profile` may be served when `authenticated()` succeeds. However, `/admin/**` must pass both the `isFreshAndIndependent` gate and role checks. If system policy mandates MFA for **every resource**, design filters/authorization accordingly so no shortcut routes exist.

Watch out for **URL variants** (`/admin`, `/admin/`, encoded paths, forward/include, handler mapping) and method security. Protecting only `/admin/**` while forgetting `/admin` or an auxiliary endpoint with the same privilege can create a bypass. For sensitive data access, prefer enforcing policy at the service or domain authorization layer so calls not arriving through a specific URL are also protected.

## 11. Standalone Java 17: Checking Whether Factors Are Independent and Fresh

This program illustrates the **decision model** after evidence has been verified by the server. It is not a real password, TOTP, or signature verifier; it only demonstrates how to reject evidence belonging to the wrong user, stale evidence, unverified evidence, and two verifications of the same factor type.

Save the file `MfaIndependenceDemo.java`:

```java
import java.time.Duration;
import java.time.Instant;
import java.util.EnumSet;
import java.util.List;

public class MfaIndependenceDemo {

    enum Factor { KNOWLEDGE, POSSESSION, INHERENCE }

    record Evidence(
        String userId,
        Factor factor,
        Instant verifiedAt,
        boolean serverVerified
    ) {}

    static boolean hasFreshMfa(
            String expectedUser,
            Instant now,
            List<Evidence> evidence) {

        EnumSet<Factor> distinct = EnumSet.noneOf(Factor.class);
        for (Evidence proof : evidence) {
            if (!proof.serverVerified()) {
                continue;
            }
            if (!expectedUser.equals(proof.userId())) {
                continue;
            }
            if (proof.verifiedAt().isAfter(now)
                    || proof.verifiedAt().isBefore(
                        now.minus(Duration.ofMinutes(5)))) {
                continue;
            }
            distinct.add(proof.factor());
        }
        return distinct.size() >= 2;
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-01-01T12:00:00Z");

        Evidence password = new Evidence(
            "user-42", Factor.KNOWLEDGE, now, true);
        Evidence pin = new Evidence(
            "user-42", Factor.KNOWLEDGE, now, true);
        Evidence totp = new Evidence(
            "user-42", Factor.POSSESSION, now, true);
        Evidence staleTotp = new Evidence(
            "user-42", Factor.POSSESSION,
            now.minus(Duration.ofMinutes(10)), true);
        Evidence otherUsersTotp = new Evidence(
            "user-99", Factor.POSSESSION, now, true);
        Evidence unverifiedTotp = new Evidence(
            "user-42", Factor.POSSESSION, now, false);

        System.out.println("Password + PIN: " +
            hasFreshMfa("user-42", now, List.of(password, pin)));
        System.out.println("Password + TOTP: " +
            hasFreshMfa("user-42", now, List.of(password, totp)));
        System.out.println("Stale TOTP: " +
            hasFreshMfa("user-42", now, List.of(password, staleTotp)));
        System.out.println("Different user: " +
            hasFreshMfa("user-42", now, List.of(password, otherUsersTotp)));
        System.out.println("Unverified proof: " +
            hasFreshMfa("user-42", now, List.of(password, unverifiedTotp)));
    }
}
```

Compile/run (JDK 17+):

```bash
javac MfaIndependenceDemo.java
java MfaIndependenceDemo
```

Exact stdout:

```text
Password + PIN: false
Password + TOTP: true
Stale TOTP: false
Different user: false
Unverified proof: false
```

**Important Explanation and Limitations:**

- `EnumSet` deduplicates identical factor types, so password + PIN fails. The code does not count input attempts.
- `serverVerified` in the demo is only an assumption **already checked outside this function**. In production, never receive this boolean from the client and set it to `true`.
- All evidence must belong to `expectedUser` and be verified within a five-minute window (an **illustrative** step-up policy number, not a standard NIST TTL).
- The model is not sufficient to assess **technical independence** between a password manager and a TOTP authenticator on the same device; enrollment/recovery, secret storage, phishing, and authenticator provenance must be reviewed separately.
- Do not use `EnumSet.size()>=2` in place of a production verifier/authorization service; there is no database, cryptographic authentication, session binding, replay protection, or role check in this demo.

## 12. Step-Up Authentication: Action-Based and Freshness-Based MFA

MFA can be required at login, or only as **step-up** before high-risk actions. For example:

- Viewing public reports inside the application: a basic authenticated session is sufficient per policy.
- Viewing salary data, changing permissions, exporting all data: MFA required.
- Transferring funds, adding a payment method, changing recovery email, registering a security key: **recently verified fresh MFA** required, and confirmation bound to the transaction may be required.

Even if a session completed MFA this morning, an action in the evening may require reauthentication. For instance, a policy like “latest factor within 5 minutes” must use the timestamp from the **verifier result**, not a client-sent timestamp. For high-risk requests, **transaction binding** (displaying and confirming the transfer amount/destination) may be required, not just “entering any OTP”.

For applications using an OIDC IdP, `max_age` or `acr_values` can be requested per provider contract, and `auth_time`/`acr`/`amr` in the verified ID Token checked to perform step-up. One must verify whether the IdP actually honors the request, what the claim mapping means, and whether it reauthenticates or simply reuses an old session. Do not treat claim presence as a universal guarantee across all issuers.

### Session Lifecycle

- After completing MFA, rotate the session ID per policy to prevent session fixation.
- Session logout, account lockout, authenticator revocation, or password reset may require invalidating old MFA state.
- Across multiple tabs or devices, MFA state must be bound to the exact session/account and never borrowed from another.
- If switching users between step one and step two, cancel the old challenge.
- With stateless JWTs, do not append `mfa=true` on the frontend. If the IdP/AS issues tokens with assurance levels, the Resource Server must verify signature, issuer, audience, expiration, freshness policy, and business permissions; the risk of stale claims remaining valid until `exp` must be addressed.

## 13. Enrollment, Changes, Lost Devices, and Recovery

A system with strong MFA login that still allows **adding/requesting factor resets** via an unprotected email can still suffer account takeover.

### 13.1. Enrollment

1. The user is logged in with sufficiently strong evidence; to add a security key or TOTP, require reauthentication/step-up depending on risk level.
2. The server generates a dedicated enrollment challenge/secret, **inactive** until control over the new authenticator is proven.
3. For TOTP: display the QR code once over HTTPS, verify the first code, protect the seed, store the secret encrypted, and limit exposure.
4. For WebAuthn: verify registration challenge, origin, RP ID, credential ID, and attestation/UV if required by policy. The new public key must be bound to the current user.
5. Audit and notify previously registered channels before changes take effect; never allow adding a new factor to automatically elevate privileges or bypass a pending step-up.

### 13.2. Changing and Removing Factors

- Require a local authenticated session with sufficient assurance, reauthentication with a remaining trusted factor, or a controlled recovery workflow.
- Do not let the holder of a hijacked session change the email/phone number and then send an OTP there to bypass the second factor.
- When removing an authenticator, revoke challenges and related sessions/state per policy; send an independent notification to the account owner.
- If removing the last factor leaves the account unable to log in, prepare an alternative method or controlled recovery.

### 13.3. Recovery

Consider CSPRNG **backup codes** displayed once, stored hashed, bounded in count/attempts, and consumed atomically, along with **backup security keys**. Helpdesk recovery for admin accounts needs strict verification workflows, dual control where appropriate, and auditing.

**Never treat answering simple security questions or controlling a weak mailbox as MFA**. Recovery can be a business exception, but it must be designed around risk, emit post-change notifications, temporarily reduce privileges, or delay sensitive operations if needed.

## 14. Attack Types and Controls

| Attack | Scenario | Primary Mitigation |
|---|---|---|
| Credential stuffing | Password leaked on another service | Independent MFA, rate limits, alerts, password policies |
| Real-time phishing / AiTM | Fake site captures password then relays TOTP to real site | WebAuthn/FIDO2 origin binding; anti-phishing, session protection |
| OTP brute force | Guessing 6-digit codes via API | Throttle by user/challenge/IP, short TTL, lock/retry policy |
| OTP replay | Reusing a code within the time step | Store timestep/consumed state, atomic update, reject replay |
| SIM swap | Attacker hijacks phone number | Avoid SMS for high risk, risk signals, delay/notification on number change |
| Push fatigue | Attacker floods push approval prompts | Number matching, context display, rate limit, forbid auto-approve |
| Phishing MFA backup code | Tricking user into entering a recovery code | Warnings, single-use codes, secure recovery flows, WebAuthn |
| Factor enrollment hijack | Attacker with password adds their own authenticator | Require step-up/reauth before enrollment |
| Session theft | Stealing cookies after MFA completes | Secure/HttpOnly/SameSite, TLS, session binding, expiry, monitoring |
| OAuth/OIDC assurance spoof | Backend trusts client-supplied MFA claims | Verify token/signature/issuer/audience/acr-amr policy |
| “Two password” bypass | UI has two steps but both are knowledge | Evaluate independent factor categories, do not count forms |
| Fallback downgrade | App allows “skipping MFA” when OTP service fails | Fail closed on sensitive routes; separately controlled recovery |
| Wrong-account factor | User B's OTP completes User A's session | Challenge binds user ID/authenticator/session and atomic consume |

**MFA is not the only defense layer:** XSS can steal sessions, malware can control devices, and advanced phishing attacks can capture session cookies after valid MFA. Least privilege, CSP, cookie/session security, authorization, anomaly monitoring, and session-hijacking mitigations are still necessary.

## 15. Application Testing Matrix

### 15.1. Definitions and Independence

| Test | Simulated State | Expected Result |
|---|---|---|
| Password succeeds | Only knowledge factor verified | Cannot access routes requiring MFA |
| Password + PIN | Two steps but two knowledge factors | **Does not satisfy MFA** |
| Password + security question | Same knowledge category, even with right answer | Fails |
| Password + valid TOTP, same user | Verified knowledge + possession | Passes under OTP policy, but do not call phishing-resistant |
| Password + another user's TOTP | OTP belongs to authenticator of different owner | Denied |
| Password + never-registered TOTP code | Even if code is valid on a spoofed client | Denied |
| Password + email OTP | Two-step flow but weak mail channel | Do not advertise as NIST email-OOB compliant |
| Password + corporate IP | IP is a risk signal | Does not elevate to MFA |
| Password + WebAuthn valid challenge/origin/UV | Two sufficient factors per policy | Passes within designed assurance scope |
| WebAuthn wrong RP ID/origin/signature | Not a valid assertion | Denied |
| WebAuthn UP only when policy requires UV | Required verification not met | Denied |

### 15.2. State, Replay, and Accounts

- Password succeeds but step two not done → `/admin`, `/payment`, or sensitive APIs remain blocked; no frontend bearer JWT carrying MFA rights.
- Completing second factor for a **different user** or **different session** → must deny; do not reuse challenge.
- Repeated wrong OTPs → decrement `attempts_left`, throttle/lock challenge per policy, do not leak account existence.
- Reusing the same OTP within the valid time window → reject replay; test concurrently across **two server nodes**.
- Expired or already-consumed challenge → fails, even if a subsequent TOTP code is valid.
- After MFA succeeds: only the right owner and current roles/permissions are granted; session fixation protection is triggered.
- MFA step canceled mid-way, user logs out, or logs into another account → old pending state is revoked.
- Removing authenticator/locking account/revoking session → old MFA state must not grant out-of-policy permissions.
- Session has only one factor yet authorization code uses `authenticated()` → test must detect the bypass.
- Factor from request header `X-MFA=true`, query `?mfa=1`, or unverified JWT → must be denied.
- Factor verified in a session 6 hours ago while endpoint requires 5-minute freshness → require step-up.

### 15.3. Recovery and Downgrade

- Attacker has password but lacks authenticator: tries “change phone”, “disable MFA”, “reset MFA” → cannot succeed with password alone.
- Helpdesk/admin recovery: has audit, notifications, dual control or risk-appropriate workflow; no public `skipMfa` path.
- TOTP/WebAuthn service unreachable: sensitive routes **do not fail open**; recover through official procedures.
- Backup codes are single-use and hard to guess; the same code cannot be used twice concurrently.
- Do not automatically downgrade from passkey/WebAuthn to SMS/email for sensitive accounts without corresponding policy/step-up.

## 16. Checklist for Taking MFA to Production

1. **Define the threat model**: assets protected, user types, phishing/session compromise, assurance requirements, and transaction sensitivity.
2. **Distinguish 2SV/2FA**: do not count steps; do not treat password+PIN or password+CAPTCHA as MFA.
3. **Choose authenticators matching requirements**: prefer phishing-resistant WebAuthn for sensitive accounts; TOTP if phishing risk is accepted; be cautious with SMS, do not use email OOB as NIST-compliant MFA.
4. **Verify evidence provenance**: the verifier proves the authenticator is registered for the **same user**, still valid, and not revoked.
5. **Protect every stage**: pending state with TTL/attempt limit, session binding, CSRF, atomic consume; do not grant privileges before completion.
6. **Do not rely on client flags**: only server-side proof or signed/trusted upstream claims verified against policy; do not let clients set factor authorities.
7. **Authorization by permission and freshness**: step-up for admin/payment/security settings, checking roles/tenant/ownership separately.
8. **Strict enrollment and recovery**: protect adding/removing/resetting factors as sensitive actions; notify and audit.
9. **Protect sessions**: TLS, Secure/HttpOnly/SameSite cookies, session rotation, timeouts, logout/revocation, XSS/CSRF mitigation.
10. **Monitor operations and test attacks**: replay, brute force, push fatigue, phishing, SIM swap, cross-account, multi-node race, downgrade, and verifier outage.
11. **Confirm exact framework version**: do not use Spring Security 7 `FactorGrantedAuthority` in Spring Security 6.x projects; check dependencies/APIs and version-specific docs.
12. **Evaluate system-wide independence**: secret storage, device compromise, shared mailbox, IdP recovery, helpdesk, and backup codes can create shared points of failure.

## 17. Self-Assessment

**Question 1.** A user enters a password and then a PIN on two different pages. Is this MFA?  
**Answer:** No. Both steps use the **knowledge** factor category.

**Question 2.** Does Password + TOTP from an app protect against all phishing?  
**Answer:** No. This is usually knowledge + possession, but a manually entered code can be relayed immediately by a fake site to the real site.

**Question 3.** Why should password + email OTP not be assumed to be strong MFA by default?  
**Answer:** The mailbox may depend on the same password and device; NIST SP 800-63B-4 prohibits using email as an OOB authenticator. Email can be useful for verification/recovery, but does not replace an independent authenticator matching the required assurance.

**Question 4.** A user logged in with a password has `Authentication.isAuthenticated()==true`. Is that enough for `/admin` requiring MFA?  
**Answer:** Not yet. It requires verifying an independent factor for the same user/session, still fresh, plus current admin permissions.

**Question 5.** A passkey user uses a fingerprint on their device. Is fingerprint data sent to the Spring backend?  
**Answer:** Not in standard WebAuthn; the authenticator performs user verification locally and creates a signed assertion; the backend checks challenge/origin/RP ID/signature/UV per policy.

**Question 6.** How should two concurrent requests with the same valid TOTP hitting two API nodes be handled?  
**Answer:** Only one may be accepted under replay policy; consumed/timestep/attempt state must be updated atomically in a shared store.

**Question 7.** If Spring Security 7 uses `FACTOR_PASSWORD` + `FACTOR_OTT`, has the system achieved NIST AAL2?  
**Answer:** That cannot be concluded from authority names alone. One must evaluate authenticator types, independence, email/SMS restrictions, enrollment, replay, session handling, and all standard requirements.

**Question 8.** MFA was completed in the morning; does a transfer in the evening require re-entry?  
**Answer:** It depends on step-up/freshness/transaction-binding policy; for sensitive operations, evaluate verification time and require a fresh factor when needed.

## References

- [OWASP — Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html): independent factors, MFA fatigue, phishing, enrollment, recovery, reset, and factor changes.
- [NIST SP 800-63B-4 — Authentication and Authenticator Management](https://pages.nist.gov/800-63-4/sp800-63b.html): authenticator categories, MFA/OOB requirements, email not an OOB authenticator, PSTN restricted, phishing resistance, replay.
- [Spring Security 7 — Multi-Factor Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/mfa.html): `FactorGrantedAuthority`, `@EnableMultiFactorAuthentication`, rules, and step-up.
- [Spring Security — FactorGrantedAuthority Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/authority/FactorGrantedAuthority.html): factor authorities and timestamps.
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): `AuthorizationManager` and policies.
- [Spring Security — One-Time Token Login](https://docs.spring.io/spring-security/reference/servlet/authentication/onetimetoken.html): OTT mechanism, not synonymous with independent evidence or NIST AAL.
- [W3C — Web Authentication Level 3](https://www.w3.org/TR/webauthn-3/): WebAuthn challenge, RP ID, origin, UP/UV, authenticator assertions.
- [RFC 6238 — TOTP](https://www.rfc-editor.org/rfc/rfc6238): time steps and TOTP one-time code mechanism.

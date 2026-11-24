# Fallback Login Options Without Weakening Authentication Policy

> **Module:** Spring Security – federation. **Parent topic:** Kerberos Integration. This article guides designing fallback login when Kerberos/SPNEGO is unavailable without lowering authentication assurance, bypassing MFA, silently downgrading to NTLM/Basic, or breaking identity mapping, business permissions, or tenant isolation.

## 1. Learning Objectives

After this lesson, you can:

1. Explain how Kerberos/SPNEGO uses HTTP `WWW-Authenticate: Negotiate`, `Authorization: Negotiate`, Kerberos service principals, keytabs, and GSS-API verification.
2. Distinguish **browser lacking SPNEGO support**, **KDC/DNS/VPN unavailable**, **wrong SPN/keytab/clock skew**, **invalid Kerberos ticket**, **disabled account**, and **missing MFA/step-up**.
3. Choose approved fallback options: OIDC Authorization Code with MFA/passkeys, SAML2 with equivalent policy, or LDAP/password **with mandatory MFA** when permitted by policy.
4. Design a shared **resource → assurance requirement → accepted authentication evidence → local authorization** matrix across all login methods.
5. Avoid treating "holds a Kerberos ticket" as automatic MFA proof, or "OIDC login succeeded" as phishing resistance proof.
6. Use `SpnegoEntryPoint`, `SpnegoAuthenticationProcessingFilter`, `AuthenticationProvider`, `SecurityFilterChain`, and `oauth2Login` in their proper roles without building fake verification providers.
7. Distinguish a fallback login-choice page from automatic privilege granting; handle HTTP 401/302/403 and browsers omitting tokens accurately.
8. Protect account linking between Kerberos realm/principal and OIDC `issuer + sub`, session fixation, CSRF, redirect URIs, and reauthentication requirements.
9. Write and run a Java 17 program classifying policy decisions with deterministic stdout; inspect a Spring Boot 3.3 OIDC fallback module that never auto-grants admin permissions.
10. Design operations for KDC/IdP outages, keytab rotation, break-glass, logging, metrics, alerting, and rollbacks.
11. Test scenarios where attackers attempt forced downgrades, forged tokens, revoked roles, users failing ACR, malformed ACRs, multi-tenancy, and browsers without Negotiate support.

**Scope:** Java Servlet, Kerberos V5/SPNEGO, and Spring Security. This lesson uses Java 17; Spring Boot 3.3.x / Spring Security 6.3.x code serves as the learning baseline. Spring Security Kerberos is a **separate extension** whose Jakarta Servlet compatibility must be verified before integrating with Boot 3.x. **This is not a guide for bypassing authentication when the KDC fails.**

## 2. One System, Multiple Devices, Same Security Policy

Suppose Orders Portal exposes these routes:

| Resource | Required Authentication Assurance | Required Application Permission |
| --- | --- | --- |
| `GET /me` | Identity authenticated by a trusted source, ACTIVE account. | User is permitted to access the Portal. |
| `GET /orders` | Authentication meeting basic policy. | `APP_ORDER_READ` and matching tenant. |
| `POST /orders/{id}/approve` | Organizational MFA meeting policy, freshness within limit. | `APP_ORDER_APPROVE` and matching order owner/tenant. |
| `GET /admin/export` | **Phishing-resistant** method, MFA, and auth freshness per security-approved policy. | `APP_ADMIN_EXPORT`, approval, and unlocked account. |
| `GET /public/health` | No end-user login required. | Never expose secrets or internal data. |

User A accesses from a domain-joined laptop and receives a valid Kerberos ticket. User B is off-domain and cannot send an SPNEGO token. Administrator C can use Kerberos SSO yet needs a fresh MFA step to export sensitive data.

**Wrong design:** When `Authorization: Negotiate` is absent, automatically render a username/password-only form with no MFA and let everyone reach `/admin/export`.

**Right design:** Users unable to use SPNEGO get an option to route to an **approved OIDC/SAML IdP**, complete fresh authentication via standard protocol, and the application still verifies the local account, permissions, tenant, and per-resource assurance. On resources requiring phishing-resistant MFA, **only** methods proving that requirement are accepted.

**Crucial:** Kerberos, OIDC, and SAML describe how identities are conveyed and verified. They **do not by themselves** dictate which method is always stronger. Assurance depends on the specific authenticator, IdP policy, MFA, device, freshness, and SP verification.

## 3. Kerberos/SPNEGO Flow to Understand Before Building Fallback

~~~text
Browser/domain device        Portal SPNEGO                 Kerberos KDC
       |                           |                            |
       | GET /orders               |                            |
       |-------------------------->|                            |
       |<-- 401 WWW-Authenticate: Negotiate                      |
       |                           |                            |
       |-- obtain service ticket ------------------------------->|
       |<---------------------- Kerberos ticket -----------------|
       |                           |                            |
       | GET /orders               |                            |
       | Authorization: Negotiate <opaque-token>                 |
       |-------------------------->|                            |
       |                           | GSS-API acceptSecContext   |
       |                           | service keytab/realm/SPN   |
       |                           | local identity mapping     |
       |                           | Spring authorization       |
       |<-- 200 or 403 ------------|                            |
~~~

The service host has an SPN like:

~~~text
HTTP/portal.example.com@EXAMPLE.COM
~~~

The browser fetches a service ticket for the exact principal; `SpnegoAuthenticationProcessingFilter` reads the token from `Authorization: Negotiate` and invokes `AuthenticationManager`. The provider verifies the ticket genuinely via trusted configuration (service account/keytab/realm), then Spring builds `Authentication` and the app runs local authorization.

**Never** treat any HTTP `Authorization: Negotiate` header with arbitrary text as authentication proof. The ticket must be decrypted/verified by the provider, validating source, target, timestamps, and Kerberos protocol constraints.

### 3.1. Related Spring Extension Notes

- `SpnegoEntryPoint` emits the `WWW-Authenticate: Negotiate` challenge; it can be configured to forward to a URL offering form/OIDC fallback choices.
- `SpnegoAuthenticationProcessingFilter` reads the Negotiate header and invokes `AuthenticationManager`. It provides `failureHandler` and `successHandler`.
- `KerberosServiceAuthenticationProvider` / `SunJaasKerberosTicketValidator` typically process service tickets via JAAS/JGSS per the extension.
- `KerberosAuthenticationProvider` can support username/password Kerberos authentication in other setups, **not automatically equivalent to MFA**.
- All of the Kerberos classes above belong to the **spring-security-kerberos extension**, not bundled automatically with Spring Boot starter security alone.

**A practical difference:** per the extension Javadoc, if the browser **sends no token**, the filter may **not invoke** the failure handler because no server-side Kerberos authentication attempt occurred. Therefore, fallback cannot be designed around catching an exception alone.

## 4. Classifying Errors Before Showing Fallback

| Classification | Example | Handling |
| --- | --- | --- |
| `NO_NEGOTIATE_CREDENTIAL` | Browser or device sends no Negotiate header. | Offer OIDC/SAML choice; **no Authentication yet**. |
| `BROWSER_NOT_CONFIGURED` | Browser lacks intranet URL allowlist, proxy blocks challenge. | Show guidance or fallback IdP; never auto-grant session. |
| `KDC_UNAVAILABLE` | DNS/VPN/KDC outage, browser cannot acquire ticket. | Log incident; allow approved fallback if IdP remains healthy. |
| `SPN_OR_KEYTAB_FAILURE` | Wrong/duplicate SPN, kvno mismatch, stale keytab, broken rotation. | Fix infrastructure; never disable Kerberos validation. |
| `CLOCK_SKEW` | Client/KDC/service clocks drifted apart. | Fix NTP/time sync; never extend tickets arbitrarily. |
| `INVALID_NEGOTIATE_TOKEN` | Forged token, integrity failure, replay, or untrusted realm. | Reject and audit/rate-limit; never treat user as verified. |
| `UNKNOWN_REALM` | Ticket from an unpermitted realm. | Reject; never auto-add trust. |
| `ACCOUNT_DISABLED` | IdP/local account locked/expired. | DENY across all methods. |
| `NO_ACCOUNT_LINK` | Kerberos or OIDC principal not linked to a local account. | DENY/provisioning; never auto-create admin. |
| `MFA_REQUIRED` | Authentication valid yet resource demands MFA. | Step-up via approved IdP; never lower requirement. |
| `PHISHING_RESISTANCE_REQUIRED` | OTP used yet policy requires passkey/FIDO2 equivalent. | Deny/stronger step-up. |
| `FALLBACK_IDP_FAILURE` | Invalid OIDC issuer/token/signature/nonce/ACR. | Reject; never open a Kerberos bypass. |
| `ALL_APPROVED_METHODS_UNAVAILABLE` | Both Kerberos and fallback IdP are down. | Fail closed, support page, separate break-glass procedure. |

**An outage only permits routing the user to another approved method, never lowering the trustworthiness of the evidence.**

### 4.1. HTTP 401, 302, 403, and 5xx Are Not Equivalent

- **401 + Negotiate:** server invites the browser to send Integrated Windows Authentication proof; user identity is not yet proven.
- **302 to OIDC/SAML IdP:** starts a new sign-in ceremony, **not** a role-granting step.
- **403:** identity is known yet lacks permission or assurance; require step-up or stop the action.
- **5xx:** backend/KDC/service configuration failure requiring operations attention; never convert to 200.
- **200:** only when both appropriate authentication and authorization succeed.

Machine clients may need `401/403`/OAuth2 resource-server tokens or mTLS rather than looping 302s to a human login page.

## 5. Safety Invariant: Fallback Must Never Lower Standards

### 5.1. Every Login Path Needs Independent Proof

Wrong:

~~~java
// WRONG: Kerberos failure never permits inventing a default user.
try {
    return kerberosProvider.authenticate(request);
} catch (Exception ex) {
    return new MyAdminAuthentication("fallback-user");
}
~~~

Right: failure → return challenge or choice page; create `Authentication` only when **another provider genuinely verifies** fresh evidence.

### 5.2. Never Automatically Relax MFA/Step-Up

If `/admin/export` requires MFA and phishing resistance, a password-only form **does not qualify** merely because Kerberos failed. If the OIDC IdP omits proper method/freshness evidence, block the resource even though basic login succeeded.

### 5.3. Never Conflate Authentication with Authorization

A Kerberos ticket or OIDC ID Token verifies identity. Permissions like `APP_ORDER_APPROVE`, `APP_ADMIN_EXPORT`, and tenant ownership are application-specific business decisions, never granted simply because the issuer/realm matched.

### 5.4. Never Silently Downgrade Protocols

Some platforms using "Negotiate" can fall back to NTLM when Kerberos fails. **Never infer solely from the Negotiate header name that a session was verified by Kerberos.** NTLM and HTTP Basic carry different security trade-offs; never enable them indiscriminately as a "whatever works" fallback. Enforce network/OS controls, logging, and NTLM auditing per policy.

### 5.5. Post-Fallback Sessions Must Obey the Same Policy

Enforce session fixation protection, CSRF on browser forms, `Secure`/`HttpOnly`/`SameSite` cookies, session timeouts, account revocation, and step-up freshness identically to Kerberos sessions. Never let a fallback session live forever just because it came from OIDC.

## 6. Fallback Options and Conditions of Use

| Option | When Used | Mandatory Conditions | Warning |
| --- | --- | --- | --- |
| OIDC Authorization Code + MFA/passkey | Non-domain devices, KDC/Negotiate failure. | IdP issuer allowlist, TLS, PKCE/state/nonce, token validation, ACR/AMR policy, identity linking. | OIDC protocol **does not prove MFA by default**. |
| SAML2 SSO via MFA-enforcing IdP | Enterprise uses managed SAML IdP. | Signed assertion, Issuer, Audience, Recipient, InResponseTo, AuthnContext, local account. | Never skip signature validation to bypass errors. |
| LDAP/AD password + second factor | Approved legacy exception. | LDAPS/TLS, MFA, rate limit, lockout, hardening, session policy. | LDAP bind/password alone is insufficient for sensitive routes. |
| Passkey/FIDO2 via IdP | Phishing-resistant MFA on supporting devices. | Exact RP origin, authenticator enrollment, IdP-validated assertion, ACR policy. | Never trust a browser self-claiming it used a passkey. |
| OIDC/SAML step-up | Kerberos valid for dashboard yet insufficient for approve/admin. | Same user, freshness, required challenge/ACR, local roles, and action permissions. | Step-up by a different user must not retain the prior user's rights. |
| Dedicated break-glass | Both KDC and IdP outage requiring emergency recovery. | Vaulted, dual-approval, hardware MFA, least privilege, short TTL, audited, post-review. | Not an "ignore MFA" button open to every user. |

**Never rank assurance merely by protocol names Kerberos/OIDC/SAML.** Evaluate the concrete authenticator, trust model, and evidence per policy.

## 7. Policy Driven by Resource, Not Login Method Errors

~~~text
GET /resource
   |
   +-- no verified authentication?
   |       |
   |       +-- SPNEGO suitable? -> challenge Negotiate
   |       |                            |
   |       |                            +-- valid ticket -> verified identity
   |       |                            +-- unsupported  -> login choice
   |       |
   |       +-- user chooses approved IdP -> OIDC/SAML
   |                                       -> validated identity
   |
   +-- verified identity
           |
           +-- link to SAME active local account
           |
           +-- load local roles, tenant, device policy
           |
           +-- check resource assurance requirement
                    |
                    +-- sufficient -> authorize resource
                    |
                    +-- insufficient -> step-up or DENY
~~~

There is no edge for "token invalid → grant admin" or "IdP down → disable MFA". Showing a fallback choice page is a UX decision, **not a change** to resource policy.

### 7.1. Valid Choice Page

A `permitAll` `/login-choice` page can offer:
- "Retry integrated sign-in" linking to the dedicated Negotiate route;
- "Sign in with organizational account" linking to `/oauth2/authorization/workforce` of the configured IdP;
- "VPN connection guide or contact support" without collecting passwords directly.

Never read `issuer`, `casServer`, or `returnTo` from untrusted query parameters to redirect to arbitrary URLs. To return to the original page, allow only allowlisted relative paths or valid same-origin `SavedRequest`s.

### 7.2. Avoiding Challenge Loops

Browsers may decline 401 Negotiate and send no token. If `/login-choice` is itself intercepted by the SPNEGO entry point, users enter an infinite 401/forward loop. The fallback page, OIDC authorization endpoint, and callbacks must reside in chains/matchers that do not accidentally block them.

## 8. NIST AAL, MFA, and Phishing Resistance

NIST SP 800-63B-4 defines **Authenticator Assurance Levels (AAL)** and authenticator properties. AAL is never determined solely by the name of the protocol used in the app.

### 8.1. Kerberos Tickets and MFA

A valid Kerberos service ticket proves what **Kerberos/KDC/acceptor** verified in that environment; it **does not automatically** prove the user recently performed MFA, used a compliant device, or used a phishing-resistant authenticator.

If an organization treats a Kerberos session as MFA-backed, it requires **trusted additional evidence** from the IdP/device/enterprise authentication ceremony, including freshness and policy mappings. Never set `mfa=true` merely because the browser skipped a password prompt.

### 8.2. OIDC ACR/AMR and auth_time

In OIDC, `acr` and `amr` can help describe authentication context/methods, and `auth_time` records authentication time. However:

1. The ID Token must have its signature, `iss`, `aud`, `exp`, `nonce`, and authorization flow `state` verified by the framework.
2. `acr` values must be explicitly agreed upon between IdP and app: there is no universal value meaning "always equivalent to AAL2".
3. `amr` alone does not prove a compliant phishing-resistant authenticator; manual OTP is typically **not phishing-resistant**.
4. Resources requiring freshness must inspect real `auth_time`, never substituting local session creation time.
5. If claims are missing/wrong or the IdP lacks an assurance contract, **fail closed** on sensitive resources.
6. A step-up flow must never switch the subject to another account while preserving old permissions.

Example internal policy names:

~~~text
BASIC:
    verified_identity + active_local_account

WORKFORCE_MFA:
    BASIC + verified_approved_MFA_evidence

PHISHING_RESISTANT_FRESH:
    BASIC + approved_phishing_resistant_authenticator
    + verified_auth_time_within_window
    + high_risk_authorization
~~~

These are **illustrative internal policies**, not standard `acr` strings emitted by every IdP.

## 9. Incident Decision Matrix

| Scenario | Basic Dashboard | Function Requiring MFA / Phishing Resistance |
| --- | --- | --- |
| Browser cannot Negotiate, OIDC works | Allow OIDC if identity/local account valid. | Allow only if IdP evidence satisfies policy. |
| KDC outage, independent OIDC IdP healthy | Fallback permitted. | Enforce MFA/freshness as usual. |
| Misconfigured SPN/keytab | Incident; fallback if approved. | Never skip GSS checks; allow via IdP only if assurance suffices. |
| Forged or integrity-failed Negotiate token | Reject/audit. | Reject; never grant roles or weaken authentication. |
| Disabled/locked account | DENY. | DENY. |
| Unlinked identity | DENY/provisioning. | DENY; never auto-grant admin permissions. |
| Valid Kerberos yet no MFA evidence | Accept if BASIC policy permits. | Challenge step-up or DENY. |
| OIDC password-only, missing assurance claim | May satisfy BASIC per policy. | Insufficient: DENY/step-up. |
| OIDC assertion bad issuer/signature/nonce | Reject. | Reject. |
| Both KDC and IdP down | No new logins. | Never lower policy; separate break-glass workflow. |
| Old session alive yet local permissions revoked | Deny per revocation policy. | Deny; never treat prior session as permanent authority. |

## 10. Java 17: Policy Decision Engine with Deterministic Stdout

This example runs offline and takes **simulated evidence already verified by a validator**. In reality, flags like `verified`, `mfa`, `phishingResistant`, and `fresh` must never come from client-controlled HTTP queries/bodies.

### 10.1. `KerberosFallbackPolicyDemo.java`

~~~java
public final class KerberosFallbackPolicyDemo {

    enum Method {
        KERBEROS, OIDC, EMERGENCY
    }

    enum Requirement {
        BASIC, MFA, PHISHING_RESISTANT_FRESH
    }

    enum Decision {
        ALLOW,
        DENY_UNVERIFIED,
        DENY_DISABLED,
        DENY_UNLINKED,
        DENY_PRIVILEGE,
        STEP_UP_MFA,
        STEP_UP_PHISHING_RESISTANT,
        STEP_UP_FRESH
    }

    record Evidence(
        Method method,
        boolean verified,
        boolean activeAccount,
        boolean linkedIdentity,
        boolean privileged,
        boolean mfa,
        boolean phishingResistant,
        boolean fresh) {
    }

    static Decision decide(Evidence e,
                           Requirement required,
                           boolean privilegedResource) {

        if (!e.verified()) {
            return Decision.DENY_UNVERIFIED;
        }
        if (!e.activeAccount()) {
            return Decision.DENY_DISABLED;
        }
        if (!e.linkedIdentity()) {
            return Decision.DENY_UNLINKED;
        }
        if (privilegedResource && !e.privileged()) {
            return Decision.DENY_PRIVILEGE;
        }

        if (required == Requirement.BASIC) {
            return Decision.ALLOW;
        }
        if (!e.mfa()) {
            return Decision.STEP_UP_MFA;
        }
        if (required == Requirement.MFA) {
            return Decision.ALLOW;
        }
        if (!e.phishingResistant()) {
            return Decision.STEP_UP_PHISHING_RESISTANT;
        }
        if (!e.fresh()) {
            return Decision.STEP_UP_FRESH;
        }
        return Decision.ALLOW;
    }

    static void show(String name, Evidence evidence,
                     Requirement required, boolean privileged) {
        System.out.println(name + "=" +
            decide(evidence, required, privileged));
    }

    public static void main(String[] args) {
        Evidence kerberos = new Evidence(
            Method.KERBEROS, true, true, true,
            false, false, false, false);

        Evidence oidcMfa = new Evidence(
            Method.OIDC, true, true, true,
            false, true, false, true);

        Evidence oidcStrong = new Evidence(
            Method.OIDC, true, true, true,
            true, true, true, true);

        Evidence oidcStale = new Evidence(
            Method.OIDC, true, true, true,
            true, true, true, false);

        Evidence forged = new Evidence(
            Method.KERBEROS, false, true, true,
            true, true, true, true);

        Evidence disabled = new Evidence(
            Method.OIDC, true, false, true,
            true, true, true, true);

        Evidence unlinked = new Evidence(
            Method.OIDC, true, true, false,
            true, true, true, true);

        Evidence missingRole = new Evidence(
            Method.OIDC, true, true, true,
            false, true, true, true);

        Evidence emergency = new Evidence(
            Method.EMERGENCY, true, true, true,
            true, false, false, true);

        show("kerberosDashboard", kerberos,
            Requirement.BASIC, false);
        show("kerberosNeedsMfa", kerberos,
            Requirement.MFA, false);
        show("oidcDashboard", oidcMfa,
            Requirement.BASIC, false);
        show("oidcMfa", oidcMfa,
            Requirement.MFA, false);
        show("oidcNotPhishingResistant", oidcMfa,
            Requirement.PHISHING_RESISTANT_FRESH, false);
        show("strongAdmin", oidcStrong,
            Requirement.PHISHING_RESISTANT_FRESH, true);
        show("staleAdmin", oidcStale,
            Requirement.PHISHING_RESISTANT_FRESH, true);
        show("forgedToken", forged,
            Requirement.BASIC, false);
        show("disabledAccount", disabled,
            Requirement.BASIC, false);
        show("unlinkedIdentity", unlinked,
            Requirement.BASIC, false);
        show("missingRole", missingRole,
            Requirement.PHISHING_RESISTANT_FRESH, true);
        show("breakGlassWeak", emergency,
            Requirement.PHISHING_RESISTANT_FRESH, true);
    }
}
~~~

### 10.2. Run

~~~bash
javac --release 17 KerberosFallbackPolicyDemo.java
java KerberosFallbackPolicyDemo
~~~

**Exact stdout:**

~~~text
kerberosDashboard=ALLOW
kerberosNeedsMfa=STEP_UP_MFA
oidcDashboard=ALLOW
oidcMfa=ALLOW
oidcNotPhishingResistant=STEP_UP_PHISHING_RESISTANT
strongAdmin=ALLOW
staleAdmin=STEP_UP_FRESH
forgedToken=DENY_UNVERIFIED
disabledAccount=DENY_DISABLED
unlinkedIdentity=DENY_UNLINKED
missingRole=DENY_PRIVILEGE
breakGlassWeak=STEP_UP_MFA
~~~

**Meaning:** Unverified evidence is rejected first, disabled accounts are blocked across every method, local permissions are checked independently, MFA never turns into phishing resistance automatically, and a password-only break-glass cannot bypass policy.

`Method` is merely a source label; the program **never lets Method=KERBEROS or OIDC inflate assurance**. In production, `Evidence` must be constructed from a real Kerberos acceptor/provider or OIDC/SAML verifier, binding verified IdP/realm + subject, freshness, and device policy. Never use simulated code as a real authenticator.

## 11. Spring Security Kerberos: Extension Points to Configure

| Component | Role | Mistake to Avoid |
| --- | --- | --- |
| `SpnegoEntryPoint` | Emits HTTP Negotiate challenge; offers overload for a fallback page. | Thinking forwarding to a login page authenticates the user. |
| `SpnegoAuthenticationProcessingFilter` | Receives and processes Negotiate header, calls manager/provider. | Treating any token prefixed "Negotiate" as valid. |
| `KerberosServiceAuthenticationProvider` | Provider verifying Kerberos service tickets. | Replacing with a provider that always returns success. |
| `SunJaasKerberosTicketValidator` | Kerberos acceptor using JAAS/keytab per implementation. | Skipping service ticket checks to "fix keytab". |
| `KerberosAuthenticationProvider` | Another Kerberos provider, not MFA by default. | Combining with the service ticket provider without understanding flows. |
| `AuthenticationManager` | Delegates to the provider matching the token type. | Letting UsernamePassword provider accept Negotiate bytes. |
| `SecurityFilterChain` | Routes paths and filter order. | Accidentally guarding OIDC callbacks with a Negotiate challenge. |
| `oauth2Login` | OIDC login via approved IdP. | Trusting the browser to self-assert issuer/ACR. |
| `saml2Login` | SAML2 fallback if enterprise uses a SAML IdP. | Skipping signature/AuthnContext checks. |
| `AuthorizationManager` | Assurance/permission gate for resources. | Relying solely on `authenticated()` for sensitive endpoints. |

### 11.1. `SpnegoEntryPoint` Is Routing, Not Authentication Policy

Spring Security Kerberos Javadoc supports configuring a fallback page:

~~~java
// CONFIG SNIPPET: imports and beans depend on the actual extension/version.
SpnegoEntryPoint entryPoint =
    new SpnegoEntryPoint("/login-choice");
~~~

With this overload, the entry point can emit `401 Negotiate` while forwarding to the login page depending on version/browser; **do not assume** a 302 redirect happens on all clients. Test across Windows/macOS/Linux browsers and proxies.

If the user sends no token, `SpnegoAuthenticationProcessingFilter.failureHandler` may never run. Provide a public `/login-choice` page and an alternative OIDC link rather than relying solely on a catch block.

### 11.2. Failed Negotiate Does Not Create a Fallback Session

~~~java
// WIRING SNIPPET: filter already initialized, matching version.
spnegoFilter.setFailureHandler((request, response, ex) -> {
    // Log error category only; DO NOT log raw Negotiate token.
    response.sendError(
        401, "Integrated login failed; choose approved sign-in");
});
~~~

A sound failure handler **never**:
- Assigns `ROLE_USER` or `ROLE_ADMIN`;
- Sets an authenticated `SecurityContext` with a default user;
- Bypasses disabled-account checks during network failures;
- Redirects to an arbitrary `returnTo`;
- Enables unapproved Basic/NTLM.

### 11.3. SecurityFilterChain Pattern by Client Group

~~~text
@Order(1): /api/**
  -> OAuth2 Resource Server JWT/opaque token or mTLS
  -> STATELESS, 401/403; no HTML login page

@Order(2): /oauth2/**, /login/oauth2/**, /login-choice
  -> OIDC callback/entry routes, never intercepted by SPNEGO challenge

@Order(3): /**
  -> browser Kerberos filter + approved OIDC fallback
  -> HttpSession/SecurityContext, CSRF, session fixation
  -> resource assurance authorization
~~~

This is an **architectural diagram**, not Java security code instantiating three chains directly. In Spring Security, the first matching chain wins `SecurityFilterChain` selection. If the OIDC callback chain is intercepted earlier, fallback breaks even though the IdP succeeded. If APIs hit the browser chain, machine clients receive 302 HTML.

**Test all callback/saved-request/redirect paths**, not just `/orders`. Accounts requiring step-up on `/admin/**` must not use another route to slip past the `AuthorizationManager`/method-security gate.

## 12. Spring Boot 3.3: OIDC Fallback Module with Assurance Check

The project below is a structured **OIDC fallback module** ready to configure against a real IdP; it omits wiring the Kerberos extension into the same chain. Keeping them separate avoids pretending a Kerberos/Jakarta dependency set was verified when only illustrating **the principle of fallback never auto-granting admin permissions**.

### 12.1. Structure

~~~text
kerberos-oidc-fallback/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/fallback/
    │   ├── FallbackApplication.java
    │   ├── SecurityConfig.java
    │   └── InfoController.java
    └── resources/
        └── application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'kerberos-oidc-fallback'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

### 12.2. `FallbackApplication.java`

~~~java
package com.example.fallback;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FallbackApplication {
    public static void main(String[] args) {
        SpringApplication.run(FallbackApplication.class, args);
    }
}
~~~

### 12.3. `application.yml`

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          workforce:
            provider: workforce
            client-id: "${WORKFORCE_OIDC_CLIENT_ID}"
            client-secret: "${WORKFORCE_OIDC_CLIENT_SECRET}"
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile
        provider:
          workforce:
            issuer-uri: "${WORKFORCE_OIDC_ISSUER_URI}"

app:
  security:
    admin-required-acr: "${WORKFORCE_ADMIN_ACR}"

server:
  servlet:
    session:
      timeout: 20m
      cookie:
        secure: true
        http-only: true
        same-site: lax
~~~

Environment variables must come from managed configuration. `WORKFORCE_ADMIN_ACR` is the **exact** value agreed upon by the IdP and security team for a verified method satisfying the requirement. Never guess an ACR just because its name contains `mfa`.

### 12.4. `SecurityConfig.java`

~~~java
package com.example.fallback;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain chain(
            HttpSecurity http,
            @Value("${app.security.admin-required-acr}")
            String requiredAcr) throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login-choice", "/error")
                    .permitAll()
                .requestMatchers("/admin/**").access(
                    (authenticationSupplier, context) -> {
                        Authentication authentication =
                            authenticationSupplier.get();
                        return new AuthorizationDecision(
                            adminAllowed(authentication, requiredAcr)
                        );
                    }
                )
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutSuccessUrl("/login-choice")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
            )
            .build();
    }

    static boolean adminAllowed(
            Authentication authentication,
            String requiredAcr) {

        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return false;
        }

        if (!(authentication instanceof OAuth2AuthenticationToken oidc)
                || !(oidc.getPrincipal() instanceof OidcUser user)) {
            return false;
        }

        // ACR is an IdP contract; never browser-supplied.
        if (requiredAcr.isBlank()
                || !requiredAcr.equals(
                    user.getIdToken().getClaimAsString("acr"))) {
            return false;
        }

        // Internal permissions remain mandatory; the demo does not grant this role.
        return authentication.getAuthorities().stream().anyMatch(
            authority ->
                "APP_ADMIN_EXPORT".equals(authority.getAuthority())
        );
    }
}
~~~

**This code intentionally DENIES admin by default**: Spring OAuth login does not emit `APP_ADMIN_EXPORT` in the sample project. Production must map local users/roles from an approved source **and** add checks for disabled accounts, tenants, `auth_time` freshness, device compliance, and transaction-level controls. Checking only ACR and role is **not enough** to claim the full `PHISHING_RESISTANT_FRESH` policy is enforced.

If the IdP omits `acr` from the Spring-validated ID Token, admin access is blocked. Never "fix" this by reading `?acr=strong` from a query parameter or defaulting ACR to strong. Token validation, issuer, audience, nonce, state, and PKCE must be verified per your OIDC/framework configuration.

### 12.5. `InfoController.java`

~~~java
package com.example.fallback;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class InfoController {

    @GetMapping("/")
    public Map<String, String> home() {
        return Map.of(
            "loginUrl", "/oauth2/authorization/workforce",
            "note", "Approved organizational identity provider");
    }

    @GetMapping("/login-choice")
    public Map<String, String> loginChoice() {
        return Map.of(
            "loginUrl", "/oauth2/authorization/workforce",
            "note", "Choose approved fallback sign-in");
    }

    @GetMapping("/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("subject", authentication.getName());
    }

    @GetMapping("/admin/status")
    public Map<String, String> adminStatus() {
        return Map.of("result", "Admin policy gate passed");
    }
}
~~~

### 12.6. Running and Limitations

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell you can run `.\gradlew.bat bootRun`. Provision a real OIDC IdP with issuer URL, HTTPS, client ID/secret, and registered public redirect URI:

~~~text
WORKFORCE_OIDC_CLIENT_ID=<registered-client>
WORKFORCE_OIDC_CLIENT_SECRET=<secret-from-vault>
WORKFORCE_OIDC_ISSUER_URI=https://idp.partner.example/realms/workforce
WORKFORCE_ADMIN_ACR=urn:example:acr:phishing-resistant
~~~

These are illustrative values; no real IdP exists on `.example`, so running the command alone does not prove end-to-end login.

Expectation: `/oauth2/authorization/workforce` starts the OIDC redirect; `/login/oauth2/code/workforce` callback is handled by Spring; `/me` requires login; `/admin/status` is denied unless **both** the exact ACR and local authority are present. Admin roles are **not** granted in the demo so access is blocked by default, demonstrating fail-closed behavior.

**Never conclude that because the project starts cleanly, MFA, PKCE, local account linking, freshness, and tenant policies are all tested.** They require integration tests against a real IdP and organizational security config.

## 13. Combining This Module with Production Kerberos/SPNEGO

### 13.1. Service Principal and Keytab

~~~text
Kerberos realm:        EXAMPLE.COM
Public URL:            https://portal.example.com
SPN:                   HTTP/portal.example.com@EXAMPLE.COM
Service keytab:        /run/secrets/portal-http.keytab
KDC/DNS/krb5.conf:     Managed network configuration
Fallback provider:     OIDC workforce
~~~

The keytab is a secret; keep it out of Git, public Docker images, logs, and UI. Verify exact SPN/host, KVNO, encryption types, KDC realm, DNS, and time sync. Across multiple nodes, keytab and service principal rollouts must stay consistent.

### 13.2. Entry Point and Failure Handler Wiring Snippet

~~~java
// WIRING SNIPPET, NOT a standalone Java class.
// Requires Kerberos extension compatible with Boot 3.x Jakarta Servlet.
SpnegoEntryPoint entryPoint =
    new SpnegoEntryPoint("/login-choice");

SpnegoAuthenticationProcessingFilter spnegoFilter =
    new SpnegoAuthenticationProcessingFilter();

spnegoFilter.setAuthenticationManager(kerberosManager);
spnegoFilter.setSkipIfAlreadyAuthenticated(true);
spnegoFilter.setFailureHandler((request, response, exception) -> {
    // Do not log Authorization: Negotiate header/token.
    response.sendError(401, "Integrated sign-in failed");
});
~~~

`kerberosManager` is a real configured bean holding the Kerberos service-ticket provider, ticket validator/keytab, and local identity mapping. This snippet **only illustrates the extension points**, not a runnable project. Never insert the filter once into the Spring chain **and** let the Servlet container auto-register it a second time.

### 13.3. Browser Sends No Token: Do Not Wait for Filter Errors

If the browser stalls on the challenge, the server receives no token and triggers no failure handler callback. Provide a directly accessible fallback page with bounded Negotiate retries and no loops. OIDC callback endpoints must be handled by permit/protocol filters without a Negotiate challenge intercepting them first.

### 13.4. Reverse Proxy Terminating Kerberos

If a gateway verifies Kerberos and forwards the username in a header, the backend may trust it only after:
- The proxy strips all inbound client-supplied `X-Authenticated-User` headers;
- The proxy genuinely verifies Kerberos, realm, service principal, and policy;
- The gateway → app channel has mTLS/trusted service identity;
- User headers are never accepted when the gateway fails;
- The backend still maps local identity, roles, tenant, and assurance;
- Replay/spoofing defenses exist when bearer assertions are used.

Internet-supplied headers are **never** a safe "Kerberos fallback" merely because they contain a username.

## 14. Same Person: Kerberos Principal and OIDC Subject

Kerberos typically yields a principal:

~~~text
alice@EXAMPLE.COM
~~~

OIDC returns an identity in a verified ID Token, e.g.:

~~~text
iss = https://idp.partner.example/realms/workforce
sub = 7519b1ac-...
email = alice@example.com
~~~

Never auto-link based on email alone. Emails can change or be reassigned. Design an approved mapping:

~~~text
local_user_id = 104

external identities:
  (KERBEROS, EXAMPLE.COM, alice@EXAMPLE.COM) -> 104
  (OIDC, trusted-issuer, 7519b1ac-...)     -> 104
~~~

If IdPs A and B share an email, two distinct `issuer+sub` pairs do not automatically refer to the same local user. Cross-realm Kerberos must also be identified by trusted source, never just the username before `@`.

### 14.1. Forbid Silent Account Switching During Step-Up

A Kerberos-logged-in user is sent to the IdP for step-up. When the callback returns:
1. Verify the assertion/token from the approved IdP.
2. Match the identity against the **exact current local user** via the approved mapping.
3. If the subject differs, never attach MFA evidence to the previous user's session.
4. If it matches, update assurance/freshness with a policy-defined TTL and rotate the session ID as needed.
5. Re-check roles, tenant ownership, disabled status, and resource authorization.

Accepting a valid ID Token **for a different user** while preserving the prior session's admin rights is a severe identity mix-up vulnerability.

## 15. MFA Step-Up for Sensitive Transactions

Example:
1. Kerberos user is verified and accesses `GET /orders` under BASIC policy.
2. User POSTs `/orders/471/approve`; policy requires fresh MFA.
3. Spring detects no validated MFA evidence → refuses to execute the transaction.
4. User is redirected to the IdP with contracted auth request/controls.
5. IdP performs appropriate MFA and returns a validated ID Token/Assertion with assurance/freshness.
6. SP verifies matching subject, `auth_time`, and claim context.
7. SP verifies `APP_ORDER_APPROVE` and matching tenant/resource.
8. The transaction executes only if **all** conditions pass.

`prompt=login`/`max_age` in OIDC can request reauthentication per profile, yet **does not enforce MFA by itself**. You must request the exact authentication context and verify the returned evidence post-callback.

Never mark step-up as "permanent". Assurance freshness requires a lifetime and must reset upon logout, session expiration, or account switching.

## 16. Avoiding Protocol Downgrade and Expanding Credential Surface

### 16.1. SPNEGO May Not Be Kerberos in Every Environment

In some Windows setups, Negotiate can use NTLM when Kerberos fails. NTLM carries distinct relay/credential abuse risks. Organizations must audit/restrict NTLM and inspect which protocol the provider/gateway actually accepted.

Never set `method=KERBEROS` or `phishingResistant=true` solely because an HTTP `Negotiate` challenge occurred.

### 16.2. HTTP Basic Does Not Replace MFA

`WWW-Authenticate: Basic` causes browsers to send encoded username/password repeatedly per request. TLS protects transport but adds neither MFA nor phishing resistance. Auto-enabling Basic fallback encourages users to type domain passwords in more places, increasing phishing exposure.

If a password/LDAP flow is strictly required for an approved legacy group, require LDAPS/TLS, separate MFA, rate limiting, lockout, password hygiene, identity linking, CSRF, session fixation, and equivalent controls per resource policy.

### 16.3. Never Retry "Until Some Provider Accepts"

Errors like `INVALID_NEGOTIATE_TOKEN`, invalid OIDC signatures, MFA-blocked IdPs, or disabled accounts must never turn into "try a weaker provider until an Authentication succeeds". Offering a manual route to a valid IdP **differs** from automatically bypassing authentication checks.

## 17. Break-Glass During a Total Outage

When KDC, AD, and IdP are all unavailable, emergency recovery may require **break-glass**, yet it is never a default admin password for general users.

Minimum conditions set by organizational policy:
1. Dedicated emergency identity, never shared with personal accounts.
2. Vaulted credentials accessed under dual-control approval per risk policy.
3. Hardware MFA/phishing-resistant method or security-approved equivalent.
4. Minimum privileges scoped to recovery tasks, never blanket business API access.
5. Automatic TTL/expiration; revoked immediately after the incident.
6. Real-time auditing, security alerts, and post-incident review.
7. Never triggered by `?emergency=true` or an unverified cookie.
8. Never treat "KDC outage" as automatic permission for any user to use break-glass.
9. Periodic drills and kill-switch/rotation tests.
10. If required assurance for a resource cannot be met, halt that resource rather than lowering standards.

## 18. Operations: Kerberos Outage and Fallback IdP Availability

### 18.1. KDC Outage

Inspect:
- KDC/realm DNS SRV, VPN, firewall, network reachability;
- service principal registration/duplicate SPNs, encryption types, keytab KVNOs;
- clock synchronization/NTP;
- trusted Kerberos realms, cross-realm trusts;
- browser trusted URIs/enterprise policies;
- redacted server logs.

**Crucial point:** A "fallback" OIDC IdP might itself rely on the same Active Directory/KDC, meaning **it is not guaranteed to survive independently** in the same outage. Test real failure domains rather than merely putting two login buttons on screen.

### 18.2. Controlled Recovery Plan

1. Confirm the incident and track method availability from observability, **never from user query strings**.
2. Present approved fallback without altering resource policies.
3. For privileged resources, enforce full MFA/phishing resistance/freshness.
4. Monitor fallback rates, invalid tokens, and identity linking errors.
5. Remediate KDC/SPN/keytab/IdP root causes; never disable GSS checks.
6. Upon recovery, run regression tests and roll back feature flags under control.
7. Audit active fallback sessions, revoked permissions, and security incident logs.

## 19. Metrics, Auditing, and Data Boundaries

### 19.1. Suggested Metrics

~~~text
auth_spnego_challenge_total{client_family}
auth_spnego_no_token_total{route_group}
auth_spnego_invalid_ticket_total{reason_class}
auth_fallback_selected_total{provider}
auth_fallback_login_total{provider,result}
auth_assurance_denied_total{resource_group,requirement}
auth_oidc_invalid_response_total{reason_class}
auth_account_link_failure_total{provider}
auth_stepup_result_total{provider,result}
auth_kdc_unavailable_total{realm}
auth_breakglass_total{purpose,result}
auth_redirect_loop_total{client_family}
~~~

These are **suggested metrics**, not Spring defaults. Labels must never contain usernames, UPNs, emails, raw Kerberos tickets, OIDC tokens, session IDs, or user-specific URLs.

### 19.2. Audit Record

~~~text
event=authentication_decision
attempt_id=internal-random-id
source=KERBEROS|OIDC|SAML|BREAK_GLASS
trusted_realm_or_issuer=approved-reference
identity_link=PASS|FAIL
account_state=ACTIVE|DISABLED
resource_requirement=WORKFORCE_MFA
assurance_evidence=VERIFIED|INSUFFICIENT|STALE
local_authorization=ALLOW|DENY
result=ALLOW|CHALLENGE|DENY
reason_class=NO_TOKEN|KDC_OUTAGE|MFA_MISSING|...
~~~

Never log `Authorization: Negotiate`, ID Tokens/access tokens, keytabs, passwords, or MFA secrets. For user investigations, use internal IDs with strict access controls and retention.

### 19.3. Alerts

| Signal | Action |
| --- | --- |
| Sudden spike in fallback rate | Investigate KDC/SPN/role changes and downgrade attacks. |
| Rising invalid Negotiate tickets | Analyze token spoofing/replay/clock drift; rate-limit per policy. |
| Rising ACR mismatches on admin | Inspect IdP MFA config and assurance mapping; fail closed. |
| Unusual identity linking failures | Halt auto-linking and check for account takeover. |
| Privileged access after fallback without MFA | Critical incident; revoke sessions and fix policy. |
| OIDC callback receives 401 Negotiate/302 loop | Fix SecurityFilterChain matchers/filter order. |
| Break-glass used outside approved incident | Security alert, post-review, and revocation. |

## 20. Integration Test Suite

| ID | Scenario | Outcome |
| --- | --- | --- |
| F01 | Domain-joined browser, valid Kerberos ticket, ACTIVE account. | Login succeeds for BASIC resource. |
| F02 | Browser omits `Authorization: Negotiate`. | Fallback choice shown; no fake Authentication created. |
| F03 | Browser stops after 401. | No loop; user can reach login-choice. |
| F04 | Forged Negotiate token. | Rejected; no roles granted. |
| F05 | Negotiate actually selects NTLM against policy. | Rejected/downgrade blocked per config. |
| F06 | SPN mismatches host. | Kerberos validation fails; no bypass. |
| F07 | Stale keytab KVNO on one node. | Ops alert raised; fallback still obeys policy. |
| F08 | KDC offline, OIDC healthy. | OIDC login allowed if evidence meets policy. |
| F09 | OIDC also impacted by AD/KDC outage. | No bypass; fails closed. |
| F10 | OIDC issuer outside allowlist. | Assertion rejected. |
| F11 | Invalid ID Token signature/exp/aud. | Rejected. |
| F12 | Invalid OIDC state/nonce. | Rejected. |
| F13 | Replayed Authorization Code. | Protocol rejects. |
| F14 | Invalid OIDC redirect URL host/HTTPS. | Rejected/fix trusted settings. |
| F15 | Password-only IdP, BASIC resource. | Accepted only if approved policy permits. |
| F16 | Password-only IdP, MFA resource. | Denied/step-up. |
| F17 | OTP MFA yet resource requires phishing resistance. | Denied/step-up. |
| F18 | Unmapped or missing ACR. | Privileged resource denied. |
| F19 | Valid ACR yet stale `auth_time`. | Fresh step-up required. |
| F20 | Valid ACR yet missing local admin role. | Denied. |
| F21 | Valid OIDC identity yet disabled local account. | Denied. |
| F22 | Same email at two IdPs, different issuer/sub. | No auto-link. |
| F23 | Validly linked Kerberos principal and OIDC subject. | Maps to same local user ID. |
| F24 | Step-up OIDC returns a different subject than Kerberos user. | Rejected/account-switch handled; old rights not kept. |
| F25 | Session ID not rotated on auth success. | Test catches fixation risk. |
| F26 | Machine API receives 302 HTML login instead of 401. | Test fails; separate API chain. |
| F27 | Fallback page blocked by Negotiate challenge. | Test fails; fix permitAll/route. |
| F28 | OIDC callback intercepted by SPNEGO filter. | Test fails; fix matcher/order. |
| F29 | Browser sends `returnTo=https://evil.example`. | No open redirect. |
| F30 | Browser sends `X-Authenticated-User: admin`. | Header stripped/untrusted. |
| F31 | Browser sends arbitrary issuer/realm. | Does not alter approved trust config. |
| F32 | Account revoked while Kerberos session remains. | Authorization/session revocation enforced properly. |
| F33 | Fallback session cookie lacks secure flags. | QA fails; enforce secure attributes. |
| F34 | Fallback login uses Basic unconditionally. | QA fails per policy; never auto-enabled. |
| F35 | KDC outage with unapproved break-glass. | Denied. |
| F36 | Approved break-glass past TTL. | Scope/privileges revoked, audited. |
| F37 | Brute-force/password guessing on fallback. | Rate-limited and locked out. |
| F38 | User in tenant A uses IdP B. | No cross-tenant access. |
| F39 | Proxy forwards spoofed identity header. | Rejected; mTLS/attestation required. |
| F40 | Kerberos fails due to clock skew. | Fix NTP; never widen validation endlessly. |
| F41 | MFA step-up finishes under another user. | Identity mismatch rejected. |
| F42 | Admin lacks policy-required device compliance. | Denied despite valid login. |
| F43 | OIDC client secret or keytab appears in logs. | QA fails/rotate/incident. |
| F44 | Kerberos restored, user retries Negotiate. | Normal flow resumes without lowering policy. |

### 20.1. Lab A — SPNEGO and Fallback

1. Prepare test KDC/AD, exact SPN, keytab, and domain-joined browser.
2. Confirm 401 Negotiate → valid Authorization Negotiate is accepted.
3. Use off-domain browser: no token sent; fallback page displayed.
4. Send malformed token in test environment and confirm no fake session is created.
5. Temporarily stop test KDC, verify OIDC fallback while still enforcing resource policy.

### 20.2. Lab B — Assurance and Account Linking

1. Test OIDC IdP configured with MFA/passkey and contracted ACR.
2. Open dashboard with BASIC evidence; attempt admin without MFA and observe denial.
3. Complete step-up for the same identity; verify `auth_time`/freshness and local roles.
4. Test mismatched subject, unknown ACR, disabled user, and wrong tenant.
5. Keep role/tenant checks identical when switching login methods.

### 20.3. Lab C — Outage and Break-Glass

1. Simulate bad keytab, clock skew, DNS/KDC outage, and IdP outage.
2. Verify logs/metrics contain zero raw credentials.
3. Test fallback kill switches and keytab/secret rotation.
4. Simulate time-bounded approved break-glass and auditing.
5. Confirm no password-only shortcut exists for high-risk resources.

## 21. Self-Assessment Questions

**1. Can HTTP Basic be auto-enabled when Kerberos sends no ticket?**  
No. Another authentication method may be used only if approved and compliant with policy.

**2. Why doesn't a filter failure handler solve all unsupported browsers?**  
The browser may send no token at all, triggering no server-side authentication exception to invoke the handler.

**3. Does OIDC login success imply MFA?**  
No. The IdP must perform MFA and emit contract-verified evidence checked by the SP.

**4. Is ACR a fixed global assurance scale?**  
No. ACR values are defined by each IdP/profile and require exact-value mapping.

**5. Is a valid Kerberos ticket always phishing-resistant MFA?**  
No. You must evaluate the authenticator ceremony/device/evidence rather than inferring from the protocol.

**6. An OIDC ID Token's email matches a Kerberos username — should they auto-link?**  
No. Use approved trusted `issuer+sub` and realm/principal/immutable identity mappings.

**7. What if the local account is disabled while OIDC IdP succeeds?**  
Still DENY.

**8. A resource requires phishing resistance yet the IdP only offers SMS OTP?**  
Deny/step-up using a policy-compliant authenticator.

**9. What if Kerberos user A steps up via OIDC using account B?**  
Never attach B's evidence to A or retain A's permissions.

**10. Is a KDC outage a license for break-glass?**  
No. Break-glass requires explicit approval, dedicated credentials, TTL, and auditing.

**11. When the fallback IdP is down, can ROLE_USER be temporarily granted?**  
No; fail closed for new authentications.

**12. Can basic resources and admin resources have different requirements?**  
Yes, provided policy is enforced at the resource/action level and cannot be bypassed.

**13. Why should APIs not return a 302 HTML login to machine clients?**  
Because machine protocols require 401/403 or OAuth2/mTLS, avoiding loops and parsing failures.

**14. If a gateway forwards `X-Authenticated-User`, when is it trustworthy?**  
Only through an authenticated gateway over a trusted protected channel with client headers stripped.

**15. Does passwordless Kerberos SSO prove the user just completed MFA?**  
No; that is an SSO UX trait and requires separate evidence for MFA/freshness.

## 22. Production Checklist

- [ ] Resource policy accurately defines BASIC, MFA, and PHISHING_RESISTANT_FRESH.
- [ ] AAL/MFA never inferred solely from "Kerberos" or "OIDC".
- [ ] Distinct handling for no-token, KDC outage, config error, invalid token, and disabled account.
- [ ] SPNEGO tokens verified via real provider/GSS-API/realm/keytab, never mock providers.
- [ ] NTLM/Basic downgrades never auto-enabled without security approval.
- [ ] OIDC/SAML fallback uses IdP/issuer/redirect URIs strictly from trusted configuration.
- [ ] OIDC Authorization Code, PKCE, state/nonce, token validation, and HTTPS align with framework/version.
- [ ] ACR/AMR/`auth_time` mappings contracted, enforcing step-up on sensitive resources.
- [ ] Account linking between Kerberos realm/principal ↔ OIDC `issuer/sub` approved.
- [ ] Disabled users, local roles, tenants, and resource ownership verified across all methods.
- [ ] OIDC callbacks and fallback pages never blocked by Negotiate challenges/redirect loops.
- [ ] Browser CSRF/session fixation/cookie/reauth policies preserved when switching methods.
- [ ] Machine API clients have dedicated security chains/responses.
- [ ] Reverse proxy strips untrusted headers and controls forwarded host/origin.
- [ ] Keytabs/secrets vaulted, with KVNO/rotation and NTP controlled.
- [ ] Verified whether IdP and KDC truly have independent failure domains.
- [ ] Break-glass has approval, MFA, least privilege, TTL, alerts, and post-review.
- [ ] Logs exclude raw Kerberos tickets, passwords, tokens, and keytabs; metrics minimize PII.
- [ ] Kill switches and rollback plans exist without relaxing policy.
- [ ] Tests F01–F44 or equivalent coverage executed in staging.
- [ ] Spring Security Kerberos extension/Jakarta Servlet compatibility verified before go-live.

## Key Takeaways

> **A Kerberos/SPNEGO failure is never a reason to lower authentication standards.** Allow fallback solely to an **approved and genuinely verified method**, with MFA/phishing resistance/freshness satisfying the resource's requirements; continue checking local user, permissions, and tenant. If no compliant method is available, **fail closed** and show support guidance instead of automatically downgrading to NTLM, Basic, password-only, or trusting self-asserted headers.

### Official References

- [Spring Security Kerberos — SpnegoEntryPoint](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/web/authentication/SpnegoEntryPoint.html): Negotiate challenge and fallback URL.
- [Spring Security Kerberos — SpnegoAuthenticationProcessingFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/web/authentication/SpnegoAuthenticationProcessingFilter.html): filter/AuthenticationManager/failure handler and browsers sending no token.
- [Spring Security Kerberos Extension source](https://github.com/spring-projects/spring-security-kerberos): modules, samples, compatibility.
- [Spring Security — OAuth2 Login Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): Authorization Code, OIDC client registration, and callbacks.
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): resource authorization, AuthorizationManager.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): SecurityContext, session fixation, logout.
- [NIST SP 800-63B-4 (2025)](https://pages.nist.gov/800-63-4/sp800-63b.html): Authenticator Assurance Levels and MFA/phishing resistance.
- [Microsoft — Integrated Windows Authentication](https://learn.microsoft.com/en-us/aspnet/web-api/overview/security/integrated-windows-authentication): Kerberos/NTLM and intranet limitations.
- [Microsoft — Restrict NTLM authentication](https://learn.microsoft.com/windows/security/threat-protection/security-policy-settings/network-security-restrict-ntlm-ntlm-authentication-in-this-domain): NTLM audit/restriction policies.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, acr, amr, auth_time.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): MFA, authentication controls, and brute-force defenses.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session IDs, cookies, and revocation.

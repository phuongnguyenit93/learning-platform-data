# Built-In MFA by Spring Security Version and What You Must Build Yourself When Not Yet Supported

## 1. Why Does This Topic Depend Heavily on Version?

**MFA (Multi-Factor Authentication)** requires authentication evidence from more than one **independent factor category** or a properly verified multi-factor authenticator. Supporting *multiple ways to log in* (password, one-time token, passkey, OIDC) **does not mean** every user is required to pass MFA.

With Spring Security, three capabilities must be separated:

1. **Authentication mechanisms:** which filters/providers/services does the framework offer to verify a specific credential?
2. **Factor tracking & enforcement:** does the framework track **which factors have been proven** and enforce all required factors on endpoints?
3. **MFA lifecycle and operations:** are authenticator enrollment, secret/key storage, retries, lockout, recovery, revocation, auditing, step-up, and session/token assurance complete?

A Spring Security **6.5** application can use `formLogin()`, `oneTimeTokenLogin()`, and `webAuthn()`, yet lacks **Spring Security 7**’s built-in overarching MFA mechanism via `@EnableMultiFactorAuthentication`. Even after upgrading, never assume the library handles every MFA business requirement: **TOTP setup/verification, delivery channels, recovery, risk policies, and IdP/API integration remain the product’s job**.

After this lesson, you will be able to:

- Build a **version-based capability matrix** instead of copying 7.x code into 6.x.
- Use `FactorGrantedAuthority`, `@EnableMultiFactorAuthentication`, and `AuthorizationManagerFactory` on Spring Security 7 Servlet.
- Know why **One-Time Token (OTT) differs from TOTP/HOTP**, and why an email magic link does not by default qualify as an independent MFA factor.
- Design an **MFA gate** in Spring Security 6.x when built-in factor authorization is absent.
- Bind proof to **user + session + timestamp + security-state version**, preventing reuse of “MFA verified” flags after password reset or logout.
- Handle MFA across form login, WebAuthn/passkeys, OIDC, JWT resource servers, and WebFlux.
- Write tests for single-factor, full-factor, expired tokens, replay, reset/recovery, and upgrades.

**Scope:** Java 17+, Spring Boot 3.x / Spring Security 6.5.x and Spring Boot 4.x / Spring Security 7.x, focusing on **Servlet**. API code snippets are clearly tagged by version; standalone pure-Java programs below compile independently. When running a real application, use **BOM/dependency management** so versions of `spring-security-core`, `config`, `web`, and `test` never mix.

## 2. Accurate Definition: MFA Is Not Just Adding an OTP Page

Common authentication methods:

| Method | Evidence Category | Points Requiring Caution |
| --- | --- | --- |
| Password | **Knowledge**: something the user knows | Password + a second PIN usually remain the same factor category |
| Authenticator-app TOTP | **Possession** of a secret on a device, typically a single-factor OTP | Vulnerable to phishing, replay, and clock drift |
| Security key/WebAuthn with user verification | Cryptographic authenticator, potentially **multi-factor** when user verification is enforced | Must check UV flag, RP ID, origin, challenge, public key, and sign counter/risk |
| Synced passkey | Cryptographic key; can sync across devices | Not automatically device-bound; assurance depends on UV/key management |
| SMS/voice OTP | Out-of-band over telecom network | SIM-swap risk; restricted under NIST in relevant contexts |
| Email magic link | Proves control of an inbox via link/token | **Does not qualify as an independent possession factor** per NIST OOB; email may share password/device |
| Spring One-Time Token | Server creates single-use token, delivered via app-chosen channel | **OTT is not TOTP**; the delivery channel determines assurance level |
| Recovery code | Single-use backup secret | Needs secure issuance/storage/revocation and proper recovery workflow |
| OAuth/OIDC ID token | Assertion from an authenticated IdP | **Does not prove MFA on its own** unless the IdP supplies trusted assurance evidence |

Per [NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b.html), **AAL2** requires two different factors or a qualifying multi-factor authenticator; email may not be used as an out-of-band authenticator under that standard. That is an **assurance standard**, not a ban on every form of email login in every app; state your compliance target accurately.

**Litmus test:** if an attacker steals only the user’s password, can they also grab the second code via **the same email inbox protected only by that password**? If yes, what is called “MFA” may lack risk independence.

## 3. Feature Matrix by Version: Do Not Confuse Authentication Mechanisms with MFA Policy

| Component | Older Spring Security 5.x / 6.x Before Feature | Spring Security **6.5.x** | Spring Security **7.0+** |
| --- | --- | --- | --- |
| Form login, `AuthenticationManager`, providers, CSRF/session | Long-standing | Yes | Yes, with upgraded APIs/DSL |
| UserDetails/passwords/roles/authorities | Yes | Yes | Yes |
| Custom `AuthorizationManager` checking a rule | Depending on minor, 5.x/6.x model | Can write a custom MFA gate | Yes, plus factor authorization integration |
| One-Time Token login `.oneTimeTokenLogin(...)` | Do not assume in older minors | **Yes** | **Yes** |
| WebAuthn/passkeys `.webAuthn(...)` | Do not assume in older minors | **Yes**, needs matching deps/repositories | **Yes**, tighter factor-policy integration |
| `FactorGrantedAuthority` and `issuedAt` | **No official equivalent API** | **Not yet available** | **Available from 7.0** |
| `@EnableMultiFactorAuthentication` | Not available | **Not available** | **Available from 7.0**, Servlet MFA |
| `AuthorizationManagerFactory` MFA rules/redirect to missing factor | No 7.x shared API | Custom orchestration/policy | Officially supported per 7.x docs |
| TOTP/HOTP enrollment/verification server for your app | Must build/integrate yourself | **Must build yourself or use library/IdP** | **Does not turn OTT into TOTP**; still needs matching component |
| Email/SMS/notification delivery for OTT | App responsibility | **App supplies handler/channel** | **App supplies handler/channel** |
| Recovery, backup codes, device loss, audit, external revocation | App/IdP | App/IdP | **Still app/IdP** |
| Equivalent MFA on WebFlux | Custom | Custom reactive orchestration | 7.x `@EnableMultiFactorAuthentication` docs note **not yet applicable to reactive** (re-verify when upgrading) |

**Never write** “Spring Security 6.5 does not support OTP” when referring to **One-Time Token login**. The accurate statement is: 6.5 has OTT login; **TOTP/HOTP authenticators** and **policy binding multiple factors into one authentication** are not automatically created by that DSL alone.

### 3.1. Checking Which Version Runs at Runtime

In a Gradle project with Spring Boot dependency management:

```bash
./gradlew dependencyInsight --dependency spring-security-config \
  --configuration runtimeClasspath

./gradlew dependencyInsight --dependency spring-security-core \
  --configuration runtimeClasspath
```

Windows PowerShell/cmd uses `gradlew.bat`. In Maven:

```bash
mvn dependency:tree -Dincludes=org.springframework.security
```

Check **resolved versions**, not just what is written in `build.gradle`. If the project is still on Boot 3.x/Security 6.x and IDE autocomplete cannot find `FactorGrantedAuthority` or `@EnableMultiFactorAuthentication`, **that API likely belongs to the 7.x branch**, not an ordinary import mistake.

### 3.2. If You Must Stay on an Older Version

Do not add `spring-security-config:7.x` to an app with `spring-security-core:6.x` just to “grab the MFA annotation”. Modules and the Boot runtime must align under the BOM; mixing majors/minors arbitrarily invites `NoSuchMethodError`, filter-chain failures, and unpredictable behavior. Two main options:

1. **Controlled stack upgrade** to a version supporting built-in MFA, backed by regression tests for login, sessions, APIs, claims, and method security.
2. **Keep the current stack**, build MFA enforcement at the **application boundary**, or delegate MFA to a trusted IdP without assuming the library fills missing pieces.

## 4. Two-Tier Architecture: Proving Factors and Deciding Access

```text
                   FIRST FACTOR
      Password / passkey / trusted IdP assertion
                          |
                          v
                 Authentication result
                          |
                          v
                   MFA policy checks
                          |
         +----------------+--------------------+
         |                                     |
  Required factors met?                Missing factor(s)?
         |                                     |
        YES                                    NO
         |                                     |
         v                                     v
   Authorized actions                Challenge/step-up path
   appropriate to AAL                 e.g. TOTP or WebAuthn
                                               |
                                       Server-side verification
                                               |
                                       One-time/replay control
                                               |
                                       Record verified factor
                                               |
                                       Re-evaluate authorization
```

**Simply “having two filters/providers” is OR, not AND.** A user can log in with password **or** OTT if both are enabled without a policy requiring both to be proven. MFA is **an authorization condition based on factors actually proven**.

### 4.1. What Must Never Be Accepted as MFA Proof

- Query parameter `?mfa=true` or client-supplied HTTP headers.
- `UserDetails.getAuthorities()` containing a static `ROLE_MFA` stored in the roles table beforehand.
- Unsigned, unencrypted/unbound cookies like `mfaPassed=true` lacking server-side verification.
- “User previously enrolled TOTP” — enrollment is not **just verified a code**.
- Existence of a `SecurityContext` after password login or `isAuthenticated()==true`.
- A `remember-me` cookie or redirecting to an OTP page prior to verification.
- JWT payload `"amr":["mfa"]` **before** verifying signature, issuer, audience, expiry, token type, and authoritative issuer.

## 5. Spring Security 7: What Is FactorGrantedAuthority?

Starting in Spring Security **7.0**, `org.springframework.security.core.authority.FactorGrantedAuthority` represents a factor used during authentication; it implements `GrantedAuthority` and records **`issuedAt`**.

Notable constants:

| Constant | Authority String | Typical Source |
| --- | --- | --- |
| `FactorGrantedAuthority.PASSWORD_AUTHORITY` | `FACTOR_PASSWORD` | Password login |
| `FactorGrantedAuthority.OTT_AUTHORITY` | `FACTOR_OTT` | Spring One-Time Token login |
| `FactorGrantedAuthority.WEBAUTHN_AUTHORITY` | `FACTOR_WEBAUTHN` | WebAuthn authentication |
| `FactorGrantedAuthority.X509_AUTHORITY` | `FACTOR_X509` | X.509 |
| `FactorGrantedAuthority.BEARER_AUTHORITY` | `FACTOR_BEARER` | Bearer authentication |
| `FactorGrantedAuthority.AUTHORIZATION_CODE_AUTHORITY` | `FACTOR_AUTHORIZATION_CODE` | OAuth2 authorization-code flow |

**Warning:** `FACTOR_BEARER` describes the **Bearer authentication mechanism**, not proof that the token underwent MFA at the IdP. Likewise, `FACTOR_OTT` only indicates Spring’s OTT flow completed, not that the OTT arrived via an independent possession channel meeting NIST AAL2.

`FactorGrantedAuthority` is evidence attached within a trusted authentication flow. Never grant this authority simply because a client asked for it; a custom provider must **verify the factor first**, then issue the factor authority. `issuedAt` lets rules enforce factor **freshness**, preventing an authentication from months ago from passing as fresh MFA forever.

### 5.1. This Is a 7.x Type, Not a Recipe for Enabling MFA on 6.x

On 6.5, if you need to record proof, use a **dedicated model** or custom `AuthorizationManager`. Do not import `FactorGrantedAuthority` from 7.x sources and pass it through sessions holding 6.5 Authentications; that mixes binary compatibility.

## 6. Spring Security 7: Enabling Mandatory MFA via Annotation

Official 7.x docs provide `@EnableMultiFactorAuthentication` to attach factor requirements to authorization rules.

This is a **Spring Security 7.x Servlet snippet** (placed in `@Configuration`; requires imports, dependency management, an account repository, and OTT delivery):

```java
@Configuration
@EnableWebSecurity
@EnableMultiFactorAuthentication(authorities = {
        FactorGrantedAuthority.PASSWORD_AUTHORITY,
        FactorGrantedAuthority.OTT_AUTHORITY
})
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .oneTimeTokenLogin(Customizer.withDefaults());

        return http.build();
    }
}
```

When configured properly:

- `/admin/**` requires **`ROLE_ADMIN` + `FACTOR_PASSWORD` + `FACTOR_OTT`**.
- Other `authenticated()` endpoints also require both PASSWORD and OTT if the annotation applies globally.
- A user who just logged in with password but lacks OTT must go through the OTT flow to satisfy the rule.
- When a user has OTT without password, they may need to complete password login per the rule.

**Important:** `oneTimeTokenLogin(Customizer.withDefaults())` configures the OTT generate/consume mechanism, yet **does not decide how tokens reach users in real life**. You must supply a `OneTimeTokenGenerationSuccessHandler` and an appropriate delivery channel. Without delivery, the config may start up cleanly while users **cannot finish the flow** as intended. Distinguish *authentication feature available* from *end-to-end MFA deployed*.

### 6.1. Importing the Right Packages

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.authorization.EnableMultiFactorAuthentication;
import org.springframework.security.core.authority.FactorGrantedAuthority;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.Customizer;
import org.springframework.security.web.SecurityFilterChain;
```

These are **Security 7 imports**. If the IDE cannot find `EnableMultiFactorAuthentication` in Boot 3/Security 6.5, do not edit package names to force a match: verify your resolved version first.

### 6.2. MFA Enforcement Must Cover Sensitive Data Control Paths

A global annotation is easy to audit, yet you must test login endpoints, logout, password reset, static resources, and callbacks to avoid redirect loops. If you only want to protect admin/credential-change routes, use selective MFA in the next section rather than forcing a machine-to-machine Bearer token through an inappropriate browser OTT challenge.

## 7. Spring Security 7: Selective MFA and Dynamic Conditions

### 7.1. Selective MFA with AuthorizationManagerFactory

In 7.x, docs provide `AuthorizationManagerFactories.multiFactor()`. Example **applying MFA only to admin and settings**:

```java
// Snippet inside a Spring Security 7 configuration, with appropriate imports.
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {

    var mfa = AuthorizationManagerFactories.multiFactor()
            .requireFactors(
                    FactorGrantedAuthority.PASSWORD_AUTHORITY,
                    FactorGrantedAuthority.OTT_AUTHORITY)
            .build();

    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/admin/**").access(mfa.hasRole("ADMIN"))
            .requestMatchers("/user/settings/**").access(mfa.authenticated())
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .oneTimeTokenLogin(Customizer.withDefaults());

    return http.build();
}
```

Per the 7.x reference, with this selective approach you can enable `@EnableMultiFactorAuthentication(authorities = {})` to activate MFA support **without publishing a global factory requiring MFA on every endpoint**. With the snippet above, **do not** expose the `mfa` factory as a global Bean if the goal is protecting only specific rules. Never assume `.hasRole("ADMIN")` includes MFA automatically unless you attach the MFA rule to the admin route in non-global configurations.

### 7.2. Conditional MFA

Policies to consider:

- Only accounts with admin roles require an extra factor.
- High-risk transactions or amounts exceeding a threshold trigger step-up.
- Recently enrolled or reset credentials always require a strong factor.
- Require Password + WebAuthn only for users who have enrolled a passkey (when that matches assurance requirements).
- Require recent reauthentication within a shorter window before changing recovery methods.

Spring Security 7 provides `AuthorizationManagerFactory` and MFA conditions, such as `.when(...)` or `MultiFactorCondition.WEBAUTHN_REGISTERED` on supported annotation branches. Never write “user has a passkey → exempt from second factor” when policy requires both.

### 7.3. Sensitive Transactions Still Require Business-Object Checks

`FACTOR_PASSWORD` + `FACTOR_OTT` do not replace:

- Checking that the user **owns** the object being modified.
- `ROLE_ADMIN` or `SCOPE_payment:approve`.
- Four-eyes / two-person approval.
- Verifying amounts, recipients, and transfer intent/dynamic linking if required by policy.
- Rate limits, fraud detection, device trust, and auditing.

**MFA is an additional assurance axis, not an authorization bypass.**

## 8. Spring Security 7: Freshness and Combining Multiple Factors

`FactorGrantedAuthority.getIssuedAt()` records when a factor was proven, and a policy may require **password within 30 minutes**, **WebAuthn within 5 minutes**, plus active admin privileges.

7.x offers a factor builder with `validDuration(...)`:

```java
// 7.x snippet, not a full class/bean.
var recentPassword = AuthorizationManagerFactories.multiFactor()
        .requireFactor(factor -> factor
            .passwordAuthority()
            .validDuration(Duration.ofMinutes(30)))
        .build();
```

You must still organize factor constraints per action and ensure server clock/token/session consistency. **Never use client timestamps** to decide “the OTP was just verified”.

### 8.1. A Passkey Can Satisfy Policy Differently

A policy might accept:

- **WebAuthn with sufficient assurance**; or
- **Password + authenticator OTP**.

The 7.x docs illustrate `AllRequiredFactorsAuthorizationManager.anyOf(...)`. Never assume **every WebAuthn assertion** has identical UV/assurance; define user verification, authenticator provenance, and compliance requirements before treating WebAuthn as a sufficient branch. A passkey can already act as a **multi-factor authenticator** when relevant criteria are met, avoiding forcing an extra password solely to count two screens.

### 8.2. Replacing a Factor Method Requires Verifiable Policy Changes

For example, if a user loses a security key, never allow a “skip factor button” that issues a fake `FACTOR_WEBAUTHN`. Recovery is a **security-sensitive authentication path** requiring appropriate assurance, auditing, and revocation of the old credential.

## 9. Spring Security 6.5 OTT: What Is Built In and What Is Missing?

Spring Security **6.5.11** includes:

```java
http.oneTimeTokenLogin(Customizer.withDefaults());
```

Reference flow:

```text
User requests a one-time token
    |
    v
OneTimeTokenService.generate(...)
    |
    v
OneTimeTokenGenerationSuccessHandler
    |
    +--> App sends token/magic link via delivery channel
    |
    v
User opens/submits token into OTT submit flow
    |
    v
OneTimeTokenService.consume(...)
    |
    v
Spring Security creates Authentication if valid
```

The framework supports **generation, consumption, filters, and a default submit page**, yet **cannot infer your product’s email/phone/token transport**. 6.5 ships with `InMemoryOneTimeTokenService` by default and `JdbcOneTimeTokenService` for persistence per the docs.

### 9.1. OTT Differs from TOTP/HOTP

| Criterion | One-Time Token (OTT) | TOTP/HOTP |
| --- | --- | --- |
| Who generates the per-use secret/value? | Server generates on user request | Authenticator computes from **enrolled secret** and time/counter |
| Delivery to user | Usually email/SMS/magic link via app handler | No per-login transmission; app computes code locally |
| Initial setup | May not require enrolling a standalone authenticator | Requires securely enrolling secret/device |
| Relation to password | Can be an **alternative login** if not forced together | Can be a **second factor** in a password+TOTP flow |
| Replay resistance | Token must support atomic one-time consumption | Must track TOTP counter/step or prevent replay |
| Phishing resistance | Depends on design; links can still be phished | **Not phishing-resistant** |
| AAL2 evidence | Not automatic just from the name OTT | Depends on authenticator/enrollment/verification and entire system |

Therefore, **`.formLogin()` + `.oneTimeTokenLogin()` on 6.5 does not by default guarantee users must use both**. If OTT is sent by email, never assume password + email link satisfies NIST OOB MFA.

### 9.2. Operational OTT Components You Must Design

- Ensure the delivery channel is user-verified and accurately bound to the account.
- Give tokens sufficient entropy, short TTLs, and atomic single-use consumption.
- Never log raw tokens; never embed links/tokens in analytics, Referer headers, or third parties.
- Rate-limit generate/resend/consume; return generic responses to prevent user enumeration.
- Multi-node setups need a shared store or consistent token service, avoiding in-memory stores at scale.
- Verify user status (disabled/locked/deleted), account mapping, nonces, and session binding per policy.
- Handle just-expired tokens, reuse attempts, concurrent requests, and resend races.
- Model the distinction between **OTT login** and **post-password step-up** as a state machine, not just UI redirects.

## 10. WebAuthn/Passkeys Exist in 6.5, Yet Enrollment and Assurance Need Care

Spring Security **6.5** supports passkeys via:

```java
http.webAuthn(webAuthn -> webAuthn
        .rpId("example.com")
        .allowedOrigins("https://example.com"));
```

This is a Servlet config snippet. The 6.5 reference uses `webauthn4j-core` and repositories such as `UserCredentialRepository` and `PublicKeyCredentialUserEntityRepository`, with corresponding JDBC options. Check dependency versions compatible with your BOM and official docs rather than copying old versions blindly.

**Spring verifies the WebAuthn ceremony**, while the product still owns:

- Credential registration only for verified accounts; enrolling a new key may require recent MFA.
- RP ID, origins, HTTPS, challenges, and user presence/user verification policies.
- Storing credential IDs, public keys, metadata/backup flags, and signCount/risk signals.
- Authorization rules for who can delete, rename, revoke, or add credentials.
- Multiple devices, synced passkeys, device loss, and recovery/binding.
- Policy deciding whether password + WebAuthn is mandatory or strong WebAuthn suffices.
- Never treating “passkey enrolled” as proof of a current WebAuthn authentication.

**Never implement WebAuthn cryptographic parsing/verification yourself** when a maintained, audited implementation exists. Mistakes checking origin/challenge/rpId easily cause account takeovers.

## 11. Spring Security 6.5: Without a Built-In MFA Factory, Where Do You Build It?

Three practical strategies:

| Strategy | Pros | Must Control |
| --- | --- | --- |
| MFA at a **trusted IdP**, app accepts verified assertions | Centralizes enrollment/step-up and policy across services | OIDC `acr/amr/auth_time`, issuer/audience, token freshness, RP/session |
| **In-app** MFA with session + custom `AuthorizationManager` | Preserves existing UX/password flows and protects specific endpoints | State machine, proof binding, TOTP service/recovery/replay, session, CSRF |
| Controlled upgrade to Security 7 Servlet | Uses framework tracking/enforcement instead of custom code | Boot 4 compatibility, API changes, method/URL rules, OTT delivery, regression tests |

**Upgrading to 7** is not always the immediate answer: if the app depends on libraries lacking Boot 4 support or uses WebFlux, you may pick an IdP or custom enforcement. Still, **avoid hand-rolling cryptography** when standards-based authenticators/trusted IdPs exist.

### 11.1. Responsibility Boundaries

**Spring Security 6.x already provides:** authentication providers, filters, roles/authorities, `SecurityContext`, `AuthorizationManager`, `SecurityFilterChain`, sessions/CSRF, event hooks, and built-in OTT/WebAuthn in verified versions.

**A 6.x application must build when needed:** “password **and** factor B” rules, stage-1 vs. stage-2 transitions, TOTP verifier/storage, enrollment/revocation/recovery, MFA proof and expiry, challenge/success/failure UI, server-side session invalidation, rate limiting, auditing, concurrency, and API/IdP assurance mapping.

Never rely on a **frontend route guard** while forgetting backend checks: clients can call `POST /admin/...` directly and skip the OTP screen.

## 12. MFA Gate Model for Spring Security 6.5 Servlet

Design flow:

```text
GET /login -> POST /login (CSRF)
      |
      v
DaoAuthenticationProvider verifies password
      |
      v
Session for user, but NO MFA proof
      |
      +--> /mfa/challenge (needs first factor)
      |        |
      |        v
      |    POST /mfa/verify (CSRF, rate limit)
      |        |
      |        v
      |    verify bound TOTP/WebAuthn, atomic replay check
      |        |
      |        v
      |    server stores MFA proof:
      |       stable userId, sessionId, securityVersion,
      |       factorKind, verifiedAt, expiresAt
      |
      v
GET/POST /admin/** -> AuthorizationManager checks
  authenticated AND role AND fresh MFA proof
      |
      +--> false: deny/challenge
      +--> true: endpoint authorization continues
```

**Design note:** in this flow, password login completes Spring Authentication yet **lacks sufficient assurance for routes requiring MFA**. Every sensitive endpoint must use the gate. If the product requires MFA **app-wide**, apply the gate to every endpoint except challenge pages, static assets, and logout; do not let `anyRequest().authenticated()` become a bypass.

### 12.1. Proof Is Server State, Not a Permanently Assigned Role

Illustrative record:

```java
public record MfaProof(
        String userId,
        String sessionId,
        long securityVersion,
        String factorKind,
        java.time.Instant verifiedAt,
        java.time.Instant expiresAt
) implements java.io.Serializable {}
```

This is an **illustrative data model**. Production prefers stable user IDs/tenant IDs rather than relying solely on mutable emails/usernames. With Spring Session/Redis, objects must serialize under the active serializer; session IDs must **rotate** properly via session fixation protections, and proofs must never copy from an old session to a new session outside policy.

Never store raw TOTP secrets, passwords, recovery codes, or passkey private keys in an MFA proof.

### 12.2. Simple Gate Using AuthorizationManager (6.5)

An implementation **suitable as a starting point** on Spring Security 6.5 Servlet:

```java
package demo.mfa;

import java.time.Clock;
import java.time.Instant;
import java.util.function.Supplier;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.RememberMeAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

public final class SessionMfaGate
        implements AuthorizationManager<RequestAuthorizationContext> {

    public static final String PROOF_ATTRIBUTE = "MFA_PROOF";
    private final Clock clock;

    public SessionMfaGate(Clock clock) {
        this.clock = clock;
    }

    // Spring Security 6.5 interface method; 7.x moves to authorize(...).
    @Override
    public AuthorizationDecision check(
            Supplier<Authentication> authentication,
            RequestAuthorizationContext context) {

        Authentication auth = authentication.get();
        if (auth == null || !auth.isAuthenticated()
                || auth instanceof AnonymousAuthenticationToken
                || auth instanceof RememberMeAuthenticationToken) {
            return new AuthorizationDecision(false);
        }

        HttpServletRequest request = context.getRequest();
        HttpSession session = request.getSession(false);
        if (session == null) {
            return new AuthorizationDecision(false);
        }

        Object stored = session.getAttribute(PROOF_ATTRIBUTE);
        if (!(stored instanceof MfaProof proof)) {
            return new AuthorizationDecision(false);
        }

        Instant now = clock.instant();
        boolean good = proof.userId().equals(auth.getName())
                && proof.sessionId().equals(session.getId())
                && !now.isBefore(proof.verifiedAt())
                && now.isBefore(proof.expiresAt())
                && "TOTP".equals(proof.factorKind());

        return new AuthorizationDecision(good);
    }
}
```

This is **`SessionMfaGate.java`**, using `MfaProof` in `demo.mfa` (place the record in `MfaProof.java` in the same package). It is a **gate demo**, **not a complete production implementation**. It assumes `auth.getName()` is a stable ID; if it is actually a mutable username/email, replace it with a stable principal ID. It also **does not yet check `securityVersion` against the source of truth**; production must add an account-state lookup/validated security stamp to revoke old proofs on password reset, account disable, or auth policy updates. Calling `getSession(false)` intentionally **avoids creating a new session** merely to evaluate the gate.

### 12.3. Wiring the Gate into HttpSecurity

```java
// Spring Security 6.5 Servlet, inside @Configuration.
@Bean
SessionMfaGate mfaGate() {
    return new SessionMfaGate(Clock.systemUTC());
}

@Bean
SecurityFilterChain security(HttpSecurity http, SessionMfaGate gate)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/login", "/error", "/assets/**").permitAll()
            .requestMatchers("/mfa/challenge", "/mfa/verify").authenticated()
            .requestMatchers("/admin/**").access(gate)
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .build();
}
```

**Important:** this `gate` currently checks only MFA proof, **not the admin role**. If `/admin/**` is an administrative path, you must **combine** `ROLE_ADMIN` and object-level authorization (for example `AuthorizationManagers.allOf(AuthorityAuthorizationManager.hasRole("ADMIN"), gate)` in 6.5, with matching generic types). Otherwise, any account with a valid MFA proof can reach admin routes: a privilege escalation bug.

In production, separate protected scopes cleanly:

```text
/admin/**            requires ROLE_ADMIN + fresh MFA + tenant permission
/billing/approve/**  requires payment role + fresh MFA + ownership
/profile/**          requires authenticated (non-sensitive)
 /mfa/**             requires first factor, no MFA proof yet
```

These URLs are **illustrative**; also cover method security `@PreAuthorize` and entry points outside the web layer. When the gate returns false, the application must define the response/challenge (browser redirect to `/mfa/challenge` or API returning 403/step-up-required per contract); Spring 6.x **does not automatically route to a missing factor like 7.x MFA** merely because the gate denied access.

### 12.4. Recording Proof at the Right Point

Set the session attribute only after a **server-side service** verifies the TOTP/WebAuthn proof:

```java
// Snippet inside a trusted MFA verification service/controller,
// NOT a complete public endpoint.
if (totpVerifier.verifyAndConsume(userId, suppliedCode)) {
    HttpSession session = request.getSession(false);
    if (session == null) {
        throw new IllegalStateException("No first-factor session");
    }
    session.setAttribute(SessionMfaGate.PROOF_ATTRIBUTE,
            new MfaProof(userId, session.getId(),
                    accountSecurityVersion, "TOTP",
                    clock.instant(),
                    clock.instant().plusSeconds(300)));
}
```

`totpVerifier` is an application service **not defined in the snippet**; it must check the user’s enrolled secret, bounded clock skew, one-time replay, rate limits, account/tenant status, transactions, and auditing. `accountSecurityVersion` comes from a trusted account record and must be checked in the gate as noted. **Never** let the frontend supply `verifiedAt` or `factorKind`.

### 12.5. Logout and Session Fixation

Logout must clear `SecurityContext`, `HttpSession`, and proofs. On password reset, account disable, device loss, binding a new TOTP, or adding a new recovery method, invalidate/revoke proofs and active sessions. When the session ID rotates upon authentication, bind the proof to the **post-rotation session**; never copy proofs from an anonymous session into an authenticated session.

## 13. Parts of TOTP/HOTP You Must Integrate Yourself

To implement standards-compliant password + TOTP, address these items:

| Item | What the App/IdP Must Provide | Never Omit |
| --- | --- | --- |
| Enrollment | Generate random secret via `SecureRandom`, show QR/`otpauth://` to verified user | HTTPS, CSRF, recent login, confirmation code |
| Secret storage | Encrypt at rest/KMS, tenant/user isolation, rotate/revoke, restrict access | Never log or send raw secrets to analytics |
| Verification | RFC 6238 TOTP, HMAC algorithm, digits, period, bounded skew | Constant-time comparison, leading zeros, replay protection |
| Replay | Store last accepted time step/counter **atomically** per user/authenticator | Never accept the same OTP twice |
| Rate limiting | Throttle attempts per user/device/IP/session | Prevent brute-forcing 6-digit codes |
| MFA proof | Issue post-verification and bind to identity/session/time/version | Never trust client-supplied flags |
| Recovery | Single-use, high entropy, hashed at rest; revocation/rotation | Never make recovery a weaker path |
| Device change | Step-up, verify old/new, notify, revoke old secret | Never re-bind on password knowledge alone |
| Auditing | Event codes, actor, factor, decision, IP/device risk | Never log OTPs or secrets |
| Availability | Clock sync, multi-node DB/store, fail closed | Never “skip MFA” when Redis/mail is down |

### 13.1. Do Not Write “TOTP Only Needs Checking 6 Digits”

A 6-digit TOTP has a finite code space; verification must enforce an **attempt budget**, short validity, **replay prevention**, and rate limiting. Allowing ±1 time step helps with clock skew while widening the guessing window. Never compare browser-supplied time.

### 13.2. HOTP vs. TOTP

- **HOTP (RFC 4226):** counter-based; the verifier maintains the counter and resynchronization window.
- **TOTP (RFC 6238):** time-based; the counter derives from current time and step size.
- **OTT (Spring):** server creates a random one-time token and sends it over a channel; does not use a shared authenticator seed automatically.

Though all look like “one-time codes”, their protocols, enrollment, and replay handling differ.

## 14. Runnable Java 17: Computing TOTP per RFC 6238 Test Vectors

This pure-Java example helps distinguish TOTP from Spring OTT. It **only** computes codes for a known test secret and timestamp, and **does not** implement enrollment, an MFA server, a replay ledger, or rate limiting.

Create `TotpRfc6238Demo.java`:

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class TotpRfc6238Demo {

    static String generate(byte[] secret, long unixSeconds, int digits)
            throws Exception {
        if (digits < 6 || digits > 8 || unixSeconds < 0) {
            throw new IllegalArgumentException("invalid TOTP parameters");
        }
        long movingFactor = unixSeconds / 30L;
        byte[] message = ByteBuffer.allocate(8)
                .putLong(movingFactor)
                .array();

        Mac mac = Mac.getInstance("HmacSHA1");
        mac.init(new SecretKeySpec(secret, "HmacSHA1"));
        byte[] digest = mac.doFinal(message);

        int offset = digest[digest.length - 1] & 0x0f;
        int binary = ((digest[offset] & 0x7f) << 24)
                | ((digest[offset + 1] & 0xff) << 16)
                | ((digest[offset + 2] & 0xff) << 8)
                | (digest[offset + 3] & 0xff);

        int divisor = 1;
        for (int i = 0; i < digits; i++) {
            divisor *= 10;
        }
        int otp = binary % divisor;
        return String.format(Locale.ROOT, "%0" + digits + "d", otp);
    }

    public static void main(String[] args) throws Exception {
        // Test secret and two timestamps from RFC 6238 Appendix B.
        byte[] secret = "12345678901234567890"
                .getBytes(StandardCharsets.US_ASCII);

        System.out.println("59: " + generate(secret, 59L, 8));
        System.out.println("1111111109: "
                + generate(secret, 1111111109L, 8));
    }
}
```

Run with JDK 17+:

```bash
javac TotpRfc6238Demo.java
java TotpRfc6238Demo
```

**Exact stdout per RFC 6238 Appendix B (HMAC-SHA1, 8 digits):**

```text
59: 94287082
1111111109: 07081804
```

Production code must separate `verifyAndConsume`: fetch the user’s enrolled secret, compute allowed time steps, compare properly formatted codes preserving leading zeros, **atomically record the last-used step**, rate-limit, and return only a boolean/decision. Never use the sample RFC secret for any real user. For high-assurance requirements, phishing-resistant authenticators like WebAuthn are preferable to TOTP.

## 15. Runnable Java 17: Modeling Multi-Factor Verification by Session/Version/TTL

The standalone program below models an **MFA proof policy** checking:

- **Identity** and **session ID** must match.
- **Security version** has not changed since password reset/revocation.
- Each required factor has a **distinct valid proof** not yet expired.
- Rejects proofs “issued in the future”.
- Expires once the reauthentication window passes.

It uses standard Java 17 with no Spring dependencies. Save `MfaProofPolicyDemo.java`:

```java
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Set;

public class MfaProofPolicyDemo {

    enum Factor { PASSWORD, TOTP, WEBAUTHN }

    record Proof(
            String userId,
            String sessionId,
            long securityVersion,
            Factor factor,
            Instant verifiedAt) {}

    static boolean allowed(
            String userId,
            String sessionId,
            long securityVersion,
            Instant now,
            Duration maxAge,
            Set<Factor> required,
            List<Proof> proofs) {

        if (maxAge.isNegative() || maxAge.isZero()) {
            return false;
        }
        for (Factor factor : required) {
            boolean found = proofs.stream().anyMatch(proof ->
                    proof.userId().equals(userId)
                    && proof.sessionId().equals(sessionId)
                    && proof.securityVersion() == securityVersion
                    && proof.factor() == factor
                    && !proof.verifiedAt().isAfter(now)
                    && now.isBefore(proof.verifiedAt().plus(maxAge)));
            if (!found) {
                return false;
            }
        }
        return true;
    }

    public static void main(String[] args) {
        Instant t0 = Instant.parse("2026-01-01T10:00:00Z");
        Duration ttl = Duration.ofMinutes(10);
        Set<Factor> required = Set.of(Factor.PASSWORD, Factor.TOTP);
        Proof password = new Proof("alice", "S1", 7,
                Factor.PASSWORD, t0);
        Proof totp = new Proof("alice", "S1", 7,
                Factor.TOTP, t0.plusSeconds(60));

        System.out.println("password only: " + allowed(
                "alice", "S1", 7, t0.plusSeconds(90),
                ttl, required, List.of(password)));

        System.out.println("two factors: " + allowed(
                "alice", "S1", 7, t0.plusSeconds(90),
                ttl, required, List.of(password, totp)));

        System.out.println("other session: " + allowed(
                "alice", "S2", 7, t0.plusSeconds(90),
                ttl, required, List.of(password, totp)));

        System.out.println("version changed: " + allowed(
                "alice", "S1", 8, t0.plusSeconds(90),
                ttl, required, List.of(password, totp)));

        System.out.println("expired: " + allowed(
                "alice", "S1", 7, t0.plusSeconds(1200),
                ttl, required, List.of(password, totp)));
    }
}
```

Run:

```bash
javac MfaProofPolicyDemo.java
java MfaProofPolicyDemo
```

**Exact stdout:**

```text
password only: false
two factors: true
other session: false
version changed: false
expired: false
```

This is an **authorization decision** model with no HTTP API, password verifier, or TOTP verifier. In production, proofs must be created **only after real verification**, never accepted from clients, stored in a trusted store, protected against session fixation, and invalidated per lifecycle rules. Using `Set<Factor>` only prevents duplicate **factor types**; authenticator independence and risk still depend on policy.

## 16. Integrating Step-Up MFA with Sensitive Endpoints on 6.x

### 16.1. URLs That Should Require MFA

Example:

| Endpoint | Requirement |
| --- | --- |
| `GET /profile` | Authenticated user |
| `POST /profile/change-email` | Authenticated + fresh MFA + owner |
| `POST /passkeys/register` | Authenticated + recent strong proof |
| `POST /mfa/enroll` | Authenticated + recent reauthentication/step-up per policy |
| `POST /mfa/disable` | Authenticated + MFA or equivalent recovery |
| `POST /admin/transfer` | Admin role + MFA + approval workflow |
| `POST /sessions/revoke-all` | Authenticated + MFA/recent reauth |
| `GET /mfa/challenge` | Password-authenticated yet lacking MFA still allowed in |
| `POST /mfa/verify` | Password-authenticated + CSRF + rate limit; proof issued only on valid code |

If `.requestMatchers("/admin/**").access(gate)` is set yet `@PreAuthorize("hasRole('ADMIN')")` sits on a service called from **another internal endpoint**, that alternative path can bypass the web gate. Define **defense-in-depth** at service/transaction boundaries for sensitive actions and ensure matching interceptors/session contexts.

### 16.2. Browser vs. API

- **Browser session flow:** 302 to `/mfa/challenge` can fit when a factor is missing.
- **REST API/SPA:** return contractual status/codes such as `403 step_up_required` or `401 reauthentication_required` depending on authentication semantics, with safe challenge-initiation metadata; never return an HTML login page in a JSON API.
- **Stateless resource server:** do not open server sessions just to store `MfaProof` when the API policy is Bearer; assurance must be verified from a trusted token/authorization server or a step-up flow issuing a new token.

### 16.3. When a User Has Only Completed Factor One, Block Sensitive Access

A password-authenticated session is valid as a Spring Security `Authentication`, yet the MFA gate must deny sensitive operations until the second proof is issued. If an app applies `anyRequest().authenticated()` to every endpoint, password login alone grants access to everything without ever reaching the OTP page: **that is a policy bug**, not a `ProviderManager` failure.

## 17. Integrating an IdP/OIDC to Reduce Custom Code

A solid option for many systems is delegating MFA to an **Identity Provider** supporting WebAuthn/FIDO, TOTP, recovery, user lifecycle, and auditing, while the Spring Security app uses `oauth2Login` (browser) or `oauth2ResourceServer` (API) with an **assurance policy**.

### 17.1. Do Not Treat OAuth2 Login as Automatic MFA

A successful OIDC login proves the IdP authenticated an identity under the IdP’s policy. If specific assurance is needed, the application may need to request/verify:

- `acr` — Authentication Context Class Reference, **values agreed with the IdP**.
- `amr` — Authentication Methods References, list of methods declared by the IdP (if present).
- `auth_time` — timestamp of user authentication at the IdP, distinct from token `iat`.
- Issuer/audience/nonce/expiry, and `azp` when applicable.
- `max_age` or `prompt=login` in the OIDC request when requiring fresh authentication; verify whether the IdP honors the contract.
- Whether session/token refreshes preserve the required assurance.

**`amr=["pwd","otp"]` is trustworthy only after the token’s signature/issuer/audience are validated and the issuer actually issues these claims under contract.** Never set `amr` on the frontend or assume every IdP uses identical claim strings.

### 17.2. Step-Up via OIDC

```text
RP/Spring application
  -> detects missing/freshness requirement
  -> redirects user to OP/IdP with agreed acr_values/max_age
  -> OP enforces policy, issues new validated assertion
  -> RP validates ID token/claims/auth_time/nonce and account linkage
  -> RP grants sensitive access for bounded window
```

This is a **high-level design**. IdPs support `acr_values`, the `claims` parameter, `prompt`, or proprietary conditional access differently; there is no single Spring API forcing every IdP to perform MFA. Run integration tests against a real IdP or sandbox instead of only mocking an `acr` claim.

### 17.3. Never Mix Trusted IdP Assurance with Local Session Flags

If a user logs out, an account is disabled, or tokens change, a stale local `mfa=true` from an old session must never bypass a new IdP policy. Bind assurance to principal, tenant, session, and a bounded time window; when revoking, handle both RP sessions and IdP grants as supported.

## 18. Resource Server/JWT, Opaque Tokens, and Microservices

For a Spring Resource Server receiving `Authorization: Bearer ...`:

- `BearerTokenAuthenticationFilter` authenticates the access token via a JWT decoder or introspector.
- `JwtAuthenticationConverter` can map claims to authorities, yet **has no idea** whether the user’s browser session passed TOTP on another frontend.
- `FACTOR_BEARER` in Security 7 describes the Bearer mechanism, **not MFA assurance from the IdP**.
- A custom `amr`/`acr` authorization manager must trust only verified issuers/claims and enforce policy per endpoint/action.
- If an API requires recent MFA while the access token was issued prior to step-up, use token exchange/reissuance/claims challenges per AS architecture; changing a local session attribute in the web app does not alter the JWT.

### 18.1. Illustrative JWT Code for Conditional Claim Inspection

```java
// Snippet after JwtDecoder has already verified the JWT;
// this is not a full AuthorizationManager yet.
Jwt jwt = jwtAuthenticationToken.getToken();
List<String> amr = jwt.getClaimAsStringList("amr");
String acr = jwt.getClaimAsString("acr");

boolean reportedStrong = amr != null
        && amr.contains("hwk"); // Example only: mapping defined by issuer contract.
// DO NOT use this boolean as a full policy; verify issuer/audience,
// required acr, auth_time/freshness, audience, and business action.
```

Never hardcode `"hwk"` as a universal guarantee across issuers; claims must follow your IdP’s contract. If a token lacks required claims for an action requiring MFA, **fail closed** rather than treating missing `amr` as “MFA optional” unless policy explicitly permits it.

### 18.2. OAuth Refresh Tokens and MFA Freshness

Refresh tokens can mint new access tokens without the user presenting a fresh factor. **A newly issued access token does not mean MFA just occurred**. For recent step-up, require trusted `auth_time`/`acr` policies or interactive reauthentication. Avoid using the access token’s `iat` to infer “just completed MFA”.

## 19. WebFlux and Reactive: Do Not Copy Servlet Annotations Verbatim

Spring WebFlux uses `ServerHttpSecurity`, `SecurityWebFilterChain`, Reactor Context/`ReactiveSecurityContextHolder`, and `ReactiveAuthenticationManager`.

**Per Spring Security 7 Javadoc for `@EnableMultiFactorAuthentication`, as of those docs the feature does not apply to reactive applications.** Therefore:

- Do not copy Servlet `@EnableMultiFactorAuthentication` and conclude every `SecurityWebFilterChain` automatically enforces multiple factors.
- On WebFlux, build a `ReactiveAuthorizationManager<AuthorizationContext>` that checks proofs/claims safely, or delegate MFA to an IdP and validate assurance.
- Never run blocking JDBC/TOTP repository calls directly on the Netty event loop.
- Reactor Context differs from Servlet ThreadLocal; never use Servlet-style `SecurityContextHolder` as the primary source in a reactive pipeline.
- WebFlux/`WebSession` proofs need multi-node sync, TTLs, logout, and separate replay checks.
- Test with `WebTestClient`/`StepVerifier`; MockMvc is for Servlet.

**Illustrative** DSL example without a proof verifier:

```java
// WebFlux snippet, not a standalone runnable file.
http.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/mfa/**").authenticated()
        .pathMatchers("/admin/**").access(reactiveMfaManager)
        .anyExchange().authenticated());
```

`reactiveMfaManager` must be a reactive implementation bean, never a Servlet `AuthorizationManager<RequestAuthorizationContext>`.

## 20. Account State, Enrollment, Recovery, and Factor Independence

### 20.1. Enrollment Is a Security-Sensitive Operation

MFA enrollment must verify the user owns the account (recent auth/step-up), generate secrets/credentials server-side, require the user to prove possession of the new factor (confirmation code/attestation per policy), commit atomically, and send notifications.

**Never** allow a session holding only a compromised password to add a new TOTP secret and let the attacker satisfy the account owner’s MFA. An unenrolled account needs onboarding/identity proofing with appropriate assurance, not an unverified “skip OTP” fallback.

### 20.2. Disabling/Re-Enrolling

Disabling TOTP/passkeys, changing phone numbers, changing recovery emails, resetting passwords, or modifying roles/account status can all alter assurance. Invalidate:

- Current MFA proofs in the session.
- Related sessions/remember-me cookies per policy.
- Trusted-device remember flags and MFA bypass grants.
- Refresh tokens/access token claims where revocation/reissuance is supported.
- Compromised recovery codes/backup factors.
- Device-bound credential bindings and support workflows.

Preferably store a `securityVersion`/stamp on the account and compare it against proofs on every sensitive operation; increment the version on security events. Ensure cache invalidation/consistency across nodes.

### 20.3. Recovery Codes Must Never Become Unlimited Bypasses

A recovery code must have high entropy, be single-use, be hashed server-side, never be redisplayed after setup, and be invalidated upon use. Recovery may substitute for a factor under defined rules, yet **must never** attach `FACTOR_WEBAUTHN` or `FACTOR_TOTP` after entering a weak email link. Record a distinct `FACTOR_RECOVERY`/assurance level in custom integrations and restrict post-recovery actions.

### 20.4. Missing Second Factor During an Outage

If an SMS gateway, TOTP store, or IdP becomes unreachable, never return `mfaVerified=true` to let users proceed. Maintain a **fail-closed** runbook for sensitive operations, availability options (backup authenticators, proper recovery, audited privileged break-glass), and status notices rather than creating a fail-open authentication bypass.

## 21. Recording Factor Proofs and Session Safety

An MFA proof should contain:

| Field | Purpose |
| --- | --- |
| `accountId`, `tenantId` | Binds accurately to user and organization |
| `sessionId`/device binding | Prevents copying proofs across sessions |
| `factorKind` and `authenticatorId` | Factor/credential verified, preventing counting the same factor twice |
| `verifiedAt`, `expiresAt` | Expiry and recent reauthentication |
| `securityVersion` | Revokes on password/reset/account policy changes |
| `assuranceLevel` or trusted `acr` | Connects assurance to business requirements |
| `challengeId`, one-time consume ID | Prevents replay/double submission |
| `riskContext` and `eventId` | Auditing/correlation without logging secrets |

**Never** store `mfaPassed=true` indefinitely in the users table, roles, or localStorage. Enrolled status is an **account capability**; verified status is **evidence for a specific authentication/session**.

### 21.1. Session Fixation and Rotation

After successful first-factor authentication, Spring Security normally applies session fixation protection; if you write custom login/challenge logic, ensure an attacker-supplied session is never reused. Bind proofs to the **current post-rotation session**, never copying them from an anonymous session into an authenticated session unless policy explicitly verifies safety.

### 21.2. Remember-Me

`RememberMeAuthenticationToken` counts as authenticated yet not fully authenticated. For MFA-sensitive operations, reject remember-me alone; require recent full authentication and factor evidence per policy. `fullyAuthenticated()` **does not mean MFA was completed**; it only distinguishes from anonymous/remember-me.

### 21.3. Logout Does Not Automatically Revoke Every Token

Local logout clears `HttpSession`/proofs, yet does not automatically revoke offline JWTs on resource servers, IdP SSO sessions, OAuth refresh grants, passkeys, or copied remember-me cookies. Design revocation in each store and test validity windows.

## 22. Required Test Cases for Spring Security 7

### 22.1. Authentication Paths and Authorities

When a 7.x app configures password + OTT:

1. Valid password, no OTT yet: holds `FACTOR_PASSWORD` yet **insufficient** authorization for protected routes.
2. Valid OTT, no password (when the mechanism allows standalone login): `FACTOR_OTT` is insufficient when rules require both.
3. Password then OTT: satisfies factor rules; route allows access if roles also match.
4. Password then OTT from **another account**: never merge authorities across users.
5. Expired/replayed OTT: never grants the factor authority.
6. Missing user role despite full MFA: still 403.
7. User logout/new session: factor authorities from the old session cannot be reused.
8. User changes password/revokes factor: proofs/authorities must be invalidated per policy.
9. Clock advances / `validDuration` expires: requires fresh step-up.
10. Custom `AuthenticationProvider` never grants `FACTOR_TOTP` prior to server-side verification.
11. With multiple filter chains, factor rules protect the **right chains and endpoints**.
12. Method security `@PreAuthorize`/service layers enforce equivalent policies as the request layer.

### 22.2. Do Not Use with(user()) to Prove Real MFA

Spring Security Test helpers like `with(user("alice"))` or `@WithMockUser` inject a test Authentication into requests, typically **bypassing login filters and factor verification**. They work for testing role gating, not for proving end-to-end MFA succeeds.

To test 7.x MFA, run the appropriate form-login/OTT/WebAuthn test flows and assert **factor authorities** through the trusted authentication path before calling protected routes. Test 401/302/403 and challenge endpoints, not just HTTP 200. If mocking authorities to unit test a factory, label it clearly as an **authorization unit test**.

### 22.3. What to Verify After Upgrading

For projects moving from Boot 3/Security 6 to Boot 4/Security 7:

- Do built-in filters attach the expected factor authorities to Authentication?
- Does full login/step-up preserve/merge authorities **for the same identity** across factor transitions?
- Are users who enrolled a factor yet have not verified it properly denied?
- Which URL/method rules are covered by `@EnableMultiFactorAuthentication`, and can any custom DSL/`AuthorizationManager` bypass the factory?
- Do WebFlux apps actually use custom/IdP MFA rather than relying on Servlet annotations?
- Do CSRF, session fixation, request caches, and OIDC callbacks remain secure?
- Does session serialization stay backward-compatible during rolling upgrades?
- Do account disabling, recovery, logout, token refresh, and IdP assurance propagation still behave properly?

## 23. Required Test Cases for Custom-Built Spring Security 6.x

| # | Scenario | Expectation |
| --- | --- | --- |
| 1 | Anonymous user calls protected endpoint | Denied, no MFA proof created |
| 2 | Valid password, no TOTP yet | Accesses single-factor routes only; sensitive actions blocked |
| 3 | Wrong password | Must not open OTP flow as an authenticated bypass |
| 4 | User enrolled TOTP yet has not submitted code | Still not MFA-verified |
| 5 | Malformed TOTP / leading-zero issue | Safely rejected |
| 6 | 10 wrong TOTP attempts | Rate-limited/locked out per policy; brute force blocked |
| 7 | Valid TOTP within bounded time window | Proof recorded for exact identity/session/version |
| 8 | Replaying the same TOTP code | Atomic last-use ledger rejects it |
| 9 | Two concurrent requests with same code | One consumption succeeds, one is rejected |
| 10 | Valid MFA proof within TTL | Protected endpoint permits if role/owner matches |
| 11 | Valid proof yet missing `ROLE_ADMIN` | Admin route denied |
| 12 | Proof for session S1, request on session S2 | Denied |
| 13 | Alice’s proof, Bob’s request | Denied |
| 14 | Proof issued in the future | Denied |
| 15 | Expired proof | Denied / triggers step-up |
| 16 | Account `securityVersion` incremented | Old proof rejected |
| 17 | Account disabled/deleted after MFA | Denied, session revoked |
| 18 | Logout then reuse cookie/session | Old proof cannot be used |
| 19 | Remember-me only | Cannot pass as MFA |
| 20 | `POST /mfa/verify` without CSRF | 403, no proof recorded |
| 21 | Anonymous `POST /mfa/verify` | No proof created / does not leak enrollment |
| 22 | Requesting MFA challenge for another account | Cannot use someone else’s challenge/OTP |
| 23 | Password/email/passkey changed | Revokes or requires re-enrollment per policy |
| 24 | Recovery code used twice | Second attempt rejected |
| 25 | Stolen session cookie | Proof/session binding/step-up per threat model |
| 26 | Redis outage or node loses state | Sensitive actions fail closed |
| 27 | Fake client-supplied IdP `acr/amr` | Rejected |
| 28 | Bearer JWT without assurance | Not treated as MFA-complete |
| 29 | Another URL endpoint calling same service | Service-layer gate protects it |
| 30 | Unenrolled user | Assured enrollment/recovery flow, never skipped |
| 31 | Cross-origin CSRF/CORS | No leaked secret/challenge or bypass |
| 32 | 2-node cluster | Consistent one-time counter and proof invalidation |
| 33 | Session fixation attacker-chosen ID | MFA proof never bound to wrong session |
| 34 | Clock skew | Only bounded window accepted, audited |
| 35 | Break-glass | Requires approval/audit/TTL, never default |
| 36 | Version upgrade | Regression tests pass before/after migration under same policy |

**Testing goal:** prove **negative paths**: users with password-only cannot reach critical operations, users with mismatched-session or expired proofs are denied, and factor-service outages never fall back to weaker paths.

## 24. Testing a Spring Security 6 Custom Gate with MockMvc

Suppose `SessionMfaGate` from section 12 is wired into `SecurityFilterChain`. Tests do not need real TOTP generation to test **the gate itself**: you can seed a known `MfaProof` in the test session and use `with(user(...))` as an authorization fixture, while clearly labeling it as **a unit/integration test of the gate**, not OTP verification testing.

**Snippet inside a Spring Boot 3.x MockMvc test**, not a standalone file:

```java
MockHttpSession session = new MockHttpSession();
session.setAttribute(SessionMfaGate.PROOF_ATTRIBUTE,
        new MfaProof("alice", session.getId(), 1L, "TOTP",
                clock.instant(), clock.instant().plusSeconds(300)));

mvc.perform(get("/admin/report")
        .session(session)
        .with(user("alice").roles("ADMIN")))
    .andExpect(status().isOk());
```

This assumes the gate’s `clock` uses an injected test clock, `/admin/report` exists, and principal name `alice` matches the proof. Because `with(user(...))` bypasses actual authentication, **do not claim password+TOTP was tested**. Add negative tests: missing proof, expired, wrong session, wrong user, version changed, and missing admin role. When testing the gate inside the app security config, ensure the role check **coexists**.

### 24.1. E2E Tests Prove Real MFA

The E2E layer should submit a **real** password/CSRF form, capture the first-factor session, submit TOTP/WebAuthn via the real endpoint, and then invoke sensitive actions. Never use `@WithMockUser` to declare an end-to-end flow complete. When testing shared-store code, run at least two app instances to catch replay races.

## 25. Diagnosing Common Failures by Symptom

### “Cannot find `@EnableMultiFactorAuthentication` in the IDE”

Check the resolved Spring Security version. This API starts in **7.0**. On Boot 3/Security 6.5 use a custom gate/IdP or upgrade the major stack; never mix 7.x config JARs into 6.x core.

### “I enabled `oneTimeTokenLogin()` on 6.5, yet users still reach admin with password alone”

That is expected behavior if authorization only requires `authenticated()`. OTT and password are **two authentication mechanisms**, not an automatic AND condition. Add a dedicated MFA rule; avoid adding fake factor codes to `UserDetails.getAuthorities()`.

### “Spring 7 password login redirects to OTP, yet no link arrives”

Check the OTT **generation success handler** and email/SMS/transport. The framework does not know your delivery channel automatically. Verify privacy/single-use storage/rate limits, and avoid logging tokens in production debugging.

### “Email magic link codes are called TOTP”

Incorrect terminology. OTT is server-generated; TOTP is computed by a client app from an enrolled shared secret/time. Do not apply TOTP counter/replay assumptions to OTT as if formats were identical; both need single-use enforcement via different mechanisms.

### “The user already has a passkey, why do they still need a password?”

A global `PASSWORD+WEBAUTHN` policy may be active, whereas the design intends sufficient WebAuthn assurance **or** password+TOTP. Define allowed combinations/conditional MFA in 7.x and enforce UV/user verification properly. Do not drop passwords carelessly if a passkey type only proves possession below your target assurance level.

### “Another user received the previous user’s factor authority”

Risk of session context/authority merging across principals during step-up. Check stable user IDs, session binding, authentication replacement/merging, and test switching accounts in the same browser. **Never** blindly union authorities from an older Authentication onto another user.

### “The same valid TOTP code is accepted twice”

You computed the code without **atomic replay tracking**. Store the last accepted timestep/challenge ID in a consistent store using conditional updates/transactions; test across multiple nodes and concurrent requests.

### “Passed TOTP then logged out, yet cookies still grant access”

Sessions, remember-me tokens, or refresh tokens were not revoked, or server proofs were not cleared. Separate authentication sessions, MFA proofs, remember-me cookies, and OAuth grants. Local logout does not revoke credentials at an external IdP/AS.

### “Annotated MFA on a WebFlux app, yet APIs still let callers in”

Servlet 7.x MFA annotations must not be assumed to apply to reactive security. Use a reactive gate/IdP assurance, test with `WebTestClient`, and check Reactor Context. Never copy Servlet `HttpSecurity`/`SecurityContextHolder` ThreadLocal patterns into WebFlux.

### “JWT has `amr=mfa`, yet API still returns 403”

The authorization manager may expect a different `acr`, the token may come from an untrusted issuer, lack `auth_time`/freshness, lack the right audience, or the trusted converter may not map assurance. **Never** fix by removing signature/audience checks.

### “MFA proofs in Redis were lost on restart and admins are locked out”

When policy protects sensitive operations, failing closed is right, while UX/availability needs proper recovery/re-step-up. Design Redis persistence, replication, backup factors, and incident runbooks; never mark verified during store outages.

## 26. Plan for Migrating from Spring Security 6.5 to 7.x

1. **Inventory** security features: login mechanisms, sessions, remember-me, custom OTT/WebAuthn/TOTP, resource servers, OIDC, multi-chain, CSRF, authz, and reactive modules.
2. **Pin a compatible Spring Boot/Spring Security BOM** per your target release; verify resolved dependencies and the migration guide.
3. **Write tests first:** first-factor-only denied on sensitive endpoints, full MFA succeeds, wrong-account/session rejected, TTL, replay, recovery, disabled accounts.
4. **Decide factor semantics:** Password+OTT? WebAuthn only? Custom Password+TOTP? External IdP assurance? Never confuse OTT with TOTP.
5. **Enable 7.x MFA** in a Servlet test environment; use the annotation for global rules or the MFA factory for selective rules, avoiding conflicting policy sources.
6. **Gradually remove old custom gates** only after proving built-in factor authorities protect every equivalent path, including `@PreAuthorize` and APIs.
7. **Keep necessary custom parts:** TOTP verifier, enrollment, delivery, recovery, auditing, risk policies, lifecycle, IdP step-up, and token assurance.
8. **Test session migration/rolling deploys:** Spring Security 7 changes Authentication/factor authority types; sessions from older versions lack new factors and must reauthenticate rather than self-elevating assurance.
9. **Handle WebFlux separately:** never assume Servlet annotations protect reactive routes.
10. **Roll out via canary**, measuring login drop-off, challenge success, factor enrollment, replay events, 401/403/redirect loops, session invalidation, and support cases.
11. **Never inject authorities into principals** just to make tests pass without a verified factor.
12. **Controlled rollback:** if rolling back to 6.5, the custom MFA gate/IdP enforcement must still work; never downgrade to password-only without an explicit security decision.

### 26.1. API/DSL Changes to Watch For

Spring Security 7 removes or replaces several legacy APIs: for example `AuthorizationManager#check` moves to `authorize`, legacy `HttpSecurity.and()` is gone from the lambda DSL, and authentication builders provide new mechanisms to merge authorities/factor proofs. Never try compiling 6.5 custom gate source code verbatim on 7 without adapting per the migration guide; verify security semantics with tests, not just a “green build”.

## 27. Solution Selection Decision Table

| Current State and Requirement | Preferred Direction | Why |
| --- | --- | --- |
| Boot 4/Security 7 Servlet app requiring password+OTT | Built-in MFA 7 + OTT delivery + policy tests | Saves writing custom factor-tracking core |
| Security 7 Servlet app requiring WebAuthn step-up | Built-in WebAuthn/factor policy with proper UV enforcement | Factor authorities and conditional rules built in |
| Boot 3/Security 6.5 app needing password + authenticator TOTP | Custom gate/IdP + TOTP library/service | No `@EnableMultiFactorAuthentication`; OTT is not TOTP |
| Boot 3/Security 6.5 app with existing strong IdP MFA | OIDC login + verified assurance mapping | Avoids duplicating enrollment/recovery |
| WebFlux app currently using JWT/OIDC | Reactive authorization or IdP step-up | Do not assume Servlet MFA annotations work |
| Multi-microservice API needing recent MFA | Token assurance contract at AS/RS | Do not rely on one service’s browser session |
| Compliance prioritizing phishing resistance | WebAuthn/FIDO2 with UV/assurance and proper recovery | OTP/email is vulnerable to phishing/compromise |
| No safe account recovery capability yet | Design recovery before broad rollout | MFA easily bypassed via helpdesk/email fallbacks |
| Need immediate multi-node disable/revocation | Shared session/grant revocation + version checks | Old authenticated tokens could remain valid |

**Selection principle:** library support reduces the **orchestration** you write yourself, while assurance, lifecycle, and deployment-specific risks still require your product’s policies, data, and tests.

## 28. Version-Aware MFA Implementation Handoff Checklist

1. Verified exact Spring Boot/Security **resolved versions** and separated Servlet from WebFlux.
2. Documented MFA explicitly as **AND/anyOf combinations**, not merely “enabling multiple login mechanisms”.
3. Selected independent factors per threat model without treating email magic links automatically as NIST AAL2.
4. On Security 7, scoped `@EnableMultiFactorAuthentication` or MFA factories accurately so no custom `AuthorizationManager` bypasses them.
5. On Security 6.5, enforced **server-side authorization gates** or trusted IdP assurance rather than frontend guards.
6. Defined mechanisms per factor: enrollment, verification, TTL, replay storage, rate limits, and UX.
7. Verified RFC 6238 TOTP against test vectors with **atomic consumption** and zero secret logging.
8. Verified WebAuthn RP ID/origin/challenge/UV, public-key bindings, and trusted credential repositories.
9. Verified OTT delivery handler/channel, single-use consumption, anti-enumeration/resend abuse; distinguished OTT from TOTP.
10. Bound session/authentication proofs to account, tenant, session, security version, factor, and `verifiedAt`/expiry.
11. Defined revocation/step-up policies for account disable, password reset, passkey removal, lost device, and logout.
12. Enforced both **role/scope/ownership** and MFA on sensitive endpoints, including alternative method/service entry points.
13. Bearer/OIDC APIs trust assurance **only from validated tokens** per issuer contract, never inferring from `FACTOR_BEARER`.
14. WebFlux has separate reactive implementations and `WebTestClient` tests.
15. Negative tests cover password-only, wrong factor, replay, expired proof, cross-session, wrong user, and cache/node outages.
16. CSRF, session fixation, CORS, `Secure`/`HttpOnly`/`SameSite`, and TLS transport remain enforced.
17. Recovery codes and helpdesk workflows create no path weaker than primary MFA.
18. Rollout emits logs/metrics by factor/decision while **never** logging raw OTPs, passwords, tokens, or private keys.
19. Prepared migration/rollback plans for major Spring Security upgrades.
20. Documented step-up triggers and recovery procedures for frontend, support, security operations, and users.

**Conclusion:** Spring Security **6.5** offers several useful **authentication mechanisms**, yet **lacks 7.x’s first-class MFA factor policy**. Spring Security **7.0+** adds `FactorGrantedAuthority`, `@EnableMultiFactorAuthentication`, and factor-aware authorization config for Servlet. Regardless of version, **MFA is trustworthy only when factors are genuinely verified, proofs are bounded by session/user/time, sensitive resources enforce the gate, and recovery does not weaken the model**.

## 29. Official References and Standards

- [Spring Security 7 — Multi-Factor Authentication (Servlet)](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/mfa.html): `FactorGrantedAuthority`, annotation, selective rules, dynamic conditions, validity, and factor combinations.
- [Spring Security 7 — What's New](https://docs.spring.io/spring-security/reference/7.0/whats-new.html): first-class MFA in 7.0, authentication/authorization API changes.
- [Spring Security 7 — FactorGrantedAuthority Javadoc](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/core/authority/FactorGrantedAuthority.html): `PASSWORD_AUTHORITY`, `OTT_AUTHORITY`, `WEBAUTHN_AUTHORITY`, `issuedAt`, API since 7.0.
- [Spring Security 7 — EnableMultiFactorAuthentication Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/authorization/EnableMultiFactorAuthentication.html): annotation and note on reactive scope.
- [Spring Security 6.5 — One-Time Token Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/onetimetoken.html): how OTT differs from TOTP/HOTP; delivery handler, service, JDBC/token lifecycle.
- [Spring Security 6.5 — Passkeys](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passkeys.html): `webAuthn()`, dependencies, repositories, RP ID/origins.
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): authentication providers, filters, SecurityContext, authorities.
- [Spring Security — Servlet Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): `AuthorizationManager` and access control.
- [Spring Security — Reactive Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): reactive rules and `ServerHttpSecurity`.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): session persistence, fixation, and security context.
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): authorization-code login and IdP integration.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT validation/claims/authorization.
- [Spring Blog — Multi-Factor Authentication in Spring Security 7](https://spring.io/blog/2025/10/21/multi-factor-authentication-in-spring-security-7/): progressive authorities and factor policy design.
- [RFC 4226 — HOTP](https://www.rfc-editor.org/rfc/rfc4226): HMAC-based One-Time Password.
- [RFC 6238 — TOTP](https://www.rfc-editor.org/rfc/rfc6238): Time-Based OTP and Appendix B test vectors.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): `acr`, `amr`, `auth_time`, `max_age`, claims validation.
- [NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b.html): AAL2, replay resistance, phishing resistance, and disallowing email as an out-of-band authenticator.
- [OWASP Multi-Factor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html): enrollment, recovery, risk, bypass protection.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): reauthentication, throttling, and generic error messages.

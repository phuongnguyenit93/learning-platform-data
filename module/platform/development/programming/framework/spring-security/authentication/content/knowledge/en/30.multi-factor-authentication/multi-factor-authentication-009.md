# Controlling All Login Paths, Remember-Me, and Account Recovery in MFA

## 1. Core Problem: Even Strong MFA Is Useless If a Bypass Path Exists

An application may require **password + OTP code** on its `/login` UI, yet an attacker can still take over an account if they can successfully authenticate through another path using only a password, magic link, remember-me cookie, legacy API token, or weak account recovery feature.

**Design principle:** Multi-Factor Authentication (**MFA**) policies must be enforced at **resource authorization boundaries** and across all **login/recovery** flows, not merely inside a login page controller. Every way of creating an `Authentication`, restoring a session, or replacing an authentication factor must be governed by the same assurance policy.

This lesson helps you:

1. Inventory **every way into an account**: form login, SSO, passkey, OTT, API, remember-me, recovery, help desk, trusted devices, and legacy endpoints.
2. Distinguish **authenticated**, **which factors were authenticated**, **whether factors are still fresh**, and **what actions are permitted**.
3. Understand `RememberMeAuthenticationToken`, remember-me cookie/DB mechanisms, and why automatic re-login **does not** prove MFA.
4. Use **Spring Security 7.x** built-in MFA features such as `FactorGrantedAuthority` and `@EnableMultiFactorAuthentication`, and understand the limits of **6.x** configurations.
5. Design recovery codes, password resets, authenticator replacements, and manual support so they do not create an MFA bypass.
6. Test **bypass cases** (negative tests) instead of only testing successful logins on the main UI.

**Scope:** Java 17+ applications on Spring Security Servlet/Spring MVC. The `@EnableMultiFactorAuthentication` API belongs to **Spring Security 7.0+**; do not apply it verbatim to Spring Security 6.5. SSO flows can delegate MFA to an IdP, yet the application must verify **trusted assurance evidence** per its IdP contract.

## 2. Distinguish Four Concepts Before Writing Code

| Concept | Question to Answer | Examples |
| --- | --- | --- |
| **Authentication** | Which principal did the request come from and via which mechanism? | Verified `Authentication` with username `linh` |
| **Authentication factor** | Which independent factors has the user proven? | Password + TOTP; WebAuthn with appropriate user verification |
| **Authentication assurance / freshness** | Is the evidence strong enough and fresh enough for this action? | Completed second factor within the last 10 minutes |
| **Authorization** | Does the principal have permission to perform this business operation? | Has `ROLE_ADMIN` and satisfies applicable MFA |

For instance, a user holding `ROLE_ADMIN` who logged in only via a remember-me cookie may still **lack MFA evidence**. Conversely, completing MFA does not automatically grant `ROLE_ADMIN`.

The concept of a **factor** under organizational policy requires appropriately independent evidence, typically from *something you know*, *something you have*, and *something you are*. Two different passwords do not automatically form MFA. Two OTPs sent to the same compromised mailbox do not automatically create two independent factors either.

**MFA enforcement** should happen where the application decides whether to allow resource access, establish a stronger session, or execute a sensitive transaction. Merely adding an OTP form while `anyRequest().authenticated()` accepts every kind of `Authentication` can leave bypasses wide open.

## 3. Think in Terms of “Account Entry Paths” Instead of “The Login Page”

An account usually has many doors:

```text
                            +-----------------+
   Password form ---------->|                 |
   OTP / OTT -------------->|                 |
   SAML / OIDC SSO -------->| Authentication  |----> Authentication
   Passkey/WebAuthn ------->| mechanisms      |       + factor evidence
   Remember-me cookie ----->|                 |               |
   Legacy Basic ----------->|                 |               v
   JWT / API token -------->|                 |        Centralized policy
   Recovery code ---------->|                 |          + freshness
   Reset-password flow ---->|                 |               |
   Support/admin flow ----->|                 |               v
                            +-----------------+        Resource / operation
                                                               |
                                                  allow / step-up / deny
```

For each path, ask yourself: can it **create a session** or `Authentication` without passing through MFA requirements? Can it **change email/phone/factors** and make subsequent login easier? Can it issue an **access token** for the same API without MFA evidence?

### Review Matrix (Minimum Set)

| Entry Path | What It Establishes | Risk If Uncontrolled |
| --- | --- | --- |
| Username/password via `/login` | Knowledge of the account password | Full login before any second factor is checked |
| TOTP/HOTP/OTT | Possession of code/credential per mechanism | Code entered in another flow without binding to right account/session or blocking replay |
| Passkey/WebAuthn | Possession of credential key and verifier-checked flags | `UV=0` treated as full user verification; skipping challenge/origin checks |
| OIDC/OAuth2 Login | IdP authenticates per trusted policy | App skips checking `acr`/`amr`, timestamps, and issuer before granting high privileges |
| SAML SSO | Assertion signed by IdP and verified by SP | Assuming a signed assertion always implies MFA; skipping AuthnContext/assurance contract checks |
| Remember-me | Browser holds a long-lived login cookie | Cookie silently grants access to change password or disable MFA |
| API Bearer/JWT | Verified token with issuer/audience/scope | Token issued via password-only path still accesses endpoints requiring MFA |
| Basic/legacy endpoint | Legacy credentials present | Bypasses MFA page via API, mobile app, or alternate host |
| Recovery code | Has an issued recovery credential | Recovery code acts as a permanent password or is not single-use |
| Password reset via email | Controls reset channel per workflow | Reset automatically creates an MFA-complete session |
| Help desk / impersonation | Support staff has operational authority | “Temporary MFA disable” without caller verification or auditing |

You do not need to **ban every other mechanism**: machine-to-machine APIs can use OAuth 2.0 client credentials unrelated to human users, under a dedicated policy. What is forbidden is letting a weaker path **inherit the privileges of an MFA-completed user session** without matching evidence.

## 4. Policy Architecture: Authentication Is an Event; Authorization Is a Decision

States can be modeled at the business level as follows:

```text
ANONYMOUS
   |
   +-- valid password -------> PRIMARY_VERIFIED
   |                                |
   |                                +-- valid second factor ---> MFA_VERIFIED
   |
   +-- remember-me cookie ----> REMEMBERED
   |                                |
   |                                +-- re-auth + factor ---> MFA_VERIFIED
   |
   +-- valid passkey --------> PASSKEY_VERIFIED
   |                                |
   |                                +-- assurance meets policy? ---> MFA-equivalent access
   |
   +-- recovery code --------> RECOVERY_LIMITED
                                    |
                                    +-- extra checks / enroll new factor
                                              |
                                              v
                                        REAUTH_REQUIRED
```

This is a **business model**, not a default Spring Security enum.

Key points:

- `PRIMARY_VERIFIED` is evidence of only **one step**; it does not necessarily grant access to areas requiring MFA.
- `REMEMBERED` only means the browser was recognized via cookie; not that a password or OTP was just used.
- `RECOVERY_LIMITED` should allow only controlled recovery actions, never full account privileges.
- `MFA_VERIFIED` must rest on evidence created by the trusted framework/server/IdP; never merely an `mfa=true` field in an HTTP request.
- Assurance can **expire** for sensitive actions even while the session stays alive.
- With user-verifying passkeys, assurance evaluation must account for verification policy, credential properties, and attestation (if needed), rather than rigidly hardcoding “password + passkey” in every architecture.

For protected endpoints, combine both **role/permission** and **factor policy**. For example, `/admin/users` may require `ROLE_ADMIN` plus two factors; `/account/disable-mfa` may additionally require very recent re-authentication and risk checks.

## 5. Spring Security 7.x: `FactorGrantedAuthority` and Built-In MFA

Starting in **Spring Security 7.0**, the framework provides `org.springframework.security.core.authority.FactorGrantedAuthority`. When the corresponding authentication mechanism completes, Spring Security can add a factor authority to `Authentication`.

Examples of constants in the 7.x API:

| Constant | Authority String | Evidence It Represents |
| --- | --- | --- |
| `FactorGrantedAuthority.PASSWORD_AUTHORITY` | `FACTOR_PASSWORD` | Password authentication |
| `FactorGrantedAuthority.OTT_AUTHORITY` | `FACTOR_OTT` | One-Time Token Login |
| `FactorGrantedAuthority.WEBAUTHN_AUTHORITY` | `FACTOR_WEBAUTHN` | WebAuthn authentication |
| `FactorGrantedAuthority.BEARER_AUTHORITY` | `FACTOR_BEARER` | Bearer token authentication |
| `FactorGrantedAuthority.AUTHORIZATION_CODE_AUTHORITY` | `FACTOR_AUTHORIZATION_CODE` | OAuth2 Authorization Code Login |
| `FactorGrantedAuthority.X509_AUTHORITY` | `FACTOR_X509` | X.509 authentication |

**Important:** the markers above record **which mechanism authenticated**, without proving by themselves that they are **independent factors** under your threat model. `FACTOR_BEARER` does not indicate whether the token was issued after MFA; `FACTOR_AUTHORIZATION_CODE` does not mean the IdP used an OTP. A `ROLE_ADMIN` loaded from the DB also does not manufacture `FACTOR_OTT`.

`FactorGrantedAuthority` has `getIssuedAt()`; policies can bound factor freshness per resource. Having an old marker from long ago is not necessarily enough for an action requiring “just verified” step-up.

### Example: Requiring Password + OTT on Protected Routes

The sample below is specifically for Spring Security **7.x** and Servlet; Spring Security 6.x lacks this annotation/class. Place it in a compatible Spring Boot **4.x** application with `spring-boot-starter-web` and `spring-boot-starter-security`.

`src/main/java/example/mfa/MfaSecurityConfig.java`:

```java
package example.mfa;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.authorization.EnableMultiFactorAuthentication;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.authority.FactorGrantedAuthority;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableMultiFactorAuthentication(authorities = {
    FactorGrantedAuthority.PASSWORD_AUTHORITY,
    FactorGrantedAuthority.OTT_AUTHORITY
})
public class MfaSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(withDefaults())
            .oneTimeTokenLogin(withDefaults());

        return http.build();
    }
}
```

**Analysis:**

1. `@EnableMultiFactorAuthentication(...)` adds requirements for `FACTOR_PASSWORD` **and** `FACTOR_OTT` to authorization rules built through Spring Security 7's built-in factory mechanism.
2. `/admin/**` requires **both** the factors **and** `ROLE_ADMIN`; it cannot be passed with the role alone.
3. Resources requiring authentication must satisfy the declared factors. The framework includes flows guiding the user to perform any missing factor.
4. `formLogin(...)` together with `oneTimeTokenLogin(...)` enable **two methods**. Declaring the requirement without providing a second authentication step prevents users from completing login.
5. This configuration **does not yet implement OTT delivery**: to run for real, you need a `UserDetailsService`, an appropriate `OneTimeTokenService`, a `OneTimeTokenGenerationSuccessHandler` sending tokens to a verified channel, CSRF/session protections, account policies, and a real SMTP/SMS server. Never print tokens to logs/responses in production.
6. Endpoints configured with `permitAll` or other mechanisms may behave differently; explicitly test login/recovery paths and **do not** assume one annotation protects every custom URL or external service.
7. If using `@EnableMethodSecurity`, verify how factor requirements apply to method authorization rules; ensure custom `AuthorizationManager`s and filter chains are tested as well.

**Do not do the following:** assign `new SimpleGrantedAuthority("FACTOR_OTT")` to every user in the database. A factor authority must originate from a **genuinely verified authentication event**, never turned into a “permanent role” at account creation.

### Checking Versions via Dependency Tree

With Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

The goal is ensuring `spring-security-*` modules share the same major version. Spring Security 7 code cannot be “fixed by changing imports” to run on Spring Security 6.5 because `@EnableMultiFactorAuthentication` and `FactorGrantedAuthority` do not exist in that line.

## 6. Choosing Global MFA vs. Risk-Based Selective MFA?

There are two models:

**A. Required for all resources needing login.** This is straightforward: users cannot enter protected areas if missing a factor. Suitable for internal apps with a uniform policy. However, ensure login/challenge/recovery endpoints operate properly so users can supply missing factors.

**B. Required for a subset of resources or users.** For instance, reading internal news only needs basic authentication, whereas changing email or creating an API key requires a fresh factor within a short window. This is the **step-up** model.

Spring Security 7.x provides `AuthorizationManagerFactories.multiFactor()` to build an `AuthorizationManagerFactory` requiring one or more factors; it can be applied selectively:

```java
// Snippet inside a Spring Security 7.x SecurityFilterChain bean.
var mfa = AuthorizationManagerFactories.multiFactor()
    .requireFactors(
        FactorGrantedAuthority.PASSWORD_AUTHORITY,
        FactorGrantedAuthority.OTT_AUTHORITY
    )
    .build();

http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/account/security/**")
        .access(mfa.authenticated())
    .requestMatchers("/admin/**")
        .access(mfa.hasRole("ADMIN"))
    .anyRequest().authenticated()
);
```

Imports for the snippet:

```java
import org.springframework.security.authorization.AuthorizationManagerFactories;
import org.springframework.security.core.authority.FactorGrantedAuthority;
```

This is a **snippet inserted into a configuration class**, not a standalone Java file. In **7.x**, `AuthorizationManagerFactories` belongs to the authorization manager package; match exact packages/Javadoc for your project's version when using it in a real build. You must also add `.formLogin(...)` and `.oneTimeTokenLogin(...)` when requiring those two factors. With multiple `SecurityFilterChain`s, apply the requirement on the **exact chain** protecting those resources; another chain having `anyRequest().authenticated()` that matches a similar route can weaken the policy.

**Note when using selective policy:** `anyRequest().authenticated()` **does not** inherit MFA requirements from a local factory created without publishing it as a bean. That is intentional design, not a framework bug. A new business route could accidentally land in “low assurance”; hence a route-classification checklist and mandatory tests are essential.

### More Complex Requirements

You may need **either of two factor sets**: a user-verifying WebAuthn **or** password + OTT. Spring Security 7.x provides `AllRequiredFactorsAuthorizationManager.anyOf(...)` to model combinations; avoid forcing both `FACTOR_PASSWORD` and `FACTOR_OTT` onto every passkey session if your policy treats a user-verifying passkey as meeting the target assurance level.

For “verified within 10 minutes”, Spring Security 7 provides factor-authority duration checks in authorization managers; never infer freshness from session creation time or remember-me cookie timestamps. Freshness policies must rely on **trusted factor verification events recorded by the system**.

## 7. Spring Security 6.x: Do Not Confuse `fullyAuthenticated()` with MFA

In Spring Security 6.x, `fullyAuthenticated()` distinguishes an `Authentication` **coming from remember-me** from non-remember-me authentications. It **does not prove two factors**.

Conceptual table:

| Request Type | `authenticated()` | `fullyAuthenticated()` | MFA Verified? |
| --- | --- | --- | --- |
| Anonymous | No | No | No |
| Accepted remember-me cookie | Yes | **No** | No |
| Valid username/password | Yes | Yes | Not necessarily — usually just one factor |
| Valid OTP-only login | Yes | Yes depending on implementation | Not necessarily — may be just one factor |
| MFA-authenticated session | Yes | Yes | Only if MFA evidence is valid and properly preserved |
| Valid Bearer JWT | Yes | Usually yes | Cannot be inferred from these two methods alone |

In 6.x applications, you can **partially restrict** remember-me by requiring `fullyAuthenticated()` on sensitive pages, but achieving real MFA still requires an enforcement layer storing and verifying **server-established factor state** (or delegating MFA to an IdP with verified assurance).

### 6.x Example: Blocking Remember-Me on Sensitive Operations

File `src/main/java/example/mfa/RememberMeBoundaryConfig.java`, used in a Spring Boot 3.x app with a real `UserDetailsService` and `PasswordEncoder`:

```java
package example.mfa;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class RememberMeBoundaryConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            UserDetailsService userDetailsService,
            @Value("${app.remember-me.key}") String rememberMeKey)
            throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/account/security/**").fullyAuthenticated()
                .requestMatchers("/admin/**").fullyAuthenticated()
                .anyRequest().authenticated()
            )
            .formLogin(withDefaults())
            .rememberMe(remember -> remember
                .key(rememberMeKey)
                .userDetailsService(userDetailsService));

        return http.build();
    }
}
```

`application.yml` can read the key from a secret manager/environment:

```yaml
app:
  remember-me:
    key: ${REMEMBER_ME_SIGNING_KEY}
```

For hash-token remember-me, this key is a secret that **must be sufficiently strong**, managed like a server-side credential; never hardcode it into Git. Applications needing per-device revocation should evaluate a persistent token repository rather than hash-based tokens alone. Remember-me should be opt-in by the user, never enabled by default on shared devices.

**Mandatory understanding:** `fullyAuthenticated()` in this example only forces the user out of the remember-me state to authenticate interactively. It **does not check OTP, TOTP, passkey, or any second factor**. A password-only form login still counts as fully authenticated. Never use this example to claim “MFA is implemented”.

When upgrading to 7.x, prefer the built-in factor authorities and authorization managers; if staying on 6.x long-term, use an external MFA IdP with a verified `acr`/`amr` contract or a thoroughly tested custom `AuthorizationManager`, rather than checking only `isAuthenticated()`.

## 8. Remember-Me: It Is an Independent Login Path

`RememberMeAuthenticationFilter` restores an `Authentication` from a cookie when `SecurityContext` has none. Spring Security offers two main implementations:

1. **`TokenBasedRememberMeServices` (hash-based):** the cookie holds username, expiry, and an HMAC/signature tied to the `UserDetails` password and a server key. No separate DB token record is needed in the default model. **A stolen cookie can be replayed** until expiration or until related components change; revoking individual devices is less convenient than with persistent tokens.
2. **`PersistentTokenBasedRememberMeServices`:** the cookie is matched against a record in `PersistentTokenRepository`, with a series-and-token rotation mechanism supported by the framework. Can be stored with `JdbcTokenRepositoryImpl`; design a dedicated DB table if device lists, selective revocation, and auditing policies are required.

**Both require `UserDetailsService`.** If the app only has an LDAP or SAML provider without a corresponding bean, do not assume the remember-me DSL works automatically.

Illustrative flow:

```text
User checked "Remember me" on an allowed login
     |
     v
Server issues remember-me cookie, with expiry/policy
     |
     v
Session expires but browser retains cookie
     |
     v
RememberMeAuthenticationFilter reads cookie
     |
     v
Creates RememberMeAuthenticationToken (when valid)
     |
     v
Authentication authenticated = true
     |
     +--> Low-risk API/view may accept if policy allows
     |
     `--> Change email, change password, register passkey, admin management?
               |
               v
          Require interactive auth + fresh MFA/step-up
```

### Why Can Remember-Me Become an MFA Bypass?

Suppose an app checks OTP only inside the login form:

1. Linh logs in with password + OTP and checks remember-me.
2. A week later, the browser auto-logs in via the cookie alone.
3. The `/account/disable-mfa` request checks only `.authenticated()`.
4. The app immediately allows disabling MFA, **with no fresh factor**.

Even with a valid cookie, step 3 is an **authorization/step-up policy** vulnerability. `isAuthenticated()` is not proof that MFA was just verified.

### Recommended Remember-Me Policy

- Allow remembering a **device/browser** only with explicit consent and bounded duration; narrow automatic privileges.
- Never issue remember-me cookies inside a **recovery-limited** flow or weak login not eligible for cookie issuance.
- Never treat “completed MFA the first time on this device” as **permanent** factor proof.
- For changing email, changing MFA, viewing API keys, internal password resets, transfers, or admin privileges: require step-up/fresh factors.
- Set `Secure`, `HttpOnly`, and appropriate `SameSite` on cookies; enforce HTTPS, session fixation protection, CSRF protection, and proper logout.
- When password/factor/email/recovery changes, enforce a policy to **revoke remember-me tokens and sessions**. With persistent tokens you can delete DB records; with hash tokens assess password/key rotation effects.
- Audit remember-me issuance, auto-login, revocation, and anomalous token reuse detection; **never log cookies**.

**Make no absolute promises:** logging out on one device or deleting the cookie does not necessarily revoke tokens copied elsewhere. Server-side revocation is required if your risk model demands it.

## 9. “Trusted Device” and “Remember This Browser” Differ from MFA

Some systems offer “don't ask for OTP on this browser for 30 days”. This usually works via a **device trust cookie** or server-side record. It is a **prompt-reduction policy** after strong authentication, not a new factor.

Define clearly:

- Is the cookie a bounded device/session hint or an auto-login bearer credential?
- Did the user confirm saving on a **personal device**? Can it be declined on shared devices?
- Are there TTL, server-side revocation, device ID, rotation, and risk conditions?
- Is device trust blocked on high-risk endpoints or after anomalous events?
- Does trust terminate on password reset, factor reset, “log out all sessions”, or lost-device reports?
- If another browser copies the cookie, is it treated as a trusted device? If yes, the mechanism is purely **cookie-based**, not proving independent hardware.

Avoid setting `mfaEnabled=false` on the account after the user clicks “Remember this device”. MFA remains configured; only **the prompt condition** changes for a specific time/scope.

## 10. Account Recovery Is Its Own Authentication Mechanism

Recovery is **not** an “authentication bypass” exception. When losing a phone, passkey, or email access, users still need a way to recover their account; if this workflow is weaker than regular login, attackers will target recovery instead of guessing OTPs.

A recovery flow should enforce a **restricted state**:

```text
Recovery requested
        |
        v
Throttling + generic response (no account enumeration)
        |
        v
Verify approved recovery evidence
        |
        v
RECOVERY_VERIFIED (with TTL, dedicated purpose)
        |
        v
Allow adding/recovering new factor per policy
        |
        v
Notify registered channel, audit, handle risk
        |
        v
Invalidate/revoke old sessions & tokens appropriately
        |
        v
Require full login/reauth with new factor
```

### Single-Use Recovery Codes

During MFA enrollment, the server can issue **a set of random recovery codes** with sufficient entropy, e.g., 8–12 codes. Users are advised to store them safely outside the protected account.

Requirements:

- Each code must be **generated by a CSPRNG**, independent of the password/TOTP secret.
- Store a **secure hash/verifier** on the server; never store raw codes long-term. With high-entropy codes, keyed HMAC/digests and matching implementations can work; validate against your threat model.
- Consumption must be **atomic** and **single-use**; never let two concurrent requests redeem the same code.
- Enforce rate limits, attempt caps, alerts, and account locks.
- Codes grant only **recovery** scope, never automatically `ROLE_ADMIN`.
- Once new codes are generated, old codes are revoked per policy; warn users about consumed/invalidated codes.
- Never send raw recovery codes to analytics, logs, insecure emails, or URL query parameters.

A recovery code can be valid recovery evidence, yet **a single recovery code alone** is not necessarily enough to grant an **MFA-complete login session**. Policy may require additional checks, a waiting delay, verification via a previously registered channel, or a trusted support workflow.

### Lost TOTP/Passkey

When resetting a factor:
1. Verify the account owner using independent evidence established **prior** to the incident.
2. Never allow an old remember-me session alone to add a passkey, change a phone number, or disable TOTP.
3. Never allow **changing the email address** and immediately using that new email to receive a recovery link without strengthened verification.
4. Notify via both old and new channels when safe, giving the user an incident reporting path.
5. Depending on risk, require a cooling-off period or review for sensitive accounts.
6. Revoke the lost or suspected-compromised factor and invalidate at-risk sessions/tokens.
7. Never automatically create a “full admin session” solely from a reset event.

## 11. Forgot Password Must Not Automatically Wipe MFA

Dangerous pattern:

```text
User clicks "Forgot password"
    -> Receives reset email
    -> Chooses new password
    -> Server automatically calls login()
    -> Session gets marked MFA_COMPLETE
```

If email is the sole recovery path, an attacker who compromises the mailbox can skip the remaining factor without knowing the TOTP code. **Password reset** and **second-factor verification** are two distinct operations.

Safer workflow:

- Use high-entropy, short-TTL, single-use, purpose-bound, rate-limited reset tokens.
- Return uniform “if the account exists...” responses to minimize user enumeration.
- Do not auto-log-in after reset—or if the product must issue a temporary session, grant only a **limited recovery session** with no sensitive privileges and never mark it MFA-complete.
- Cancel other outstanding reset tokens when policy requires; revoke or require re-auth on previously issued sessions/remember-me cookies.
- Send notifications to verified channels; never log new passwords or raw tokens.
- Enforce MFA per policy on the user's next login, and handle lost-password-**and**-factor separately.

**Never equate “has email reset” with “satisfies MFA”.** Email can serve as an account-control mechanism in recovery, yet meeting assurance levels demands policy and threat-model design, not endpoint naming.

## 12. Changing, Disabling, or Adding Factors: Sensitive Operations

Endpoints such as:

```text
POST /account/mfa/disable
POST /account/mfa/totp/reset
POST /account/passkeys/register
DELETE /account/passkeys/{credentialId}
PUT /account/recovery-email
POST /account/recovery-codes/regenerate
POST /account/api-keys
```

must not be protected by `authenticated()` alone when the application requires MFA on accounts.

**Protections should include:**

1. **Fresh re-authentication/step-up** using an enrolled factor within policy limits (e.g., 5–15 minutes for MFA changes).
2. **Account-scoped authorization**: users manage only their own credentials; support admins must never use broad privileges to read users' private secrets.
3. **CSRF protection** on state-changing operations in session/cookie flows; never use GET to modify factors.
4. **Session fixation/rotation** and factor state updates upon completion.
5. **Out-of-band notifications**, event-identified auditing, repeated-failure detection, and quotas.
6. **Recovery exceptions** only via a dedicated recovery workflow with short TTL and least privilege.
7. **Never trust** frontend-supplied fields like `mfaVerified=true`, `trusted=true`, or `assurance=high`.

Changing an authenticator can be a high-risk event even if the session has held MFA status since morning; check **freshness** rather than relying on a week-old cookie.

## 13. SSO via OIDC/SAML: Delegating MFA to an IdP Still Requires Verification

An application may use `oauth2Login()` or `saml2Login()` instead of handling password+OTP directly. In that case MFA policy may be enforced by the **Identity Provider (IdP)**, yet the RP/app must still validate assurance evidence.

### With OpenID Connect (OIDC)

Some IdPs emit claims such as:

- `acr`: authentication context class reference, authentication level/type per agreement.
- `amr`: authentication methods references, methods used; semantics depend on the issuer.
- `auth_time`: timestamp when the user authenticated at the IdP.

**You must have a contract with the issuer** covering accepted values, which token carries the claims, signature/issuer/audience checks, assurance levels, and lifetimes. Never infer from `email_verified=true` or `scope=openid` that the user performed MFA.

**Illustrative** example, not a universal policy for every IdP:

```json
{
  "iss": "https://idp.example.org",
  "sub": "user-7392",
  "aud": "client-application",
  "auth_time": 1920000000,
  "acr": "urn:example:assurance:phishing-resistant",
  "amr": ["hwk", "user"]
}
```

The illustrative values above **do not** carry universal global meaning. Trust them only if emitted by the real IdP, the token is verified, and the interpretation contract is explicitly configured. For step-up, the app can request `acr_values`/`max_age` if supported by the IdP and **verify the returned claims**; sending parameters does not guarantee the IdP honored them.

### With SAML 2.0

SAML includes `AuthnStatement` and `AuthnContextClassRef` describing authentication method context per IdP. A **signed SAML Response** alone does not prove two factors: the signature proves the message came from a trusted IdP, not that the user used OTP/passkey if the assertion lacks corresponding context evidence.

Map assurance policies via an IdP-specific contract, validate assertion signature/issuer/audience/recipient/timestamps, bind to the right account, handle aged sessions, and re-authenticate on sensitive actions. `ForceAuthn` or `RequestedAuthnContext` can be sent as **requests** to the IdP; the app must still verify the actual response.

### When MFA Cannot Be Proven from the IdP

Do not guess. Policy can:
- Deny routes requiring high assurance.
- Redirect the user to an IdP supporting step-up and verify the returned result.
- Collect an additional factor in the application, using a properly designed and state-protected flow.

## 14. API/Bearer Tokens and Mobile Clients Are Commonly Overlooked Bypass Paths

Having MFA on a web page does not mean REST endpoints, mobile apps, or tokens from another flow satisfy MFA. For example:

```text
Web form /login        -> password + TOTP -> session
Legacy /api/login      -> password        -> JWT
Same /api/admin        -> accepts JWT with ROLE_ADMIN
```

If `/api/admin` checks only JWT signature and role, `/api/login` can **bypass MFA requirements**.

Design requirements:
- APIs accept only **access tokens** with valid issuer, audience, token type, expiration, and scopes.
- For user-interactive APIs requiring MFA, require **verified** assurance bindings from the issuer/token exchange/authorization server.
- `FACTOR_BEARER` in Spring Security 7 proves only **Bearer token** usage, not that the token was issued after MFA.
- Apps must never synthesize `FACTOR_PASSWORD` and `FACTOR_OTT` by reading two unverified text claims from a JWT.
- Machine-to-machine client credentials, mTLS workload identities, and human interactive sessions should have **separate policies**, neither forcing machine tokens to “enter OTP” nor letting machine tokens impersonate human users.
- If a bearer token is stolen, requiring MFA at issuance **does not always stop token replay**. Enforce TTLs, revocation, token binding/DPoP/mTLS sender-constraining where appropriate, and session governance.

In architectures with multiple gateways/sidecars, also inspect direct backend paths that bypass MFA/authorization enforcement points.

## 15. Spring Security Filter Chains: Control Both Order and Matchers

Many applications define multiple `SecurityFilterChain` beans:

```text
Chain A: /api/**       -> Bearer token
Chain B: /admin/**     -> Form login
Chain C: /**           -> Default catch-all
```

Spring Security selects a filter chain by **security matcher** and order; an endpoint needing MFA protection that lands in a lower chain requiring only `authenticated()` can be bypassed.

Checklist:
1. List the exact matchers and `@Order` of every chain.
2. Check `/api/admin/**`, `/actuator/**`, `/internal/**`, WebSocket handshakes, GraphQL, gRPC gateways, or separate admin hosts/ports.
3. Never assume `requestMatchers("/admin/**")` covers `/api/admin/**`.
4. Watch differing GET/POST methods and Spring MVC path matching rules.
5. Keep centralized policy for sensitive resources; multiple chains must remain consistent.
6. Enforce **method-level authorization** in services when multiple callers or HTTP layers exist.
7. Verify custom filters or hand-written login endpoints use `AuthenticationManager`/`SecurityContextRepository` properly; never fabricate authenticated tokens from a username alone.
8. In Spring Security 6+, if custom login saves the session manually, **explicitly save `SecurityContext`** into the proper `SecurityContextRepository`; verify session strategies and never bypass the login lifecycle.

Never glance once at `/login` and conclude every endpoint enforces MFA.

## 16. Session Management, Freshness, and Assurance Step-Up

After MFA, applications commonly maintain sessions via `HttpSession`/cookies. Session persistence is essential for UX, yet “this session completed MFA once” does not mean **every future action** is allowed forever.

Design should store/verify:
- Account owner/session ID and **authentication method/factor evidence** from a trusted source.
- Factor completion timestamp (`issuedAt`, `auth_time`) and per-operation time limits.
- Risk events: account recovery, password change, MFA disablement, new credential registration, token revocation, suspected lost device.
- Session invalidation and session refresh after privilege/factor changes.
- Ensuring remember-me or recovery sessions **never auto-upgrade** to MFA-complete simply when the user refreshes a page.
- Distributed state across nodes: unified session/permission view, avoiding races during logout/revocation.

### Session Cookies and Remember-Me Cookies Are Different Objects

| Component | Purpose | Security Consequence |
| --- | --- | --- |
| Session cookie | Points to an active HTTP session | If stolen, can hijack an MFA-completed session; needs TTL, revocation, CSRF, and protections |
| Remember-me cookie | Re-creates authentication when session is gone | Usually **lower assurance** than interactive login, lacks freshness |
| Trusted-device cookie | Optional hint to reduce MFA prompts per policy | Not a new factor itself; if copied, can be abused |
| Recovery token | Proves right to perform a bounded recovery task | Must never serve as a full-privilege session |
| OAuth access token | API privileges within issued lifetime | Must check audience/issuer/scope/assurance per business logic |

Never let remember-me **refresh** the MFA timestamp. And never delete only the remember-me cookie while forgetting to revoke persistent DB tokens or already-issued sessions.

### Actions That Should Require Fresh Authentication

- Changing password, recovery email, or phone number.
- Adding/removing passkeys or TOTP factors.
- Creating high-privilege API tokens.
- Viewing/rotating secret keys, accessing admin consoles.
- Transferring funds, changing beneficiaries, or high-risk operations.
- Resetting MFA when signs of account takeover appear.

Freshness should rely on a **new verification event**, not the last time the user loaded a page.

## 17. Standalone Java 17: Simulating Policy Across Multiple Entry Paths

The program below **needs no Spring** and illustrates the “deny unless evidence satisfies policy” mindset. Evidence inputs are passed as simulated values **already verified by trusted authentication sources**; **never use** this class to accept browser-sent flags in production.

Create file `MfaEntryPolicyDemo.java`:

```java
import java.time.Duration;
import java.time.Instant;

public class MfaEntryPolicyDemo {

    record Evidence(
        boolean passwordVerified,
        boolean secondFactorVerified,
        boolean rememberMeOnly,
        boolean recoveryLimited,
        Instant secondFactorAt) {}

    static boolean mayUseAdmin(
            Evidence evidence, Instant now, Duration maxAge) {
        if (evidence == null || evidence.rememberMeOnly()
                || evidence.recoveryLimited()
                || !evidence.passwordVerified()
                || !evidence.secondFactorVerified()
                || evidence.secondFactorAt() == null) {
            return false;
        }

        Duration age = Duration.between(evidence.secondFactorAt(), now);
        return !age.isNegative() && age.compareTo(maxAge) <= 0;
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-06T09:00:00Z");
        Duration maxAge = Duration.ofMinutes(10);

        Evidence passwordOnly =
            new Evidence(true, false, false, false, null);
        Evidence remembered =
            new Evidence(true, true, true, false, now);
        Evidence recovery =
            new Evidence(true, true, false, true, now);
        Evidence freshMfa =
            new Evidence(true, true, false, false, now.minusSeconds(120));
        Evidence staleMfa =
            new Evidence(true, true, false, false, now.minusSeconds(3600));

        System.out.println("password-only=" + mayUseAdmin(passwordOnly, now, maxAge));
        System.out.println("remember-me=" + mayUseAdmin(remembered, now, maxAge));
        System.out.println("recovery=" + mayUseAdmin(recovery, now, maxAge));
        System.out.println("fresh-mfa=" + mayUseAdmin(freshMfa, now, maxAge));
        System.out.println("stale-mfa=" + mayUseAdmin(staleMfa, now, maxAge));
    }
}
```

Run:

```bash
javac MfaEntryPolicyDemo.java
java MfaEntryPolicyDemo
```

**Exact stdout:**

```text
password-only=false
remember-me=false
recovery=false
fresh-mfa=true
stale-mfa=false
```

Key lessons:
- Password-only fails a policy requiring two factors.
- A remember-me cookie **does not** elevate privileges even when the simulated record sets both booleans; that entry path carries lower assurance.
- A recovery session cannot access admin functions.
- MFA evidence older than the 10-minute limit fails step-up.
- This class **does not** verify WebAuthn signatures, passwords, TOTPs, or tokens. `Evidence` must be built by a trusted server pipeline bound to account/session and protected against tampering. Production also requires `ROLE_ADMIN`, account status checks, authorization, and concurrency handling.

### Why Is Putting a Single “mfa” Boolean in the Session Insufficient?

A `Boolean.TRUE` in the session can become stale after recovery, factor reset, role changes, or device revocation. Arbitrary request data is even worse. You need an evidence/risk model with **clear provenance, validity window, and revocation capability**; in Spring Security 7, this can build on factor authorities and `issuedAt` per policy. Custom flows must update state consistently.

## 18. Mandatory Testing: “Bypass Paths Must Fail”

Good testing covers two parts: (A) verifying actual authentication mechanisms; (B) verifying policy with both valid and missing-factor cases.

### Behavior Matrix

| Scenario | Correct Outcome When Route Requires MFA |
| --- | --- |
| Not logged in | Redirect to login or appropriate 401 |
| Right password but missing second factor | **Denied** access to sensitive route |
| Valid password + OTT/TOTP within window | Allowed if role and other conditions pass |
| Valid remember-me cookie, old session expired | **Require re-auth/step-up**, do not allow immediately |
| Trusted-device cookie copied to another browser | Must not automatically elevate to MFA-complete |
| Session has User A's OTP but account switched to B | Denied; never bind factors across accounts/sessions |
| Valid recovery code | Enters only granted recovery flow, never admin immediately |
| Already-used recovery code | Denied; on concurrent attempts at most one wins |
| Successful password reset | Does not automatically create an MFA-complete session |
| Just changed email/recovery phone | Cannot use new channel immediately to bypass checks |
| OIDC token lacking sufficient `acr`/`amr` | Denied access to high-assurance routes |
| Signed SAML with insufficient `AuthnContext` | Confirms SSO only; does not elevate MFA level |
| Valid JWT issued via legacy password-only flow | Fails API's MFA policy |
| Right admin role via Basic authentication only | Denied access to route requiring MFA |
| MFA satisfied but missing `ROLE_ADMIN` | Authorization denied |
| Factor verified past step-up window | Require fresh factor |
| User disabled/locked or credential revoked | Denied even if old session/role remains |
| Login via alternate path or HTTP method | Same policy still applies |
| Multiple overlapping `SecurityFilterChain`s | No weaker-policy path matches sensitive routes |

**HTTP status codes are not always fixed**: browser sessions may redirect to the missing factor step; REST APIs typically return 401/403 depending on entry point and authentication state. Assert **no access granted**, rather than expecting one identical status across all configurations.

### Java 17 Policy Unit Tests

`MfaEntryPolicyDemo` helps verify timestamp logic and blocking remember-me/recovery. In real applications, add JUnit tests for:
- Evidence missing a factor.
- `issuedAt` in the future, null, or expired.
- Right account, yet token/recovery code was revoked.
- Wrong tenant/role.
- Account changed a factor while a session remained open.
- Race between two requests redeeming a single-use token.

### Spring Security MockMvc: Avoiding a Testing Trap

`@WithMockUser` or `.with(user("admin").roles("ADMIN"))` **mocks an Authentication**, without proving the real app ran TOTP/WebAuthn/OTT. If a test uses `@WithMockUser`, it **only** checks authorization against a fake principal—it does not prove the primary login flow or remember-me fails to bypass MFA.

For integration tests:
1. Use a test account with enrolled factors; send requests through the **real login endpoints**.
2. Log in with password only and hit MFA-required routes: must fail/redirect.
3. Complete the second factor with a valid token/challenge and retry the route: must succeed if authorized.
4. Delete the session, keep the remember-me cookie, and try the route: must be blocked until re-authenticated.
5. Use an email reset/recovery code then try an admin route: blocked or restricted to recovery-limited.
6. Replace/revoke a factor, then test old sessions and trusted devices: must follow updated policy.
7. Test every `SecurityFilterChain`, host/port/API version, and mobile client.
8. Test `@PreAuthorize` on services reachable via MVC as well as schedulers/gRPC/gateways if present.

Measure enforcement at the **resource boundary**, not just screenshots of entering an OTP.

## 19. Real-World Failure Scenarios and Classifications

| Symptom | Common Root Cause | Mitigation |
| --- | --- | --- |
| User with `ROLE_ADMIN` enters admin without OTP | Checking only role or `authenticated()` | Enforce factor policy in authorization manager / IdP assurance |
| Remember-me cookie opens MFA-disable page | `.authenticated()` accepts remember-me | Separate low/high assurance; step-up + freshness, `fullyAuthenticated()` only as secondary guard |
| Password reset via email auto-logs in | Recovery treated as full authentication | Grant only recovery-limited; require full login/re-auth |
| JWT from legacy app reaches MFA-required API | Skipping issuer/audience/assurance checks, shared role | Separate token policies by audience and issuance flow |
| Session gets new role without new factor | Role mapping mistaken for MFA proof | Never derive `FACTOR_...` from DB roles |
| User A's OTP works for User B's session | Challenge/factor not bound to account and session | Bind challenge to exact account/transaction; consume once |
| Users locked out after losing phones | Recovery not designed upfront | Strong recovery codes and secure support workflows |
| Help desk disables TOTP after a phone call | Weak identity verification, no auditing | Strong proofing, separation of duties, delays/notifications |
| “Remember device” lasts forever | Missing TTL/revocation or treating cookie as factor | Limit lifetime and privileges; revoke on risk events |
| OIDC SSO active yet app doesn't know if IdP did MFA | Missing `acr`/`amr` contract, ignoring `auth_time` | Require and verify assurance from IdP |
| `/api/admin` unaffected by `/admin/**` rules | Different matcher/chain | Audit all `securityMatcher`s, `@Order`, and method security |
| Spring Security 6.x cannot find `FactorGrantedAuthority` | Class introduced in 7.0 | Upgrade consistently or use trusted IdP/custom MFA mechanism |
| MFA tests pass yet production still bypassed | MockMvc used `@WithMockUser` without testing login filters | End-to-end test every auth path and remember-me |
| Persistent remember-me token still works after logout | Clearing only session cookie or miswired logout | Revoke cookie **and** server-side token per design |
| MFA disabled yet session retains full strength | Assurance/session state not updated after change | Invalidate/step-down/re-auth per policy |

## 20. Deployment and Operations Checklist

### 20.1. Before Release

- [ ] Inventory **all** authentication endpoints/flows: web, API, mobile, admin, legacy, SSO, OTT, passkey, Basic, remember-me, recovery, help desk.
- [ ] Every sensitive resource has an approved **role + factor + freshness** policy.
- [ ] Authentication factors are recorded only after trusted server/IdP verification; never read `mfa=true` from input.
- [ ] Remember-me or trusted-device cookies are never accepted as fresh factor evidence.
- [ ] Password resets never auto-mark sessions MFA-complete.
- [ ] Recovery codes are single-use, high-entropy, brute-force-resistant, and stored/verified securely.
- [ ] Changing MFA/recovery email/passkey requires re-auth, auditing, and notifications.
- [ ] Cookies/sessions/tokens have proper TTLs, CSRF protection, rotation, and revocation.
- [ ] SSO IdP assurance claims are verified against issuer/claim/contract rules.
- [ ] JWTs/APIs enforce audience/issuer/scope/assurance per resource; password-only paths cannot enter admin.
- [ ] All `SecurityFilterChain` matchers, role rules, and `@PreAuthorize` annotations are audited.
- [ ] Negative bypass tests cover multi-node and account/session recovery scenarios.
- [ ] Runbooks exist for helping users who lost factors without leaking secrets or arbitrarily granting privileges.

### 20.2. In Operations

Monitor missing-factor login rates, recovery failures, repeated OTP/recovery-code attempts, anomalous remember-me cookie issuance, new devices, factor resets, and session revocations. Distinguish UX friction from account takeover signals, apply appropriate rate limits, and notify users on security changes.

Never log passwords, OTPs, raw reset links, remember-me cookies, JWTs, or TOTP seeds. Store only event IDs and minimal metadata needed for investigation. Risk signals like IP, ASN, or new device **assist** risk evaluation, but never replace a verified authentication factor.

## 21. Decision Summary

A tight MFA system has at least three layers:

1. **Authentication pipeline:** each mechanism verifies password, OTT, passkey, SSO, or tokens per standard, attaching trusted evidence with account and timestamp.
2. **Authorization and assurance:** every sensitive request verifies role **and** required factors **and** freshness; never let browser-remembered, legacy, or recovery paths satisfy conditions via a shortcut.
3. **Lifecycle and recovery:** factor changes, password resets, lost devices, trusted devices, remember-me, and help desk all require policies, auditing, notifications, and revocation.

Spring Security 7.x provides `FactorGrantedAuthority` and `@EnableMultiFactorAuthentication`/authorization managers to model factor requirements on Servlet. Spring Security 6.x has `fullyAuthenticated()` to block remember-me, yet **that is not MFA**. Regardless of version, the most common vulnerabilities still lie in **secondary login paths or recovery flows**, not in the OTP comparison math.

## 22. Official References

- Spring Security 7.0 — Multi-Factor Authentication: https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/mfa.html
- Spring Security 7.0 Javadoc — `FactorGrantedAuthority`: https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/core/authority/FactorGrantedAuthority.html
- Spring Security 7.0 Javadoc — `@EnableMultiFactorAuthentication`: https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/config/annotation/authorization/EnableMultiFactorAuthentication.html
- Spring Security 6.5 — Remember-Me Authentication: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/rememberme.html
- Spring Security — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- OWASP — Multifactor Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html
- OWASP — Forgot Password Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html
- OWASP — Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html

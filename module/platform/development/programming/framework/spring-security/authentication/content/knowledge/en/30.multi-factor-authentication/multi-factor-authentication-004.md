# Relationship Between Factor-Providing Mechanisms and Factor-Requiring Rules in Spring Security

## 1. Two Separate Things That Must Go Together

When designing Multi-Factor Authentication (MFA), there are two **independent** questions:

1. **Which authentication mechanism provides the factor?** For example: username/password, one-time token (OTT), WebAuthn/passkey, certificate authentication, or an external IdP. Each mechanism verifies a type of evidence and can record the factor the user has performed.
2. **Which factors does the access rule require?** For example: viewing a regular page requires login; changing email requires both password and OTT; administration requires role ADMIN **and** two valid factors.

Enabling two login methods **is not synonymous** with requiring both. If an application configures `formLogin()` and `oneTimeTokenLogin()` while every page only uses `authenticated()`, in a standard configuration the user can complete **either one** to enter the page. Conversely, if a rule requires two factors without a mechanism to provide the missing factor, the user cannot satisfy the requirement.

Therefore, the proper relationship is:

```text
Authentication mechanism / factor provider
    password ──────────> FACTOR_PASSWORD
    one-time token ────> FACTOR_OTT
    WebAuthn ──────────> FACTOR_WEBAUTHN  (depends on config and version)
                  │
                  ▼
       User's Authentication
        (identity + verified factors)
                  │
                  ▼
     Resource authorization rules
      /dashboard : authenticated
      /settings  : PASSWORD AND OTT
      /admin     : ROLE_ADMIN AND PASSWORD AND OTT
                  │
                  ▼
         Allow / deny / step-up
```

**Core point:** a mechanism **provides** trusted authentication state; a policy **requires** a set of authentication states. Both are connected through `Authentication`, `GrantedAuthority`, and `AuthorizationManager` or an equivalent policy system.

This article focuses on Spring Security Servlet. **Spring Security 7.0+** includes framework-level MFA APIs such as `FactorGrantedAuthority`, `@EnableMultiFactorAuthentication`, and `AuthorizationManagerFactories.multiFactor()`. They were introduced in the 7.0 line; **Spring Security 6.x does not include these 7.0 APIs**. Examples using 7.0+ are clearly marked to avoid copying into Boot 3 / Security 6 applications.

## 2. Factors, Mechanisms, and Permissions Are Not the Same Thing

NIST/OWASP typically classify factor categories by evidence type:

- **Something you know:** what the user knows, such as a password/PIN.
- **Something you have:** what they possess or control, such as a device, authenticator, or hardware token.
- **Something you are:** biometric characteristics.
- Location, behavioral, and risk signals can serve as an additional layer, but are **not automatically** equivalent to an independent factor in all standards.

Three levels must be distinguished:

| Concept | Examples | Role in Policy |
| --- | --- | --- |
| **Authentication mechanism** | Password login, OTT login, WebAuthn, OIDC login | Runs the credential/evidence verification flow |
| **Factor evidence** | `FACTOR_PASSWORD`, `FACTOR_OTT`, factor verification timestamp | Indicates which authentication step has been performed |
| **Authorization authority** | `ROLE_ADMIN`, `SCOPE_report.read` | Indicates business privileges, not proof of MFA |

`ROLE_ADMIN` **does not** mean the administrator has completed MFA. `authenticated()==true` **does not** mean two factors are satisfied. Conversely, someone who completed two factors may still not be allowed to manage users if they lack `ROLE_ADMIN`.

**The same factor must not be counted twice just because there are two screens.** Asking for a password twice does not turn it into MFA. Two codes sent to the same inbox may still rely on a single possession source. An email magic link and a password may be two mechanisms, yet their **independence and strength** depend on mailbox control, phishing susceptibility, account recovery, and implementation details.

WebAuthn/passkey is a **method** that can carry varying assurance properties depending on authenticator, user verification, and policy. Do not conclude “password must always be enabled too” or “a passkey always equals two factors” without checking against the desired assurance level.

## 3. A Simple Mathematical Model

Let:

- `P` be the **set of verified and still-valid factors** of the current Authentication.
- `R(resource)` be the **set of factors required by the resource**.
- `A(resource)` be other authorization conditions such as role, scope, tenant, and ownership.
- `F(resource)` be freshness/assurance checks when the resource requires recent authentication.

A request is permitted when:

```text
authenticated
AND requiredFactors(resource) ⊆ verifiedValidFactors(authentication)
AND authorizationPolicy(resource, principal)
AND freshnessPolicy(resource, factorEvidence)
```

If `P = {PASSWORD}` and `R = {PASSWORD, OTT}`, it is not satisfied. If `P = {PASSWORD, OTT}`, the factor part is satisfied, yet `ROLE_ADMIN` or object-level permissions must still be checked separately.

### 3.1. State Table

| User State | `authenticated()` | `PASSWORD` Only | `PASSWORD AND OTT` | `ROLE_ADMIN AND PASSWORD AND OTT` |
| --- | --- | --- | --- | --- |
| Not logged in | No | No | No | No |
| Logged in with password | Yes | Yes | No | No |
| OTT only (if supported by system) | Yes | No | No | No |
| Password then OTT | Yes | Yes | Yes | Only if `ROLE_ADMIN` is present |
| Both factors, but OTT too old per policy | Yes | Yes | Yes if freshness is not required | No if policy requires fresh OTT |
| Admin with valid password + OTT | Yes | Yes | Yes | Yes, if other business conditions also pass |

The table illustrates the difference between **successful login**, **sufficient factors**, **sufficient role**, and **sufficient freshness**. The Password/OTT columns must be understood within a system that reliably verifies factors; simply attaching a `FACTOR_*` string to an object is not security proof.

## 4. Spring Security 7: FactorGrantedAuthority Is the Bridge

In Spring Security 7.0+, `FactorGrantedAuthority` is a `GrantedAuthority` implementation with special meaning: it records the factor used and the issuance time via `getIssuedAt()`. Standard mechanisms can add the corresponding factor authority to `Authentication` upon authentication.

Representative constants:

| Constant in `FactorGrantedAuthority` | Authority String | Typical Source |
| --- | --- | --- |
| `PASSWORD_AUTHORITY` | `FACTOR_PASSWORD` | Password authentication |
| `OTT_AUTHORITY` | `FACTOR_OTT` | One-Time Token login |
| `WEBAUTHN_AUTHORITY` | `FACTOR_WEBAUTHN` | WebAuthn authentication |
| `X509_AUTHORITY` | `FACTOR_X509` | X.509 authentication |
| `AUTHORIZATION_CODE_AUTHORITY` | `FACTOR_AUTHORIZATION_CODE` | OAuth2 Authorization Code mechanism |
| `BEARER_AUTHORITY` | `FACTOR_BEARER` | Bearer token authentication |

**Do not read this table as a certificate guaranteeing MFA in every system.** For example, `FACTOR_BEARER` may only indicate that the Bearer mechanism was used; it **does not** prove the bearer access token reflects user MFA. `FACTOR_AUTHORIZATION_CODE` does not imply the IdP performed two factors. Actual assurance depends on the protocol and the issuer's authentication policy.

When a mechanism authenticates successfully, it **provides** a factor authority. When an authorization rule checks factors, it **consumes** that evidence. An application can accept multiple mechanisms, but only configured rules bind them together.

For custom factors, only construct `FactorGrantedAuthority` from a vetted authentication component **after** genuine verification; never take `FACTOR_OTT`, timestamps, or `amr`/`acr` from a client-supplied HTTP header. `FactorGrantedAuthority.fromAuthority(...)` is an object-creation API, **not a credential-verification API**.

## 5. Responsibilities of Each Layer in the Flow

A two-step flow typically consists of:

1. **Authentication entry point:** detects that the user lacks credentials or is missing a factor and routes them to the appropriate login/step-up method.
2. **Password/OTT/WebAuthn mechanism:** receives evidence, invokes the provider/manager to verify it, and handles anti-replay and errors.
3. **Authentication / SecurityContext:** represents identity, authorities, and completed factors. Saving/restoring the context must fit the session lifecycle.
4. **AuthorizationManager:** at access time, checks the route/method's required factors and required roles/scopes.
5. **Controller/service:** executes business logic **only after** policy allows; continues enforcing tenant/ownership/transaction rules.

When only password is present and the user hits `/settings/security` requiring Password + OTT, the system must not silently “skip OTT because the user is authenticated”. It must request OTT as well. If the user fails to provide it or the OTT is expired, the resource remains blocked.

**Conversely, merely enabling `oneTimeTokenLogin()` is not enough to require MFA.** Some users could log in with OTT alone if authorization only calls `authenticated()`. “Having a mechanism” is a **capability**; “requiring it” is a **policy**.

### 5.1. Why Not Put Logic in the Controller?

Counter-example:

```java
// COUNTER-EXAMPLE — do not copy:
@GetMapping("/transfer")
public String transfer(Authentication authentication) {
    if (authentication.isAuthenticated()) {
        return "transfer allowed";
    }
    return "login required";
}
```

This is a snippet illustrating the flaw, not a full class. It checks neither factors, freshness, nor permissions. Moreover, authorization decisions inside controllers are easily forgotten on other endpoints. It is far better to centralize policy in URL/method security while still checking data permissions in the service layer.

## 6. Standalone Java 17 Example: Providing Mechanisms and Requiring Rules

The following example **does not depend on Spring** and accurately models the relationship between factor sets so it is easy to run with `javac`/`java`. It does not replace a real authentication system or `SecurityContext`.

**`FactorPolicyDemo.java`**

```java
import java.util.EnumSet;
import java.util.Set;

public class FactorPolicyDemo {
    enum Factor { PASSWORD, OTT }
    record Session(Set<Factor> factors, boolean admin) {}

    static boolean allowsSettings(Session session) {
        return session.factors().containsAll(
                EnumSet.of(Factor.PASSWORD, Factor.OTT));
    }

    static boolean allowsAdmin(Session session) {
        return session.admin() && allowsSettings(session);
    }

    public static void main(String[] args) {
        Session passwordOnly =
                new Session(EnumSet.of(Factor.PASSWORD), true);
        Session both =
                new Session(EnumSet.of(Factor.PASSWORD, Factor.OTT), false);
        Session adminBoth =
                new Session(EnumSet.of(Factor.PASSWORD, Factor.OTT), true);

        System.out.println("password-only settings = "
                + allowsSettings(passwordOnly));
        System.out.println("password-only admin = "
                + allowsAdmin(passwordOnly));
        System.out.println("both settings = "
                + allowsSettings(both));
        System.out.println("both admin = "
                + allowsAdmin(both));
        System.out.println("admin both admin = "
                + allowsAdmin(adminBoth));
    }
}
```

Compile and run from the directory containing the file:

```bash
javac FactorPolicyDemo.java
java FactorPolicyDemo
```

Exact stdout:

```text
password-only settings = false
password-only admin = false
both settings = true
both admin = false
admin both admin = true
```

Meaning: even though all are `authenticated`, a user with only password fails Settings requirements, while a user with both factors but without the ADMIN role still cannot access Admin. In real Spring, these sets/authorities **must be produced by a trusted authentication process**, with expiration and session checks.

## 7. Spring Security 7 Example: Applying MFA Across the Entire Application

**Version requirement:** this sample uses **Spring Security 7.0+**, typically paired with the compatible Spring Boot 4.x ecosystem, Java 17+. Do not copy verbatim into Spring Boot 3.x / Security 6.x. `@EnableMultiFactorAuthentication` and `FactorGrantedAuthority` were introduced in Spring Security 7.0.

Demo goals:

- `/public/**` pages are accessible without login.
- Regular pages require both password **and** OTT.
- `/admin/**` requires `ROLE_ADMIN` in addition to both factors.
- Authentication mechanisms are form/password and one-time-token login.

The **core** imports and configuration below go in `SecurityConfig.java`:

```java
package com.example.mfa;

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
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/public/**").permitAll()
                        .requestMatchers("/admin/**").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .oneTimeTokenLogin(Customizer.withDefaults())
                .build();
    }
}
```

**Reading the code as two independent parts:**

- `formLogin(...)` / `oneTimeTokenLogin(...)` **provide authentication methods**. When processed successfully, each mechanism can record `FACTOR_PASSWORD`/`FACTOR_OTT` into Authentication in Spring 7's MFA system.
- `@EnableMultiFactorAuthentication(authorities={PASSWORD,OTT})` **places additional requirements** onto authorization rules built via the supporting factory. Thus `hasRole("ADMIN")` checks not only the role but also enforces the required factors; `authenticated()` likewise no longer means just a single factor.
- `permitAll()` and public rules should still be organized intentionally; per the MFA factory API, additional factor requirements do not turn `permitAll()` into a protected endpoint.
- Even when the password is correct, a user lacking OTT still fails a protected endpoint subject to MFA.

**Runnable scope:** this class compiles in a Spring Security 7.x project with Servlet web security, but is **not yet a complete OTT token-sending system**. You must configure a user store, password encoder, token delivery service, and `OneTimeTokenGenerationSuccessHandler`. In production, determine the recipient email/address from verified account data, enforce rate limits, and protect magic links from exposure; see section 10.

**Do not confuse:** `@EnableMultiFactorAuthentication` does not turn one password into two factors. It only makes policies require additional factors supplied by the appropriate mechanisms.

## 8. Requiring MFA Only for Sensitive Endpoints

Not every website needs two factors on every page. You can use `AuthorizationManagerFactories.multiFactor()` to build per-URL local policies.

In Spring Security 7.0+, example configuration (**replaces** the global example in section 7; do not put both `SecurityConfig` classes in the same project):

```java
package com.example.mfa;

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
public class SelectiveMfaSecurity {

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        var mfa = AuthorizationManagerFactories.multiFactor()
                .requireFactors(
                        FactorGrantedAuthority.PASSWORD_AUTHORITY,
                        FactorGrantedAuthority.OTT_AUTHORITY)
                .build();

        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/public/**").permitAll()
                        .requestMatchers("/admin/**")
                        .access(mfa.hasRole("ADMIN"))
                        .requestMatchers("/user/settings/**")
                        .access(mfa.authenticated())
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .oneTimeTokenLogin(Customizer.withDefaults())
                .build();
    }
}
```

**Key takeaway:** `@EnableMultiFactorAuthentication(authorities={})` activates supporting infrastructure without setting a global requirement. The `mfa` object is created **inside the method**, not registered as a global factory bean. Therefore:

| URL | Applied Rule | Which Factors Are Required? |
| --- | --- | --- |
| `/public/**` | `permitAll()` | None |
| `/user/settings/**` | `mfa.authenticated()` | Password and OTT |
| `/admin/**` | `mfa.hasRole("ADMIN")` | Password, OTT, `ROLE_ADMIN` |
| Remaining URLs | `authenticated()` | Logged in, without adding the two factors from the local factory |

This example precisely demonstrates **the relationship between provided factors and the rules requiring them**: both mechanisms can exist for all requests, yet only endpoints using the MFA authorization manager enforce both.

Do not confuse `securityMatcher` (selecting a filter chain) with `requestMatchers` (selecting rules inside a chain). With multiple chains, ensure sensitive endpoints actually route through the chain containing the MFA rule rather than being unintentionally skipped by a higher-priority chain.

## 9. How MFA Rules Express AND and OR Conditions

### 9.1. All Factors Must Be Present (AND)

Typical model:

```text
allow = authenticated
    AND has(FACTOR_PASSWORD)
    AND has(FACTOR_OTT)
    AND businessAuthorization
```

In Spring Security 7, `AuthorizationManagerFactories.multiFactor().requireFactors(...)` creates authorization managers requiring all specified factors combined with normal roles/authorities.

For simple logic, documentation also describes `hasAllAuthorities(...)`, e.g., a **Spring Security 7.x snippet** inside `authorizeHttpRequests`:

```java
.requestMatchers("/admin/**").hasAllAuthorities(
        "ROLE_ADMIN",
        FactorGrantedAuthority.PASSWORD_AUTHORITY,
        FactorGrantedAuthority.OTT_AUTHORITY)
```

Checking individual strings is explicit, yet repetitive and cannot always express freshness or complex conditions. If a project uses `hasAllAuthorities` in a specific version, verify availability and semantics for that exact version. Never substitute `hasAnyAuthority(PASSWORD,OTT)`: **ANY/OR** allows just one factor.

### 9.2. One of Several Valid Factor Combinations (OR of AND Groups)

Sometimes policy accepts:

- A WebAuthn login with sufficient assurance, **or**
- Password **and** OTT.

That is:

```text
allow = has(FACTOR_WEBAUTHN)
        OR (has(FACTOR_PASSWORD) AND has(FACTOR_OTT))
```

This must never be wrongly simplified to:

```text
has(FACTOR_WEBAUTHN)
OR has(FACTOR_PASSWORD)
OR has(FACTOR_OTT)
```

The wrong version allows password alone. With Spring Security 7, documentation provides `AllRequiredFactorsAuthorizationManager.anyOf(...)` to combine groups. Those groups must reflect the product's assurance policy and the actual properties of WebAuthn/OTT; never infer assurance solely from the number of factor constants.

### 9.3. How Do Permissions and Factors Combine?

MFA **does not replace** `ROLE_ADMIN`, `SCOPE_transfer.write`, or tenant checks. In practice: `allow = required factors AND required business authority AND resource ownership`. When using a factory to wrap rules, verify these conditions are genuinely **AND**, not overridden by a filter, entry point, or fallback branch.

## 10. Factor-Providing Mechanisms Must Be Genuinely Implemented

### 10.1. Password Login

`formLogin()` only enables the flow that accepts and checks username/password. A real system needs a `UserDetailsService`/repository, an appropriate `PasswordEncoder` (such as an adaptive encoder), brute-force limits, session protection, and a password reset policy. Simply storing a username in the session and granting `FACTOR_PASSWORD` **is not** password verification.

### 10.2. One-Time Token (OTT) Login

Spring Security provides `oneTimeTokenLogin()`. **OTT differs from TOTP/HOTP**:

- **OTT**: the server generates a single-use token, sends it to the user (e.g., an email magic link), and verifies the token at an endpoint. Usually does not require pre-installing an authenticator app.
- **TOTP/HOTP**: codes computed from a pre-established secret/credential; not synonymous with Spring Security `oneTimeTokenLogin()`.

Spring Security provides the token generation/consumption infrastructure and UI, **but cannot know the application's recipient addresses or delivery route**. You must implement `OneTimeTokenGenerationSuccessHandler` to send via a trusted channel. You need TTL policies, single-use enforcement, replay protection, token-request rate limits, protection of the magic link endpoint, and recipient lookup from verified user account data—never an attacker-supplied target email.

**Implementation pseudocode** for a handler (not standalone runnable Java):

```text
onOneTimeTokenGenerated(request, token):
    username = token.username
    recipient = trustedAccountDirectory.emailFor(username)
    require recipient is verified
    magicLink = trustedPublicBaseUrl + "/login/ott?token=" + encode(token.value)
    secureEmailSender.send(recipient, magicLink)
    redirectUserTo("/ott/sent")
```

Do not log raw OTTs or magic links, and never use an unverified `request.getHeader("Host")` as the base for generating links. In production, the email channel can be compromised; if both password reset and OTT share the same inbox, factor independence degrades.

### 10.3. WebAuthn/Passkey

WebAuthn has its own ceremony and cryptographic checks, including relying-party ID, origin, challenge, signature, credential binding, and user verification per policy. Only add `FACTOR_WEBAUTHN` **after** trusted WebAuthn verification succeeds. Never treat a client-asserted cookie claiming passkey usage as a factor.

### 10.4. OIDC, Bearer Tokens, and IdP-Verified Factors

A browser app using `oauth2Login()` can have the IdP authenticate via password/MFA; a Resource Server receiving a Bearer JWT may also see claims like `acr`, `amr`, and `auth_time`. However, that **does not automatically mean** Spring Security has recorded local `FACTOR_PASSWORD` and `FACTOR_OTT` factors.

To trust external MFA, verify the token/issuer/audience/signature/time, claim semantics per the IdP contract, assurance level, and freshness. Never extract claims from an unverified token or accept an `X-MFA: true` header from the client. If local policy requires PASSWORD + OTT, determine whether there is a trusted mapping from IdP assertions to local evidence or perform factors in the application itself—do not simply enable OIDC and assume both constants are present.

## 11. Freshness: Present Factors That Are Too Old

A factor verified yesterday may suffice to view a dashboard, yet **not** to approve a current payment. Spring Security 7 provides `FactorGrantedAuthority.getIssuedAt()` and lets rules declare `validDuration` for the corresponding factor.

**Spring Security 7.x** example (snippet placed inside the filter chain builder method; requires importing `java.time.Duration` and `AuthorizationManagerFactories`):

```java
var passwordLast30Minutes = AuthorizationManagerFactories.multiFactor()
        .requireFactor(factor -> factor
                .passwordAuthority()
                .validDuration(Duration.ofMinutes(30)))
        .build();

http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/admin/**")
        .access(passwordLast30Minutes.hasRole("ADMIN"))
        .anyRequest().authenticated());
```

In this example, the admin page requires `ROLE_ADMIN` and a password factor verified within the last 30 minutes. This **only requires a recent password**, and does not automatically demand OTT unless policy adds it. For resources requiring both fresh password and fresh OTT, include both factors with their respective valid durations.

Distinguish clearly:

- **Factor authority** stores the `issuedAt` timestamp.
- **Resource rule** decides how long a factor counts as sufficiently fresh.
- The same factor can be fresh enough for page A while already too old for page B.

If you only check `hasAuthority("FACTOR_PASSWORD")` as a string, you may **bypass freshness**. Check timestamps using factor types and supporting policies, or via trusted evidence issued by the AS/IdP.

**Session risk:** if factor evidence lives as long as the session without freshness rules, password changes, account locks, or IdP logouts do not automatically revoke access. Design appropriate timeouts, security context persistence, step-up, and session invalidation.

## 12. Mechanisms and Rules Must Stay Consistent Across the Session Lifecycle

A real flow typically passes through these states:

```text
Anonymous
  │ password login succeeds
  ▼
Authenticated + PASSWORD
  │ access /dashboard: allowed
  │ access /settings: missing OTT → require step-up
  │ submit valid OTT (same identity and same transaction)
  ▼
Authenticated + PASSWORD + OTT
  │ access /settings: allowed
  │ access /admin: also requires ROLE_ADMIN
  ▼
Factor expired / user locked / session expired
  └── Reauthenticate or deny per policy
```

**Conditions to verify:**

1. An OTT must never elevate factors for **a different user** than the currently authenticating session. Bind properly to account and request to prevent session swapping.
2. When completing the next factor, the context must preserve the exact identity, authorities, and previously verified states; never accidentally overwrite the whole `Authentication` or retain factors from another session.
3. Logout must clear sessions/evidence per policy. Session fixation protection, `Secure`/`HttpOnly`/`SameSite` cookies, and CSRF must be configured appropriately for browser login.
4. When user permissions or factor requirements change, define how sessions/contexts are refreshed. Policy updates are not automatically reflected in an improperly cached custom session.
5. Remember-me, API keys, client-asserted auth tokens, or unconsumed magic link URLs **are not** fresh OTT evidence. Weaker mechanisms must never grant strong authorities.
6. If a factor fails/expires or the OTP/OTT delivery system errors out, **fail closed** on protected endpoints. A separately vetted recovery flow may exist, but never `permitAll()`.

## 13. Spring Security 6.x: Do Not Confuse Version-Specific APIs

`FactorGrantedAuthority`, `AuthorizationManagerFactories.multiFactor()`, and `@EnableMultiFactorAuthentication` were introduced in Spring Security **7.0**. Boot 3.x / Security 6.x apps **cannot** copy these imports/APIs and expect them to compile. However, the architectural principles remain identical:

- Use authentication mechanisms/providers that genuinely verify each factor.
- Record evidence in a trusted server-side model (session/MFA state) or trusted IdP claims.
- Apply a custom `AuthorizationManager<RequestAuthorizationContext>` / method security to enforce multiple conditions.
- Enforce an AND relationship between roles/scopes and required factors, with TTL, tenant, and auditing.
- Never allow weaker authentication methods such as API keys, remember-me, non-MFA JWTs, or password-only fallbacks to bypass sensitive policies.

**Architectural pseudocode for Security 6**, not Spring 7 API:

```text
AuthenticationManager / IdP verifies PASSWORD
    → server-side session contains verifiedPasswordAt

OTT service verifies one-time token for SAME principal
    → server-side session contains verifiedOttAt

AuthorizationManager for /settings
    → require authenticated
    → require verifiedPasswordAt within policy window
    → require verifiedOttAt within policy window
    → require same principal/session and no revocation
    → allow else deny/step-up
```

Storing factor state in a session bean or custom authentication is only meaningful if **clients cannot tamper with it** and session/CSRF protections are active. Never use a request parameter `mfa=true` or `@PreAuthorize("isAuthenticated()")` as a substitute for factor checks. For new builds wanting standard MFA APIs, consider upgrading to a supported version and checking the corresponding docs.

## 14. HTTP APIs and Clients Without Browser Sessions

MFA over a **web session** differs from bearer-token APIs:

- With browsers, individual mechanisms accumulate factors onto `Authentication`, and authorization rules decide when to step up.
- With stateless resource servers, each request is typically authenticated via a bearer access token. The API cannot automatically infer the user completed OTT at the IdP merely by receiving a token. It must verify the **API-targeted access token**, issuer, signature or introspection, audience, expiry, scope, and assurance claims per contract.
- If the token carries `acr`, `amr`, or `auth_time`, confirm the issuer's exact semantics; a new token may be needed after step-up. Never grant `FACTOR_OTT` from an ununderstood `amr` claim or from an ID token not meant for the API.
- A client-credentials token usually represents a **service**, not an MFA-authenticated user. Never let an API key/service token satisfy a policy requiring user factor proof.
- Data-level authorization still requires tenant, ownership, and transaction policies after factors/claims are trusted.

**Separating authentication mechanisms from policy** remains the central principle. On the API side, providing factors may occur at the IdP/AS; on the Resource Server side, rules checking **verified assurance** live in the authorization layer.

## 15. Testing Matrix Matching “Provide” and “Require”

| Case | Verified Factor/Evidence | Rule | Expected Result |
| --- | --- | --- | --- |
| Guest accesses protected dashboard | None | Authenticated | Deny / redirect to login |
| Password-logged-in user accesses dashboard | PASSWORD | Authenticated | Allow |
| Password-logged-in user accesses settings | PASSWORD | PASSWORD + OTT | Deny, require OTT |
| OTT-only user accesses settings | OTT | PASSWORD + OTT | Deny, require password |
| User with password and OTT accesses settings | PASSWORD + OTT | PASSWORD + OTT | Allow |
| Non-admin user with both factors accesses admin | PASSWORD + OTT, no role | `ROLE_ADMIN` + both factors | Deny |
| Admin with both factors accesses admin | `ROLE_ADMIN` + PASSWORD + OTT | `ROLE_ADMIN` + both factors | Allow |
| Admin with stale OTT | Factors present, OTT expired per rule | Fresh OTT | Deny, step-up |
| User with ADMIN role but password only | ADMIN + PASSWORD | `ROLE_ADMIN` + both factors | Deny |
| Attacker sends `X-FACTOR-OTT: true` | No trusted factor | PASSWORD + OTT | Deny |
| Bearer access token without MFA from issuer | Token-verified Bearer | Endpoint needs user assurance | Deny |
| Password reset or logout | Evidence revoked per policy | Sensitive page | Require re-login / step-up |

The test suite must verify that sensitive controllers/services **never** execute when a factor is missing; checking status codes alone is not enough. Responses may be a redirect (browser), 401 (API), or 403 (logged in without permission), depending on entry point and UX.

### 15.1. Policy Unit Tests vs. Mechanism Tests Are Two Different Layers

**Policy tests** can use Spring Security Test to mock principals/factor authorities. They answer “given the right factor set, does authorization enforce all of them?”. However, mocking authorities **does not prove** password/WebAuthn/OTT were genuinely verified.

**Mechanism integration tests** must run end-to-end through filters/managers and factor sources: password hashes and account policies, OTT single-use/TTL/same user, WebAuthn origin/challenge/signature/RP ID, session state, and timestamps. Use a controlled test environment and never leak real tokens into logs.

### 15.2. Testing Missing Factors and Step-Up

In Spring Security 7, documentation explains that when a rule requires Password + OTT, a user missing a factor can be directed to the corresponding login endpoint. In real integration tests, test the **actual** redirect/login challenge flow; do not hardcode that every MFA failure returns HTTP 403 or that every flow redirects identically.

In particular, test switching principals between steps, OTT replay, consuming a token twice, multiple tabs, mid-flow logout, TTL expiration, and differing per-route requirements. If a test simply sets up `Authentication` with both authorities and asserts 200, you have not verified the quality of the factor-providing mechanism.

## 16. Factor Independence and Anti-Downgrade

Having **two factor labels** does not guarantee true MFA. Ask:

1. Do both mechanisms rely on the same secret or recovery channel? If an inbox is compromised, both password resets and magic links can be controlled.
2. Is the second factor bound to the **exact user, session, and transaction**? Another user's token must never complete MFA for the current account.
3. Are phishing, brute force, replay, rate limits, token forwarding, CSRF, and clickjacking appropriately mitigated for each mechanism?
4. After completion, are there time limits, device bindings, or reauthentication requirements for high-value transactions?
5. Is there a recovery path that undermines assurance? For example, supporting “forgot code so password alone works” on a payment-approval endpoint creates a bypass.
6. Can weaker auth methods like Basic, API keys, remember-me, old cookies, or non-assurance OAuth2 bearer tokens still reach the endpoint?
7. When adding another `SecurityFilterChain`, does the endpoint match the chain containing the factor rule?

**Never issue factor authorities from unverified headers or query strings.** Every factor must originate from a trusted mechanism or properly verified trusted IdP claims. Policies must fail closed when evidence is insufficient.

## 17. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Enabling only `formLogin` and `oneTimeTokenLogin` | Two login **options**, does not automatically require both | Add rules requiring all needed factors |
| Enabling `@EnableMultiFactorAuthentication` without an OTT mechanism | Users cannot supply the missing factor | Configure OTT/WebAuthn and token delivery |
| Using `authenticated()` for admin without an MFA factory | Password-only may be accepted | Use global factory or selective `mfa.hasRole(...)` |
| Using `hasAnyAuthority(PASSWORD,OTT)` | OR logic; a single factor suffices | Use AND / `requireFactors(...)` |
| Confusing `ROLE_ADMIN` with `FACTOR_PASSWORD` | Having privileges does not mean MFA was done | Check roles and factors separately |
| Adding `FACTOR_OTT` to `UserDetails` from the database | Authority granted without ever performing OTT | Issue factors only after genuine authentication |
| Ignoring `issuedAt`/freshness | Stale step-up may remain valid | Enforce `validDuration` or reliable time rules |
| Assuming email OTP and password are always independent | Shared recovery channel / phishing risk | Evaluate channel independence; consider WebAuthn |
| Using `acr`/`amr` from an unverified JWT | Forged token can bypass MFA | Verify issuer, signature, audience, time, and IdP contract |
| Copying Security 7 APIs into Security 6 | Fails to compile or misunderstands capabilities | Check version; use custom policy or upgrade |
| Testing only the “both factors → 200” happy path | Misses password-only bypasses | Negative matrix: missing/expired/mixed factors |
| Completing second factor for a different principal | Session/account confusion | Bind factor to the exact same user/session |
| Non-single-use / no-TTL OTT | Vulnerable to replay or prolonged link exposure | TTL, atomic consume, anti-replay, and rate limiting |
| Recovery mechanism skips MFA | Recovery becomes the weak auth path | Design recovery/step-up with commensurate assurance |
| Missing tenant/data permission checks | MFA completes yet wrong resources are accessed | Enforce business authorization after MFA |

## 18. Practice Exercises

1. Read the global MFA sample in section 7 and identify which lines **provide** Password/OTT and which lines **require** both factors. If you remove `@EnableMultiFactorAuthentication` while keeping both login mechanisms, how does the policy change?
2. Read the selective MFA sample in section 8. Why is `/dashboard` accessible with one factor while `/user/settings/**` requires both? If `mfa.authenticated()` is changed to `authenticated()`, what condition is lost?
3. Write a test request for a user with `ROLE_ADMIN` but only password, verifying `/admin/**` is denied. Add a valid OTT and verify success. Then test an expired OTT.
4. Implement `OneTimeTokenGenerationSuccessHandler` sending a magic link to an email retrieved from a trusted account directory; protect against `Host` spoofing, replay, TTL expiration, send floods, and token exposure in logs.
5. Design the rule `FACTOR_WEBAUTHN OR (FACTOR_PASSWORD AND FACTOR_OTT)`. Write the logical expression and explain why `hasAnyAuthority(...)` over all three factors is wrong.
6. In an existing Boot 3/Security 6 app, analyze how to build a custom authenticated MFA state/`AuthorizationManager` without using 7.x-only APIs. Highlight stale session and fake factor risks.
7. A Resource Server receives a JWT with `acr=mfa` from a trusted issuer. Identify the conditions that must be verified before accepting the token and how it differs from local `FactorGrantedAuthority`.

## 19. Summary

- **Factor-providing mechanisms** verify concrete evidence and record trusted factors on `Authentication`.
- **Factor-requiring rules** are the resource's authorization policy: which factors are needed, how AND/OR combine, how long they remain valid, and what roles/tenants/permissions apply.
- **Enabling multiple login mechanisms does not automatically enable MFA**; without authorization rules, a single mechanism may suffice to log in.
- **Setting factor-requiring rules without providing mechanisms** prevents users from completing the flow, or requires routing them through a designed step-up path.
- Spring Security **7.0+** provides `FactorGrantedAuthority`, `@EnableMultiFactorAuthentication`, and `AuthorizationManagerFactories.multiFactor()` for Servlet; Security **6.x** must manage policies/evidence within its version's capabilities.
- A factor only has value when it comes from **genuine authentication**, the exact principal, without replay, and with proper lifecycle/freshness. Business roles and authorization remain required separately.
- Test both the **providing** side (password/OTT/WebAuthn) and the **requiring** side (authorization matrix and bypass attempts).

**Official Documentation for Further Reading:**

- [Spring Security 7.0 — Multi-Factor Authentication](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/mfa.html)
- [Spring Security 7.0 — One-Time Token Login](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/onetimetoken.html)
- [Spring Security 7.0 Javadoc — FactorGrantedAuthority](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/core/authority/FactorGrantedAuthority.html)
- [Spring Security 7.0 Javadoc — EnableMultiFactorAuthentication](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/config/annotation/authorization/EnableMultiFactorAuthentication.html)
- [Spring Security — Authorization architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [OWASP Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html)
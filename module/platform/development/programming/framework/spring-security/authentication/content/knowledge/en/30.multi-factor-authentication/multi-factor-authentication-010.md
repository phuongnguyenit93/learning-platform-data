# Testing MFA: Missing Factors, Expiration, Replay, and Identity Switching in Spring Security

## 1. Why Must We Test Factor States Instead of Only “Login Succeeded”?

**Multi-Factor Authentication (MFA)** requires multiple pieces of evidence from independent factor categories, such as a password (something you know) and another possession/control method like a device-protected passkey or an OTP/OTT over a registered channel (something you have). A proper MFA system must block a sensitive request if evidence is missing, stale, reused, or belongs to **someone else**. Simply seeing HTTP 200 after a clean login does not prove any of these properties.

The scope of this article is **testing multi-factor mechanisms in Spring Security authentication** on Servlet applications, focusing on four primary failure categories:

1. **Missing factor:** the user logged in with a password but has no second-factor evidence; or has an OTT without password authentication required by policy.
2. **Expired factor:** an OTT/TOTP code exceeded its validity TTL, or the second authentication succeeded long ago while the sensitive operation requires a **recently verified** factor.
3. **Replayed factor:** an already-consumed OTT, an already-used TOTP in the same time step, a reused WebAuthn challenge/response, or two concurrent requests using the same token.
4. **Identity switching:** password authenticated for Alice while the second factor belongs to Bob, or the session switched from Alice to Bob while still “carrying over” Alice's factor authorities.

**An invariant rule:** allow an MFA-protected operation only when all required factors are **valid, sufficiently fresh, belong to the exact same account/transaction**, and have not been unlawfully consumed. The application must also check **authorization** (roles/tenant/resource ownership) after authentication passes. MFA does not automatically grant admin privileges.

### Spring Security Version Warning

- **Spring Security 7.0+ (Servlet)** adds native MFA modeling with `FactorGrantedAuthority`, `@EnableMultiFactorAuthentication`, `AuthorizationManagerFactories.multiFactor()`, and `RequiredFactor` with validity durations. Those are the APIs shown in the Spring examples.
- **Spring Security 6.x** provides authentication mechanisms such as `formLogin` and `oneTimeTokenLogin` (OTT since 6.4), but **lacks the native MFA API suite above**. Do not copy 7.x `FactorGrantedAuthority`/`@EnableMultiFactorAuthentication` imports into a 6.5 project. For 6.x, build custom MFA mechanisms or upgrade to a compatible ecosystem.
- The Spring 7.x examples require a compatible environment, e.g., **Spring Boot 4.x + Java 17+**. The standalone Java 17 section near the end does not depend on Spring and helps test principles even before upgrading.

## 2. Evidence Model: Authentication, Factors, and Policy

In Spring Security 7.x, each successful authentication mechanism can supply a `FactorGrantedAuthority` in `Authentication`. Supported values include:

| Value / Concept | Meaning | Use in Testing |
| --- | --- | --- |
| `FactorGrantedAuthority.PASSWORD_AUTHORITY` | Evidence of password mechanism, e.g., `FACTOR_PASSWORD` | Test that password alone is insufficient when policy also needs OTT |
| `FactorGrantedAuthority.OTT_AUTHORITY` | Evidence of One-Time Token mechanism, e.g., `FACTOR_OTT` | Test that OTT alone is insufficient when policy also needs password |
| `FactorGrantedAuthority.WEBAUTHN_AUTHORITY` | Evidence of WebAuthn | Test against an actually enrolled passkey credential; do not assume every device supports it |
| `FactorGrantedAuthority.getIssuedAt()` | Timestamp when factor evidence was issued | Test factors exceeding “max age” on sensitive endpoints |
| `AuthorizationManagerFactories.multiFactor()` | Builds rules combining factors | Test that only having all required factors and roles grants entry |
| `RequiredFactor.validDuration(Duration)` | Sets maximum accepted freshness for a factor on an authorization rule | Test just before and after the time boundary |

**Distinguish two types of “expiration”:**

- **Challenge/token expiry:** an OTT issued at 10:00 with a 5-minute TTL can no longer be used if unconsumed at 10:05. This applies **before** OTT evidence is successfully recorded.
- **Factor freshness:** an OTT was successfully consumed at 10:00, yet a transfer at 10:04 requires an OTT within 2 minutes. The authority may still exist in the session, but **policy must consider the factor too old**. This is an **authorization** check and cannot be inferred merely from the authority name `FACTOR_OTT`.

Similarly, an HTTP session may live for 8 hours while password proof for changing email must be fresh within 10 minutes. **Session lifetime**, **challenge TTL**, and **factor `validDuration`** are three distinct clocks.

An illustrative policy:

- `GET /dashboard`: requires only an authenticated user.
- `POST /payments/confirm`: requires password within the last 30 minutes **and** OTT within the last 2 minutes; plus permission as the transaction owner.
- `POST /admin/users/suspend`: requires `ROLE_ADMIN` + both factors within organizationally defined windows.
- Anonymous or password-only callers are directed to provide the missing factor; **never** return sensitive action results merely because the caller logged in somehow.

Spring Security 7 documentation notes that `FactorGrantedAuthority` carries `issuedAt` and policies can define different `validDuration`s per route. Never manually instantiate `SimpleGrantedAuthority("FACTOR_OTT")` to “trick” a test flow; doing so does not prove a factor was actually provided and lacks a valid timestamp.

## 3. State Diagram and Trust Boundaries

```text
[ANONYMOUS]
    | valid password for Alice
    v
[ALICE: PASSWORD_ONLY] --- GET /dashboard ---> ALLOWED (if policy allows)
    | POST /payments/confirm
    +---> DENIED / needs OTT (missing factor)
    |
    | Server issues OTT challenge for exact Alice, transaction/session
    v
[ALICE: PASSWORD_ONLY + PENDING_OTT]
    | wrong/expired/Bob's/replayed token
    +---> DENIED, do not grant FACTOR_OTT
    |
    | POST consumes valid OTT for exact Alice, one-time
    v
[ALICE: PASSWORD + OTT_VERIFIED]
    | payment within freshness windows + business permission
    +---> ALLOWED
    |
    | wait until OTT proof exceeds validDuration
    v
[ALICE: OTT_PROOF_STALE]
    +---> DENIED sensitive action / require fresh OTT
    |
    | switch principal to Bob, logout, session reset
    v
[BOB: FACTORS_CLEARED]
    +---> must not inherit Alice's password/OTT
```

**Mandatory boundary:** raw tokens/challenges from the client are **untrusted input**. The server must bind evidence to a stable account ID, project/tenant (if applicable), browser transaction/session or appropriate independent verification mechanism, expiry, single-use state, and active policy. Never use form-submitted email/display name to switch principals after another factor was already verified.

A system might not bind OTT to the exact originating browser (for instance, a magic link opened on another device), in which case there must be **clear rules**: logging in via link may establish its own authentication, without automatically adding that factor to another user's session. If attaching to an **in-progress MFA transaction**, prove the challenge belongs to that exact user/transaction. Never write code like “any valid code adds `FACTOR_OTT` to the current session”.

## 4. Mandatory Test Matrix

| ID | Given / Precondition | Action | Then / Pass Criteria |
| --- | --- | --- | --- |
| M01 | Anonymous, no factors | `POST /payments/confirm` | Payment not executed; browser routed to login, API gets appropriate denial status |
| M02 | Alice authenticated password only | Call endpoint requiring password+OTT | Must **not** return 2xx; prompted for OTT factor |
| M03 | Alice authenticated OTT only | Call endpoint requiring both factors | Must **not** return 2xx; prompted for password |
| M04 | Alice has both factors, fresh and valid | Call endpoint + right permissions | Allowed; audited properly as Alice |
| M05 | Unused OTT past TTL | Submit expired OTT | Rejected; no factor proof added |
| M06 | Valid OTT already consumed once | Resubmit same raw token | Second attempt rejected; no new session/elevation created |
| M07 | Two requests use same OTT | Concurrent POSTs with same token, two sessions | At most **one** consumption succeeds |
| M08 | Alice already verified OTP/TOTP at step X | Resubmit step X | Per anti-replay policy, rejected or treated as used; never grants proof a second time |
| M09 | Alice has OTT proof older than max age | Call endpoint requiring fresh proof | Denied even though session stays authenticated |
| M10 | Alice valid password, token issued to Bob | Submit Bob's token in Alice's flow | Rejected; no factor recorded for Alice |
| M11 | Alice completes MFA, then switches to Bob | Call sensitive endpoint in Bob's session | Prompted to re-verify; never inherits Alice's factors |
| M12 | Alice has factors, logs out, Bob logs in on same browser | Call endpoint | Does not retain old session's evidence |
| M13 | Alice has MFA, role USER | Call admin endpoint | Denied despite valid MFA (separate role/policy) |
| M14 | Expired OTT while old session still active | POST token from another browser | Rejected; no session opened |
| M15 | Request missing CSRF on form/cookie flow | POST challenge/login | Blocked by CSRF filter; no proof created |
| M16 | Tenant A's factor, similar user in Tenant B | Submit proof to Tenant B | Rejected due to stable identity/tenant mismatch |
| M17 | MFA enrollment reset/revoked or password changed | Reuse old proof per revocation policy | Revoked evidence cannot be used |
| M18 | Right factors, but request targets another user's object | Access resource | Denied by business authorization |
| M19 | Valid fresh factors, but MFA policy tightened | Access endpoint after change | Enforces current factor requirement, not stale cached result |
| M20 | Two competing tabs/requests in one session | Switch identity while OTT pending | Must never attach proof to wrong account regardless of response order |

**Testing statuses:** web apps may **302 redirect to the missing factor form**, while APIs may return 401/403 depending on authentication entry point/access-denied flow. Tests should assert **no 2xx/business side effects**, **proper challenge/redirect**, and **no factor granted**, rather than hardcoding 403 for every application.

## 5. Testing Missing Factors: Do Not Confuse Partial Authentication with Full MFA

### 5.1. Password-Only

In Spring Security 7, a user can be validly logged in with only `FACTOR_PASSWORD`. Normal `.authenticated()` rules may allow low-risk endpoints; rules requiring password + OTT must deny/redirect for completion. Never just check `SecurityContextHolder.getContext().getAuthentication() != null` and assume “MFA is satisfied”.

Test sequence:

1. Using browser/session A, open a protected route; perform a real password login POST with valid CSRF.
2. Capture the server-returned session cookie; on the next request in the same session, call `GET /dashboard`, expected to pass if policy requires only `authenticated`.
3. Call `POST /payments/confirm` without consuming an OTT—must **fail**.
4. Verify underneath: no payment database row created, no “success” email sent, no side effects produced.
5. Verify the server redirects to the OTT form or returns a factor-required error; it must never silently “add `FACTOR_OTT`” merely because the user entered a password.

### 5.2. OTT-Only

In configurations permitting OTT as the initial login method, a user can hold `FACTOR_OTT` without `FACTOR_PASSWORD`. Test the reverse direction: routes needing both must not pass, and the framework can route the user to password login. **Having two login mechanisms does not automatically create MFA**: configuring `formLogin()` and `oneTimeTokenLogin()` without a combining rule may allow logging in with **either one**.

### 5.3. Roles Do Not Substitute for Factors

A `ROLE_ADMIN` account authenticated only with a password must still provide OTT if the admin route requires MFA. Likewise, a user holding both factors without `ROLE_ADMIN` must not enter admin routes. Write two-way tests, not just “admin MFA passes”.

### 5.4. Observing the Exact Account

When asserting authenticated factors, check `Authentication.getName()` and the stable account ID. If tenant is part of identity, assert tenant ID and corresponding issuer/session. Reject test cases where MockMvc passes `@WithMockUser(authorities={"FACTOR_PASSWORD","FACTOR_OTT"})` and claims to have tested real password/OTT: that approach **mocks both factors as already satisfied** and skips authentication handlers.

## 6. Expiration: Challenge Expiry and Factor Freshness Are Two Different Test Cases

### 6.1. OTT Challenge Past TTL

Spring Security One-Time Token Login provides `OneTimeTokenService.generate(...)` and `consume(...)`. Use a code with a specific expiry, e.g., issued at 10:00:00 with a 5-minute TTL. Expectations:

- Submitted at 10:04:59 (unused): can succeed if other conditions pass.
- Submitted at or after **10:05:00**: **invalid**, produces no new factor or session.
- Link opened at 10:04 but POST login submitted at 10:05:01: must still be rejected. GET only displays the form; it **does not extend TTL**.
- Tokens must not “resurrect” if the server clock steps backward; use consistent clocks, clear skew policies, and expiry-enforcing storage.

In tests, **never use `Thread.sleep(300_000)`**. Inject a fake `Clock`, set `Instant` in a test token store, or use a controlled mutable clock to ensure determinism; if a framework service does not accept a `Clock`, use a fake/test implementation only in appropriate unit/integration tests alongside a real provider end-to-end test.

### 6.2. Stale Factor Proof

Spring Security 7.x provides `FactorGrantedAuthority.getIssuedAt()` and per-rule `validDuration`. Example test:

- Alice authenticates password at 10:00:00, OTT at 10:04:00.
- `/user/settings` requires password within 30 minutes: at 10:29 it can pass with the still-fresh password (if other factors/policies pass).
- `/payments/confirm` requires OTT within 2 minutes: at 10:06:01 it must **not execute**, even though OTT previously succeeded.
- If policy requires both factors to be fresh, refreshing only OTT when password has already expired is insufficient; the **missing/stale factor** per rule must be refreshed.

Do not confuse an **expired OTT code** with **stale OTT factor evidence**. An OTT consumed at 10:04 can no longer be reused as a code, yet the authenticated evidence may remain valid until 10:06 per policy. Conversely, an unused code past its TTL does not become valid evidence just because the server session is still alive.

### 6.3. Boundaries and Time

Test immediately before, exactly at, and immediately after the boundary. When the backend uses `Instant`/`Clock`, avoid converting timestamps to local timezones for comparison; TTL is an elapsed duration, not local calendar time. Check clock skew, multiple pods, caches, and slow requests. The condition at exact expiry is typically **`now < expiresAt`**; verify exact comparison behavior against your token service design and test explicitly.

## 7. Replay: Tokens, Time Steps, and Race Conditions

### 7.1. OTT Submitted Twice

After `POST /login/ott` successfully consumes OTT `T`, another POST carrying `T` from a fresh browser must fail. Even if a browser performs a GET on `/login/ott?token=T` and sees the form, POSTing an already-consumed `T` must never log in again. If the second test reuses the already-authenticated session cookie, it might still reach protected pages via the **prior session**; therefore always use a **separate unauthenticated browser/session** to prove token replay is truly rejected and avoid false positives.

### 7.2. Concurrent Replay

Two concurrent requests fetch OTT `T` from the DB. If the service runs `SELECT ...` then `DELETE ...` without atomic/locking primitives, both can read `T` before either deletes it. The expected invariant is **at most one successful consumption**, tested against a real database under concurrency (not just an in-memory map).

**Security advisory:** Spring published **CVE-2026-22751** (21/04/2026) affecting how applications use `JdbcOneTimeTokenService` in certain unpatched **Spring Security 6.4/6.5/7.0** releases; a TOCTOU flaw could allow one token to create multiple sessions when requests race concurrently. When deploying, use patched releases such as 6.5.10 or 7.0.5+ in those lines (6.4.16 via Enterprise Support), check your actual BOM at runtime, and **still run concurrency tests**.

### 7.3. TOTP/HOTP Replay

TOTP differs from OTT: the 6-digit code is derived from a shared seed and time step, **not a random token stored and deleted by the server**. A server may allow a ±1 step window for clock skew, yet anti-replay policy requires a **last-accepted step/counter** or replay ledger updated atomically. Otherwise, the same TOTP code could be resubmitted within the same time step and accepted again. For HOTP, track counters and block reusing old counters. Never reuse `OneTimeTokenService.consume` logic for TOTP without understanding RFC 6238/RFC 4226.

### 7.4. WebAuthn Challenge Replay

A WebAuthn authentication assertion involves a server-generated **challenge**, RP ID/origin, credential ID, authenticator signature, and other checks. Replaying an assertion for an already-used challenge or across another session/transaction must be rejected. Authenticator **sign counters** do not increment on every device; never rely solely on counters to catch all replays. The server needs random challenges, TTLs, single-use enforcement, origin/RP ID/credential binding, and signature validation.

### 7.5. Do Not Confuse Token Replay with Session Persistence After Login

Single-use OTT **does not stop the newly logged-in valid session from continuing to work** via its session cookie. A test “resending `GET /private` still returns 200” does not mean OTT was replayed: that is reusing an authenticated **session**. To test OTT single-use, you must test **re-POSTing consume for `T`** without an existing authentication.

## 8. Identity Switching: Never Mix Alice's and Bob's Factors

This failure class is dangerous because single-user “happy path” tests rarely catch it.

### 8.1. Alice's Password + Bob's Token

Example:

```text
Session S (Alice authenticated password)
  principal = account-id-alice
  FACTOR_PASSWORD issuedAt=10:00
  Alice's pending OTT challenge = T_A

Attacker/bug submits Bob's token T_B in MFA completion POST:
  T_B exists, may be unexpired, yet ownerAccountId = bob
  session/principal = alice

MANDATORY OUTCOME:
  Do not grant FACTOR_OTT to Alice.
  Do not switch principal to Bob merely because token T_B is valid.
  Do not allow sensitive endpoint.
```

When a multi-step authentication flow combines two factors, ensure **the exact same stable account ID**, and where required by design, bind the factor challenge to **transaction ID, session ID, tenant ID, and authentication epoch**. Never match by display name or uncanonicalized email input; the same `username=admin` can exist across two tenants/realms.

### 8.2. Switching Principals Mid-Flow

Alice passes password login and the app prepares OTT. In the same browser, the user logs out, logs in as Bob, or an admin uses `SwitchUserFilter` impersonation to switch users. If the app keeps Alice's `FACTOR_PASSWORD` or pending token `T_A` in the session and applies it to Bob, MFA policy can be bypassed.

Tests must prove:

- After switch/logout, Alice's factor evidence is never carried over to Bob. Reset/re-evaluate transactions, `SecurityContext`, session, and factor-related caches per policy.
- A token issued to Alice before switching cannot serve as Bob's OTT proof even if POSTed to the right endpoint.
- When switching **back to Alice**, do not assume all old proofs remain fresh: policy may require re-MFA for sensitive actions. Carefully control admin impersonation and audit both actor and subject.
- Two concurrent requests—one switching users and one consuming an OTT—must never mix factors across principals when saving results.
- If implementing “remember device” or saved authentication, this matters even more: markers must apply only to **that exact user+device+policy+expiry**, never to every account sharing the browser.

### 8.3. Distinguishing User Switch from Privilege Elevation

- **Logging in as someone else:** `Authentication.getPrincipal()` or stable account identity changes; all evidence belonging to the old user must be invalidated/re-evaluated.
- **Elevating privileges for the same user:** the principal stays Alice, yet additional proof/step-up is required for a sensitive action; factor evidence belonging to Alice can be evaluated under time policy.
- **Admin impersonation:** `SwitchUserFilter` retains original user info via `SwitchUserGrantedAuthority`, which must never count as MFA evidence for the impersonated user. Maintain dedicated policies for admin operations and privilege boundaries.
- **Login session fixation:** session IDs may rotate at login; pending tokens/transactions must follow the session lifecycle safely rather than caching an old session identifier and silently bypassing checks.

Also test the case where **Bob submits Bob's own valid email/OTP** while the active session belongs to Alice. Returning an “authenticated Bob” is not a second step for Alice; it is a different identity and must be a clean new login flow with an explicit lifecycle.

## 9. Spring Security 7 Configuration: Requiring Two Factors and Freshness

### 9.1. Simple Global Configuration

For a **Spring Boot 4.x + Spring Security 7.x + Java 17+ (Servlet/MVC)** project, the configuration below follows the official pattern. Place it in `src/main/java/com/example/mfa/GlobalMfaSecurity.java` in a project that already has `@SpringBootApplication` and Spring Web, Security, and test dependencies:

```java
package com.example.mfa;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.authorization.EnableMultiFactorAuthentication;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.authority.FactorGrantedAuthority;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
@EnableMultiFactorAuthentication(authorities = {
        FactorGrantedAuthority.PASSWORD_AUTHORITY,
        FactorGrantedAuthority.OTT_AUTHORITY
})
public class GlobalMfaSecurity {

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

This is Spring configuration code **for an existing project**, not standalone Java runnable with `javac`. You must configure a real `UserDetailsService`, password encoder, OTT delivery channel, token store, and login views. With defaults, `POST /ott/generate` issues tokens, `GET /login/ott` renders the submit page, and `POST /login/ott` consumes tokens. Enabling `oneTimeTokenLogin(Customizer.withDefaults())` alone **does not send emails**; the app needs a `OneTimeTokenGenerationSuccessHandler` delivering tokens to verified emails.

With the 7.x configuration above, Spring Security integrates `FACTOR_PASSWORD` and `FACTOR_OTT` requirements into the rules. Admin routes additionally require `ROLE_ADMIN`. When a factor is missing, the framework guides the user to the mechanism for the missing factor; actual URLs/statuses depend on entry points and UI configuration. For public endpoints, add `permitAll()` on the exact routes; never disable CSRF just to get token generation/consumption working.

### 9.2. Requiring Fresh Factors Only on Sensitive Endpoints

This example enforces a policy of **password proof no older than 30 minutes** and **OTT proof no older than 2 minutes** on payment routes, while the dashboard requires only normal authentication. Spring Security 7.x provides factory support via `RequiredFactor`; the use case uses `@EnableMultiFactorAuthentication(authorities = {})` to enable support without **enforcing** MFA globally:

```java
package com.example.mfa;

import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationManagerFactories;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.authorization.EnableMultiFactorAuthentication;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
@EnableMultiFactorAuthentication(authorities = {})
public class RecentMfaSecurity {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        var recentFactors = AuthorizationManagerFactories.multiFactor()
                .requireFactor(factor -> factor.passwordAuthority()
                        .validDuration(Duration.ofMinutes(30)))
                .requireFactor(factor -> factor.ottAuthority()
                        .validDuration(Duration.ofMinutes(2)))
                .build();

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/error").permitAll()
                .requestMatchers("/payments/**")
                    .access(recentFactors.authenticated())
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .oneTimeTokenLogin(Customizer.withDefaults());
        return http.build();
    }
}
```

**Choose only one** of the two configuration classes to run; do not let both register overlapping chains matching all requests in one app. Add business route authorization and CSRF per product requirements; Alice having fresh proofs does not mean she may transfer money from Bob's account. Note that `validDuration` checks *proof timestamp*, not the TTL of an unconsumed OTT code.

If your real project runs **Spring Security 6.5**: `@EnableMultiFactorAuthentication`, `FactorGrantedAuthority`, and `AuthorizationManagerFactories.multiFactor()` do not exist. You must build factor+freshness policies and integrate them into `AuthorizationManager`/login flows yourself, or upgrade to the compatible ecosystem. Never simulate this by adding `FACTOR_OTT` from a client-declared request parameter.

## 10. Servlet Integration Testing with MockMvc: Separating Policy Tests and End-to-End

### 10.1. Three Testing Layers with Different Goals

| Layer | How State Is Created | What It Proves | What It Does Not Prove |
| --- | --- | --- | --- |
| **Unit policy test** | Construct fake factor evidence and a controlled clock | Rules reject missing/expired/mismatched cases per check function | Does not prove real password, OTT, or WebAuthn work |
| **MockMvc filter-chain test** | `@SpringBootTest` + `@AutoConfigureMockMvc`, real POST/password and OTT logins through Spring filter chain | Sessions, CSRF, redirects, and factor authorities are created/consumed properly | Does not necessarily test real SMTP/DB/cluster if mocked |
| **Real Integration/E2E** | Browser, test SMTP, shared token DB, reverse proxy, multiple nodes | Challenges reach the right person; real replay/race/cross-user/session behavior | Still needs unit tests for exact boundary/freshness checks |

**Do not use `@WithMockUser` or `.with(user("alice"))` as proof that OTT passed**. They inject a mock authentication directly—useful for testing route authorization, yet skipping `GenerateOneTimeTokenFilter`, `OneTimeTokenService.consume`, and token delivery logic.

### 10.2. Password-Only Test Steps

In a Java JUnit/Spring Test, you can start with:

```java
// Fragment inside @SpringBootTest + @AutoConfigureMockMvc,
// with @Autowired MockMvc mvc, test UserDetailsService,
// valid password for "alice", and static imports formLogin(), get(), status().

var loginResult = mvc.perform(formLogin()
        .user("alice")
        .password("password-from-test-fixture"))
        .andReturn();

// Use the session from the login response/request, do not use @WithMockUser.
// Then GET/POST sensitive routes using this session:
// + Assert business operation was not executed;
// + Assert redirect to OTT or denial per policy,
//   do not treat every redirect status as a failure.
// Password-only must not hold both factors.
```

This is an **illustrative snippet inside a test class**; a real example needs a test password fixture, Spring Security Test static imports, and version-appropriate session handling, rather than being standalone. If a test is pre-authenticated via a helper, it may skip the exact flow under measurement.

### 10.3. Real OTT Test Steps, Without Reusing Codes

1. Register a test-only `TestOneTimeTokenGenerationSuccessHandler` that delivers magic links to an account-bound fake inbox without printing tokens.
2. Send `POST /ott/generate` with `username=alice` and a CSRF token via browser/session A; retrieve OTT `T_A` from the fake inbox.
3. `GET /login/ott?token=T_A`; verify the GET page **creates no proof**; if needed, check the DB to confirm the token is still unconsumed.
4. `POST /login/ott` with form `token=T_A` + CSRF in the proper flow; assert `Authentication.getName()=alice`, OTT factor is present, and subsequent requests carry the saved session/cookie properly.
5. Open an unauthenticated browser/session B and `POST /login/ott` with **the same `T_A`** + fresh CSRF; must be rejected and create no authentication for B.
6. Repeat with Bob's `T_B` in Alice's browser: if the flow is completing MFA for Alice, Bob's proof must never be attached to Alice. Assert principal identity after the response, not just HTTP status.
7. With a JDBC/shared store, fire two concurrent `T_A` requests from two sessions and assert **exactly one** consumption succeeds. Inspect database token state afterward.

### 10.4. MockMvc Example: CSRF/HTTP Method

In a test with `MockMvc mvc` and imports for `post`, `csrf`, and `status`:

```java
// Missing CSRF: only proves CSRF filter rejects.
mvc.perform(post("/ott/generate")
        .param("username", "alice"))
   .andExpect(status().isForbidden());

// Only with CSRF does it reach GenerateOneTimeTokenFilter.
// Specific expected status depends on custom success handler:
// mvc.perform(post("/ott/generate")
//         .with(csrf())
//         .param("username", "alice"))
//    .andExpect(status().is3xxRedirection());
```

Never use a 403 from a CSRF failure to claim “MFA rejected an expired factor”: that is a **failure at a different layer**. When testing expiry/replay, ensure CSRF is valid and the token actually reaches the authentication provider/service before asserting MFA rejection.

### 10.5. Assert Both Permissions and Side Effects

For a payment action in a test, when the request is denied assert that **the `payments` table adds no row**, no event/order is emitted, and no payment processor runs. An HTTP 302 redirect might still conceal controller execution if checked by status alone. The Spring filter chain must block **before** business side effects occur.

## 11. Standalone Java 17: Self-Contained Test Suite for All Four Failure Classes

Save as `MfaNegativeCasesDemo.java`. The example below is a **miniature MFA state model**: it simulates password evidence + second token, random nonces, TTL, freshness, atomic single-use consumption, session, and principal binding. Uses JDK 17+, with no Spring dependency. It does not verify real passwords, send OTPs/emails, or **replace** production authentication flows, databases, or Spring `SecurityContext`.

```java
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public final class MfaNegativeCasesDemo {

    private static final SecureRandom RANDOM = new SecureRandom();
    private static final Duration TOKEN_TTL = Duration.ofMinutes(5);
    private static final Duration PASSWORD_FRESH = Duration.ofMinutes(30);
    private static final Duration OTT_FRESH = Duration.ofMinutes(2);

    record Challenge(String account, String session, long epoch,
                     Instant expiresAt) {}

    // This is a single-JVM fake token store, not a database.
    private static final ConcurrentHashMap<String, Challenge> PENDING =
            new ConcurrentHashMap<>();

    static String randomToken() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }

    static boolean fresh(Instant proof, Duration maxAge, Instant now) {
        return proof != null
                && !now.isBefore(proof)
                && now.isBefore(proof.plus(maxAge));
    }

    static final class BrowserSession {
        private final String sessionId;
        private String account;
        private long epoch;
        private Instant passwordAt;
        private Instant ottAt;

        BrowserSession(String sessionId) {
            this.sessionId = sessionId;
        }

        synchronized void passwordLogin(String id, Instant now) {
            // Entering username/password of another user is an identity switch.
            if (!Objects.equals(this.account, id)) {
                this.account = id;
                this.epoch++;
                this.passwordAt = null;
                this.ottAt = null;
            }
            this.passwordAt = now;
        }

        synchronized String issueOtt(Instant now) {
            if (this.account == null) {
                throw new IllegalStateException("No account in session");
            }
            String token = randomToken();
            PENDING.put(token, new Challenge(this.account,
                    this.sessionId, this.epoch, now.plus(TOKEN_TTL)));
            return token;
        }

        synchronized boolean submitOtt(String token, Instant now) {
            Challenge proof = PENDING.get(token);
            if (proof == null
                    || !Objects.equals(proof.account(), this.account)
                    || !proof.session().equals(this.sessionId)
                    || proof.epoch() != this.epoch) {
                return false;
            }
            if (!now.isBefore(proof.expiresAt())) {
                PENDING.remove(token, proof);
                return false;
            }
            // Atomic compare-and-remove: only one request wins.
            if (!PENDING.remove(token, proof)) {
                return false;
            }
            this.ottAt = now;
            return true;
        }

        synchronized boolean canPerformSensitiveAction(Instant now) {
            return this.account != null
                    && fresh(this.passwordAt, PASSWORD_FRESH, now)
                    && fresh(this.ottAt, OTT_FRESH, now);
        }

        synchronized void switchIdentity(String nextAccount) {
            this.account = nextAccount;
            this.epoch++; // old pending challenges are no longer valid
            this.passwordAt = null;
            this.ottAt = null;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Instant t0 = Instant.parse("2026-11-06T00:00:00Z");
        BrowserSession alice = new BrowserSession("browser-A");
        alice.passwordLogin("alice", t0);

        System.out.println("missingOtt=" +
                alice.canPerformSensitiveAction(t0));

        String expired = alice.issueOtt(t0);
        System.out.println("expiredToken=" +
                alice.submitOtt(expired, t0.plusSeconds(301)));

        String valid = alice.issueOtt(t0.plusSeconds(10));
        System.out.println("validToken=" +
                alice.submitOtt(valid, t0.plusSeconds(20)));
        System.out.println("bothFresh=" +
                alice.canPerformSensitiveAction(t0.plusSeconds(21)));
        System.out.println("replay=" +
                alice.submitOtt(valid, t0.plusSeconds(22)));
        System.out.println("staleFactor=" +
                alice.canPerformSensitiveAction(t0.plusSeconds(180)));

        BrowserSession bob = new BrowserSession("browser-B");
        bob.passwordLogin("bob", t0);
        String bobsToken = bob.issueOtt(t0);
        System.out.println("otherIdentityToken=" +
                alice.submitOtt(bobsToken, t0.plusSeconds(30)));

        String alicePending = alice.issueOtt(t0.plusSeconds(30));
        alice.switchIdentity("bob");
        System.out.println("afterIdentitySwitch=" +
                alice.canPerformSensitiveAction(t0.plusSeconds(31)));
        System.out.println("oldChallengeAfterSwitch=" +
                alice.submitOtt(alicePending, t0.plusSeconds(32)));

        BrowserSession carol = new BrowserSession("browser-C");
        carol.passwordLogin("carol", t0);
        String shared = carol.issueOtt(t0);
        CountDownLatch begin = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(2);
        AtomicInteger accepted = new AtomicInteger();
        Runnable attempt = () -> {
            try {
                begin.await();
                if (carol.submitOtt(shared, t0.plusSeconds(1))) {
                    accepted.incrementAndGet();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                done.countDown();
            }
        };
        new Thread(attempt).start();
        new Thread(attempt).start();
        begin.countDown();
        done.await();
        System.out.println("concurrentSuccess=" + accepted.get());
    }
}
```

Compile and run:

```bash
javac MfaNegativeCasesDemo.java
java MfaNegativeCasesDemo
```

Expected stdout is **deterministic** because the test uses fixed timestamps and prints Booleans/counts rather than random secrets/tokens:

```text
missingOtt=false
expiredToken=false
validToken=true
bothFresh=true
replay=false
staleFactor=false
otherIdentityToken=false
afterIdentitySwitch=false
oldChallengeAfterSwitch=false
concurrentSuccess=1
```

Result explanation:

- `missingOtt=false`: even after password succeeded, sensitive policy still requires the second factor.
- `expiredToken=false` at 301 seconds: OTT exceeded its 5-minute TTL.
- `validToken=true` proves a valid token is accepted **once**; `bothFresh=true` at 21 seconds.
- `replay=false`: the deleted code cannot be submitted a second time. A replay attempt does not automatically revoke an active authenticated session; that is a separate incident-policy decision.
- `staleFactor=false` at 180 seconds: password is still within 30 minutes, yet the OTT proof from second 20 exceeded its 2-minute window.
- `otherIdentityToken=false`: Bob/session B's token cannot be added to Alice/session A's evidence.
- `afterIdentitySwitch=false`: switching principal to Bob clears both old password and OTT evidence.
- `oldChallengeAfterSwitch=false`: Alice's pending token can no longer be used for Bob in the same browser.
- `concurrentSuccess=1`: two threads submit the same token concurrently in one JVM; only one remove succeeds.

**Do not overgeneralize:** thread locking in the demo models **one session in a JVM**; multi-node/DB production must guarantee atomicity with transactions/unique constraints/conditional updates. Tokens in the demo are mapped as raw strings for readability; production should limit exposure, hash at rest, clean up expired entries, and deliver tokens securely. **The `passwordLogin` method does not verify real passwords**: it assumes a password authentication step passed and only serves to test the state machine.

## 12. Testing Identity Switching in a Real System

To avoid synthetic tests, configure fixtures with **two independent accounts** having stable IDs:

| Account | Password | Second-Factor Channel | Role / Tenant |
| --- | --- | --- | --- |
| Alice | Alice's test password | Inbox A / Credential A | `ROLE_USER`, tenant A |
| Bob | Bob's test password | Inbox B / Credential B | `ROLE_USER`, tenant B |
| Admin | Admin test password | Admin inbox / Admin passkey | `ROLE_ADMIN`, tenant A |

Specific tests:

1. Password-log in as Alice in session A; generate Alice's pending OTT.
2. Generate Bob's OTT in session B. Submit Bob's OTT in session A. Expected: **no** factor granted to Alice; do not open Bob's session as though it were step 2 for Alice. Audits must safely log a wrong-account/transaction error.
3. Alice completes MFA with Alice's OTT; assert access to Alice's resources. Switch session A to Bob via logout/login or an allowed switch-user feature, then call an MFA-required endpoint. Expected: **no** old factors apply to Bob.
4. Try submitting Alice's old pending OTT after the switch. Expected: adds no factor to Bob. If the OTP service binds only to user rather than session, tests must clearly separate whether it is a fresh login flow or step-up for the current user.
5. For `SwitchUserFilter` admin impersonation: verify only admins may switch, original authentication is managed per filter, and **factor requirements are evaluated against the appropriate principal/actor**; never treat an admin's OTT as proof for the impersonated user.
6. Log out both sessions and try replaying old fixed cookies/sessions; must never “restore” factor evidence from cache.
7. Race two requests: POST Alice's OTT and switch session to Bob, then assert the final outcome is never Bob holding Alice's OTT factor.

**Dangerous counter-example:** a request handler merely sets `session.setAttribute("mfaPassed", true)`. After switching users, the Boolean remains true and Bob can bypass MFA. If state must live in the session, store **account ID + factor type + `issuedAt` + transaction ID/epoch**, re-check on every critical operation, and clear state on logout/identity switch. In Spring Security 7, prefer built-in factor-aware authorization over ad-hoc Booleans.

## 13. Structuring Tests to Avoid False Positives

### Distinguish “Denied by MFA” from “Denied by Something Else”

When testing an expired factor, send a request with **valid CSRF**, an account with the right role, a business object with the right owner, a valid session, and a token reaching the right handler. Otherwise, the test might return 403 due to missing CSRF/role, tricking you into thinking MFA expiration is working. Assert event/log reasons (without printing secrets), token consumption, and data side effects.

### Controlled Clocks

Never use `Thread.sleep` waiting for tokens to expire in CI. Use an injectable `Clock`, fake token store, or fixed `Instant`, or adjust factor `issuedAt` in unit tests for `RequiredFactor.validDuration`. Real integration tests must verify the library version in use honors the expected clock semantics. Check `expiry.minusNanos(1)`, `expiry`, and `expiry.plusNanos(1)` where supported.

### Separate Browsers/Sessions

An already-authenticated browser might get 200 even if you resubmit a wrong link, simply because the **old session** is still valid. Always use an unauthenticated browser or separate session to test login replay. Factor-mixing tests must use **two accounts and two inboxes**, not Alice alone.

### Real Concurrency

JDBC/cluster races require concurrency at the HTTP request and DB transaction level; `synchronized` on one test object does not prove system-wide safety. Measure exact counts of new sessions and successful consumptions, not merely HTTP 302 counts. Ensure test client retry/redirect settings do not distort request counts.

### Business Side Effects

Whenever MFA fails, the system must not execute payments, change emails, or manage users. Pair “no side effects” assertions alongside HTTP response assertions. Remember role/tenant/resource ownership is separate from factor verification.

### Security Context Lifecycle

On Spring Security 6/7, a custom authentication filter that populates `SecurityContext` must still save it via `SecurityContextRepository` to persist across requests; principal changes must replace/reset state properly. Session fixation protection, concurrent session control, logout, and cache invalidation require integration tests alongside the authentication flow. Never let partial authentication be “frozen into full MFA” inside an old session.

## 14. Common Bugs and Fixes

| Symptom | Common Root Cause | How to Verify / Fix |
| --- | --- | --- |
| Password-only still enters admin endpoint | Checking only `authenticated()`/role; missing factor rule | Use Spring 7 MFA factory or custom factor-aware authorization |
| Form+OTT enabled yet two factors not required | Two mechanisms exist merely as **alternative login options** | Explicitly declare MFA requirements on routes |
| Expired OTT token still accepted | Store fails to check `expiresAt` or clock bug | Assert expired challenge at/after TTL |
| Already-consumed OTT still creates extra sessions | Non-atomic store; race in JDBC/cluster | Apply patched release and test two concurrent requests |
| GET magic link consumes token | Custom handler logs in on GET | Keep GET display-only, POST consume with CSRF |
| Authority stays valid forever despite stale factor | Checking authority name instead of `issuedAt+validDuration` | Use `RequiredFactor.validDuration` per route |
| Bob gets Alice's factors | Missing stable principal/tenant/transaction check when merging proofs | Bind proof to account+session/epoch; clear on switch |
| Replay test still returns 200 | Test reused previously authenticated session | Use a fresh session and assert token store state |
| Unit tests pass yet production fails | `@WithMockUser` skipped OTP provider and email | Run integration tests with real filters/services |
| Expiry test fails on CSRF first | Missing `csrf()` blocked request before reaching provider | Supply valid CSRF before asserting expiry |
| Token appears in logs/referrer | Full magic link query logged or leaked to third-party scripts | HTTPS, referrer policy, mask tokens, short TTL |
| MFA passes yet user reads another's data | Confusing authentication with authorization | Assert role/tenant/object ownership separately |
| Switching users still sees full MFA | `mfaPassed` Boolean stored in session | Clear/recheck factors per principal and generation |
| Multi-pod uses InMemory OTT store | Token created on A does not exist on B | Use a shared store with atomic consumption |
| Spring 6.5 fails to compile `FactorGrantedAuthority` | Native MFA APIs introduced in 7.0 | Upgrade consistently or use custom MFA policy |
| Factor `validDuration` behaves unexpectedly on route | Wrong clock/policy/window, or required factors applied globally | Compare rules, test before/after boundary and per endpoint |
| Session ID rotation loses OTP state | Session fixation migration or cookie/path mismatch | Verify session persistence, transaction binding, and redirects |
| Account locked/disabled not checked at factor 2 | Only trusting OTT token presence | Enforce account state and recheck privileges on completion |

## 15. Acceptance Checklist

An MFA system is thoroughly tested when:

- [ ] **Missing factor:** password-only and OTT-only are blocked on routes requiring two factors; public/dashboard routes follow policy.
- [ ] **Freshness:** TTL of unused codes and freshness of verified proofs are distinguished; before/at/after expiry boundaries have deterministic tests.
- [ ] **Replay:** used OTT/TOTP/challenges cannot elevate privileges again; two concurrent requests cannot both consume one.
- [ ] **Identity switching:** Alice's factors never become Bob's factors, even across session switches, logouts, impersonation, or racing requests.
- [ ] **Principal/tenant:** matches the exact stable identity of the current transaction; other users or tenants are rejected.
- [ ] **CSRF/session:** POSTs are tested with valid CSRF, proper browser cookies, and session fixation/logout/re-auth are verified separately.
- [ ] **Role/ownership:** passing MFA without required roles/resource permissions is still denied.
- [ ] **Observability:** audit events record missing/stale/replayed/mismatched attempts without logging raw OTPs/tokens/sensitive PII.
- [ ] **Spring version:** built-in examples target Spring Security 7.x; 6.x projects do not misuse 7.x APIs.
- [ ] **E2E:** real tests cover email/OTP/WebAuthn providers, shared databases, multiple instances, and concurrency.

**Encapsulated principle:** Never ask only “is the user authenticated?”—ask **“did this exact user supply all required factors, are they sufficiently fresh, never previously reused, and does the evidence belong to the exact transaction/session under inspection?”**. Then still enforce resource authorization.

### References

- [Spring Security — Multi-Factor Authentication (Servlet, Spring Security 7.x)](https://docs.spring.io/spring-security/reference/servlet/authentication/mfa.html)
- [Spring Security 7.0 — What's New (MFA support)](https://docs.spring.io/spring-security/reference/7.0/whats-new.html)
- [Spring Security API — EnableMultiFactorAuthentication (since 7.0)](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/authorization/EnableMultiFactorAuthentication.html)
- [Spring Security API — FactorGrantedAuthority](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/authority/FactorGrantedAuthority.html)
- [Spring Security API — AuthorizationManagerFactories](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationManagerFactories.html)
- [Spring Security — One-Time Token Login](https://docs.spring.io/spring-security/reference/servlet/authentication/onetimetoken.html)
- [Spring Security — Authentication Persistence / Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — MockMvc Authentication Tests](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html)
- [Spring Security — MockMvc Result Matchers](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/result-matchers.html)
- [Spring Security — SwitchUserFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/switchuser/SwitchUserFilter.html)
- [Spring Security — CVE-2026-22751 (JDBC OTT concurrent use)](https://spring.io/security/cve-2026-22751/)
- [RFC 6238 — Time-Based One-Time Password Algorithm (TOTP)](https://www.rfc-editor.org/rfc/rfc6238)
- [RFC 4226 — HOTP](https://www.rfc-editor.org/rfc/rfc4226)

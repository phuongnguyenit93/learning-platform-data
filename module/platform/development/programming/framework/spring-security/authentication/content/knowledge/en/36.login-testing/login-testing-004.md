# Testing Valid Login, Wrong Password, Locked Account, and Disabled Account

> **Topic:** Testing the username/password authentication flow in Spring Security, from `AuthenticationProvider` to filters, HTTP responses, and login sessions. The four core scenarios are **valid login**, **wrong password**, **locked account**, and **disabled account**. This lesson targets Java 17+, Spring Boot 3.x, and Spring Security 6.x Servlet; in addition to the status matrix, it covers CSRF, preventing account enumeration, sessions, security events, and infrastructure errors. The accounts/passwords below are **test data** and must never be used in production.

## 1. Learning outcomes

After this lesson, you can:

1. Distinguish successful authentication (`Authentication.isAuthenticated()`) from HTTP 200/302 responses, resource authorization, and persisting `SecurityContext` in a session.
2. Build `UserDetails` fixtures for four scenarios: enabled + right password, enabled + wrong password, `isAccountNonLocked() == false`, and `isEnabled() == false`.
3. Test properly at two layers: **provider-level** for internal results/exceptions, and **HTTP-level** through the Spring Security filter chain for real responses and sessions.
4. Use `spring-security-test`, `MockMvc`, `formLogin()`, `authenticated()`, `unauthenticated()`, CSRF tokens, and follow-up requests within the same session.
5. Understand `BadCredentialsException`, `LockedException`, and `DisabledException`; why internal reasons differ while public login must avoid username/account-state enumeration.
6. Test boundaries for temporary lockouts, long-term disablement, non-existent accounts, wrong OTP/MFA, old sessions, brute force, and repository errors so tests leave no bypass path.
7. Write trustworthy tests: isolated fixtures, encoded passwords, not merely mocking a logged-in user, meaningful assertions, and not assuming every Spring app returns the exact same response.

## 2. Real authentication model in Spring Security

With **default form login**, the flow can be visualized as:

~~~text
Browser POST /login (username, password, CSRF)
   |
   v
Spring Security FilterChain
   |
   +-- CsrfFilter: checks CSRF for POST
   |
   +-- UsernamePasswordAuthenticationFilter
             |
             +-- unauthenticated UsernamePasswordAuthenticationToken
             |
             v
       AuthenticationManager (usually ProviderManager)
             |
             v
       DaoAuthenticationProvider
             |
             +-- UserDetailsService.loadUserByUsername(...)
             +-- UserDetails account status
             +-- PasswordEncoder.matches(raw, encoded)
             +-- checks credential expiry / related policies
             |
             +-- SUCCESS: authenticated Authentication
             +-- FAILURE: AuthenticationException
   |
   +-- Success: session strategy / SecurityContext / success handler
   +-- Failure: clear failed context / failure handler / generic response
~~~

`DaoAuthenticationProvider` works with `UserDetailsService` and `PasswordEncoder`. `UsernamePasswordAuthenticationFilter` is part of the form-login Servlet chain; if using HTTP Basic, custom JSON login, OAuth2 Login, SAML, or WebFlux, the flow and HTTP statuses differ. **Do not use a `formLogin` test to claim a stateless JWT API works properly.**

Note on internal check ordering: `AbstractUserDetailsAuthenticationProvider` has **pre-authentication checks** for account state, password checks, and **post-authentication checks** for expired credentials. Spring Security patch releases may adjust how checks are executed to mitigate timing enumeration. Therefore, test each state with a **known right password**, do not rely on arbitrary exception expectations when an account is **both locked and given a wrong password**, and do not treat an older version's timing as a stable contract.

## 3. Defining the four main scenarios accurately

| Scenario | User exists? | Password | Account locked? | Enabled? | Expected result |
| --- | --- | --- | --- | --- | --- |
| A — valid login | Yes | Correct | No | Yes | Provider issues an authenticated Authentication; form login enters success flow |
| B — wrong password | Yes | Wrong | No | Yes | `BadCredentialsException` in standard provider; no authenticated session created |
| C — locked account | Yes | Correct to isolate state variable | Yes | Yes | Not authenticated; typically `LockedException` in the standard provider path |
| D — disabled account | Yes | Correct to isolate state variable | No | No | Not authenticated; typically `DisabledException` |
| E — non-existent user | No | Any | N/A | N/A | Not authenticated; public response does not confirm user existence |
| F — account expired | Yes | Correct | No | Yes but account expired | Not authenticated; distinct from disabled |
| G — credentials expired | Yes | Correct | No | Yes | Not authenticated or directed to a separate password-update flow per policy |
| H — DB/LDAP/IdP error | Unverified | Unverified | Unknown | Unknown | Infrastructure failure; not counted as wrong password and never fail-open |

Across cases A–D, **use the same valid password** for the different fixtures, e.g., `test-password-123!`, and change only *one* condition per test. That way, if C/D fail, the cause can be attributed strictly to account state rather than an accidental secret mismatch. These values exist only in test scope and must **be encoded by `PasswordEncoder`** when placed in the store.

**Do not confuse "account locked" with "account disabled":** `isAccountNonLocked=false` usually represents a lock state, potentially temporary if computed from `lockedUntil`. `isEnabled=false` represents disablement by a business/administrative decision. A temporary lock expiring must not automatically re-enable a disabled account.

## 4. Four key flags on UserDetails

Spring Security `UserDetails` exposes distinct signals:

| Method | true means | false can lead to |
| --- | --- | --- |
| `isEnabled()` | User is enabled | `DisabledException` |
| `isAccountNonLocked()` | Account is **not** locked | `LockedException` |
| `isAccountNonExpired()` | Account has not expired | `AccountExpiredException` |
| `isCredentialsNonExpired()` | Credentials (password/proof) have not expired | `CredentialsExpiredException` |

These are **evaluation conditions for an authentication attempt**, not mandatory columns in a DB table. A `UserDetailsService` may compute `isAccountNonLocked()` from `lockedUntil` and server time, or map a dedicated lock flag. When using an `InMemoryUserDetailsManager` fixture, however, you can configure `User.withUsername(...).accountLocked(true).disabled(true)` directly and keep each state independent.

**A frequent source of test bugs:** `UserDetails.isAccountNonLocked()` is not a getter named `isLocked()`. Returning false means **locked**. Similarly, `disabled(true)` on the builder causes `isEnabled() == false`. Inverting the logic causes tests to pass for accounts that should have been rejected.

### HTTP/session state is not identical to UserDetails state

- **HTTP 302** can be either a successful login redirecting to the target URL or a failed login redirecting to `/login?error`. Never assert only `status().is3xxRedirection()`.
- **HTTP 401** is common in unauthenticated Basic/Bearer APIs. Default browser form-login failures **do not necessarily return 401**; they may redirect.
- **HTTP 403** usually means authenticated but missing permission, or a POST blocked by CSRF; do not assume it means "wrong password".
- **Disabled/locked UserDetails** is checked during a new authentication; that state **does not automatically destroy all existing `HttpSession`s** unless the application implements session revocation or per-request account-state checking.
- **`SecurityContextHolder`** holds the authentication for the current execution context, while persistence across requests depends on `SecurityContextRepository`/session strategy.

## 5. Designing tests at three levels

| Testing level | Goal | Tools |
| --- | --- | --- |
| **Pure policy unit test** | Computing `lockedUntil`, disabled flag, reset/counters, clock boundaries | Java/JUnit, `Clock.fixed` |
| **Authentication provider test** | UserDetails lookup, PasswordEncoder, and exception type per account | Real `DaoAuthenticationProvider` or configured `AuthenticationManager` |
| **HTTP integration test** | CSRF, filter chain, form POST, redirects, security context, cookies/sessions, protected routes | `@SpringBootTest`, `@AutoConfigureMockMvc`, `spring-security-test` |

Do not use `@WithMockUser` or `get("/private").with(user("alice"))` to prove **passwords are verified**. These two helpers inject a pre-built principal into the test request, usually **bypassing the very `DaoAuthenticationProvider`** you need to verify. They are useful for testing authorization after authentication, not as a substitute for `formLogin()` or invoking a real `AuthenticationManager`.

**Recommended test suite structure:** For each case, clearly specify preconditions (fixture state), request/credentials, internal Authentication result, public HTTP response, session/context, and audit/counters if applicable. A test passes only when both **positive** outcomes (valid account reaches route) and **negative** outcomes (wrong/locked/disabled cannot reach route) are verified.

## 6. Dependencies and example project structure

With Maven on Spring Boot 3.x, integration tests typically require `spring-boot-starter-security`, `spring-boot-starter-web`, `spring-boot-starter-test`, and **`spring-security-test`** in test scope. The Spring Boot BOM should manage Spring library versions to avoid API drift.

The `pom.xml` snippet below is the **dependencies block** inside a Boot project that already has a parent/BOM and Java 17, not a complete Maven file:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Example project files:

~~~text
src/main/java/example/login/
    LoginTestingApplication.java
    LoginTestSecurityConfig.java
    PrivateController.java
src/test/java/example/login/
    LoginScenariosTest.java
~~~

The classes below share the `example.login` package. This is a **demo fixture using `InMemoryUserDetailsManager`**, not a production account design. When moving to a real project, replace in-memory users with proper repositories/adapters, and add MFA, account policies, rate limiting, and live session checking.

## 7. A small Spring Boot app for real HTTP testing

File `LoginTestingApplication.java`:

~~~java
package example.login;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LoginTestingApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoginTestingApplication.class, args);
    }
}
~~~

File `LoginTestSecurityConfig.java`:

~~~java
package example.login;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class LoginTestSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService testUsers(PasswordEncoder encoder) {
        UserDetails active = User.withUsername("active")
                .password(encoder.encode("test-password-123!"))
                .roles("USER")
                .build();

        UserDetails locked = User.withUsername("locked")
                .password(encoder.encode("test-password-123!"))
                .roles("USER")
                .accountLocked(true)
                .build();

        UserDetails disabled = User.withUsername("disabled")
                .password(encoder.encode("test-password-123!"))
                .roles("USER")
                .disabled(true)
                .build();

        return new InMemoryUserDetailsManager(active, locked, disabled);
    }

    @Bean
    DaoAuthenticationProvider daoProvider(UserDetailsService testUsers,
            PasswordEncoder encoder) {
        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(testUsers);
        provider.setPasswordEncoder(encoder);
        return provider;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http,
            DaoAuthenticationProvider daoProvider) throws Exception {
        return http
                .authenticationProvider(daoProvider)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/error").permitAll()
                        .anyRequest().authenticated())
                .formLogin(form -> form
                        .defaultSuccessUrl("/private", true)
                        .failureUrl("/login?error"))
                .build();
    }
}
~~~

**Why is it configured this way?**

- All three users share the same **BCrypt-encoded** test password, letting us isolate locked/disabled states. In real accounts, never hardcode passwords or secrets like this.
- `active`: defaults to enabled/non-locked/non-expired.
- `locked`: builder `accountLocked(true)` makes `isAccountNonLocked()` return false.
- `disabled`: builder `disabled(true)` makes `isEnabled()` return false.
- `DaoAuthenticationProvider` is explicitly registered with `SecurityFilterChain`; a real application must ensure no **other provider** handles username/password while bypassing policy.
- `defaultSuccessUrl("/private", true)` makes successful redirects **deterministic** for testing; `failureUrl("/login?error")` uses a generic response so locked/disabled accounts are not disclosed in public URLs.
- **CSRF remains at default**. Do not disable CSRF just to make form login tests pass. `spring-security-test`'s `formLogin()` helper automatically adds a valid CSRF token in tests.
- The demo uses Spring Security's default login page because `loginPage(...)` is not specified; no custom HTML is needed. In production, custom login pages typically include generic messages, rate limiting, CSRF, and proper UX.

File `PrivateController.java`:

~~~java
package example.login;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PrivateController {
    @GetMapping("/private")
    public String privatePage(Principal principal) {
        return "private:" + principal.getName();
    }
}
~~~

`/private` uses the authenticated identity directly from `Principal`. Testing access to it after login verifies **session continuity**, not just the POST `/login` result.

## 8. MockMvc: testing all four states actually passing through the filter chain

File `LoginScenariosTest.java` under `src/test/java/example/login/`:

~~~java
package example.login;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LoginScenariosTest {

    @Autowired
    MockMvc mvc;

    @Test
    void correctPasswordCreatesAuthenticatedSession() throws Exception {
        MvcResult result = mvc.perform(formLogin()
                        .user("active")
                        .password("test-password-123!"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/private"))
                .andExpect(authenticated().withUsername("active"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) result.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(get("/private").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("private:active"));
    }

    @Test
    void wrongPasswordDoesNotAuthenticate() throws Exception {
        mvc.perform(formLogin()
                        .user("active")
                        .password("wrong-password"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?error"))
                .andExpect(unauthenticated());
    }

    @Test
    void lockedAccountDoesNotAuthenticate() throws Exception {
        mvc.perform(formLogin()
                        .user("locked")
                        .password("test-password-123!"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?error"))
                .andExpect(unauthenticated());
    }

    @Test
    void disabledAccountDoesNotAuthenticate() throws Exception {
        mvc.perform(formLogin()
                        .user("disabled")
                        .password("test-password-123!"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?error"))
                .andExpect(unauthenticated());
    }

    @Test
    void unknownUserHasSamePublicFailureDestination()
            throws Exception {
        mvc.perform(formLogin()
                        .user("not-present")
                        .password("test-password-123!"))
                .andExpect(redirectedUrl("/login?error"))
                .andExpect(unauthenticated());
    }

    @Test
    void protectedPageWithoutLoginRedirectsToLogin()
            throws Exception {
        mvc.perform(get("/private"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrlPattern("**/login"));
    }
}
~~~

### What these tests actually prove

- `formLogin()` sends a **POST to the real login endpoint** with username/password and a valid CSRF token, unlike mocking with `@WithMockUser`.
- The valid test verifies the **redirect to /private**, `authenticated()` carrying the right username, and then **GET /private reusing the login session** returning the expected body. This is end-to-end proof inside MockMvc that the context is preserved for follow-up requests.
- The three wrong/locked/disabled tests all check the exact same public failure URL and `unauthenticated()`. This intentionally prevents clients from inferring which account is locked from the URL alone.
- The unknown-user test ensures at least **the same redirect destination** as wrong/locked/disabled; timing, response length, cookies, and side-channel testing require dedicated evaluation.
- The test does not claim that no `HttpSession` exists at all on failures, because CSRF/request cache may create an `HttpSession` without an authenticated principal. What must be asserted is **no authenticated security context** for protected routes.

**API version note:** This is integration code inside a Spring Boot 3.x + Spring Security 6.x project configured as above. `formLogin()` and result matchers come from `spring-security-test`. If your project uses another dependency version, align the BOM and imports; do not copy a Spring Security 7 method verbatim into 6.x.

## 9. Verifying internal exceptions with DaoAuthenticationProvider

HTTP form login intentionally returns a **generic failure response**. To distinguish causes in provider unit/integration tests, invoke the real provider with an unauthenticated token and assert the exception type — **this is an assertion for internal server channels, not content returned to the browser**.

You can add to the same `LoginScenariosTest.java` (inside class `LoginScenariosTest`, adding appropriate imports):

~~~java
@Autowired
org.springframework.security.authentication.dao.DaoAuthenticationProvider
        provider;

@Test
void activeWithWrongPasswordRaisesBadCredentials() {
    org.assertj.core.api.Assertions.assertThatThrownBy(() ->
            provider.authenticate(
                    org.springframework.security.authentication
                            .UsernamePasswordAuthenticationToken
                            .unauthenticated("active", "wrong-password")))
            .isInstanceOf(
                    org.springframework.security.authentication
                            .BadCredentialsException.class);
}

@Test
void lockedWithCorrectPasswordRaisesLocked() {
    org.assertj.core.api.Assertions.assertThatThrownBy(() ->
            provider.authenticate(
                    org.springframework.security.authentication
                            .UsernamePasswordAuthenticationToken
                            .unauthenticated("locked", "test-password-123!")))
            .isInstanceOf(
                    org.springframework.security.authentication
                            .LockedException.class);
}

@Test
void disabledWithCorrectPasswordRaisesDisabled() {
    org.assertj.core.api.Assertions.assertThatThrownBy(() ->
            provider.authenticate(
                    org.springframework.security.authentication
                            .UsernamePasswordAuthenticationToken
                            .unauthenticated("disabled", "test-password-123!")))
            .isInstanceOf(
                    org.springframework.security.authentication
                            .DisabledException.class);
}
~~~

**Boundary:** The expectations above apply to the fixture's standard `DaoAuthenticationProvider`, when each account has **a single failure state** and the locked/disabled cases use the correct password. If you write a custom `AuthenticationProvider`, provider chain, or user lookup, exception types may differ. In particular, never treat exception precedence for an account that is **both disabled and locked** as a business contract unless explicitly specified. First test that public state still rejects, then test internal mapping per the allowed implementation.

### Why can't you just assert `status().isUnauthorized()`?

In the configured `formLogin` flow, **401 is not the expected response for wrong-password**. The failure handler redirects to `/login?error`, so 302 + unauthenticated is the proper assertion. In a separate JSON API, 401 may be right; tests must follow **the endpoint's protocol** rather than treating form-login and Basic/Bearer HTTP codes as equivalent.

## 10. Standalone Java 17 example: simulating state decisions

The following example **is not a Spring Security implementation**; it isolates the four-state decision problem using a fixed `Instant` and a `passwordMatches` boolean representing a password-verification result already produced by a trusted component. It does not hardcode, compare, or store plaintext passwords in code, avoiding inadvertently teaching `equals` for passwords in production.

File `LoginStateDemo.java`:

~~~java
import java.time.Instant;

public final class LoginStateDemo {
    enum Verdict {
        AUTHENTICATED, BAD_CREDENTIALS, LOCKED, DISABLED
    }

    record Account(boolean enabled, Instant lockedUntil) {}

    static Verdict evaluate(Account account,
            boolean passwordMatches, Instant now) {
        if (account == null) {
            return Verdict.BAD_CREDENTIALS;
        }
        if (!account.enabled()) {
            return Verdict.DISABLED;
        }
        if (now.isBefore(account.lockedUntil())) {
            return Verdict.LOCKED;
        }
        return passwordMatches
                ? Verdict.AUTHENTICATED
                : Verdict.BAD_CREDENTIALS;
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-06T00:00:00Z");
        Account active = new Account(true, Instant.EPOCH);
        Account locked = new Account(true, now.plusSeconds(60));
        Account disabled = new Account(false, Instant.EPOCH);

        System.out.println("correct: " +
                evaluate(active, true, now));
        System.out.println("wrong password: " +
                evaluate(active, false, now));
        System.out.println("locked: " +
                evaluate(locked, true, now));
        System.out.println("disabled: " +
                evaluate(disabled, true, now));
        System.out.println("locked at deadline: " +
                evaluate(locked, true, now.plusSeconds(60)));
        System.out.println("unknown account: " +
                evaluate(null, false, now));
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac LoginStateDemo.java
java LoginStateDemo
~~~

Exact stdout:

~~~text
correct: AUTHENTICATED
wrong password: BAD_CREDENTIALS
locked: LOCKED
disabled: DISABLED
locked at deadline: AUTHENTICATED
unknown account: BAD_CREDENTIALS
~~~

**Understanding the example accurately:** `Account(enabled, lockedUntil)` is only a model **for studying state/clock**. `passwordMatches` is already the result from a trusted password verifier; the program performs no password hashing, account lookup, HTTP session, MFA, or real login. The demo policy checks disabled before locked, but does not describe mandatory Spring Security internal ordering across all versions. In a real application, use `PasswordEncoder.matches`, `UserDetailsService`, providers, and dedicated policies.

The `now == lockedUntil` boundary allows retrying login in the temporary lockout model. It does not automatically unlock an account with `isEnabled=false`, does not reset the disabled flag, and cannot replace per-account/IP retry limits.

## 11. Ensuring CSRF: tests must not disable protection just to pass

Form login uses cookie-based sessions and performs a POST affecting authentication state. Spring Security protects POSTs with CSRF by default; the `formLogin()` helper generates a valid CSRF token. If test code instead uses `post("/login").param("username",... )` without passing CSRF, you may get **403** before Spring even checks the password.

Distinguishing test:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void loginWithoutCsrfIsForbidden() throws Exception {
    mvc.perform(post("/login")
                    .param("username", "active")
                    .param("password", "test-password-123!"))
            .andExpect(status().isForbidden());
}
~~~

This snippet is **an additional method inside a test class that already has an `mvc` field**, not a standalone runnable file. It only holds for a chain retaining CSRF like the fixture above. If the framework/test setup customizes the CSRF repository, token behavior must match the actual contract.

**Common pitfall:** Developers see 403, conclude "even a valid password cannot log in", and fix the test by calling `csrf.disable()` in production. The right fix is sending valid CSRF in cookie-based flows. For JSON APIs using only Bearer tokens, the CSRF threat model differs, yet CSRF must not be disabled arbitrarily on browser endpoints.

## 12. Session continuity and consequences of account state

A valid login test that only POSTs and sees 302 still does not prove follow-up requests are authorized. You must reuse the session/cookie issued after login to call a protected endpoint and confirm `principal.getName()` or authorities are accurate.

Conversely, **wrong-password, locked, and disabled** attempts must never promote an anonymous session to authenticated. Check that:

- A generic redirect response does not prove login success.
- The `SecurityContext` of a failed request has no authenticated principal.
- A session created for CSRF or request caching (if any) **must not be mistaken for a logged-in session**.
- A browser resending an old cookie from a **previously authenticated session** is a separate case: a form-login failure does not by itself guarantee a policy revoking all prior sessions of that user.
- Check session fixation protection: after a successful login, the session ID may change (`changeSessionId()`); tests must not hardcode raw IDs.
- Logout uses the configured HTTP method/CSRF, the session is invalidated, and new requests carry no old authentication.
- Concurrency policies (`maximumSessions`), logout-all-devices, and account disablement must be tested with a session registry/shared store; flipping `isEnabled` in the DB **does not by default** destroy previously issued sessions.

**Policy example for a disabled account:** if the business requires blocking even currently open sessions, add session revocation/token invalidation or an authorization/status-checking layer on protected requests. Such tests cannot merely call `provider.authenticate(...)`, because the provider typically runs only on fresh logins.

### Scenario where a session already exists before the account is locked

When an account is locked due to external password guessing, should you invalidate active valid sessions? That is a risk decision: invalidating every session can turn the bad-password counter into a DoS tool. Distinguish **temporary login throttling** from **compromise-driven security disablement**; test each behavior per policy rather than assuming locked and disabled have the same effect on existing sessions.

## 13. Testing generic error messages and preventing username enumeration

On the backend, `BadCredentialsException`, `LockedException`, and `DisabledException` carry distinct internal meanings. However, public login should not expose information that helps an attacker confirm whether a username exists or an account is locked.

**Recommended display matrix for form login:**

| Input | Public redirect | Public message | Internal audit category |
| --- | --- | --- | --- |
| Active + wrong password | `/login?error` | "Unable to sign in" | BAD_CREDENTIALS |
| Non-existent user | `/login?error` | "Unable to sign in" | UNKNOWN_ACCOUNT (restricted visibility) |
| Locked + right password | `/login?error` | "Unable to sign in" | LOCKED |
| Disabled + right password | `/login?error` | "Unable to sign in" | DISABLED |
| DB auth store unavailable | Error boundary per policy | "Service temporarily unavailable" | INFRA_ERROR |

**Do not necessarily treat infrastructure outages with the same status as wrong passwords**: if the DB/LDAP cannot be read, fail closed and monitor system errors without incrementing the user's bad-password count. Still, the public reason for unknown/locked/disabled accounts must not reveal the username, remaining attempts, or unlock time that unauthenticated actors could exploit.

### Timing side channel and 2026 patch

Even when URLs/bodies match, differing execution paths can make response times distinguish active/disabled/locked users. Spring disclosed **CVE-2026-22746** on 2026-04-20 regarding **user attribute enumeration via timing** when `DaoAuthenticationProvider` is configured using `isEnabled`/`isAccountNonExpired`/`isAccountNonLocked`. Corresponding OSS branches were fixed in **Spring Security 6.5.10 and 7.0.5**; update to the latest patch of your active branch rather than relying on generic messages alone.

Timing tests are noisy (JIT, caches, scheduler, network, password encoder); do not write unit tests asserting `responseTimeA == responseTimeB`. Use security reviews, sound statistical benchmarks, and execution-branch inspection; never try to patch it with `Thread.sleep` on request threads because that creates a resource-exhaustion DoS risk.

Do not put full usernames/emails into high-cardinality metric logs. Internal auditing may need clear categories under RBAC/retention, but never log passwords, session cookies, OTPs, or exception messages containing secrets.

## 14. Locked vs. disabled accounts: testing different mechanisms

"Locked" has two meanings that are often conflated:

1. **Temporary lockout due to wrong passwords:** `lockedUntil`, failure count within a window, can expire automatically and decay after a valid retry.
2. **Security/administrative lock:** indicates investigation/recovery via a dedicated process; does not unlock merely because time passes.
3. **Disabled:** account deactivated by policy or organization; does not expire on a timer and is usually disallowed from creating new sessions.

The `User.accountLocked(true)` fixture illustrates state at test time, **has no clock**, and does not unlock after 60 seconds. To test lock expiration, `UserDetailsService` must compute `isAccountNonLocked` from `lockedUntil` plus an injected `Clock`, and tests must check exact boundaries. Never write `Thread.sleep(60_000)` tests that are both slow and non-deterministic.

Separately test the case where an admin disables an account while a login attempt is in flight: a success or bad-password counter reset must not overwrite the state back to ACTIVE from a stale snapshot and re-open the account improperly. Use transactions/optimistic locking to update only the counter column rather than overwriting the whole account row.

### Difficult combined cases

- **Locked + disabled:** Public result must deny; internal exception type may depend on check order, version, and policy. Do not assert precedence if the contract does not specify it.
- **Wrong password + locked:** Public result must deny; do not mandate one specific exception type across all patched Spring versions.
- **Unknown username + disabled** makes no sense; unknown is merely unverified input and must not create real account state from a request.
- **Disabled yet still holding a prior authenticated session:** access will persist without an additional session/status policy; test revocation if the product guarantees it.
- **Remember-me/SSO login:** may skip entering a new password; verify the mechanism still respects disabled state and MFA requirements per contract.
- **Temporarily locked by an attacker:** do not automatically destroy all active victim sessions, as that itself helps an attacker cause DoS.

## 15. Infrastructure errors, brute-force controls, and auditing

A good test suite must distinguish **authentication denied** from **unable to authenticate**.

| Cause | Test must record | Must NOT do |
| --- | --- | --- |
| `BadCredentialsException` | One invalid password attempt | Double-count in both provider and failure handler |
| `LockedException` | Account not allowed to try at that time | Label as "wrong password" or increment bad-password counter |
| `DisabledException` | Policy forbids login | Auto-unlock in handler when the user presents the right password |
| `UsernameNotFoundException` | No verified account | Return information confirming user existence |
| DB timeout/LDAP outage | Infrastructure failure, fail closed | Create a temporary authenticated principal or count user failures |
| Wrong MFA OTP | Separate second-factor failure | Overwrite or suppress password audit logs arbitrarily |
| Session store outage | Cannot guarantee login persistence | Report login completed when no session exists |
| Missing or invalid CSRF | 403 before password auth | Count as wrong password and lock the account |
| Rate limiter blocks before auth | 429/challenge per policy | Let the request hit the password encoder before limiting |

### Auditing with clear event categories

Record successes/failures with `attempt_id`, UTC server timestamp, safe user ref, method, category, and correlation ID. Never log raw passwords, Authorization headers, cookies, OTPs, CSRF tokens, credential hashes, or session IDs. With `AuthenticationFailureHandler` and `AuthenticationEventPublisher`, distinguish **provider-level failure** from **HTTP login failure** so metrics/audits do not double-count attempts.

Test event emission: each wrong password increments the counter once in the source of truth; locked/disabled accounts are not counted as bad-password; the final event reflects the true state. When using Spring Security test fixtures, clean up counters/rate limits between tests so one test does not unexpectedly lock another.

## 16. How REST JSON, Basic, and Bearer tests differ from form login

| Mechanism | Input | Possible failure response | Right test |
| --- | --- | --- | --- |
| Browser form login | `POST /login` + CSRF | Redirect `/login?error` | `formLogin()` + redirect + unauthenticated |
| HTTP Basic | `Authorization: Basic ...` | `401` + `WWW-Authenticate` | `httpBasic(...)`, status/authentication |
| Custom JSON login | `POST /api/auth/login` JSON | `401`/JSON error per custom controller | `post(...).contentType(...)` and policy |
| OAuth2/OIDC Login | Redirect to IdP, token/code callback | Redirect or protocol error | Integration with mock IdP, state/nonce, issuer |
| Bearer JWT Resource Server | `Authorization: Bearer ...` | `401` invalid token, `403` insufficient scope | Resource Server/JWT decoder mock and claims |
| WebFlux | reactive request/response | Per `SecurityWebFilterChain` | `WebTestClient` and reactive security config |

**Do not apply `formLogin`'s 302 expectations to a JSON API.** Conversely, testing JSON while injecting `@WithMockUser` skips password credential checks. Each authentication entry point needs its own test suite, especially when the application has multiple `SecurityFilterChain`s with different matchers or ordering.

## 17. Test mistakes that easily cause "false passes"

| Testing mistake | Why unreliable | Replacement |
| --- | --- | --- |
| `@WithMockUser("active")` to test right password | Never checks any password | `formLogin()` or real `AuthenticationManager` |
| Asserting only status 302 | Both success and failure redirect | Assert exact `redirectedUrl` and authenticated state |
| Asserting only body contains "login error" | Can return an error while keeping an old session | Check context and follow-up requests |
| Wrong password on a locked user | Fails to isolate locked state | Use the right password for locked/disabled |
| Disabling CSRF in security config to make tests pass | Alters the production threat model | Use `formLogin()`/`csrf()` |
| Calling `PasswordEncoder.matches` manually in test and concluding form login works | Skips filters, provider, session | Full-chain integration test |
| Testing locked account after brute-force test without resetting fixtures | Depends on test execution order | Fresh fixtures or state cleanup between tests |
| Asserting 401 for default form login | Wrong redirect protocol | Check 302 `/login?error` |
| Passing raw passwords from DB like real test fixtures | Leaks secrets or uses a different encoder | Encode in test-only store |
| Asserting `session == null` on login failure | CSRF/request cache may create an anonymous session | Assert unauthenticated and protected route denied |
| Skipping HTTP method/CSRF checks | 403 mistaken for password failure | Test CSRF independently |
| Omitting unknown-user test | May miss username enumeration | Same public behavior and timing review |
| Skipping session continuity | 302 success yet next request is still anonymous | GET protected endpoint with same session |
| Inverting `UserDetails.isAccountNonLocked()` | Locked user can log in | Fixture verifies non-locked flag accurately |
| Conflating disabled and expired | Wrong policy and UX | Test flags/exceptions/routes separately |
| Not checking the provider chain | Another provider might bypass state checks | Test all login entry points |
| Treating every exception as BadCredentials | Outages lock out users by mistake | Distinguish infra errors/audits |
| Relying on order/timing of one Spring version | Security patches change behavior | Test public contract, pin BOM, track advisories |

## 18. Project adoption checklist

**Fixtures, environment, and dependencies**

- [ ] Test project uses Java 17+, compatible Spring Boot/Security BOM, and `spring-security-test` in test scope.
- [ ] Active, wrong-password, locked, and disabled accounts are created independently, with test passwords encoded by the same `PasswordEncoder`.
- [ ] No production credentials, no hardcoded real secrets, and no raw passwords logged.
- [ ] Tests run inside the real `SecurityFilterChain`, not bypassed with `@WithMockUser` when password verification is required.

**Authentication and HTTP results**

- [ ] Active + correct -> right authenticated principal/roles, right success redirect.
- [ ] Active + wrong -> unauthenticated, generic failure redirect.
- [ ] Locked + correct -> unauthenticated, no full session created.
- [ ] Disabled + correct -> unauthenticated, does not auto-unlock when a cooldown ends.
- [ ] Unknown user and equivalent failure states have public responses that do not disclose account state.
- [ ] Assert internal exceptions where appropriate, without exposing messages/stack traces to browsers.
- [ ] CSRF stays intact; follow-up requests with the same session to protected endpoints behave properly.
- [ ] If MFA is present, password success does not equal full login; test pending/verified factors.

**Operability and security**

- [ ] Test account status mapping, UTC `lockedUntil`, clock boundaries, stale user caches, and concurrent updates.
- [ ] Test disabled state when a session is already active, if policy requires revocation/reauth.
- [ ] DB/LDAP/session-store errors never create an authenticated context and never count as bad passwords.
- [ ] Record accurate audit categories, avoid double-counting, and never log credentials or unnecessary PII.
- [ ] Every authentication entry point (form, Basic, API, OIDC, remember-me) has matching tests.
- [ ] Spring Security is patched against account-attribute timing advisories; review username enumeration risks beyond response bodies.
- [ ] Tests are independent, deterministic, avoid long `Thread.sleep`, and do not depend on execution order or shared Redis state.

**Conclusion:** Testing login is not merely comparing a username/password and hoping for HTTP 200. With Spring Security, you must prove **a valid password produces a real Authentication and proper session/authorization**, while **wrong passwords, locked accounts, and disabled accounts cannot create a valid login**. Errors can differ internally inside the provider for auditing, but public responses should avoid leaking identity/state; meanwhile CSRF, session continuity, MFA, clocks, rate limits, and infrastructure must each be tested as distinct boundaries.

## Official references

- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security — Testing Form Based Authentication](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/form-login.html)
- [Spring Security — MockMvc Authentication Result Matchers](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/result-matchers.html)
- [Spring Security — Setting Up MockMvc and Spring Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html)
- [Spring Security — DaoAuthenticationProvider Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html)
- [Spring — CVE-2026-22746: User Attribute Enumeration when Using DaoAuthenticationProvider](https://spring.io/security/cve-2026-22746/)
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP — Web Security Testing Guide: Testing for Weak Lock Out Mechanism](https://owasp.org/www-project-web-security-testing-guide/)
- [Java SE 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html)

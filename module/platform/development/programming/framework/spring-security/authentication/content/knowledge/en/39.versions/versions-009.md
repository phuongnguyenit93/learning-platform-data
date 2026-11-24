# Regression Test Suite for Login, Identity Persistence, and Access Revocation After Spring Security Upgrades

## 1. The Problem: The Application Still Runs, Yet Authentication Boundaries Shifted

Upgrading Spring Boot, Spring Framework, Spring Security, the servlet container, or an authentication library is more than bumping a version number. There may be zero compile errors, the login screen still returns HTTP 302, and unit tests stay green—while critical security behaviors have changed:

- `POST /login` accepts the right password yet `SecurityContext` **is not persisted**: the redirect succeeds, and the next request is treated as anonymous.
- User A logged in, yet a new request accidentally carries B’s principal because tests mocked `SecurityContextHolder` without sending proper sessions/cookies.
- Session IDs do not rotate across login; session fixation protection was lost when editing the filter chain.
- `GET /logout` begins executing logout or `POST /logout` stops requiring CSRF, creating a forced-logout vulnerability.
- Logout redirect succeeds, yet the old session is still accepted by the backend.
- Disabling an account only blocks new logins; **already-authenticated sessions** keep accessing resources because authentication sits in the HTTP session.
- The Resource Server returns 200 for a revoked access token because validators, introspection, or caches were configured differently after the upgrade.
- Old refresh tokens continue minting new access tokens after rotation or logout; nodes have not synchronized revocation state.
- A new `SecurityFilterChain` matches the wrong paths: `/api/**` runs through browser-oriented filters or vice versa.
- Tests using `@WithMockUser`/`.with(user(...))` pass, while the real authentication flow is broken.
- Browsers, reverse proxies, SSO callbacks, `SameSite` cookies, or TLS differ before vs. after the upgrade.

**Lesson focus:** build a **repeatable** regression suite comparing baseline and candidate builds across three invariants: **(1) right logins succeed and invalid ones fail; (2) identities neither vanish nor mix on subsequent requests; (3) access is revoked accurately and never resurrects**.

Examples use **Java 17, Spring Boot 3.3.12, and Spring Security Servlet** to illustrate concrete code and commands. This is a **pinned lab baseline**, not a claim that it is the latest stable release at all times. For real upgrades to other Boot/Security versions, read the migration guide **for that exact version pair** and run the same contract tests across old and new builds; never carry old BOMs/test libraries forward into a newer release when incompatible.

### 1.1. Learning Outcomes

After this lesson, you will be able to:
1. Author test matrices covering anonymous requests, bad credentials, disabled accounts, session persistence, CSRF, session fixation, logout, and account revocation.
2. Explain the roles of `SecurityContextRepository`, `SecurityContextHolderFilter`, `SessionAuthenticationStrategy`, `LogoutFilter`, and the HTTP session.
3. Write `MockMvc` tests that actually create a login session and **reuse that exact session** on subsequent requests.
4. Distinguish session `logout` from OAuth2 access tokens, refresh tokens, and SSO sessions so you never test the wrong expectations.
5. Use an illustrative revocation guard proving that disabling an account rejects **already-open sessions**.
6. Separate smoke tests, regression tests, browser/proxy E2E, multi-node tests, and negative security tests.
7. Design CI comparing baseline/candidate, storing evidence, and gating rollout/rollback.

## 2. Define Invariants Before Changing Dependencies

An **invariant** is a security property the system must preserve even as framework implementations change. Express invariants as observable API/browser outcomes rather than over-asserting internal class or filter details.

| Group | Invariant | Minimum Test |
| --- | --- | --- |
| Login | Anonymous cannot read protected endpoints | GET protected → login redirect / 401 per contract |
| Login | Valid credentials verified via real provider | Valid POST login → authenticated, success redirect |
| Login | Wrong password never creates authenticated principal | Invalid POST login → failure, no data access |
| Login | Disabled/locked account cannot log in | Form login with disabled account → failure |
| CSRF | Login/state-changing POST requires token in browser-session flows | POST login/logout/settings missing token → 403 |
| Identity persistence | Follow-up request with same session reads right user | Login → GET /me with same session → 200 + exact principal |
| Session isolation | Session A never turns into B | Two logins/browser contexts → isolated principals |
| Session fixation | Pre/post-login session IDs change | Pre-auth session ID differs from post-auth session ID |
| Authorization | Authenticated user lacking role is still blocked | USER calls ADMIN → 403 |
| Logout | POST logout + CSRF ends session | Session invalidated; next request cannot access |
| Logout | GET logout has no side effect | GET only shows confirmation; session remains valid |
| Revocation | Disabling account **blocks old sessions too** when required | Disable → old request gets 401/403, session revoked |
| Revocation | Revoked/expired/wrong-issuer/wrong-audience access tokens rejected | Invalid token → 401 |
| Revocation | Rotated/reused/revoked refresh token mints no new token | Reuse old refresh → rejected, audited |
| Multi-node | Auth and revocation consistent across LB/pods | Node switch → right identity; revoke → denied on all nodes |
| Browser | Real cookies/TLS/redirects behave properly | Browser HTTPS, Secure/HttpOnly/SameSite, cookie jar |
| Audit | Failures never leak credentials/tokens/sessions | Logs/traces redacted, request-id present |

**Matrix takeaway:** “Login returns 302” proves only one segment. Regression suites must continue to **the next request** and **the post-revocation request**.

## 3. Baseline and Candidate: Meaningful Before–After Testing

Pick two environments:
- **Baseline:** the working release prior to upgrade, including app artifact, Spring Boot/Security transitive versions, Java runtime, Tomcat, reverse proxy, and real config.
- **Candidate:** the new build with **explicitly declared** changes: dependencies, JVM, config, custom authentication code, filter chains, session repository, or gateway.

Never change multiple variables simultaneously without recording them if you need to pinpoint regression sources. Pin versions and record artifact digests; never compare two environments with mismatched test data, users, or cookie policies and blame the upgrade for breaking authentication.

### 3.1. Record the Fingerprint Before Testing

A concise report includes:

~~~text
application: authentication-service
baseline: release-X, artifact sha256 ...
candidate: release-Y, artifact sha256 ...
java: 17 (or actual runtime)
spring-boot: final resolved version
spring-security: final resolved version
servlet-container: embedded/external and version
session-store: local / JDBC / Redis / other
auth-modes: form session / bearer / SSO / Basic / remember-me
csrf: enabled for browser-session paths
public-origin: https://login.example.org
ingress/LB: image/version and forwarded-headers strategy
browser: Chromium/Firefox/WebKit per support matrix
migration-notes: references to changelog entries
~~~

Capture real dependencies:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency spring-security-web \
  --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency spring-security-config \
  --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency spring-security-test \
  --configuration testRuntimeClasspath
~~~

Without a Gradle Wrapper, you can use a local Gradle installation supported by the release. Command output varies by version; never store credentials or secret environment variables in build logs.

### 3.2. Same Contract Tests, Swapping Only the Application Artifact

Do not write tests that only run on the candidate and call that regression testing; run the **exact same test suite** against both baseline and candidate using independent test data and the same external contract.

**Approved** behavior changes should live in an explicit list—for instance, shifting anonymous API responses from login redirects to 401 JSON—verified by product/security sign-off. Avoid brittle full HTML/error-JSON snapshots that mask critical permission regressions.

Results matrix:

| Case | Baseline | Candidate | Decision |
| --- | --- | --- | --- |
| Valid login → identity at next request | PASS | PASS | Keep |
| Logout → old session rejected | PASS | FAIL | Block rollout |
| Invalid CSRF login | PASS | PASS | Keep |
| Disabled active session | NOT IMPLEMENTED | PASS | New feature, must document |
| JWT wrong audience rejected | PASS | FAIL | Block rollout |
| Login page CSS hash changed | Changed | Changed | Likely non-security |

**Never change an expected 403 into 200 just to make the candidate pass.** Every authentication, authorization, or revocation difference requires explicit review.

## 4. Why Can Upgrading Spring Security Lose Identity After a Redirect?

In Spring Security Servlet, `SecurityContextHolder` stores Authentication for the current request context. For a **subsequent** request to recover the principal, authentication must be saved and restored via `SecurityContextRepository`, typically `HttpSessionSecurityContextRepository` when using HTTP sessions.

In Spring Security 6, the migration guide emphasizes **explicit saving** for custom authentication mechanisms: `SecurityContextHolderFilter` **reads** the context from the repository, while code constructing `Authentication` in a custom filter/controller must save the context explicitly if it needs cross-request persistence.

Diagram:

~~~text
POST /custom-login
    |
    +-- AuthenticationManager.authenticate(...) -> authenticated
    |
    +-- SecurityContextHolder.setContext(context)
    |
    +-- [MISSING securityContextRepository.saveContext(...)]
    |
    v
HTTP 200 / redirect looks successful

GET /me (NEW request, same JSESSIONID)
    |
    +-- SecurityContextHolderFilter reads repository
    +-- No saved context -> anonymous
    v
302 /login or 401
~~~

Spring Security’s **default `formLogin`** mechanisms handle persistence properly; the bug occurs especially when writing custom converters, filters, or JSON login controllers that only set the ThreadLocal context.

**Proper fix in custom login** (illustrative code fragment, not a standalone controller):

~~~java
Authentication candidate =
        UsernamePasswordAuthenticationToken.unauthenticated(
                loginRequest.username(), loginRequest.password());

Authentication authenticated =
        authenticationManager.authenticate(candidate);

SecurityContext context =
        securityContextHolderStrategy.createEmptyContext();
context.setAuthentication(authenticated);
securityContextHolderStrategy.setContext(context);

// CRITICAL STEP so the next request can read the identity.
securityContextRepository.saveContext(context, request, response);
~~~

Production must also invoke `SessionAuthenticationStrategy` for session fixation/concurrent sessions, login CSRF, rate limiting, account status, and error handling; this snippet highlights only **explicit save**. Do not rewrite default Spring form login unless custom behavior is genuinely needed.

### 4.1. Session Fixation and ID Requirements

Spring Security rotates session IDs after successful authentication on modern servlet containers, typically via `changeSessionId`. Tests should capture the **pre-login ID** (from the anonymous session holding the CSRF token) and assert the **post-login ID differs**. Never print real IDs to test logs; compare in memory only. Never assume the post-login principal is verified just because the ID changed—test authentication separately.

### 4.2. Identity Persistence Does Not Mean Accepting Credentials Forever

With form login, `SecurityContext` lives in the session; if an account is disabled in the database after login, subsequent requests can still see the cached authenticated principal. That is **not automatically** a framework bug. If requirements state “disable/revoke must block open sessions within ≤N seconds”, the product must implement a strategy: session invalidation, session versioning, token versioning, revocation stores, security epochs, or per-request/bounded-TTL account status checks.

Regression tests must match **the application’s revocation SLA**, never assuming `UserDetailsService` is re-queried on every request.

## 5. Designing a Lab Project with Real Tests

We build a Spring Boot 3.3.12 / Java 17 application featuring:
- Default Spring Security HTML form login with CSRF enabled.
- User `student` with role `USER`, and `auditor` with role `USER` to test session isolation.
- Protected `GET /me` and `POST /preferences`; `GET /admin` requires `ADMIN`.
- HTTP session storing `SecurityContext` after form login.
- A lab-implemented `AccountRevocationGuard` to invalidate active sessions when `student` is disabled.
- JUnit/MockMvc tests executing real login requests and reusing `MockHttpSession`, never using `@WithMockUser` to fake login.
- A pure Java 17 demo illustrating the revocation invariant standalone without requiring a server for quick runs.

**Lesson goal:** test session and revocation *boundaries*, not build a production user-management system. `AccountState` uses an `AtomicBoolean` in a single JVM; multi-node production requires a centralized state store and clear cache-invalidation/latency bounds.

### 5.1. Source Structure

~~~text
auth-regression-lab/
├── settings.gradle
├── build.gradle
├── src/
│   ├── main/java/demo/regression/
│   │   ├── RegressionApplication.java
│   │   ├── AccountState.java
│   │   ├── AccountRevocationGuard.java
│   │   ├── SecurityConfig.java
│   │   ├── Preferences.java
│   │   └── ProtectedController.java
│   └── test/java/demo/regression/
│       └── AuthenticationRegressionTest.java
└── RevocationInvariant.java
~~~

### 5.2. Gradle Config

`settings.gradle`:

~~~groovy
rootProject.name = 'auth-regression-lab'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.12'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot dependency management resolves Spring Security along the same release line. When upgrading the candidate, bump the BOM/plugin and inspect resolved versions; never force a newer `spring-security-web` into an older Boot without compatibility review.

### 5.3. Java 17 Application

`src/main/java/demo/regression/RegressionApplication.java`:

~~~java
package demo.regression;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RegressionApplication {
    public static void main(String[] args) {
        SpringApplication.run(RegressionApplication.class, args);
    }
}
~~~

### 5.4. AccountState — Simulated Revocation State for Testing

`src/main/java/demo/regression/AccountState.java`:

~~~java
package demo.regression;

import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.stereotype.Component;

@Component
public class AccountState {
    private final AtomicBoolean disabled = new AtomicBoolean(false);

    public boolean isDisabled() {
        return disabled.get();
    }

    public void disable() {
        disabled.set(true);
    }

    public void restore() {
        disabled.set(false);
    }
}
~~~

This is **in-JVM state for a single app instance**, not a distributed revocation store. Multi-node tests must use Redis/JDBC/event policies or a real identity service and verify consistency. Depending on requirements, also audit actor, timestamp, reason, expiry, and revocation transactions.

### 5.5. Guard to Revoke Open Sessions Too

`src/main/java/demo/regression/AccountRevocationGuard.java`:

~~~java
package demo.regression;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public final class AccountRevocationGuard extends OncePerRequestFilter {

    private final AccountState state;

    public AccountRevocationGuard(AccountState state) {
        this.state = state;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();

        boolean studentSession = auth != null
                && auth.isAuthenticated()
                && !(auth instanceof AnonymousAuthenticationToken)
                && "student".equals(auth.getName());

        if (studentSession && state.isDisabled()) {
            // Revoke the EXISTING session, not only block new logins.
            HttpSession session = request.getSession(false);
            if (session != null) {
                session.invalidate();
            }
            SecurityContextHolder.clearContext();
            response.setHeader("Cache-Control", "no-store");
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        chain.doFilter(request, response);
    }
}
~~~

**How it works:** Spring Security restores the request’s context from the session before the guard runs; the guard sees principal `student` and denies access if state is disabled. It invalidates the session and returns HTTP **401** per the **lab’s own contract**. This is **not** automatic default Spring Security behavior when an admin disables an account.

**Production warnings:**
- Never track accounts with a global `AtomicBoolean`; key by stable user ID + tenant and check security epochs/revocation timestamps.
- Define cache TTL/consistency SLAs and **fail closed** when the revocation store is unavailable per your risk model. Never allow access simply because a cache/DB timed out.
- Guard against races between in-flight requests and revoke commands; test “request started after revoke committed” vs. “cancel in-flight requests”.
- Avoid creating a new session during the check: use `getSession(false)`.
- When returning 401 from a web session endpoint, real apps may redirect and clear cookies; 401 here makes revocation clear in tests.
- In distributed systems, invalidate sessions via a shared session repository or server-side revocation check rather than relying on JVM-local `HttpSession`/`AtomicBoolean`.

### 5.6. Preferences State to Verify Zero Side Effects

`src/main/java/demo/regression/Preferences.java`:

~~~java
package demo.regression;

import java.util.concurrent.atomic.AtomicReference;
import org.springframework.stereotype.Component;

@Component
public class Preferences {
    private final AtomicReference<String> theme =
            new AtomicReference<>("light");

    public String getTheme() {
        return theme.get();
    }

    public void setTheme(String value) {
        theme.set(value);
    }

    public void reset() {
        theme.set("light");
    }
}
~~~

Lab state shared in one JVM serves solely to test CSRF and side effects. Production must store settings per user/tenant with authorization and persistence.

### 5.7. SecurityFilterChain

`src/main/java/demo/regression/SecurityConfig.java`:

~~~java
package demo.regression;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder, AccountState state) {

        String studentHash = encoder.encode("student-password-123");
        String auditorHash = encoder.encode("auditor-password-123");

        return username -> {
            if ("student".equals(username)) {
                return User.withUsername("student")
                        .password(studentHash)
                        .roles("USER")
                        .disabled(state.isDisabled())
                        .build();
            }

            if ("auditor".equals(username)) {
                return User.withUsername("auditor")
                        .password(auditorHash)
                        .roles("USER")
                        .build();
            }

            throw new UsernameNotFoundException(
                    "Account not found");
        };
    }

    @Bean
    SecurityFilterChain security(
            HttpSecurity http, AccountState state) throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/health").permitAll()
                        .requestMatchers("/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .formLogin(login -> login
                        .defaultSuccessUrl("/me", true))
                .logout(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .addFilterBefore(
                        new AccountRevocationGuard(state),
                        AuthorizationFilter.class)
                .build();
    }
}
~~~

Why use only **one** filter chain? So learners clearly trace requests through login → session → guard → authorization. If a product has Bearer-only `/api/**`, configure a separate chain with explicit matchers/`@Order` and test both schemes independently. Never disable CSRF app-wide just to test login.

Spring Security’s `formLogin` handles verification and persistence for **session auth**, and `csrf` protects unsafe actions. The guard sits before `AuthorizationFilter` yet after authentication-context restoration; it **does not replace** password validation at login. `UserDetailsService` reads `state.isDisabled()` on **each new login**, while the guard checks it on every protected request in a student session.

### 5.8. Protected Endpoints

`src/main/java/demo/regression/ProtectedController.java`:

~~~java
package demo.regression;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProtectedController {

    private final Preferences preferences;

    public ProtectedController(Preferences preferences) {
        this.preferences = preferences;
    }

    @GetMapping(value = "/health",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String health() {
        return "OK";
    }

    @GetMapping("/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @GetMapping("/admin")
    public Map<String, String> admin(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @GetMapping("/preferences")
    public Map<String, String> preferences() {
        return Map.of("theme", preferences.getTheme());
    }

    @PostMapping("/preferences")
    public Map<String, String> update(
            @RequestParam String value) {
        if (value.isBlank() || value.length() > 30) {
            throw new IllegalArgumentException(
                    "Invalid value in lab");
        }

        preferences.setTheme(value);
        return Map.of("theme", preferences.getTheme());
    }
}
~~~

`/me` displays the username without returning session IDs, passwords, raw authorities, or tokens. `/admin` tests authenticated-but-forbidden access. `/preferences` is a state-changing operation requiring a CSRF token under cookie-session auth.

## 6. JUnit/MockMvc Regression Tests That Actually Traverse Login

**Common mistake:** writing `mvc.perform(get("/me").with(user("student")))` and concluding “login/session persistence works”. In reality, `user()` injects an Authentication for a single test request **without** exercising password login, CSRF, or session persistence. Use it to test **authorization**, not as proof of end-to-end login.

Spring Security Test provides `formLogin()` (submits POST login with a valid CSRF token), `logout()`, `csrf()`, and `authenticated()/unauthenticated()` result matchers. Capture `MockHttpSession` from the real login response and send it on subsequent requests to test `SecurityContextRepository`.

`src/test/java/demo/regression/AuthenticationRegressionTest.java`:

~~~java
package demo.regression;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class AuthenticationRegressionTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    AccountState account;

    @Autowired
    Preferences prefs;

    @AfterEach
    void cleanup() {
        account.restore();
        prefs.reset();
    }

    private MockHttpSession loginAs(
            String username, String password) throws Exception {
        MvcResult result = mvc.perform(formLogin()
                        .user(username)
                        .password(password))
                .andExpect(status().is3xxRedirection())
                .andExpect(authenticated().withUsername(username))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) result.getRequest().getSession(false);
        assertThat(session).isNotNull();
        return session;
    }

    @Test
    void anonymousCannotReadProtectedIdentity() throws Exception {
        mvc.perform(get("/me"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void correctPasswordCreatesAuthentication() throws Exception {
        MockHttpSession session =
                loginAs("student", "student-password-123");

        mvc.perform(get("/me").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("student"));
    }

    @Test
    void wrongPasswordNeverAuthenticates() throws Exception {
        mvc.perform(formLogin()
                        .user("student")
                        .password("wrong-password"))
                .andExpect(unauthenticated())
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void loginPostWithoutCsrfTokenIsRejected() throws Exception {
        mvc.perform(post("/login")
                        .param("username", "student")
                        .param("password", "student-password-123"))
                .andExpect(status().isForbidden());
    }

    @Test
    void securityContextSurvivesIndependentHttpRequests()
            throws Exception {

        MockHttpSession session =
                loginAs("student", "student-password-123");

        mvc.perform(get("/me").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("student"));

        mvc.perform(get("/preferences").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.theme").value("light"));
    }

    @Test
    void twoSessionsDoNotMixPrincipals() throws Exception {
        MockHttpSession first =
                loginAs("student", "student-password-123");
        MockHttpSession second =
                loginAs("auditor", "auditor-password-123");

        mvc.perform(get("/me").session(first))
                .andExpect(jsonPath("$.username").value("student"));

        mvc.perform(get("/me").session(second))
                .andExpect(jsonPath("$.username").value("auditor"));
    }

    @Test
    void roleCheckStillDeniesAuthenticatedNonAdmin()
            throws Exception {

        MockHttpSession session =
                loginAs("student", "student-password-123");

        mvc.perform(get("/admin").session(session))
                .andExpect(status().isForbidden());
    }

    @Test
    void unsafePostMissingCsrfHasNoSideEffect()
            throws Exception {

        MockHttpSession session =
                loginAs("student", "student-password-123");

        mvc.perform(post("/preferences")
                        .session(session)
                        .param("value", "dark"))
                .andExpect(status().isForbidden());

        assertThat(prefs.getTheme()).isEqualTo("light");

        mvc.perform(post("/preferences")
                        .session(session)
                        .with(csrf())
                        .param("value", "dark"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.theme").value("dark"));
    }

    @Test
    void getLogoutDoesNotImmediatelyRevokeSession()
            throws Exception {

        MockHttpSession session =
                loginAs("student", "student-password-123");

        mvc.perform(get("/logout").session(session))
                .andExpect(status().isOk());

        mvc.perform(get("/me").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("student"));
    }

    @Test
    void logoutWithoutCsrfDoesNotRevokeSession()
            throws Exception {

        MockHttpSession session =
                loginAs("student", "student-password-123");

        mvc.perform(post("/logout").session(session))
                .andExpect(status().isForbidden());

        mvc.perform(get("/me").session(session))
                .andExpect(status().isOk());
    }

    @Test
    void logoutWithCsrfInvalidatesTheSession()
            throws Exception {

        MockHttpSession session =
                loginAs("student", "student-password-123");

        mvc.perform(post("/logout")
                        .session(session)
                        .with(csrf()))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?logout"));

        assertThat(session.isInvalid()).isTrue();

        // Do not re-attach an already invalidated MockHttpSession object.
        mvc.perform(get("/me"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void disabledAccountCannotLoginAgain() throws Exception {
        account.disable();

        mvc.perform(formLogin()
                        .user("student")
                        .password("student-password-123"))
                .andExpect(unauthenticated())
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void disablingAccountRevokesAlreadyOpenSession()
            throws Exception {

        MockHttpSession oldSession =
                loginAs("student", "student-password-123");

        mvc.perform(get("/me").session(oldSession))
                .andExpect(status().isOk());

        account.disable();

        mvc.perform(get("/me").session(oldSession))
                .andExpect(status().isUnauthorized());

        assertThat(oldSession.isInvalid()).isTrue();
    }

    @Test
    void sessionIdRotatesDuringFormLogin() throws Exception {
        MvcResult page = mvc.perform(get("/login"))
                .andExpect(status().isOk())
                .andReturn();

        MockHttpSession before =
                (MockHttpSession) page.getRequest().getSession(false);
        assertThat(before).isNotNull();
        String beforeId = before.getId();

        MvcResult login = mvc.perform(post("/login")
                        .session(before)
                        .with(csrf())
                        .param("username", "student")
                        .param("password", "student-password-123"))
                .andExpect(status().is3xxRedirection())
                .andExpect(authenticated().withUsername("student"))
                .andReturn();

        MockHttpSession after =
                (MockHttpSession) login.getRequest().getSession(false);
        assertThat(after).isNotNull();
        assertThat(after.getId()).isNotEqualTo(beforeId);
    }
}
~~~

### 6.1. Reviewing the Suite Against the Three Invariants

**Login:** tests anonymous access, right/wrong passwords, missing CSRF, disabled accounts, and insufficient roles. `formLogin()` sends requests through `UsernamePasswordAuthenticationFilter` with a valid CSRF token, never assuming users appear magically.

**Identity persistence:** the helper captures `MockHttpSession` from the **real login request**. Two distinct `GET` requests with the same session must return the right principal; two distinct sessions must never mix. The fixation test compares before/after IDs without printing values.

**Revocation:** POST logout missing CSRF does not terminate the session; valid POST invalidates it. Disabling an account **with an active session** is caught by the guard, returning 401 + invalidating; this lab-implemented behavior prevents false-green tests that only block new logins.

### 6.2. Count and Expectations

The class above has **14 test methods**. Expected outcomes when the lab is set up accurately:
- 14 tests pass on Spring Boot 3.3.12 / Java 17 and a compatible embedded servlet container.
- Zero authenticated identity on anonymous or wrong-password requests.
- Post-login, sessions are reused across independent requests.
- Revoked sessions never “resurrect” on new requests.

**Accuracy note:** this is example code reviewed against Spring Security APIs; the document does not claim to have compiled or executed it live. If CI fails, inspect real stack traces/logs rather than changing expected 401/403 to 200, disabling CSRF, or switching tests to `with(user())` to mask persistence bugs.

### 6.3. What to Add When Testing Against a Real Container

`MockHttpSession` is neither a browser cookie jar nor a distributed session store. In real environments, **preserve the exact `JSESSIONID` cookie** after login and send subsequent requests via an HTTP client/browser rather than instantiating mock sessions. After logout, replay the **old** cookie against the backend/proxy—it must not authenticate. When using a distributed session repository, test across **two distinct app instances**. In MockMvc, never re-attach an invalidated `MockHttpSession` because the test object may throw instead of simulating a browser sending a stale cookie.

## 7. Running the Lab and Reading Results

Requirements: JDK 17+ and a compatible Gradle Wrapper; if no wrapper is present, install a compatible Gradle version and generate the wrapper via a separate step.

~~~bash
# Linux/macOS:
./gradlew clean test

# Windows:
# gradlew.bat clean test

# If the demo project does not yet have a Gradle Wrapper:
gradle clean test
gradle bootRun
~~~

Do not hardcode fixed Gradle stdout because test runners, dependency resolution, and environments vary. Expected behavior is that the suite passes per contract, while **actual results** exist only after the learner executes it.

### 7.1. Pure Java 17: Simulating Revocation State Without Spring

To make crystal clear that holding a valid session/token **does not** mean it lasts forever, create `RevocationInvariant.java`:

~~~java
import java.util.HashMap;
import java.util.Map;

public class RevocationInvariant {
    record Session(String id, String user, long issuedVersion) {}

    public static void main(String[] args) {
        Map<String, Long> currentVersion = new HashMap<>();
        currentVersion.put("alice", 1L);

        Session before = new Session("local-lab-id", "alice", 1L);
        System.out.println("before revoke: "
                + valid(before, currentVersion));

        // Admin decides to revoke all of alice's sessions:
        currentVersion.put("alice", 2L);
        System.out.println("after revoke: "
                + valid(before, currentVersion));

        Session fresh = new Session("new-lab-id", "alice", 2L);
        System.out.println("new session: "
                + valid(fresh, currentVersion));
    }

    private static boolean valid(
            Session session, Map<String, Long> versions) {
        Long current = versions.get(session.user());
        return current != null
                && current.longValue() == session.issuedVersion();
    }
}
~~~

Compile and run:

~~~bash
javac RevocationInvariant.java
java RevocationInvariant
~~~

Deterministic output:

~~~text
before revoke: true
after revoke: false
new session: true
~~~

Meaning: a session carries the authentication version at issuance. When a trusted source increments `authVersion`, older sessions become invalid even if cookies/session IDs remain. **This is an educational model**, not a production token-signing/session implementation: the code uses a non-thread-safe `HashMap`, fixed IDs instead of a CSPRNG, and lacks DB consistency/expiry/anti-replay. In real systems, token/session versions come from a trusted store keyed by user ID with race/cache controls—never client-asserted versions.

## 8. Upgrade Focus: Session Management Migration

Changes to review during an upgrade:

| Area | Verify Before/After | Risk |
| --- | --- | --- |
| `SecurityContextHolderFilter` | When context is read, who saves it, cleared at request end | User logs in yet next request turns anonymous |
| `SecurityContextRepository` | HttpSession / RequestAttribute / Delegating / Null | Sessions suddenly stateful/stateless |
| `requireExplicitSave` | Do custom logins call `saveContext` | Persistence silently breaks after upgrade |
| `SessionAuthenticationStrategy` | Called on success; fixation, concurrent sessions | Old session ID reused |
| `sessionCreationPolicy` | `IF_REQUIRED` / `ALWAYS` / `NEVER` / `STATELESS` | Unintended excess sessions or auth never saved |
| `LogoutFilter` | POST + CSRF, invalidates session/context/repository | Logout redirects yet privileges remain unrevoked |
| `AuthorizationFilter` | Matchers/methods and order | Protected paths turn public |
| `ExceptionTranslationFilter` | Anonymous vs. authenticated denied, entry point | Wrong 401/403/302 hides failures |
| `CsrfFilter` | Token repo, handler, SPA rotation after login/logout | Login CSRF, unsafe POST bypass |
| `UserDetailsService`/provider | Disabled/locked/password encoder | Grants auth to invalid account states |
| Remember-me | Cookie/token persistence, theft/replay, logout cleanup | Auto-relogin after logout |
| OAuth2 Resource Server | JWT decoder/introspection validation, scopes/aud/iss | Invalid tokens still accepted |
| Session store | Redis/JDBC serialization/TTL/spring-session versions | Sessions lost during rolling deploys |
| Proxy/cookies | Forwarded HTTPS, Secure/SameSite/Domain | Browsers drop sessions or send wrong scope |

### 8.1. Example of a New Test Catching Upgrade-Induced Persistence Loss

A misleading test:

~~~java
// Illustrative only: DOES NOT prove real login.
mvc.perform(get("/me").with(user("student")))
   .andExpect(status().isOk());
~~~

Right test:

~~~java
// Illustrative fragment inside @SpringBootTest + @AutoConfigureMockMvc:
MvcResult login = mvc.perform(formLogin()
        .user("student").password("student-password-123"))
    .andExpect(authenticated().withUsername("student"))
    .andReturn();

MockHttpSession session =
    (MockHttpSession) login.getRequest().getSession(false);

mvc.perform(get("/me").session(session))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.username").value("student"));
~~~

If a custom auth filter sets `SecurityContextHolder` without calling `saveContext`, the second test catches the regression even while the first test always stays green. This is a crucial regression test when moving Spring Security 5→6 or redesigning JSON login flows.

### 8.2. When Multiple SecurityFilterChains Exist

Suppose a system has:
- `/web/**` using session cookies, form login/CSRF.
- `/api/**` using OAuth2 Bearer, stateless.
- `/actuator/health` public while admin endpoints require roles.
- OIDC/SAML callbacks following separate protocols.

On upgrade, test matcher precedence and filter selection:
1. Session cookies **never** accidentally authenticate Bearer-only API endpoints.
2. Bearer tokens never accidentally trigger login-page redirects for APIs.
3. `/admin/**` is never shadowed by a `permitAll` chain above it.
4. CORS and CSRF exceptions apply **only to the exact endpoints/protocols** requiring them.
5. Form session persistence is not broken by `NullSecurityContextRepository` from an API chain.
6. Sending cookies and Bearer together never picks an out-of-contract mechanism.

Use explicit `@Order` + `securityMatcher`; regression tests should assert response status, principal, and headers per route contract rather than pinning internal filter names (which can change across framework upgrades).

## 9. Logout Does Not Mean Revoking Every Token

With **session-based form login**, Spring Security’s default `POST /logout` invalidates the HTTP session, clears `SecurityContext`, and clears CSRF tokens/remember-me state accordingly. It **does not** by default revoke every access token held by clients, log out all other browsers, or terminate external IdP SSO sessions.

Especially with OAuth2:
- **Self-contained JWT access tokens** still within expiry continue passing resource-server checks that only verify signatures/`exp`/`iss`/`aud` without checking denylists, `authVersion`, `jti`, or session bindings.
- **Opaque tokens** can be blocked via introspection when the AS marks `active=false`, yet gateway/RS caches can extend validity until TTL expiry.
- **Refresh tokens** typically require rotation and revocation at the authorization server; revoking a refresh token does not necessarily invalidate existing JWT access tokens immediately.
- **OIDC/SAML login sessions** at the IdP represent distinct state from local app sessions; back-channel/front-channel logout, state/correlation, and session mappings must be tested per protocol.

**Regression criteria must state explicit revocation SLAs**: for example, “local session rejected immediately on the request after logout”; “opaque token rejected within at most N seconds per cache TTL”; “JWT may remain valid until exp if policy permits”. If **immediate JWT revocation** is required, design dedicated validation/revocation architecture rather than assuming `SecurityContextLogoutHandler` does it.

### 9.1. Bearer/Refresh Token Matrix Needed in Practice

| Test | Setup | Expected |
| --- | --- | --- |
| No Bearer token | GET protected API without Authorization | 401 + Bearer challenge |
| Expired access token | Fixed clock past `exp` | 401, never reaches controller |
| Not-yet-valid | `nbf` in the future | 401 |
| Wrong issuer | `iss` outside trust allowlist | 401 |
| Wrong audience | `aud` not targeting this API | 401 per custom audience validation |
| Invalid signature/`alg` | Forged token | 401 |
| Missing scope | Valid token lacking authority | 403 |
| Revoked opaque token | AS/introspection `active=false` | 401 within cache TTL bound |
| Revoked JWT | `jti` denylist/authVersion updated | 401 **if** RS actually checks revocation |
| Refresh rotation | Old refresh token reused | Rejected, token family handled per policy |
| Concurrent refresh | Two requests race with one refresh token | One transaction wins, reuse detected |
| Logout | Local session ended | Local session unusable; Bearer tested separately |
| Clock skew | Timestamp near exp/nbf | Only configured skew accepted, not unbounded |
| Cross-tenant token | Valid scope yet wrong tenant | 403/404, zero data leak |

### 9.2. Pseudo-Test Example for Token Revocation (Not Claimed as Spring Default)

~~~java
// Contract test pseudocode for a Resource Server.
// Not a standalone @Test class: requires JwtDecoder,
// Authorization Server/test issuer, and a real revocation store.
//
// String token = tokenFactory.issue("user-1", "api.read");
// assertThat(api.get("/api/me", token).status()).isEqualTo(200);
// revocationService.revokeByJti(tokenJti(token));
// eventuallyWithin(Duration.ofSeconds(2), () ->
//     assertThat(api.get("/api/me", token).status()).isEqualTo(401));
~~~

If the organization **lacks** a `jti` denylist or token-version check, never write fake tests demanding immediate JWT revocation on logout. In that case, policy relies on short-lived access tokens, refresh revocation, and documented exposure windows—or else redesigns architecture to meet the SLA. When immediate revocation is required, **build and verify the mechanism rather than tweaking an HTTP status in a test**.

## 10. Browser Regression: Do Not Test Only with MockMvc

An app can pass MockMvc session tests yet fail in real browsers:
- `SameSite=None` cookies missing `Secure` are rejected.
- Nginx terminates TLS, yet the app redirects to HTTP due to misconfigured forwarded headers.
- A host-only cookie widens `Domain` in a new commit.
- `HttpOnly` gets disabled so the frontend can read the session, increasing XSS risk.
- An SPA uses a stale CSRF token after login/logout, causing subsequent POSTs to 403.
- Multiple browser tabs share a cookie, and logging out in tab A must affect tab B in the same session.
- IdP callbacks use top-level POSTs and `SameSite` policy blocks correlation cookies.
- DevTools/browser storage state holds pre-upgrade sessions that fail to deserialize after upgrade.

### 10.1. Playwright Regression Skeleton

The test below is an **integratable test fragment** for an already-configured HTTPS staging environment, not standalone code for the MockMvc project in section 5 (which only builds an HTTP session lab without Nginx/TLS containers). Point `BASE_URL` in CI to a real HTTPS origin with certificate verification enabled (never ignore errors).

~~~javascript
import { test, expect } from "@playwright/test";

const BASE = process.env.BASE_URL;

test("login cookie survives next request, logout revokes", async ({
  page, context
}) => {
  if (!BASE) throw new Error("BASE_URL is required");

  await page.goto(BASE + "/login");
  await page.locator('input[name="username"]').fill("student");
  await page.locator('input[name="password"]').fill(
    process.env.LAB_USER_PASSWORD);
  await page.locator('button[type="submit"]').click();

  await expect(page).toHaveURL(BASE + "/me");

  const cookie = (await context.cookies(BASE))
    .find(c => c.name === "JSESSIONID");
  expect(cookie).toBeDefined();
  expect(cookie.httpOnly).toBe(true);
  expect(cookie.secure).toBe(true);

  // A new request in the SAME browser context.
  await page.reload();
  await expect(page.locator("body")).toContainText("student");

  await page.goto(BASE + "/logout");
  await page.locator('form[action="/logout"] button').click();

  await page.goto(BASE + "/me");
  await expect(page).toHaveURL(/\/login/);
});
~~~

To use this skeleton, you need a Playwright config/test runner, `BASE_URL`, a test account, and matching login/logout page behavior. Before production use, never log passwords, save session storage-state, or enable `ignoreHTTPSErrors:true`. Browser tests complement MockMvc with a **real cookie jar and TLS**, rather than simulating `SameSite` via request API clients.

### 10.2. Two Browser Contexts and Logging Out One Session

If a user has multiple devices/sessions:
- Browser A logs in → session A.
- Browser B logs in → session B.
- Logging out A **normally only** ends A, not necessarily B.
- Only a **logout-all-devices** feature must revoke both; tests follow product contracts.
- Account disable/forced revocation must affect both A and B within the product’s committed SLA.
- Cookies carry accurate `Secure/HttpOnly/SameSite/Path/Domain` flags; never rely solely on `document.cookie` since `HttpOnly` blocks JS reads.

Never write “logging out A must log out B” when the product only provides local logout, as that tests the wrong expectation.

## 11. Multi-Node / Session Store / Rolling Deployments

In a multi-pod deployment:

~~~text
Login  -> load-balancer -> app-A -> writes session S to Redis
GET /me -> load-balancer -> app-B -> reads session S from Redis
Disable account -> service updates revocation state
GET /me -> load-balancer -> app-C -> must deny per SLA
Logout -> app-B invalidates S; app-A/app-C must not resurrect S
~~~

The test suite should:
1. Force login and the follow-up request onto **different nodes** to confirm `SecurityContext` deserializes/restores.
2. Verify session rotation after login so the old ID loses access.
3. Upgrade nodes one by one in a rolling upgrade (mixed versions), verifying session serialization compatibility or explicit re-login policy.
4. Revoke a session via node A and replay the old cookie against nodes B/C; it must be denied within the committed consistency window.
5. Evaluate Redis/JDBC TTLs, cache invalidation, persistence, session expiration events, and store failover.
6. When the revocation store loses connectivity, confirm the app fails closed/times out safely rather than silently bypassing.
7. Run concurrent login/logout/disable across threads/nodes; verify races never restore privileges.
8. Test upgrade followed by rollback: can the older release read the new session format? If not, plan safe drain/re-authentication.
9. Ensure audits never log raw session IDs, JWTs, passwords, or refresh tokens.

**Never call a unit test using `ConcurrentHashMap` a multi-node test.** Use at least two app instances backed by a real session/revocation store or Testcontainers with full networking.

### 11.1. Testing Exact “Revoked” Rules Under Races

Define the **commit point** of a revocation command. For example:
- Whether a request started **before** revocation commits may finish depends on business requirements.
- Requests started **after** commit must be blocked within SLA (immediately or after published cache TTL).
- Never allow a post-revocation write request to succeed merely because the session authenticated earlier.
- Use transactions, token/session versions, cache invalidation, and audits with reliable timestamps/IDs.
- Avoid `Thread.sleep(5000)` to wait out revocation TTLs if CI is flaky; inject `Clock` or use bounded polling and record measured elapsed time.

## 12. Common Post-Upgrade Regressions

| Symptom | Typical Root Cause | Guarding Test |
| --- | --- | --- |
| Login succeeds then `/me` returns 302 | Custom login never saved context | Real login → new request with same session |
| `/me` always 200 in tests | Tests use `@WithMockUser`, skipping login | Separate authentication integration tests |
| Session ID never rotates | Session fixation strategy/filter mismatch | Compare pre/post IDs |
| GET logout executes logout | CSRF disabled or GET matcher altered | GET confirmation + session stays usable |
| POST logout missing token still 302 succeeds | Unintentional CSRF ignore | Negative CSRF test |
| Old cookie still works after logout | Repo never cleared/invalidated, proxy session cache | Replay old cookie via real HTTP client |
| Disabled user’s old session still reads `/me` | Only checked `UserDetails` at login, no live revocation | Disable after login then retry old session |
| Cookie-authenticated API reaches Bearer-only endpoint | Wrong chain matcher/order | Token/cookie isolation tests |
| JWT with wrong `aud`/`iss` still accepted | Decoder validators dropped in config | Issuer/audience negative tests |
| Expired JWT still returns 200 | Clock/skew/cache validator regression | Fixed `Clock` + exp tests |
| Old refresh token still works | Token family rotation/reuse detection broken | Concurrent refresh tests |
| Node A OK, node B unauthorized | Different session store/serialization | Cross-node test |
| Candidate login fails only in browsers | Cookie flags/forwarding/SPA CSRF changed | HTTPS Playwright E2E |
| Wrong 401 vs. 403 status | Entry point/denied handler changed | Per-scheme contract tests |
| Two users’ sessions mix | ThreadLocal/session leak or test reuse | Two-session isolation test |
| Admin endpoint becomes public | Overly broad `permitAll`/chain priority | Anonymous forbidden + role tests |
| Remember-me re-logs in after logout | `RememberMeServices`/cookie cleanup changed | Logout remember-me regression |
| Build green yet prod fails | Test libraries and runtime use different BOMs | `dependencyInsight` + artifact fingerprint |

## 13. Why Should Tests Avoid Over-Coupling to Implementation Details?

A regression test should assert:
- HTTP status/redirects per the public API contract.
- Principal on **subsequent requests**.
- Session ID rotation and `HttpOnly`/`Secure` flags.
- Zero side effects after 403/401.
- Revoked sessions/tokens lose access.
- Authorization, method, and tenant isolation.

It does not need to assert:
- Every filter sitting at an exact internal index when framework internals evolve.
- `SecurityContextHolderFilter` remaining the sole class name across every release line when only external behavior matters.
- Specific password hashes matching byte-for-byte after encoder upgrades (salts/algorithms evolve; correctness is `matches` and migration).
- Brittle full-HTML login snapshots, CSRF token strings, or random cookie IDs.
- Exact millisecond CI response times.
- Stack trace or exception text wording that can change without breaking contracts.

Implementation details can be checked in a dedicated **architecture test** when there is a clear security rationale, while rollout gates should prioritize critical invariants.

## 14. CI Gate, Reporting, and Rollback Strategy

Suggested pipeline:

~~~text
Resolve dependencies + SBOM + advisory scan
   |
   v
Unit tests / password and account-state tests
   |
   v
Spring Security MockMvc regression tests
   |
   v
Build immutable candidate image
   |
   v
Deploy ephemeral HTTPS + proxy + session store
   |
   v
Browser E2E + cross-node/revocation cases
   |
   v
Compare baseline / candidate contract results
   |
   +-- FAIL: stop promotion, capture redacted evidence, investigate
   |
   +-- PASS: staged rollout/canary, monitor auth error and session metrics
   |
   v
Release / rollback plan with session compatibility verified
~~~

**Typical mandatory gates:** anonymous blocked from protected endpoints, invalid credentials rejected, context restored, session fixation active, CSRF on logout, logout revokes, revoked tokens/disabled sessions blocked per contract, and zero privilege escalation.

Post-rollout, monitor:
- Login success/failure rates grouped by reason (never log passwords).
- Session creations/invalidations and abnormal re-login loops.
- 401/403/302 shifts by route and user-agent.
- Unusual CSRF failures after SPA/frontend deployments.
- Redis/JDBC session read/write errors and deserialization exceptions.
- Aggregated JWT validation failures by category (issuer/audience/exp/scope), never logging raw tokens.
- Logout/revocation propagation latency against SLOs.

**Never auto-rollback based on a single raw metric** if doing so could log out all users or reintroduce a patched CVE. Evaluate session format/downgrade impact, revocation-store schemas, token signing keys, and data differences between baseline and candidate.

### 14.1. Regression Report Format

~~~text
Suite: auth-upgrade-regression
Candidate: <release, digest, Boot/Security/Java versions>
Baseline: <release, digest>
Environment: <proxy/TLS, session store, browser, nodes>
Tests:
  LOGIN-01 anonymous denied: PASS/FAIL
  LOGIN-02 correct password: PASS/FAIL
  LOGIN-03 bad/disabled password: PASS/FAIL
  CONTEXT-01 persisted across requests: PASS/FAIL
  SESSION-01 fixation rotated: PASS/FAIL
  SESSION-02 two identities isolated: PASS/FAIL
  CSRF-01 unsafe POST without token denied: PASS/FAIL
  LOGOUT-01 GET no side effect: PASS/FAIL
  LOGOUT-02 POST invalidates session: PASS/FAIL
  REVOKE-01 disabled live session denied: PASS/FAIL
  TOKEN-01 expired/wrong audience/issuer denied: PASS/FAIL
  TOKEN-02 refresh family revocation: PASS/FAIL
  HA-01 cross-node session and revocation: PASS/FAIL
Regressions:
  - ID, expected, actual, severity, owner, link to redacted log
Decision:
  - promote / hold / rollback (approved)
~~~

Never store cookies/session tokens, raw Authorization headers, private keys, refresh tokens, CSRF tokens, or passwords in CI artifacts. Even E2E traces for test accounts can carry credentials; enforce redaction, access control, and retention limits.

## 15. Post-Upgrade Reasoning Exercises

**Q1.** `POST /login` returns 302 and `authenticated()` passes, yet `GET /me` with the same session redirects 302. What are the likely causes?  
**Answer:** Custom login code may only set `SecurityContextHolder` without saving via `SecurityContextRepository`; or the browser did not send the cookie, or the session store failed to read it. Isolate using MockMvc session persistence and browser/proxy tests.

**Q2.** A test with `.with(user("alice"))` on `/me` passes. Does that prove login works?  
**Answer:** No. It injects a mock principal for that single request, bypassing password authentication, session fixation, and persistence.

**Q3.** An account is disabled in the DB, yet an old session still reads the API. Is default Spring Security buggy?  
**Answer:** Not necessarily. The session cached the Authentication; if the product requires revoking live sessions, implement a revocation mechanism and test post-disable behavior.

**Q4.** POST logout has CSRF and redirects to `/login?logout`, yet the browser still calls the API using an old JWT. Is logout broken?  
**Answer:** Not necessarily. Local session logout does not automatically revoke independent access JWTs; verify against your token revocation SLA and architecture.

**Q5.** A JWT has a valid signature, yet its `aud` belongs to a different API. Should it return `403 insufficient_scope`?  
**Answer:** No. The token is invalid for this resource and must fail authentication (typically 401).

**Q6.** After upgrading, session-based API calls succeed on node A yet fail on node B. What test is missing?  
**Answer:** **Cross-node session store/serialization tests**, covering rolling upgrades, shared session data, TTLs, and persistence.

**Q7.** Should logging out in tab A end tab B’s session?  
**Answer:** **If both share the same browser session cookie, usually yes.** However, logging out one device does not automatically log out every device; distinguish same-session logout from logout-all.

**Q8.** Login succeeds yet a subsequent POST returns 403. Does that mean the session was not saved?  
**Answer:** Not necessarily. Session auth may be intact while the CSRF token rotated after login or was missing; test `GET /me` and inspect token vs. session separately.

**Q9.** Is a test using `Thread.sleep(2000)` to wait for JWT expiration reliable?  
**Answer:** **Poor practice.** Inject `Clock`, test `exp`/`nbf`/skew deterministically, and use bounded eventual assertions in distributed setups.

**Q10.** Can you fix a regression by changing all expected 401/403 statuses to 200?  
**Answer:** **No.** That could mask privilege escalation; security contract changes must be reviewed, never “relaxed” in tests to pass.

## 16. Checklist Before Approving an Upgrade

- [ ] Ran the same auth regression suite on baseline and candidate; recorded versions and artifact digests.
- [ ] Tested real logins through providers, not only `@WithMockUser`.
- [ ] Anonymous requests, wrong credentials, and disabled accounts are all rejected.
- [ ] Successfully logged-in users are restored on a **new** request using the same session.
- [ ] Sessions A and B never mix principals; role/tenant checks remain intact.
- [ ] Session ID rotates after login, preventing fixation.
- [ ] CSRF is enabled on unsafe browser-session requests, including login and logout.
- [ ] GET logout changes no state; POST logout with CSRF invalidates the session.
- [ ] Browsers use real cookies over HTTPS; Secure/HttpOnly/SameSite/Path/Domain match policy.
- [ ] Disabling/force-revoking an account blocks open sessions within the product’s SLA.
- [ ] JWT/opaque/refresh tokens have dedicated revocation tests independent of local logout.
- [ ] Issuer/audience/expiry/scopes, clock skew, and token replay are all tested.
- [ ] Multi-node/shared sessions/rolling deploys/rollbacks preserve session serialization compatibility.
- [ ] No filter chain matcher accidentally exposes protected routes.
- [ ] Tests never leak passwords, sessions/cookies, CSRF tokens, access/refresh tokens, or private keys.
- [ ] CI gates, owners, canary metrics, and a safe rollback plan are in place.

## 17. Learning Resources

- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): `SecurityContextRepository`, explicit save, session fixation, concurrent sessions.
- [Spring Security 6.5 — Session Management Migration](https://docs.spring.io/spring-security/reference/6.5/migration/servlet/session-management.html): persistence changes across releases.
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): `UsernamePasswordAuthenticationFilter`, login redirects, and failures.
- [Spring Security 6.5 — Handling Logouts](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html): session/context invalidation, GET confirmation, POST logout.
- [Spring Security — MockMvc Form Login Tests](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/form-login.html): `formLogin()` sending valid CSRF tokens.
- [Spring Security — MockMvc Logout Tests](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/logout.html): logout request post-processors.
- [Spring Security — MockMvc Result Matchers](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/result-matchers.html): `authenticated()`, `unauthenticated()`.
- [Spring Security — MockMvc Setup](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html): `springSecurity()` and the filter chain.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): signature/issuer/exp/nbf and custom validation.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): cookies, session fixation, invalidation, timeouts.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): credential validation, generic errors, throttling.
- [OWASP — OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): authorization/token security recommendations.

**Conclusion:** Post-upgrade Spring Security regression **is not a single login test returning 302**. The suite must prove the complete chain: **anonymous blocked → valid login → context persists on subsequent requests → user/roles accurate and isolated → session rotates → logout or revocation genuinely ends access**. Separate session revocation from OAuth access/refresh tokens and run the identical contract across baseline and candidate builds. A suite relying solely on mock principals will miss the most dangerous persistence and access-revocation failures.
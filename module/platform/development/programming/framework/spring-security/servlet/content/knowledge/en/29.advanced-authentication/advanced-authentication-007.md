# Requiring Reauthentication Before Sensitive Operations or After a Time Interval

## 1. Scenario and Security Goal

A user already logged into a Spring MVC application can perform low-risk tasks like viewing their profile, reading notifications, or searching. However, the following operations carry a different level of risk:

- Changing passwords, recovery email addresses, phone numbers, or MFA methods.
- Deleting accounts, downloading sensitive data, or viewing payment details.
- Adding payout accounts, changing limits, or executing money transfers.
- Granting administrative privileges or modifying an organization’s security settings.

If you only check that **`SecurityContext` holds a logged-in `Authentication`**, a login session created hours ago can still execute sensitive operations. Someone else might have used the computer while the account owner stepped away, a session cookie might have been stolen, or the user logged in via remember-me instead of freshly proving their identity.

**Reauthentication** requires the user to prove their identity again before executing a sensitive action or after a period of time since the last sufficiently trusted check. **Step-up authentication** is a broader concept: raising authentication assurance, such as re-verifying a password and then performing WebAuthn/passkey, MFA, or authenticating via an IdP at an appropriate assurance level.

Example policy:

- Accessing **GET /account**: requires only a normal login session.
- Executing **POST /account/security-settings**: must have freshly reauthenticated within the last **5 minutes**.
- Once 5 minutes have passed, the login session can continue being used for regular pages, while sensitive endpoints deny access until reauthentication succeeds.
- If a wrong password is entered during reauthentication, do not grant temporary access; depending on policy, clear any older reauthentication evidence.
- For very high-risk actions, you may need **one confirmation per specific transaction** or phishing-resistant MFA rather than a shared 5-minute window.

This lesson uses **Spring Boot 3.x, Spring Security 6.x, Servlet stack, Java 17+**, modeling login with **formLogin** and password reauthentication. OAuth2 Login/SSO, passkeys, and MFA require different verification approaches, distinguished clearly in later sections.

## 2. Easily Confused Concepts

| Mechanism | What Question Does It Answer? | Does It Replace Reauthentication? |
| --- | --- | --- |
| **Authentication** | Who is sending the request? | No: knowing the user is logged in does not tell when they last authenticated |
| **Authorization** | Does this person have permission to perform the action? | No: must check both permissions **and** authentication freshness |
| **Session idle timeout** | After how much inactivity does the session expire? | No: continuous activity keeps a session alive even when the initial login is very old |
| **Session absolute timeout** | How long can a session live at most from issuance? | No: bounds session lifetime, does not create fresh evidence for sensitive operations |
| **Remember-me** | Can login be restored from a long-lived cookie? | No: remember-me usually does not meet “just proved identity” requirements |
| **CSRF protection** | Did a state-changing request truly originate from the user’s authorized flow? | No: a CSRF token does not prove the user just reauthenticated |
| **Reauthentication freshness** | When did the most recent reauthentication occur, by whom, and how? | This is one component of the security requirement |
| **MFA / step-up** | Did authentication achieve the required assurance level? | Can complement freshness, but requires checking factors/assurance, not just timestamps |

Spring Security’s **isFullyAuthenticated()** expression only distinguishes anonymous/remember-me states from full authentication in framework terms; **it does not enforce a 5-minute threshold**. Likewise, **Authentication.isAuthenticated()** does not tell when the user last re-entered their password.

Never infer authentication time from **session.getCreationTime()**, last access time, or when a bearer JWT was issued (**iat**). Those values have different meanings from **when a reauthentication challenge was completed**.

## 3. Policy Design: Enforcing at the Security Boundary

The goal is to apply reauthentication to **every entry point of a sensitive operation**, rather than only checking in an HTML page. In Spring Security Servlet, conditions can be placed in **authorizeHttpRequests(...)** using **AuthorizationManager<RequestAuthorizationContext>**. When the condition fails, the request never reaches the controller.

~~~text
User already has HttpSession + SecurityContext
                │
                ├── GET /account
                │       → authenticated → view page
                │
                ├── POST /account/security-settings
                │       → CSRF check
                │       → AuthorizationManager:
                │          - current authentication valid?
                │          - reauth evidence exists in session?
                │          - evidence belongs to this exact username?
                │          - timestamp under 5 minutes old?
                │       → conditions met → sensitive controller
                │       → missing/expired → 403 + require reauthentication
                │
                └── POST /account/reauth
                        → must be fully logged in and carry CSRF token
                        → re-verify password via AuthenticationManager
                        → success: store server-side reauth evidence
                        → failure: grant no evidence
~~~

**Two independent conditions must hold simultaneously:** (1) the account has **permission** to perform the business action, and (2) the session user holds authentication evidence **sufficiently fresh and strong**. A user without admin permissions must not edit admin settings even right after entering the correct password.

### How Should Reauthentication Evidence Be Managed?

A value like **RecentProof(username, verifiedAt)** stored **in the server-side HttpSession** suffices for a single-node password-reauthentication demo:

- Store **username or a stable subject** so account B cannot use account A’s marker.
- Store **Instant verifiedAt** generated by the server after successful reauthentication, never taking timestamps from forms/browsers.
- When checking, use the server’s clock and **Duration.ofMinutes(5)**; never trust a client sending **reauth=true** or **lastAuthenticatedAt**.
- Never write **passwords, OTPs, access tokens, or secrets** into the session marker.
- On logout, session invalidation must wipe the marker; on account switches, clear the marker and verify the principal.
- If the app runs across multiple instances, session storage/replication must share the marker with the security context. If using stateless JWTs or no HttpSession, design dedicated step-up evidence instead of copying this pattern.
- If a security incident flags a session as compromised, do not just wait for TTL expiry; provide a mechanism to revoke sessions/evidence.

**The 5-minute window is a policy example**, not a built-in Spring Security rule. For large transfers or credential changes, a broad window may be insufficient; bind proof to the transaction, re-confirm each time, limit attempts, and use appropriate MFA.

## 4. Spring Boot 3.x / Spring Security 6.x Example

The example has two endpoints: **POST /account/reauth** re-verifies the password, and **POST /account/security-settings** represents a simulated sensitive operation. By default, Spring Security creates form login at **/login** and protects POSTs with CSRF tokens. All example paths belong to the same Servlet application.

In a Spring Boot 3.x project with Gradle wrapper:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

File **src/main/java/com/example/reauth/ReauthApplication.java**:

~~~java
package com.example.reauth;

import java.io.Serial;
import java.io.Serializable;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.RememberMeAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration;
import org.springframework.security.authentication.AuthenticationException;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class ReauthApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReauthApplication.class, args);
    }
}

// Server-issued evidence. Contains no password or OTP.
record RecentProof(String username, Instant verifiedAt)
        implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;
}

final class ReauthPolicy {
    private ReauthPolicy() {}

    static final String SESSION_KEY =
            ReauthPolicy.class.getName() + ".RECENT_PROOF";
    static final Duration FRESH_FOR = Duration.ofMinutes(5);

    static boolean isFresh(
            HttpServletRequest request,
            Authentication current,
            Clock clock) {

        if (current == null ||
                !current.isAuthenticated() ||
                current instanceof AnonymousAuthenticationToken ||
                current instanceof RememberMeAuthenticationToken) {
            return false;
        }

        HttpSession session = request.getSession(false);
        if (session == null) {
            return false;
        }

        Object value = session.getAttribute(SESSION_KEY);
        if (!(value instanceof RecentProof proof)) {
            return false;
        }

        Instant now = clock.instant();
        return proof.username().equals(current.getName()) &&
                !proof.verifiedAt().isAfter(now) &&
                now.isBefore(proof.verifiedAt().plus(FRESH_FOR));
    }
}

@Configuration
class SecurityConfiguration {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        // Local demo only; do not use these usernames/passwords in production.
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("demo-only-password"))
                        .roles("USER")
                        .build(),
                User.withUsername("bob")
                        .password(encoder.encode("another-demo-password"))
                        .roles("USER")
                        .build());
    }

    @Bean
    AuthenticationManager authenticationManager(
            AuthenticationConfiguration configuration) throws Exception {
        return configuration.getAuthenticationManager();
    }

    @Bean
    AuthorizationManager<RequestAuthorizationContext> recentPasswordCheck(
            Clock clock) {
        return (authentication, context) ->
                new AuthorizationDecision(
                        ReauthPolicy.isFresh(
                                context.getRequest(),
                                authentication.get(),
                                clock));
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            AuthorizationManager<RequestAuthorizationContext>
                    recentPasswordCheck) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/", "/error").permitAll()
                        // An independent authorization layer before the controller:
                        .requestMatchers(HttpMethod.POST,
                                "/account/security-settings")
                                .access(recentPasswordCheck)
                        .requestMatchers(HttpMethod.POST,
                                "/account/reauth")
                                .fullyAuthenticated()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .logout(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .build();
    }
}

@RestController
class AccountController {
    private final AuthenticationManager authenticationManager;
    private final Clock clock;

    AccountController(
            AuthenticationManager authenticationManager,
            Clock clock) {
        this.authenticationManager = authenticationManager;
        this.clock = clock;
    }

    @GetMapping("/")
    String home() {
        return "Sign in, then POST /account/reauth before sensitive POST";
    }

    @GetMapping("/account")
    String account(Authentication current) {
        return "account=" + current.getName();
    }

    @PostMapping("/account/reauth")
    ResponseEntity<Void> reauthenticate(
            @RequestParam("password") String password,
            Authentication current,
            HttpServletRequest request) {

        HttpSession session = request.getSession(false);
        if (session == null) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }

        // Every retry clears the old proof; failures are never inherited.
        session.removeAttribute(ReauthPolicy.SESSION_KEY);

        try {
            Authentication verified =
                    authenticationManager.authenticate(
                            UsernamePasswordAuthenticationToken
                                    .unauthenticated(
                                            current.getName(), password));

            if (!verified.isAuthenticated() ||
                    !verified.getName().equals(current.getName())) {
                throw new ResponseStatusException(
                        HttpStatus.UNAUTHORIZED,
                        "Reauthentication failed");
            }

            session.setAttribute(
                    ReauthPolicy.SESSION_KEY,
                    new RecentProof(current.getName(), clock.instant()));

            return ResponseEntity.noContent().build();
        } catch (AuthenticationException exception) {
            // Do not return details like "username not found" or "wrong password".
            throw new ResponseStatusException(
                    HttpStatus.UNAUTHORIZED,
                    "Reauthentication failed");
        }
    }

    @PostMapping("/account/security-settings")
    String updateSensitiveSettings() {
        // Demo: a real implementation must also check business permissions,
        // validate input, audit, and persist changes via a service.
        return "sensitive action accepted";
    }
}
~~~

### Mechanism in the Code

1. **AuthorizationManager** checks the marker in the server-side session before the sensitive operation’s controller is called. If the marker is missing, belongs to another user, or is older than **5 minutes**, it returns **AuthorizationDecision(false)**. The user can still access regular resources.
2. **POST /account/reauth** can only be called from a **fullyAuthenticated** session, so remember-me alone is not enough. The password is checked via **AuthenticationManager**, passing through the configured password/provider mechanism rather than string comparisons or browser-sent values.
3. Only after the password is correct and the username matches the active session does the server record **RecentProof(username, Instant.now(...))**. Never update the marker on a GET request, page refresh, or merely clicking an “I confirm” button.
4. Failed reauthentication clears the old proof. That is the demo’s *fail-closed* choice; a real application may prompt again or temporarily lock attempts after too many failures.
5. **CSRF remains enabled.** Both the password-entry POST and the settings-change POST require a valid CSRF token. With HTML forms, use Spring Security/Thymeleaf token integration or read a securely supplied token; **never** disable CSRF to make the form work.
6. **Logout** invalidates the session, making the marker invalid. **Username is bound to the marker** to prevent using another account’s proof in the same session. For multi-instance apps, ensure proper session replication if using a session store.
7. The sensitive endpoint in the demo only returns an illustrative body and **does not actually modify data**. In a real app, the service must enforce object-level authorization, auditing, transactions, and idempotency.

**Important:** This mechanism is **password-based reauthentication**, not MFA. It does not meet requirements like phishing-resistant MFA, transaction signature confirmation, or risk-based authentication. A freshly reauthenticated session can still be hijacked; time-bound proofs only limit the window, not eliminate risk.

### Role, Account, and Session Changes

- **Never use a simple boolean `true` marker.** A boolean can live indefinitely, lacks account binding, and conveys no assurance level.
- **Logging into a different account:** the app must clear step-up state on successful login/switch-user rather than relying solely on username. Username binding is an added defense layer, not a replacement for session lifecycle management.
- **Session fixation:** Spring Security normally rotates the session identifier on `formLogin`. Never disable default session fixation defenses just to keep a marker.
- **Changing password or MFA settings:** after changes, you may need to log out other sessions, revoke refresh tokens, and invalidate issued step-up proofs. Clearing a marker in one session does not automatically revoke sessions on other devices.
- **Permission checks:** the example only has `ROLE_USER`, whereas a real admin endpoint must check **hasRole("ADMIN")** or the matching policy alongside freshness—never replace role checks with timestamps.

## 5. Testing with MockMvc

In tests, **spring-security-test** provides the **user(...)** request post-processor to simulate an authenticated request without driving a form-login UI. Still, **POST /account/reauth** invokes the **real `AuthenticationManager`** and verifies the demo account’s password. This test approach verifies freshness and password re-checking, yet **is not a complete integration test** for production login forms/remember-me/SSO.

File **src/test/java/com/example/reauth/ReauthenticationTest.java**:

~~~java
package com.example.reauth;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import java.time.Duration;
import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ReauthenticationTest {
    @Autowired
    MockMvc mvc;

    private static MockHttpSession session() {
        return new MockHttpSession();
    }

    @Test
    void sensitiveActionWithoutProofIsForbidden() throws Exception {
        mvc.perform(post("/account/security-settings")
                        .session(session())
                        .with(user("alice").roles("USER"))
                        .with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    void correctPasswordCreatesFreshProof() throws Exception {
        MockHttpSession session = session();

        mvc.perform(post("/account/reauth")
                        .session(session)
                        .with(user("alice").roles("USER"))
                        .with(csrf())
                        .param("password", "demo-only-password"))
                .andExpect(status().isNoContent());

        mvc.perform(post("/account/security-settings")
                        .session(session)
                        .with(user("alice").roles("USER"))
                        .with(csrf()))
                .andExpect(status().isOk())
                .andExpect(content().string("sensitive action accepted"));
    }

    @Test
    void wrongPasswordDoesNotCreateFreshProof() throws Exception {
        MockHttpSession session = session();

        mvc.perform(post("/account/reauth")
                        .session(session)
                        .with(user("alice").roles("USER"))
                        .with(csrf())
                        .param("password", "incorrect-password"))
                .andExpect(status().isUnauthorized());

        mvc.perform(post("/account/security-settings")
                        .session(session)
                        .with(user("alice").roles("USER"))
                        .with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    void expiredProofIsForbidden() throws Exception {
        MockHttpSession session = session();
        session.setAttribute(
                ReauthPolicy.SESSION_KEY,
                new RecentProof(
                        "alice", Instant.now().minus(Duration.ofMinutes(10))));

        mvc.perform(post("/account/security-settings")
                        .session(session)
                        .with(user("alice").roles("USER"))
                        .with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    void proofCannotBeReusedByAnotherAccount() throws Exception {
        MockHttpSession session = session();
        session.setAttribute(
                ReauthPolicy.SESSION_KEY,
                new RecentProof("alice", Instant.now()));

        mvc.perform(post("/account/security-settings")
                        .session(session)
                        .with(user("bob").roles("USER"))
                        .with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    void failedRetryRemovesPreviousProof() throws Exception {
        MockHttpSession session = session();
        session.setAttribute(
                ReauthPolicy.SESSION_KEY,
                new RecentProof("alice", Instant.now()));

        mvc.perform(post("/account/reauth")
                        .session(session)
                        .with(user("alice").roles("USER"))
                        .with(csrf())
                        .param("password", "incorrect-password"))
                .andExpect(status().isUnauthorized());

        mvc.perform(post("/account/security-settings")
                        .session(session)
                        .with(user("alice").roles("USER"))
                        .with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    void csrfIsStillRequiredForReauthentication() throws Exception {
        mvc.perform(post("/account/reauth")
                        .session(session())
                        .with(user("alice").roles("USER"))
                        .param("password", "demo-only-password"))
                .andExpect(status().isForbidden());
    }
}
~~~

Run from the root of a Spring Boot project with Gradle wrapper:

~~~bash
./gradlew test --tests com.example.reauth.ReauthenticationTest
~~~

On Windows:

~~~powershell
.\gradlew.bat test --tests com.example.reauth.ReauthenticationTest
~~~

**Expected result when the sample code is placed in a compatible Boot 3.x project:** 7 tests pass. Missing proof, expired proof, proof belonging to another account, or missing CSRF receives **403**; wrong password receives **401**; correct password records the proof and allows the sensitive request (**204** then **200**). These are expectations for the demo setup, **not a confirmed execution result**.

**Do not test by directly sending a fake cookie or a client-controlled boolean.** In the tests above, the `HttpSession` attribute is stored by the server-side mock, and the reauthentication controller genuinely verifies the password.

### Additional Testing in a Real System

| Test Case | What to Verify |
| --- | --- |
| Creating a session via real form login | Login rotates session ID per policy and never accidentally retains a prior user’s proof |
| Logging out then reusing cookie | Marker is no longer valid; sensitive actions remain denied |
| Reauthenticate at t=0, act at t=4 min | Permitted if authorized |
| Reauthenticate at t=0, act at t=6 min | Rejected while regular-page session remains valid |
| Account lacks business permission | Still 403 even with fresh proof |
| Session expired / rotated | Cannot reuse previous session’s proof |
| Concurrent tabs and requests | No race conditions allowing expired or single-use proofs to be reused |
| Multi-instance cluster | Proof is valid only via shared session, never stored in a JVM static variable |
| Password brute-force on reauth endpoint | Attempt limits, anomaly detection, auditing, and blocking per policy |
| Remember-me / SSO | Proof not granted unless re-verified via an actual method |
| High-risk operation | Is evidence bound to the target/transaction and usable only for that exact action? |

For time-based tests, use a **fixed or controllable `Clock`** to verify exact 4m59s / 5m00s boundaries instead of `Thread.sleep` or testing close to wall-clock time. The example uses `Clock.systemUTC` for simplicity, so the expiration test sets a timestamp several minutes past the threshold to avoid flakiness.

## 6. Using Step-Up with OAuth2 Login / OpenID Connect / MFA

An application logging users in through an IdP does not necessarily know their passwords. **Never ask to store or forward an IdP password to the resource application for local checking.** Instead, run a reauthentication flow at the IdP using parameters and policies supported by that IdP.

Concepts to distinguish:

- **prompt=login** in OIDC can ask the IdP for interactive re-login, yet the application must verify the outcome and assurance policy; never treat a redirect URL alone as proof.
- **max_age** requests an authentication-age limit at the IdP. Per OIDC, when `max_age` is requested, the ID Token should include **auth_time** so the RP can check authentication time.
- **auth_time** reflects when the user authenticated according to the IdP’s claim; it is not the same as the ID Token’s **iat**, nor when the application received the callback.
- **acr** indicates Authentication Context Class Reference (assurance level per IdP profile); **amr** describes authentication methods per IdP. Value meanings must be part of the contract between application and IdP—never assume every `acr` means MFA.
- **WebAuthn/passkey**, TOTP, push challenges, and password reauthentication differ in phishing and replay resistance. For sensitive financial operations, consider phishing-resistant authenticators and transaction-content confirmation.
- **Session freshness** in the app and **auth_time at the IdP** are two separate layers. The RP must bind step-up results to the right user/session and prevent reuse past expiration.

Reference flow:

~~~text
User already logged into app
    │
    ├─ Requests sensitive information change
    ▼
App sees no fresh proof / sufficient assurance
    │
    ▼
Redirect to IdP with supported step-up request
    │  (e.g., max_age or acr_values per contract)
    ▼
IdP re-authenticates / executes additional factor
    │
    ▼
OAuth2/OIDC callback: app verifies state/nonce, ID Token,
iss/aud/signature, auth_time, and matching acr/amr
    │
    ▼
App stores server-side proof (subject, time, assurance, purpose)
    │
    ▼
Security authorization permits properly scoped action
~~~

With Spring Security OAuth2 Login on Servlet, extra OIDC parameters are typically integrated via configuration or customizing **OAuth2AuthorizationRequestResolver** alongside login result handling. The decisive factor is not a “re-login” button, but **verifying the evidence returned by the IdP**; exact mechanisms depend on Spring Security version and IdP.

**Never use an application session refresh as step-up evidence.** An IdP may immediately redirect the user back because an SSO session still exists; if policy demands recent identity proof, request and verify **auth_time**, assurance/method, or an additional challenge.

## 7. UX and Operational Safety

### 7.1. UX When Freshness Has Expired

When a user hits a sensitive endpoint with an expired proof:

1. **Never execute the business action** first and ask for a password afterward.
2. For REST endpoints, return **403** with an API-contract error code such as **reauthentication_required**; for web MVC, redirect the user to an internal step-up page.
3. Do not turn every 403 into “re-enter password”: the user might **lack permissions**, which reauthentication will not fix.
4. After success, re-check permissions and request validity rather than blindly “auto-approving” an old action without confirmation.
5. If saving a return URL, accept only **safe relative paths** or an allowlist of destinations; never allow arbitrary external URLs causing **open redirects**.
6. When the user switches accounts or logs out in another tab, clear/invalidate old proofs.

### 7.2. Residual Risks

| Risk | Mitigation |
| --- | --- |
| Session stolen **after** reauthentication | Short TTL, session binding, detection, per-transaction confirmation for critical actions |
| Password guessing on reauth endpoint | Rate limiting, throttling, auditing, alerts, and MFA; never expose detailed failure reasons |
| XSS firing requests inside a stepped-up session | CSP, output encoding, script controls, short windows, and transaction confirmation |
| CSRF when user logs in via cookies | Keep CSRF protection; step-up does not eliminate CSRF |
| Proof persists after login/account switch | Clear proof on login success, logout, account switch, and credential changes |
| Admin actions missing role checks | Combine role/object authorization with freshness |
| Inconsistent session storage across cluster | Shared session store and multi-node request testing |
| Clock drift | Use UTC, NTP, testable `Clock`; never use client time |
| User re-enters password on a phishing site | HTTPS, trusted UI, passkey/WebAuthn, or IdP step-up when suitable |
| Operation requiring “single-use” | Proof bound to purpose/transaction, nonce, tiny TTL, atomic consumption, and idempotency |
| Storing proof in localStorage or client-editable cookie | Store state server-side or use properly signed/verified evidence; never trust client booleans |

### 7.3. When to Re-Prompt Even Before 5 Minutes?

Elapsed time is one factor, not the only one. A system may force fresh reauthentication when:

- The user makes a change directly affecting account recovery or MFA methods.
- Unusual device, IP, location, or behavior is flagged by a trusted risk engine; avoid false lockouts from a single weak signal.
- The account recently had a password change, session revocation, detected credential compromise, or risk-state transition.
- A transaction requires confirming a **specific amount, recipient, or target**, not just entering a password within a short window.
- Compliance policies require a specific authenticator type or assurance level.

Note: IP or user-agent are not reliable independent authentication factors to “prove” a user; use them only as supplementary signals while weighing UX and privacy.

## 8. Common Mistakes to Avoid

| Mistake | Why It Is Dangerous | Correct Approach |
| --- | --- | --- |
| Calling only **authenticated()** on sensitive URLs | A session logged in hours ago is still accepted | Add authentication time and level checks |
| Using only **isFullyAuthenticated()** | Imposes no time limit since previous authentication | Combine with a freshness check |
| Accepting **lastLoginTime** from the browser | Users can tamper with the request | Create proof server-side when real auth succeeds |
| Setting **boolean reauthenticated=true** in session | Can live too long without time/user binding | Proof with principal, timestamp, assurance, and TTL |
| Using demo PIN/OTP without rate limiting | Vulnerable to brute-force or replay | Attempt limits, TTL, single-use, and monitoring |
| Checking only in the web form controller | Other APIs may invoke the business logic directly | Enforce at security boundaries and service authorization across all entry points |
| Disabling CSRF because reauth exists | Cookie sessions remain vulnerable to CSRF | Keep CSRF for unsafe methods |
| Re-logging via IdP without checking **auth_time** | SSO may skip challenges and return immediately | Request and verify OIDC freshness and assurance |
| Using JWT **iat** instead of `auth_time` | A fresh token does not prove the user just entered credentials | Use trusted reauth claims/signals |
| Issuing proof for user A and using it as user B | Marker is not bound to identity | Bind proof to principal, session, and purpose |
| Treating fresh proof as full authorization | Freshness does not replace RBAC/ABAC | Check roles, resource ownership, and policies too |
| Testing only the happy path with the right password | Misses missing CSRF, expiration, or replay | Negative tests and exact time/identity tests |

## 9. Pre-Production Completion Checklist

- Explicitly define which **paths/actions** require reauthentication, which roles may perform them, and each action’s risk level.
- Define the **freshness window** (e.g., 5 minutes) and whether proof covers multiple operations or a single transaction.
- Choose an appropriate **reauthentication method**: password via provider, OIDC `auth_time`/`acr`, MFA, WebAuthn. Never ask for passwords when the app is just an IdP’s OAuth2 Client.
- Record proof **only after successful verification**; store with session/user/time/purpose; clear on logout, account switch, credential change, or security incidents.
- Enforce conditions at the **Spring Security authorization boundary** and check business permissions in services. Never just hide frontend buttons or show popups.
- Ensure **CSRF**, session fixation protection, `HttpOnly`/`Secure`/`SameSite` cookies, and session expiration still work properly.
- Test timeouts using a **controllable `Clock`**, wrong passwords, remember-me, user switching, session invalidation, concurrent requests, missing permissions, and alternate endpoints hitting the same business logic.
- Limit brute-force attempts, audit step-up successes/failures, and never log plaintext passwords/OTPs.
- For ultra-sensitive transactions, add confirmation bound to a **transaction-specific nonce**, very short TTL, single-use, and anti-replay.
- In multi-node or IdP deployments, verify session/proof consistency and true authentication-event assurance rather than relying on client-device timestamps.

**Conclusion:** “Logged in” and “just proved identity strongly enough” are two distinct conditions. Spring Security lets you enforce re-checks right at **AuthorizationManager** and verify passwords via **AuthenticationManager**; with OAuth2/OIDC, rely on trusted step-up evidence from the IdP. Good design checks the right person, at the right time, with the right assurance level and business permissions—while maintaining authorization, CSRF, and session protection.

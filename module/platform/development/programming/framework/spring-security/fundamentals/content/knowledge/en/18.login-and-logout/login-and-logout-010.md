# Reauthentication Before Sensitive Operations and Multi-Factor Authentication (MFA) Concepts

## 1. Why might a successful login still not be enough?

A logged-in session proves the application previously authenticated the user, yet **does not guarantee that the person currently using the browser is still the account owner**. A browser may be left unattended on a shared computer, a session cookie may be stolen, or the device may have changed hands. Therefore, before high-consequence operations, the application may need to ask the user to **prove their identity again**.

For example: a customer logged in 2 hours ago and is reading transaction history. When they request to change their OTP phone number, create a new API key, or change a payout account, the server requires reauthentication before proceeding. The user can confirm with their current password, a passkey, or a stronger authentication method depending on policy. This is a distinct protection step from merely checking `authenticated()`.

After this lesson, you should be able to distinguish:

- **Authentication:** Who is requesting access? What evidence confirms their identity?
- **Authorization:** Does that identity have permission to perform this operation?
- **Reauthentication:** Requiring fresh authentication proof while the user already has an active login session.
- **Multi-factor authentication (MFA):** Using evidence from at least two **independent factor categories**; can occur at login or during reauthentication.
- **Step-up authentication:** Raising the assurance level when an operation or risk demands it; may require a stronger factor, an additional factor, or recent re-verification near the time of the operation.

**Key point:** `hasRole("ADMIN")` is about permissions; `authenticated()` is about authentication state; neither **automatically proves** the user just re-entered their password or used MFA. Spring Security's `fullyAuthenticated()` further distinguishes remember-me types, yet it also **is not synonymous** with "authenticated a few minutes ago."

## 2. When is reauthentication needed?

Do not force users to re-enter their password on every request. Classify actions by consequence and risk signals.

| Scenario | Suggested sensitivity | Possible protection |
| --- | --- | --- |
| Reading public pages | Low | No login required |
| Reading one's own routine data | Normal | Valid login session + access permission |
| Changing email address, password, or phone number | High | Reauthenticate near the time of change; consider MFA, change notifications |
| Adding/removing MFA devices, security keys, backup codes | High | Reauthenticate via a registered, trusted method; separate recovery workflow |
| Transferring funds, editing payees, viewing/downloading secret keys | Very high | Strong step-up, transaction-detail verification, time and usage limits |
| Login from unfamiliar device, anomalous behavior, recent account recovery | Risk-based | Extra verification step, restricted permissions, or require fresh login |

This table is a **design example**, not a universal set of timeouts or assurance levels for every product. Specific policies depend on threats, legal obligations, UX, and available authentication methods.

**Triggers for reauthentication** can be based on: sensitive actions, elapsed time since last authentication, elevated risk from device/IP, changes to login factors, account recovery, password changes, or anomaly detection systems. An IP address or "familiar device" is only a **risk signal**, never an independent authentication factor.

### 2.1. Freshness and assurance are two different dimensions

Examples:

1. Someone just entered a **password** 20 seconds ago: very fresh proof, yet only demonstrates the "something you know" factor.
2. Someone logged in with **password + security key** 6 hours ago: the earlier login had MFA, yet may not be fresh enough for an upcoming transaction.
3. Someone just confirmed a **passkey with user verification**: proof can be both fresh and high-assurance, depending on the authenticator and verification result.

Step-up policies typically check **both assurance level and time of verification**. Never rely solely on a session cookie, a user role, a boolean `mfaEnabled`, or the fact that MFA was once enabled to infer that the current authentication meets requirements.

## 3. What is MFA and what actually qualifies as "multi-factor"?

Three primary categories are commonly used:

| Category | Meaning | Examples |
| --- | --- | --- |
| **Something you know** | Memorized secret | Password, PIN used as a credential |
| **Something you have** | Proof of controlling an authenticator | FIDO2 security key, TOTP generator app, device storing a private key |
| **Something you are** | Biometric characteristic of the user | Fingerprint, face when verified by a trusted mechanism |

**Two different passwords** or **password + security question** are still two proofs from the "something you know" category and do not form true MFA. **Password + TOTP from an authenticator app** usually constitutes two factors: knowing the password and controlling the OTP-generating device/secret. A **passkey/WebAuthn unlocked with biometrics or PIN on the authenticator** can act as a multi-factor authenticator in a single authentication ceremony; the server must verify the WebAuthn result, including `userVerification` per policy, rather than assuming every passkey tap carries the same assurance level.

Some literature lists location or behavior as verification signals. In system design, **IP location or behavioral traits are typically risk-evaluation signals**, never an independent MFA factor simply because they differ from a password.

### 3.1. Comparing common methods

| Method | Pros | Limitations to remember |
| --- | --- | --- |
| Password + TOTP (time-based code) | Common, requires no cellular signal | Vulnerable to phishing/relay; must prevent code guessing and OTP reuse |
| Password + SMS OTP | Accessible | Risk of SIM swap, SMS interception, phishing, and carrier dependency |
| Password + email link/one-time token | Easy to implement | Depends on email account security; may not be truly independent of recovery channel |
| Password + FIDO2 security key | Strong phishing resistance when origin/RP ID verified properly | Requires device support and backup-key management |
| Passkey with user verification | Convenient UX, WebAuthn bound to RP/origin, phishing-resistant | Must evaluate key syncing, authenticator types, and assurance policy |
| Push approval | Fast | Risk of "MFA fatigue" (push bombing); requires challenge/number matching and rate limits |
| Recovery code | Helps recover account when device is lost | Must be protected like a credential, single-use, not a shortcut bypassing full recovery |

**OTP does not equal phishing-resistant authentication**: users can be tricked into typing codes into a fake site while an attacker relays them immediately. WebAuthn/FIDO2 is designed to bind proof to the legitimate website and thwart that phishing vector when properly implemented.

Terminology note: `TOTP/HOTP` are one-time codes generated from a registered secret, whereas Spring Security's **One-Time Token Login (OTT)** is a flow that generates a login token and delivers it to the user (typically via email/SMS). They **are not the same protocol**; merely enabling `oneTimeTokenLogin()` does not create TOTP authenticator-app integration.

## 4. Safe reauthentication flow for a sensitive operation

Suppose a user wants to rotate an API key. Recommended flow:

1. **Check existing login and permissions.** The server still verifies account/resource ownership, roles, and access policy.
2. **Determine step-up requirement.** If sufficiently fresh/strong proof is missing, return instructions to start reauthentication; do not execute the operation.
3. **Create a context-bound challenge.** Record the account, session/transaction, operation type, target to change, expiration, and an appropriate random nonce/ID.
4. **Verify fresh proof on the server.** E.g., the user re-enters their password over TLS or completes a WebAuthn assertion/TOTP flow. Never trust a `verified=true` flag sent from the browser.
5. **Issue short-lived bound proof.** Can be stored server-side in session/challenge storage; issued only after the verifier validates it. Never put passwords or OTPs in cookies, browser-crafted JWTs, or logs.
6. **Re-check right at the executing endpoint.** Right account? Right operation, target, transaction data? Unexpired? Unused? Still authorized? Every check must run on the **server**, right when executing.
7. **Consume the proof and execute safely.** For real transactions, prevent races/double-submits using atomic storage operations, idempotency keys, and auditing.
8. **Notify and monitor.** Send notifications when login factors or critical security settings change; emit audit events without logging credentials.

A rule like "reauthentication proof is valid for **2 minutes and only for a single API key change**" is an **illustrative choice**, not a default timeout from Spring Security or NIST. Real systems must evaluate their own risks and policies.

~~~text
Client has valid session
    |
    v
POST /account/change-sensitive-setting
    |
    +-- Insufficient permissions? --> 403 / deny
    |
    +-- No fresh proof? ------------> Require reauthentication
    |                                      |
    |                                POST /account/reauthenticate
    |                                      |
    |                                Verify password / another factor
    |                                      |
    |                                Save short-lived confirmation proof
    |                                      |
    +<-------------------------------------+
    |
    v
Check identity + action + TTL + unused
    |
    +-- Fails? ---------------------> 403 / repeat step-up
    |
    v
Consume confirmation proof and execute operation
~~~

To avoid **time-of-check/time-of-use (TOCTOU)** and reuse, high-value operations must check/consume the proof atomically alongside the transaction update. Never set a permanent `isMfaVerified=true` flag on the user profile and allow every sensitive action forever.

## 5. Spring Security: where to place the checks

In Servlet applications, `SecurityFilterChain` normally handles request authentication and authorization. `SecurityContextHolder` stores the current request's context; `Authentication` holds principal, authorities, authentication method, and other details. **Spring Security 6 does not automatically provide an "authenticated within 2 minutes" check for every app** just because the user logged in. Business freshness policies must be implemented deliberately.

Defense layers should include:

- **Security chain:** Block unauthenticated requests and enforce authorization rules. E.g., `.requestMatchers("/account/**").authenticated()`.
- **Reauthentication step:** Verify credentials/second factor via a trusted verifier, with rate limiting and audit events; store the confirmation marker only after success.
- **Sensitive endpoint:** Independently verify the issued proof, scope, lifetime, and target. Protect all APIs, batch actions, and alternative endpoints; hiding a UI button is not a security control.
- **Session and CSRF:** Cookie-based web apps still must handle CSRF, session fixation, logout, idle timeout, TLS, and `Secure`/`HttpOnly`/`SameSite`. Reauthentication does not replace these layers.

If the app is an OAuth2/OIDC client, it can leverage the Identity Provider's (IdP) reauthentication/step-up policies. When doing so, validate the token and trusted issuer claims like `auth_time`, `acr`, and `amr` **when issued by the IdP under a clear contract**; sending `prompt=login` or `max_age=0` only matters if the IdP enforces it and the RP checks the result.

## 6. Hands-on example: password reauthentication in Servlet

This example **illustrates single-factor reauthentication**, **not MFA yet**. After logging in via form, the user wants to call an endpoint simulating changing a security setting. The server forces password re-verification and issues a session-scoped proof with a 2-minute lifetime, bound to the user and action type. The proof is consumed on first use.

The example uses **Java 17**, **Spring Boot 3.5.0** (Spring Security 6.x, Servlet), and Web + Security dependencies. The example runs standalone in a demo app; there is no need to write a login page because Spring Security provides default form login.

**`pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
  </parent>
  <groupId>example</groupId>
  <artifactId>step-up-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
  </dependencies>
</project>
~~~

**`src/main/java/example/stepup/StepUpApplication.java`:**

~~~java
package example.stepup;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import java.io.Serializable;
import java.time.Duration;
import java.time.Instant;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class StepUpApplication {
    public static void main(String[] args) {
        SpringApplication.run(StepUpApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authz -> authz
                .requestMatchers("/account/**").hasRole("USER")
                .anyRequest().permitAll())
            .formLogin(Customizer.withDefaults())
            // Keep default CSRF enabled for cookie-based POSTs.
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails demo = User.withUsername("demo")
            .password(encoder.encode("demo123"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(demo);
    }
}

@RestController
@RequestMapping("/account")
class StepUpController {
    private static final String PROOF_KEY =
        StepUpController.class.getName() + ".proof";
    private static final String ACTION = "CHANGE_SENSITIVE_SETTING";
    private static final Duration LIFETIME = Duration.ofMinutes(2);

    private final UserDetailsService users;
    private final PasswordEncoder encoder;

    StepUpController(UserDetailsService users, PasswordEncoder encoder) {
        this.users = users;
        this.encoder = encoder;
    }

    @GetMapping("/me")
    String me(Authentication authentication) {
        return "Logged in: " + authentication.getName();
    }

    @PostMapping("/reauthenticate")
    ResponseEntity<String> reauthenticate(
            Authentication authentication,
            @RequestParam String password,
            HttpServletRequest request) {

        HttpSession session = request.getSession(false);
        if (session == null) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .body("No active login session");
        }

        // Remove old proof even when reauthentication fails.
        session.removeAttribute(PROOF_KEY);

        UserDetails user;
        try {
            user = users.loadUserByUsername(authentication.getName());
        } catch (UsernameNotFoundException ex) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .body("Unable to reauthenticate");
        }

        boolean accountUsable = user.isEnabled()
            && user.isAccountNonLocked()
            && user.isAccountNonExpired()
            && user.isCredentialsNonExpired();
        if (!accountUsable || !encoder.matches(password, user.getPassword())) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .body("Unable to reauthenticate");
        }

        // Server-side confirmation marker: do not store password in session.
        session.setAttribute(PROOF_KEY,
            new Proof(authentication.getName(), ACTION, Instant.now()));
        return ResponseEntity.ok("Reauthentication succeeded");
    }

    @PostMapping("/change-sensitive-setting")
    ResponseEntity<String> changeSensitiveSetting(
            Authentication authentication,
            HttpServletRequest request) {

        HttpSession session = request.getSession(false);
        if (session == null) {
            return forbidden();
        }

        // Consume once, synchronized within the session for a single-server demo.
        Object stored;
        synchronized (session) {
            stored = session.getAttribute(PROOF_KEY);
            session.removeAttribute(PROOF_KEY);
        }

        Instant now = Instant.now();
        if (!(stored instanceof Proof proof)
                || !proof.username().equals(authentication.getName())
                || !ACTION.equals(proof.action())
                || proof.issuedAt().isAfter(now)
                || Duration.between(proof.issuedAt(), now)
                    .compareTo(LIFETIME) > 0) {
            return forbidden();
        }

        // Access-control illustration only, does NOT mutate real data.
        return ResponseEntity.ok("Allowed: sample operation approved");
    }

    private ResponseEntity<String> forbidden() {
        return ResponseEntity.status(HttpStatus.FORBIDDEN)
            .body("Reauthentication required before sensitive operation");
    }

    private record Proof(
        String username, String action, Instant issuedAt
    ) implements Serializable {
        private static final long serialVersionUID = 1L;
    }
}
~~~

**Run the sample** (with Java 17 and Maven installed):

~~~bash
mvn spring-boot:run
~~~

Open `http://localhost:8080/login` and sign in as `demo / demo123`. Use a browser, Postman, or a client with a **valid session cookie and CSRF token** to send the two POST requests. With Spring Security's default CSRF, calling `curl -X POST` without sending a token typically returns **403 before reaching the controller**; that is proper protective behavior, not broken reauthentication code.

Server logic verification sequence:

| Case | Expected result |
| --- | --- |
| Not logged in, access `/account/me` | Redirected to login |
| Logged in, yet POST `/account/change-sensitive-setting` before reauthenticating | 403, requires reauthentication |
| POST `/account/reauthenticate` with wrong password | 401, no proof issued |
| POST `/account/reauthenticate` with right password | 200, proof stored in session |
| Immediately afterward POST `/account/change-sensitive-setting` | 200, displays simulated result |
| Call sensitive endpoint a second time without reauthenticating | 403 because proof was already consumed |
| Wait over 2 minutes after reauthentication before calling the operation | 403 because proof expired |
| Logging out invalidates the session | No valid proof remains |

**Explanation:** The security chain only guarantees the user is logged in and has `ROLE_USER`. The controller is responsible for **re-verifying credentials** and checking proof close to the time of the operation. In this sample, the proof exists only inside one `HttpSession` and binds to the exact username/action. The password is checked against the hash via `PasswordEncoder`, never stored directly in the session.

**Intentional limitations of the demo:** user data resides in memory, the demo password is fixed in source, and there is no rate limiting, auditing, automatic account lockout, distributed session handling, cross-node race handling, transaction IDs, or real data mutation. In real systems, re-verify through an appropriate `AuthenticationManager`/provider so login policies and attempt limits apply; store challenges in a shared data store and consume atomically. The code above teaches **the principles of reauthentication**, **not a production implementation template or MFA**.

## 7. Applying MFA directly in Spring Security 7 (Servlet)

Spring Security **7.0 and higher** provides built-in MFA capabilities on Servlet such as `FactorGrantedAuthority`, `@EnableMultiFactorAuthentication`, and `AuthorizationManagerFactories.multiFactor()`. These APIs **do not exist in Spring Security 6.x**: the Spring Boot 3.5.0 example in section 6 cannot copy the configuration below verbatim.

Spring Security 7 records information about the **factors actually used** during authentication on `Authentication` as `FactorGrantedAuthority`, for example:

- `FactorGrantedAuthority.PASSWORD_AUTHORITY`: password factor;
- `FactorGrantedAuthority.OTT_AUTHORITY`: one-time token login;
- `FactorGrantedAuthority.WEBAUTHN_AUTHORITY`: WebAuthn.

MFA rules require **both sides**: requiring the necessary factor authorities in authorization and configuring authentication mechanisms **capable of supplying** those factors. Merely declaring a custom authority string or a database flag is insufficient to prove MFA occurred.

The configuration below is a **snippet for a Spring Security 7.0+ application**, illustrating requiring password + OTT only for `/account/security/**`. It is **not a standalone application**: the app needs users, a secure OTT generation/delivery mechanism, and proper token storage. When using it, choose this configuration **instead of** section 6's demo security chain, without adding a second chain with overlapping matchers.

~~~java
package example.stepup;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationManagerFactories;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.authorization.EnableMultiFactorAuthentication;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.authority.FactorGrantedAuthority;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

@Configuration
@EnableMultiFactorAuthentication(authorities = {})
class SelectiveMfaSecurity {
    @Bean
    SecurityFilterChain mfaChain(HttpSecurity http) throws Exception {
        var mfa = AuthorizationManagerFactories
            .<RequestAuthorizationContext>multiFactor()
            .requireFactors(
                FactorGrantedAuthority.PASSWORD_AUTHORITY,
                FactorGrantedAuthority.OTT_AUTHORITY)
            .build();

        return http
            .authorizeHttpRequests(authz -> authz
                .requestMatchers("/account/security/**")
                    .access(mfa.authenticated())
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .oneTimeTokenLogin(Customizer.withDefaults())
            .build();
    }
}
~~~

**Additional configuration needed before real-world use:**

1. OTT delivery channel: Spring Security does not know user email/SMS addresses or how your app sends tokens. Provide a `OneTimeTokenGenerationSuccessHandler` to deliver to the right user without leaking tokens in logs.
2. Token store: Spring Security's default example uses `InMemoryOneTimeTokenService`; in multi-instance setups, consider `JdbcOneTimeTokenService` or an appropriate backend with expiration/consumption policies.
3. Factor independence: an OTT delivered to the same email inbox may not provide enough assurance for high-risk operations. Consider WebAuthn/passkeys or another authenticator suited to your security goals.
4. Authentication timing: holding two factor authorities proves those mechanisms were used; if an operation requires **reauthenticating right before execution**, also enforce freshness limits or `RequiredFactor`/matching policies. Do not equate MFA with freshness.

**Applying MFA application-wide:** Spring Security 7 also allows `@EnableMultiFactorAuthentication(authorities = { FactorGrantedAuthority.PASSWORD_AUTHORITY, FactorGrantedAuthority.OTT_AUTHORITY })` to add requirements across matching authorization rules. When required only for specific routes, use selective configuration as above to avoid blocking every request.

**WebAuthn:** passkey support in Spring Security requires the `spring-security-webauthn` module and registering trusted credentials with the exact RP ID/origin. Do not write your own WebAuthn verifier by comparing a client-supplied "passkey" string.

**WebFlux:** the `HttpSecurity` and `SecurityFilterChain` examples in this section apply to Servlet. Reactive applications must use `ServerHttpSecurity` and `SecurityWebFilterChain` with version-compatible MFA/step-up solutions; do not mix Servlet APIs directly into WebFlux.

## 8. Properly designing reauthentication in OAuth2/OIDC and SSO

In SSO systems, the application usually does not hold the user's password; having the RP app collect the IdP password in a custom form is inappropriate. Instead:

1. The RP sends a re-login request through the IdP using the integrated protocol. OIDC can use parameters such as `max_age`, `prompt=login`, or `acr_values` if supported by the IdP.
2. The IdP performs reauthentication or step-up. If MFA is required, the IdP must use methods meeting organizational policy.
3. The RP validates the ID token/response and reads trusted-issuer evidence such as `auth_time` (authentication time), `acr` (authentication context class reference), and `amr` (authentication methods references) **if issued by the IdP under a clear contract**.
4. The RP compares assurance level and freshness against the operation's requirements, binding step-up success to the right user and transaction. If claims are absent or insufficient, deny the operation rather than trusting the outbound request.

Never conclude "the IdP definitely reauthenticated the user" simply because the RP appended `prompt=login` to the URL. Check the **signed/verified result from the issuer** and the IdP's policy. Likewise, `scope` or an access token's mere existence does not prove the user's session recently completed MFA.

When using access tokens for APIs, clearly decide where step-up is checked: gateway, resource server, business service, or a combination. Never let direct endpoint calls bypass UI/gateway checks.

## 9. Enrollment, recovery, and MFA factor lifecycle

MFA does not end at the "enter code" screen. An authentication factor's lifecycle typically includes:

- **Enrollment:** The user already has a trusted session; before attaching a new factor, require reauthentication and verify possession of the authenticator. For TOTP, secrets/QR enrollments must be transmitted securely, never logged or arbitrarily redisplayed; require code verification before activation.
- **Usage:** TOTP/OTPs need expiration, attempt limits, replay prevention, and bounded clock-skew handling; push notifications should require active confirmation and prevent approval spam. For WebAuthn, validate challenge, origin, RP ID, signature, and user verification as required.
- **Modification/removal:** Changing or removing a factor is highly sensitive; never let a stolen-cookie session disable MFA silently. Send notifications and emit audits on changes.
- **Recovery codes:** Generate with a CSPRNG, store hashed or with equivalent protection, display once, enforce single use, limit requests, and record usage. Never treat recovery codes as a silent shortcut.
- **Lost authenticator:** Provide a recovery flow with commensurate assurance, delays, or extra checks when needed. A weak security question can nullify all of MFA's value.
- **Logout/revocation:** Revoke session- or transaction-bound step-up evidence, delete/revoke credentials upon critical changes, and bound lifetimes.

Practical rule: **the weakest link is often factor re-enrollment or account recovery**. Treat MFA setup, reset, removal, and backup as core parts of authentication design, not secondary features.

## 10. How reauthentication, MFA, and other controls relate

| Control | Solves | Does NOT solve by itself |
| --- | --- | --- |
| Checking `authenticated()` | Request is tied to a logged-in user | Freshness, MFA, per-operation permissions |
| `hasRole(...)` or ABAC policy | User is authorized for the route/resource | Hijacked sessions, reauthentication |
| Requiring password re-entry | Subject proved recent knowledge of password | MFA, phishing resistance if password-only |
| MFA | Evidence from multiple independent factor categories / strong credentials | Authentication timing, task permissions, transaction target |
| Per-transaction step-up | Verification level tailored to a specific action | Other session/XSS/CSRF protections |
| CSRF token | Reduces cross-site browser-triggered state changes | Session theft, phished credentials |
| HTTPS + cookie flags | Protects transport/session IDs in specific contexts | Permission or freshness decisions |
| Logging/auditing | Event traceability and investigation | Blocking unauthorized actions if enforcement is missing |

Specifically, **reauthentication does not replace CSRF**. If the browser automatically sends a session cookie to an endpoint, state-changing requests must still be protected. **MFA does not cure XSS**: malicious scripts running inside a valid session can access data and trigger actions depending on the defense model.

## 11. Common implementation mistakes

**Mistake 1 – Implementing the code prompt only on the frontend.** Users can call the sensitive API directly. **Fix:** enforce the proof/MFA policy on the server in the executing endpoint across every equivalent entry point.

**Mistake 2 – Storing `mfaVerified=true` permanently in the user profile.** That only says a flag was once set, not how or when verification occurred. **Fix:** store authentication outcomes with issuer, method, timestamp, session/action binding, and TTL; never use a global boolean instead of proof.

**Mistake 3 – Using password + security question and calling it 2FA.** Both belong to "something you know." **Fix:** use independent factor categories, preferring appropriate phishing-resistant authentication.

**Mistake 4 – Checking elapsed time only in the browser.** Users can alter clocks or requests. **Fix:** record and evaluate timestamps using the server's clock; apply bounded clock-skew handling when verifying tokens across systems.

**Mistake 5 – Accepting the same OTP/magic link multiple times.** Attackers can replay the credential. **Fix:** single-use tokens, short TTL, atomic consumption, rate limits, and anti-enumeration.

**Mistake 6 – Reauthenticating once unlocks everything.** Proof used to view data should not automatically remain valid for withdrawing funds or changing an MFA device. **Fix:** bind proof to action, account, target, or transaction digest plus TTL; consume upon use.

**Mistake 7 – Forgetting authorization checks after reauthentication.** A regular user can reauthenticate themselves yet still has no right to perform admin actions or touch another user's data. **Fix:** combine authentication, authorization, and step-up; check ownership in the business layer.

**Mistake 8 – Omitting brute-force limits and security-change alerts.** A "re-enter password" form is another credential-guessing surface. **Fix:** rate limit per account/IP/risk, write safe audits, notify on factor changes; never log passwords, OTPs, recovery codes, or raw tokens.

**Mistake 9 – Confusing Spring OTT with TOTP authenticators.** OTT has the server generate and send a token; TOTP uses a provisioned shared secret and code-generation algorithm. **Fix:** pick the right standard and verify implementation and method independence.

**Mistake 10 – Allowing MFA reset via an email channel much weaker than primary MFA.** An attacker only needs to compromise email to bypass protection. **Fix:** build recovery flows scaled to risk with strong verification, delays/anomaly controls, and notifications.

## 12. Testing checklist

After implementation, test both in the backend and with real browsers:

1. **Unauthenticated account:** sensitive operations cannot execute.
2. **Logged in with right role, but no step-up yet:** endpoint still denies or demands reauthentication.
3. **Wrong credentials/wrong OTP/expired:** no proof issued; rate limiting triggers; no information leaks.
4. **Valid credentials and passing verification:** proof issued only for that user and action; no overly broad grants.
5. **Switching user/session/transaction after challenge:** old proof is rejected.
6. **TTL expired:** proof is rejected, even while the login session remains valid.
7. **Replay/double submit:** proof cannot execute two transactions; test concurrent races and multi-node deployments.
8. **Missing CSRF token with cookie authentication:** state-changing requests are blocked.
9. **Alternate API paths:** no endpoint bypasses step-up/authorization checks.
10. **Logout, password reset, MFA removal, suspected account takeover:** issued proofs are invalidated per policy.
11. **MFA enrollment/recovery:** no shortcut bypasses strong authentication.
12. **Audit and privacy:** logs capture events and correlation IDs, never passwords, OTPs, recovery codes, or cookie/session tokens.

Distinguish **happy-path tests** from **attack tests**: using another session's cookie, modifying a transaction ID between challenge and commit, reusing an old OTP, sending two concurrent requests, hitting bypass URLs, checking CSRF, and verifying outcomes for each failure mode.

## 13. Self-check questions

**Question 1.** Someone has `ROLE_ADMIN` and logged in yesterday. Is that enough to export all API keys? **No.** Admin permissions differ from verifying identity freshly and strongly enough for a sensitive action.

**Question 2.** Re-entering a password before changing an email—does that turn the app into MFA? **No.** That is reauthentication using the same password factor; MFA requires evidence from an independent category (or a multi-factor authenticator meeting policy).

**Question 3.** Password + TOTP reduces risk; are those two factors completely phishing-resistant? **Not yet.** Codes can be relayed through a fake site; WebAuthn/FIDO2 is a stronger phishing-resistant option when properly implemented.

**Question 4.** If an app verified MFA at login, can all subsequent step-up checks be skipped? **Not necessarily.** Sensitive operations may still require freshness and transaction binding.

**Question 5.** Is Spring Security's `oneTimeTokenLogin()` the same as TOTP via Google Authenticator? **No.** OTT is a single-use token generated/sent by the application, unlike TOTP derived from a shared secret.

**Question 6.** Why must reauthentication proof be bound to the session/action and single-use? **To prevent one verification from being reused for another action or account**, reducing replay and limiting exposure if a session is hijacked.

## 14. References

- [Spring Security – Multi-Factor Authentication, Servlet, Spring Security 7](https://docs.spring.io/spring-security/reference/servlet/authentication/mfa.html)
- [Spring Security – One-Time Token Login](https://docs.spring.io/spring-security/reference/servlet/authentication/onetimetoken.html)
- [Spring Security – Passkeys/WebAuthn](https://docs.spring.io/spring-security/reference/servlet/authentication/passkeys.html)
- [Spring Security – SecurityContext and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [OWASP Authentication Cheat Sheet – Reauthentication, MFA, Adaptive Authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP Session Management Cheat Sheet – Reauthentication after risk events](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html)
- [NIST SP 800-63B – Digital Identity Guidelines (current edition)](https://pages.nist.gov/800-63-4/sp800-63b.html)

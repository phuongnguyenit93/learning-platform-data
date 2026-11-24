# Choosing Advanced Authentication Features by Spring Security Version and What Applications Must Build Themselves

> **Scope:** Spring Security on the **Servlet stack**. This guide covers choosing advanced authentication capabilities, accurately reading the support scope of the **actual framework version**, and dividing responsibilities among Spring Security, the Identity Provider (IdP), the application, and the operations team. Main examples use Java 17, Spring Boot 3.3.x, and Spring Security 6.x; features introduced in 6.4+ must not be assumed to exist in every 6.x version.

## 1. The Problem: “Spring Security Supports It” Differs from “A Complete Product”

A business requirement is often phrased in sentences like:

- “Allow login with a passkey, while still needing a recovery method if the device is lost.”
- “Accounts normally use passwords; transferring money requires authenticating with an additional factor.”
- “Send a one-time login link via email that expires quickly and can only be used once.”
- “Employees log in via SSO to use the company’s MFA.”
- “When upgrading Spring Security, do MFA features, sessions, and UI automatically work?”

The answer must separate **at least four layers of responsibility**:

1. **Protocol/mechanism:** framework code that creates filters, receives requests, verifies credentials/tokens, maintains `Authentication`, and integrates with `SecurityFilterChain`.
2. **Policy:** when one or multiple factors are required, which resources demand step-up, which permissions are bound to an identity and at what assurance level; not just “log in and allow every action.”
3. **Experience/lifecycle:** UI, enrollment, reset, recovery, device replacement, rate limiting, notifications, and user support.
4. **Operations/trust:** secret storage, credential repository, email/SMS gateway, HSM/PKI, IdP, auditing, monitoring, dependency versions, and security testing.

**Having a filter or DSL for a feature does not mean the framework completes all four layers.** Conversely, when the company already uses an IdP that supports MFA and passkeys, the application often does not need to implement the entire authentication protocol itself; Spring Security can act as an OIDC/SAML client or resource server to validate tokens for the intended purpose.

## 2. Version Axis: Read What Is Actually Running Before Choosing an API

Spring Boot manages a set of Spring Security dependencies via its BOM. Therefore, “using Boot 3” does not automatically prove that an API introduced in a newer Spring Security release is available. In particular, distinguish **Spring Security 6.0/6.1/6.2/6.3** from **6.4+** and later release branches.

| Version Group | Platform / Configuration Style | Points to Check Before Using Advanced Features |
|---|---|---|
| Spring Security 5.x, typically paired with Boot 2.x | Much code still uses `javax.servlet` or legacy configuration | Review the migration guide when upgrading; do not copy classes/namespaces to 6.x without changes. `WebSecurityConfigurerAdapter` is no longer the configuration approach for 6.x |
| Spring Security 6.0–6.3, typically paired with Boot 3.x | Java 17+, `jakarta.servlet`, declaring `SecurityFilterChain` as beans with lambda DSL | Form login, HTTP Basic, OAuth2 client/resource server, SAML2, LDAP/X.509, and familiar authentication building blocks form the baseline; do not assume the 6.4 WebAuthn/one-time token login DSLs are present |
| Spring Security 6.4+ | Still in the 6.x generation, with additional features | Adds new support for **WebAuthn/passkeys** and **one-time token login**; verify exact minor/patch versions, dependencies, repository configuration, and corresponding samples. The framework scaffolding still does not mean the application has complete MFA |
| Major versions after 6.x (e.g., 7.x when chosen by a project) | May change APIs, default behaviors, and module scopes | Only use MFA/DSL/version-specific features after verifying documentation, migration guides, and the dependency tree for the exact deployed version; do not assume 6.x APIs remain unchanged or that every factor policy is built in |

This table **does not replace release notes**. Features, classes, DSLs, and defaults can vary across minor releases, patch releases, or dependency packages. In this guide, configurations belonging to the common 6.x baseline are separated from 6.4+ capabilities to avoid teaching the wrong API.

### 2.1. Identifying the Actual Version

For Gradle projects:

```bash
./gradlew dependencyInsight \
  --dependency spring-security-web \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency spring-security-config \
  --configuration runtimeClasspath
```

For Maven:

```bash
./mvnw dependency:tree \
  -Dincludes=org.springframework.security
```

Check the **resolved version**, not just the version number written in an online example. Record the Boot version, Java version, and optional artifacts such as `spring-security-oauth2-client`, `spring-security-oauth2-resource-server`, `spring-security-saml2-service-provider`, and `spring-security-ldap`. Optional modules do not automatically exist just from `spring-boot-starter-security`.

When evaluating a new feature, read the documentation for the **exact version** of the Servlet module, check the migration guide, release notes, test samples, and dependency requirements. If the system is on a version without the feature, the options are **a tested upgrade**, **using an IdP that already has the capability**, or **building it yourself with a risk assessment** — never calling a DSL that does not exist.

## 3. Matrix: What Spring Security Provides vs. What the Application Must Still Do

| Need | Spring Security / Platform Building Blocks Available | Parts the Application / Other Teams Remain Responsible For |
|---|---|---|
| Username/password | `formLogin`, `AuthenticationManager`, `AuthenticationProvider`, `PasswordEncoder`, session, and CSRF | User registration, strong passwords, email verification, password reset, brute-force protection, lockout/anti-enumeration, UX, audit |
| Enterprise SSO | `oauth2Login` or `saml2Login` and corresponding modules | Client/RP registration, IdP, MFA policy, account linking, role mapping, recovery, session/logout |
| API bearer token | `oauth2ResourceServer`, JWT/opaque token validation | Authorization server/IdP, audience/scope contract, entitlement checks, token issuance/revocation strategy |
| Certificate authentication | `x509`, pre-auth mechanism with Servlet/TLS infrastructure | PKI, CA, client cert lifecycle/revocation, TLS termination, cert-to-account mapping |
| LDAP | `spring-security-ldap`, LDAP authentication/provider | Directory schema, LDAPS/trust store, group-to-authority mapping, timeout/availability, password policy |
| Passkey/WebAuthn | WebAuthn integration support in suitable versions (e.g., 6.4+) | Credential store, registration UX, device management, recovery, proper relying party/origin, account takeover prevention |
| One-time token login | One-time token login capability in suitable versions (e.g., 6.4+) | External link generation/delivery, email provider, recipient verification, anti-abuse, storage/TTL, delivery UX, and testing |
| TOTP authenticator app | Can integrate provider/filter/DSL depending on version | QR enrollment, TOTP secret, secure storage, retry limits, time skew, replay prevention, recovery codes, MFA policy |
| SMS/email code | Use common components or custom logic per design | OTP delivery, anti-abuse, rate limiting, risk engine, TTL, replay prevention, user identification, fail-safe; SMS is vulnerable to SIM swap |
| MFA and step-up | Authentication/authorization primitives; factor-based features may appear in newer versions | Factor selection, mandatory conditions, trust level, when to re-auth, session factor state, which transactions are sensitive, recovery |
| Session protection | Session management, concurrent session controls, CSRF, logout, security context | Actual cookie policy, distributed sessions, device inventory, revocation, HA, and incident handling |
| Remember-me | Supported remember-me mechanism | Alignment with threat model, token store, rotation, revocation, never treating remember-me as an MFA factor |
| Audit and anomalous behavior | Events/logging/extension points | Business audit, credential stuffing protection, risk detection, alerting, PII protection, and incident response operations |

Examine the matrix with three questions: **Is there a credential verification mechanism? Is there a policy controlling permissions and additional authentication steps? Is there a complete real-world lifecycle?** If any answer is “not yet,” simply “enabling support” still means the product is incomplete.

## 4. MFA: Factors, Policies, and Step-Up

### 4.1. What Counts as Multiple Factors?

MFA requires evidence from **at least two independent factor categories** under an appropriate security model:

- **Something you know:** password or PIN.
- **Something you have:** authenticator, security key device, controlled private key.
- **Something you are:** biometric characteristics when the system authenticates properly under a supported model.

Two different passwords or a password plus a security question **do not automatically constitute MFA**. Email OTP can serve as an additional verification step, but its independence and assurance level depend on how the mailbox is protected; it must not be assumed equivalent to a phishing-resistant security key. TOTP can also be phished in real time, unlike origin-bound WebAuthn.

**Passkeys** (WebAuthn/FIDO2) use public-key cryptography bound to a relying party/origin and can be a strong login method with user verification on the authenticator. Whether it counts as one or multiple factors under an assurance policy depends on the authenticator type and user verification requirements—**logging in with a passkey does not automatically satisfy every MFA policy**.

### 4.2. Step-Up Is a Policy, Not Just a Second Login Page

For example, a user is already logged in to read reports, but transferring money requires **re-authenticating with a strong factor within a recent time window**:

```text
GET /dashboard
   |
   +--> Authenticated session --> allow viewing dashboard
   |
POST /payments/confirm
   |
   +--> Authorized to perform transaction?
   |      +-- No --> 403
   |
   +--> Authentication level / factor still valid per policy?
          +-- No --> transition to step-up flow
          |          (IdP or verified factor mechanism)
          +-- Yes --> continue CSRF checks, business validation,
                      transaction binding when appropriate, then process
```

Spring Security provides primitives such as `Authentication`, `GrantedAuthority`, authorization rules, `AuthenticationManager`, and provider/filter chains. However, the application **must define** the policy: who needs step-up, which assurance level applies, whether user presence is required, how recent verification must be, risk conditions, and how retries/rollbacks are constrained.

If using an IdP that supports authentication levels, the application can request higher assurance via protocol parameters (such as OIDC `acr_values`/`max_age` depending on IdP capabilities), and then **verify signed and valid evidence from the IdP** according to the contract. `amr`/`acr` are not always present, and their names/values are not uniform across IdPs. **Never trust self-asserted headers like `X-MFA-Passed: true` or an unverified claim.**

Do not just set a Boolean “MFA passed” flag in JavaScript/localStorage. Factor state must be bound to the principal, login session, timestamp, method, and policy; and be securely updated/revoked upon logout, password change, session risk, or account recovery.

### 4.3. Built-In Features Do Not Mean End-to-End MFA

In versions with **one-time token login**, the mechanism to generate/consume a one-time token does not automatically turn a password login flow into “two independent factors.” If an email link can be used **instead of** a password to log in, that is **passwordless/magic-link** login, not automatically a second factor. If an authenticated factor still requires an additional factor, the application must build the policy and enforce completing that flow.

In versions with **WebAuthn**, the framework may provide endpoints/DSLs and handle the ceremony to some extent; however, key registration, credential storage, device replacement, lost-device handling, recovery, account takeover risks, and UX must still be analyzed within the scope of the actual application/IdP.

## 5. One-Time Token Login, OTP, and Magic Links: Three Things Not to Conflate

The term “OTP” is sometimes used for several different mechanisms:

| Mechanism | How the User Uses It | Key Difference |
|---|---|---|
| One-time token login / magic link | Receives a link containing a token, opens it once to log in | The token is an **access/login credential**; it must be generated, stored, delivered, and consumed securely |
| TOTP per RFC 6238 | Enters a time-varying code from an authenticator app | Based on a shared secret and clock; requires replay protection, attempt limits, and secret management |
| Email/SMS code | Enters a code sent by the server over an out-of-band channel | Depends on email/phone security and anti-abuse limits |

Newer Spring Security releases may provide a flow for the first type, but **do not assume** there is a built-in standard TOTP provider, recovery codes, email delivery, or automatic MFA policy in all versions. Choose solutions according to your threat model; if the organization already has an IdP supporting those flows, the application should usually consume results from the IdP instead of owning an entire OTP system.

### 5.1. Minimum Requirements When Implementing One-Time Codes/Links Yourself

If the problem requires the application to handle one-time tokens itself:

1. Generate tokens using a cryptographically secure random source (`SecureRandom`) with sufficient entropy; **do not use timestamps, usernames, or incrementing numbers** that make tokens predictable.
2. Store only a **hash/secure verification representation** instead of the raw token when the model supports it; design lookups properly and avoid logging tokens.
3. Enforce a **short expiration**, single use, and **atomic** consumption so two concurrent requests cannot use the same token.
4. Bind the token to the user, purpose (login/reset/step-up), and usage conditions; a password-reset token must not automatically work as an MFA verification token.
5. Rate-limit resends, attempts, IPs/devices per the threat model; reduce account enumeration via differing messages.
6. Deliver over a trusted channel and minimize leaks via referrer, logs, browser history, or analytics; after consumption, redirect to a URL without the token.
7. Provide account recovery, revocation of unused tokens, abuse blocking paths, and security auditing.

Email links risk being accessed by **email security scanners or link previews** before the user clicks them. Protocol design should avoid placing irreversible sensitive actions/logins on an automatic HTTP GET that scanners can trigger; consider an explicit confirmation step and an appropriate consumption policy.

### 5.2. What Does TOTP Require?

TOTP codes are typically based on a shared secret and a time step. Beyond the algorithm itself, a product needs:

- Initial secret enrollment/verification; activate the factor only after the user proves the authenticator is configured.
- Protecting the secret at rest, never exposing the secret again after enrollment; controlled backup/rotation.
- A bounded clock-skew acceptance window, **preventing code reuse** within the validation window, and retry limits.
- High-entropy recovery codes, stored securely and single-use; support flows must not become an MFA bypass path.
- Rules for combining with primary authentication: password + TOTP is two factors when independent and properly enforced, whereas a TOTP code alone is insufficient to satisfy every policy.

Do not equate “having a 6-digit code” with WebAuthn and conclude both have the same phishing resistance. Phishing resistance and recoverability must be evaluated separately.

## 6. Passkey/WebAuthn: Framework Version and Credential Store Responsibilities

WebAuthn uses a **public-key credential** registered with a relying party. The authenticator holds the private key; the application/IdP verifies the challenge response against the public key and required metadata.

```text
Passkey registration
 Browser + authenticator -> generate credential key pair
            |
            +--> Spring Security / WebAuthn server component
            |       verify challenge, origin, rpId
            v
     Credential repository -> store public key, credential ID,
                              user binding, required metadata

Passkey login
 Browser + authenticator -> sign challenge for the right RP
            |
            v
     Server verifies signature, challenge, origin/rpId,
     user presence/verification per policy
            |
            v
      Authentication -> authorization -> session
```

**The first question is version**: in the Spring Security 6.x branch, WebAuthn/passkey support was added in **6.4+**. An application running Boot 3.3.x managed with an older Spring Security version may **not have** the same DSL/APIs from the 6.4+ docs. Before applying online examples, check the dependency tree and the WebAuthn reference docs for your version.

**The second question is storage architecture.** A test flow working with an experimental repository does not mean you have production credential storage: you must address schema, backups, transactions, account ID, credential ID uniqueness, updating sign counters/metadata if used, credential revocation, and auditing. If a passkey is attached to an account that still has a weak email/password reset flow, recovery can downgrade overall security.

**The third question is origin boundaries.** RP ID, origin, HTTPS, local environments, reverse proxies/forwarded headers, staging/production domains, and multi-subdomain architectures must be consistent. Do not take an untrusted `Host` or `X-Forwarded-Host` header as an authoritative RP ID. Browsers enforce WebAuthn origin/rpId; the backend must validate them properly as well.

**The fourth question is authenticator type.** Platform authenticators and roaming security keys differ in UX and backup capabilities. The project must define user verification requirements, passkey syncing, device replacement, revocation, and fallback when no authenticator is available.

If an enterprise IdP already manages passkeys, the application can simply use `oauth2Login` and the trust policy negotiated with the IdP instead of building a passkey server itself. When step-up is needed, there must be a contract to verify authentication level rather than just trusting that “the user used a passkey once.”

## 7. Choosing an IdP vs. Building MFA Yourself?

### 7.1. Cases Where an IdP Is Preferred

Systems with multiple applications, enterprise users, centralized MFA/passkey/authorization requirements, conditional access, risk-based login, and device management usually benefit from integrating **OIDC/SAML 2.0** with an existing IdP.

The Servlet application receives authentication from the IdP flow and creates its own application session if needed. Spring Security helps handle the protocol and validate tokens/assertions according to configuration. However, the application still owns:

- **Account linking:** mapping stable identifiers (`issuer + subject` in OIDC) to internal users; never auto-merge solely by email.
- **Authorities/permissions:** mapping verified claims/groups to business permissions, applying deny-by-default and up-to-date permission data.
- **Step-up policy:** sensitive actions require appropriate assurance, auth age, or factors; verify the IdP actually met them.
- **Session lifecycle:** cookies, CSRF, logout, TTL, invalidation when permissions change, and concurrent active sessions.
- **Protecting business flows:** transaction reconciliation, backend authorization, auditing, and alerting.
- **Incident conditions:** IdP downtime, signing key rotation, clock skew, redirect URIs, and redirect loops.

**OAuth2 login differs from OAuth2 resource server**: `oauth2Login()` is for browser user login (OIDC when using the `openid` scope); `oauth2ResourceServer()` is for APIs receiving access tokens. Both can share an IdP, but they do not replace each other.

### 7.2. Cases Where Building In-House Makes Sense

Build in-house when the organization has specialized protocols/devices or an IdP cannot meet requirements, provided **there is a security team for long-term operations**. Responsibility boundaries must be confirmed: who issues tokens, who handles TTL/replay, who manages account recovery, who protects secrets, and who tests during Spring Security upgrades.

A custom provider is not automatically secure just because it implements `AuthenticationProvider`. The design requires proper business auditing, rate limiting, anti-enumeration, transaction-bound verification, timeout/atomic state handling, secure logging, and abuse tests.

A hybrid approach often makes sense: **the IdP authenticates the user**, while the application **enforces transaction policies itself** and calls the IdP for step-up when necessary. Do not put all payment-approval logic into a login claim that may have been issued hours earlier.

## 8. Runnable Example: Servlet Authentication Baseline on Spring Boot 3.3.x

Example goal: verify what standard Spring Security 6.x **actually provides out of the box** before adding MFA. The application has form login, BCrypt-hashed passwords, role-protected endpoints, default CSRF/session handling, and authorization tests. This is a **single-factor** baseline and does not claim to be OTP/passkey/MFA.

### 8.1. Creating the Project

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
```

Create Java package `demo.features`. File `src/main/java/demo/features/FeatureDecisionApplication.java`:

```java
package demo.features;

import java.security.Principal;
import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class FeatureDecisionApplication {
    public static void main(String[] args) {
        SpringApplication.run(FeatureDecisionApplication.class, args);
    }

    @GetMapping("/")
    public String home() {
        return "public";
    }

    @GetMapping("/account")
    public Map<String, String> account(Principal principal) {
        return Map.of("user", principal.getName(), "page", "account");
    }

    @GetMapping("/admin")
    public String admin() {
        return "admin";
    }
}
```

File `src/main/java/demo/features/SecurityConfig.java`:

```java
package demo.features;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(
            PasswordEncoder encoder, @Value("${DEMO_PASSWORD}") String password) {
        UserDetails user = User.withUsername("learner")
            .password(encoder.encode(password))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(user);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .requestMatchers("/account").authenticated()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().denyAll())
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
```

To run with the Gradle Wrapper, set the environment variable in a controlled local terminal and run:

```bash
export DEMO_PASSWORD='choose-a-long-local-demo-password'
./gradlew bootRun
```

These commands are for Bash. If using PowerShell, set the environment variable using PowerShell syntax instead of copying `export`. Do not hardcode production passwords into configuration files or commit secrets.

Opening `http://localhost:8080/` will display:

```text
public
```

Opening `http://localhost:8080/account` when not logged in: the browser is redirected to the default login page. Logging in with `learner` and the demo password returns JSON:

```json
{"page":"account","user":"learner"}
```

Field order in a JSON object is not guaranteed; the example only illustrates the values. User `learner` does not have `ROLE_ADMIN`, so accessing `/admin` returns 403. Spring Security handles login/session/authorization; a real application must still build the user store, account registration, password reset, auditing, MFA policy, and role issuance/revocation.

**Scope warning:** the example keeps default CSRF protection enabled. Do not disable `csrf` just to make POST requests “easier to test.” The password is only for a local environment, not a production identity system.

### 8.2. Testing the Policy with MockMvc

File `src/test/java/demo/features/SecurityConfigTest.java`:

```java
package demo.features;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.endsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "DEMO_PASSWORD=local-test-secret")
@AutoConfigureMockMvc
class SecurityConfigTest {
    @Autowired
    MockMvc mvc;

    @Test
    void publicPageWorksWithoutLogin() throws Exception {
        mvc.perform(get("/"))
            .andExpect(status().isOk());
    }

    @Test
    void accountRequiresLogin() throws Exception {
        mvc.perform(get("/account"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string("Location", endsWith("/login")));
    }

    @Test
    @WithMockUser(username = "learner", roles = "USER")
    void accountShowsAuthenticatedUser() throws Exception {
        mvc.perform(get("/account"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("learner"));
    }

    @Test
    @WithMockUser(username = "learner", roles = "USER")
    void normalUserCannotAccessAdmin() throws Exception {
        mvc.perform(get("/admin"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "admin-test", roles = "ADMIN")
    void adminCanAccessAdmin() throws Exception {
        mvc.perform(get("/admin"))
            .andExpect(status().isOk());
    }
}
```

Run:

```bash
./gradlew test
```

Tests using `@WithMockUser` verify **authorization rules**, not actual password authentication. To verify form login, you need separate tests sending a POST `/login` with a CSRF token and an in-memory user, or browser testing; to verify MFA, you need a **separate test suite** proving a password-only user is not allowed to access endpoints requiring a second factor.

### 8.3. Why Should the Baseline Not Be Called MFA?

In the code above, after a single password entry, Spring Security creates an authenticated `Authentication`. The `authenticated()` rule on `/account` only requires a logged-in principal; **it does not specify the number of factors**. To protect `/payments/confirm`, the project must define an additional contract: factors, timing, re-auth policy, user/session binding, bypass prevention, and recovery. If on a version with framework MFA support, configure the corresponding policy/DSL; otherwise, an IdP or a tested custom flow is the appropriate choice. Never promote an unverified authority marker as a security factor.

## 9. Designing Boundaries When Integrating Multiple Methods

An application may simultaneously support an OIDC portal, direct passkeys, API bearer tokens, and some OTP flows. However, having multiple `AuthenticationProvider`s/filters **does not automatically mean** they coordinate safely.

Architecture pattern:

```text
Browser portal
  +-- OIDC client / browser session
  +-- Step-up policy enforced by IdP or internal system
  |
Machine-to-machine API
  +-- Resource server (JWT/opaque access token)
  +-- Audience/scope + per-resource authorization
  |
Recovery / device management
  +-- Separately protected endpoint, rate limiting, and audit
  +-- Only allow factor changes after proving account ownership
```

**Split security chains by URL** when needed, using `securityMatcher(...)` and explicit chain ordering. Ensure fallbacks do not accidentally `permitAll` unmatched URLs. Avoid mixing session cookies with API bearer tokens and accepting any Authentication variant for operations requiring high assurance.

Authorization policies must still check **business permissions**. For example, a user who passes MFA but does not belong to the transaction management group still **must not** approve money transfers. MFA confirms identity evidence; authorization confirms permission to act.

## 10. Versions, Upgrades, and Operations

### 10.1. Checklist Before Enabling a New Feature

1. **Finalize requirements:** login methods, when MFA applies, which factors, recovery, assurance levels, and revocation workflow.
2. **Check the BOM:** obtain the exact resolved `spring-security-*` artifacts; verify that the feature/DSL exists in that minor version.
3. **Read version-exact reference docs:** `SecurityFilterChain`, `AuthenticationProvider`, repository, and filter ordering APIs/DSLs; do not copy newer-version examples into older projects.
4. **Check modules:** add required dependencies rather than hoping the core security starter includes SAML2, LDAP, OAuth2 client, or resource server.
5. **Draw a threat model:** account enumeration, brute-force, phishing, replay, session fixation, CSRF, XSS, proxy trust, callbacks/redirects, and account recovery.
6. **Set IdP/app boundaries:** who verifies factors, validates claims, stores secrets/certs, issues/consumes tokens, sends emails, and has reset privileges.
7. **Test on staging:** factor enrollment, valid login, invalid login, lock/revocation, lost device, concurrent requests, and IdP/DB/email downtime.
8. **Configure metrics and auditing:** success/failure, step-up challenges, recovery changes, credential add/remove, auth age, abnormal alerts.
9. **Prepare rollback and migration plans:** legacy credential data, active sessions/tokens, downtime, factor transitions across versions.
10. **Verify results:** distinguish testing Spring Security primitives from E2E browser/TLS/IdP tests; never declare a feature complete just because unit tests pass.

### 10.2. Common Upgrade Mistakes

**Mistake 1 — Using new APIs on an older project.** A WebAuthn/one-time token article written for Spring Security 6.4+ cannot be copied verbatim into Boot 3.3.x managing an older Security version. Inspect the dependency tree, then perform a compatible upgrade if needed.

**Mistake 2 — Manually bumping only `spring-security-web` while leaving other modules behind.** Mixing `spring-security-config`, `web`, `core`, and OAuth2 modules at incompatible versions can cause errors or unexpected behavior. Prefer the BOM and supported dependency management workflows.

**Mistake 3 — Confusing an authentication-producing filter with an MFA verification step.** Single-factor login does not automatically become multi-factor; step-up must be enforced at endpoints and via trusted factor state.

**Mistake 4 — Equating email OTP with TOTP or passkeys.** Each method has different threat models, independence, and phishing resistance. Criteria are needed to select methods based on account and transaction sensitivity.

**Mistake 5 — Testing only the happy path.** Lost devices, delayed email, IdP downtime, OTP reuse, permission revocation, and two concurrent consume requests are where bypasses tend to appear.

**Mistake 6 — Using recovery weaker than the primary factor.** An email reset path or support desk without ownership verification can negate the value of passkeys/MFA.

**Mistake 7 — Missing application-level authorization.** A user who just logged in via an IdP must still be denied when lacking role/resource permissions. Assurance and authorization are two independent dimensions.

**Mistake 8 — Neglecting session protection because “we already have MFA.”** CSRF, cookies, fixation, session timeout, logout, token leakage, and XSS still matter.

## 11. Testing Matrix by Release and Responsibility

| Test Group | PASS Condition | Responsible Layer |
|---|---|---|
| Dependency/version gate | Feature, DSL, and modules exist in the exact resolved version; clean build/tests | Build pipeline + framework |
| Form login + password | Valid login works, wrong password cannot log in, CSRF/session work properly | Framework + application |
| OIDC/SAML login | Issuer/signature/audience/state/nonce/redirect valid per protocol; unknown issuer rejected | IdP + Spring Security |
| Passkey enrollment | Account owner verified, RP/origin valid, credential linked to right user, revoke/recovery works | WebAuthn component + app/IdP |
| One-time token | TTL, atomic one-use, repeated requests rejected, no token leaked to logs, scanners do not trigger prematurely | Framework token service + app delivery |
| TOTP | Correct code, bounded skew window, wrong/replayed code rejected, single-use recovery codes | Auth service/app/IdP |
| MFA step-up | Password-only cannot access factor-protected pages; verified factor meeting policy grants access | Authorization policy + trusted factor state |
| Role/permission | MFA user without business permission still receives 403 | Application authorization |
| Revocation | When credential is deleted/user locked, login/actions are blocked within SLA | App/IdP/session store |
| Downtime | IdP/email/DB failures do not fall back to anonymous-but-authorized or skip factors | Service resilience |
| Multi-chain | Portal/API/recovery hit the right filter chains; safe fallback | Spring Security config + tests |
| Upgrade regression | Build, login, token checks, session, step-up, recovery, and auditing work on the new version | CI/E2E + operations |

**Mandatory step-up test example:** create a test user with password-authenticated state only; send a POST request to a sensitive endpoint with a **valid CSRF token** (so CSRF 403 is not mistaken for step-up) and verify no business state changed and the proper challenge is returned. Repeat with valid factor state and sufficient permissions; then test expired factors, switching principals, logout, replay, and locked accounts. These tests must connect to the actual factor mechanism rather than manually flipping a flag and claiming security.

## 12. Decision Rules and Key Takeaways

The selection process can be summarized in four steps:

1. **Choose who executes authentication.** If an enterprise IdP already provides MFA/passkeys, prefer standard integration with the IdP; if a specialized method is needed, evaluate the capabilities supported by your current Spring Security version.
2. **Choose APIs by exact version.** Within 6.x, do not infer that 6.4+ features exist in all 6.x releases; when moving to newer lines, review migration guides and defaults before copying code.
3. **List everything that must be built/maintained.** Enrollment, credential stores, email delivery, secret lifecycles, recovery, sessions, step-up, role mapping, auditing, and anti-abuse usually go beyond configuring a single filter.
4. **Test failure conditions.** Do not just check that “login works”; prove that users missing required factors or permissions are denied, tokens cannot be replayed, recovery is secure, and sessions can be revoked.

**Conclusion:** Spring Security Servlet provides **authentication and authorization building blocks**, with scope varying by version; the application or IdP must complete **policies, credential lifecycles, UX, recovery, and security operations**. An advanced authentication solution is only complete when both halves—version-accurate framework capabilities **and** product responsibilities—are defined, implemented, and tested.
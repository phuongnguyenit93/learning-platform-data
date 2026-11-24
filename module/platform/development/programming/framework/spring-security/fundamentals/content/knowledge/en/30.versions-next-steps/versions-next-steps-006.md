# Deep Dive into Authentication, Passwords, and Account Source Integration

## 1. Goals and Place in the Learning Path

After the Spring Security fundamentals, this deep-dive step answers three practical questions: **who is logging in**, **how the application verifies and stores credentials**, and **which system the user's identity comes from**. The goal is not just opening a login page, but understanding the authentication flow, choosing an appropriate password storage mechanism, connecting account sources, and testing failure cases.

The primary scope is **Spring Security for Servlet/Spring MVC applications**. Examples run on **Java 17 and Spring Boot 3.5.x (Spring Security 6.x)**; when moving to Boot 4/Spring Security 7, read the corresponding migration guide and re-verify dependencies, DSL, and default behaviors. Core principles such as `SecurityFilterChain`, `AuthenticationManager`, `PasswordEncoder`, and distinguishing LDAP from OIDC remain foundational knowledge. WebFlux/reactive applications use different APIs and filter chains; do not copy Servlet configurations verbatim.

**Completion criteria:** explain form login and HTTP Basic flows on your own; know how to hash passwords for storage, verification, and hash upgrades; replace in-memory users with a database; pick the right path when an organization uses LDAP or an identity provider; and design safe tests, logging, and error handling.

## 2. Authentication Does Not Equal Authorization

- **Authentication:** verifying who a principal is. For example, account `learner` provides the correct password or an IdP issues a valid login result.
- **Authorization:** after authentication, deciding whether that principal is allowed to perform an action. A successfully logged-in user can still be denied `/admin`.
- **Principal:** the identity represented after authentication; for password login it is typically `UserDetails`, for OIDC it may be `OidcUser`, and for a JWT resource server it is typically `Jwt`.
- **Credentials:** the secret/proof used for authentication. Raw passwords must remain in memory as briefly as possible; never log them, store them in sessions, or return them in APIs.
- **Authorities/roles:** permissions attached to `Authentication`. `hasRole("ADMIN")` usually checks the `ROLE_ADMIN` authority; `hasAuthority("SCOPE_read")` checks the exact authority name without prepending a prefix.

An unauthenticated request may receive **401** (especially with HTTP Basic/APIs) or **302** to a login form (browsers). An authenticated request lacking privileges typically receives **403**. The actual output depends on the authentication mechanism, content negotiation, and `AuthenticationEntryPoint`/`AccessDeniedHandler` configuration; do not assume every unauthenticated request always returns the same code.

## 3. Tracing the Authentication Flow in Spring Security

Conceptual diagram for form login or HTTP Basic:

```text
HTTP request
  -> servlet SecurityFilterChain
  -> filter reads credentials
  -> Authentication (unauthenticated)
  -> AuthenticationManager, typically ProviderManager
  -> matching AuthenticationProvider
       -> DaoAuthenticationProvider
          -> UserDetailsService loads user, hash, status, authorities
          -> PasswordEncoder.matches(rawPassword, storedHash)
  -> Authentication (succeeded, containing principal and authorities)
  -> SecurityContext, held by SecurityContextHolder during the request
  -> authorization check -> controller or 403
```

**Roles to distinguish:**

| Component | Responsibility | Common mistake |
|---|---|---|
| `SecurityFilterChain` | Selects filters and HTTP protection rules | Assuming writing a `/login` controller alone makes Spring protect the entire app |
| `AuthenticationManager` | Accepts authentication requests, returns `Authentication` or throws | Manually calling the manager in every controller when the framework already provides filters |
| `ProviderManager` | Coordinates one or more `AuthenticationProvider`s | Registering overlapping providers without clarity on which handles which token |
| `DaoAuthenticationProvider` | Authenticates username/password via user details and encoder | Writing string-based password comparisons manually |
| `UserDetailsService` | **Loads** a user by username | Thinking this service checks passwords directly |
| `PasswordEncoder` | One-way password `encode` and `matches` | Using plain MD5/SHA-256, or comparing hashes with `equals` |
| `SecurityContextHolder` | Accesses the current authentication context | Using `ThreadLocal` carelessly across async tasks assuming context propagates automatically |

With form login, Spring typically uses a session to maintain state across requests; with HTTP Basic, the client sends credentials on every request (safe only over HTTPS). With bearer tokens, the app can authenticate each request without traditional login sessions. `SecurityContext` is the current request's context; persisting and reloading it across requests depends on the configured `SecurityContextRepository` and session/token mechanism.

Failure paths: wrong password, disabled/locked/expired account, unreachable account store, wrong token audience/issuer, or missing authority are **different causes** that should be distinguished in internal logs/metrics while keeping client-facing responses minimal so they do not leak details.

## 4. Passwords: Hash, Salt, Work Factor, and Gradual Upgrades

Login passwords **must never be stored in plaintext or encrypted symmetrically for decryption**. Store a **salted one-way hash using an adaptive algorithm**: bcrypt, PBKDF2, scrypt, or Argon2. Adaptive algorithms include a cost parameter (work factor) to make bulk password guessing expensive in resources. Choose cost via benchmarks on real infrastructure, balancing latency against attack resistance; do not mechanically copy a single fixed number for every system.

Spring Security provides `PasswordEncoder` and `DelegatingPasswordEncoder`:

```java
PasswordEncoder encoder =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();

String stored = encoder.encode("study-only-123"); // example, do not write to logs
boolean ok = encoder.matches("study-only-123", stored); // true
boolean wrong = encoder.matches("incorrect", stored);  // false
```

This is an **illustrative snippet** running in a project that already has Spring Security dependencies; it is not a standalone Java program. `stored` typically looks like `{bcrypt}$2a$...`: the `{id}` prefix tells `DelegatingPasswordEncoder` which verifier to select. Each `encode` call can yield a different hash because of the random salt, so never verify via `encoder.encode(raw).equals(stored)`. Call `matches(raw, stored)`.

Correct lifecycle:

1. **Registration:** enforce password policy and abuse prevention; `encode` **once** before saving; persist the hash, never the raw password.
2. **Login:** load the user, check account status, call `matches`; only upon success establish the authenticated session under the appropriate mechanism.
3. **Password change:** re-authenticate when required, verify the old password, store the new hash, and consider revoking old sessions/tokens according to risk level.
4. **Forgot password:** send a one-time token over a verified channel with a short TTL and single-use enforcement; store only a hash of the reset token if persisted in the DB; never send the old password.
5. **Hash upgrades:** on successful login, use `PasswordEncoder.upgradeEncoding` together with `UserDetailsPasswordService`/an appropriate update flow to persist the stronger hash. Handle concurrency and avoid overwriting a password that was just changed.
6. **Migrating legacy data:** classify existing stored hashes; prepend `{id}` only when you are certain of the actual algorithm. The error `There is no PasswordEncoder mapped for the id "null"` usually indicates a hash lacks the required prefix. Never “fix” this by enabling `{noop}` for real user data.

**Remember:** never use `NoOpPasswordEncoder` or `User.withDefaultPasswordEncoder()` in production; never use fast hashes like plain SHA-256 to store passwords; never roll your own salt or hashing algorithm when standard libraries provide them.

## 5. Java 17 Lab: Authenticating with In-Memory Accounts

This lab intentionally uses a single demo user to make the flow easy to observe. Do not ship demo credentials, test endpoints, or `InMemoryUserDetailsManager` as-is to production.

Create a Maven project with this structure:

```text
security-lab/
  pom.xml
  src/main/java/com/example/securitylab/SecurityLabApplication.java
```

**`pom.xml`** — uses Spring Boot 3.5.0 to fix a concrete version for the example; real application builds must follow a supported BOM and security patches.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>security-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/com/example/securitylab/SecurityLabApplication.java`** — complete Java 17 class with `main` and the required beans:

```java
package com.example.securitylab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
@RestController
public class SecurityLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityLabApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(withDefaults())
            .httpBasic(withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        var learner = User.withUsername("learner")
            .password(encoder.encode("study-only-123"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(learner);
    }

    @GetMapping("/public")
    public String publicPage() {
        return "PUBLIC";
    }

    @GetMapping("/profile")
    public String profile(Authentication authentication) {
        return "Hello, " + authentication.getName();
    }

    @GetMapping("/admin")
    public String admin() {
        return "ADMIN";
    }
}
```

**Run** from the `security-lab` directory with JDK 17+ and Maven:

```bash
mvn test
mvn spring-boot:run
```

Open another terminal to test:

```bash
curl -i http://localhost:8080/public
curl -i -u learner:study-only-123 http://localhost:8080/profile
curl -i -u learner:wrong http://localhost:8080/profile
curl -i -u learner:study-only-123 http://localhost:8080/admin
```

Expected results in order: **200** with body `PUBLIC`; **200** with `Hello, learner`; **401** for HTTP Basic with wrong password; **403** for an authenticated user without the `ADMIN` role. When opening `/profile` in an unauthenticated browser, you will see a redirect to the default login page. The demo password in code is for learning only; production loads secrets from secure configuration sources and typically manages users via a DB/IdP.

**Explanation:** `UserDetailsService` supplies an account with `ROLE_USER`; `PasswordEncoder` creates a hash compatible with the provider; Spring Security uses filters and the manager to check the password; `SecurityFilterChain` specifies `/public` is open, `/profile` requires authentication, and `/admin` requires a different role. Form login maintains a browser session; HTTP Basic is convenient for observing with curl, yet clients send credentials every request, so use it only over TLS.

**Try next:** add an `ADMIN`-role user; replace `hasRole("ADMIN")` with `hasAuthority("ROLE_ADMIN")` and explain the equivalence; add a `POST` endpoint and observe default CSRF rather than automatically calling `csrf.disable()`.

## 6. Moving from Demo Users to Real Account Sources

Do not force every identity system into a single `UserDetailsService`. The data source and **authentication protocol** determine which adapter fits:

| Source/mechanism | Common integration | Where credentials are verified | When to choose |
|---|---|---|---|
| In-memory | `InMemoryUserDetailsManager` | Application, via `PasswordEncoder` | Demos, tests, prototypes |
| Spring's standard JDBC tables | `JdbcUserDetailsManager` | Application compares password with DB hash | Standard schema, simple requirements |
| Domain/JPA DB | Custom `UserDetailsService` + repository | Application compares with hash stored in user table | Existing schema, custom roles and statuses |
| LDAP/Active Directory | LDAP authentication provider, typically bind | Directory server | Centralized enterprise user management |
| Google/Keycloak/Okta/... via OIDC | `oauth2Login`, `OidcUserService`/mapping as needed | Identity Provider (IdP) | Federated login/SSO |
| API receiving JWT access tokens | OAuth2 Resource Server | API verifies token signature, issuer, expiry, audience | Securing APIs; **does not build its own password store** |

### 6.1. Database: Knowing the Boundary Between Domain and Spring Security

For internal accounts, a minimal table design typically includes `id`, `login` with a unique index, `password_hash`, `enabled`, lock/expiration state, and role/permission relationships. The repository only **reads** records; the `UserDetailsService` adapter converts them to `UserDetails`; `DaoAuthenticationProvider` handles password matching.

Example **illustrative adapter snippet**, assuming the application defines `AccountRepository` and `Account` with the methods shown in the code:

```java
@Service
public class AccountUserDetailsService implements UserDetailsService {
    private final AccountRepository accounts;

    public AccountUserDetailsService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    public UserDetails loadUserByUsername(String login) {
        Account a = accounts.findByLogin(login)
            .orElseThrow(() -> new UsernameNotFoundException("Unknown user"));
        return User.withUsername(a.login())
            .password(a.passwordHash())
            .disabled(!a.enabled())
            .authorities(a.authorities().toArray(String[]::new))
            .build();
    }
}
```

Appropriate Spring Security/Spring Framework types must be imported; this snippet **does not compile standalone** because the repository and entity depend on the project schema. Crucially, `passwordHash()` returns the **already-stored hash**; do not re-encode it when loading the user. `authorities()` must return normalized names such as `ROLE_USER` or specific permissions; never grant `ROLE_ADMIN` just because a client passed a `role=ADMIN` parameter. Handle username case sensitivity, account locking, caching, and permission revocation under a consistent policy.

`JdbcUserDetailsManager` fits when using the default SQL schema or appropriately configured queries; it **does not automatically know** arbitrary enterprise schemas. With JPA, define repositories and role relationships for efficient querying, avoiding lazy-loading errors outside transactions and N+1 queries; check execution plans/indexes when account counts grow large.

### 6.2. LDAP: Authenticating via Bind, Not Fetching Hashes from the Directory

When using LDAP bind, the application sends username/password to the directory over a protected connection and the directory performs authentication. **LDAP bind does not rely on `UserDetailsService` to fetch password hashes**; this is a key difference from `DaoAuthenticationProvider`. Learn about distinguished names (DN), user search base/filters, group-to-authority mapping, referrals, timeouts, LDAPS/StartTLS, and protecting the service account password. If LDAP is unavailable, fallback policies must be explicit; never silently accept logins from untrusted cached data.

### 6.3. SSO/OIDC: Identities Authenticated by an IdP

With Spring Security OAuth2 Client and `ClientRegistration` configuration, enable `oauth2Login(withDefaults())`. In the OIDC flow, the application redirects the user to the IdP, receives an authorization code, exchanges it for tokens over the back channel, and validates identity data. **Never collect users' Google/Keycloak passwords in an internal form.** Configure redirect URIs accurately; store client secrets in a controlled secret manager/environment; OIDC requires validating `issuer`, `audience`, and flow-specific checks, typically using `iss` + `sub` claims as a stable federated identifier.

Distinguish three roles:

- **OAuth2 Login client:** logs users into a web application; results may be stored in the HTTP session.
- **OAuth2 Resource Server:** verifies bearer access tokens on API calls; must validate signature, `iss`, `exp`/`nbf`, and appropriate `aud`; scopes may map to `SCOPE_*`.
- **Authorization Server/IdP:** issues tokens and executes authorization/authentication flows. Adding `oauth2Login` or `oauth2ResourceServer` to an application **does not automatically turn it into an Authorization Server**.

If local accounts must be linked to external identities, store a unique key such as `(issuer, subject)`; enforce account-linking policies with proper verification and consent. Emails can change or be unverified; **never merge two accounts automatically just because their emails match**. Distinguish **login** (authentication), **account provisioning**, **profile synchronization**, and **application authorization**; they are not the same operation.

### 6.4. When Multiple Account Sources Exist

Before configuring multiple providers, write down clearly:

1. Which usernames/tenants/realms belong to which source? Can usernames collide?
2. Who is responsible for verifying credentials? Local DB, LDAP, or IdP?
3. After authentication, where are internal authorities derived from, are they cached, and when do they expire?
4. When a user is disabled, changes departments, or loses privileges at the source, how soon does the application reflect it?
5. Are account-linking, logout, and session/token revocation flows designed appropriately for each source?

Only add a custom `AuthenticationProvider` when the protocol truly does not match mechanisms Spring Security already supports. If multiple providers support the same `Authentication` type, define ordering, selection conditions, and error handling to prevent unsafe fallbacks.

## 7. Safe Operations and Handling Edge Cases

**Login surface.** Use HTTPS for all credential/token exchanges; enforce rate limiting by account and network signals, detect credential stuffing, and keep login error responses neutral enough to reduce user enumeration. Monitor 401 and 403 rates, lockouts, IdP/LDAP errors, and hashing latency; avoid logging passwords, tokens, cookies, authorization headers, or sensitive hashes.

**Sessions and CSRF.** For cookie/session-based web apps, keep CSRF protection for state-changing actions, use `HttpOnly`, `Secure`, and appropriate `SameSite` cookie attributes, apply session-fixation/rotation protection, and implement clean logout. CSRF is distinct from CORS; **CORS does not replace authentication or CSRF**. For bearer-token APIs, define how clients store tokens, prevent XSS, and handle token expiry/refresh/revocation—do not disable CSRF globally merely because one API endpoint exists.

**Account states.** Disabled, locked, expired, credentials-expired, and lacking permissions are distinct concepts. Do not return details such as “email exists but is disabled” to unauthenticated callers; internal logs should use safe reason codes. Test concurrency around password changes or role revocations.

**Performance.** Adaptive hashing intentionally consumes CPU/RAM; set work factors based on benchmarks and real load, and avoid running password verification on every request when sessions or tokens are appropriate. For DB/LDAP/IdP sources, configure timeouts, connection pools, and circuit breakers per your architecture, and manage cache/TTL to avoid stale permissions.

**Authorization responsibility.** `@PreAuthorize`, HTTP matchers, and service-layer rules must stay consistent. Being authenticated does not grant access to every record; enforce ownership/tenant checks in the business layer. Test both horizontal access (IDOR) and role-modification privileges.

## 8. Hands-On Roadmap with Acceptance Criteria

| Phase | Tasks | Proof of completion |
|---|---|---|
| A. Trace authentication | Run demo; set breakpoints in filters/providers, observe `Authentication` before and after login | Correctly explain principal, credentials, authorities, and 200/401/403/302 |
| B. Password management | Implement safe register/login/change-password, hash with `DelegatingPasswordEncoder`, add tests for wrong passwords and legacy hashes | No plaintext in DB; `matches` works; malformed hash formats are handled safely |
| C. Source integration | Replace in-memory with a real DB; then spin up a test LDAP server or OIDC sandbox | Successful/failed login, disabled accounts, role mapping, and identity origin all have tests |
| D. Hardening & migration | Add CSRF/session controls, rate limits, safe auditing, token/role revocation, and hash migration | Integration tests, monitoring checklist, and rollback plan when changing auth mechanisms |

Follow the exercises in order:

1. **In-memory → JDBC/JPA:** create 2 accounts `reader`/`admin`, store hashes, enforce unique login; valid users get proper permissions and wrong passwords are rejected.
2. **Business authorization:** `/profile` for authenticated users; `/admin` only for `ROLE_ADMIN`; add a case where one user tries to access another user's data.
3. **Password change/reset:** test expired tokens, token reuse, new hashes, and session invalidation.
4. **Directory or OIDC:** pick **one** external mechanism matching real needs, set up a sandbox, map authorities, and test when the upstream source rejects or is unavailable.
5. **Automated testing:** use `spring-security-test` with `@WithMockUser` or MockMvc request post-processors when testing authorization; add integration tests with real authentication rather than mocking only provider results. For POSTs with CSRF, use `with(csrf())` in tests or send valid CSRF tokens from the client.

Minimum test cases to cover:

| Input | Expected result |
|---|---|
| Anonymous accessing protected resource | Redirect to login or 401, per configured mechanism |
| Valid username/password, enabled account | `Authentication` succeeds, proper authorities attached |
| Wrong password or nonexistent account | Login fails; public message does not reveal account existence |
| Disabled/locked/expired | Rejected per policy |
| User lacking role accessing admin | 403 after authentication |
| Valid legacy hash | Authenticated with matching encoder, with an upgrade path |
| LDAP/IdP error or expired/wrong issuer/audience token | No invalid session or permissions granted |
| Password change/permission revocation/logout | Session/token/cached authorities invalidated per policy |

## 9. Self-Check Comprehension Questions

**Why isn't `UserDetailsService` a “login function”?** It is responsible for loading user records so an appropriate provider can verify credentials and build `Authentication`; LDAP bind and OIDC models use different flows.

**Why does encoding the same password twice produce different strings?** The algorithm uses a random salt; use `matches` to compare a raw password against a stored hash.

**How does `hasRole("ADMIN")` differ from `hasAuthority("ADMIN")`?** `hasRole` usually checks `ROLE_ADMIN`; `hasAuthority` matches the exact string. Verify prefix configuration and authority mapping in your application.

**When an application receives a JWT from an IdP, is it implementing an OAuth2 login page?** Not necessarily. A Resource Server validates access tokens on API requests; OAuth2/OIDC Login handles user login flows into an application.

**When an employee is disabled in LDAP/IdP, do application permissions vanish immediately?** That depends on session duration, token lifetime, caching, and sync/revocation mechanisms. You need an explicit policy and tests—never assume instant propagation automatically.

## 10. Official Documentation for Further Learning

- [Servlet Authentication Architecture — Spring Security](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Username/Password Authentication, UserDetailsService, JDBC, LDAP — Spring Security](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/index.html)
- [Password Storage and DelegatingPasswordEncoder — Spring Security](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html)
- [LDAP Authentication — Spring Security](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html)
- [OAuth2 Login and OIDC — Spring Security](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [OAuth2 Resource Server — Spring Security](https://docs.spring.io/spring-security/reference/servlet/oauth2/index.html)
- [Testing CSRF with MockMvc — Spring Security](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)
- [Spring Boot system requirements and migration](https://docs.spring.io/spring-boot/reference/)

After these exercises, learners should be able to describe the **source of truth for identity**, **how credentials are verified**, **how authorities are granted and revoked**, the **password/session/token lifecycle**, and **testing evidence** for their own application.
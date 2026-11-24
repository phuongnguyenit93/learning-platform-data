# Completed Factors and Insufficient Authentication State (MFA in Spring Security)

## 1. Objectives and Core Question

A user enters the correct password and has logged into the application. Should they immediately be allowed to open the page to change bank account details, create an admin API key, change the recovery email, or export sensitive data? **Not necessarily.** The application may require an additional second authentication factor, or require an already-completed factor to be sufficiently fresh within a few minutes.

This is the key point of Multi-Factor Authentication (**MFA**): the **“authenticated”** state and the **“has reached the authentication level required by the resource”** state are not always the same.

For example: the user has a valid password but has not verified a one-time token (OTT). Basic login succeeded, yet an endpoint requiring two factors is **still disallowed**. The application should guide the user to the missing step (step-up) without forcing them to reinitialize everything unnecessarily.

After this lesson, you can:

1. Distinguish `Authentication.isAuthenticated()`, `ROLE_*`, `FactorGrantedAuthority`, and the MFA requirements of each endpoint.
2. Identify the lists of **completed factors**, **missing factors**, and **expired factors**.
3. Interpret partial states in the password → OTT/WebAuthn flow, what is held in `SecurityContext`, and why full privileges must not be granted after the first step.
4. Use the official MFA features of **Spring Security 7.x**: `@EnableMultiFactorAuthentication`, `FactorGrantedAuthority`, `AuthorizationManagerFactories.multiFactor()`.
5. Create policies enforcing MFA application-wide or only for critical pages; configure `validDuration`, per-user conditions, and alternative method combinations.
6. Know compatibility limits with Spring Security 6.x, WebFlux, and risks around sessions, reauthentication, and recovery.
7. Write and test an illustrative model in Java 17+, then connect it to a real Spring Security Servlet flow.

**Focus:** not a tutorial on every type of OTP/passkey from scratch, but **how to track the evidence already obtained and handle cases where that evidence does not yet satisfy the access policy**.

## 2. “Successful Login” Differs from “Sufficient Level to Access a Resource”

In Spring Security, `Authentication` describes the principal, authorities, and the result of an authentication mechanism. After a successful password login, `isAuthenticated()` can be `true`. That proves **password authentication was accepted**; it does not by itself prove the user completed additional factors.

Several roles and components:

| State/Component | Answers the Question | Does It Replace MFA? |
| --- | --- | --- |
| `Authentication.isAuthenticated()` | Is there a successful Authentication? | **No**. Does not know which factors an endpoint requires |
| `ROLE_ADMIN` | Has the application granted the admin role to the principal? | **No**. A role is a business privilege, not login evidence |
| `FACTOR_PASSWORD` | Was the user authenticated with a password via a supported mechanism? | **One piece of evidence**, not the entire policy |
| `FACTOR_OTT` | Did the user complete authentication via one-time token? | **Another piece of evidence**; token provenance determines actual trustworthiness |
| `FactorGrantedAuthority.getIssuedAt()` | When was the factor authenticated? | Used to check freshness; does not itself specify validity duration |
| `AuthorizationManager` / MFA policy | Which roles, factors, and freshness window does the resource require? | This is where sufficiency is decided for a **specific resource** |
| `SecurityContext` and session | How is evidence/Authentication persisted on subsequent requests? | Must not escalate privileges or extend factor validity beyond policy |

**Further distinction:** a user having enrolled a passkey or enabled MFA in their profile **does not** mean they just completed login using a passkey or second factor. *Registration/enrollment state* and *authentication-completed state* are two different pieces of data.

An easy-to-visualize model:

```text
Identity:             learner
Application roles:    [ROLE_USER, ROLE_ADMIN]

Completed factors (evidence):
    FACTOR_PASSWORD  issuedAt = 11:45
    FACTOR_OTT       missing

Endpoint /profile:
    requires authenticated                   -> SUFFICIENT

Endpoint /admin/export:
    requires ROLE_ADMIN + FACTOR_PASSWORD
    (within 10 min) + FACTOR_OTT (within 5 min)
                                             -> INSUFFICIENT
    missing OTT; password is also too old
```

For sensitive endpoints, **authorization must fail-closed** if a required factor is missing, too old, or belongs to a different session/user.

## 3. How Does Spring Security 7 Record Completed Factors?

Starting in **Spring Security 7.0**, the framework includes a built-in MFA model using `FactorGrantedAuthority`. This is a form of `GrantedAuthority` that carries an `issuedAt` timestamp rather than just a string authority name.

Constants used in Spring documentation:

| Constant | Authority string | Corresponding Mechanism |
| --- | --- | --- |
| `FactorGrantedAuthority.PASSWORD_AUTHORITY` | `FACTOR_PASSWORD` | Password authentication |
| `FactorGrantedAuthority.OTT_AUTHORITY` | `FACTOR_OTT` | Spring's One-Time Token Login |
| `FactorGrantedAuthority.WEBAUTHN_AUTHORITY` | `FACTOR_WEBAUTHN` | WebAuthn/passkey |
| `FactorGrantedAuthority.BEARER_AUTHORITY` | `FACTOR_BEARER` | Bearer token mechanism, not automatically synonymous with MFA |
| `FactorGrantedAuthority.AUTHORIZATION_CODE_AUTHORITY` | `FACTOR_AUTHORIZATION_CODE` | OAuth2 Authorization Code login |
| `FactorGrantedAuthority.X509_AUTHORITY` | `FACTOR_X509` | X.509 client certificate authentication |

The list gives examples of Spring-supported factors; depending on the release, there may be additional constants or integrations. **Do not confuse `FACTOR_*` with `ROLE_*` or `SCOPE_*`:** a factor records *how identity was proven*, whereas roles/scopes generally relate to *resource usage permissions*.

### 3.1. Factor Timestamps

The API documentation shows creating a `FactorGrantedAuthority` as follows:

```java
// Snippet for Spring Security 7.x:
FactorGrantedAuthority proof = FactorGrantedAuthority
    .withAuthority(FactorGrantedAuthority.PASSWORD_AUTHORITY)
    .issuedAt(Instant.now())
    .build();

String authority = proof.getAuthority();
Instant completedAt = proof.getIssuedAt();
```

The two imports are `java.time.Instant` and `org.springframework.security.core.authority.FactorGrantedAuthority`. This code only illustrates the data type; **never construct a “completed” factor from request headers or user input** before the corresponding authentication mechanism genuinely succeeds.

`issuedAt` records when the evidence was issued. The authority itself **does not declare “valid for 30 minutes”**: the same password authentication might be fresh enough for the profile page (30 minutes) yet not fresh enough for the funds transfer page (5 minutes). Expiration is enforced **in each resource's authorization policy**.

### 3.2. You Cannot Self-Mark Completion

The following code is a **security vulnerability**:

```java
// WRONG: sees X-MFA-Done header and self-grants factor authority.
String done = request.getHeader("X-MFA-Done");
if ("true".equals(done)) {
    authorities.add(
        FactorGrantedAuthority.fromAuthority("FACTOR_OTT"));
}
```

A client header is not evidence that the user verified an OTT. Only a trusted authentication mechanism (or an adapter that has verified evidence from an IdP under a strict contract) may add a factor.

**Proper technique:** the password filter/provider verifies the password; the one-time token filter/provider verifies the single-use consumed token; the WebAuthn server verifies the challenge, origin, and signature. After each mechanism succeeds, the framework has a sound basis to update the satisfied factors.

## 4. State Transition Diagram for “Insufficient Authentication Level”

Consider an application policy: viewing `/profile` requires any valid authentication; entering `/settings/security` requires password **and** OTT; entering `/admin/export` additionally requires `ROLE_ADMIN`.

```text
                              [ANONYMOUS]
                                  |
                          enter username/password
                                  |
                            verify password
                                  v
             [AUTHENTICATED: FACTOR_PASSWORD]
                 |                    |
                 | GET /profile       | GET /settings/security
                 v                    v
              ALLOWED          INSUFFICIENT MFA
                                      |
                         missing FACTOR_OTT
                                      |
                       challenge / step-up redirect
                                      |
                         user obtains valid OTT
                                      |
                               verify OTT
                                      v
          [AUTHENTICATED: FACTOR_PASSWORD + FACTOR_OTT]
                                      |
                     check role, freshness, session
                                      |
                         GET /settings/security
                                      v
                                   ALLOWED
```

**Partial authentication does not mean anonymous.** After password login, the account is identified; the user may be allowed to perform low-risk tasks. Only when accessing a sensitive page is additional evidence required.

**It does not always have to be password before OTT.** Spring Security 7 can determine which factor is missing and direct the user to the appropriate mechanism; the documentation describes cases where a user who completes OTT first is directed back to password login. Product policy may enforce a specific order or other constraints, but must never mark a step as “completed” before it occurs.

### 4.1. Policy Matrix

Assume all factors are still within their validity window:

| Available Evidence | `/profile` needs authenticated | `/settings` needs password + OTT | `/admin` needs password + OTT + ROLE_ADMIN |
| --- | --- | --- | --- |
| None | Deny or redirect to login | Deny or login | Deny or login |
| Password only | Allow | Missing OTT → step-up | Missing OTT, and possibly missing role |
| OTT only | May be authenticated in an eligible flow | Missing password → step-up | Missing password, and possibly missing role |
| Password + OTT | Allow | Allow | Only when `ROLE_ADMIN` is present |
| Password + OTT but OTT expired per policy | Allow if no extra constraint | Require fresh OTT verification | Require fresh OTT, and still need role |
| Has `ROLE_ADMIN` but password only | Allow | Missing OTT | **Must not bypass MFA just because of admin role** |

This is the **logical outcome of the sample policy**. The final HTTP response may be a `302` redirect to the missing mechanism, `401`, or `403` depending on the client type and configured `AuthenticationEntryPoint`/AccessDeniedHandler. Do not claim every “missing factor” state must return 401.

### 4.2. Distinguishing Four Types of Insufficient State

1. **No authentication at all:** anonymous request, needs a login method.
2. **Authenticated but missing a required factor:** e.g., password done, OTT not yet done.
3. **All factor types present but evidence is too old:** requires reauthentication/step-up per `validDuration`.
4. **All factors present but missing business privileges:** e.g., lacks `ROLE_ADMIN`. Providing OTT **does not** resolve a missing-role error.

UI/monitoring can present these states clearly to users/support, but internal details must be masked when the caller is unauthenticated to avoid leaking account existence or overly detailed policies.

## 5. Why Is “Authentication Level” a Per-Resource Requirement?

Every request should not be hardcoded to the same authentication level. A product might specify:

- Viewing a normal profile page: authenticated user.
- Changing a shipping address: fresh password or passkey.
- Viewing API keys, changing security email: password + independent factor.
- Performing a large financial operation: strong factors, tight time window, and potentially binding to the specific transaction.
- Admin acting on another user: MFA + `ROLE_ADMIN` + tenant/object ownership check.

This is **step-up authentication**: requiring additional evidence only when the risk level of the action demands it. Do not use a “MFA enabled” flag in the user profile in place of evaluating recently issued factors.

A policy can be expressed with these parts:

```text
RequiredAuthenticationLevel(resource, subject, action, risk):
    identity must be authenticated
    required business roles/scopes must match
    required factor combinations must be satisfied
    each required factor must be fresh enough
    application/tenant/device/risk constraints must pass
```

Spring Security 7 provides very helpful factor-authorization organization; business policies such as transfer limits or transaction signing requirements **still belong in the business layer**.

## 6. Versions and Dependencies: Spring Security 7 vs. 6.5

This is important when learning or practicing because the APIs differ significantly:

| Stack | Built-In MFA Status | Implementation Approach |
| --- | --- | --- |
| **Spring Security 6.5 / Spring Boot 3.5** | Has password, OTT, WebAuthn individually; **lacks 7.x's factor-aware MFA model and `@EnableMultiFactorAuthentication` annotation** | Write custom state machine/policy or upgrade; do not copy 7.x imports into a 6.5 app |
| **Spring Security 7.0–7.1 / Spring Boot 4.x** | Has `FactorGrantedAuthority`, `@EnableMultiFactorAuthentication`, and `AuthorizationManagerFactories.multiFactor()` for Servlet | Use official MFA APIs with Web Security/AuthorizationManager |
| **Reactive WebFlux** | In Spring Security 7.0/7.1 docs, the new MFA annotations **do not yet apply equivalently to the reactive stack** | Do not drop a Servlet `SecurityFilterChain` into `SecurityWebFilterChain`; check your reactive version and build a dedicated policy |

Spring Security 7.0 introduced MFA as a new feature (Spring blog on **21/10/2025**), so if your IDE reports `FactorGrantedAuthority` or `@EnableMultiFactorAuthentication` is missing, check the **actual major version** before changing imports.

**Java:** Spring Boot 4 still maintains a Java 17 baseline while supporting newer JDKs. Examples use Java 17 with Spring Boot `4.0.9` (released October 2026), Spring Framework 7, and Spring Security 7.x via Boot's BOM. In new systems, prefer your organization's current patch branch.

Example Maven dependencies on Boot 4:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webmvc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-mail</artifactId>
    </dependency>
</dependencies>
```

In Boot 4.x, `spring-boot-starter-webmvc` is the explicit starter for Servlet MVC; do not take old examples and assume all dependencies/modules/test packages match Boot 3.x. **No separate “MFA starter” is needed** to get `FactorGrantedAuthority` once Spring Security 7 config/web/core is brought in by the corresponding starter/BOM. OTT requires a **reliable token delivery system** (email, SMS, or another channel), which Spring Security **cannot provide automatically** on behalf of your application.

Practical verification:

```bash
mvn dependency:tree -Dincludes=org.springframework.security
mvn dependency:tree -Dincludes=org.springframework.boot
mvn -v
```

Do not mix Spring Security 7 artifacts into Boot 3.x or pin Spring Framework versions outside the BOM without technical justification.

## 7. Configuring MFA in Spring Security 7: Three Approaches

### 7.1. Enforcing Password + OTT Across All Authorization Rules

According to Spring Security 7 documentation, the shortest way is:

```java
// @Configuration snippet in a Spring Security 7.x application
@EnableMultiFactorAuthentication(authorities = {
    FactorGrantedAuthority.PASSWORD_AUTHORITY,
    FactorGrantedAuthority.OTT_AUTHORITY
})
class GlobalMfaConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .oneTimeTokenLogin(Customizer.withDefaults())
            .build();
    }
}
```

Corresponding imports: `org.springframework.security.config.annotation.authorization.EnableMultiFactorAuthentication` and `org.springframework.security.core.authority.FactorGrantedAuthority`. This is a **Spring config snippet**; you need the application wiring, user store, and OTT delivery as in section 9 for a runnable app.

Meaning:

- `/admin/**` requires `ROLE_ADMIN + FACTOR_PASSWORD + FACTOR_OTT`.
- Routes using `authenticated()` also require both factors via the global factory.
- `permitAll()` and special mechanisms do not automatically become new logins; MFA enforcement applies via the authorization rules wrapped by the factory.
- With multiple `SecurityFilterChain`s and method security, verify factory/annotation scope and test exactly which routes are protected.

### 7.2. Requiring MFA Only on Sensitive Endpoints (Selective MFA)

Not every app should require two factors on every page. Spring Security supports keeping ordinary routes at `authenticated()` while sensitive routes use a dedicated factory.

```java
// Spring Security 7.x configuration snippet:
@EnableMultiFactorAuthentication(authorities = {})
class SelectiveMfaConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        var mfa = AuthorizationManagerFactories.multiFactor()
            .requireFactors(
                FactorGrantedAuthority.PASSWORD_AUTHORITY,
                FactorGrantedAuthority.OTT_AUTHORITY)
            .build();

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/admin/**")
                    .access(mfa.hasRole("ADMIN"))
                .requestMatchers("/settings/security/**")
                    .access(mfa.authenticated())
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .oneTimeTokenLogin(Customizer.withDefaults())
            .build();
    }
}
```

Note that `@EnableMultiFactorAuthentication(authorities = {})` **enables MFA support without creating a global factor requirement**. `mfa` is only a local variable, not published as an `AuthorizationManagerFactory` Bean. If published as a Bean, other authorization rules could have MFA applied more broadly than intended.

Meaning: `/profile` only requires login; `/settings/security/**` requires password+OTT; `/admin/**` requires password+OTT+role. This model most closely matches “already has some factors, but not yet sufficient for a specific screen”.

### 7.3. Per-User or Time-Based Factor Requirements

When a product uses opt-in MFA or has privileged users, avoid writing manual filters. Spring Security provides `AuthorizationManagerFactories.multiFactor().when(...)` and `RequiredAuthoritiesRepository` to determine requirements per user or account settings.

**Illustrative** configuration example:

```java
// A factory Bean that applies globally when present in the context:
@Bean
AuthorizationManagerFactory<Object> policy() {
    return AuthorizationManagerFactories.multiFactor()
        .requireFactors(
            FactorGrantedAuthority.PASSWORD_AUTHORITY,
            FactorGrantedAuthority.OTT_AUTHORITY)
        .when(auth -> "admin".equals(auth.getName()))
        .build();
}
```

If conditions rely on username, consider username changes, impersonation, and multi-tenancy; usually looking up by a stable user ID or trusted account security policy is better than hardcoding `"admin"`.

**Validity duration:** Spring Security supports:

```java
// Snippet only: password must be fresh within 10 minutes
var freshPassword = AuthorizationManagerFactories.multiFactor()
    .requireFactor(factor -> factor
        .passwordAuthority()
        .validDuration(Duration.ofMinutes(10)))
    .build();
```

Different policies can set different `validDuration`s for the same `FACTOR_PASSWORD`. Never mutate the timestamp inside `FactorGrantedAuthority` to “refresh” a factor; **genuine reauthentication** must be required again.

## 8. Standalone Java 17: Clearly Seeing Missing and Expired Factors

Before integrating Spring, you can simulate “completed factors” and “endpoint requirements” in plain Java 17. The program below **runs without Maven** and produces deterministic output. It is **not a replacement implementation for Spring MFA**; its purpose is to clarify the logic and test edge cases.

Create the file `MfaFactorStateDemo.java`:

```java
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;

public class MfaFactorStateDemo {

    record Proof(String authority, Instant issuedAt) {}

    record Required(String authority, Duration validFor) {}

    static List<String> missingOrExpired(
            List<Required> required,
            List<Proof> completed,
            Instant now) {

        List<String> problems = new ArrayList<>();

        for (Required requirement : required) {
            Optional<Proof> latest = completed.stream()
                .filter(p -> p.authority().equals(
                    requirement.authority()))
                .max(Comparator.comparing(Proof::issuedAt));

            if (latest.isEmpty()) {
                problems.add(requirement.authority() + ":MISSING");
            } else {
                Instant issued = latest.get().issuedAt();
                Instant deadline = issued.plus(
                    requirement.validFor());
                if (issued.isAfter(now) || !now.isBefore(deadline)) {
                    problems.add(requirement.authority() + ":EXPIRED");
                }
            }
        }
        return problems;
    }

    static String state(List<String> problems) {
        return problems.isEmpty()
            ? "GRANTED"
            : "DENIED " + problems;
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-01-01T12:00:00Z");

        List<Proof> completed = new ArrayList<>();
        completed.add(new Proof(
            "FACTOR_PASSWORD",
            Instant.parse("2026-01-01T11:45:00Z")));

        List<Required> profile = List.of(
            new Required("FACTOR_PASSWORD",
                         Duration.ofMinutes(30)));

        List<Required> admin = List.of(
            new Required("FACTOR_PASSWORD",
                         Duration.ofMinutes(10)),
            new Required("FACTOR_OTT",
                         Duration.ofMinutes(5)));

        System.out.println("profile: " + state(
            missingOrExpired(profile, completed, now)));

        System.out.println("admin before OTT: " + state(
            missingOrExpired(admin, completed, now)));

        completed.add(new Proof("FACTOR_OTT", now));

        System.out.println("admin after OTT: " + state(
            missingOrExpired(admin, completed, now)));

        completed.add(new Proof("FACTOR_PASSWORD", now));

        System.out.println("admin after refresh: " + state(
            missingOrExpired(admin, completed, now)));
    }
}
```

Compile/run:

```bash
javac --release 17 MfaFactorStateDemo.java
java MfaFactorStateDemo
```

**Exact stdout:**

```text
profile: GRANTED
admin before OTT: DENIED [FACTOR_PASSWORD:EXPIRED, FACTOR_OTT:MISSING]
admin after OTT: DENIED [FACTOR_PASSWORD:EXPIRED]
admin after refresh: GRANTED
```

Explanation:

- Password 15 minutes ago: fresh enough for `/profile` (30-minute limit) yet too old for `/admin` (10-minute limit).
- User completes OTT: `FACTOR_OTT` is newly proven, but password has not been “auto-refreshed”.
- Only when password is genuinely reauthenticated are both factors fresh enough and `/admin` requirements satisfied.
- In a real product, this check must also combine roles, account status, and resource checks; this example focuses only on factor timestamps.
- At the exact boundary `issuedAt + validDuration`, the program treats the factor as expired to **fail-closed**.

Do not copy `missingOrExpired` into a project and synthesize `Proof` from client input. Spring Security already provides `FactorGrantedAuthority` and authorization managers to handle evidence created by trusted authentication.

## 9. Spring Boot 4 / Java 17 Application: Password Then OTT Experience

This is a Spring Boot **4.0.9** / Spring Security **7.x** example for Servlet MVC, demonstrating an account that has both a role and an insufficient-factor state. It uses **selective MFA** so `/profile` is reachable after password login, while `/settings/security` requires password+OTT.

Because OTT must be **delivered to the account owner**, the example configures secure SMTP via environment variables and an email address fixed server-side for user `learner`. Without a test SMTP server, the app can start and accept password login, but **cannot complete OTT delivery**. This is a real infrastructure requirement; never “demo” it by returning the token in a public HTTP response.

### 9.1. Project Structure

```text
mfa-factor-state/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/mfa/MfaApplication.java
    │   └── resources/application.yml
    └── test/
        └── java/demo/mfa/MfaApplicationTests.java
```

### 9.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.9</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>mfa-factor-state</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-mail</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
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

MVC/testing modules follow Boot 4 packaging; do not use the Boot 3 import path `org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc` in Boot 4 tests.

### 9.3. `application.yml`

```yaml
server:
  port: 8080

spring:
  mail:
    host: "${SMTP_HOST}"
    port: "${SMTP_PORT:587}"
    username: "${SMTP_USERNAME}"
    password: "${SMTP_PASSWORD}"
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000

app:
  demo:
    password: "${DEMO_PASSWORD}"
    recipient-email: "${DEMO_RECIPIENT_EMAIL}"
    sender-email: "${DEMO_SENDER_EMAIL}"
    public-base-url: "${PUBLIC_BASE_URL:http://localhost:8080}"
```

The service requires an SMTP server capable of delivering mail to the account owner. Environment variables must be configured in a secret manager or a dev environment with an SMTP sink; never commit passwords/mail credentials to Git.

### 9.4. `MfaApplication.java`

```java
package demo.mfa;

import java.security.Principal;
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.security.authorization.AuthorizationManagerFactories;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.authorization.EnableMultiFactorAuthentication;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.authority.FactorGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.ott.OneTimeTokenGenerationSuccessHandler;
import org.springframework.security.web.authentication.ott.RedirectOneTimeTokenGenerationSuccessHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.util.UriComponentsBuilder;

@SpringBootApplication
@EnableWebSecurity
@EnableMultiFactorAuthentication(authorities = {})
@RestController
public class MfaApplication {

    public static void main(String[] args) {
        SpringApplication.run(MfaApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            @Value("${app.demo.password}") String password) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode(password))
            .roles("ADMIN")
            .build();
        return new InMemoryUserDetailsManager(learner);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            OneTimeTokenGenerationSuccessHandler delivery)
            throws Exception {

        var highAssurance = AuthorizationManagerFactories.multiFactor()
            .requireFactors(
                FactorGrantedAuthority.PASSWORD_AUTHORITY,
                FactorGrantedAuthority.OTT_AUTHORITY)
            .build();

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public", "/ott/sent").permitAll()
                .requestMatchers("/admin/**")
                    .access(highAssurance.hasRole("ADMIN"))
                .requestMatchers("/settings/**")
                    .access(highAssurance.authenticated())
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .oneTimeTokenLogin(ott ->
                ott.tokenGenerationSuccessHandler(delivery))
            .build();
    }

    @Bean
    OneTimeTokenGenerationSuccessHandler delivery(
            JavaMailSender sender,
            @Value("${app.demo.recipient-email}") String receiver,
            @Value("${app.demo.sender-email}") String from,
            @Value("${app.demo.public-base-url}") String publicBaseUrl) {

        var redirect =
            new RedirectOneTimeTokenGenerationSuccessHandler("/ott/sent");

        return (request, response, token) -> {
            // The demo has a single local user; receiver is not taken from
            // a request parameter that an untrusted caller could modify.
            if ("learner".equals(token.getUsername())) {
                String link = UriComponentsBuilder
                    .fromUriString(publicBaseUrl)
                    .path("/login/ott")
                    .queryParam("token", token.getTokenValue())
                    .toUriString();

                SimpleMailMessage mail = new SimpleMailMessage();
                mail.setFrom(from);
                mail.setTo(receiver);
                mail.setSubject("Your one-time sign-in link");
                mail.setText("Use this link to finish authentication:\n"
                    + link);
                sender.send(mail);
            }
            redirect.handle(request, response, token);
        };
    }

    @GetMapping("/")
    Map<String, String> home() {
        return Map.of(
            "login", "/login",
            "profile", "/profile",
            "mfaProtected", "/settings/security");
    }

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/ott/sent")
    String sentPage() {
        return "If eligible, a sign-in link has been sent.";
    }

    @GetMapping("/profile")
    String profile(Principal principal) {
        return "profile:" + principal.getName();
    }

    @GetMapping("/settings/security")
    String securitySettings(Principal principal) {
        return "security:" + principal.getName();
    }

    @GetMapping("/admin/export")
    String admin(Principal principal) {
        return "admin:" + principal.getName();
    }
}
```

**Reading the configuration:**

- `@EnableMultiFactorAuthentication(authorities = {})` enables MFA support without forcing factors onto every rule.
- `highAssurance.authenticated()` requires the user to be authenticated **and** have `FACTOR_PASSWORD` + `FACTOR_OTT` on `/settings/**`.
- `highAssurance.hasRole("ADMIN")` additionally requires `ROLE_ADMIN` on `/admin/**`.
- `/profile` only uses `authenticated()`, so it can be accessed after the password step even without OTT.
- Both `formLogin()` and `oneTimeTokenLogin()` are configured so Spring has mechanisms to prompt for any missing factor.
- Spring Security creates/verifies the one-time token and orchestrates login; the `delivery` bean only **sends the token** to the channel bound to the account.
- The link includes the one-time token in the query string to support the default OTT login page, following Spring documentation samples. Avoid logging query strings, set `Referrer-Policy: no-referrer`, and control URLs/caching/tracing. Never derive `publicBaseUrl` from arbitrary client headers.

**Production limitations:** the in-memory user store and default in-memory OTT service are for demo only. A real product requires an account repository, `JdbcOneTimeTokenService` or a multi-node consistent store, TLS, secure SMTP, rate limiting, and an email-verified/recovery policy. **Do not turn this code into production merely by swapping the SMTP address.**

### 9.5. Running and Observing the Two Access Levels

On a host with Java 17+, Maven, and a test/relay SMTP server:

```bash
export DEMO_PASSWORD='a-strong-local-test-password'
export DEMO_RECIPIENT_EMAIL='learner@example.test'
export DEMO_SENDER_EMAIL='no-reply@example.test'
export SMTP_HOST='smtp.example.test'
export SMTP_PORT='587'
export SMTP_USERNAME='smtp-user'
export SMTP_PASSWORD='smtp-credential'
export PUBLIC_BASE_URL='http://localhost:8080'

mvn spring-boot:run
```

The `example.test` addresses are **illustrative values**, not real SMTP servers; you must use an SMTP server/addresses you control. Only run plain HTTP on loopback during development; real deployments must use HTTPS and an accurate `PUBLIC_BASE_URL`.

In the browser:

1. Open `http://localhost:8080/profile`; you are redirected to `/login`.
2. Log in with `learner` and the configured test password: `/profile` returns `profile:learner`.
3. Open `/settings/security`: because only password is present, Spring Security routes the user through the **OTT step-up** flow or corresponding page instead of allowing immediate access.
4. From the OTT page, submit a request to generate a one-time token for `learner`. Spring requires a CSRF token for the token-generation POST.
5. Check the email sent to the mailbox bound to the account, open the link in the same session/browser as required by the login flow, and complete OTT.
6. Return to `/settings/security`: if both factors are valid, you receive `security:learner`.
7. Visit `/admin/export`: with the ADMIN role and sufficient factors, you receive `admin:learner`. A regular user who has the factors but lacks `ROLE_ADMIN` is still denied.

**Never implement a public “/debug/get-ott” endpoint.** That would turn the second factor into a secret any caller can fetch, rendering MFA meaningless.

OTT in Spring is **One-Time Token Login** (typically sending a magic link), which differs from a 6-digit TOTP/HOTP generated by an authenticator app. If an enterprise uses TOTP, that is a separate integration; do not claim `FACTOR_OTT` merely because a text field takes six digits.

## 10. Testing Insufficient/Sufficient Factor States in Spring

You cannot simply use `@WithMockUser(roles = "ADMIN")` to prove MFA is complete. It creates a mock principal/authorities for basic authorization tests and **does not perform actual password/OTT steps**.

In Spring Security 7, `AllRequiredFactorsAuthorizationManager` inspects `FactorGrantedAuthority` evidence and timestamps, not just an arbitrary `"FACTOR_OTT"` string. To unit-test authorization rules, you can construct a mock Authentication **clearly marked as test data** using the factor builder:

```java
package demo.mfa;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.FactorGrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "app.demo.password=test-password",
    "app.demo.recipient-email=learner@example.test",
    "app.demo.sender-email=sender@example.test",
    "app.demo.public-base-url=http://localhost:8080",
    "spring.mail.host=localhost",
    "spring.mail.port=1025"
})
@AutoConfigureMockMvc
class MfaApplicationTests {

    @Autowired
    MockMvc mvc;

    private static Authentication evidence(boolean withOtt) {
        List<GrantedAuthority> authorities = new ArrayList<>();
        authorities.add(new SimpleGrantedAuthority("ROLE_ADMIN"));
        authorities.add(
            FactorGrantedAuthority.withAuthority(
                FactorGrantedAuthority.PASSWORD_AUTHORITY)
                .issuedAt(Instant.now()).build());

        if (withOtt) {
            authorities.add(
                FactorGrantedAuthority.withAuthority(
                    FactorGrantedAuthority.OTT_AUTHORITY)
                    .issuedAt(Instant.now()).build());
        }

        return UsernamePasswordAuthenticationToken.authenticated(
            "learner", null, authorities);
    }

    @Test
    void publicPageIsAnonymousFriendly() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void profileNeedsOnlyFirstFactor() throws Exception {
        mvc.perform(get("/profile")
                .with(authentication(evidence(false))))
            .andExpect(status().isOk())
            .andExpect(content().string("profile:learner"));
    }

    @Test
    void completedFactorsUnlockProtectedEndpoint() throws Exception {
        mvc.perform(get("/settings/security")
                .with(authentication(evidence(true))))
            .andExpect(status().isOk())
            .andExpect(content().string("security:learner"));
    }

    @Test
    void bothFactorsPlusRolePermitAdmin() throws Exception {
        mvc.perform(get("/admin/export")
                .with(authentication(evidence(true))))
            .andExpect(status().isOk())
            .andExpect(content().string("admin:learner"));
    }
}
```

Run:

```bash
mvn test
```

Expected: **4 tests pass** when the project/build/Bean configuration is properly set up. These tests **do not send mail** and **do not use real OTT codes**: they inject an Authentication with freshly issued factor authorities directly to verify MVC authorization rules.

**You must test the missing-factor state** with a request that has password but no OTT; however, do not hardcode an assertion that the result is always 403: by default Spring Security 7 may **redirect to the OTT step** based on the missing factor. In a browser UI, check the Location header and continuation; for JSON APIs, configure the entry point/denied handler per API contract to return 401/403 + `step_up_required` status without leaking secrets.

To prove MFA **actually works**, you need an integration test covering password login → generating OTT → delivery to a test mailbox → consuming the token → verifying authorities and sensitive route access. The MockMvc tests above only verify policy, not mail channel security, token expiry, CSRF, or account ownership.

## 11. When a Factor Is Completed but Too Old

A factor may still be recorded in Authentication, yet its time policy has expired:

```text
12:00 Password authentication succeeds
12:01 OTT authentication succeeds
12:05 /profile                         -> ALLOWED
12:20 /settings/security:
      requires password within 10 min
      and OTT within 5 min             -> INSUFFICIENT (both too old)
12:21 Password reauthentication      -> HAS fresh password
      OTT not yet re-verified          -> STILL INSUFFICIENT
12:22 OTT reauthentication           -> HAS both fresh
      /settings/security             -> ALLOWED
```

This diagram illustrates a **freshness** policy, not an automatic default timeout for every factor. Spring Security separates `issuedAt` and `validDuration` so different endpoints can apply different requirements.

**Boundary notes:**

- When server clocks drift out of sync, timestamps and TTLs can be miscalculated. Use a consistent time source, test boundary cases, and synchronize with NTP.
- Never reset `issuedAt` merely because the session was extended or the browser sent a new request.
- Once one factor is refreshed, policy considers only **that factor** fresh; never implicitly refresh other factors.
- A user still holding a valid session **does not mean every piece of evidence inside that session remains fresh forever**.
- For high-risk operations, per-transaction reauthentication/transaction binding or additional risk signals may be required. Simply having “OTT within 5 minutes” may not stop an attacker using a hijacked session during those 5 minutes.

## 12. Factor Combinations: Not Every Login Path Needs the Same Pair

Some products want to allow **WebAuthn alone** (if user verification/policy is strong enough) *or* **password + OTT**. Spring Security 7 supports combining condition groups with `AllRequiredFactorsAuthorizationManager.anyOf(...)`.

**Spring 7 snippet** example using configured factor-aware managers:

```java
AllRequiredFactorsAuthorizationManager<Object> passkey =
    AllRequiredFactorsAuthorizationManager.<Object>builder()
        .requireFactor(factor -> factor.webauthnAuthority())
        .build();

AllRequiredFactorsAuthorizationManager<Object> passwordAndOtt =
    AllRequiredFactorsAuthorizationManager.<Object>builder()
        .requireFactor(factor -> factor.passwordAuthority())
        .requireFactor(factor -> factor.ottAuthority())
        .build();

DefaultAuthorizationManagerFactory<Object> mfa =
    new DefaultAuthorizationManagerFactory<>();

mfa.setAdditionalAuthorization(
    AllRequiredFactorsAuthorizationManager.anyOf(
        passkey, passwordAndOtt));
```

To complete the configuration, wire `mfa.authenticated()` into `authorizeHttpRequests(...).requestMatchers(...).access(...)` and configure the actual mechanisms `formLogin()`, `oneTimeTokenLogin()`, `webAuthn()` along with a credential repository.

**Note:** these are two **policy-allowed combinations**, not a check for “any single weak factor suffices”. A WebAuthn passkey with user verification satisfies different risk criteria than an email OTP. Combining factor groups must be grounded in the threat model and actual assurance level, not just the count of `FACTOR_*` labels.

## 13. Where Is Completion State Stored and What Must Be Invalidated?

### 13.1. Authentication and SecurityContext

In the Servlet stack, Spring Security stores `Authentication` in `SecurityContextHolder` for the current request; depending on `SecurityContextRepository` configuration, it is persisted/restored across requests via the HTTP session.

For MFA, the framework needs a model that retains previously proven factors so the next step **adds to them** rather than resetting everything. Never arbitrarily overwrite an existing Authentication with one containing only the new factor and lose the old factor. Also never merge factors from two users or two sessions.

The logical data in the session can be understood as:

```text
SessionId: S-123
Principal: learner
Authorities: ROLE_ADMIN
CompletedFactors:
    FACTOR_PASSWORD (issuedAt: 12:00)
    FACTOR_OTT      (issuedAt: 12:01)
CurrentRequiredPolicy:
    /profile        -> authenticated
    /settings/**    -> PASSWORD + OTT
    /admin/**       -> ROLE_ADMIN + PASSWORD + OTT
```

This is a conceptual description, **not the exact serialized Spring Security session schema**. Policy should be evaluated from server-side configuration on every request; never trust a “CurrentRequiredPolicy” supplied by the browser.

### 13.2. Session Fixation, Logout, Revocation, and Privilege Changes

- When login/step-up succeeds, ensure the session is protected against fixation per Spring Security configuration; cookies should use appropriate `Secure`, `HttpOnly`, and `SameSite` flags.
- Logout must clear the valid context/session and any pending challenge state; never store factors in a custom cookie and skip server-side verification.
- When an account is disabled, the user changes their password, a WebAuthn credential is revoked, or permissions are updated, have an invalidation/re-evaluation strategy. An old session is not a permanent license.
- Across multiple nodes, session stores/challenge stores must be consistent; the default in-memory OTT service does not automatically handle distributed clusters or restarts. See `JdbcOneTimeTokenService` for suitable environments.
- When using stateless JWTs carrying an “MFA completed” claim, the token-issuing server must accurately know the evidence and timestamp; the resource server must verify issuer, audience, signature, expiry, and claim semantics. Never take `mfa=true` from a request parameter.

### 13.3. Never Expose the Full Authentication

You can safely display factor status (e.g., “additional verification required”) to a logged-in user. However, avoid returning raw `Authentication.getCredentials()`, OTP tokens, recovery codes, or session details. Even authorities/`issuedAt` are internal security metadata whose retrieval endpoints should be controlled.

## 14. OTT Is Not OTP; Factor Independence Is Crucial

Spring Security supports `oneTimeTokenLogin()` and grants `FACTOR_OTT` when that mechanism completes. OTT is typically a **magic link/token** generated by the server and delivered to the user via email/SMS or another channel.

**Do not confuse them:** TOTP/HOTP are one-time codes generated from a shared secret based on time/counter. Spring OTT is not a built-in TOTP authenticator app. Adding `oneTimeTokenLogin()` does not automatically create an SMS gateway, SMTP service, recovery policy, or strong delivery channel.

True MFA requires considering **factor independence**:

- Password + magic link sent to the same inbox used for password resets can depend heavily on mailbox control; evaluate the real risk.
- Password + WebAuthn with user verification and RP binding generally has very different properties from password + email OTT.
- Authenticating with a password on a malware-compromised device where the second token also appears on that same device does not completely eliminate session hijacking risk.
- FIDO2/passkeys can provide phishing-resistant authentication, yet authorization/session management and preventing account recovery takeover remain the application's responsibility.

The factor strings used by the framework **are not self-certifying NIST/AAL scores**. If a system must comply with an assurance standard (such as NIST SP 800-63), evaluate authenticator type, identity proofing, storage, session handling, replay protection, recovery, and all standard risks—never equate `FACTOR_PASSWORD+FACTOR_OTT` to “guaranteed AAL2”.

## 15. Error Behavior and UX/API Handling

| Situation | Logical State | Reasonable Handling |
| --- | --- | --- |
| Anonymous accesses `/profile` | Unauthenticated | Browser: redirect `/login`; API: 401 per contract |
| Valid password, no OTT; enters `/profile` | Sufficient evidence for endpoint | Allow |
| Valid password, no OTT; enters `/settings/security` | Missing `FACTOR_OTT` | Step-up to OTT challenge; block sensitive operation |
| Valid OTT, no password; enters route needing both | Missing `FACTOR_PASSWORD` | Go to password login |
| Both present, but password older than 10 min | Stale factor | Reauthenticate password (and OTT if also stale) |
| Both factors present, missing `ROLE_ADMIN` | Missing business privilege | 403 or access denied; do not “make admin” after OTT |
| Wrong/expired/consumed OTT | Factor not completed | Deny, rate limit; do not grant `FACTOR_OTT` |
| User A has password, User B's token submitted | Evidence from different principal | Deny; never mix identities/factors |
| User enrolled a passkey but hasn't used it this session | Enrolled, not completed `FACTOR_WEBAUTHN` | Require assertion if policy needs that factor |
| OTT/mail service fails | Cannot complete factor | Fail-closed for endpoints requiring factor; show safe retry |

### 15.1. 401, 403, or 302?

In a **web UI** with form login, when a factor is missing Spring Security 7 can automatically redirect to the missing authentication mechanism (e.g., OTP/OTT page). If the resource is a **JSON API**, do not automatically redirect to an HTML login page that API clients cannot parse; configure responses per contract such as `401 step_up_required` or `403 insufficient_authentication`, with controlled hints about the next method.

Do not rely on a single HTTP status code to infer exactly which factors are held: the HTTP response depends on `ExceptionTranslationFilter`, `AuthenticationEntryPoint`, access-denied configuration, content negotiation, and authentication mechanisms.

### 15.2. Avoiding Infinite Redirect Loops

If a global MFA policy applies even to the screen used to complete a factor, requests can fall into a loop `/login` → `/ott/generate` → `/login`. Use the built-in DSL/entry points/framework integration and test end-to-end; never write a `CustomAccessDeniedHandler` that blindly redirects back to the same page without checking authentication state.

## 16. Advanced Security and Testing

Checklist for a multi-factor system with completion states:

1. **Each factor granted at the right time:** only after cryptographic/credential verification succeeds, never based on request headers/queries/booleans.
2. **No principal swapping:** A's password plus B's OTT must never become “A has both factors”.
3. **No OTT reuse:** expired or already-consumed tokens must be rejected, even if the browser replays an old request.
4. **Freshness:** test immediately before, exactly at, and after `validDuration`; test clock skew.
5. **Step-up:** a user with password but missing OTT can reach low-assurance routes, cannot reach high-assurance routes, and reaches them only after OTT.
6. **Privilege:** sufficient factors without required role/tenant ownership must still return 403.
7. **Recovery:** access recovery must not wipe out all MFA policies; enrolling/changing an OTP channel must require sufficiently strong reauthentication.
8. **Throttling:** rate-limit password attempts, OTT generation requests, OTT verification, link resends, and new factor creation to prevent enumeration/spam/DoS.
9. **Session:** test session fixation, expiry, logout, multiple tabs, multiple devices, and clustered nodes.
10. **CSRF:** password/OTT forms, settings, and token-generation POSTs must be protected for browser flows; never disable all CSRF just to “make MFA work”.
11. **Transport:** HTTPS, cookies, protect query tokens from referrers/logs, and keep secrets out of telemetry.
12. **Version:** verify Spring Boot 4/Security 7 packages and test the actual dependency tree; do not use 7.x MFA code on 6.5.
13. **Audit:** log “password verified”, “OTT verified”, and “MFA required but incomplete” with protected user/session IDs; never log raw tokens/passwords.
14. **Monitoring:** track step-up failure rates, token delivery delays, abuse, and redirect loops without exposing personal data.

One particularly valuable test: the user initially has `ROLE_ADMIN` in `Authentication` but only `FACTOR_PASSWORD`. If the app still allows `/admin/export`, then **the MFA policy has been bypassed**. Roles and factors must both participate in access conditions—never use “role OR factor” unless product policy explicitly requires otherwise.

## 17. Self-Check Questions

1. **Does an Authentication with `isAuthenticated() == true` mean MFA is complete?** No. It may only prove a single mechanism; resource policy must be checked.
2. **How does Spring Security 7 represent a completed factor?** `FactorGrantedAuthority`, containing the authority name and `issuedAt`.
3. **Why not just store a boolean `mfaDone=true`?** It does not tell you which factor, when it was verified, which user/session it belongs to, or which endpoints it remains valid for.
4. **Can a password from 15 minutes ago and a fresh OTT access a route requiring a password within 10 minutes?** No; the password must be reauthenticated.
5. **What is the difference between `ROLE_ADMIN` and `FACTOR_OTT`?** A role is a business permission; a factor is evidence of an authentication method.
6. **Why is `@EnableMultiFactorAuthentication(authorities = {})` useful?** It enables MFA support without forcing a global factor requirement, allowing selective step-up routes.
7. **Can `@EnableMultiFactorAuthentication` be used on Spring Security 6.5?** Not with the 7.x API; an upgrade or compatible custom design is needed.
8. **How does OTT differ from TOTP?** OTT is typically a server-issued and delivered token/link; TOTP is a code generated by an authenticator from a shared secret and time.
9. **After a user registers a passkey, do they automatically carry `FACTOR_WEBAUTHN` on every request?** No; enrollment differs from completing a WebAuthn assertion in the current session.
10. **Why is `@WithMockUser` insufficient to test actual MFA?** It does not exercise login mechanisms/token issuance and may not populate proper `FactorGrantedAuthority` entries.
11. **Does a missing factor always return HTTP 401?** No. A browser may receive a step-up redirect; an API may follow a 401/403 contract depending on handlers.
12. **Does Spring Security 7 allow requiring “passkey or password+OTT”?** Yes, using `AllRequiredFactorsAuthorizationManager.anyOf(...)` combining the corresponding policies.
13. **Why must factors be invalidated/re-evaluated after account changes?** The session may hold a stale Authentication while privileges and authentication methods have changed.
14. **If the mail server fails to send an OTT, can we skip the check?** No. Routes requiring OTT must fail-closed; an approved recovery strategy is needed.

## 18. Official Documentation for Further Reading

- Spring Security – Multi-Factor Authentication (Servlet): https://docs.spring.io/spring-security/reference/servlet/authentication/mfa.html
- Spring Security – One-Time Token Login: https://docs.spring.io/spring-security/reference/servlet/authentication/onetimetoken.html
- Spring Security – FactorGrantedAuthority API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/authority/FactorGrantedAuthority.html
- Spring Security – EnableMultiFactorAuthentication API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/authorization/EnableMultiFactorAuthentication.html
- Spring Security – AuthorizationManagerFactories API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationManagerFactories.html
- Spring Security – AllRequiredFactorsAuthorizationManager API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AllRequiredFactorsAuthorizationManager.html
- Spring Security – Servlet authentication architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security – Testing with MockMvc: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Security – MFA in Spring Security 7 (official blog, 21/10/2025): https://spring.io/blog/2025/10/21/multi-factor-authentication-in-spring-security-7/
- Spring Boot 4 – Sending Email: https://docs.spring.io/spring-boot/reference/io/email.html
- Spring Boot 4 – Testing applications: https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html
- Spring Boot 4 – Web MVC starter: https://docs.spring.io/spring-boot/reference/web/index.html

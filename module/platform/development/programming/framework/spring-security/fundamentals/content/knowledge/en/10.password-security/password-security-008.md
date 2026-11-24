# NoOpPasswordEncoder and Sample Passwords Are Not Deployment Configurations

> **Key takeaway:** `NoOpPasswordEncoder` **does not hash, encrypt, or protect passwords**: `encode(rawPassword)` returns the exact password content verbatim; `matches(rawPassword, storedPassword)` essentially checks whether two strings match. Spring Security retains it for **legacy compatibility and testing**, yet has marked it **deprecated/insecure**. A `{noop}password` entry in a tutorial is a **compatibility syntax** of `DelegatingPasswordEncoder`, **not a secure storage format**. Passwords like `password`, `123456`, or `demo-pass` in examples are **not configurations for production deployment**. For real accounts, use an adaptive password hash such as Argon2id, bcrypt, scrypt, or PBKDF2 properly configured, manage credentials outside source code, and use HTTPS.

This lesson belongs to the **Passwords** topic in **Spring Security – Fundamentals**, focusing on Spring Security 6.5.x, Java 17, and Spring Boot 3.5.x. It answers three questions: **What is wrong with NoOp?**, **Why do tutorials sometimes still contain `{noop}` and sample passwords?**, and **How do you transition from demo/legacy setups to a safely operable configuration?**

## 1. Learning Objectives

After this lesson, you can:

1. Explain `PasswordEncoder.encode` and `PasswordEncoder.matches` accurately, along with the differences among reversible encryption, adaptive hashing, and NoOp.
2. Demonstrate via an isolated unit test that `NoOpPasswordEncoder.getInstance()` does not protect secrets.
3. Read `{noop}password`, `{bcrypt}$2a$...`, and an unprefixed bcrypt hash correctly when using an encoder directly.
4. Distinguish **`NoOpPasswordEncoder`**, **`User.withDefaultPasswordEncoder()`**, **`BCryptPasswordEncoder`**, and **`PasswordEncoderFactories.createDelegatingPasswordEncoder()`**.
5. Understand why `{noop}` exists in the compatibility decoder map yet new applications **must not** store passwords in that format.
6. Configure `UserDetailsService`, `PasswordEncoder`, and `SecurityFilterChain` without exposing real passwords in production runtime code.
7. Run a Java 17 Spring Boot sample application whose demo accounts activate only under a `lab` profile, with a default mode that blocks logging in as demo users.
8. Write MockMvc tests verifying real Basic authentication (200/401/403) and CSRF, plus unit tests confirming passwords are hashed.
9. Plan legacy password migrations with clear priorities, rollback/monitoring, and without “just adding `{noop}`” to hide configuration errors.
10. Recognize risks even when BCrypt is used: hardcoded shared passwords, header logging, plain HTTP without TLS, brute-force, missing revocation, and broken authorization.

## 2. Placing NoOpPasswordEncoder in the Authentication Flow

A typical HTTP Basic or form login request:

```text
Browser/client:
    username="alice", password="<user-entered password>"
                         |
                         v
               Authentication Filter
                         |
                         v
     UsernamePasswordAuthenticationToken (unauthenticated)
                         |
                         v
                 AuthenticationManager
                         |
                         v
                 DaoAuthenticationProvider
                     /            \
                    v              v
           UserDetailsService    PasswordEncoder
                    |              |
                    v              |
            stored password hash   |
                    +--------------+
                         |
                 matches(raw, stored)
                         |
              +----------+----------+
              |                     |
            false                  true
              |                     |
         AuthenticationException   Authentication verified
                                    |
                                    v
                             Authorization rules
```

`PasswordEncoder` defines the core methods:

```java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);
    boolean matches(CharSequence rawPassword, String encodedPassword);
    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
```

This is a **conceptual signature** corresponding to Spring Security 6.5, not a file learners need to declare themselves: the framework already provides the interface. In real source code, the interface may include extra annotations.

- `encode` is used when **creating or changing** a password; its output is saved in the user store.
- `matches` is used on **login**; it checks the client-supplied raw password against the stored password hash.
- `upgradeEncoding` helps identify formats or work factors needing an upgrade, if the implementation supplies that logic.
- `UserDetailsService` only loads the username, encoded password, and authorities; it does not take over the password encoder or provider's job.
- Passwords and encoded passwords are not JWTs, session cookies, CSRF tokens, or API keys. Each secret has its own lifecycle and verification method.

### 2.1. Where Does NoOp Sit?

`NoOpPasswordEncoder` also implements `PasswordEncoder`, yet **performs an identity operation**:

```text
NoOpPasswordEncoder.encode("secret")
    -> "secret"

NoOpPasswordEncoder.matches("secret", "secret")
    -> true

NoOpPasswordEncoder.matches("wrong", "secret")
    -> false
```

It can help a tiny tutorial skip hashing to focus on authentication flow. However, if the database or config leaks, an attacker immediately reads the exact secret used to log in. Even when kept only in memory, hardcoded source/configs can still leak via Git, build artifacts, logs, or snapshots.

**Key point:** `NoOpPasswordEncoder` **is not a way to “disable password checking.”** It still checks passwords, just in plaintext; that is not secure password storage.

## 3. Why Does Spring Security Still Include NoOpPasswordEncoder?

### 3.1. Historical and Compatibility Reasons

Older Spring Security apps once stored plaintext passwords, and some systems must verify legacy records during a migration. Spring Security retains `NoOpPasswordEncoder` for compatibility and test scenarios, while marking it **deprecated** because it is insecure. “The API exists in the library” does not mean “the API is recommended for production.”

Pre-5.0 Spring Security had different defaults; modern password storage supports multiple algorithms and formats via `DelegatingPasswordEncoder`. Never copy `NoOpPasswordEncoder.getInstance()` verbatim from an old blog post into a new app.

### 3.2. Exact Call to Obtain the Singleton

```java
import org.springframework.security.crypto.password.NoOpPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

// ONLY IN UNIT TESTS TO DEMONSTRATE WHY IT IS UNSAFE.
PasswordEncoder noop = NoOpPasswordEncoder.getInstance();
String stored = noop.encode("test-secret");

System.out.println(stored.equals("test-secret"));  // true
System.out.println(noop.matches("test-secret", stored)); // true
```

**This is an illustrative snippet**, not a standalone Java file: imports, class, and `main` are abbreviated. Section 9 provides a complete unit test. The API returns a `PasswordEncoder` singleton; do not call `new NoOpPasswordEncoder()`, as the constructor is not intended for public use. The deprecation warning here is an **intentional security warning**, not a warning to suppress in deployment configs.

### 3.3. What Does “No-Op” Mean and Not Mean?

| Statement | True/False | Explanation |
| --- | --- | --- |
| NoOp creates no password hash | **True** | Output equals the raw input |
| NoOp prevents password leaks on a DB dump | **False** | Plaintext can be read directly |
| NoOp does not check passwords | **False** | It still compares them directly |
| NoOp is only dangerous over HTTP | **False** | HTTPS protects transit, not DB dumps or source code |
| NoOp may exist to read legacy data | **True** | Conditional compatibility purpose; must be migrated |
| NoOp is deprecated so it won't compile | **False** | Deprecated does not mean removed |
| `{noop}` is a kind of hash | **False** | It is a format ID for plaintext comparison |
| NoOp is suitable as a production `@Bean PasswordEncoder` | **False** | All credentials risk being stored in plaintext |
| Hashing passwords replaces HTTPS | **False** | User passwords still travel across the network |
| Sample passwords in documentation are strong enough for production | **False** | Public, predictable, shared credentials |

## 4. Understanding `DelegatingPasswordEncoder`'s `{noop}` Properly

### 4.1. Format of Stored Passwords

`DelegatingPasswordEncoder` selects an algorithm by prefix:

```text
{id}encodedPassword
```

Examples:

```text
{noop}legacy-password
{bcrypt}$2a$10$...bcrypt-hash-portion...
{pbkdf2@SpringSecurity_v5_8}...pbkdf2-hash-portion...
{argon2@SpringSecurity_v5_8}...argon2-hash-portion...
```

**Note:** Ellipses are explanatory placeholders, **not** valid password hashes to store directly. With the default implementation from `PasswordEncoderFactories.createDelegatingPasswordEncoder()`, `{id}` determines the decoder at login. The default encoder for **encoding** new passwords is typically `bcrypt`, while several legacy decoders remain available for **matches**.

`{noop}legacy-password` means the stored password payload is `legacy-password` in plaintext. The `{noop}` prefix **adds no hash, salt, encryption, or protection whatsoever**.

### 4.2. Recommended Modern Configuration for Understanding Formats

```java
@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
}
```

With this factory, Spring Security 6.5 uses bcrypt to **encode new passwords** and prepends `{bcrypt}`. When `matches` encounters a stored hash with a supported prefix, it delegates to the matching implementation, including `{noop}` for legacy/testing compatibility. The presence of a NoOp decoder **does not permit writing new plaintext passwords to the DB**.

Illustrative example (real hashes use random salts and vary):

```text
Input password:
    "SomeLabPassphrase2026!"

passwordEncoder.encode(input):
    "{bcrypt}$2a$10$..."  (long hash, salt-dependent)

passwordEncoder.matches(input, encoded):
    true

passwordEncoder.matches("wrong", encoded):
    false

passwordEncoder.matches("legacy-password", "{noop}legacy-password"):
    true  <-- COMPATIBILITY, not a new security level
```

`PasswordEncoderFactories.createDelegatingPasswordEncoder()` **does not accept unprefixed plaintext as a valid format**. If the stored password is `abc123` while the encoder expects `{id}`, you will typically see:

```text
There is no PasswordEncoder mapped for the id "null"
```

The fix is not prepending `{noop}` to every new password. Identify what format the store holds, define a clear migration plan, and configure an encoder suited to the remaining data during transition.

### 4.3. Comparing with Direct BCryptPasswordEncoder

```java
PasswordEncoder direct = new BCryptPasswordEncoder();
String hash = direct.encode("SomeLabPassphrase2026!");
// Output looks like $2a$... or an appropriate bcrypt variant.
// Does not automatically include the "{bcrypt}" prefix added by DelegatingPasswordEncoder.
```

When using `BCryptPasswordEncoder` directly, it expects bcrypt hashes formatted like `$2a$...` or `$2b$...` depending on version, and **does not expect the `{bcrypt}` prefix**. When using the default `DelegatingPasswordEncoder`, stored passwords need the prefix to pick the decoder.

| Declared Encoder | `encode("password")` Produces | Stored Value Accepted by `matches` |
| --- | --- | --- |
| `NoOpPasswordEncoder` | `password` | Plaintext `password` |
| Direct `BCryptPasswordEncoder` | bcrypt hash (typically `$2a$...`) | Direct bcrypt hash |
| Default `DelegatingPasswordEncoder` | `{bcrypt}` + bcrypt hash | Any mapped `{id}`, including legacy formats |
| `User.withDefaultPasswordEncoder()` | bcrypt hash with helper-appropriate prefix | Not a justification to skip production password security |

**Important:** Never prepend `{noop}` before a bcrypt hash. `{noop}$2a$...` makes the encoder compare the user's raw input directly against the hash characters—legitimate logins will fail. Conversely, never strip `{bcrypt}` from stored values while still using the default Delegating encoder without configuring a mapping, because the decoder will lack an ID.

## 5. `User.withDefaultPasswordEncoder()` Is Not the Same as NoOp

In Spring Security learning materials you may see:

```java
UserDetails user = User.withDefaultPasswordEncoder()
    .username("student")
    .password("SamplePasswordForDemoOnly")
    .roles("USER")
    .build();
```

Unlike NoOp, this helper **can hash the password** via a convenience configuration and store `{bcrypt}...`. However, official guidance warns to **use this convenience helper only for learning/samples**: the raw password still appears verbatim in Java source, compiled artifacts, or configuration; an attacker can read the credential before ever touching a database hash.

**Distinguish two risks:**

1. **NoOp:** Passwords are stored in plaintext in `UserDetails`/DB — risk at storage.
2. **withDefaultPasswordEncoder + hardcoded raw password:** The stored value may be safely hashed, **yet the raw password still sits in source/build artifacts** — risk via supply chain, deployment, or source disclosure.

Never say calling `encode` alone makes everything automatically safe. Password security requires **credential provenance**, **hashing at rest**, **transport security**, **account governance**, and **credential lifecycles**.

### 5.1. Is a Hardcoded Bcrypt Hash Completely Safe?

No. If source code embeds a bcrypt hash of a public sample password (`Demo123!`), attackers already know the plaintext from documentation or guessing. If source holds a hash of a real secret password shared across environments, that account is hard to revoke, prone to reuse, and dangerous if leaked. With CI, container images, and config repos, attackers can attempt to crack weak passwords offline. Use a real user store/IdP and secret management rather than shared long-lived accounts.

### 5.2. Spring Boot's Generated User Is Not a Production Account

When you add `spring-boot-starter-security` without configuring a user or provider, Spring Boot MVC may generate a default user `user` with a random password logged at WARN level. Boot documentation explicitly states this generated password is **for development only**.

If you set `spring.security.user.password=demo-pass` in `application.properties` and expose that account on a public server, the password becomes an easily exposed secret in configs, artifacts, or deployment tooling. Even if the app hashes the password internally, it remains a sample/shared credential lacking proper lifecycle management.

**For production:** configure a real user source/identity provider, eliminate generated users, remove test users, and store zero raw passwords in repositories. Add CI/deployment checks to catch sample accounts or mistakenly enabled lab profiles.

## 6. Distinct Layers of Password Protection

| Layer | Problem Solved | Does NoOp Help? |
| --- | --- | --- |
| Password hashing at rest | Limits plaintext recovery if user DB is dumped | **No** |
| Random salt | Stops identical passwords from sharing hashes and degrades precomputed attacks | **No** |
| Work factor / memory hardness | Makes offline guessing resource-expensive | **No** |
| HTTPS/TLS | Protects credentials in transit | **No**; even with bcrypt, TLS is required |
| Secret management | Prevents raw credentials from leaking in Git/builds/env | **No** |
| Account lockout/rate limit | Throttles online guessing and credential stuffing | **No** |
| MFA/passkey/step-up | Raises authentication assurance in sensitive flows | **No** |
| Route/resource authorization | Restricts permissions after login | **No** |
| Session/token revocation | Revokes access upon compromise | **No** |
| Logging redaction | Keeps Basic headers/passwords out of logs | **No** |

### 6.1. Password Hashing Is One-Way, Not Encryption

For login passwords, the backend **never needs to decrypt the password hash to compare**. It calls `matches(raw, storedHash)`. Reversible encryption like AES suits business data that must be read back, not typical user password storage, because leaking the decryption key exposes every password.

Never use `Base64.getEncoder()`, MD5, SHA-1, or plain SHA-256 as a password storage algorithm. Base64 is trivially reversible encoding; fast hashes let attackers test huge candidate volumes offline. High-entropy CSPRNG secrets (such as reset tokens) have a different threat model, whereas **human passwords** require a dedicated password-hashing algorithm.

### 6.2. Adaptive Options

- **Argon2id:** typically recommended by OWASP for new systems, with memory/time/parallelism parameters; requires supporting dependencies and real hardware benchmarks.
- **bcrypt:** widespread and straightforward in Spring Security; pay attention to bcrypt's effective input limit and tune work factor for real load.
- **scrypt:** memory-hard password hashing supported by Spring Security.
- **PBKDF2:** useful for FIPS requirements or compatible ecosystems; pick strong PRF/iteration counts per current guidance.
- **DelegatingPasswordEncoder:** routes current and legacy formats by prefix, supporting incremental upgrades without forcing all users to reset simultaneously.

Never pick cost parameters by copying a number off Stack Overflow. Password verification must be costly enough to deter offline guessing while meeting login latency and peak traffic budgets without enabling high-cost DoS. Benchmark on real infrastructure, enforce rate limiting, and monitor login failures.

### 6.3. Salt and Pepper

Random salts are usually generated automatically by adaptive password encoders and stored alongside the hash without requiring secrecy; they ensure identical plaintexts produce distinct hashes. A pepper is a system-level secret that can add defense-in-depth when backed by an HSM/secret store, requiring rotation, backups, and breach response planning. **A pepper does not replace a salt or adaptive hashing.**

### 6.4. TLS Is Not Enough If Password Storage Is Broken

If an app uses HTTPS yet stores `User.password="alice123"` in its users table, a database dump still exposes passwords. Conversely, an app using bcrypt that accepts passwords over plain HTTP without TLS lets network attackers sniff raw passwords. You need **both**, along with least-privilege access and proper auditing.

### 6.5. Do Not Verify Hashes in Controllers

```java
// Design anti-pattern:
if (request.password().equals(user.getPasswordHash())) {
    // ...
}
```

This fails because it compares a raw password against a hash; if the stored password happens to be NoOp plaintext, it may appear to “work” and mask the bug. In Spring Security, let `DaoAuthenticationProvider` + `PasswordEncoder` perform credential validation. When an app implements password change/reset logic, the service calls the encoder to hash the new password and the repository stores only the hash—never accepting a client-supplied hash as a “new password.”

## 7. Anti-Patterns: Configurations Never to Deploy

### 7.1. Registering a NoOpPasswordEncoder Bean

```java
// DANGEROUS ANTI-PATTERN: DO NOT USE FOR DEPLOYMENT.
@Configuration
class InsecureSecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return NoOpPasswordEncoder.getInstance();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("admin")
                .password("admin123")
                .roles("ADMIN")
                .build()
        );
    }
}
```

This is an **intentional snippet for risk analysis** requiring the corresponding Spring imports. Placed in an application context, the NoOp bean allows credential validation against plaintext sample passwords and creates a public admin account. It does not build a complete security chain itself, yet when used by an authentication provider, the risks lie in **credential storage** and **predictable admin access**.

**Why is this severe?** Source code holds username/password, JARs can be inspected, and CI logs or deployment environments can leak; if admin endpoints exist, a public sample credential can grant elevated privileges. Even changing the password to a long string while keeping it hardcoded and shared across environments makes rotation and revocation painful.

### 7.2. Adding a NoOp Prefix Does Not Fix the Problem

```java
UserDetails user = User.withUsername("admin")
    .password("{noop}admin123")
    .roles("ADMIN")
    .build();
```

This too is an **anti-pattern**: with `DelegatingPasswordEncoder` containing the noop mapping, Basic/form login compares plaintext after the prefix. Having curly braces only tells Spring Security **how to compare**—it does not mean the password is hashed.

### 7.3. Putting Passwords in application.yml

```yaml
# ANTI-PATTERN — DO NOT COMMIT AND DO NOT DEPLOY.
spring:
  security:
    user:
      name: admin
      password: admin123
      roles: ADMIN
```

`spring.security.user.*` is a Boot development convenience. Production must use real accounts, an IdP, or secret management; never treat YAML as safe credential storage, as it can end up in source control, config servers, images, snapshots, or build environment dumps.

### 7.4. Is “I Only Run on Localhost” Safe?

Using sample accounts in a lab **can be acceptable** if completely isolated from real environments, bound strictly to loopback, touching no real data, reusing no real passwords, and granting no privileges beyond scope. Never carry sample configs into public staging or production just because “it worked in tests.” CI/CD should block test profiles and demo users from reaching deployments.

### 7.5. “The Password Is Hashed in the DB, So Why Is Source Still Risky?”

If source contains:

```java
.password(encoder.encode("CommonPassword2026!"))
```

then the password is hashed **at runtime**, yet the raw plaintext sits right in source code. Attackers know the password without cracking any hash, especially if reused across environments. That is why a demo using bcrypt is still not production-ready merely because it calls `encode`.

## 8. Controlled Pattern: Lab Profile, Safe Encoder, No Sample Accounts by Default

This section builds a Spring Boot MVC app enforcing:

1. `PasswordEncoder` is `DelegatingPasswordEncoder` with bcrypt for new passwords—**not a NoOp bean**.
2. Sample users exist **only when the `lab` profile is active** and strictly for local study.
3. When **`lab` is inactive**, the app registers a `UserDetailsService` that rejects every username so Spring Boot does not auto-generate a default user instead; this is a **fail-closed example setup**, not a production backend user store.
4. `SecurityFilterChain` protects `/me`, `/admin`, `POST /notes`, and denies other routes.
5. Demo passwords in Java source are **test data**, not secrets; never deploy this source publicly or reuse those passwords on any real account.
6. Unit tests may invoke `NoOpPasswordEncoder` **purely for observation**, while the main application never registers NoOp as its password encoder bean.

**Lab versions:** Java 17+, Spring Boot **3.5.16**, and Spring Security 6.5.x managed by the Boot BOM. Spring Boot 3.5.16 is the final OSS release in the 3.5.x line (released 2026-06-25); new production systems should target a supported branch such as Boot 4.x and follow the corresponding version guides.

### 8.1. Directory Structure

```text
password-encoder-lab/
├── pom.xml
└── src/
    ├── main/java/demo/password/PasswordEncoderLabApplication.java
    └── test/java/demo/password/
        ├── PasswordEncoderBehaviorTests.java
        └── PasswordEncoderHttpTests.java
```

### 8.2. Maven pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>password-encoder-lab</artifactId>
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

### 8.3. Complete Java Application

Create `src/main/java/demo/password/PasswordEncoderLabApplication.java`:

```java
package demo.password;

import jakarta.servlet.DispatcherType;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class PasswordEncoderLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(PasswordEncoderLabApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class LabSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        // New encodes -> {bcrypt}...; includes legacy mappings for matches.
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    @Profile("lab")
    UserDetailsService labUsers(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("student")
                .password(encoder.encode("LabOnlyPassphrase2026!"))
                .authorities("ROLE_USER", "NOTES_WRITE")
                .build(),
            User.withUsername("lab-admin")
                .password(encoder.encode("LabAdminPassphrase2026!"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    @Profile("!lab")
    UserDetailsService noDemoUsersOutsideLab() {
        // Fail-closed example: no lab/default accounts available to log in.
        // Production must REPLACE this bean with a real identity provider.
        return username -> {
            throw new UsernameNotFoundException(
                "No application user store configured");
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST, "/notes")
                    .hasAuthority("NOTES_WRITE")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(Customizer.withDefaults())
            .build();
    }
}

@RestController
class LabController {

    @GetMapping("/public")
    String publicMessage() {
        return "public";
    }

    @GetMapping("/me")
    String currentUser(Authentication authentication) {
        return "me:" + authentication.getName();
    }

    @GetMapping("/admin")
    String admin() {
        return "admin-ok";
    }

    @PostMapping("/notes")
    String createNote(Authentication authentication) {
        // Lab does not write to a database.
        return "created:" + authentication.getName();
    }
}
```

**Points to observe:**

- `@Profile("lab")` ensures sample users are registered only when the `lab` profile is active. This provides separation **at the Spring bean level**, though it **does not guarantee production cannot accidentally enable `lab`**. Real apps need build/deployment policies blocking that profile in production or keeping fixtures strictly inside `src/test`.
- `@Profile("!lab")` provides a user source that rejects all usernames when `lab` is inactive. This both prevents Boot's generated default user in the demo and demonstrates the **fail closed** principle. It is not a real user-management implementation.
- `PasswordEncoderFactories.createDelegatingPasswordEncoder()` hashes new lab passwords with bcrypt and the `{bcrypt}` prefix. **There is no `NoOpPasswordEncoder` bean in the main app.**
- Passwords like `LabOnlyPassphrase2026!` are deliberately in the lab source solely for learners to experiment with. Because the source is public, they **must not be treated as secrets**, even though their stored hashes use BCrypt.
- `httpBasic` transmits username/password in the HTTP Basic header; Base64 is not encryption. Real networks require HTTPS; the lab uses loopback.
- `SessionCreationPolicy.STATELESS` requires credentials on every request; never assume a later request remembers the principal automatically.
- CSRF is enabled. `POST /notes` requires a valid CSRF token in tests; do not disable CSRF merely to make `curl` POSTs easier.
- `anyRequest().denyAll()` covers the default chain across all requests, leaving no backdoor beyond explicitly granted URLs.
- The demo exposes a public endpoint to test authorization; in production, replace the user store with a real identity source, secrets, and business policies rather than shipping an app with “no users” as a login system.

### 8.4. Hazards Even When Using Bcrypt

Even though the demo avoids a NoOp bean:

1. If you copy the `lab-admin` account into production, attackers can read the username/password from source and abuse real admin access.
2. If you enable the `lab` profile on a public server, both demo accounts can log in with their declared authorities.
3. If using plain HTTP without TLS, network attackers can sniff raw Basic headers; BCrypt at storage cannot stop that.
4. If logging `Authorization`, credentials can leak into log aggregation or observability platforms.
5. If omitting rate limiting, attackers can still perform high-volume online password guessing despite bcrypt's CPU cost.
6. If `/admin` or services check only login without verifying ownership/tenant, a valid role holder can access out-of-scope data.
7. If reusing one sample password across test, staging, and production, a breach in a less-secure environment spreads elsewhere.

**Clear boundary:** This example shows how to **avoid NoOp in the main application** and isolate demo users by profile; it is **not ready to expose to the Internet** as a real product.

## 9. Unit Tests: Proving NoOp Differs from Bcrypt/Delegating

Create `src/test/java/demo/password/PasswordEncoderBehaviorTests.java`:

```java
package demo.password;

import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.NoOpPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PasswordEncoderBehaviorTests {

    @Test
    void noopDemonstratesPlaintextRiskOnlyInIsolatedTest() {
        // Deprecation is intentional: never register this encoder as a bean.
        PasswordEncoder noop = NoOpPasswordEncoder.getInstance();

        String stored = noop.encode("test-only-secret");

        assertEquals("test-only-secret", stored);
        assertTrue(noop.matches("test-only-secret", stored));
        assertFalse(noop.matches("incorrect", stored));

        // Stored password is exposed verbatim — why NoOp is unsafe.
        assertFalse(stored.startsWith("{bcrypt}"));
    }

    @Test
    void delegatingEncoderHashesNewPasswordsAndUnderstandsLegacyId() {
        PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();

        String raw = "LongLabPassphrase2026!";
        String stored = encoder.encode(raw);

        assertTrue(stored.startsWith("{bcrypt}"));
        assertNotEquals(raw, stored);
        assertTrue(encoder.matches(raw, stored));
        assertFalse(encoder.matches("wrong-password", stored));

        // This proves LEGACY reading capability, NOT RECOMMENDED FOR STORAGE.
        assertTrue(encoder.matches("legacy-secret", "{noop}legacy-secret"));
        assertFalse(encoder.matches("bad", "{noop}legacy-secret"));

        // Unprefixed plaintext is not a valid storage format
        // for default DelegatingPasswordEncoder.
        assertThrows(IllegalArgumentException.class,
            () -> encoder.matches(raw, "plain-without-id"));
    }

    @Test
    void directBcryptHashAndDelegatingHashHaveDifferentFormats() {
        PasswordEncoder direct = new BCryptPasswordEncoder();
        PasswordEncoder delegating =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();

        String raw = "AnotherLabPassphrase2026!";
        String directHash = direct.encode(raw);
        String delegatedHash = delegating.encode(raw);

        assertTrue(directHash.startsWith("$2"));
        assertTrue(delegatedHash.startsWith("{bcrypt}"));

        assertTrue(direct.matches(raw, directHash));
        assertTrue(delegating.matches(raw, delegatedHash));

        // Both use salts; differing hashes still match the same raw password.
        assertNotEquals(directHash, delegatedHash);

        // Never feed a direct hash lacking {id} into Delegating without migrating.
        assertThrows(IllegalArgumentException.class,
            () -> delegating.matches(raw, directHash));
    }
}
```

Purpose of the tests:

- `noopDemonstratesPlaintextRiskOnlyInIsolatedTest` **deliberately calls an insecure API** to illustrate the risk, without registering a bean or creating real accounts.
- `delegatingEncoderHashesNewPasswordsAndUnderstandsLegacyId` shows developers can maintain legacy compatibility while issuing new hashes; **compatibility is not permission to keep storing plaintext**.
- `directBcryptHashAndDelegatingHashHaveDifferentFormats` demonstrates prefixes and salts. Never hardcode an expected full bcrypt hash: random salting changes the output.
- Compiler warnings from `NoOpPasswordEncoder` deprecation are intentional, not an error to “fix” by upgrading versions or creating a production wrapper.

## 10. MockMvc Integration Tests: Valid Credentials, Invalid Credentials, Roles, Missing CSRF

Create `src/test/java/demo/password/PasswordEncoderHttpTests.java`:

```java
package demo.password;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("lab")
class PasswordEncoderHttpTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    UserDetailsService users;

    @Autowired
    PasswordEncoder encoder;

    @Test
    void labPasswordsAreHashedAndManagedByServer() {
        UserDetails student = users.loadUserByUsername("student");
        String stored = student.getPassword();

        assertTrue(stored.startsWith("{bcrypt}"));
        assertFalse(stored.equals("LabOnlyPassphrase2026!"));
        assertTrue(encoder.matches("LabOnlyPassphrase2026!", stored));

        assertTrue(student.getAuthorities().stream()
            .anyMatch(a -> a.getAuthority().equals("ROLE_USER")));
        assertTrue(student.getAuthorities().stream()
            .anyMatch(a -> a.getAuthority().equals("NOTES_WRITE")));
    }

    @Test
    void basicCredentialsAreVerifiedByRealProvider() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));

        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me")
                .with(httpBasic("student", "LabOnlyPassphrase2026!")))
            .andExpect(status().isOk())
            .andExpect(content().string("me:student"));

        mvc.perform(get("/me")
                .with(httpBasic("student", "bad-password")))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me")
                .with(httpBasic("not-a-user", "LabOnlyPassphrase2026!")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticationDoesNotGrantEveryAuthority() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("student", "LabOnlyPassphrase2026!")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin")
                .with(httpBasic("lab-admin", "LabAdminPassphrase2026!")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-ok"));

        mvc.perform(post("/notes")
                .with(httpBasic("lab-admin", "LabAdminPassphrase2026!"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void postRequiresBothCsrfTokenAndPermission() throws Exception {
        mvc.perform(post("/notes")
                .with(httpBasic("student", "LabOnlyPassphrase2026!")))
            .andExpect(status().isForbidden());

        mvc.perform(post("/notes")
                .with(httpBasic("student", "LabOnlyPassphrase2026!"))
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());

        mvc.perform(post("/notes")
                .with(httpBasic("student", "LabOnlyPassphrase2026!"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("created:student"));

        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void unmatchedPathIsDenied() throws Exception {
        mvc.perform(get("/unlisted")
                .with(httpBasic("student", "LabOnlyPassphrase2026!")))
            .andExpect(status().isForbidden());
    }
}
```

**Why use `httpBasic` instead of `@WithMockUser` alone?** `@WithMockUser` creates a fake principal in tests to check authorization, **without proving password hashes and the provider work properly**. `httpBasic("student", "...")` sends an HTTP Basic header through the security filter, so the provider uses the lab's real `UserDetailsService` and `PasswordEncoder`. This properly tests both valid/invalid login and authorization.

The tests also show that a user with `ROLE_ADMIN` **does not automatically** hold `NOTES_WRITE`, and CSRF can block POST independently of permissions. A `403` on a request missing CSRF **does not prove on its own** that the provider accepted the password; the GET tests and valid-CSRF POST tests supply that evidence.

### 10.1. Run Commands

In the directory containing `pom.xml`:

```bash
java -version
mvn -version
mvn test
```

The JUnit/MockMvc tests above do not open a browser or TCP port. `mvn test` is expected to pass given compatible code and dependencies; **these are expected commands and outcomes for the learner to run**, not a report of Maven having executed in the authoring environment.

Run the app in lab mode on a development machine:

```bash
mvn spring-boot:run -Dspring-boot.run.profiles=lab
```

Use another terminal and call `localhost` only:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u student http://localhost:8080/me
curl -i -u student http://localhost:8080/admin
curl -i -u lab-admin http://localhost:8080/admin
```

When `curl -u student` or `curl -u lab-admin` prompts for a password, enter the **lab-only** `LabOnlyPassphrase2026!` or `LabAdminPassphrase2026!`. Never embed passwords on command lines or shell history, and never use these accounts on public systems. On older PowerShell, use `curl.exe` instead of the `curl` alias.

Demo behavior table:

| Request | Credentials | Expected Status |
| --- | --- | --- |
| `GET /public` | None | 200 |
| `GET /me` | None | 401 |
| `GET /me` | Student right password | 200 |
| `GET /me` | Student wrong password | 401 |
| `GET /admin` | Student right password | 403 |
| `GET /admin` | Lab admin right password | 200 |
| `POST /notes` | Student right, missing CSRF | 403 |
| `POST /notes` | Student right, valid CSRF | 200 |
| `POST /notes` | Lab admin right, valid CSRF but missing NOTES_WRITE | 403 |
| `GET /unlisted` | Student right | 403 |

If run **without `lab` enabled**, the user store bean throws `UsernameNotFoundException` for any username; `GET /me` cannot be accessed with demo accounts. That proves **the lesson's fail-closed setup**, not that it is a production identity solution. Before real deployment, replace it with a proper user store/IdP with safe lifecycles, integration tests, secret management, TLS, rate limits, and deployment profile guards.

## 11. Pitfalls When Migrating Legacy Plaintext or `{noop}` Data

This is where many people make dangerous fixes. Suppose a database holds:

```text
username | stored_password
alice    | {noop}alice-old-pass
bob      | {bcrypt}$2a$10$...
charlie  | plain-without-prefix
```

**Illustrative data only**; never use real passwords and never paste production hashes or tokens into issues. These rows belong to three distinct formats. With the default `DelegatingPasswordEncoder`:

- Alice can match via the legacy `noop` mapping — data is **still unsafe** because plaintext sits in the DB.
- Bob uses prefixed bcrypt — compatible with the delegating encoder.
- Charlie has no prefix — throws an ID `null` error; never silently treat all unprefixed rows as plaintext without verifying the data source.

### 11.1. A Trustworthy Migration Process

1. **Bounded inventory:** Identify which formats exist (plaintext, unprefixed bcrypt, versioned PBKDF2, custom hashes), account counts, and risks; never dump plaintext passwords into shared CSV files.
2. **Block new bad data:** Ensure all new registrations, password changes, and resets write adaptive hashes under current policy. Never let new code write `{noop}`.
3. **Evidence-based mapping:** Only add prefixes to values verified with certainty to match a format; never apply an “unprefixed means noop” rule across the board.
4. **Isolate legacy handling:** Bound duration, scope, and access to legacy decoders; use dedicated feature flags/configs and audit legacy logins.
5. **Upgrade after credential verification:** When a user enters a valid raw password, re-`encode` with the new algorithm and persist the hash via properly wired `UserDetailsPasswordService`/upgrade logic.
6. **Mandatory resets for accounts that cannot upgrade safely:** If no plaintext remains (only weak legacy hashes) or policy requires blocking, mandate a password reset through a verified recovery channel; never email new passwords.
7. **Retire/lock legacy paths:** Once accounts migrate, stop accepting `{noop}`, remove compatibility code, rotate related secrets, and monitor error rates.
8. **Test rollbacks and observe:** Track login rates, account lockouts, ID decoding errors, CPU increases from higher work factors, and safe rollback behavior without writing plaintext back.

### 11.2. `upgradeEncoding` and UserDetailsPasswordService

`PasswordEncoder.upgradeEncoding(storedHash)` can signal whether the current hash/format should be re-encoded. When supported, `DaoAuthenticationProvider` coordinates with `UserDetailsPasswordService` to store the new hash **after the password verifies successfully**.

**Important:** Creating a `PasswordEncoder` does not auto-migrate the database. You need a repository/service writing hashes, safe transactions, concurrency guards, and tests covering the real provider/implementation. Never put upgrade logic in a controller accepting a client-supplied `newEncodedPassword`.

An architectural sketch:

```java
// Snippet — requires the project's repository, entity, and transactional policy.
class DatabaseUserDetailsPasswordService
        implements UserDetailsPasswordService {

    @Override
    public UserDetails updatePassword(
            UserDetails user, String newEncodedPassword) {
        // Store the NEW hash generated by the encoder (not the raw password).
        // Must check ownership, version, transaction, and minimal audit.
        // Return UserDetails reflecting the new password hash.
        return updatedUserDetails;
    }
}
```

This snippet **does not compile standalone** because `updatedUserDetails` is a domain-dependent placeholder; **it is not runnable code**. In a real implementation, persist `password_hash` in the repository with optimistic locking and return an updated `UserDetails`. Never strip or alter prefixes arbitrarily.

### 11.3. Why Not Automatically `setDefaultPasswordEncoderForMatches(NoOp)`?

`DelegatingPasswordEncoder.setDefaultPasswordEncoderForMatches(...)` can configure a fallback for unknown IDs. However, if that fallback is NoOp, every stored password missing an ID gets compared as plaintext, hiding bad data and widening legacy exposure beyond intent. For unknown formats, **fail closed**, emit redacted metrics for engineering follow-up, or apply a tightly scoped migration adapter with a firm removal plan. Never configure “all null IDs become plaintext” to silence startup or login errors.

### 11.4. No Need to Decrypt Bcrypt to Migrate

Adaptive hashing is one-way; you cannot “decrypt a hash” to recover raw passwords. Proper migration means:

- For accounts presenting a valid raw password on login, verify against the legacy hash, then `encode(raw)` under the current format and update storage.
- For accounts without a verifiable raw password at migration time, require a secure password reset rather than trying to decrypt.
- For genuine legacy plaintext records, while technically hashable in bulk by a job, carefully assess data access, security posture, and incident response because the plaintext itself may already have been exposed. Ensure migration logs and backups do not spread plaintext further.
- For direct-format bcrypt needing a `{bcrypt}` prefix when moving to delegating, **prepend only after confirming the data truly consists of bcrypt hashes**; that is format tagging, not rehashing.

### 11.5. Do Not Conflate Passwords with Other Secret Types

Refresh tokens, reset tokens, and API keys do not necessarily follow the same password-hashing policy; they are usually high-entropy CSPRNG strings with different expiry, revocation, and hashing models. Do not switch passwords from bcrypt to plain SHA-256 just because SHA-256 is used to hash reset tokens. Conversely, using `NoOpPasswordEncoder` for API key credentials can also expose secrets—design token verification and storage separately.

## 12. How Should You Interpret Tutorials When Reading Them?

### 12.1. Three Common Phrases

**`password("{noop}password")`**: a shortcut for demoing authentication with a fixed password in samples. Learners must recognize this as **plaintext in source and storage**, not deployment advice.

**`NoOpPasswordEncoder.getInstance()`**: an insecure legacy/testing API often appearing in older articles or isolated unit tests.

**`User.withDefaultPasswordEncoder().password("password")`**: a getting-started helper that may hash the stored value, yet leaves the raw password in source code and is therefore unsafe for real accounts.

### 12.2. Does Simply Adding BCrypt Make It “Production Ready”?

No. Imagine:

```java
User.withUsername("superadmin")
    .password(encoder.encode("password"))
    .roles("ADMIN")
    .build();
```

`BCrypt` protects the hash in memory, yet the password is `password` which anyone can guess, hardcoded in source, given admin privileges, and lacking lifecycle management. **Not production-ready.**

### 12.3. When Is NoOp Acceptable in Tests?

In **unit tests verifying NoOp's own behavior**, never touching real data, never registered as an application-wide password encoder bean, never exposing public routes, and never shipped in artifacts with real-privilege accounts. For security integration tests, even test environments should use a real encoder so bugs in formatting, salting/`matches`, disabled accounts, and Basic/form login surface. Never make a habit of using NoOp across integration tests merely to shave milliseconds off bcrypt.

### 12.4. Can Sample Passwords Be Used on Staging?

Only if staging is completely isolated, accesses no real data, is non-public or strongly restricted, uses temporary dedicated accounts, and enforces strict controls. Even better, **prefer** IdP/test accounts provisioned secretly with controlled lifecycles rather than pasting a public password from a blog post. Many breaches start with forgotten debug accounts left in public-facing environments.

## 13. Distinguishing Password Format Errors from Authentication/Authorization Errors

| Symptom | Possible Cause | Safe Diagnosis |
| --- | --- | --- |
| `There is no PasswordEncoder mapped for the id "null"` | Stored password lacks `{id}` under delegating | Check format via redacted metadata/samples; identify legacy origin |
| `401` with a password the user believes is right | Wrong hash format, mismatched encoder, locked/disabled account, nonexistent user | Test provider `matches` in a controlled environment; never log raw inputs |
| `403` after successful authentication | Missing authority, CSRF rejection, other security rule | Test permissions and CSRF separately |
| Every password logs in | Likely custom auth always succeeding or test using a mock principal, not necessarily NoOp | Trace the authentication provider and test wrong passwords |
| Configured password works, yet DB holds plaintext | NoOp or broken custom password storage | Audit config and stored formats; prioritize incident response |
| Bcrypt hashes differ for the same raw input | Random salt | Use `matches`, never compare two `encode` calls |
| Hash has `{bcrypt}`, yet direct BCrypt returns false | Direct encoder given delegating prefix | Align mapping/format or unwrap in a controlled migration |
| `@WithMockUser` login test passes, Basic login fails | Mock bypasses provider and password checks | Write real `httpBasic`/form-login integration tests |
| User `user` appears after deployment | Spring Boot default user auto-config was never replaced | Inspect user-source beans and generated-password logs |
| Works locally, prod exposes `lab-admin` account | Test profile/fixtures accidentally active | Enforce CI/CD guards, remove/manage accounts, audit binaries/configs |

### 13.1. Do Not “Fix” Password Errors by Opening `permitAll()`

If authentication fails, changing:

```java
.authorizeHttpRequests(auth -> auth
    .anyRequest().permitAll())
```

merely **removes authentication/authorization requirements** without fixing password encoding. This is a dangerous anti-pattern. Isolate `PasswordEncoder`, `UserDetailsService`, `AuthenticationManager`, and `SecurityFilterChain` to find which layer failed. Never disable CSRF or filters just to turn tests green.

### 13.2. Never Log or Echo Credentials While Debugging

Never write login request bodies, `Authorization: Basic ...`, password hashes, reset tokens, `JSESSIONID`, or access tokens into logs, metric labels, or error messages. You may log correlation IDs, outcomes, mechanism types, redacted exception classes, and normalized user IDs when permitted by policy. Keep secrets out of URLs and command histories.

### 13.3. Rate Limiting and Credential Stuffing

Good password hashing reduces risk from **offline data dumps**. It does not stop **online password guessing** or credential stuffing using passwords leaked from other services. Apply IP/account/device/risk rate limits, MFA/step-up, and anomaly detection; avoid naive lockouts easily abused to DoS victim accounts.

## 14. Minimum Test Matrix for Password Configuration

| Check | Input / State | Expectation |
| --- | --- | --- |
| NoOp behavior in isolated unit test | `encode("x")` | Returns `"x"` verbatim, proving insecurity |
| Delegating new encode | `encode("x")` | Carries `{bcrypt}` per current factory |
| Delegating matches valid | Right raw + bcrypt hash | true |
| Delegating matches invalid | Wrong raw + bcrypt hash | false |
| Bounded legacy mapping | Right raw + `{noop}x` | true while mapping remains active |
| Unknown prefix | Raw + unprefixed/unknown ID | Exception / fail closed |
| Direct BCrypt | `$2...` hash + direct encoder | matches true |
| Wrong format | `{bcrypt}...` + direct BCrypt encoder | Not accepted automatically |
| Lab user store | `student` password hash | Plaintext is not stored |
| GET /me anonymous | No credentials | 401 |
| GET /me valid | Student right password | 200 |
| GET /me invalid | Student wrong password | 401 |
| GET /admin student | Right password, missing ADMIN | 403 |
| GET /admin lab-admin | Has ROLE_ADMIN | 200 |
| POST /notes missing CSRF | Student valid credentials | 403 |
| POST /notes valid CSRF | Student has NOTES_WRITE | 200 |
| POST /notes lab-admin | Missing NOTES_WRITE | 403 |
| Non-lab profile | No demo users | Demo accounts cannot log in |
| Production user source | No sample passwords | Supplied by controlled store/IdP |
| CI/deployment | Lab profile, noop bean, `{noop}` test credentials | Blocked from production images/configs |

The status codes above belong to the sample app with HTTP Basic, specific rules, and CSRF enabled. If a project uses form login, anonymous requests may get a 302 redirect; with OAuth2/JWT, providers and outputs differ. Never compare status codes without considering configuration context.

## 15. Pre-Deployment Review Checklist

### PasswordEncoder Configuration

- [ ] No `@Bean NoOpPasswordEncoder` or `return NoOpPasswordEncoder.getInstance()` in production configs?
- [ ] No new stored passwords created using `{noop}` or plaintext?
- [ ] Verified whether the encoder bean is direct bcrypt or delegating, and stored formats match?
- [ ] If using delegating, no broad NoOp fallback configured for unknown IDs?
- [ ] Time-bound plan in place to upgrade remaining legacy/`{noop}` hashes?
- [ ] Adaptive algorithm and work factor chosen per guidelines and real-hardware benchmarks?
- [ ] No plain MD5/SHA-1/SHA-256, Base64, or reversible encryption used for password storage?

### Secrets and Accounts

- [ ] No `admin`/`user`/`demo` accounts with public shared passwords in production?
- [ ] No `User.withDefaultPasswordEncoder()` with hardcoded raw passwords in production?
- [ ] No `spring.security.user.password=...` carried over from sample configs in deployment?
- [ ] Test users confined to `src/test` or a `lab` profile blocked by CI/CD?
- [ ] Real user source/IdP, admin provisioning, lifecycle, and revocation controls in place?
- [ ] Password hashes, secrets, and Basic headers excluded from logs, traces, and responses?
- [ ] Passwords transmitted exclusively over HTTPS, never plain HTTP Basic?
- [ ] Password change/reset, MFA/step-up, rate limits, and auditing configured properly?

### Testing and Operations

- [ ] Any `NoOp` unit test lives strictly in test code, never as a live application bean?
- [ ] Integration tests verify passwords through the real provider, not `@WithMockUser` alone?
- [ ] Tests cover wrong passwords, locked accounts, wrong roles, CSRF, and denied URLs?
- [ ] App does not expose an unexpected Boot default user?
- [ ] Production-profile tests confirm lab credentials cannot authenticate?
- [ ] Metrics/audits track legacy logins and migration progress without logging plaintext?
- [ ] Incident response plan ready if plaintext passwords were ever stored (resets/rotation, blast-radius check, legal/policy notifications)?
- [ ] Rollback/migration tests and latency thresholds checked when raising work factors?

## 16. Quick Self-Check

**Question 1.** What does `NoOpPasswordEncoder.encode("hello")` produce?

**Answer:** `"hello"`. No salt, no hash. The password remains plaintext.

**Question 2.** Does saving `{noop}hello` in the DB encrypt the password?

**Answer:** No. `{noop}` is an ID for the delegating decoder, and `hello` is plaintext.

**Question 3.** With the default `DelegatingPasswordEncoder`, does `encode("hello")` output `{noop}hello`?

**Answer:** No. Spring Security 6.5's default factory uses `bcrypt` to encode new passwords, usually producing `{bcrypt}...`. It retains select legacy IDs for matching purely for compatibility.

**Question 4.** If `User.withDefaultPasswordEncoder()` already hashes, why not hardcode it in production source?

**Answer:** The raw password still sits in source and compiled bytecode, so it can be read or reused. Hashing at storage does not solve secrets exposed in code.

**Question 5.** Should `{noop}` be prepended to every password missing a prefix to fix an ID null error?

**Answer:** No. That can turn legacy hashes into unusable strings or expose unprotected passwords. Inventory formats, migrate properly, and fail closed on unrecognized entries.

**Question 6.** Do direct `BCryptPasswordEncoder` and `DelegatingPasswordEncoder` share the exact same storage format?

**Answer:** Not quite. Direct bcrypt produces `$2...` hashes; default Delegating adds the `{bcrypt}` prefix to identify the encoder.

**Question 7.** If a `@WithMockUser` test passes, does that prove the password encoder is wired correctly?

**Answer:** No. Mock users bypass the password provider. Use `httpBasic`/form-login tests with a real user store and encoder.

**Question 8.** BCrypt protects passwords in the database, so why is HTTPS still required?

**Answer:** Clients transmit raw passwords to the server; over plain HTTP without TLS, network attackers can steal credentials before the backend ever hashes or matches them.

**Question 9.** Does `NoOpPasswordEncoder` help stop online brute-force attacks?

**Answer:** No. It merely compares plaintext strings. Stopping brute-force requires rate limits, policies/monitoring, MFA/step-up, and related defenses.

**Question 10.** If an application accidentally deploys sample users to the Internet, is switching from NoOp to BCrypt enough to resolve the incident?

**Answer:** No. Public credentials may already have been used. Disable/delete sample accounts, rotate credentials, inspect audit/access logs, revoke sessions/tokens, assess impact, and block recurrence in CI/CD.

## 17. Key Takeaways Summary

1. **`NoOpPasswordEncoder` = zero password protection at rest.** It suits only isolated tests or planned legacy migrations, never a production `PasswordEncoder`.
2. **`{noop}` is a compatibility format tag, not a hash.** The password after it remains plaintext.
3. **Default `DelegatingPasswordEncoder` encodes new hashes with bcrypt** and the `{bcrypt}` prefix; being able to read legacy formats does not justify writing new legacy records.
4. **`withDefaultPasswordEncoder()` may hash, yet hardcoded raw passwords still leak in source.** Sample accounts and passwords must never enter real environments.
5. **Pair adaptive password hashing with TLS and a real identity source.** BCrypt/Argon2id/scrypt/PBKDF2, cost tuning, monitoring, rate limiting, lifecycle, and secret management complement one another.
6. **Test the real authentication path:** send real passwords through the provider/filter rather than relying on mock principals, and test both failed passwords and authorization.
7. **Migrations require format inventories and fail-closed behavior**, never shortcuts with a NoOp fallback or arbitrary `{noop}` prefixes.
8. **Lab/test profiles are only risk-reduction tools for study**; production needs real account provisioning, CI/CD guards, and zero public test credentials.

## Official Documentation and Security Guidance

- [Spring Security 6.5 — Password Storage, DelegatingPasswordEncoder, {id} format, NoOp, and withDefaultPasswordEncoder](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security 6.5 — NoOpPasswordEncoder Javadoc (deprecated/insecure)](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/NoOpPasswordEncoder.html)
- [Spring Security 6.5 — PasswordEncoder Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/PasswordEncoder.html)
- [Spring Security 6.5 — BCryptPasswordEncoder Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/bcrypt/BCryptPasswordEncoder.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 6.5 — UserDetailsService](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details-service.html)
- [Spring Security 6.5 — MockMvc HTTP Basic](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html)
- [Spring Security 6.5 — MockMvc CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
- [Spring Boot 3.5 — Spring Security Auto-Configuration](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html)
- [Spring Boot 3.5.16 release (2026-06-25) and end of 3.5.x OSS support](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/)
- [OWASP Password Storage Cheat Sheet — adaptive hashes, salt/pepper, and work factors](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [OWASP Authentication Cheat Sheet — protecting online logins and account lifecycles](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)

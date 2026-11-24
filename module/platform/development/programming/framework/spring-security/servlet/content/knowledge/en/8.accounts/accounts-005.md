# DaoAuthenticationProvider and the Credential Verification Process

> **Context:** Spring Security **Servlet**, Java 17+, Spring Security 6.x. This lesson focuses on how `DaoAuthenticationProvider` verifies username/password against accounts supplied by `UserDetailsService`. The final example uses Spring Boot 3.x for a runnable Servlet application; the provider mechanism also applies when configuring Spring Security without Boot.

## 1. Role of DaoAuthenticationProvider

When a user submits a username and password, the application has only received an **identity claim and proof**. You cannot yet treat the user as authenticated or trust roles sent by the client. You must verify the proof against trusted account data, and only then create an `Authentication` marked as authenticated.

`DaoAuthenticationProvider` is a Spring Security `AuthenticationProvider` for **username/password authentication**. It fetches account information via `UserDetailsService`, checks account status flags, uses `PasswordEncoder` to compare the input password with the stored hash, and then returns a valid `Authentication` or throws an `AuthenticationException`.

"DAO" does not mean the provider only works with JDBC/JPA. The provider has no direct knowledge of a `users` table or `UserRepository`; `UserDetailsService` can be backed by a database, an identity service, or an in-memory store.

| Component | Responsibility | Not Responsible For |
| --- | --- | --- |
| `BasicAuthenticationFilter` / `UsernamePasswordAuthenticationFilter` | Extracts credentials from HTTP requests, builds an authentication request, calls the manager, and handles HTTP success/failure | Does not verify BCrypt hashes itself |
| `AuthenticationManager` | The `authenticate(Authentication)` contract | Is not a DAO loading entities |
| `ProviderManager` | Common manager implementation, picks a compatible `AuthenticationProvider` | Does not know the users table schema |
| **`DaoAuthenticationProvider`** | Verifies username/password using `UserDetailsService` and `PasswordEncoder` | Does not directly set up HTTP sessions or grant URL access permissions |
| `UserDetailsService` | Looks up and returns `UserDetails` by username | Does not authenticate passwords itself |
| `PasswordEncoder` | Hashes passwords when saving, compares `matches(raw, encoded)` at login | Does not look up users |
| `UserDetails` | Supplies encoded password, account status, and authorities from a trusted source | Does not itself validate HTTP requests |

Distinguish **authentication** from **authorization**. The DAO provider only verifies credentials/accounts. An authenticated user can still be rejected by `AuthorizationFilter` for lacking endpoint permissions.

## 2. Overall Flow in a Servlet Application

```text
HTTP request: Basic Authorization header or POST login form
                  |
                  v
Spring Security filter in the Servlet filter chain
  - reads username/password
  - creates unauthenticated UsernamePasswordAuthenticationToken
                  |
                  v
AuthenticationManager.authenticate(request)
                  |
                  v
ProviderManager
  - finds AuthenticationProvider with matching supports()
                  |
                  v
DaoAuthenticationProvider
  +--> UserDetailsService.loadUserByUsername(username)
  +--> Checks account non-locked, enabled, non-expired
  +--> PasswordEncoder.matches(rawPassword, storedPasswordHash)
  +--> Checks credentials non-expired
  +--> Creates authenticated Authentication
                  |
         +--------+------------+
         |                     |
    Authentication       AuthenticationException
    with principal,      (BadCredentials, Disabled,
    authorities           Locked, ...)
         |                     |
         v                     v
Filter saves/sets        Filter/entry point
SecurityContext          handles failure (e.g., HTTP 401)
         |
         v
AuthorizationFilter: checks request authorization
         |
         v
Controller or 403 if insufficient authorities
```

**An unauthenticated request** is typically a `UsernamePasswordAuthenticationToken` with username and raw password. Upon success, the provider creates a different `Authentication` object with the verified principal/authorities. `ProviderManager` typically erases credentials from the result whenever possible. Afterward, the **security filter**, not the DAO provider, handles `SecurityContext`, cookies/sessions/HTTP responses.

`DaoAuthenticationProvider` inherits behavior from `AbstractUserDetailsAuthenticationProvider`, so it also includes account status checks and optional caching/retry mechanisms depending on configuration.

## 3. The Provider's Input Must Be an Untrusted Request

Example of an unauthenticated token:

```java
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;

Authentication request =
        UsernamePasswordAuthenticationToken.unauthenticated(
                "lan", "mat-khau-tu-form");

System.out.println(request.isAuthenticated()); // false
System.out.println(request.getName());          // lan
```

This is a **fragment** to understand the contract, not a standalone class. `principal` is initially the username string; `credentials` is the submitted password; `authorities` are not yet granted. Never take roles/authorities sent by the client to construct an authenticated result before provider verification.

`DaoAuthenticationProvider` primarily supports `UsernamePasswordAuthenticationToken`. The `supports(Class<?>)` method only answers **whether the provider can process this authentication type**, not whether the credentials are valid.

The successful output may be an authenticated `UsernamePasswordAuthenticationToken`, though `principal` is normally switched to `UserDetails` (or `String` if configured differently). Therefore, blindly casting `authentication.getPrincipal()` to `String` is unsafe. For general code, `authentication.getName()` is usually more convenient.

## 4. UserDetailsService Loads the Account, Does Not Verify Passwords

Spring Security's contract:

```java
public interface UserDetailsService {
    UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException;
}
```

This is an abbreviated signature for illustration; **you do not need to define this interface** in your project because Spring Security already provides it.

`UserDetailsService` supplies `UserDetails`, typically containing:

| Method/Property | Meaning During Matching |
| --- | --- |
| `getUsername()` | Username retrieved from the account store |
| `getPassword()` | **Stored password hash**, not plaintext |
| `getAuthorities()` | Trusted roles/authorities from the server or IdP |
| `isEnabled()` | Whether the account is enabled |
| `isAccountNonLocked()` | `false` means the account is locked |
| `isAccountNonExpired()` | `false` means the account has expired |
| `isCredentialsNonExpired()` | `false` means credentials have expired |

For example, given a `users` table with columns `password_hash`, `enabled`, `locked`: the `UserDetailsService` implementation must map these fields accurately. If `locked=true` in the database, it must return `isAccountNonLocked()==false`; if you forget to map it, a locked account could still log in. Roles must come from trusted data, not from a `role` field in client-submitted JSON.

If the username is not found, the service throws `UsernameNotFoundException`. Under default configuration, `DaoAuthenticationProvider` normally **masks this detail into `BadCredentialsException`** so login failure messages do not reveal whether an account exists.

In real environments, enforce unique constraints or clear username/email normalization rules; watch out for case sensitivity, Unicode, and username changes. Avoid leaking account store details through exception messages.

## 5. Verification Process: Layer-by-Layer Checks

### 5.1. Selecting a Compatible Provider

`ProviderManager` typically manages a list of `AuthenticationProvider`s. For a `UsernamePasswordAuthenticationToken`, it picks a provider whose `supports(...)` matches. If no provider supports it and no parent manager resolves it, a `ProviderNotFoundException` may occur.

One `ProviderManager` can hold multiple providers. A provider can return `null` to pass handling along; for certain `AuthenticationException`s, the manager may try other providers depending on the exception type; severe account-status errors can halt the chain immediately. Do not assume "all providers are always called" or "only the first provider is ever called".

### 5.2. Loading UserDetails

The DAO provider takes the username from the input, calls `loadUserByUsername`, and obtains the encoded password, flags, and authorities. It does not trust any password hash sent by the client. Some configurations use `UserCache`; when a cache is present, the provider may read stale info and retry from the data source in certain scenarios. Design cache invalidation when passwords, roles, or disabled/locked states change.

### 5.3. Checking Status Before Password Comparison

Under `AbstractUserDetailsAuthenticationProvider`'s default mechanism, these conditions are normally rejected:

- `isAccountNonLocked()==false` -> `LockedException`.
- `isEnabled()==false` -> `DisabledException`.
- `isAccountNonExpired()==false` -> `AccountExpiredException`.

These account-status steps are separate from whether the raw password matches the hash. A locked account is not allowed "through" just because the password is right.

### 5.4. PasswordEncoder.matches Verifies the Password

The core step is:

```java
// Conceptual fragment: the provider itself calls the equivalent of this comparison.
boolean correct = encoder.matches(rawPassword, storedPasswordHash);
```

`rawPassword` comes from the request; `storedPasswordHash` comes from `UserDetails.getPassword()`. With BCrypt, the hash includes salt/cost and `matches` knows how to check it. Therefore **do not** do this:

```java
// WRONG for salted hashes: two encode calls are not guaranteed to match.
boolean correct = encoder.encode(rawPassword)
        .equals(storedPasswordHash);
```

Also never store plaintext in the DB, and do not treat password hashing as reversible encryption. `PasswordEncoder.matches` returns false on a wrong password, and the provider throws `BadCredentialsException` as normal behavior. If you hit an encoder-id/hash-format error during algorithm migration, that is a data configuration issue to fix, not an indication the user typed the wrong password.

**When choosing an encoder:**

- `BCryptPasswordEncoder` accepts BCrypt hashes generated by `encode`, typically starting with a BCrypt prefix such as `$2a$`.
- `DelegatingPasswordEncoder` uses a storage format usually prefixed with an algorithm ID, e.g., `{bcrypt}...`, to identify the algorithm. Hashes without an ID may not be handled by the default decoder unless a compatibility fallback is configured.
- You can tune the work factor/cost according to performance and security targets. Upgrading hashes when users log in can use `PasswordEncoder.upgradeEncoding` and `UserDetailsPasswordService` when configured; **it does not happen automatically just by swapping beans**.

### 5.5. Checking Expired Credentials

`isCredentialsNonExpired()==false` normally leads to `CredentialsExpiredException`. This differs from "wrong password entered"; the application may need a password-change flow instead of granting a normal access session.

### 5.6. Creating a Successful Authentication

After passing all checks, the provider builds a result with `isAuthenticated()==true`, a trusted `principal`, and `GrantedAuthority` instances from the user. For example, a user granted `ROLE_READER` receives authority `ROLE_READER`; never grant `ROLE_ADMIN` just because the request targets `/admin`.

By default, `ProviderManager` attempts to erase credentials on the result via `CredentialsContainer.eraseCredentials()` when available. In practice, do not rely on every provider always returning `getCredentials()==null`; proactively avoid logging secrets. Be careful when a `UserDetails` object is cached/shared and could be affected by credential erasure.

## 6. Success Outcomes and Failures to Distinguish

| Scenario | Typical Exception / Result | Handling Direction |
| --- | --- | --- |
| Valid username/password and valid account | Authenticated `Authentication` with authorities | Filter saves context, then authorization checks permissions |
| Password mismatch | `BadCredentialsException` | Safe login-failure response, avoiding detail leaks |
| Username not found | Typically `BadCredentialsException` at provider boundary | Prevent username enumeration |
| Account locked | `LockedException` | Follow lock/unlock policy |
| Account disabled | `DisabledException` | Check activation status |
| Account expired | `AccountExpiredException` | Account expiration policy |
| Credentials expired | `CredentialsExpiredException` | Credential change/reset flow |
| No provider supports token | `ProviderNotFoundException` | Inspect manager/provider wiring and token type |
| Data store/service error | Typically `AuthenticationServiceException` or infrastructure error | Handle service errors, do not disguise as wrong password |

`DaoAuthenticationProvider` **does not return HTTP 401, 403, or 302 itself**. It returns an `Authentication` or throws `AuthenticationException`. At the Servlet filter layer, entry points and failure handlers decide the appropriate status or redirect: HTTP Basic usually returns 401; form login may redirect to the login page. If authentication succeeds but lacks an authority required by the endpoint, authorization usually returns 403.

## 7. Runnable Example: Java 17 + Spring Security 6 + Servlet HTTP Basic

Create a Maven application with Spring Boot 3.3.5 and web/security dependencies. The example uses in-memory accounts to clearly show success, wrong-password, locked, and disabled cases. All passwords in the code are **strictly for learning**; never bring demo accounts into real systems.

| Username | Demo Password | Status | Role |
| --- | --- | --- | --- |
| `lan` | `lan-pass` | Normal | `READER` |
| `quan` | `quan-pass` | Normal | `ADMIN` |
| `khoa` | `khoa-pass` | Locked | `READER` |
| `my` | `my-pass` | Disabled | `READER` |

Structure:

```text
dao-auth-demo/
├── pom.xml
└── src/main/java/demo/daologin/
    ├── DaoAuthApplication.java
    ├── SecurityConfig.java
    └── DemoController.java
```

### 7.1. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>dao-auth-demo</artifactId>
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

### 7.2. `DaoAuthApplication.java`

```java
package demo.daologin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DaoAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(DaoAuthApplication.class, args);
    }
}
```

### 7.3. `SecurityConfig.java`

```java
package demo.daologin;

import java.util.List;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails lan = User.withUsername("lan")
                .password(encoder.encode("lan-pass"))
                .roles("READER")
                .build();
        UserDetails quan = User.withUsername("quan")
                .password(encoder.encode("quan-pass"))
                .roles("ADMIN")
                .build();
        UserDetails khoa = User.withUsername("khoa")
                .password(encoder.encode("khoa-pass"))
                .roles("READER")
                .accountLocked(true)
                .build();
        UserDetails my = User.withUsername("my")
                .password(encoder.encode("my-pass"))
                .roles("READER")
                .disabled(true)
                .build();
        return new InMemoryUserDetailsManager(lan, quan, khoa, my);
    }

    @Bean
    DaoAuthenticationProvider daoProvider(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider = new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        return provider;
    }

    @Bean
    AuthenticationManager authenticationManager(DaoAuthenticationProvider provider) {
        return new ProviderManager(List.of(provider));
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AuthenticationManager manager) throws Exception {
        // Force HTTP Basic to use the exact declared manager/provider.
        http.authenticationManager(manager);
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/whoami").authenticated()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
        );
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    ApplicationRunner verifyDaoFlow(AuthenticationManager manager) {
        return args -> {
            Authentication input =
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "lan", "lan-pass");

            System.out.println("input.authenticated=" + input.isAuthenticated());
            Authentication success = manager.authenticate(input);
            System.out.println("output.authenticated=" + success.isAuthenticated());
            System.out.println("output.name=" + success.getName());
            System.out.println("output.authorities=" + success.getAuthorities());
            System.out.println("output.credentialsErased="
                    + (success.getCredentials() == null));

            try {
                manager.authenticate(
                        UsernamePasswordAuthenticationToken.unauthenticated(
                                "lan", "wrong"));
            } catch (BadCredentialsException e) {
                System.out.println("wrongPassword=" + e.getClass().getSimpleName());
            }
            try {
                manager.authenticate(
                        UsernamePasswordAuthenticationToken.unauthenticated(
                                "missing", "anything"));
            } catch (BadCredentialsException e) {
                System.out.println("unknownUser=" + e.getClass().getSimpleName());
            }
            try {
                manager.authenticate(
                        UsernamePasswordAuthenticationToken.unauthenticated(
                                "khoa", "khoa-pass"));
            } catch (LockedException e) {
                System.out.println("lockedUser=" + e.getClass().getSimpleName());
            }
            try {
                manager.authenticate(
                        UsernamePasswordAuthenticationToken.unauthenticated(
                                "my", "my-pass"));
            } catch (DisabledException e) {
                System.out.println("disabledUser=" + e.getClass().getSimpleName());
            }
        };
    }
}
```

**Code analysis:**

1. `InMemoryUserDetailsManager` holds `UserDetails`; `password(encoder.encode(...))` stores the BCrypt hash, never keeping raw passwords in the user's password property.
2. The `DaoAuthenticationProvider` bean knows `UserDetailsService` and `PasswordEncoder`, without needing to know what storage system sits behind it.
3. `ProviderManager(List.of(provider))` manages the provider for authentication. `http.authenticationManager(manager)` connects the chain's HTTP Basic filter to this manager.
4. `verifyDaoFlow` runs at startup, calling the manager directly to show **unauthenticated input and authenticated output**. Calling the manager directly **does not automatically save `SecurityContext` into a session**; HTTP flows are handled by security filters.
5. `getAuthorities()` fetches roles from the user store: `ROLE_READER`, not from the request. `hasRole("ADMIN")` checks `ROLE_ADMIN` under the default prefix.
6. The wrong-password, unknown-user, locked, and disabled cases use specific exception types to illustrate the check branches. Outside a lesson, never return full internal exception details to clients.
7. The example only handles GET so CSRF policy does not need changes. Real applications must evaluate CSRF according to cookies/sessions, API authentication, and how clients operate.

### 7.4. `DemoController.java`

```java
package demo.daologin;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/whoami")
    public String whoami(Authentication authentication) {
        return "user:" + authentication.getName();
    }

    @GetMapping("/admin")
    public String admin(Authentication authentication) {
        return "admin:" + authentication.getName();
    }
}
```

### 7.5. Build, Run, and Observe Stdout

In the directory containing `pom.xml`:

```bash
mvn spring-boot:run
```

Upon successful startup, besides Spring Boot's default log lines, `ApplicationRunner` prints in order (expected with the sample configuration):

```text
input.authenticated=false
output.authenticated=true
output.name=lan
output.authorities=[ROLE_READER]
output.credentialsErased=true
wrongPassword=BadCredentialsException
unknownUser=BadCredentialsException
lockedUser=LockedException
disabledUser=DisabledException
```

From the output, we can see: a correct password yields an `Authentication` with the user's authority, while a wrong password and nonexistent username are masked under the same error category. Locked/disabled accounts are not treated as successful logins. The result returned by `ProviderManager` has its credentials erased when the token supports that mechanism.

### 7.6. Testing the Servlet Flow via HTTP Basic

The following `curl` commands are for POSIX shells. The comments below show the **expected HTTP status/body** for the sample app at `localhost:8080`.

```bash
# Unauthenticated:
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/whoami
# 401

# Wrong password:
curl -s -o /dev/null -w '%{http_code}\n' \
  -u lan:wrong http://localhost:8080/whoami
# 401

# Valid username/password:
curl -s -u lan:lan-pass http://localhost:8080/whoami
# user:lan

# Authenticated but lacks ROLE_ADMIN:
curl -s -o /dev/null -w '%{http_code}\n' \
  -u lan:lan-pass http://localhost:8080/admin
# 403

# Has ROLE_ADMIN:
curl -s -u quan:quan-pass http://localhost:8080/admin
# admin:quan

# Locked account:
curl -s -o /dev/null -w '%{http_code}\n' \
  -u khoa:khoa-pass http://localhost:8080/whoami
# 401

# Disabled account:
curl -s -o /dev/null -w '%{http_code}\n' \
  -u my:my-pass http://localhost:8080/whoami
# 401
```

All passwords above are strictly for local learning. HTTP Basic transmits credentials in headers; use only with **HTTPS** on real systems. Never put real passwords into shell history or logs.

**Why does `lan` get 403 on `/admin` despite the right password?** `DaoAuthenticationProvider` already authenticated `lan` properly, but the `hasRole("ADMIN")` policy requires `ROLE_ADMIN`; `lan` only has `ROLE_READER`. A 403 belongs to the **authorization** layer, not a sign that the provider failed password comparison.

## 8. When Using a Real Database

Replace `InMemoryUserDetailsManager` with a `UserDetailsService` implementation. The provider still works against the interface:

```text
POST login or Basic header
        |
        v
DaoAuthenticationProvider
        |
        v
UserDetailsService.loadUserByUsername
        |
        v
UserRepository / JDBC / external user store
        |
        v
UserDetails: password hash + flags + authorities
        |
        v
PasswordEncoder.matches(raw, encoded)
        |
        v
Authentication succeeded or exception
```

Example mapping from JPA (a fragment **not runnable standalone** because the project must declare `UserRepository`, `UserEntity`, and the authority mapping helper):

```java
@Override
public UserDetails loadUserByUsername(String username) {
    UserEntity entity = repository.findByUsername(username)
            .orElseThrow(() -> new UsernameNotFoundException("User not found"));

    return User.withUsername(entity.getUsername())
            .password(entity.getPasswordHash())
            .disabled(!entity.isEnabled())
            .accountLocked(entity.isLocked())
            .authorities(mapTrustedAuthorities(entity))
            .build();
}
```

Integration notes:

- `getPasswordHash()` must return the **intact encoded hash** compatible with `PasswordEncoder`; do not call `encode` on every user load to "refresh" the password hash.
- Enforce unique constraints, consistent username/email normalization, and account for Unicode/case-sensitivity.
- Roles/permissions must come from trusted sources; map `ROLE_...` and business authorities according to policy.
- Account flags must be mapped accurately; locked/disabled data must reflect onto `UserDetails`.
- If caching is used, invalidate caches when passwords/roles/flags change. Specifically avoid cached objects being unintentionally mutated by `eraseCredentials`.
- Never weaken password policies when migrating from BCrypt to a Delegating encoder. You can use `upgradeEncoding` + `UserDetailsPasswordService` if truly designing a new hash-storage strategy.
- Reinforce with rate limiting, credential-stuffing defenses, safe audit logging, HTTPS, session/cookie protection, and CSRF per application design. The DAO provider does not supply all of these defense layers automatically.

## 9. Common Confusions

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Wrong password still logs in successfully | Code constructs an authenticated token from input, bypassing the provider | Ensure the filter calls `AuthenticationManager`, and grant authorities only after verification |
| `ProviderNotFoundException` | Manager has no provider supporting the token | Check `ProviderManager` and `supports` |
| Every user gets 401 after changing encoder | Password hashes in the store do not match the decoder | Check BCrypt/Delegating, `{bcrypt}` prefix, storage, and migration |
| Unknown user raises `BadCredentialsException` | Mechanism masking username-existence details | This is typically intentional protection against account enumeration |
| Locked user can still log in | `UserDetails.isAccountNonLocked()` mapped wrong or filter uses another provider | Cross-check flags and manager wiring |
| Login works but `/admin` returns 403 | Missing `ROLE_ADMIN` or CSRF/other policy denial | Check authorities and authorization rules |
| No password visible in the result | `ProviderManager` erased credentials | Do not rely on credentials in the authenticated result |
| User changed roles yet requests keep old roles | Session `SecurityContext` or user cache holds stale data | Design proper refresh/re-auth/invalidation |
| DB down produces an HTTP response like wrong password | Service error handling layer does not distinguish | Handle `AuthenticationServiceException`/infrastructure errors safely |
| Basic credentials exposed in logs | Logging raw headers or `Authentication` before secret erasure | Redact credentials and restrict log access |

A good debugging sequence is: **did the filter extract the right username/password -> did `ProviderManager` pick the right provider -> did `UserDetailsService` load the right user -> are flags valid -> did `PasswordEncoder.matches` succeed -> does output have authorities -> what did HTTP authorization decide**.

Do not add `permitAll()` or disable CSRF to fix a password error; those belong to different layers.

## 10. Comparison with JWT, Form Login, and Other Mechanisms

- **Form login** uses `UsernamePasswordAuthenticationFilter`; username/password is usually verified by the DAO provider, then the filter handles sessions/context and success/failure handlers.
- **HTTP Basic** uses `BasicAuthenticationFilter`; credentials can still be verified by `DaoAuthenticationProvider`, though clients send the header on every request.
- **JWT Resource Server** uses dedicated JWT authentication components (decoders, validators, appropriate providers); do not feed a JWT string to the DAO provider expecting it to verify signatures/issuer/audience.
- **OAuth2/OIDC login, WebAuthn, OTP, or API keys** likewise need appropriate authentication components. They can coexist alongside a username/password system, but the DAO provider does not handle every type of credential itself.

**DaoAuthenticationProvider does not replace SecurityFilterChain.** The security chain selects filters, authentication entry points, sessions, and authorization rules. The provider is only the username/password verification step inside that flow.

## 11. Self-Review Questions

1. **Does UserDetailsService compare passwords?** No. It loads the user; the provider uses `PasswordEncoder.matches`.
2. **Does DaoAuthenticationProvider know about the users table?** No. It depends on `UserDetailsService`.
3. **Why use `matches(raw, encoded)` instead of `encode(raw).equals(encoded)`?** Algorithms like BCrypt use a salt; each encode call can produce a different hash.
4. **Can a locked account with the right password log in?** No, it is rejected based on account status.
5. **Can an unknown user turn into BadCredentialsException?** Yes, masking details is common default behavior.
6. **Does the DAO provider set SecurityContext and HTTP session itself?** No. Security filters and the context repository handle that part.
7. **Does the authentication result get role ADMIN because the client sent role ADMIN to the API?** No. Authorities must be fetched from a trusted source after verification.
8. **Why return HTTP 403 when the password is correct?** Authentication succeeded, but authorization lacked the required role/permission or another request policy denied it.
9. **If switching from in-memory to JPA, do you have to rewrite the provider?** Usually you only swap `UserDetailsService` and configure data/encoder, without changing DAO provider logic.
10. **Do password hashes always upgrade automatically after swapping encoders?** No, a corresponding mechanism like `UserDetailsPasswordService` and upgrade conditions are required.

## 12. Implementation Checklist

- [ ] Accept username/password as an **unauthenticated** `Authentication`; never trust client-supplied roles.
- [ ] Use `UserDetailsService` to return accurate hashes/flags/authorities from a server-side store.
- [ ] `PasswordEncoder` matches the hash format, uses `matches` for verification, and never stores raw passwords.
- [ ] Check locked/disabled/expired/credential-expired flags, granting no access when unmet.
- [ ] Handle `AuthenticationException` at the appropriate filter/entry point without leaking username enumeration.
- [ ] Never arbitrarily log passwords, Basic headers, bearer tokens, or encoded passwords.
- [ ] Test valid passwords, wrong passwords, unknown users, locked/disabled accounts, and authenticated users lacking permissions.
- [ ] Ensure HTTP filters invoke the right manager/provider; do not confuse authentication with authorization.
- [ ] Enforce HTTPS, brute-force defenses, controlled auditing, and appropriate session/CSRF policies.
- [ ] Manage password-hash migrations, account status, user caches, and permissions across the account lifecycle.

**Mechanism summary:** `DaoAuthenticationProvider` performs **look up UserDetails -> check account status -> `PasswordEncoder.matches` -> check credential expiry -> return trusted Authentication or throw AuthenticationException**. `ProviderManager` coordinates providers; Servlet security filters connect this process to HTTP requests, `SecurityContext`, and access control.
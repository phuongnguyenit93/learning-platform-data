# Customizing the User Source via `UserDetailsService` in Spring Security

> **Scope:** Spring Security for Servlet applications, username/password authentication with Java 17+ and Spring Boot 3.x. The goal is to replace the default user source with an application-managed data source, understand how Spring Security uses that data, and verify success/failure cases. Do not conflate `UserDetailsService` with JWT/OIDC authentication mechanisms or WebFlux's `ReactiveUserDetailsService`.

## 1. When Is a Custom `UserDetailsService` Needed?

An initial application might use Spring Boot's sample account or `InMemoryUserDetailsManager`. In real deployments, accounts typically reside in a database with fields such as username, password hash, locked/enabled status, and authority list. **`UserDetailsService` is the extension point for fetching that account data by username.** As a result, the application continues using Spring Security's standard security mechanisms instead of rewriting the entire login flow.

After this lesson, you should be able to:

1. Distinguish the responsibility of **loading user information** from **verifying the password**.
2. Map a data-source record to `UserDetails` in compliance with the contract.
3. Register the service bean so the username/password flow can use your custom accounts.
4. Test non-existent accounts, wrong passwords, locked accounts, valid logins, and missing roles.
5. Know when a different `AuthenticationProvider` or a dedicated mechanism for JWT/OIDC is required.

## 2. The `UserDetailsService` Contract

Basic interface:

```java
package org.springframework.security.core.userdetails;

public interface UserDetailsService {
    UserDetails loadUserByUsername(String username)
        throws UsernameNotFoundException;
}
```

`loadUserByUsername` **takes only the username**, not the raw password. It must return a complete `UserDetails`, and **must not return `null`**. If the user is not found, it must throw `UsernameNotFoundException`. Per the interface contract, a user with no `GrantedAuthority` may also be treated as unable to be validly loaded.

`UserDetails` provides the data the provider needs:

| Component | Meaning during authentication |
| --- | --- |
| `getUsername()` | Login name / account identifier. |
| `getPassword()` | **Stored hash**, not the raw password and not a value re-hashed when reading. |
| `getAuthorities()` | Authorities granted by a trusted system: `ROLE_USER`, `ROLE_ADMIN`, etc. |
| `isEnabled()` | Whether the account is enabled. |
| `isAccountNonLocked()` | Whether the account is not locked. |
| `isAccountNonExpired()` | Whether the account has not expired. |
| `isCredentialsNonExpired()` | Whether the credentials have not expired. |

You can use `org.springframework.security.core.userdetails.User` and the `User.withUsername(...)` builder to convert a database record into `UserDetails`. Only implement `UserDetails` directly when you genuinely need custom principal data and understand the credentials lifecycle.

### 2.1. Responsibility Boundaries

| Component | Responsibility |
| --- | --- |
| Application-defined `AccountRepository` | Read accounts and authorities from a database or internal service. |
| Custom `UserDetailsService` | Convert an account to `UserDetails`, throwing `UsernameNotFoundException` if missing. |
| `PasswordEncoder` | `encode` passwords when registering/changing passwords; `matches` to check a raw password against a hash. |
| `DaoAuthenticationProvider` | Call the service and encoder, and check account conditions during username/password authentication. |
| `AuthenticationManager` | Coordinate registered `AuthenticationProvider` instances. |
| Security filters | Read HTTP credentials, invoke authentication, and establish `SecurityContext`. |
| Authorization rules | Evaluate authorities after authentication to allow/deny resources. |

**Do not check passwords yourself inside `loadUserByUsername`**: this method has no password parameter, and `DaoAuthenticationProvider` is already responsible for matching via the encoder. Also do not grant `ROLE_ADMIN` merely because a client requests that role; authorities must come from server-side data/rules.

## 3. Username/Password Authentication Flow

```text
HTTP Basic or form login
        |
        v
Authentication Filter
        | creates unauthenticated UsernamePasswordAuthenticationToken
        v
AuthenticationManager (typically ProviderManager)
        |
        v
DaoAuthenticationProvider
        | calls loadUserByUsername(username)
        v
Custom UserDetailsService -> AccountRepository
        |
        v
UserDetails (username, stored hash, authorities, account flags)
        |
        +--> check account status
        +--> PasswordEncoder.matches(rawPassword, storedHash)
        |
        +-- failure --> authentication failure (APIs typically 401)
        |
        v
Authentication succeeds -> SecurityContext
        |
        v
Authorization rule checks authorities
        |-- sufficient permissions --> controller
        +-- missing permissions --> typically 403
```

The diagram is a conceptual model and does not depict the exact order of every internal step or every `SecurityFilterChain`.

**Distinguishing outcomes:**

- No credentials sent to a protected endpoint: **unauthenticated**, HTTP Basic APIs typically return 401.
- Non-existent username, wrong password, locked account: **authentication failed**, HTTP Basic APIs typically return 401. The server should avoid exposing details that allow account enumeration.
- Valid username/password but missing authority: **authenticated, insufficient permissions**, APIs typically return 403.
- Valid username/password and sufficient permissions: the endpoint continues processing, e.g., 200 on success.

With form login, the application may **redirect** to `/login` or `/login?error` instead of returning 401 directly. `UserDetailsService` does not decide the HTTP response.

## 4. Runnable Java 17+ Example

The example uses a custom in-memory repository. This is a **custom source** because `UserDetailsService` reads through a custom repository; switching to JPA/JDBC only requires replacing the repository adapter. HTTP Basic is enabled so 401 and 403 are clearly visible.

### 4.1. Gradle Configuration

Create `settings.gradle`:

```groovy
rootProject.name = 'userdetails-source-demo'
```

Create `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

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

Spring Boot 3.3.5 is pinned for example reproducibility, **not a claim of the latest version**. Use Gradle 8.x and JDK 17+; network access is needed to download dependencies the first time.

### 4.2. Complete Source Code

Create `src/main/java/demo/userdetails/UserDetailsSourceDemoApplication.java`:

```java
package demo.userdetails;

import java.util.List;
import java.util.Map;
import java.util.Optional;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Repository;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class UserDetailsSourceDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(UserDetailsSourceDemoApplication.class, args);
    }
}

record Account(
    String username,
    String passwordHash,
    List<String> authorities,
    boolean enabled,
    boolean locked
) {}

interface AccountRepository {
    Optional<Account> findByUsername(String username);
}

@Repository
class MapAccountRepository implements AccountRepository {
    private final Map<String, Account> accounts;

    MapAccountRepository(PasswordEncoder encoder) {
        accounts = Map.of(
            "reader", new Account(
                "reader", encoder.encode("reader123"),
                List.of("ROLE_USER"), true, false
            ),
            "admin", new Account(
                "admin", encoder.encode("admin123"),
                List.of("ROLE_USER", "ROLE_ADMIN"), true, false
            ),
            "locked", new Account(
                "locked", encoder.encode("locked123"),
                List.of("ROLE_USER"), true, true
            )
        );
    }

    @Override
    public Optional<Account> findByUsername(String username) {
        return Optional.ofNullable(accounts.get(username));
    }
}

@Service
class AccountUserDetailsService implements UserDetailsService {
    private final AccountRepository repository;

    AccountUserDetailsService(AccountRepository repository) {
        this.repository = repository;
    }

    @Override
    public UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException {
        Account account = repository.findByUsername(username)
            .orElseThrow(() ->
                new UsernameNotFoundException("Invalid credentials")
            );

        return User.withUsername(account.username())
            .password(account.passwordHash())
            .authorities(account.authorities().toArray(String[]::new))
            .disabled(!account.enabled())
            .accountLocked(account.locked())
            .build();
    }
}

@Configuration
class SecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable);

        return http.build();
    }
}

@RestController
class DemoApi {
    @GetMapping("/api/public")
    String publicApi() {
        return "public";
    }

    @GetMapping("/api/me")
    String me(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/api/admin")
    String adminApi() {
        return "admin";
    }
}
```

**Explanation of each part:**

1. `MapAccountRepository` holds three dummy accounts, each with a **BCrypt hash**, authority set, and status flags. The `AccountRepository` interface makes it easy to swap data sources without changing security code.
2. `AccountUserDetailsService` is a `@Service` bean implementing `loadUserByUsername`; if the repository finds nothing, it throws `UsernameNotFoundException` and **does not return `null`**.
3. The mapper supplies `account.passwordHash()` directly. `DaoAuthenticationProvider` uses the `PasswordEncoder` bean to check raw passwords; the service **does not re-hash and does not call `matches`**.
4. `.authorities(...)` assigns server-stored authorities. Reader has `ROLE_USER`, while admin also has `ROLE_ADMIN`.
5. `.accountLocked(account.locked())` preserves the lock state. Omitting this mapping can cause locked accounts to be treated as unlocked.
6. `hasRole("ADMIN")` checks for the `ROLE_ADMIN` authority by default; the remaining paths require `authenticated()`, except `/api/public`.
7. `.httpBasic(...)` enables Basic; `.formLogin(...disable)` disables login redirects, making API statuses clear. The endpoints only use GET, so CSRF does not need to be disabled.
8. In a basic username/password configuration, the service bean and encoder can be wired into `DaoAuthenticationProvider` by Spring Security. If the application already defines a custom manager/provider, inspect the actual wiring.

**Use the sample accounts and passwords only in learning environments.** Production requires HTTPS, storing hashes/roles in a protected data store, brute-force protection, and account lifecycle management.

### 4.3. Running and Observing

From the project directory, if the Gradle Wrapper is present:

```bash
./gradlew bootRun
```

On Windows, use `gradlew.bat bootRun`; if there is no wrapper, use `gradle bootRun` from a compatible Gradle 8.x installation. By default, the HTTP server listens on `http://localhost:8080`.

Each line below is a separate command run in a Bash terminal with `curl`:

```bash
# 1. No credentials sent
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/me

# 2. Non-existent username
curl -s -o /dev/null -w '%{http_code}\n' -u nobody:wrong http://localhost:8080/api/me

# 3. Wrong password
curl -s -o /dev/null -w '%{http_code}\n' -u reader:wrong http://localhost:8080/api/me

# 4. Locked account
curl -s -o /dev/null -w '%{http_code}\n' -u locked:locked123 http://localhost:8080/api/me

# 5. Valid reader login
curl -s -o /dev/null -w '%{http_code}\n' -u reader:reader123 http://localhost:8080/api/me

# 6. Reader lacking ADMIN role
curl -s -o /dev/null -w '%{http_code}\n' -u reader:reader123 http://localhost:8080/api/admin

# 7. Admin with sufficient permissions
curl -s -o /dev/null -w '%{http_code}\n' -u admin:admin123 http://localhost:8080/api/admin

# 8. Public resource
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/public
```

Expected results in order, one line per command:

```text
401
401
401
401
200
403
200
200
```

Additionally, `curl -s -u reader:reader123 http://localhost:8080/api/me` returns the body `reader`. This confirms that the principal actually has the username from the repository.

**Explanation:** (1) unauthenticated; (2) record not found; (3) wrong password; (4) locked account; all four typically return 401 with Basic. (5) valid credentials; (6) authentication succeeded but role is missing, hence 403; (7) sufficient permissions; (8) `permitAll()`.

### 4.4. Testing with MockMvc, Avoiding Bypassing the Real Flow

Create `src/test/java/demo/userdetails/UserDetailsFlowTest.java`:

```java
package demo.userdetails;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class UserDetailsFlowTest {
    @Autowired MockMvc mvc;

    @Test
    void badPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/me").with(httpBasic("reader", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void lockedAccountIsRejected() throws Exception {
        mvc.perform(get("/api/me").with(httpBasic("locked", "locked123")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validReaderCanSeeProfile() throws Exception {
        mvc.perform(get("/api/me").with(httpBasic("reader", "reader123")))
            .andExpect(status().isOk());
    }

    @Test
    void readerCannotAccessAdmin() throws Exception {
        mvc.perform(get("/api/admin").with(httpBasic("reader", "reader123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanAccessAdmin() throws Exception {
        mvc.perform(get("/api/admin").with(httpBasic("admin", "admin123")))
            .andExpect(status().isOk());
    }
}
```

Run `./gradlew test` or `gradlew.bat test` on Windows. `httpBasic(...)` sends credentials through a real `MockMvc` request so the filter/provider invokes the custom service. Conversely, **using `@WithMockUser` alone can bypass `UserDetailsService` and password comparison**, so it is insufficient for testing this extension point.

## 5. Moving from Map to Database

In a real system, the user source may be PostgreSQL/MySQL, JDBC, JPA, or an internal service. **Keep the `AccountRepository` interface** and replace `MapAccountRepository` with a database adapter. A minimal illustrative schema:

```sql
CREATE TABLE app_users (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    enabled BOOLEAN NOT NULL,
    locked BOOLEAN NOT NULL
);

CREATE TABLE user_authorities (
    user_id BIGINT NOT NULL REFERENCES app_users(id),
    authority VARCHAR(100) NOT NULL,
    PRIMARY KEY (user_id, authority)
);
```

DDL syntax depends on the database system; you must choose a **username case-sensitivity** rule, a unique index, and consistently normalized data. With JPA, use a repository query returning `Optional<AppUser>`, load authorities, and convert the entity into `Account`. Ensure all needed data is fetched within the transaction: lazy-loaded authorities accessed after the session closes can cause `LazyInitializationException`. You can use a fetch join, entity graph, or map within the read transaction scope.

The following snippet **only illustrates the adapter** and does not run standalone because it requires `AppUserEntity`, `AuthorityEntity`, `AppUserJpaRepository`, and Spring Data JPA configuration:

```java
@Override
public Optional<Account> findByUsername(String username) {
    return jpaRepository.findWithAuthoritiesByUsername(username)
        .map(entity -> new Account(
            entity.getUsername(),
            entity.getPasswordHash(),
            entity.getAuthorities().stream()
                .map(AuthorityEntity::getName)
                .toList(),
            entity.isEnabled(),
            entity.isLocked()
        ));
}
```

**Passwords:** When creating/changing a password, call `passwordEncoder.encode(raw)` **once to store the hash**. On login, the repository returns that stored hash; `DaoAuthenticationProvider` uses `PasswordEncoder.matches(raw, storedHash)`. BCrypt generates a random salt, so encoding the same password twice usually produces two different hashes. **Never compare using `encode(raw).equals(storedHash)`**. If using `DelegatingPasswordEncoder`, store the format with a prefix such as `{bcrypt}`; the error "no PasswordEncoder mapped for id null" typically means the hash lacks a prefix or the encoder configuration mismatches.

**Authorities:** `hasRole("ADMIN")` requires `ROLE_ADMIN` by default; `hasAuthority("ADMIN")` requires the string `ADMIN`. `User.withUsername(...).roles("ADMIN")` automatically adds the `ROLE_` prefix; when stored data already contains `ROLE_ADMIN`, use `.authorities("ROLE_ADMIN")`. Never accept roles from client input to grant permissions. Changing roles in the database also does not automatically revoke permissions from previously issued sessions or tokens.

**Reliability:** Never concatenate SQL strings from usernames; use query parameters/ORM. Avoid returning JPA entities or password hashes through APIs. Never log raw passwords, hashes, or tokens. Non-existent users/accounts should receive a generic login error response to reduce information leakage. Add indexes, query timeouts, and define behavior when the database is unavailable; **never allow login merely because a lookup failed**.

## 6. Special Situations to Consider

### 6.1. Why Is `loadUserByUsername` Not Called?

There are several valid reasons:

- The request belongs to a different `SecurityFilterChain` or uses a different `AuthenticationProvider`.
- The app has a custom `AuthenticationManager`, so the new bean is not automatically used as expected.
- The endpoint is `permitAll()` and the request sent no credentials.
- The request already has an authenticated `SecurityContext`/session, so the repository does not need to be queried every time.
- The app uses OAuth2 Resource Server JWT, OAuth2/OIDC login, or another SSO mechanism.
- Multiple `UserDetailsService` beans make autowiring/provider selection ambiguous.

**How to check:** inspect the active chain and provider, test with real HTTP Basic/form login requests, trace invocations of the custom service, and inspect safe security logs. Do not conclude the service is broken merely because a breakpoint was not hit on a request that already had a session.

### 6.2. Caching, Account Locking, and Permission Lifecycle

Caching `UserDetails` can reduce load on the data source, but easily becomes stale when a user changes their password, gets locked, or loses authorities. Define clear TTL/invalidation policies. Also, `AuthenticationManager` may erase credentials from the principal after authentication; if a cache shares a `UserDetails` instance whose password was erased, subsequent authentications may fail unexpectedly. Do not enable caching without verifying how the cache interacts with `CredentialsContainer` and credential erasure.

Locking an account in the database does not by default invalidate active logged-in sessions or previously issued Bearer tokens. If business requirements demand immediate revocation, design additional mechanisms for token revocation/checking, session invalidation, and authorization synchronization.

### 6.3. When Is `UserDetailsService` Not Suitable?

| Requirement | Suitable mechanism |
| --- | --- |
| In-memory demo users | `InMemoryUserDetailsManager`. |
| Users in a compatible JDBC schema | `JdbcUserDetailsManager` or `JdbcDaoImpl`. |
| Users in a custom database schema | Custom `UserDetailsService` + repository. |
| Authentication with non-username/password credentials | Custom `AuthenticationProvider` or specialized provider. |
| Bearer JWT / opaque-token API | OAuth2 Resource Server + decoder/introspector/provider. |
| OAuth2/OIDC Login | Corresponding `OAuth2UserService` / `OidcUserService`. |
| WebFlux reactive | `ReactiveUserDetailsService`. |

`UserDetailsService` is a **user data lookup** strategy for password-based authentication. It does not decode JWTs, validate signatures, exchange OAuth2 authorization codes, or provide non-blocking reactive authentication.

## 7. Common Mistakes and How to Fix Them

**Mistake 1: returning `null` when a user is not found.** Violates the contract. Use:

```java
Account account = repository.findByUsername(username)
    .orElseThrow(() -> new UsernameNotFoundException("Invalid credentials"));
```

This line belongs to the `loadUserByUsername` method shown in section 4, not a standalone Java program.

**Mistake 2: re-hashing the password hash when reading.** If the database has a BCrypt hash, do not call `encoder.encode(account.passwordHash())`: you are hashing a hash, causing raw passwords not to match. Return `account.passwordHash()` as-is.

**Mistake 3: mapper forgets the `locked` or `enabled` flag.** An account locked in the database may be treated as valid by Spring Security if `UserDetails` is built with unlocked defaults. You must accurately reflect the account/credentials states supported by the system.

**Mistake 4: authorities have the wrong prefix.** The provider authenticates successfully, but the controller returns 403 because the database stores `ADMIN` while `hasRole("ADMIN")` requires `ROLE_ADMIN`. Fix the mapping or use the matching rule; do not blindly grant higher privileges to silence the error.

**Mistake 5: incomplete `UserDetails` data.** Returning a user with no authorities, an empty password hash, or a username inconsistent with the DB can cause authentication failure or wrong authorization. Ensure the repository loads all authorities within the transaction.

**Mistake 6: inconsistent case sensitivity.** Logging in as `Alice` vs `alice` depends on lookup behavior; if business logic requires case-insensitivity, normalize on both writes and reads as well as in the unique constraint. Avoid transforming the username in one direction and accidentally mapping to the wrong account.

**Mistake 7: using `@WithMockUser` and concluding the custom service was tested.** `@WithMockUser` creates a mock authentication, usually bypassing the provider/`UserDetailsService`. Use real Basic credentials or form login requests for integration testing.

**Mistake 8: blaming every 401/403 on the service.** A 401 can be caused by password, account flags, or provider/encoder; a 403 is missing permissions or a policy like CSRF. Inspect the chain, method, path, authorities, and response handler before modifying the source.

## 8. Implementation Checklist

- [ ] Identify a single authoritative data source and a unique username/canonicalization policy.
- [ ] `loadUserByUsername` returns a complete `UserDetails` or throws `UsernameNotFoundException`.
- [ ] `getPassword()` returns the stored hash; `PasswordEncoder` is configured consistently.
- [ ] Authorities and enabled/locked/expired flags accurately reflect server data.
- [ ] The `UserDetailsService` bean is actually used by the username-password provider/chain.
- [ ] Tests cover non-existent user, wrong password, locked account, valid login, and missing role.
- [ ] Policies are in place for security logs, HTTPS, brute-force protection, and account locking.
- [ ] When using DB/cache, manage transactions, queries/indexes, invalidation, and stale sessions/tokens.

## 9. Check Questions

**Q1.** A user has the correct password, but `locked=true` in the database, and you want to block login. What needs to be done?  
**A1.** The mapper must set `.accountLocked(true)` on `UserDetails`; the provider checks account status during authentication.

**Q2.** Why does `loadUserByUsername` not accept a password?  
**A2.** It is a user lookup API; password verification belongs to `DaoAuthenticationProvider` and `PasswordEncoder`.

**Q3.** Should `getPassword()` return plaintext or a bcrypt hash?  
**A3.** Return the stored hash. The raw password is used only during provider password verification and is neither stored nor logged.

**Q4.** A valid user has the `ROLE_USER` authority; what does an API requiring `hasRole("ADMIN")` return?  
**A4.** Normally 403 due to missing `ROLE_ADMIN`, even though the username/password were valid.

**Q5.** An app only authenticates Bearer JWTs, and `UserDetailsService` is not called. Is this a bug?  
**A5.** Not necessarily; JWT Resource Server uses its own provider/decoder. Only combine with a DB lookup if the design requires it.

## 10. Summary and Official Documentation

**`AccountRepository` defines where users are read from; a custom `UserDetailsService` shapes the user for Spring Security; `DaoAuthenticationProvider` and `PasswordEncoder` verify username/password; `UserDetails` carries server-controlled authorities and status.** A correct implementation must be verified with real authentication requests, not solely with tests mocking the principal.

References:

- [UserDetailsService in Spring Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details-service.html)
- [UserDetails and credentials](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details.html)
- [DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Username/Password Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/)
- [Password storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)

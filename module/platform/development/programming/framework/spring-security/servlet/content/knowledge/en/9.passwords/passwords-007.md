# Upgrading Password Hashes via UserDetailsPasswordService

In a **Spring Security Servlet** application, user passwords are usually stored as **salted, cost-parameterized password hashes**, not plaintext passwords. Over time, hashing policies evolve: an older algorithm is no longer preferred, the cost factor is no longer high enough, or the system adopts a new algorithm tag such as `{bcrypt}`. An application with existing users needs to upgrade old hashes **without knowing each user's original password upfront**.

Spring Security supports **opportunistic password rehashing on successful authentication** by coordinating:

- `PasswordEncoder.matches(rawPassword, storedHash)`: verifies the password the user just submitted against the stored value.
- `PasswordEncoder.upgradeEncoding(storedHash)`: indicates whether the stored hash needs an upgrade under the current encoder's policy.
- `PasswordEncoder.encode(rawPassword)`: generates a new hash from the exact password just verified.
- `UserDetailsPasswordService.updatePassword(user, newEncodedPassword)`: persists the **new hash**, not the raw password, to the account store.
- `DaoAuthenticationProvider`: the component that orchestrates these steps after password authentication succeeds if configured with a `UserDetailsPasswordService`.

This is **not** decrypting an old hash, nor is it a forgot-password reset flow. This lesson explains the processing flow, API contracts, Spring Security 6.x configuration, a JDBC example, testing, and boundaries around security, performance, and data concurrency.

## 1. Why upgrade hashes?

A password hash can embed information identifying its algorithm and cost; for example, a BCrypt string typically begins with a prefix like `$2a$10$...`, where `10` represents the log2 cost. With a delegating encoder (`DelegatingPasswordEncoder`), stored data may start with an algorithm identifier such as `{bcrypt}$2a$10$...`.

Scenarios requiring an upgrade:

| Scenario | Stored value | Current policy | Desired outcome |
| --- | --- | --- | --- |
| Raising BCrypt cost | BCrypt cost 8 | BCrypt cost 12 | Users who log in successfully get a BCrypt cost 12 hash written |
| Algorithm migration | `{pbkdf2}...` | Current encoder produces `{bcrypt}...` or another chosen algorithm | Verify with the permitted old algorithm, then write with the new algorithm |
| Retiring legacy format | Old hash without `{id}` | New strings have `{bcrypt}` | Have a **controlled** legacy verifier, then write hashes in the new format |
| Already meets policy | Hash uses current algorithm and cost | Policy unchanged | Avoid unnecessary writes |
| Wrong password | Any hash | Any | Reject authentication, **do not upgrade** |
| Non-password authentication | OAuth2 SSO/JWT or other mechanism | Internal password policy | No plaintext is available by default to rehash; needs a separate flow |

Raising cost must be based on benchmarks and real load capacity. Too low a cost increases brute-force risk if the DB is breached, while too high a cost can create CPU/latency bottlenecks when many users log in concurrently.

**Crucial requirement:** only generate a new hash from a **newly verified password**. Never generate a new hash by calling `encode(oldHash)`; doing so turns the old hash string itself into the "password" and prevents the real password from matching.

## 2. Role of each API

| Component | Contract or method | Responsibility |
| --- | --- | --- |
| `UserDetailsService` | `loadUserByUsername(username)` | Loads account, password hash, and authorities |
| `PasswordEncoder` | `matches(raw, encoded)` | Compares the presented password against the stored hash |
| `PasswordEncoder` | `upgradeEncoding(encoded)` | Decides whether the hash should be replaced under the new policy |
| `PasswordEncoder` | `encode(raw)` | Generates a new hash from the raw password available during authentication |
| `UserDetailsPasswordService` | `updatePassword(user, newPassword)` | Persists the new hash and returns a `UserDetails` reflecting the updated password |
| `DaoAuthenticationProvider` | DAO-based account authentication logic | Coordinates service, encoder, and replacing the password hash after success |
| `AuthenticationManager` | `authenticate(...)` | Coordinates the corresponding authentication providers |
| `SecurityContext` | `setAuthentication(...)` | Holds the authentication result for the processing scope, **not** where hashes are stored |

Core method of the `UserDetailsPasswordService` interface:

~~~java
// Spring Security API contract shape:
public interface UserDetailsPasswordService {
    UserDetails updatePassword(UserDetails user, String newPassword);
}
~~~

This is **interface signature illustration code**, requiring the corresponding `UserDetails` import if added to a project; it is not a runnable class. The parameter name `newPassword` can be misleading: in `DaoAuthenticationProvider`'s upgrade flow, it is the **encoded/hashed password produced by the encoder**, not a raw password.

The service implementation must ensure:

1. The hash value is written to the exact right account, matching the username/ID in the store.
2. Authorities, enabled status, tenant, or account metadata are not altered unintentionally.
3. An appropriate `UserDetails` is returned after the update so the provider has a consistent authentication result.
4. Transactions, concurrency, database errors, and change auditing are handled as required by the environment.
5. Raw passwords/hashes are never placed in logs or responses.

## 3. Automatic upgrade flow at login

In a Servlet application using username/password via HTTP Basic or form login with `DaoAuthenticationProvider`, the typical flow is:

~~~text
HTTP request carrying username + raw password
               |
               v
Authentication filter
               |
               v
AuthenticationManager -> DaoAuthenticationProvider
               |
               +--> UserDetailsService.loadUserByUsername(username)
               |       |
               |       +--> UserDetails.password = storedEncoded
               |
               +--> check account status
               +--> PasswordEncoder.matches(rawPassword, storedEncoded)
                       |
              +--------+--------+
              |                 |
           false               true
              |                 |
              v                 v
       Auth failed          Auth succeeded
       DO NOT update hash       |
                                v
                     PasswordEncoder.upgradeEncoding(storedEncoded)
                          |                    |
                        false                 true
                          |                    |
                          v                    v
                     Keep old hash    encode(rawPassword)
                                               |
                                               v
                           UserDetailsPasswordService.updatePassword(
                               user, newEncodedPassword)
                                               |
                                               v
                           Authentication succeeds, using the
                           properly updated UserDetails
~~~

This model applies when the provider **is configured** with `UserDetailsPasswordService`. Simply declaring an encoder bean without wiring the password service into the provider will not automatically cause logins to call `updatePassword(...)`.

Points to note:

- `matches(...)` runs **before** `upgradeEncoding(...)` in the upgrade decision; new hashes are never created for wrong passwords.
- `updatePassword(...)` is only called when the encoder indicates an upgrade is needed (per provider behavior in the active version) and the password update service is configured.
- The service updates the **hash**; it must never receive a raw password to store in the DB.
- If the user's hash already satisfies the policy, login does not need to write to the DB merely to rotate the salt.
- The upgrade is a **side effect of a successful password authentication**; it is not a background job upgrading all non-logging-in users.

**Do not confuse hash upgrades with password changes:** the password the user enters remains the same; only the stored hash's algorithm/parameters/format changes. For user-initiated password changes, a separate password-change API with its own authorization/credential checks is needed.

## 4. How does PasswordEncoder.upgradeEncoding work?

The `PasswordEncoder` interface defines `encode(...)`, `matches(...)`, and the default method `upgradeEncoding(...)`. An implementation can inspect info inside the stored string to determine whether the hash is sufficiently up to date.

### 4.1. BCryptPasswordEncoder and strength

Example current policy:

~~~java
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

PasswordEncoder encoder = new BCryptPasswordEncoder(12);
~~~

Suppose the DB holds BCrypt created with cost 8 (e.g., starting with `$2a$08$...`). `BCryptPasswordEncoder(12)` can **verify** the old hash because the hash embeds its own cost, and `upgradeEncoding(oldHash)` can return `true` because the old cost is lower than the configured cost.

After a valid login, the provider can write a new hash with cost 12. If the hash is already at cost 12 or higher, upgrading solely due to lower cost is unnecessary; nor should you downgrade cost just because configuration changed from 12 to 10.

Semantic examples:

~~~text
Stored: bcrypt(cost=8)     -> policy bcrypt(cost=12) -> upgrade=true
Stored: bcrypt(cost=12)    -> policy bcrypt(cost=12) -> upgrade=false
Stored: bcrypt(cost=14)    -> policy bcrypt(cost=12) -> do not downgrade cost
Wrong password entered     -> never reaches upgrade step
~~~

These lines are **semantic descriptions**, not output from a specific command. Cost 8 in this lesson only illustrates legacy data; low costs are not recommended for real systems. Choose work factors based on load, latency budgets, and current security guidance.

### 4.2. DelegatingPasswordEncoder and the {id} prefix

`DelegatingPasswordEncoder` stores the algorithm via a prefix:

~~~text
{bcrypt}$2a$12$...
{pbkdf2}...
{argon2}...
~~~

This model lets the authentication mechanism identify which encoder to use for **legacy values**, while `encode(...)` uses the **current `idForEncode`**. When the stored hash's id is no longer the new id, `upgradeEncoding(...)` can report that an upgrade is needed. When the id matches, the delegate encoder can further inspect parameters such as BCrypt cost.

Example bean using Spring Security's factory:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
}
~~~

This factory chooses the algorithm configuration and prefixed storage format per the Spring Security version in use; do not assume a specific cost without checking the actual version and bean.

**Formats must be consistent:**

- Direct `BCryptPasswordEncoder` normally works with BCrypt hashes like `$2a$...` (without a `{bcrypt}` prefix).
- `DelegatingPasswordEncoder` uses the `{id}` prefix for routing; for data without an id, default behavior may reject it because the encoder is unknown.
- When migrating old prefix-less data, you can configure a fallback decoder **only during the migration window and strictly for trusted formats**, or force a password reset. Never arbitrarily accept `{noop}` or plaintext as a production "fix".
- Never edit a hash's prefix directly without verifying its body matches the declared algorithm's format. Changing `{sha256}` to `{bcrypt}` does not convert SHA-256 data into BCrypt.

### 4.3. Without enough information, rehashing is impossible

Hashing is a one-way transformation; you cannot recover the raw password from a stored hash to compute a new hash. Thus, lazy rehash-on-login happens **only when the user submits the right password again**. For accounts that rarely log in, define a policy: wait for the next login, require a password change/reset, or retire legacy hash support after an announced deadline.

If you disable the old algorithm's verifier completely, users still on old hashes cannot log in to self-upgrade. Migration plans must account for a **bounded compatibility window**, metrics on un-upgraded users, and a secure reset flow.

## 5. How does UserDetailsPasswordService relate to UserDetailsService?

The two interfaces have similar names but distinct responsibilities:

~~~text
UserDetailsService
    loadUserByUsername(username)
            -> UserDetails containing encoded password

UserDetailsPasswordService
    updatePassword(user, newEncodedPassword)
            -> persist new hash, return updated UserDetails
~~~

A single class can implement both; for example, Spring Security's `JdbcUserDetailsManager` can act as the account lookup source and provide password update behavior when configured compatibly with the schema/queries.

If an application uses a `JpaRepository` or custom domain service, you can create an adapter implementing `UserDetailsPasswordService`. **Conceptual fragment** example without concrete JPA repository code:

~~~java
@Override
@Transactional
public UserDetails updatePassword(UserDetails user, String newEncodedPassword) {
    Account account = repository.findByUsername(user.getUsername())
            .orElseThrow(() -> new UsernameNotFoundException(
                    "Account no longer exists"));

    account.setPasswordHash(newEncodedPassword);
    repository.save(account);

    return User.withUserDetails(user)
            .password(newEncodedPassword)
            .build();
}
~~~

Here `Account`, `repository`, `@Transactional`, and imports belong to **the project**, not a standalone class. Using `User.withUserDetails(...)` is appropriate when the `UserDetails` data and authorities can be represented fully by this builder; if the application has a custom principal carrying specialized attributes, return a `UserDetails` type preserving all required fields.

Ensure the service never bypasses tenant boundaries. When usernames can collide across tenants, key by an immutable identifier or a verified tenant predicate; `WHERE username=?` alone could update the wrong user.

### Why must it return UserDetails?

`UserDetailsPasswordService.updatePassword(...)` returns `UserDetails` so the provider can proceed with a user reflecting the new password and consistent account data. Returning an object still holding the old hash after updating the DB can cause inconsistent processing/caching results. Returning `null` violates operational expectations and can cause errors during authentication.

Never alter username, authorities, enabled status, or account flags merely to update a hash. If other policy/state updates are needed simultaneously, treat that as a separate business decision with explicit transactions and tests.

## 6. Practical example: Spring Boot + H2 + JdbcUserDetailsManager

Goal of the example: create a demo account with **BCrypt cost 8 (legacy)**, configure the current policy as **BCrypt cost 12**, log in via HTTP Basic, and observe the `password` column in the `users` table upgraded to a cost 12 hash.

This is code for **Spring Boot 3.x / Spring Security 6.x / Java 17+**; it requires Spring, H2, and Maven on the classpath. The Spring code **will not compile with bare JDK `javac` alone**. `DaoAuthenticationProvider` constructors and APIs have changes/deprecations across 6.x releases; the example uses the common traditional configuration for Spring Security 6.x and should be adjusted if your project pins a different version.

### 6.1. Maven dependencies

In `pom.xml` of a Spring Boot project with an appropriate parent/BOM, include these dependencies:

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
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
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

Do not mix Spring Security versions that conflict with the Spring Boot BOM. In newer Spring Boot versions, test/autoconfiguration packages may vary; adjust imports to match your version.

### 6.2. Default JDBC schema

Create `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE users (
    username VARCHAR(50) PRIMARY KEY,
    password VARCHAR(500) NOT NULL,
    enabled BOOLEAN NOT NULL
);

CREATE TABLE authorities (
    username VARCHAR(50) NOT NULL,
    authority VARCHAR(100) NOT NULL,
    CONSTRAINT fk_auth_user FOREIGN KEY (username) REFERENCES users(username),
    CONSTRAINT uq_auth UNIQUE (username, authority)
);
~~~

These two tables match the standard user and authority lookups of `JdbcUserDetailsManager`. Password hashes need a column long enough for prefixed formats, BCrypt, Argon2, or the chosen algorithm. If the production schema differs (e.g., a `password_hash` column), configure **both the read and update password queries** to match the schema—not just the SELECT query.

Create `src/main/resources/application.properties`:

~~~properties
spring.datasource.url=jdbc:h2:mem:password_upgrade_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

In-memory H2 is for learning only; never use it as a production account database. Real environments must use versioned migrations, DB access controls, TLS where appropriate, and backup plans.

### 6.3. Spring Boot class

Create `src/main/java/com/example/demo/PasswordUpgradeApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PasswordUpgradeApplication {
    public static void main(String[] args) {
        SpringApplication.run(PasswordUpgradeApplication.class, args);
    }
}
~~~

### 6.4. Encoder bean, JDBC manager, and DaoAuthenticationProvider

Create `src/main/java/com/example/demo/PasswordUpgradeConfig.java`:

~~~java
package com.example.demo;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.JdbcUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class PasswordUpgradeConfig {

    @Bean
    JdbcUserDetailsManager users(DataSource dataSource) {
        return new JdbcUserDetailsManager(dataSource);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(12); // NEW policy.
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            JdbcUserDetailsManager users,
            PasswordEncoder encoder) throws Exception {

        DaoAuthenticationProvider provider = new DaoAuthenticationProvider();
        provider.setUserDetailsService(users);
        provider.setPasswordEncoder(encoder);

        // This is the crucial wiring for the post-authentication upgrade step:
        provider.setUserDetailsPasswordService(users);

        http.authenticationProvider(provider)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/me").authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    CommandLineRunner seedLegacyAccount(JdbcUserDetailsManager users) {
        return args -> {
            String password = System.getenv("DEMO_PASSWORD");
            if (password == null || password.isBlank()) {
                return; // Do not create an account with a default password.
            }

            // INTENTIONALLY create a low-cost hash only to observe the upgrade.
            PasswordEncoder oldEncoder = new BCryptPasswordEncoder(8);
            if (!users.userExists("alice")) {
                users.createUser(User.withUsername("alice")
                    .password(oldEncoder.encode(password))
                    .roles("USER")
                    .build());
            }
        };
    }
}
~~~

**Core configuration points:**

1. `JdbcUserDetailsManager` provides `UserDetailsService` and the ability to persist updated passwords via the `UserDetailsPasswordService` interface.
2. `DaoAuthenticationProvider` verifies passwords using the `BCryptPasswordEncoder(12)` bean.
3. `provider.setUserDetailsPasswordService(users)` tells the provider how to **write the new hash**.
4. Demo account `alice` initially has a BCrypt cost 8 hash yet still verifies against the cost 12 encoder.
5. When `alice` logs in **successfully**, the provider can rehash at cost 12, call `users.updatePassword(...)`, and proceed to build the authentication result.
6. When the password is wrong, the hash is not upgraded. Once cost 12 is reached, subsequent logins normally do not trigger updates.

Declaring `JdbcUserDetailsManager` and `PasswordEncoder` beans is insufficient if the provider actually handling authentication is a different one or lacks the password service wiring. In an application with multiple providers, chains, filters, SSO, or JWT, identify **which provider actually processes credentials**.

**Version note:** `DaoAuthenticationProvider()` and `setUserDetailsService(...)` may be marked deprecated in newer Spring Security 6.x releases. If your library supports a constructor taking `UserDetailsService`, use that constructor and remove the setter. Only change provider instantiation syntax; do not alter the semantics of `setPasswordEncoder(...)` or `setUserDetailsPasswordService(...)`.

### 6.5. Endpoint to observe login

Create `src/main/java/com/example/demo/WhoAmIController.java`:

~~~java
package com.example.demo;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/me")
    public String me(Principal principal) {
        return "Hello, " + principal.getName();
    }
}
~~~

`/me` is protected with `authenticated()`, so when a request reaches the controller under the sample config, a valid principal is already authenticated. The public endpoint does not touch `principal`.

### 6.6. Running the demo and checking the database

After setting up the project/Maven wrapper and a suitable JDK, on a Unix-like test machine:

~~~bash
export DEMO_PASSWORD='only-local-demo-password'
./mvnw spring-boot:run
~~~

This is a **dummy password for development only**. In real environments, never pass passwords via command lines/histories as shown, never provision fixed demo accounts, and never copy production passwords into lesson files.

Send requests before logging in:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
~~~

Expected behavior: `/public` normally returns `200`, and `/me` without credentials normally returns `401` with an HTTP Basic challenge. Next:

~~~bash
curl -i -u alice http://localhost:8080/me
~~~

`curl` will prompt for the password; enter the exact password you set when seeding. With a successful setup, the response is typically HTTP 200 with body `Hello, alice`.

Inspect the password column in H2 using an authorized SQL tool:

~~~sql
SELECT username, password, enabled
FROM users
WHERE username = 'alice';
~~~

Before the first valid login, Alice's hash has BCrypt cost 8, typically showing `$08$` in the BCrypt prefix; after the valid login, the new hash typically has cost 12 (`$12$`). Actual hash strings differ on every run due to random salts; **there is no fixed output string to copy**.

In production, never expose hashes on public dashboards/logs. During testing, prefer asserting state/format via integration tests in isolated environments; if reading actual hashes is necessary, restrict permissions and data retention.

## 7. Automated testing of hash values before and after login

Within the same project containing `spring-boot-starter-test`, `spring-security-test`, `JdbcUserDetailsManager`, and `JdbcTemplate`, an integration test can seed a user with a low-cost hash and perform real HTTP Basic requests via `MockMvc`.

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.JdbcUserDetailsManager;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PasswordUpgradeIntegrationTest {

    @Autowired MockMvc mvc;
    @Autowired JdbcUserDetailsManager users;
    @Autowired JdbcTemplate jdbc;
    @Autowired PasswordEncoder encoder;

    private String stored(String name) {
        return jdbc.queryForObject(
            "SELECT password FROM users WHERE username = ?",
            String.class,
            name
        );
    }

    @Test
    void successfulLoginUpgradesHashButWrongPasswordDoesNot()
            throws Exception {

        String username = "upgrade-test-user";
        String raw = "test-only-password";
        String legacyHash = new BCryptPasswordEncoder(8).encode(raw);

        if (users.userExists(username)) {
            users.deleteUser(username);
        }
        users.createUser(User.withUsername(username)
            .password(legacyHash)
            .roles("USER")
            .build());

        String before = stored(username);
        assertEquals(legacyHash, before);
        assertTrue(encoder.matches(raw, before));
        assertTrue(encoder.upgradeEncoding(before));

        // WRONG password must not write a new hash.
        mvc.perform(get("/me").with(httpBasic(username, "incorrect")))
            .andExpect(status().isUnauthorized());
        assertEquals(before, stored(username));

        // CORRECT password: provider verifies then saves the new hash.
        mvc.perform(get("/me").with(httpBasic(username, raw)))
            .andExpect(status().isOk());

        String after = stored(username);
        assertNotEquals(before, after);
        assertTrue(encoder.matches(raw, after));
        assertFalse(encoder.upgradeEncoding(after));

        // Subsequent login with a hash that already meets policy.
        mvc.perform(get("/me").with(httpBasic(username, raw)))
            .andExpect(status().isOk());
        assertEquals(after, stored(username));
    }
}
~~~

The test uses dummy passwords, in-memory H2, and an isolated account. It verifies **the database actually changed** after login through the provider, rather than merely proving a call to `PasswordEncoder.encode(...)` can generate a new hash. Assertions rely on the demo setup: an active provider, `BCryptPasswordEncoder(12)`, wired password service, and HTTP Basic requests routed through the Spring Security filter chain.

If another environment uses a custom provider or modified login handling events, adapt the test accordingly. If Spring Security caches user details, verify the update path/cache invalidation and confirm authentication results remain consistent after the hash changes.

### Testing additional scenarios

| Case | Input | Expected behavior |
| --- | --- | --- |
| Wrong password | Raw credential mismatches | No hash written; authentication error |
| Disabled/locked user | Account invalid per policy | Never upgraded as a successful login |
| Low-cost hash | Valid credential, active service | New policy-compliant hash written |
| Already policy-compliant hash | Valid credential | No unnecessary update |
| Read-only store | Valid credential but update fails | Handle error deliberately, do not claim upgrade succeeded |
| Algorithm switch | Old encoder still verifies, new policy differs | Format converted after login; test compatibility |
| Concurrent logins | Two requests both using old password | Do not overwrite concurrent password/permission changes |
| Password reset | User cannot supply valid old password | Use reset workflow, do not fake automatic upgrade |

A unit test mocking `@WithMockUser` **does not trigger `DaoAuthenticationProvider` real password verification**, so it cannot test the hash upgrade path. You need integration tests with real credentials or dedicated provider tests with a mock `UserDetailsPasswordService` verifying invocation counts.

## 8. Standalone Java 17: simulating the upgrade decision

To understand the sequence **verify → check upgrade need → persist new hash**, you can use the following plain Java 17 program. It **does not hash real passwords and does not authenticate users**: the `passwordVerified` flags assume a result already returned by a trusted password verifier. This deliberately keeps the example from being mistaken for a production password hashing algorithm.

Save file `PasswordUpgradeDecisionDemo.java`:

~~~java
public class PasswordUpgradeDecisionDemo {
    record Account(String username, int storedCost) {}

    static String login(Account user, boolean passwordVerified, int policyCost) {
        if (!passwordVerified) {
            return user.username() + " -> rejected; hash unchanged";
        }
        if (user.storedCost() < policyCost) {
            return user.username() + " -> upgrade "
                    + user.storedCost() + " to " + policyCost;
        }
        return user.username() + " -> accepted; hash unchanged";
    }

    public static void main(String[] args) {
        System.out.println(login(new Account("alice", 8), true, 12));
        System.out.println(login(new Account("bob", 8), false, 12));
        System.out.println(login(new Account("carol", 12), true, 12));
        System.out.println(login(new Account("dave", 14), true, 12));
    }
}
~~~

Compile/run commands:

~~~bash
javac PasswordUpgradeDecisionDemo.java
java PasswordUpgradeDecisionDemo
~~~

Exact stdout:

~~~text
alice -> upgrade 8 to 12
bob -> rejected; hash unchanged
carol -> accepted; hash unchanged
dave -> accepted; hash unchanged
~~~

In a Spring Security system, `PasswordEncoder.matches(...)` produces the real verification result; `upgradeEncoding(...)` evaluates actual algorithms/costs instead of comparing integers; `UserDetailsPasswordService.updatePassword(...)` persists the encoded password after successful authentication. The plain Java model above helps visualize the decision branches and **does not replace BCrypt/Argon2/PBKDF2**.

## 9. When not using JDBC: implementing a responsible hash persistence service

An application may hold accounts in JPA, MongoDB, an internal service, or another store. Build an adapter implementing `UserDetailsPasswordService` with a **trusted identifier** and appropriate write privileges. Application service pattern:

~~~java
// Illustrative fragment inside a fully designed @Service bean.
@Override
@Transactional
public UserDetails updatePassword(UserDetails user, String encodedPassword) {
    Account account = accountRepository.findByLogin(user.getUsername())
        .orElseThrow(() -> new UsernameNotFoundException(
            "Account unavailable"));

    account.setPasswordHash(encodedPassword);
    accountRepository.save(account);

    return User.withUserDetails(user)
        .password(encodedPassword)
        .build();
}
~~~

This is a **pseudo-real fragment**: `Account`/repository are custom domain types; imports and transaction configuration must be added. In multi-tenant systems or systems allowing shared usernames, looking up by `user.getUsername()` alone may be unsafe. Require a verified identifier, tenant boundaries, and proper concurrency controls.

### Concurrency and competing password updates

Two logins for the same user might both observe the old hash and produce two different new hashes due to salt. If both used the same valid password, overwriting one new hash with the other usually does not break the password, though it causes extra DB writes. More dangerously:

1. Request A verifies the old password.
2. Request B actively **changes/resets the password** to a different value.
3. Request A uses stale user data and writes the "upgraded hash" of the old password over the new hash.

This can resurrect the old password. Design updates with **optimistic concurrency**:

~~~sql
UPDATE users
SET password = ?
WHERE username = ?
  AND password = ?;
~~~

Here the parameters are `newEncodedPassword`, `username`, and the previously read **oldEncodedPassword**. If affected rows equal 0, the data changed; **do not overwrite unconditionally**. This is a reference SQL strategy, not the guaranteed default query of `JdbcUserDetailsManager`. With a version column, you can use `WHERE id=? AND version=?`. If using `JdbcUserDetailsManager` with simple update SQL, evaluate concurrency requirements and add a custom update layer if business rules require stale-write protection.

Do not emit a "login succeeded, hash upgraded" response if the DB update failed; authentication status and retry handling should follow application policy with safe logging/auditing and thorough tests.

### Mind the UserDetailsService cache

A provider or application may cache `UserDetails`. After the hash changes in the DB, the cache must be updated or invalidated accordingly. If the cache still holds the old hash, subsequent authentications may behave confusingly or rehash repeatedly. Never assume every login queries the database anew; inspect your actual `UserCache` and custom cache layers.

## 10. Upgrading hashes as a migration strategy

A successful migration is more than swapping the `PasswordEncoder` bean:

### Step 1: Inventory data

Identify algorithms, costs, `{id}` prefixes, and account percentages per format; avoid writing full hashes/secrets to logs. If the old DB contains plaintext or weak hashes, treat it as a security issue requiring a strict transition plan and potentially mandatory resets.

### Step 2: Choose the new policy and compatibility rules

Benchmark password hashing (CPU, memory, concurrent logins) on real infrastructure. Pick a secure new encoder with suitable parameters. Retain legacy verifiers **strictly for specific formats** during the migration window. Never create an "any hash matches" config or a fallback that skips password checks.

### Step 3: Connect provider and password service

Identify which provider receives username/password. Wire the new encoder and `UserDetailsPasswordService` to the right `DaoAuthenticationProvider`; verify the successful auth path calls the service and persists the new hash. With multiple login methods, do not confuse OIDC/JWT/SSO with DB password authentication.

### Step 4: Test before rollout

Test wrong password, right password, disabled accounts, old hash, new hash, concurrency, DB failure, cache, and app permissions. In test environments, verify post-login hash format via restricted queries; never print raw passwords.

### Step 5: Observe and finish

Track **counts of accounts still on old formats** and upgrade success/failure rates without collecting credentials. After a period, users who have not logged in need a password reset or another operational strategy. Remove legacy verifiers only once a plan covers remaining users.

### Step 6: Prepare rollback

If issues arise after issuing new hashes, code rollback cannot simply revert to an encoder **that only understands old hashes**. When planning deployment, ensure the rollback application version can verify both old and new formats, or have a controlled recovery path. **Never downgrade hashes** just to enable rollback.

## 11. Common misconceptions

| Misconception | Why it is wrong | How to handle |
| --- | --- | --- |
| "Just change the BCrypt bean from 8 to 12 and DB auto-updates" | Provider may lack `UserDetailsPasswordService` | Wire the service, test hashes before/after login |
| "Old hashes can be decoded and re-encoded without login" | Password hashes are one-way | Wait for valid login or mandate reset |
| "`PasswordEncoder.encode(oldHash)` is an upgrade" | The old hash is not the raw password | Only encode the newly verified password |
| "New hashes must match if passwords match" | BCrypt uses random salts | Use `matches(...)`, never compare hash strings |
| "Wrong passwords should also trigger upgrades" | No proof of valid password | Never alter hashes when authentication fails |
| "`UserDetailsPasswordService` expects raw password" | Interface receives encoded password to save | Never pass raw passwords into repositories/logs |
| "Upgrading hash changes the user's password" | Password stays the same | Distinguish hash update from reset/change |
| "`DelegatingPasswordEncoder` always understands prefix-less hashes" | May not know which encoder applies | Design safe legacy fallback or reset |
| "If lowering cost, data should be downgraded" | Lowering cost weakens brute-force resistance | Do not downgrade; review policy |
| "`DaoAuthenticationProvider` always runs on every SSO/JWT request" | Each mechanism uses different providers/filters | Inspect the real authentication path |
| "A successful login proves DB updated" | Service may be missing or update failed | Assert hashes before/after in integration tests |
| "Hash upgrades are always race-safe" | Concurrent password changes can suffer stale writes | Optimistic locking/conditional updates |
| "Strong hashes eliminate login rate limits" | Online brute force differs from offline | Rate limiting, MFA, monitoring, anti-enumeration |
| "Dropping old hash support right at deploy is safe" | Dormant users may lose login access | Phased transition and controlled resets |

## 12. Self-check exercises

**Exercise 1.** User Alice has BCrypt cost 8 stored, and the app uses `BCryptPasswordEncoder(12)`. Alice logs in with the right password through a provider wired with `UserDetailsPasswordService`. What happens?

**Answer:** The provider verifies the raw password against the cost 8 hash; the encoder signals an upgrade is needed; the provider creates a cost 12 hash from the raw password, calls the service to update the hash, and finishes authentication. Alice's entered password does not change.

**Exercise 2.** Alice enters the wrong password for the same account. Should `updatePassword(...)` be called?

**Answer:** No. The password was not verified; neither the wrong input nor the old hash may be used to write a new stored hash.

**Exercise 3.** Stored data is `{pbkdf2}...` and the new encoder produces `{bcrypt}...`. When can data migrate?

**Answer:** While configuration still validly verifies legacy PBKDF2 hashes; a login with the right password can generate a new BCrypt hash and persist it via the password service. If the old algorithm has already been disabled, users must go through a reset/other migration flow.

**Exercise 4.** `JdbcUserDetailsManager` is configured for login, yet after every valid login the hash does not change. What are the first two possibilities to check?

**Answer:** Either `upgradeEncoding(storedHash)` returned false because the hash already meets policy, or the active provider is not wired with `UserDetailsPasswordService` / another provider is handling auth. Check beans, auth path, encoder state, and integration tests.

**Exercise 5.** Why can `UPDATE users SET password=? WHERE username=?` be insufficient during a concurrent password reset?

**Answer:** A login that verified the old password can write its upgraded old hash **after** the reset changed the password. Use conditional updates/optimistic locking or equivalent concurrency control to avoid overwriting newer changes.

**Exercise 6.** A BCrypt hash is re-encoded after login and the string is completely different, yet the user still logs in with the old password. Is this a bug?

**Answer:** No. Different salts produce different hashes; the verifier must still return `matches(raw, newHash) = true`. This is the exact expected result of rehashing.

**Exercise 7.** All active users' hashes have been upgraded, yet accounts dormant for years still hold old hashes. Can you call `UserDetailsPasswordService.updatePassword(...)` with the old hash value to finish them automatically?

**Answer:** No. You must have the valid raw password or run a secure password reset workflow. Never encode an old hash in place of a password.

## 13. Application checklist

- [ ] Identify **stored** hash formats/costs and the **new** encoder policy.
- [ ] Ensure `PasswordEncoder.matches(...)` still understands legacy formats supported during migration.
- [ ] Test `upgradeEncoding(...)` on old hashes, new hashes, and invalid inputs.
- [ ] Identify the exact `DaoAuthenticationProvider` handling login; wire `UserDetailsPasswordService` to it.
- [ ] Service writes only the **encoded password**, returns a consistent `UserDetails`, and preserves all other attributes.
- [ ] Design transactions, optimistic updates, cache invalidation, and DB failure handling per domain rules.
- [ ] Test wrong password **no write**, right password **upgrades**, subsequent login **no rewrite**.
- [ ] Never store/log raw passwords, hashes, tokens, or credentials; control DB read privileges.
- [ ] Evaluate work factor and rate limiting to avoid auth bottlenecks when raising cost.
- [ ] Plan for dormant accounts, compatible rollbacks, and timely retirement of old algorithms.
- [ ] Distinguish hash migration from password reset/change and from OAuth2/SSO/JWT mechanisms.

**Conclusion:** `UserDetailsPasswordService` is **the persistence step for upgraded password hashes**, while verification, upgrade decision, and new hash generation happen through the collaboration of `DaoAuthenticationProvider` and `PasswordEncoder`. The mechanism only makes sense when a user **has just authenticated successfully with a password** and the provider is wired to the update service; the application must still enforce schema sizing, format compatibility, concurrency, and a migration plan.
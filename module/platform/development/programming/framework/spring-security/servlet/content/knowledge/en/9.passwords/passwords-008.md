# Migrating Legacy Password Data While Controlling Accepted Algorithms

> **Scope:** Spring Security on the **Servlet stack**, Java 17+, with integration examples using Spring Boot 3 / Spring Security 6.x. The goal is to read legacy password hash data **during a controlled transition window**, verify using only explicitly approved algorithms, upgrade to a new hash **after the user enters the correct password**, and retire legacy algorithms on schedule. Do not follow a "try every encoder until one matches" mindset or accept unidentified hashes by default.

## 1. The real-world problem

A long-lived system can hold multiple generations of passwords:

| Storage form | Structural example | Issue |
| --- | --- | --- |
| Legacy BCrypt without prefix | `$2a$08$...` | No application-level algorithm metadata; legacy work factor may be low. |
| Legacy BCrypt tagged with custom ID | `{bcrypt-v1}$2a$08$...` | Exact algorithm family is known; needs transition and higher work factor. |
| Current BCrypt with ID | `{bcrypt}$2a$12$...` | Can be accepted under the new policy. |
| Legacy PBKDF2 | `{pbkdf2-legacy}...` | Must know the **exact** historical PRF, salt, iterations, format, and output length. |
| Unknown algorithm, MD5/SHA-1/plaintext-like string | Data of unverified provenance | **Do not guess**, do not add `noop`, and do not try weak algorithms by default. |

Strings with `...` in the table only show **shape**; they are not usable production hashes. Actual formats must be cross-checked against stored data, legacy code, old migrations, and reliable test vectors.

Four mandatory questions to answer before writing a migration:

1. **Which hashes are stored?** Verify algorithm, version, parameters, format, prefix, pepper if any, and where salts reside. Without sufficient evidence, route the record into a recovery/reset flow.
2. **Which versions are still allowed for verification?** Define an allowlist with an owner, risk level, sunset deadline, and account scope.
3. **What is the new hash?** Pick a dedicated password hashing algorithm and a work factor measured on target hardware. Lesson examples use BCrypt cost 12 for illustration, without claiming 12 is optimal for every environment.
4. **When to upgrade?** When a raw password is available from a **verified successful login**, or when the user performs a password change/reset flow. You cannot meaningfully upgrade merely by changing an old hash string's prefix.

## 2. Distinguishing three commonly confused operations

**Algorithm tagging:** changing `$2a$08$...` to `{bcrypt-v1}$2a$08$...` once proven from metadata or old source code that the record is definitely legacy BCrypt. This **does not change password protection strength**; it only helps the system select the right verifier.

**Password verification:** the user enters a raw password; `PasswordEncoder.matches(raw, stored)` uses the right encoder from the allowlist to verify. Never decrypt hashes because password hashing is not reversible encryption.

**Rehashing/upgrading:** after verification succeeds, use the **newly entered raw password** to create a new hash with the current algorithm/work factor, then safely update the DB. This is the step that gradually converges data toward the new policy.

~~~text
Stored hash             Entered password
    |                          |
    +------ algorithm ID ------+
               |
               v
       policy allows ID?
          /           \
        no            yes
         |             |
         v             v
   reject safely   PasswordEncoder.matches(...)
                       /             \
                  wrong               right
                    |                   |
                    v                   v
               auth failed       upgradeEncoding(...)?
                                    /        \
                                  yes         no
                                   |           |
                                   v           v
                            encode password    login succeeded
                            with new policy
                                   |
                                   v
                            write DB safely
                                   |
                                   v
                            login succeeded
~~~

**Important:** start only from a system-managed **stored hash**. Never accept a client-supplied `{id}hash` string and trust its ID to select policy or grant access. The algorithm list resides in **server configuration**, not in requests.

## 3. `DelegatingPasswordEncoder` and an explicit algorithm list

Spring Security provides `DelegatingPasswordEncoder`: a password hash has the form `{id}encodedPassword`. `id` picks the matching `PasswordEncoder` from a server-configured map; `idForEncode` specifies the algorithm used to **create new hashes**.

With an example configuration:

~~~text
{bcrypt}    $2a$12$...     -> encoder for BCrypt cost 12
{bcrypt-v1} $2a$08$...     -> verifier for legacy BCrypt cost 8
{noop}      secret          -> NOT in allowlist
{md5}       ...             -> NOT in allowlist
<no-id>     $2a$08$...      -> unclassified, not accepted by default
~~~

The table only illustrates **ID-based routing**. BCrypt hashes embed cost inside the string, so one `BCryptPasswordEncoder` can verify BCrypt hashes with historical costs; two IDs are used here to express **lifecycle policy**, not two different cryptographic algorithms.

### Password policy bean: `PasswordPolicyConfig.java`

~~~java
package com.example.passwordmigration;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.crypto.password.DelegatingPasswordEncoder;

@Configuration
public class PasswordPolicyConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        Map<String, PasswordEncoder> allowed = Map.of(
                "bcrypt", new BCryptPasswordEncoder(12),
                "bcrypt-v1", new BCryptPasswordEncoder(8)
        );

        // Only the bcrypt ID is used when creating new hashes.
        // The bcrypt-v1 ID is temporarily retained to verify legacy records.
        return new DelegatingPasswordEncoder("bcrypt", allowed);
    }
}
~~~

**Why is this a genuine allowlist?**

- Only two IDs, `bcrypt` and `bcrypt-v1`, are declared. Any hash with `{noop}`, `{md5}`, or another ID is absent from the map.
- `idForEncode="bcrypt"` means `encode(raw)` creates a **new** hash of the form `{bcrypt}$2...`.
- `bcrypt-v1` is allowed to **verify**, and is never chosen as the algorithm for creating new hashes in this configurer.
- Do not call `setDefaultPasswordEncoderForMatches(...)` to guess prefix-less hashes, and never supply `NoOpPasswordEncoder` as a fallback. Missing/unsupported IDs must fail closed. By default `DelegatingPasswordEncoder` may throw `IllegalArgumentException` for unmapped IDs; the application should control error observation and responses rather than turning that error into a bypass path.
- Do not call `PasswordEncoderFactories.createDelegatingPasswordEncoder()` if your security requirement is **narrowing the set of permitted algorithms**: the default factory may register more compatibility encoders than your strict policy allows.

Do not confuse an **ID-level allowlist** with a guarantee that all internal parameters match. If one ID represents multiple PBKDF2 generations with different salts/iterations/PRFs, decide **how to distinguish parameter versions** or bind separate verifiers. Never use a "current default" encoder to verify PBKDF2 data generated with older parameters.

## 4. Authentication lifecycle and automatic upgrade on successful login

For username/password on the Servlet stack:

~~~text
UsernamePasswordAuthenticationFilter
    -> AuthenticationManager
        -> DaoAuthenticationProvider
            -> UserDetailsService.loadUserByUsername(username)
               -> UserDetails.getPassword() returns "{bcrypt-v1}..."
            -> PasswordEncoder.matches(rawPassword, storedHash)
               -> accepts only IDs in allowlist
            -> check account status
            -> if valid and upgradeEncoding(storedHash)==true:
                   newHash = PasswordEncoder.encode(rawPassword)
                   UserDetailsPasswordService.updatePassword(user, newHash)
            -> return authenticated Authentication
    -> SecurityContext / success handler / session per config
~~~

`UserDetailsService` only **reads** the user and stored hash. `PasswordEncoder` verifies the hash. `UserDetailsPasswordService` provides a **new-hash write** hook used by Spring Security when the provider has authenticated successfully and determined an upgrade is needed.

A failed login **must never** write a new hash, call `encode` and save an attacker's password, or "mark as migrated". Remember: password hashes have no reverse operation; rehashing requires the valid raw password just provided by the user.

### Where does `upgradeEncoding(...)` operate?

`PasswordEncoder.upgradeEncoding(encodedPassword)` indicates whether the current hash needs an upgrade under the encoder's policy. `DelegatingPasswordEncoder` can request an upgrade when the hash's ID differs from `idForEncode`; for hashes matching the current ID, it can delegate the check to the inner encoder to inspect parameters like BCrypt cost.

Example with the policy in section 3:

| Stored hash | Verified by | Upgraded on successful login? |
| --- | --- | --- |
| `{bcrypt-v1}$2a$08$...` | `bcrypt-v1` | Yes, because the ID differs from the new-hash ID `bcrypt`. |
| `{bcrypt}$2a$08$...` | `bcrypt` | Potentially yes: `BCryptPasswordEncoder(12).upgradeEncoding(...)` inspects the embedded cost. |
| `{bcrypt}$2a$12$...` | `bcrypt` | Normally no upgrade needed under a cost 12 policy. |
| `{noop}rawpassword` | No encoder | Not authenticated; handled by block/reset policy. |
| `$2a$08$...` without ID | No default encoder | Not allowed to log in until properly classified/tagged or reset. |

`upgradeEncoding` does not write to the DB by itself. For durable updates, configure `UserDetailsPasswordService` on the active `DaoAuthenticationProvider` or implement equivalent logic in a custom authentication provider.

## 5. Spring Boot integration example with an existing account store

The example illustrates a Spring Boot 3, Spring Security 6, Java 17 application with a simple account table and JDBC. It configures the provider explicitly to avoid relying on which bean the app auto-selects when multiple managers/providers exist.

**Dependencies:** `spring-boot-starter-web`, `spring-boot-starter-security`, `spring-boot-starter-jdbc`, H2 for demo/test; `spring-boot-starter-test` and `spring-security-test` for testing. These are **files belonging to a Spring Boot project** with a main class and build file, not single-file Java SE programs compiled solely with `javac`.

### 5.1. Schema: `src/main/resources/schema.sql`

~~~sql
CREATE TABLE app_account (
    username VARCHAR(100) PRIMARY KEY,
    password_hash VARCHAR(255) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE
);
~~~

A production system should use versioned migrations (Flyway/Liquibase), backups, and pre/post checks. In multi-tenant setups, query keys and unique constraints must include the trusted tenant. For the H2 demo, you can use:

~~~properties
spring.datasource.url=jdbc:h2:mem:migrationdemo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

This configuration is **for learning/testing only**; never use in-memory H2 to store production passwords.

### 5.2. Looking up hashes from the DB: `DatabaseUserDetailsService.java`

~~~java
package com.example.passwordmigration;

import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

@Service
public final class DatabaseUserDetailsService
        implements UserDetailsService {

    private final JdbcTemplate jdbc;

    public DatabaseUserDetailsService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    private record Account(
            String username, String passwordHash, boolean enabled) {}

    @Override
    public UserDetails loadUserByUsername(String username) {
        List<Account> rows = jdbc.query(
                """
                SELECT username, password_hash, enabled
                FROM app_account
                WHERE username = ?
                """,
                (rs, row) -> new Account(
                        rs.getString("username"),
                        rs.getString("password_hash"),
                        rs.getBoolean("enabled")
                ),
                username
        );

        if (rows.isEmpty()) {
            throw new UsernameNotFoundException("Invalid username or password");
        }

        Account account = rows.get(0);

        return User.withUsername(account.username())
                .password(account.passwordHash())
                .disabled(!account.enabled())
                .authorities("ROLE_USER")
                .build();
    }
}
~~~

The `?` placeholder binds `username` as a parameter rather than concatenating SQL from requests. `.password(account.passwordHash())` returns the **stored encoded password** verbatim (including `{id}`), **not** a plaintext password. This adapter does not run `matches(...)` and does not assert authentication itself.

`ROLE_USER` is hardcoded only to keep the demo focused on password migration; **production must load real authorities from a server-managed source**, not assign a shared authority when multi-level authorization is required. Account locking, password expiration, and account expiration need corresponding schema/mapper extensions.

### 5.3. Writing new hashes with compare-and-swap: `JdbcPasswordUpgradeService.java`

~~~java
package com.example.passwordmigration;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsPasswordService;
import org.springframework.stereotype.Service;

@Service
public final class JdbcPasswordUpgradeService
        implements UserDetailsPasswordService {

    private final JdbcTemplate jdbc;

    public JdbcPasswordUpgradeService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public UserDetails updatePassword(UserDetails user, String newPassword) {

        // Only write if the old hash still matches: protects against overwriting
        // a concurrent password reset or update.
        int updated = jdbc.update(
                """
                UPDATE app_account
                SET password_hash = ?
                WHERE username = ? AND password_hash = ?
                """,
                newPassword,
                user.getUsername(),
                user.getPassword()
        );

        if (updated != 1) {
            throw new IllegalStateException(
                    "Password changed concurrently; retry authentication");
        }

        // Return the principal containing the new hash per the API contract.
        return User.withUserDetails(user)
                .password(newPassword)
                .build();
    }
}
~~~

Explanation:

- `UserDetailsPasswordService.updatePassword(...)` is called **after verifying the right password**, when the provider determines an upgrade is needed; `newPassword` here is the **newly encoded hash**, not a raw password.
- The SQL statement uses **compare-and-swap (CAS)**: the `AND password_hash = ?` clause prevents overwriting a new password if another process just reset/migrated it.
- If two valid logins run concurrently on the same old hash, one update may succeed while the second sees `updated=0`. The demo fails closed and asks to retry; production may re-read and resolve contention safely, but must never overwrite a password reset or ignore errors without checking.
- On database errors, the path must fail safely and raise appropriate operational alerts rather than pretending the upgrade persisted. Consider transactions, audit events, and retry bounds per your architecture.
- Never log `newPassword`, `user.getPassword()`, or credentials. Even as hashes, they remain operationally sensitive data.

### 5.4. Connecting the provider and filter chain: `SecurityConfig.java`

~~~java
package com.example.passwordmigration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UserDetailsPasswordService;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    AuthenticationProvider accountProvider(
            UserDetailsService users,
            PasswordEncoder passwordEncoder,
            UserDetailsPasswordService passwordUpdates) {

        // Spring Security 6.x: compatible no-arg constructor + setters.
        DaoAuthenticationProvider provider = new DaoAuthenticationProvider();
        provider.setUserDetailsService(users);
        provider.setPasswordEncoder(passwordEncoder);
        provider.setUserDetailsPasswordService(passwordUpdates);
        return provider;
    }

    @Bean
    SecurityFilterChain webChain(
            HttpSecurity http,
            AuthenticationProvider accountProvider) throws Exception {

        http
            .authenticationProvider(accountProvider)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
~~~

The example declares `DaoAuthenticationProvider` explicitly to highlight its three dependencies: `UserDetailsService`, `PasswordEncoder`, and `UserDetailsPasswordService`. Creating the provider with the no-arg constructor and setters works across Spring Security 6.x releases, though some APIs are deprecated in newer 6.x versions; on major upgrades, use the equivalent constructor/API supported by the target version. Do not register the same provider repeatedly across multiple managers without understanding the chain model.

A simple `/me` controller to test authenticated requests:

~~~java
package com.example.passwordmigration;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class UserController {

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/me")
    public String me(Authentication authentication) {
        return authentication.getName();
    }
}
~~~

With stateful form login, `POST /login` requires a valid CSRF token when CSRF is enabled; standard security filters handle form login, session fixation, and `SecurityContext` persistence per configuration. Never disable CSRF just to test migration.

## 6. Legacy data without `{id}`: how to transition?

There are two distinct cases:

**A. Data clearly proven to be legacy BCrypt missing a prefix.** If backed by evidence from old source code, schemas, migration history, or test vectors, an administrative job can prepend `{bcrypt-v1}` to the hash **without needing the original password**. This is strictly a **tagging operation** and does not increase hash strength. Afterward, a successful login verifies with legacy BCrypt and generates a new `{bcrypt}...` hash.

**B. Data whose algorithm cannot be determined or that appears to contain policy-unapproved plaintext/MD5.** Do not try multiple algorithms sequentially "just in case"; never enable `noop` or a global fallback. Route accounts into an identity-verified reset/recovery flow or handle under an approved risk process.

Example SQL update for **a previously classified record**, using a parameterized migration app:

~~~sql
UPDATE app_account
SET password_hash = ?
WHERE username = ? AND password_hash = ?;
~~~

Corresponding bound values: hash with new prefix, username, **exact old hash value**. Using the old hash condition prevents overwriting if the user changed their password during migration. Never run a bulk statement like "every string not starting with `{` is BCrypt" without proof.

### Verification criteria before adding prefixes

- Data originates from a verified legacy system.
- Algorithm and format of each group are well known; for BCrypt, confirm hash structure, version marker, and cost within valid bounds.
- Have a plan to count **records per group** while keeping hashes and passwords out of logs.
- Have tested backups and rollback procedures; protect backups under sensitive-data policies.
- Only assign IDs on the approved allowlist; **never** tag unknown IDs as `{bcrypt}` just to pass validation.
- Use appropriate batch sizes, error metrics, and concurrent-update detection.

For **legacy PBKDF2**, naming the algorithm alone is not enough. Implementations vary in salt length, iteration count, PRF, hex/base64 encoding, or pepper. Without knowing the exact parameters and salt storage, you cannot build a valid verifier. Once determined, write a dedicated legacy encoder with **fixed parameters** and register it under a dedicated ID like `pbkdf2-v1`; do not guess using current PBKDF2 defaults.

## 7. Standalone Java 17 example: checking the allowlist before calling a verifier

The experiment below illustrates **ID selection policy**. It **does not hash or verify passwords** and does not replace Spring Security. Its purpose is to demonstrate that the system only considers server-approved IDs.

Create `PasswordHashPolicyDemo.java`:

~~~java
import java.util.Set;

public final class PasswordHashPolicyDemo {
    private static final Set<String> ALLOWED =
            Set.of("bcrypt", "bcrypt-v1");

    static String policyDecision(String storedHash) {
        if (storedHash == null || !storedHash.startsWith("{")) {
            return "REJECT: untagged";
        }

        int close = storedHash.indexOf('}');
        if (close <= 1 || close == storedHash.length() - 1) {
            return "REJECT: malformed";
        }

        String id = storedHash.substring(1, close);
        if (!ALLOWED.contains(id)) {
            return "REJECT: id=" + id;
        }
        if (id.equals("bcrypt-v1")) {
            return "ALLOW legacy: verify, then upgrade on success";
        }
        return "ALLOW current: verify with current encoder";
    }

    public static void main(String[] args) {
        System.out.println(policyDecision("{bcrypt}example-hash"));
        System.out.println(policyDecision("{bcrypt-v1}example-hash"));
        System.out.println(policyDecision("{noop}plain"));
        System.out.println(policyDecision("$2a$08$example"));
        System.out.println(policyDecision("{bcrypt}"));
    }
}
~~~

Compile/run with JDK 17 or higher:

~~~bash
javac PasswordHashPolicyDemo.java
java PasswordHashPolicyDemo
~~~

**Exact** stdout:

~~~text
ALLOW current: verify with current encoder
ALLOW legacy: verify, then upgrade on success
REJECT: id=noop
REJECT: untagged
REJECT: malformed
~~~

The `example-hash` strings are only placeholders for **ID-check inputs**, not valid password hashes; the program deliberately **does not call `matches`**. On a real system, passing the allowlist check is **not enough**: you must still validate hash syntax, parameter policies, and verify the password with the matching encoder. When the format is unknown, prefer rejecting and running recovery rather than guessing.

## 8. Integration testing: only the right password gets rehashed

Create `src/test/java/com/example/passwordmigration/PasswordMigrationIntegrationTest.java` in the Spring Boot project with the main class, beans, and H2 above:

~~~java
package com.example.passwordmigration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class PasswordMigrationIntegrationTest {

    @Autowired JdbcTemplate jdbc;
    @Autowired MockMvc mvc;
    @Autowired PasswordEncoder encoder;

    @BeforeEach
    void reset() {
        jdbc.update("DELETE FROM app_account");
    }

    private void insert(String username, String hash) {
        jdbc.update(
            "INSERT INTO app_account(username, password_hash, enabled) VALUES (?, ?, ?)",
            username, hash, true
        );
    }

    private String hashFor(String username) {
        return jdbc.queryForObject(
            "SELECT password_hash FROM app_account WHERE username = ?",
            String.class, username
        );
    }

    @Test
    void correctPasswordUpgradesLegacyHash() throws Exception {
        String legacy = "{bcrypt-v1}"
                + new BCryptPasswordEncoder(8).encode("test-only");
        insert("alice", legacy);

        mvc.perform(formLogin().user("alice").password("test-only"))
            .andExpect(authenticated().withUsername("alice"));

        String upgraded = hashFor("alice");
        assertTrue(upgraded.startsWith("{bcrypt}"));
        assertTrue(encoder.matches("test-only", upgraded));
    }

    @Test
    void wrongPasswordDoesNotChangeStoredHash() throws Exception {
        String legacy = "{bcrypt-v1}"
                + new BCryptPasswordEncoder(8).encode("test-only");
        insert("bob", legacy);

        mvc.perform(formLogin().user("bob").password("incorrect"))
            .andExpect(unauthenticated());

        assertEquals(legacy, hashFor("bob"));
    }

    @Test
    void unsupportedAlgorithmIsNotSilentlyAccepted() {
        assertThrows(IllegalArgumentException.class,
                () -> encoder.matches("hello", "{noop}hello"));
    }
}
~~~

Spring Security Test provides the `formLogin()` request builder with CSRF handling matching the default flow. The tests insert accounts into H2, actually invoke the authentication filter/provider, and query the DB to verify whether **the hash changed or stayed intact**.

**What the tests confirm:**

1. Valid login with a legacy ID hash ⇒ legacy verifier used ⇒ `upgradeEncoding` flags upgrade needed ⇒ new hash begins with `{bcrypt}`, and the new policy's `matches` accepts the right password.
2. Wrong login ⇒ no rehash; `password_hash` column stays unchanged.
3. The `noop` ID is not in the map ⇒ encoder does not silently accept plaintext. The exact library exception type should be verified against your actual version; the test illustrates the default behavior of `DelegatingPasswordEncoder` without a default encoder.

Run in a project with Maven Wrapper:

~~~bash
./mvnw test
~~~

The Spring snippets in sections 5–8 require the Spring Boot classpath and build file; they do not run standalone with `javac`. Build output depends on the environment, so no assumed stdout is claimed. Real applications must also test other authentication mechanisms (HTTP Basic, remember-me, custom providers, multiple security chains) if they share the password store.

### Additional tests needed before rollout

| Scenario | Expected outcome |
| --- | --- |
| `{bcrypt-v1}` and correct raw password | Logs in; hash is rehashed to the current ID using the valid password. |
| `{bcrypt-v1}` and wrong password | Rejected; DB is **not** updated. |
| `{bcrypt}` with cost lower than new policy | If `upgradeEncoding` requires it, raises cost after valid login. |
| `{bcrypt}` with current parameters | Logs in; does not needlessly rewrite the hash on every request. |
| `{noop}`, `{md5}`, unknown ID, or prefix-less hash | No fallback, login fails; triggers proper error/recovery path. |
| Malformed hash even with allowlisted ID | Verifier rejects; does not grant `Authentication`. |
| Disabled/locked account | Fails authentication even with right password; never rehashes to "unlock". |
| Two concurrent logins or simultaneous admin password reset | Does not overwrite new password; CAS/transaction handles conflict safely. |
| DB failure during `updatePassword` | Does not claim migration succeeded; monitored with safe failure path. |
| Form login missing CSRF token | Does not reach successful authentication in a properly CSRF-protected app. |
| Old passwords unused for months | Handled via reset/sunset plan rather than keeping legacy verifiers indefinitely. |

## 9. Why not "try every algorithm until one matches"?

A common anti-pattern:

~~~text
for (encoder in allEncoders) {
    if (encoder.matches(raw, stored)) {
        return authenticated;
    }
}
~~~

This is an **anti-pattern**, not a design to deploy. Problems:

- Malformed/unverified-provenance data may be accepted unintentionally by an overly weak encoder.
- A "plaintext"-looking string can match `NoOpPasswordEncoder`; enabling noop increases bypass risk.
- The system does not know cleanly which policy verified a record for auditing and retirement.
- Varying complexity and response times can cause operational issues, side channels, or DoS.
- When changing algorithms, trying multiple paths does not fix missing metadata; it hides data errors and compounds migration cost.

**Alternative:** every record must be reliably classified by ID/metadata; map only to approved encoders. If information is missing to pick a unique verifier, send the record to a reset flow instead of guessing.

**Do not treat hash prefixes as self-proving:** the `{bcrypt}` prefix is only verifier-routing metadata; it does not prove the account belongs to the right user or used a valid cost. Maintain database integrity controls, look up users by trusted identity, and restrict hash modifications behind authorized APIs.

## 10. Phased migration in production

### Phase 0 — Survey and classify

- Count records by source/format/ID **without exporting hashes or passwords** to dashboards/logs.
- Verify legacy password-saving code and test vectors to confirm every algorithm, pepper, encoding, and parameter.
- Audit password resets, account changes, SSO, APIs, remember-me, caches, sessions, and legacy clients.
- Choose the current algorithm and work factor after benchmarking on real infrastructure; balance brute-force resistance against login latency/CPU.
- Define a temporary allowlist of IDs and a **sunset date**. Require approved security exceptions if a legacy algorithm is too weak; prefer forced resets when safety is insufficient.

### Phase 1 — Normalize verified metadata

- Back up following secret-protection procedures with verified restore capability.
- For legacy groups with proven format, attach the `{legacy-id}` routing tag via compare-and-swap; process in checkpointed batches.
- Unclassified records must remain **unverifiable by fallback** and go through recovery/reset.
- Never rewrite `{bcrypt-v1}hash` to `{bcrypt}hash` just to make completion metrics look done; if cost/algorithm has not changed, **no rehash occurred**.

### Phase 2 — Read both old and new per policy

- Deploy a **narrow** `DelegatingPasswordEncoder` allowlist with `idForEncode` pointing strictly to the current algorithm.
- Verify the provider uses the right encoder and `UserDetailsPasswordService`; if multiple `AuthenticationProvider`s exist, review each separately.
- The unknown-ID error path must fail safely without leaking username existence/hashes and without silently allowing `noop`.
- Deploy metrics: legacy verifications, upgrade successes/failures, remaining legacy accounts, login latency, and CPU. Never record secrets.
- Support controlled application rollbacks, but never roll back new password hashes to weaker algorithms.

### Phase 3 — Rehash-on-login / reset

- User with valid password and legacy hash ⇒ verify old ⇒ new hash ⇒ CAS update.
- When users **change/reset passwords**, always encode under the new policy; these flows must never write legacy hashes.
- Users who do not log in for months will not self-upgrade; send reasonable reset prompts or upgrade when they return, depending on the sunset deadline.
- If a legacy algorithm is unacceptably weak, **do not wait indefinitely for logins**; enforce resets via an identity-verified channel.

### Phase 4 — Retire legacy acceptance

- Confirm remaining legacy account counts, dormant-user policies, and client authentication coverage.
- Remove old IDs from the allowlist after the approved deadline; re-test unknown IDs/legacy IDs.
- Keep all new passwords on the new scheme; remove migration code once finished.
- Update runbooks, alerts, audits, and account recovery flows. Never keep weak verifiers forever because "a few old users remain".

**The definition of "migration complete"** is not merely that the column now has prefixes. Completion means eligible users hold current hashes, un-upgraded accounts went through recovery/reset or appropriate disabling, and old verifiers have been removed per policy.

## 11. Risks and edge cases

### Missing algorithm ID

If `DelegatingPasswordEncoder` encounters a bare hash lacking `{id}` without a default, it cannot reliably pick an encoder; default behavior may throw an exception. This signals unmigrated data. Never "fix" it with `setDefaultPasswordEncoderForMatches(NoOpPasswordEncoder...)` or a generic fallback that accepts arbitrary strings.

If short-term support is needed for a **certainly identified** set of bare BCrypt hashes, run a data-tagging job first or an explicit ID/format lookup from trusted metadata; never identify them by trying encoders sequentially.

### Legacy MD5/SHA-1/plaintext

These formats do not meet modern password storage requirements. If the old system genuinely holds them, prioritize **identity-verified password resets**; any transitional exception must be an approved security decision with narrow scope, time limits, and mitigations. Never add a weak encoder into the system-wide default allowlist just to avoid customer support tickets.

### Changing algorithms and parameters

Changing BCrypt cost, moving from BCrypt to Argon2id, or raising PBKDF2 iterations are all **new-hash** migrations requiring the raw password when rehashing. Especially with PBKDF2, the same algorithm name with different parameters/formats constitutes distinct verifier schemes.

Never pick an algorithm just because its name sounds newer; evaluate maintained libraries, environment (memory/CPU), security standards, and system limits. Benchmark and measure real authentication latency.

### Pepper, HSMs, and historical secret formats

If legacy hashes were created from `pepper + password` or a KDF using an external secret, you must know the exact byte/encoding combination and still possess the secret to verify. Losing the pepper can render legacy passwords unverifiable; in that case, run a reset workflow rather than assuming the current encoder can verify them.

Peppers/keys must be managed via an appropriate secret manager/HSM—never stored in source code, DB dumps, or logs. Rotation may require parallel key IDs and time-bounded transitions; that is a separate cryptographic policy alongside password-hash algorithm IDs.

### Race condition during password change

The demo uses `UPDATE ... WHERE password_hash = oldHash`. Suppose an admin resets the password during a login:

~~~text
T1: reads hash A -> verifies password matches A
T2: resets password -> writes hash B
T1: tries updating A -> hash C with condition stored=A
Result: 0 rows updated; B remains intact, not overwritten
~~~

This is the **correct behavior to protect the reset**. T1 may need to retry authentication per security design, and a user whose password was reset must never silently retain a valid new session. If using a `UserDetails` cache or event-driven updates, solve consistency equivalently.

### Multiple instances and availability

A rolling deployment with multiple server versions running concurrently must ensure older code **can read** the new hash scheme before newer instances start writing them; otherwise a user logging in on instance A gets upgraded and is then rejected on instance B running old code. A safe strategy typically deploys code that **reads both legacy and new** first, then enables **writing new**, and finally removes legacy reads. Never lower cryptographic standards to mask rollout bugs.

Also bound aggregate password-hashing cost: every login is expensive in CPU/memory; enforce rate limiting, appropriate account lockout/backoff, credential-stuffing defenses, and performance monitoring to prevent DoS.

## 12. Common errors and diagnostics

| Symptom | Possible cause | Check/safe action |
| --- | --- | --- |
| `There is no PasswordEncoder mapped for the id "null"` | Legacy hash lacks prefix. | Classify and tag with evidence or reset; never enable noop fallback. |
| Prefix added yet login still fails | ID mismatches format/cost/pepper, password truly wrong, or data corrupted. | Check test vectors and encoder history; never brute-force algorithms blindly. |
| `{bcrypt-v1}` logs in yet DB does not change | `UserDetailsPasswordService` not wired to right provider; updater failed; `upgradeEncoding` not triggered. | Test provider + service + DB after successful login. |
| Login succeeds yet new scheme still has old cost | Only changed prefix without calling `encode(raw)`; new encoder cost not raised. | Inspect new hash generated by encoder; never rename legacy IDs. |
| Failed login updates hash | Custom flow rehashes before verifying, lacking success boundary. | Persist only after successful auth; test wrong password keeps hash unchanged. |
| Password reset record overwritten | Unconditional update after reading old hash. | Use CAS/transactions and handle conflicts. |
| User logs in on node A yet fails on node B | Nodes lack matching allowlist or compatible versions. | Two-phase reader-before-writer rollout; consistent config. |
| Hashes still stored as plaintext after migration | Client/service bypasses encoder, script writes raw values, `noop` permitted. | Audit all create/change/reset password flows; forbid plaintext storage. |
| Group of dormant users still legacy | They never log in so rehash-on-login never runs. | Enforce reset/sunset schedule rather than keeping old support forever. |
| Authentication returns 500 on unknown ID | Encoder throws format error unhandled at proper boundary. | Fail closed and route error through proper handling/monitoring, never convert to successful login. |

## 13. Deployment checklist

- [ ] Inventory and evidence exist for every historical hash/password format, including parameters and peppers.
- [ ] **Allowed ID → encoder** list exists, with every mapping having an owner/approval and expiration if legacy.
- [ ] `idForEncode` points strictly to the approved scheme for new passwords.
- [ ] `noop` is disabled, no fallback for unknown-ID hashes, and never sequentially try multiple encoders.
- [ ] Accounts with unclassifiable hashes go through safe reset/recovery.
- [ ] `UserDetailsService` returns full stored hash; `DaoAuthenticationProvider` uses the policy encoder.
- [ ] `UserDetailsPasswordService` or equivalent flow is wired to the provider with CAS DB updates.
- [ ] Tests: right password → rehash; wrong password → no write; unknown ID → reject; policy cost → upgrade.
- [ ] Verify across session/form login, APIs, multi-node, caches, disabled accounts, concurrent logins, and password resets.
- [ ] Metrics/audits **contain no** raw passwords, password hashes, tokens, or session cookies.
- [ ] Sunset schedule, legacy-encoder removal criteria, and guidance for long-inactive users are defined.
- [ ] Rollback never reverts current hashes back to weak schemes.

## 14. Review questions

**Q1. Why is merely prepending `{bcrypt}` to an old hash not a password upgrade?** Because the hash body and cost remain old. True rehashing requires the valid raw password and encoding with the new scheme.

**Q2. How does `DelegatingPasswordEncoder` choose a verifier?** It extracts `{id}` from the stored hash and looks up the encoder in the server's allowlist map. `idForEncode` specifies the encoder used when creating new hashes.

**Q3. Should you enable a blanket fallback for all legacy password data missing `{id}`?** No. Only tag records after proving the historical scheme with certainty, or use a reset workflow. Blind fallbacks expand weak algorithms beyond policy.

**Q4. How does `UserDetailsPasswordService`'s role differ from `UserDetailsService`?** `UserDetailsService` reads the user/hash; `UserDetailsPasswordService` writes the upgraded hash after the provider authenticates successfully and requests an upgrade.

**Q5. Why is `WHERE password_hash = oldHash` needed when updating?** To prevent a login based on an old hash from overwriting a concurrent password change/reset from another thread/server.

**Q6. Can old hashes be converted to Argon2id without knowing the original password?** No, unless the valid raw password is present at login/change/reset. Hashing is one-way and cannot safely convert between schemes by algorithm name alone.

**Q7. Is it acceptable to keep legacy encoders forever because some accounts never log in?** No. Set a retirement deadline for old acceptance, handle dormant users, and maintain recovery/reset flows.

**Remember:** **Classify accurately → narrow allowlist → verify with approved scheme → rehash only after success → update safely → retire legacy on schedule.** This is how to migrate a password store without accidentally accepting weak algorithms or breaking authentication workflows.

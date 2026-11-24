# encode, matches, and upgradeEncoding in the Password Lifecycle

## 1. Objectives and Context

In a **Spring Security application using the Servlet stack**, passwords go through several stages: a user registers or resets their password; the server generates a password hash for storage; on each username/password authentication attempt, the server verifies the password the user provides; and when algorithm or strength policies change, the application can upgrade old hashes during a valid login.

The **org.springframework.security.crypto.password.PasswordEncoder** interface provides three core operations:

1. **encode(rawPassword)**: transforms the user-supplied password into a storable **encoded password/hash**. With bcrypt, the resulting string contains a salt and cost parameter; two encodes of the same password typically produce different strings.
2. **matches(rawPassword, encodedPassword)**: verifies whether the entered password matches the stored hash. It does not decrypt the hash, and you should not compare two encode calls with equals.
3. **upgradeEncoding(encodedPassword)**: returns a boolean indicating whether **the stored hash needs to be upgraded** under the encoder's current policy. This method **does not** authenticate, rehash, or write data to the database.

This lesson helps you understand all three methods accurately, connect them to **DaoAuthenticationProvider** and **UserDetailsPasswordService**, and run a Java 17+/Spring Boot 3.3.13 example with old/new bcrypt costs, testing successful login, failed login, hash upgrades, and avoiding overwriting a new password due to a race condition.

**Scope:** Spring Security Servlet, focused on username/password authentication. OAuth2 login, JWT, and custom AuthenticationProviders handle credentials differently; do not apply this mechanism verbatim to every Authentication type.

## 2. Raw password, password hash, and salt

| Component | Meaning | How to handle |
| --- | --- | --- |
| Raw password | Secret entered by the user | Handle only temporarily over HTTPS, never store in plaintext |
| Encoded password/hash | Value returned by PasswordEncoder.encode | Store in a protected data store |
| Salt | Random data so two accounts with the same password do not produce identical hashes | Usually embedded in the bcrypt hash string; not a secret replacing the password |
| Work factor/cost | Parameter controlling hash computation effort | Choose after benchmarking, evaluating latency and load |
| PasswordEncoder | Component providing encode/matches/upgradeEncoding | Must be compatible with the hash format in the store |
| UserDetails.getPassword() | Hash value used for authentication via provider | Must not contain raw passwords in production |

**PasswordEncoder has no decode().** Proper password hashing is a one-way mechanism. When a user forgets their password, the application must verify permission to reset and then **encode a new password**, rather than recovering the old password from the hash.

**Bcrypt does not produce a fixed output for the same raw password.** Random salt makes two hash strings usually differ. Therefore, never use `encoder.encode(raw).equals(storedHash)` as a verification step.

## 3. Contract of PasswordEncoder

The three core methods, written according to the API structure:

~~~java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);

    boolean matches(CharSequence rawPassword, String encodedPassword);

    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
~~~

This is an **illustrative signature** of the existing interface in Spring Security; do not recreate this interface file in the practice project.

### 3.1. encode: use only for raw passwords that need to be stored

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder(10);

String first = encoder.encode("a-password");
String second = encoder.encode("a-password");

boolean firstMatches = encoder.matches("a-password", first);
boolean secondMatches = encoder.matches("a-password", second);
~~~

The two variables `first` and `second` usually differ; **firstMatches = true** and **secondMatches = true**. Do not expose the returned hash in API responses, logs, or exception messages.

Typical times to call encode are: account registration, password change, password reset after verifying authorization, or hash upgrade once the raw password has been proven correct at login. With `updatePassword` called by DaoAuthenticationProvider, **newPassword is already a hash**—do not encode it a second time.

### 3.2. matches: verifying credentials

~~~java
String storedHash = encoder.encode("a-password");

boolean correct = encoder.matches("a-password", storedHash);
boolean incorrect = encoder.matches("bad-password", storedHash);
~~~

Deterministic results:

~~~text
correct = true
incorrect = false
~~~

`matches` takes the raw password as the first argument and **the hash from the data store** as the second argument. It requires an encoder compatible with the hash format. If the database stores strings with the **{bcrypt}** prefix but you use a raw BCryptPasswordEncoder to read them, check your configuration: direct BCryptPasswordEncoder expects a raw bcrypt hash, whereas DelegatingPasswordEncoder understands `{id}` prefixes.

When the password is wrong, do not update the hash and do not treat `upgradeEncoding` as proof of authentication. Before allowing access, the provider may also check account enabled/locked/expired flags and other rules.

### 3.3. upgradeEncoding: only a policy signal

~~~java
boolean shouldUpgrade = encoder.upgradeEncoding(storedHash);
~~~

- **true:** the encoder detects that the old hash should be replaced with a new representation under the current policy.
- **false:** the encoder does not require an upgrade; do not infer whether the password is right or wrong.
- Do not pass raw passwords into `upgradeEncoding`.
- There are no database side effects whatsoever simply from calling this method.
- `PasswordEncoder` has a default method returning false; implementations can evaluate upgrades in their own way.

In particular, **BCryptPasswordEncoder** can compare the work factor inside the hash against the configured strength. If the old hash has a lower cost than the current strength, it should be upgraded. If the cost is equal or higher, it usually does not suggest downgrading.

## 4. Password lifecycle and hash update decisions

~~~text
[Registration / change / password reset]
    new rawPassword
        |
        v
    check policy, verify set/change authorization
        |
        v
    PasswordEncoder.encode(rawPassword)
        |
        v
    INSERT or UPDATE password_hash

[Login]
    rawPassword from request
        |
        v
    UserDetailsService retrieves storedHash
        |
        v
    PasswordEncoder.matches(rawPassword, storedHash)
        |
        +-- false --> authentication fails, DO NOT UPDATE hash
        |
        +-- true --> authentication succeeds via appropriate provider
                        |
                        v
                upgradeEncoding(storedHash)?
                        |
                        +-- false --> keep current hash
                        |
                        +-- true --> encode(verified rawPassword)
                                           |
                                           v
                                    save new hash with safe update
                        |
                        v
                Valid Authentication for the request
~~~

The diagram presents **conceptual decisions**, not the entire internal call stack. The provider also checks user state, publishes events, and constructs the `Authentication` according to the specific configuration. The crucial rule is **never upgrade a hash based on an unauthenticated password**.

| Scenario | encode | matches | upgradeEncoding | Storage action |
| --- | --- | --- | --- | --- |
| Create account | Yes | Not necessarily | No | INSERT encoded password |
| Wrong password login | No | Returns false | Not needed | None |
| Correct login, current hash | No | Returns true | Returns false | None |
| Correct login, legacy hash | Yes, with verified raw | Returns true | Returns true | UPDATE new hash |
| Change password | Yes, with new password | May need to check old password | Not the primary condition | UPDATE new hash |
| Reset password | Yes, after valid token/verification | Cannot check forgotten password | No | UPDATE + revoke reset token |

**You cannot rehash the entire database solely from old stored hashes.** One-way password hashes do not provide the raw password needed to compute a valid hash under the new policy. Common strategies are **opportunistic upgrade** upon successful login, or requiring a reset for accounts that have not logged in for a long time.

## 5. BCryptPasswordEncoder: why do old hashes still match?

BCryptPasswordEncoder can normally accept a hash stored with an older cost and check the raw password using the parameters embedded in the hash, even if the current instance is configured with a new strength.

~~~java
PasswordEncoder oldEncoder = new BCryptPasswordEncoder(6);
PasswordEncoder currentEncoder = new BCryptPasswordEncoder(10);

String oldHash = oldEncoder.encode("secret-123");

boolean valid = currentEncoder.matches("secret-123", oldHash);
boolean needsUpgrade = currentEncoder.upgradeEncoding(oldHash);
~~~

Expected result in this scenario:

~~~text
valid = true
needsUpgrade = true
~~~

Strength 6 is used solely to illustrate the difference; **it is not a production recommendation**.

A bcrypt string typically has the structure:

~~~text
$2a$10$...salt-and-hash...
     ^^
     cost
~~~

You may encounter prefixes `2a`, `2b`, or `2y` depending on the source/version. The cost parameter is part of the hash, so there is no need to store a separate cost column for verification purposes.

If the current encoder is BCrypt(10):

- Bcrypt hash with cost 6: **matches** correct password = true; **upgradeEncoding** = true.
- Hash with cost 10: correct matches = true; upgradeEncoding = false.
- Hash with cost 12: correct matches = true; upgradeEncoding is normally false, because it does not downgrade cost just to match the current value.
- Corrupted or non-bcrypt hash: you cannot rely on matches/upgradeEncoding to infer safely. Format validation and migration policies are required.

**Choosing strength:** raising the cost makes both successful and failed logins consume more CPU. Benchmark on real hardware, balancing latency against offline brute-force resistance and DoS risk, rather than raising it arbitrarily without load testing.

## 6. When does DaoAuthenticationProvider upgrade automatically?

**DaoAuthenticationProvider** is an AuthenticationProvider that uses **UserDetailsService** and **PasswordEncoder** for username/password. When configured properly, it can perform hash upgrades automatically:

1. UserDetailsService looks up the user and returns the current encoded password.
2. DaoAuthenticationProvider calls PasswordEncoder.matches(raw, storedHash).
3. After successful authentication, the provider checks encoder.upgradeEncoding(storedHash).
4. When an upgrade is needed **and a UserDetailsPasswordService is present**, the provider calls PasswordEncoder.encode(proven-correct raw password).
5. The provider calls UserDetailsPasswordService.updatePassword(user, newEncodedHash).
6. The provider builds the Authentication result; ProviderManager typically erases credentials from the result after authentication.

The interface for saving the new hash:

~~~java
package org.springframework.security.core.userdetails;

public interface UserDetailsPasswordService {
    UserDetails updatePassword(UserDetails user, String newPassword);
}
~~~

**newPassword in updatePassword is an encoded hash**, not a raw password. Any implementation that calls encode(newPassword) a second time will store a **hash of a hash**, preventing the original password from matching on subsequent logins.

Simply having a PasswordEncoder bean does not make automatic updates work. You must **wire UserDetailsPasswordService to the right provider** or design an equivalent mechanism. For custom AuthenticationProviders, you are responsible for ensuring the password check succeeds before upgrading, while maintaining transactions and data consistency.

### Critical race condition

Request A logs in with the old password. Before A updates the hash, request B successfully changes/resets the password and saves a new hash. If A performs an unconditional UPDATE, A may write the **upgraded hash of the old password** over the new password, causing B's reset action to be overwritten.

With a database, use **optimistic locking/row version**, or a conditional UPDATE **WHERE password_hash = old_hash** (and appropriate account version), then handle the 0-rows-updated case. Sensitive systems may also need to recheck account status and revoke sessions/tokens. Do not assume a simple compare-and-swap alone solves every authorization revocation issue after a password reset.

## 7. Runnable Spring Boot example: upgrading bcrypt cost 6 to 10

The following project uses **Java 17+**, **Spring Boot 3.3.13**, Maven, and stateless HTTP Basic. This is a local learning environment: sample users/passwords must not be used in production.

Three accounts:

- **legacy / legacy-pass**: initially hashed with bcrypt cost 6; a successful login upgrades it to cost 10.
- **current / current-pass**: cost 10 hash; a successful login does not require an update.
- **badlogin / badlogin-pass**: cost 6 hash; used to test sending a wrong password to verify the hash is not changed.

File tree:

~~~text
password-lifecycle-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/passworddemo/
    │   ├── PasswordLifecycleApplication.java
    │   ├── SecurityConfig.java
    │   ├── InMemoryAccountService.java
    │   └── AccountController.java
    └── test/java/com/example/passworddemo/
        └── PasswordLifecycleTest.java
~~~

### 7.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>password-lifecycle-demo</artifactId>
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
~~~

Do not declare a separate Spring Security version manually; the Spring Boot parent manages compatible versions within the release line.

### 7.2. PasswordLifecycleApplication.java

~~~java
package com.example.passworddemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PasswordLifecycleApplication {

    public static void main(String[] args) {
        SpringApplication.run(PasswordLifecycleApplication.class, args);
    }
}
~~~

Classes are placed under the same package `com.example.passworddemo` so Spring Boot component scan finds the configuration and controller.

### 7.3. InMemoryAccountService.java

We use a **ConcurrentHashMap** as a simulated store and implement both UserDetailsService and UserDetailsPasswordService. Notably, the **UserDetails returned to the provider is a copy**: this prevents ProviderManager.eraseCredentials from mutating the object stored inside the Map directly.

~~~java
package com.example.passworddemo;

import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsPasswordService;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class InMemoryAccountService
        implements UserDetailsService, UserDetailsPasswordService {

    private final Map<String, UserDetails> accounts =
        new ConcurrentHashMap<>();

    public InMemoryAccountService(
            PasswordEncoder oldEncoder,
            PasswordEncoder currentEncoder) {

        accounts.put("legacy", User.withUsername("legacy")
            .password(oldEncoder.encode("legacy-pass"))
            .roles("USER")
            .build());

        accounts.put("current", User.withUsername("current")
            .password(currentEncoder.encode("current-pass"))
            .roles("USER")
            .build());

        accounts.put("badlogin", User.withUsername("badlogin")
            .password(oldEncoder.encode("badlogin-pass"))
            .roles("USER")
            .build());
    }

    @Override
    public UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException {

        UserDetails stored = accounts.get(username);

        if (stored == null) {
            throw new UsernameNotFoundException("User not found");
        }

        // Do not return the same mutable instance held in cache/store.
        return User.withUserDetails(stored).build();
    }

    @Override
    public UserDetails updatePassword(
            UserDetails user, String newPassword) {

        // newPassword is ALREADY a hash encoded by DaoAuthenticationProvider.
        UserDetails result = accounts.compute(
            user.getUsername(),
            (username, current) -> {
                if (current == null) {
                    throw new UsernameNotFoundException("User not found");
                }

                // Do not overwrite if the hash changed between load and update.
                if (!Objects.equals(
                        current.getPassword(), user.getPassword())) {
                    return current;
                }

                return User.withUserDetails(current)
                    .password(newPassword)
                    .build();
            }
        );

        // The returned copy is also detached from the object in the Map.
        return User.withUserDetails(result).build();
    }

    // Only for unit/integration tests in the same package.
    String hashForTest(String username) {
        UserDetails stored = accounts.get(username);
        if (stored == null) {
            throw new UsernameNotFoundException("User not found");
        }
        return stored.getPassword();
    }
}
~~~

**Key points to understand:**

- The Map holds **hashes**, not raw passwords.
- BCrypt(6) and BCrypt(10) are used only to seed test data.
- loadUserByUsername creates a copy so the principal can have its credentials erased without corrupting the original record.
- updatePassword does not encode again. It simply receives the new hash and saves it.
- Map.compute helps avoid a simple lost update when the original hash changes concurrently, though it does not replace optimistic locking/versioning, transactions, or revocation policies in production.
- The `hashForTest` method is package-private; there is no HTTP endpoint exposing password hashes.

When using a database and JPA entities, do not let a managed entity and the principal object undergoing credential mutation/erasure be the same instance when that would cause hard-to-control side effects. Design clear boundaries between stored data, authenticated UserDetails, and caches.

### 7.4. SecurityConfig.java

~~~java
package com.example.passworddemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(10);
    }

    @Bean
    InMemoryAccountService accountService(PasswordEncoder currentEncoder) {
        return new InMemoryAccountService(
            new BCryptPasswordEncoder(6),
            currentEncoder
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            InMemoryAccountService accounts,
            PasswordEncoder encoder) throws Exception {

        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider();
        provider.setUserDetailsService(accounts);
        provider.setPasswordEncoder(encoder);
        provider.setUserDetailsPasswordService(accounts);

        http
            .authenticationProvider(provider)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public").permitAll()
                .requestMatchers("/me").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable);

        return http.build();
    }
}
~~~

**Three key links:**

1. The current PasswordEncoder is BCrypt(10), so BCrypt cost 6 hashes **still match**, while **upgradeEncoding returns true**.
2. DaoAuthenticationProvider is explicitly configured with **UserDetailsService**, **PasswordEncoder**, and **UserDetailsPasswordService**, enabling successful logins to persist the new hash automatically.
3. HTTP Basic with SessionCreationPolicy.STATELESS makes each curl request authenticate independently, making it convenient to observe one upgrade followed by subsequent requests with no further upgrades.

The example intentionally does not disable CSRF. The test endpoints only use GET, requiring no CSRF token. When adding POST/PUT/DELETE, evaluate CSRF according to the client model; browsers can automatically send cached HTTP Basic credentials. Use HTTPS, login rate limiting, and real user data management in production deployments.

### 7.5. AccountController.java

~~~java
package com.example.passworddemo;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    @GetMapping("/public")
    public Map<String, String> publicEndpoint() {
        return Map.of("message", "public-ok");
    }

    @GetMapping("/me")
    public Map<String, String> profile(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }
}
~~~

The controller does not return raw passwords, hashes, the Authentication object, or the Authorization header. Password hashes are inspected only internally via tests; do not create an endpoint that returns hashes to clients.

## 8. Running the example and testing scenarios

From the directory containing pom.xml:

~~~bash
mvn spring-boot:run
~~~

Use another terminal to run curl; on some Windows PowerShell versions you need to call **curl.exe** to avoid the alias.

**Public:**

~~~bash
curl -i http://localhost:8080/public
~~~

Expected HTTP **200**, JSON with `message = "public-ok"`.

**Without credentials:**

~~~bash
curl -i http://localhost:8080/me
~~~

Expected HTTP **401** because the endpoint requires authentication.

**Legacy wrong password:**

~~~bash
curl -i -u legacy:wrong-pass http://localhost:8080/me
~~~

Expected **401**. The stored cost 6 hash is not upgraded because authentication has not succeeded.

**Legacy correct password:**

~~~bash
curl -i -u legacy:legacy-pass http://localhost:8080/me
~~~

Expected **200**, JSON with `username = "legacy"`. The first login uses `matches` to verify the cost 6 hash, `upgradeEncoding` sees an upgrade is needed, and DaoAuthenticationProvider calls UserDetailsPasswordService to save the cost 10 hash. Calling this command a second time still returns 200, but the hash has already reached cost 10 so it does not need to be rewritten.

**Current correct password:**

~~~bash
curl -i -u current:current-pass http://localhost:8080/me
~~~

Expected **200** and no hash update because the cost is already 10.

| Request | Expected status | Hash impact |
| --- | --- | --- |
| GET /public without credentials | 200 | None |
| GET /me missing credentials | 401 | None |
| GET /me legacy wrong password | 401 | None |
| GET /me legacy correct first time | 200 | Cost 6 → cost 10 |
| GET /me legacy correct second time | 200 | Keeps cost 10 hash |
| GET /me current correct | 200 | Unchanged |

You cannot prove the hash was updated from status 200 alone. The following test reads the hash directly from the internal store; never include hashes in JSON returned to users.

## 9. Integration test: verifying all three APIs and the persistence step

Create **src/test/java/com/example/passworddemo/PasswordLifecycleTest.java**:

~~~java
package com.example.passworddemo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class PasswordLifecycleTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    PasswordEncoder encoder;

    @Autowired
    InMemoryAccountService accounts;

    @Test
    void correctLegacyLoginUpgradesAndPersistsHash() throws Exception {
        String before = accounts.hashForTest("legacy");

        assertEquals(6, bcryptCost(before));
        assertTrue(encoder.matches("legacy-pass", before));
        assertTrue(encoder.upgradeEncoding(before));

        mvc.perform(get("/me").with(httpBasic("legacy", "legacy-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("legacy"));

        String after = accounts.hashForTest("legacy");
        assertNotEquals(before, after);
        assertEquals(10, bcryptCost(after));
        assertTrue(encoder.matches("legacy-pass", after));
        assertFalse(encoder.upgradeEncoding(after));

        mvc.perform(get("/me").with(httpBasic("legacy", "legacy-pass")))
            .andExpect(status().isOk());

        assertEquals(after, accounts.hashForTest("legacy"));
    }

    @Test
    void badPasswordDoesNotTriggerUpgrade() throws Exception {
        String before = accounts.hashForTest("badlogin");
        assertEquals(6, bcryptCost(before));

        mvc.perform(get("/me").with(httpBasic("badlogin", "wrong-pass")))
            .andExpect(status().isUnauthorized());

        assertEquals(before, accounts.hashForTest("badlogin"));
        assertTrue(encoder.upgradeEncoding(before));
    }

    @Test
    void CurrentHashNeedsNoUpgrade() throws Exception {
        String before = accounts.hashForTest("current");
        assertEquals(10, bcryptCost(before));
        assertFalse(encoder.upgradeEncoding(before));

        mvc.perform(get("/me").with(httpBasic("current", "current-pass")))
            .andExpect(status().isOk());

        assertEquals(before, accounts.hashForTest("current"));
    }

    private static int bcryptCost(String encodedHash) {
        // Raw bcrypt hash: $2a$10$...
        return Integer.parseInt(encodedHash.split("\\$")[2]);
    }
}
~~~

Run:

~~~bash
mvn test
~~~

The three tests use separate users so they do not depend on execution order. Note that the test named `CurrentHashNeedsNoUpgrade` starting with an uppercase letter is still a valid Java method; `lowerCamelCase` naming is usually recommended for consistency.

**Key expectations:**

- The `legacy` test confirms the hash changed, cost went from 6 to 10, `matches` still passes, `upgradeEncoding` after the update is false, and the second login does not rewrite the hash unnecessarily.
- The `badlogin` test confirms wrong password → 401, and the hash remains unchanged even though it does not yet meet the new strength.
- The `current` test confirms a compliant hash is not rewritten on every authentication.

**Why is MockMvc needed?** A unit test calling `encoder.upgradeEncoding` alone only reveals the true/false answer. Testing through HTTP Basic and SecurityFilterChain additionally proves that DaoAuthenticationProvider **actually** calls `updatePassword` after a successful login. For production, test with a real DB/transaction and concurrent password change/reset scenarios.

## 10. DelegatingPasswordEncoder and the {id} format

A system may have gone through multiple generations of password storage algorithms: bcrypt, PBKDF2, scrypt, Argon2. Spring Security provides **DelegatingPasswordEncoder** to dispatch encoders by ID.

Example formats:

~~~text
{bcrypt}$2a$10$...
{pbkdf2}...
{scrypt}...
{argon2}...
~~~

These are **illustrative patterns**, not complete hashes usable for login. The ID between `{` and `}` identifies the right encoder; the hash string after the ID must have been generated properly by that algorithm.

Configuration from the factory:

~~~java
PasswordEncoder encoder =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();
~~~

You must import `org.springframework.security.crypto.factory.PasswordEncoderFactories` and `PasswordEncoder` in the class using them. Do not hardcode the assumption that the factory always uses a specific cost: the policy changes across versions and configurations.

- **encode(raw)** uses the selected encoder to generate a new hash, usually with a `{id}` prefix.
- **matches(raw, stored)** picks the encoder from the stored hash's ID.
- **upgradeEncoding(stored)** can check both whether the old ID differs from the current ID and the upgrade policy inside the selected encoder.

If historical data stores bcrypt **without `{bcrypt}`**, you cannot assume a new DelegatingPasswordEncoder will automatically match that data; you must design migration/fallback strictly for verified formats. Do not enable NoOpPasswordEncoder as a broad fallback to make login errors disappear, as that can cause the system to accept improperly hashed passwords.

### When changing algorithms, can everything be rehashed immediately?

No, if you only have old password hashes and no raw passwords. You must convert after a valid authentication or require a reset according to a plan. You can track the percentage of old hashes upgraded via safe metrics, without outputting raw passwords or hashes into logs.

## 11. Common pitfalls and how to avoid them

### Pitfall 1: double encoding

UserDetailsPasswordService receives **newPassword already as a hash** from the provider. If you call `encoder.encode(newPassword)` and save it, you create a hash of a hash. The original password can no longer authenticate as before.

### Pitfall 2: calling encode then comparing with equals

Bcrypt uses random salt so `encoder.encode(raw)` can differ from `storedHash` even when `raw` is correct. Always use `matches(raw, storedHash)`.

### Pitfall 3: calling upgradeEncoding and believing the DB updates itself

`upgradeEncoding` is a boolean query. The provider/application must perform the encode and persist the new hash once authentication succeeds.

### Pitfall 4: rehashing an old hash as a raw password

Doing `encode(storedHash)` does not properly upgrade a password hash; it turns **the old hash string** into a new input, making the user's raw password stop matching. You cannot recover the raw password from a one-way hash.

### Pitfall 5: wrong encoder or format

A plain BCryptPasswordEncoder is not a DelegatingPasswordEncoder; a hash with a `{bcrypt}` prefix is not the same as a raw bcrypt hash. Identify the stored format and handle migration in a controlled way.

### Pitfall 6: raising cost without benchmarking

Increasing strength can overload CPU on the login endpoint. Measure latency on real hardware, accounting for concurrent requests, rate limiting, and DoS resilience.

### Pitfall 7: cached UserDetails getting erased

In the username/password flow, ProviderManager usually erases credentials from the Authentication result. If the principal uses **the same mutable UserDetails object** held in a cache, erasure can wipe the password hash in the cache. Return independent copies and have a cache invalidation strategy.

### Pitfall 8: upgrading after a wrong password

Never update the password when `matches` has not succeeded. Knowing that a hash is "outdated" does not prove the caller knows the right password.

### Pitfall 9: overwriting a password reset due to a race condition

A rehash from an in-flight login must not overwrite a new password hash saved by a reset flow. Use optimistic locking/conditional updates against the old value, controlling account state and transactions.

### Pitfall 10: saving an upgraded hash while still serving stale cache

If UserDetailsService/UserCache uses a cache, you must evict/refresh the data after saving the new hash. Otherwise, other requests may keep reading the old hash or outdated authorities/account flags.

### Pitfall 11: exposing password hashes in business APIs

Do not return raw passwords, password hashes, Authorization headers, or the entire Authentication in API responses. Never create an endpoint just to debug hashes; replace it with controlled internal tests.

## 12. Distinguishing upgrade, change, and password reset

**Hash upgrade:** the user keeps **the same raw password**. After a valid login, the application creates a new encoded representation according to policy. For accounts that do not log in, hashes may remain old until a migration/reset occurs.

**Password change:** the user requests using a **new raw password**. The flow must check permissions, possibly require the old password/step-up auth, then encode the new password and update atomically, invalidate caches, and consider revoking sessions/tokens.

**Password reset:** the user does not know the old password. The application must verify an appropriate reset token/proof, check single-use and expiration, then encode the new password and revoke the reset token. Never use `upgradeEncoding` as a reset mechanism.

**Password history:** if you need to check whether a new password matches an old one, use `matches(newRaw, storedHistoricalHash)` instead of comparing two bcrypt hashes with `equals`. Storing password history increases data sensitivity and requires separate retention and access controls.

## 13. Diagnosing when a hash does not upgrade

Follow this sequence:

1. **What is the current encoder?** Is it really BCrypt(10) or another configuration?
2. **What format is the hash in the database?** Raw bcrypt, `{bcrypt}`, `{argon2}`, or a truncated string?
3. **Does `matches` return true?** If false, do not try to upgrade another way to bypass authentication.
4. **What does `upgradeEncoding` return?** Is the current cost/ID actually lower than the policy?
5. **Is the active AuthenticationProvider actually DaoAuthenticationProvider?** Are there multiple providers/chains?
6. **Is UserDetailsPasswordService set on the provider?** If not, there is nowhere for the automatic flow to persist.
7. **Does `updatePassword` write `newEncodedHash` directly?** Avoid double encoding.
8. **Did the update succeed?** Check transactions, optimistic locking, conditional updates, or non-existent users.
9. **Was the cache invalidated/refreshed?** Is UserDetailsService cache or UserCache using shared objects?
10. **Does the next request actually re-authenticate?** Form login sessions may not go through the provider on every GET; stateless HTTP Basic is easier to observe.
11. **Are there account status errors?** A locked, disabled, or expired user can fail authentication even when `matches` is true.
12. **Are secrets being logged?** Never log raw passwords, hashes, or Authorization headers just for diagnostics.

| Symptom | Possible cause | Check |
| --- | --- | --- |
| Correct password but old cost hash does not change | Missing UserDetailsPasswordService | Attach the service to the right provider |
| Correct login, upgradeEncoding is false | Hash already meets strength or has the right ID | Check the actual encoder |
| Cannot log in after an upgrade | Double encoding or wrong hash written | updatePassword and matches |
| User changed password but old password still works | Stale cache or upgrade UPDATE overwrote reset | Invalidation, version/CAS |
| Login becomes much slower afterward | New cost too high and insufficient capacity | Benchmark, rate limiting |
| All users fail after changing encoder | Incompatible `{id}` format | Delegating/migration |
| First login works, second fails | Cached UserDetails erased | Defensive copy |
| Wrong password request modifies hash | Upgrade logic ran before matches | Upgrade only after successful authentication |

## 14. Self-check exercises

### A. Three APIs

A user has a bcrypt cost 6 hash, and the current encoder has strength 10. The user supplies the right password. What do `matches` and `upgradeEncoding` return respectively? Does calling `upgradeEncoding` alone update the DB?

**Answer:** `matches = true`; `upgradeEncoding = true`; the DB **does not change automatically**. You must encode the proven-correct raw password and persist the new hash.

### B. Why do two hashes differ?

Two encodes of the same password with bcrypt produce different strings. Does that mean the two passwords are different?

**Answer:** No. Random salt makes hashes differ, yet `matches` with the same raw password can still return true for both.

### C. Old hashes without raw passwords

A cron job wants to convert all cost 6 hashes to 10 using only the old hash data. Is this valid?

**Answer:** You cannot compute a valid hash for the original password without knowing the raw password. Upgrade on a valid login or require a reset via a secure mechanism.

### D. Missing wiring

If `provider.setUserDetailsPasswordService(accounts)` is removed from SecurityConfig, what changes?

**Answer:** DaoAuthenticationProvider no longer has a service to update the encoded hash via the automatic flow; legacy can still match, but the hash is not persisted. The legacy test catches this failure.

### E. Concurrent scenario

Login A matched the old password. Reset B changed the password. A proceeds to UPDATE the rehashed old password to the DB. What is the bug?

**Answer:** A can overwrite reset B, resurrecting the old password. Use conditional UPDATE/optimistic locking, versioning, and handle account state.

### F. Avoiding double encoding

In `UserDetailsPasswordService.updatePassword(user, newPassword)`, should you call `encoder.encode(newPassword)` again?

**Answer:** No. `newPassword` is an encoded string produced by the provider.

### G. Changing algorithms

Why is a plain BCryptPasswordEncoder unsuitable for matching both `{bcrypt}` and `{argon2}` simultaneously?

**Answer:** It only understands raw bcrypt hashes. Use DelegatingPasswordEncoder with configured IDs/encoders and an appropriate migration policy.

## 15. Application checklist

- [ ] Registration/change/reset: store only **encode(raw)**, never store plaintext.
- [ ] Login: use **matches(raw, storedHash)**, do not compare two encoded strings.
- [ ] Understand **upgradeEncoding(encoded)** only evaluates policy, does not authenticate or write to DB.
- [ ] Only upgrade the same password after **successful** authentication.
- [ ] If using DaoAuthenticationProvider auto-upgrade, attach UserDetailsPasswordService and PasswordEncoder properly.
- [ ] updatePassword saves the already-encoded hash, without double encoding.
- [ ] Benchmark current cost and plan a reasonable migration.
- [ ] Hash format in the store matches BCrypt or DelegatingPasswordEncoder and `{id}` prefixes.
- [ ] Protect concurrent password reset/change with version/CAS/transactions.
- [ ] UserDetails/cache do not share mutable objects that get erased; ensure invalidation.
- [ ] Test old/new logins, correct/wrong passwords, repeated requests, and password reset races.
- [ ] Do not log or return raw passwords, hashes, tokens, Authorization headers, or sensitive cookies.
- [ ] The system has HTTPS, rate limiting, appropriate CSRF policy, and a secure reset mechanism.

**Remember:** **encode** creates a hash for storage, **matches** checks a newly entered password against a stored hash, and **upgradeEncoding** indicates whether that hash should be modernized. When **DaoAuthenticationProvider + UserDetailsPasswordService** are integrated properly, the application can upgrade hashes **during valid logins** without changing the user's password, without modifying data on failed logins, and without overwriting a newly set password during concurrent changes.

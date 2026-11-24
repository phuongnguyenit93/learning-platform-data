# PasswordEncoder.encode and matches in Spring Security

## 1. The Practical Problem: Storing a Verifiable Password Without Saving the Original

A Java application has registration, password change, and login screens. At registration time, the user submits a **raw password**. The system needs to store a value it can verify on subsequent logins without writing the original password to the database.

Spring Security provides the **PasswordEncoder** interface. Its two most important methods are:

- **encode(rawPassword):** creates an **encoded password** to store in the credentials repository. For password-storage encoders such as BCrypt, the result is a one-way hash with a salt and a work factor.
- **matches(rawPassword, encodedPassword):** verifies whether the password the user just entered corresponds to the stored encoded password. Under normal conditions the method returns a boolean; an implementation may throw a format/algorithm error if the stored hash is invalid.

Flow:

~~~text
REGISTRATION / PASSWORD CHANGE
password entered by user
      |
      v
PasswordEncoder.encode(rawPassword)
      |
      v
password_hash in database

LOGIN
password entered by user + username
      |                        |
      |                        v
      |                 Read password_hash from DB
      |                        |
      +------------+-----------+
                   |
                   v
PasswordEncoder.matches(rawPassword, storedHash)
                   |
           +-------+-------+
           |               |
         true            false
           |               |
  continue auth       reject credentials
  and status checks
~~~

**PasswordEncoder uses “encode” in its API name, but for BCrypt/Argon2/PBKDF2/scrypt, this processes the password with a costly key derivation/hash function, not reversible encryption.** The system does not need to recover plaintext to log in. It only needs to verify the candidate password against the stored hash.

Article scope: **Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring MVC/Servlet**. Using Spring Security Crypto, you can practice without running a server; the full example below also demonstrates HTTP Basic, UserDetailsService, PasswordEncoder, and MockMvc. Any specific version used in production must still be supported and patched for security.

### Learning Outcomes

After this lesson, you will be able to explain:

1. What encode and matches accept/return, and the exact parameter order.
2. Why encoding the same password twice with BCrypt usually produces two different strings.
3. How salts, work factors, and one-way hashing affect password storage and verification.
4. When to use BCryptPasswordEncoder versus DelegatingPasswordEncoder.
5. What role the **{bcrypt}** prefix plays and why a hash missing a prefix can fail.
6. The role of PasswordEncoder in registration, login, password change, and hash migration.
7. How to use UserDetailsService/DaoAuthenticationProvider instead of comparing passwords manually in a Controller.
8. Common mistakes: double hashing, reversing matches arguments, String.equals comparisons, using {noop}, truncating database columns, leaking hashes in JSON/logs.
9. How to write tests verifying valid/invalid authentication with a runnable Spring Boot application.
10. How to read the upgradeEncoding signal and plan cost/algorithm changes without breaking accounts.

## 2. The PasswordEncoder Contract

The Spring Security interface has three key methods:

~~~java
public interface PasswordEncoder {

    String encode(CharSequence rawPassword);

    boolean matches(CharSequence rawPassword,
                    String encodedPassword);

    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
~~~

This is a **simplified contract shape for explanation**, not a file to redefine in your application. Depending on the version, signatures and nullability annotations may differ; import the real **org.springframework.security.crypto.password.PasswordEncoder**.

| Method | Input | Output | When to Use |
| --- | --- | --- | --- |
| **encode** | Raw password supplied by the user | String that can be stored for later verification | Registration, password change/reset, upgrading a hash after verification |
| **matches** | Candidate raw password; encoded password from storage | true/false when verification is valid | Login, checking the current password before changing it |
| **upgradeEncoding** | Stored encoded password | boolean indicating whether a new encoding should be used | Assessing cost/algorithm migration, combined with a hash update mechanism |

### 2.1. Argument Order for matches to Remember

~~~java
boolean valid = encoder.matches(
    rawPasswordFromLoginRequest,
    encodedPasswordFromDatabase
);
~~~

**The first argument is the raw password; the second argument is the stored hash/encoded password.** Reversing them will fail verification. The second parameter is not a “second password.”

During login using DaoAuthenticationProvider, Spring Security performs this comparison. A typical Controller **does not need to read the password hash and call matches itself** when username/password authentication is configured properly.

### 2.2. encode Does Not Guarantee Deterministic Output

With BCryptPasswordEncoder, a random salt is generated for each hash. Therefore:

~~~java
String first = encoder.encode("sample-pass");
String second = encoder.encode("sample-pass");

boolean firstMatches = encoder.matches("sample-pass", first);
boolean secondMatches = encoder.matches("sample-pass", second);
~~~

The result is **firstMatches=true** and **secondMatches=true**. **first** and **second** usually differ because of the salt. Do not write unit tests comparing a freshly generated hash string against a fixed hash literal unless you are specifically testing a controlled test vector.

Two outputs could coincidentally collide if the random salts collide, though the probability is extremely low; do not base application correctness on the assumption that two hashes are 100% guaranteed to differ on every run.

## 3. One-Way Hashes, Salts, and Work Factors

### 3.1. Why Not Store Plaintext?

If the user table has a password column holding the exact string entered by the user, a single database leak or exposed backup immediately reveals credentials that may be reused elsewhere.

Instead, password hashing is an intentionally **hard-to-reverse** computation. When the user logs in, the system does not “decrypt” the hash; it verifies the newly entered candidate using the corresponding algorithm and parameters.

**Hashing does not render a secret harmless.** If an attacker obtains the hash, they can still attempt offline password guessing. Therefore, you need an algorithm built for passwords, an appropriate cost parameter, restricted DB permissions, backup protection, and policies against weak passwords.

### 3.2. What Is a Salt Used For?

A salt is a random value accompanying each hash. With BCrypt, the salt is stored as part of the encoded password string. The same raw password with different salts produces different hashes. This makes it harder to spot users who share the same password and limits the usefulness of precomputed hash tables.

**A salt is not a secret** in the sense that it must be hidden separately for verification to work. Still, the password hash + salt must be protected as sensitive credential data. Do not invent your own separate salt-storage scheme or use a static username as a salt instead of a standard algorithm.

### 3.3. Work Factor / Cost

BCryptPasswordEncoder takes a **strength** parameter (log rounds). The higher the cost, the more work hashing and matches require, which slows down offline brute force. However, an overly high cost increases login latency, CPU load, and DoS risk if the endpoint lacks rate limiting.

Example:

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder(12);
~~~

This is an encoder creation snippet requiring the necessary imports and is **not a standalone Spring Boot file**. Choose the cost by benchmarking your hardware and load profile, rather than assuming 12 is always appropriate for every product. In Spring Security 6.3.x, the default BCryptPasswordEncoder() constructor uses strength 10; specific defaults can change across versions and wrappers.

### 3.4. Store the Full Hash String

Do not truncate the salt, prefix, or cost portion. If the database column is too short, the hash gets truncated, causing logins with the right password to fail.

A column such as **VARCHAR(255)** is usually large enough for many common formats like BCrypt with a {bcrypt} prefix, but you must check against your actual algorithm, upgrade needs, and database column limits. There is no single fixed length valid for every encoder or version.

## 4. BCryptPasswordEncoder: Basic Example

BCrypt is a password hashing algorithm with a salt and work factor. The **BCryptPasswordEncoder** class in Spring Security Crypto implements PasswordEncoder.

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder();

String storedHash = encoder.encode("hello-123");

boolean correct = encoder.matches("hello-123", storedHash);
boolean incorrect = encoder.matches("wrong-123", storedHash);
~~~

**correct=true**, **incorrect=false**. The exact hash depends on the salt, so no fixed hash string is listed as stdout.

### 4.1. Structure of a BCrypt String

A BCrypt hash typically starts with a form such as:

~~~text
$2a$10$...
~~~

Here, the version $2a$ (or a supported variant) and cost 10 live in the metadata; the remainder holds the salt and hash data. A typical BCrypt string is 60 characters long. The ellipsis is only a **structural placeholder**, not a real encoded password to pass into matches.

BCryptPasswordEncoder directly produces **$2a$...** strings, typically **without the {bcrypt} prefix**. If you switch to DelegatingPasswordEncoder later, you must handle stored formatting according to Delegating's conventions.

### 4.2. BCrypt Has an Input Length Limit

Traditional BCrypt considers only about the first **72 bytes** of password input. This is a byte limit, different from Unicode character count (Vietnamese characters can occupy multiple bytes in UTF-8). Some modern implementations handle long inputs differently, so verify the behavior of your exact library and version.

When designing a password policy, **do not silently truncate users' passwords to “make them fit.”** Choose byte-length rules and an algorithm deliberately, avoid two different long passwords being treated as identical due to truncation, consider Argon2id/scrypt/PBKDF2 when appropriate, and test with real Unicode inputs.

Do not pre-hash with SHA-256 and pass that into BCrypt without a reviewed design; chaining algorithms and encodings can introduce new compatibility and security risks.

### 4.3. Do Not Use encoder.encode to Compare Directly Against an Old Hash

Wrong approach:

~~~java
boolean wrongWay = encoder.encode(inputPassword)
    .equals(hashFromDatabase);
~~~

With BCrypt, encode generates a new salt, so the two strings normally differ even when the raw password is correct. Right approach:

~~~java
boolean rightWay = encoder.matches(
    inputPassword, hashFromDatabase
);
~~~

Also never call **encoder.matches(encoder.encode(inputPassword), storedHash)**. The first argument must be the **raw password**, not a newly generated hash.

## 5. DelegatingPasswordEncoder: Choosing the Algorithm by Prefix

An application running for many years may encounter hashes from different eras. Using a single BCryptPasswordEncoder directly forces custom code whenever you change algorithms or handle legacy hashes.

**DelegatingPasswordEncoder** is a wrapper that selects an encoder based on an **id** stored alongside the hash. Spring Security provides a factory:

~~~java
PasswordEncoder encoder =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();
~~~

With the standard factory configuration, newly encoded passwords usually take the form:

~~~text
{bcrypt}$2a$10$...
~~~

**{bcrypt}** is the encoder's id; the remainder is the BCrypt hash with salt/cost. This prefix is used for algorithm routing, not as an extra hashing layer.

### 5.1. General Format

~~~text
{id}encodedPassword
~~~

Example ids may include bcrypt, pbkdf2, scrypt, or argon2 depending on version/configuration. Do not assume legacy ids or weak algorithms are permitted to **encode new passwords**; supporting legacy reads should only be part of a controlled migration plan.

### 5.2. How Do encode and matches Work?

When calling encode:

1. DelegatingPasswordEncoder selects the encoder for writing new hashes via **idForEncode**, which is bcrypt in the standard factory.
2. The inner encoder generates a salted BCrypt hash.
3. The wrapper prepends the **{bcrypt}** prefix and returns the string for storage.

When calling matches:

1. The wrapper reads the id from the stored encoded password.
2. It looks up the corresponding encoder in the id → PasswordEncoder map.
3. It passes the **raw password** and the encoded password payload to that encoder for verification.
4. It returns true/false if the format and algorithm are supported.

### 5.3. Common Error: There is no PasswordEncoder mapped for the id null

If you use DelegatingPasswordEncoder while the database contains **unprefixed** BCrypt hashes—for instance starting directly with $2a$—the wrapper does not know which id should handle them. By default it may throw **IllegalArgumentException** with a message like “There is no PasswordEncoder mapped for the id null”.

The cause is not necessarily a wrong password. This is usually a **mismatch between the stored format and the configured PasswordEncoder**.

How to handle it depends on the data source:

- If you are certain all legacy records were created with BCrypt without a prefix, you can write a data migration **prepending the literal {bcrypt} to existing hashes**. Adding the id metadata does not require knowing raw passwords, because the BCrypt hash itself is unchanged.
- If the store holds multiple algorithms, classify the records and run a verified migration plan; do not blindly prepend {bcrypt} to everything.
- DelegatingPasswordEncoder offers **setDefaultPasswordEncoderForMatches** to set a fallback encoder when an id is unrecognized. Use this only in a controlled way for verified migrations—never fall back to NoOp or silently accept arbitrary invalid strings.
- After migration, test legacy and new users, column length, hash format, rollback, and monitor authentication error rates.

**Do not work around this by arbitrarily stripping {bcrypt} from new hashes** if the system uses DelegatingPasswordEncoder. Maintain a consistent storage convention.

### 5.4. Comparing the Two Options

| Feature | BCryptPasswordEncoder | DelegatingPasswordEncoder |
| --- | --- | --- |
| Algorithm for new writes | BCrypt directly | Determined by idForEncode, factory usually selects bcrypt |
| Typical stored string | $2a$... | {bcrypt}$2a$... |
| Verifying other legacy formats | Does not route automatically | Can map multiple ids/encoders |
| Upgrading algorithms | Requires a custom migration plan | Built-in foundation to encode with new hash and match old hashes |
| Risk when misconfigured | Inappropriate cost/format or prefix mismatch | Unknown id, unsafe fallback |
| Best suited for | Systems using a single controlled BCrypt format | Systems wanting versioned hashes and structured migration |

In the sample application in section 7, we choose **PasswordEncoderFactories.createDelegatingPasswordEncoder()** and use that same bean to create user hashes. That way both encode and matches understand the same prefix and algorithm.

## 6. Registration, Password Change, and Login Flows

### 6.1. Account Registration

The service receives the raw password after input validation, hashes it once, and stores it:

~~~java
String encoded = passwordEncoder.encode(rawPassword);
jdbcTemplate.update(
    "INSERT INTO app_users(username, password_hash) VALUES (?, ?)",
    normalizedUsername, encoded
);
~~~

This is a service snippet assuming a PasswordEncoder, JdbcTemplate, and a validated username; **it is not a complete registration endpoint**. A real application needs unique constraints, validation, transactions, email/phone verification as required, abuse protection, and safe responses.

The database stores **encoded**, never the raw password. Do not return the hash to the client as a “receipt” upon registration.

### 6.2. Login

DaoAuthenticationProvider retrieves the hash from UserDetailsService:

~~~text
login input (raw password)
    |
    v
DaoAuthenticationProvider
    |
    +-- UserDetailsService: load user with encoded password
    |
    +-- PasswordEncoder.matches(raw, storedEncoded)
    |
    +-- Account status checks
    |
    +-- Authentication success or failure
~~~

In standard Spring Security, the Controller does not call encode again on login and does not compare hashes itself. With form login, the filter/manager/provider already handles that when configured properly.

### 6.3. Changing Password When Current Password Is Known

A typical flow:

1. Verify the logged-in user, CSRF/session/re-authentication per policy.
2. Check the **current password** with matches if the operation requires it.
3. Validate the new password against policy and reuse rules if required.
4. Call **encode(newRawPassword)**.
5. Update the hash in the database using transactions and concurrency control.
6. Revoke/refresh sessions, tokens, or devices according to policy.
7. Never write the raw password, old hash, or new hash to logs, events, or responses.

**Do not hash a hash**: if code reads the old encoded password and calls encode(encodedOld), the user will no longer be able to log in with their old raw password. Only encode raw passwords legitimately submitted by the user.

### 6.4. Password Reset

With password reset, the user proves authorization via a single-use/TTL reset token rather than providing the old password. Once the token is verified, handle the new password as above: validate → encode → save hash → invalidate the reset token → consider revoking other sessions/tokens.

**PasswordEncoder does not handle reset-token security for you.** It only hashes passwords. Reset tokens must be unpredictable, stored and consumed once securely, and never leaked in logs or URL analytics.

## 7. Complete Spring Boot 3.x Example

### 7.1. Creating the Project

Use Spring Initializr to create a Java 17+, Spring Boot 3.x, Gradle Groovy DSL project with the Gradle Wrapper. Select **Spring Web** and **Spring Security** dependencies. In the dependencies block of **build.gradle**:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

This snippet shows the dependencies block in a Gradle project that already includes the Spring Boot plugin/BOM and Java toolchain; it is not a standalone full build.gradle file. The app uses in-memory demo users to focus on PasswordEncoder without needing a database.

### 7.2. Java File

Create **src/main/java/com/example/password/PasswordDemoApplication.java**:

~~~java
package com.example.password;

import java.security.Principal;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class PasswordDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PasswordDemoApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
            .createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("learner")
                .password(encoder.encode("demo-only-123"))
                .roles("LEARNER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-only-123"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    CommandLineRunner passwordLab(PasswordEncoder encoder) {
        return args -> {
            String hash = encoder.encode("local-example");

            System.out.println(
                "prefix bcrypt: " + hash.startsWith("{bcrypt}"));
            System.out.println(
                "correct: " + encoder.matches("local-example", hash));
            System.out.println(
                "wrong: " + encoder.matches("not-the-password", hash));
        };
    }
}

@RestController
class DemoEndpoints {

    @GetMapping("/public")
    String publicEndpoint() {
        return "public OK";
    }

    @GetMapping("/me")
    String me(Principal principal) {
        return "hello " + principal.getName();
    }

    @GetMapping("/admin")
    String adminEndpoint() {
        return "admin OK";
    }
}
~~~

This is **a complete Java file placed in a Boot project**: public class PasswordDemoApplication matches the filename, and DemoEndpoints is a package-private class in the same package. Spring Boot component scan discovers the Controller. The file uses APIs available in Java 17 and Spring Security 6.x.

### 7.3. What Each Part Does

- **passwordEncoder()** creates a DelegatingPasswordEncoder bean. New hashes from the standard factory typically carry the {bcrypt} prefix.
- **users(...)** calls **encode** when seeding users, then stores the encoded passwords in InMemoryUserDetailsManager. No plaintext passwords are stored in UserDetails.
- **security(...)** enables HTTP Basic, configures /public as public, /me as authenticated, and /admin as requiring ROLE_ADMIN. All other URLs use denyAll.
- **passwordLab(...)** runs a quick check on startup without logging raw passwords or hashes. It only prints boolean results and prefix recognition.
- **DemoEndpoints** only reads Principal.getName and never returns the entire Authentication or UserDetails.

Literal passwords are **for local demo use only**. Production needs a persistent user store and dedicated credential processes; never hardcode demo passwords in source deployed to real environments.

### 7.4. Running and Deterministic Output

From the Gradle Wrapper directory:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell, use **.\gradlew.bat bootRun**.

Aside from Spring Boot startup logs, the three lines printed by CommandLineRunner will show:

~~~text
prefix bcrypt: true
correct: true
wrong: false
~~~

**There is no fixed hash in stdout**, because BCrypt generates a random salt. The output above follows the article's DelegatingPasswordEncoder factory and does not depend on a specific hash.

Assuming the app listens on default port 8080:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u learner:demo-only-123 http://localhost:8080/me
curl -i -u learner:wrong http://localhost:8080/me
curl -i -u learner:demo-only-123 http://localhost:8080/admin
curl -i -u admin:admin-only-123 http://localhost:8080/admin
~~~

In PowerShell, use **curl.exe** when curl is an alias. Over real networks, **HTTP Basic requires HTTPS/TLS**; Base64 does not secure passwords. To avoid placing passwords in shell history, run **curl -i -u learner URL** and enter the password when prompted.

### 7.5. Expected HTTP Results

| Request | Expected Status | Why |
| --- | --- | --- |
| GET /public anonymous | **200**, public OK | permitAll |
| GET /me anonymous | **401** | HTTP Basic requires authentication |
| GET /me learner right password | **200**, hello learner | Provider uses matches and authenticates successfully |
| GET /me learner wrong password | **401** | matches fails |
| GET /admin learner right password | **403** | User is authenticated but lacks ROLE_ADMIN |
| GET /admin admin right password | **200**, admin OK | Has ROLE_ADMIN |

These are **expectations based on the code**, not output from a server executed inside this document. HTTP 401/403 responses are affected by AuthenticationEntryPoint, filters/handlers, and other customizations if present in a real app.

**Key takeaway:** In the application, you only see **encode when creating accounts**, and never see the Controller call matches. The matches check is performed by DaoAuthenticationProvider after the HTTP Basic filter passes credentials to AuthenticationManager.

### 7.6. A Public Endpoint Can Still Return 401 on Invalid Credentials

permitAll does not disable BasicAuthenticationFilter. If a client deliberately sends an Authorization: Basic header with the wrong password to /public, the filter may still attempt credential verification and return 401 before permitAll authorization is evaluated. That does not mean the public endpoint turned private.

## 8. Automated Testing for encode/matches and HTTP Basic

Create **src/test/java/com/example/password/PasswordDemoApplicationTest.java**:

~~~java
package com.example.password;

import java.nio.charset.StandardCharsets;
import java.util.Base64;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PasswordDemoApplicationTest {

    @Autowired PasswordEncoder encoder;
    @Autowired UserDetailsService users;
    @Autowired MockMvc mvc;

    private String basic(String username, String rawPassword) {
        String pair = username + ":" + rawPassword;
        String encodedPair = Base64.getEncoder().encodeToString(
            pair.getBytes(StandardCharsets.UTF_8));
        return "Basic " + encodedPair;
    }

    @Test
    void encodeCreatesStoredHashThatMatchesOnlyCorrectPassword() {
        String hash1 = encoder.encode("local-secret");
        String hash2 = encoder.encode("local-secret");

        assertTrue(hash1.startsWith("{bcrypt}"));
        assertTrue(hash2.startsWith("{bcrypt}"));
        assertTrue(encoder.matches("local-secret", hash1));
        assertTrue(encoder.matches("local-secret", hash2));
        assertFalse(encoder.matches("different", hash1));
    }

    @Test
    void storedUserPasswordIsEncoded() {
        String stored = users.loadUserByUsername("learner")
            .getPassword();

        assertTrue(stored.startsWith("{bcrypt}"));
        assertTrue(encoder.matches("demo-only-123", stored));
        assertFalse(encoder.matches("wrong", stored));
    }

    @Test
    void loginAndAuthorizationAreSeparate() throws Exception {
        mvc.perform(get("/me")
                .header(HttpHeaders.AUTHORIZATION,
                    basic("learner", "demo-only-123")))
            .andExpect(status().isOk())
            .andExpect(content().string("hello learner"));

        mvc.perform(get("/me")
                .header(HttpHeaders.AUTHORIZATION,
                    basic("learner", "wrong")))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/admin")
                .header(HttpHeaders.AUTHORIZATION,
                    basic("learner", "demo-only-123")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin")
                .header(HttpHeaders.AUTHORIZATION,
                    basic("admin", "admin-only-123")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin OK"));
    }
}
~~~

All assertions verify the **contract** rather than comparing a hash against a hardcoded string. The first test intentionally does not assert that two hashes must strictly differ, because of the random salt; what matters is that **both hashes match the same raw password** while a wrong password does not match.

Run:

~~~bash
./gradlew test
~~~

On PowerShell use **.\gradlew.bat test**.

This is a complete test file in a Boot project with spring-boot-starter-test. MockMvc builds the Basic header directly, so spring-security-test is not required merely to send HTTP Basic requests in this lesson. Always verify namespaces and versions when integrating into another project.

**These examples and tests are written against the API and have not been executed inside this article itself.** In a real system, run the build/tests to verify dependency versions and results in your specific environment.

## 9. upgradeEncoding: When Should a Hash Be Regenerated?

Password hashing parameters and algorithms may need to change over time. The PasswordEncoder interface includes **upgradeEncoding(encodedPassword)**, which returns true when the implementation judges the current hash should be upgraded. The default implementation returns false; some encoders like BCrypt/DelegatingPasswordEncoder implement custom logic.

This **does not automatically replace the hash in the database**. It is only a signal.

### 9.1. Safe Hash Upgrade Flow

Once an application has successfully verified a user, it can:

~~~java
boolean valid = encoder.matches(rawPassword, storedHash);

if (valid && encoder.upgradeEncoding(storedHash)) {
    String upgraded = encoder.encode(rawPassword);
    accountRepository.updatePasswordHash(userId, upgraded);
}
~~~

This is a logic snippet inside a service that already has an encoder, repository, userId, and safely handled raw password; **it is not a standalone runnable file**.

Key points:

1. Only rehash after the raw password has been verified as correct.
2. Rehash the **raw password**, never encode the old hash.
3. Save the new hash transactionally and guard against concurrent password changes.
4. Never log the old or new hash.
5. When changing/updating credentials, consider token/session revocation.
6. Ensure the old hash format is recognized by the encoder for matches before attempting an upgrade.

In the DaoAuthenticationProvider architecture, **UserDetailsPasswordService** integrates to update the encoded password after authentication when configured compatibly. Configure and test that mechanism; do not assume merely declaring a PasswordEncoder bean will automatically upgrade every old hash in the database.

### 9.2. You Cannot Bulk-Change Algorithms Without Raw Passwords

From a BCrypt hash, you cannot extract the raw password and immediately convert it to Argon2id. Safely upgrading algorithms normally requires **waiting for a valid login** to rehash the verified raw password, or forcing a password change through a verified flow.

Only when changing the id metadata of the **same known algorithm/format**—for example prepending {bcrypt} before a raw BCrypt hash—can a format migration be done without raw passwords. That differs from migrating to a new hashing algorithm.

## 10. Comparing Password Hashing Algorithms

| Algorithm/Encoder | Characteristics | Notes |
| --- | --- | --- |
| **BCryptPasswordEncoder** | Password hashing with salt/cost; widely used | Cost must be benchmarked; note input bytes/72-byte limit |
| **Argon2PasswordEncoder** | Memory-hard password hashing, typically Argon2id by configuration | Requires appropriate dependencies/parameters/memory for the version |
| **SCryptPasswordEncoder** | Memory-hard key derivation | Tune CPU/memory cost operationally |
| **Pbkdf2PasswordEncoder** | Based on PBKDF2 with iterations, salt, and hash parameters | Choose sufficiently strong parameters; fits certain compliance environments |
| **DelegatingPasswordEncoder** | Wrapper selecting encoder by prefix id | Manage id map, default behavior, and legacy migration |
| **NoOpPasswordEncoder** | No password protection; plaintext comparison | **Never use in production** |
| **MessageDigestPasswordEncoder/Plain SHA** | Legacy methods that may lack proper work factors | Do not choose for new passwords; plan migration |

Spring Security includes multiple encoders to support compatibility and migration. **The existence of an encoder does not mean its algorithm is suitable for new passwords.** For modern password storage, use a dedicated password algorithm with tunable cost and consult current security recommendations.

### 10.1. Must Every Application Use BCrypt Specifically?

No. BCrypt is a pragmatic choice in many systems, while Argon2id, scrypt, or PBKDF2 also have valid use cases. Choose based on threat model, library/version, infrastructure support, and benchmarks—not guesswork about “which algorithm is always strongest.”

Whichever encoder you choose, **rate limiting, MFA where appropriate, secret handling, and database access controls** must still be designed. Slow hashing protects against offline guessing but does not stop online guessing against your login API by itself.

## 11. Common Spring Security Configuration Mistakes

### 11.1. Stored Password Has {bcrypt} While the Bean Is a Plain BCryptPasswordEncoder

If the database contains strings starting with **{bcrypt}$2a$...** while the bean is **new BCryptPasswordEncoder()**, matches may reject the prefix because BCryptPasswordEncoder directly expects BCrypt strings starting with $2a/$2b/$2y.

**Fix:** Use a prefix-compatible DelegatingPasswordEncoder, or perform an explicit format migration. Never bypass the error by storing plaintext.

### 11.2. Stored Password Lacks an id While the Bean Is DelegatingPasswordEncoder

The error typically reads “There is no PasswordEncoder mapped for the id null”. Check which legacy encoder produced the unprefixed hashes; decide on migration based on the actual data origin. Do not prepend {bcrypt} to hashes produced by a different algorithm.

### 11.3. DaoAuthenticationProvider Reports Wrong Password Even Though the User Is Sure It Is Right

Possible causes include:

- The raw password input was trimmed, normalized, or otherwise altered before matches.
- The database stores truncated hashes due to a short column.
- Different environments use different encoders, versions, costs, or formats.
- The database stores double-hashed passwords.
- UserDetailsService loads the wrong account or returns a value from a different column.
- A custom salt/pepper changed without versioning.
- Long Unicode inputs differ at the byte level.
- A profile/config/AuthenticationManager is using a different UserDetailsService than expected.

Never fix this by disabling password checks. Debug via **format/length/algorithm id and safe error categories**, and never print raw passwords or full hashes to logs.

### 11.4. Using User.withDefaultPasswordEncoder in Production

Some Spring Security samples include a convenience helper for quick demos. That helper must not be used for real password storage. Provide a secure PasswordEncoder bean and call encode when creating accounts.

### 11.5. Using {noop} to Fix “id null”

{noop} is the format for an encoder that performs no hashing, existing mainly for compatibility/demonstration. It is not a format fix for BCrypt. Storing "{noop}password" lets anyone with DB read access see passwords in the clear. Never use it in production.

### 11.6. Generating Hashed Passwords Manually and Hardcoding Them in Source

Fixed hashes may be used for test fixtures or controlled migrations, but production should go through registration/password-change flows and managed secret sources. Never commit sample accounts with usable passwords into real production builds.

### 11.7. Comparing with String.equals in the Controller Layer

With BCrypt, hashes differ due to salts; moreover, Controllers should not perform authentication themselves when Spring Security is already in place. Let DaoAuthenticationProvider call matches per contract; business endpoints receive the framework-verified Principal/Authentication.

### 11.8. Allowing DB Login Without Checking Account Status

A valid password does not mean an account is permitted to operate. DaoAuthenticationProvider also checks enabled, locked, expired, and implemented flags. Custom providers must not skip these checks.

### 11.9. Leaking Hashes via Authentication, UserDetails, or JSON

UserDetails typically exposes getPassword() for the provider. However, Controllers should never return UserDetails, Authentication, or a JPA entity containing password_hash. Use response DTOs with only the needed fields. A leaked password hash can still be brute-forced offline.

### 11.10. Ignoring Timing Differences

If you write custom auth code and return immediately when a username is missing, the user-not-found branch may finish faster than the branch executing BCrypt.matches; this creates a **user enumeration** channel. Use up-to-date patched providers, apply rate limits, and test locked/disabled states per security advisories. Do not assume returning the same HTTP 401 eliminates all timing side channels.

## 12. Handling Passwords and Sensitive Data Across Layers

| Location | What to Do | What to Avoid |
| --- | --- | --- |
| HTTP login request | Receive password over HTTPS, validate input | Passing it in URL/query or logging request bodies |
| Registration/password service | Call encode and store the hash | Saving raw passwords or returning hashes to clients |
| UserDetailsService | Load encoded password along with authorities/flags | Authenticating via string comparison itself |
| DaoAuthenticationProvider | Use matches to verify credentials | Trusting client-asserted roles |
| SecurityContext/Principal | Hold authenticated identity/authorities | Serializing passwords/hashes/tokens to APIs |
| Database | Protect password_hash, proper indexing/uniqueness | Overly short columns, unprotected backups |
| Logs/tracing | Request ID, safe error categories | Authorization headers, cookies, raw passwords, hashes |
| Password reset | Single-use token + encode(new password) | Resending old passwords or logging tokens |
| Hash migration | Verify, upgrade, and audit | Changing encoders without checking all legacy hashes |

### 12.1. Do Not Store Raw Passwords in Long-Lived Java Fields

In Servlets or the JVM, a raw password may briefly reside in a String/buffer during authentication. That does not mean you should keep it in entities, sessions, static fields, caches, or events. Minimize scope, lifetime, and logging touchpoints.

With Java Strings, immediate erasure of every copy from the heap cannot be guaranteed. Design credential flows to avoid long-lived copies, protect memory dumps, and prefer vetted APIs/libraries.

### 12.2. A Password Hash Is Not Authorization

A matching password only verifies account credentials. Authorization must still check ROLE_USER/ROLE_ADMIN, ownership, tenant, business state, and re-authentication/MFA for sensitive operations. PasswordEncoder does not decide whose records a user may read.

## 13. Verification Checklist in a Real Project

When implementing a PasswordEncoder, verify:

1. encode(raw) produces a string in the expected format, not the raw password.
2. matches(raw, encode(raw)) returns true.
3. matches(wrong, encode(raw)) returns false.
4. Raw passwords with Unicode, special characters, and length boundaries behave per policy.
5. The same password normally produces two distinct salted hashes, and **both verify successfully**.
6. Database columns are wide enough and never truncate hashes or prefixes.
7. Legacy hashes/formats are handled cleanly or fail migration explicitly.
8. The PasswordEncoder bean is actually used by the provider, with no stray encoder in other environments.
9. On login, valid input yields 200 and invalid input yields 401 per Basic policy.
10. A user with the right password but missing role receives 403, not confused with an invalid password.
11. Disabled/locked accounts cannot log in merely because the password matches.
12. When changing passwords, the new hash matches and the old hash is no longer valid.
13. When upgradeEncoding returns true, the upgrade flow stores the new hash with proper concurrency/revocation handling.
14. Raw passwords and hashes are never exposed in logs, responses, tracing, or exceptions.
15. Rate limits, brute-force defenses, password reset tokens, and version-specific security advisories are tested.

### 13.1. Test Design Tips

You do not need to assert an entire BCrypt hash string against a literal. For salted password hashing, test the invariants: valid format, correct true/false matches, and compatibility after persistence round-trips. Performance cost benchmarks should run separately in a controlled environment rather than setting rigid millisecond thresholds on varied CI machines.

## 14. Self-Check Questions

**Question 1.** When is encode("abc") used?  
**Answer:** When creating an encoded password for storage, such as during registration or password change.

**Question 2.** In what order does matches accept its two parameters?  
**Answer:** Raw password first, stored encoded password second.

**Question 3.** Why can encoding the same password twice produce two different strings?  
**Answer:** Because of the random salt in password hashing algorithms such as BCrypt.

**Question 4.** Should you compare encode(raw).equals(storedHash)?  
**Answer:** No, because the new hash uses a different salt. Use matches(raw, storedHash).

**Question 5.** Does matches decrypt the hash to recover the original password?  
**Answer:** No. It verifies the raw candidate against the algorithm and metadata of the stored hash.

**Question 6.** Do a standalone BCryptPasswordEncoder and DelegatingPasswordEncoder use the same storage format?  
**Answer:** Not necessarily. Direct BCrypt usually stores $2a$..., whereas the Delegating factory usually stores {bcrypt}$2a$....

**Question 7.** What does an “id null” error when using DelegatingPasswordEncoder suggest?  
**Answer:** The stored hash lacks an encoder id prefix or has an incompatible format.

**Question 8.** Can you simply prepend {bcrypt} to a valid legacy BCrypt hash?  
**Answer:** Yes, once you have confirmed with certainty that the hash is BCrypt; this only adds id metadata and does not change the algorithm.

**Question 9.** Why must {noop} never be used in production?  
**Answer:** It provides no password protection; stored values can be plaintext.

**Question 10.** Which components does DaoAuthenticationProvider use to check passwords?  
**Answer:** UserDetailsService loads the hash and PasswordEncoder.matches verifies the raw password.

**Question 11.** Does upgradeEncoding automatically update the database column?  
**Answer:** No. It is only a signal; you need an update mechanism after verifying the raw password.

**Question 12.** Why can’t you extract raw passwords from BCrypt hashes to bulk-convert them to Argon2?  
**Answer:** Password hashing is one-way; you need the raw password during a valid authentication or password-change flow.

**Question 13.** Is a higher BCrypt strength unconditionally better?  
**Answer:** No. You must balance offline attack resistance, latency, CPU usage, and online DoS risk.

**Question 14.** If the password is right yet accessing an admin URL still returns 403, is the encoder broken?  
**Answer:** Not necessarily. Authentication succeeded, but authorization lacks ROLE_ADMIN.

**Question 15.** Should password hashes be logged to debug login issues?  
**Answer:** No. Hashes are sensitive data that can be attacked offline if leaked.

## 15. Official References

- Spring Security — Password Storage and DelegatingPasswordEncoder: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Spring Security — PasswordEncoder API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/crypto/password/PasswordEncoder.html
- Spring Security 6.3 — BCryptPasswordEncoder API: https://docs.spring.io/spring-security/site/docs/6.3.x/api/org/springframework/security/crypto/bcrypt/BCryptPasswordEncoder.html
- Spring Security — Cryptography and PasswordEncoder: https://docs.spring.io/spring-security/reference/features/integrations/cryptography.html
- Spring Security — Username/Password Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/
- Spring Security — DaoAuthenticationProvider: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security — UserDetailsService: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html

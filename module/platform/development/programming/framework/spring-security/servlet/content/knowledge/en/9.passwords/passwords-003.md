# DelegatingPasswordEncoder and Prefix-Tagged Storage Format

## Objectives and Context

When a Spring Security Servlet application manages accounts with passwords, it should not store plaintext passwords and should not manually compare password strings against values in the database. Spring Security provides the `PasswordEncoder` interface to store values hashed with an appropriate algorithm, verify passwords on login, and support upgrading storage formats over time.

**DelegatingPasswordEncoder** is a `PasswordEncoder` implementation that enables **a storage format containing an algorithm identifier prefix**; as a result, old and new data can coexist during a transition period while the application still knows which encoder to use for verification. The core of this lesson is understanding the exact role of the prefix, how an encoder is chosen for new saves, and how one is chosen for verifying stored data.

After studying this lesson, you will know:

- The exact syntax of the stored password string: **{id}encodedPassword** and the meaning of each part.
- The difference between `encode(rawPassword)`, `matches(rawPassword, storedPassword)`, and `upgradeEncoding(storedPassword)`.
- Which encoder `DelegatingPasswordEncoder` selects to **newly encode** and which encoder it selects to **verify old hashes**.
- The role of `PasswordEncoderFactories.createDelegatingPasswordEncoder()`, `idForEncode`, and the `id → PasswordEncoder` mapping table.
- How to handle strings without a prefix, unrecognized prefixes, legacy data, and the risks of using a fallback encoder.
- How to build a runnable Java 17+ example with Spring Boot 3.x/Spring Security 6.x and write tests with deterministic output.
- How to implement hash upgrades during login without forcing users to change their passwords immediately.

Context: Spring Security 6.x on the **Servlet stack**, Java 17+, though the `PasswordEncoder` mechanism lives in the password management layer and can be used independently of web filters. Examples with Spring Boot versions are explicitly noted to avoid confusing syntax from older versions.

## 1. What problem does PasswordEncoder solve?

The core interface (an illustration of the public signature, not the full library source):

~~~java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);

    boolean matches(CharSequence rawPassword, String encodedPassword);

    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
~~~

The three operations have distinct responsibilities:

1. **encode(rawPassword)**: produces an encoded/hashed value for **storage**. With an algorithm suitable for passwords, a single input can produce different outputs due to random salt.
2. **matches(rawPassword, encodedPassword)**: receives the password just entered by the user and the stored string. The method returns true/false after using the appropriate encoder; it **does not decrypt the hash** to retrieve the original password.
3. **upgradeEncoding(encodedPassword)**: indicates whether the stored string needs to be converted to the current encoding or a stronger configuration. It only makes a decision; it **does not automatically update the database**.

A typical account record:

~~~text
username       password_hash
------------   ---------------------------------------------------
alice          {bcrypt}$2a$10$...<valid hash and salt characters>...
bob            {argon2@SpringSecurity_v5_8}...<valid value>...
~~~

The ellipses are only **structural illustrations**, not valid hashes to pass directly into `matches()`. Never treat an example containing ellipses as a test value.

**Security goal:** password hashing must be designed for password storage (with salt and an appropriate work factor/computational cost), not raw SHA-256/MD5 alone. Even strong passwords still need brute-force protections, rate limiting, MFA when appropriate, HTTPS transport, and database protection.

## 2. The {id}encodedPassword format

A string stored by `DelegatingPasswordEncoder` typically has the form:

~~~text
{id}encodedPassword
~~~

Explanation:

- The opening/closing curly braces act as the prefix delimiter.
- **id** is the identifier string of the encoder registered in `DelegatingPasswordEncoder`, for example `bcrypt`.
- **encodedPassword** is the output returned by the corresponding encoder; it may internally include salt, cost, algorithm parameters, or internal version info.
- The entire **{id}encodedPassword** value is stored in the `password_hash` column. Do not strip the prefix before saving or before calling `DelegatingPasswordEncoder.matches()`.

Example structure of a bcrypt hash:

~~~text
{bcrypt}$2a$10$xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
|      | | |  |
|      | | |  +-- bcrypt salt/hash payload (illustrative, not for real use)
|      | | +----- bcrypt cost inside the bcrypt string (e.g. 10)
|      | +------- start of the bcrypt format: $2a$
|      +--------- hash string portion from the selected encoder
+---------------- id prefix used by DelegatingPasswordEncoder
~~~

**The `{bcrypt}` prefix is not a salt**, not a secret, and does not by itself make the hash stronger. It is **routing metadata** so the application knows which `PasswordEncoder` implementation must process `encodedPassword`. The bcrypt algorithm still embeds its own salt/cost into the bcrypt hash string.

A few id forms you may encounter (the set of ids supported by the factory and parameter versions can change across Spring Security versions):

| Stored string form | Meaning |
| --- | --- |
| `{bcrypt}$2a$...` | Hashed with `BCryptPasswordEncoder`; the bcrypt part contains salt and cost |
| `{pbkdf2}...` | String generated by the PBKDF2 encoder corresponding to id `pbkdf2` |
| `{pbkdf2@SpringSecurity_v5_8}...` | Dedicated ID for a specific PBKDF2 configuration version |
| `{scrypt}...` | String generated by the corresponding `SCryptPasswordEncoder` |
| `{argon2@SpringSecurity_v5_8}...` | A versioned ID for an Argon2 encoder |
| `{noop}literal-password` | Legacy/test plaintext data, **must not be used to store new passwords in production** |

Do not assume every factory in every version registers the exact same set of ids in the table; always check the Spring Security version and actual mapping. If a database column stores `{bcrypt}...`, the id itself is "bcrypt", **not** "$2a$" or "10". Those components belong inside bcrypt's `encodedPassword`.

Do not add two prefixes to the same record, such as `{bcrypt}{bcrypt}$2a$...`, or strip the `{bcrypt}` part when calling `DelegatingPasswordEncoder.matches()`. Both can cause verification to fail.

## 3. Two directions: encode and matches

Imagine the constructor:

~~~java
DelegatingPasswordEncoder encoder =
        new DelegatingPasswordEncoder("bcrypt", encoders);
~~~

Where `encoders` is a pre-supplied `Map<String, PasswordEncoder>` containing an entry with key `bcrypt`.

### When saving a new password: encode

~~~text
rawPassword
     |
DelegatingPasswordEncoder.encode(rawPassword)
     |
idForEncode = "bcrypt"
     |
encoders.get("bcrypt").encode(rawPassword)
     |
returns "{bcrypt}" + encodedValue
     |
store the full string in password_hash
~~~

**idForEncode** specifies the primary encoder for **new passwords**; it does not force old passwords with other ids to change immediately. If you want all new passwords to move to a new algorithm/configuration, you change `idForEncode` and the appropriate mapping; you can still keep old mappings for `matches()`.

### When logging in: matches

~~~text
newly entered password + stored password_hash
     |
DelegatingPasswordEncoder.matches(raw, "{id}encoded")
     |
read id between { and }
     |
look up encoders.get(id)
     |
delegate.matches(raw, encoded)
     |
true or false
~~~

At this step, **the id in the record itself** decides which encoder is selected. Never use `idForEncode` to check all old data, because that breaks compatibility with prior-generation hashes.

A valid verification:

~~~java
String stored = passwordEncoder.encode("ForLocalDemo#2026");
boolean correct = passwordEncoder.matches("ForLocalDemo#2026", stored);
boolean wrong   = passwordEncoder.matches("incorrect", stored);
~~~

With a properly configured encoder, `correct` is true and `wrong` is false. You cannot predict the full `stored` string because of the random salt; do not compare two `encode(raw)` calls with `String.equals()` to verify a password.

## 4. Using Spring Security's built-in factory

Common starting approach:

~~~java
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

PasswordEncoder passwordEncoder =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();
~~~

This snippet must be placed in an appropriate Java class/method with `spring-security-crypto` on the classpath. In typical Spring Security 6 configurations, the factory creates a `DelegatingPasswordEncoder`, uses **bcrypt as `idForEncode`**, and includes mappings for methods supporting legacy data compatibility. Do not interpret the factory as automatically scanning and guessing hash types from string shape when no prefix is present: verification relies on the declared id.

Example of saving a new password using the factory:

~~~text
raw = "ForLocalDemo#2026"
encoded = passwordEncoder.encode(raw)
encoded usually starts with "{bcrypt}$2a$..." or an equivalent valid bcrypt format
passwordEncoder.matches(raw, encoded) == true
~~~

The strings in the example only describe expected results; the actual hash varies by salt. In the default factory, the set of encoders/ids may include older methods for the purpose of **reading and migrating legacy data**—it does not mean methods like `noop`, MD5, or plain SHA-256 are recommended for new password storage.

### Distinguishing the factory from DelegatingPasswordEncoder itself

- `PasswordEncoderFactories.createDelegatingPasswordEncoder()` is a **convenience method** that creates a `DelegatingPasswordEncoder` with default mappings for that version.
- `DelegatingPasswordEncoder` is the **dispatch mechanism** based on id that allows custom mappings and `idForEncode`.
- `BCryptPasswordEncoder` is **a concrete encoder**, which can be used directly, though when used directly it will not prepend the `{bcrypt}` prefix.
- If you previously used `BCryptPasswordEncoder` directly to save passwords, the DB may contain only `$2a$...` without `{bcrypt}`. After switching to `DelegatingPasswordEncoder`, that data needs an explicit migration strategy instead of assuming it will still match.

## 5. Complete, runnable Java 17+ example

To focus on hashing/verification, we build a command-line Spring Boot application, **without needing HTTP endpoints**. It still uses the exact Spring Security `PasswordEncoder` that Servlet applications typically use. Integration with Servlet login will be explained later.

Example Spring Boot 3.3.x project (Gradle Groovy DSL, Java 17). Another compatible Spring Boot project can be used if the plugin/dependency versions are updated accordingly.

### 5.1. File structure

~~~text
password-encoder-lab/
  settings.gradle
  build.gradle
  gradlew / gradlew.bat (if the project has a Gradle wrapper)
  src/main/java/dev/example/passwords/
    PasswordEncodingDemoApplication.java
  src/test/java/dev/example/passwords/
    PasswordEncodingDemoApplicationTest.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'password-encoder-lab'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
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
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

File `src/main/java/dev/example/passwords/PasswordEncodingDemoApplication.java`:

~~~java
package dev.example.passwords;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

@SpringBootApplication
public class PasswordEncodingDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PasswordEncodingDemoApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    CommandLineRunner runPasswordDemo(PasswordEncoder encoder) {
        return args -> {
            String raw = "ForLocalDemo#2026";
            String stored = encoder.encode(raw);

            System.out.println("prefix=" + stored.startsWith("{bcrypt}"));
            System.out.println("correct=" + encoder.matches(raw, stored));
            System.out.println("wrong=" + encoder.matches("not-the-password", stored));

            String oldNoopValue = "{noop}legacy-test-only";
            System.out.println("legacyMatches="
                    + encoder.matches("legacy-test-only", oldNoopValue));
            System.out.println("needsUpgrade="
                    + encoder.upgradeEncoding(oldNoopValue));
        };
    }
}
~~~

This is **complete Java code for an application in a project with dependencies already configured**, with no need to register a `SecurityFilterChain` because the exercise focuses on `PasswordEncoder` and does not open an HTTP server. The `raw` and `{noop}` strings are dummy data for learning purposes and must not be used as real passwords.

Run in the directory with the Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell you can use:

~~~powershell
./gradlew.bat bootRun
~~~

Lines printed by the application (Spring Boot may print additional banners/logs, and log line order may vary by environment):

~~~text
prefix=true
correct=true
wrong=false
legacyMatches=true
needsUpgrade=true
~~~

Why are the above values deterministic?

- The factory uses bcrypt for new encodes, so the stored string starts with `{bcrypt}`.
- `matches()` invokes the right bcrypt encoder with the entered password so it returns true; the wrong password returns false.
- The default factory allows checking legacy `{noop}` data to support migration, so `oldNoopValue` is verified against the literal value.
- `upgradeEncoding("{noop}...")` is true because the record's id differs from the current `idForEncode` (bcrypt).

**Never print `stored` or `raw` values to production logs**; the demo only prints boolean results. Across multiple runs, bcrypt hashes for the same raw password usually differ due to random salt, yet each hash still verifies the right raw password.

### 5.2. Testing with JUnit 5

File `src/test/java/dev/example/passwords/PasswordEncodingDemoApplicationTest.java`:

~~~java
package dev.example.passwords;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class PasswordEncodingDemoApplicationTest {

    @Autowired
    PasswordEncoder encoder;

    @Test
    void newHashesCarryAlgorithmPrefixAndMatchRawPassword() {
        String raw = "ForLocalDemo#2026";
        String stored = encoder.encode(raw);

        assertThat(stored).startsWith("{bcrypt}");
        assertThat(encoder.matches(raw, stored)).isTrue();
        assertThat(encoder.matches("bad-password", stored)).isFalse();
    }

    @Test
    void legacyNoopCanBeReadButRequiresUpgrade() {
        String stored = "{noop}legacy-test-only";

        assertThat(encoder.matches("legacy-test-only", stored)).isTrue();
        assertThat(encoder.upgradeEncoding(stored)).isTrue();
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

The test suite does not compare against a hardcoded bcrypt hash, so it will not fail due to changing salts. To test return values, assert only the prefix along with the appropriate `matches`/`upgradeEncoding` results. **The existence of the `{noop}` mapping in the factory is for compatibility, not advice to store plaintext.**

### 5.3. Why not run javac on a single file?

Classes such as `PasswordEncoderFactories`, `PasswordEncoder`, `@SpringBootApplication`, and JUnit come from libraries outside the JDK. Therefore, a standalone `javac PasswordEncodingDemoApplication.java` command will fail without providing the full classpath. This example needs a build tool to load the right dependencies; using `bootRun`/`test` as above is a transparent, reproducible way. The same encoder can be deployed in a real Servlet application without changing the `encode`/`matches` contract.

## 6. Choosing your own id and encoder list

The default factory is convenient for general-purpose systems, but a project may want a higher work factor or to define the exact set of accepted algorithms. `DelegatingPasswordEncoder` lets you pass **`idForEncode` and a `Map`**.

Example Bean in a Spring `@Configuration` class (method code with imports, not a standalone runnable program):

~~~java
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.DelegatingPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration
class PasswordPolicyConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        Map<String, PasswordEncoder> encoders = Map.of(
                "bcrypt", new BCryptPasswordEncoder(12));

        return new DelegatingPasswordEncoder("bcrypt", encoders);
    }
}
~~~

Explanation:

1. `idForEncode` is `bcrypt`; new encodes return the `{bcrypt}` prefix followed by the bcrypt hash.
2. Every `matches()` call on `{bcrypt}...` will use `BCryptPasswordEncoder`.
3. `BCryptPasswordEncoder(12)` has cost/work factor 12. Benchmark according to server resources and authentication latency budget; **there is no single cost suitable for every infrastructure**.
4. This mapping **does not support `{noop}`, `{pbkdf2}`, `{argon2}`...**. If the DB still has those ids, only switch to a narrow mapping once you have a compatibility and migration plan.
5. Do not declare both this `PasswordPolicyConfig` and the `PasswordEncoder` bean in the section 5 demo at the same time without resolving the bean conflict; this is an **alternative configuration option**, not an addition to the existing application.

If `{bcrypt}` hashes with a lower cost already exist, the bcrypt hash stores its cost; `BCryptPasswordEncoder(12)` can still verify bcrypt hashes with an old cost in a valid format. After successful authentication, `upgradeEncoding` can indicate records that need a cost bump. You do not write "cost 12" into the prefix yourself: the ID and the cost parameter inside bcrypt are two separate layers.

### Switching from bcrypt to another algorithm/version

A common scenario is changing the encoder used for new values:

~~~text
Initial phase: idForEncode = "bcrypt"    --> stores {bcrypt}...
Later phase:   idForEncode = "argon2-v2" --> stores {argon2-v2}...
                 |
                 +-- mapping still has "bcrypt" to match old hashes
                 +-- mapping has "argon2-v2" for new hashes
~~~

The name `argon2-v2` here is **solely a custom application ID for illustration**, not a default id guaranteed to exist. To deploy it, you need a real encoder with proper parameters, required dependencies, and benchmarked CPU/memory resources; do not change the id by editing the prefix string of old hashes. A bcrypt hash cannot turn into Argon2 by changing `{bcrypt}` to `{argon2}`.

If you only change **cost parameters within the same algorithm**, you can keep the current id or use an explicit versioned id, depending on your compatibility strategy and the delegate's `upgradeEncoding` capability. Not every `PasswordEncoder` automatically knows when it needs upgrading; you must check the implementation.

## 7. Wrong prefixes, missing prefixes, and errors reading legacy data

### 7.1. Missing prefix

Suppose the database stores a raw bcrypt string directly:

~~~text
$2a$10$...<valid bcrypt hash without the Spring Security prefix>...
~~~

When using `BCryptPasswordEncoder` directly, this string can be verified. When switching to `DelegatingPasswordEncoder`, the extracted id is **null** because there is no `{id}`, so by default there is no encoder mapped to `null`. In practice, an `IllegalArgumentException` may occur stating no `PasswordEncoder` is mapped for this id.

A safe solution requires **verifying the data's origin with certainty**:

- If all legacy records are verified to be valid bcrypt, you can perform an offline migration prepending `{bcrypt}` to **those specific records** after thorough checks and backups.
- Or have a controlled transition mechanism at the repository/login layer that identifies which legacy format a prefix-less record belongs to, verifies it, and saves a new value via the current `PasswordEncoder`.
- Never blindly assign `{bcrypt}` to records that could be MD5, salted SHA-256, plaintext, or another structure.

Illustrative SQL expressing the idea, **do not run directly on production**:

~~~sql
-- Only after proving this dataset consists of valid bcrypt hashes.
-- Exact statement depends on the DBMS and record selection criteria.
UPDATE users
SET password_hash = CONCAT('{bcrypt}', password_hash)
WHERE password_hash LIKE '$2a$%'
  AND password_hash NOT LIKE '{%';
~~~

This SQL statement is only a **simulation of the metadata-addition strategy**; it does not fully validate hashes and does not handle all bcrypt variants. Before an actual migration, back up the database, verify on a copy, use transactions/batches, check all bcrypt variants (`'$2a$'`, `'$2b$'`, `'$2y$'`) supported by your current encoder, and avoid overwrites while multiple instances are authenticating.

### 7.2. ID not in the mapping

Suppose the DB stores `{custom-id}...` but you have not registered `encoders.get("custom-id")`. `DelegatingPasswordEncoder` by default throws `IllegalArgumentException` rather than silently trying all encoders. This is sensible behavior: **do not guess algorithms from untrusted strings**.

Distinguish two situations:
- The ID is recognized, but `raw` is wrong → `delegate.matches(...)` returns false.
- The ID has no mapping → configuration/data error, which may raise an exception; handle and alert operations rather than simply labeling it "user entered wrong password".

Do not expose detailed exception messages about IDs, hash structure, or account names in public responses. Do not let an API throw bulk 500 errors after deployment without database compatibility testing.

### 7.3. Should setDefaultPasswordEncoderForMatches be used?

`DelegatingPasswordEncoder` has the `setDefaultPasswordEncoderForMatches(...)` API allowing you to specify a fallback when there is no encoder for the extracted id. This feature can help during a migration phase **when you know the exact legacy dataset**, but it carries risks:

- The fallback may be invoked even when the id is unknown, not only when the record lacks a prefix.
- The fallback encoder receives the stored value according to the API contract; do not assume its prefix is stripped or normalized in ways you have not tested.
- Choosing `NoOpPasswordEncoder` as the fallback can accidentally turn plaintext/unknown formats into accepted login credentials.
- A "try every encoder" fallback obscures data provenance, increases attack surface, and hides corrupted data.

Prefer explicit, time-boxed migrations with metrics and tests. If you still must use a fallback, write tests for **records with valid id, missing id, and unknown id**, along with a plan to remove the fallback after migration.

## 8. upgradeEncoding and hash upgrade strategies at login

Consider three records:

~~~text
alice: {bcrypt}<bcrypt hash with current cost>
bob:   {bcrypt}<bcrypt hash with older, lower cost>
carol: {noop}legacy-password (only illustrates insecure old data)
~~~

When the current `idForEncode` is `bcrypt` and the delegate `BCryptPasswordEncoder` has a newly configured cost:

- `alice` may not need an upgrade.
- `bob` may need an upgrade because the new `BCryptPasswordEncoder` configuration detects the old cost.
- `carol` needs an upgrade because the `noop` id differs from `idForEncode`.
- If the current id switches to `argon2`/a new version, old `{bcrypt}` records are usually marked for upgrade due to the differing id.

**`upgradeEncoding` only inspects hash status**; it does not verify the raw password and does not generate a new hash. The safe upgrade workflow runs **after the password has been verified**:

~~~text
User submits rawPassword over HTTPS
      |
load existing password_hash from DB
      |
passwordEncoder.matches(rawPassword, storedHash)
      |
      +-- false: fail, do not modify hash
      |
      +-- true: valid password
                |
       passwordEncoder.upgradeEncoding(storedHash)
                |
                +-- false: keep as is
                |
                +-- true: newHash = passwordEncoder.encode(rawPassword)
                            |
                    controlled DB update
                            |
                  continue login flow
~~~

In Spring Security Servlet using `DaoAuthenticationProvider`, **UserDetailsPasswordService** is the extension point for updating the encoded password after authentication, if the provider is configured to use it. This object receives `UserDetails` and **a new encoded password**, updates the data store, and returns the corresponding `UserDetails`. Do not confuse it with `PasswordEncoder`: the encoder does not write to the database itself.

Conceptual signature:

~~~java
public interface UserDetailsPasswordService {
    UserDetails updatePassword(UserDetails user, String newPassword);
}
~~~

The parameter name `newPassword` in this API **refers to the re-encoded password value passed in by the provider**, not plaintext that you should encode a second time. If you save that value by calling `encode(...)` again, you will store a hash of a hash and the user will no longer be able to log in with their original password.

Illustrative SQL for **compare-and-swap** to prevent overwrites from concurrent logins:

~~~sql
UPDATE users
SET password_hash = :new_hash
WHERE id = :user_id
  AND password_hash = :old_hash;
~~~

Here `:new_hash` must be the valid new hash, and `:old_hash` is the value read during verification. Check the updated row count and handle retries/re-reads if there was a concurrent update or the user just changed their password. Exact logic depends on transactions/repositories; the SQL snippet is not a complete `UserDetailsPasswordService` implementation.

### Why can't you "convert all hashes" in a batch without the original passwords?

A one-way hash cannot be converted directly from bcrypt to Argon2 by decrypting. Without the raw password, you cannot compute the hash of a new algorithm from the original password. Valid options include:

- **Rehash on successful login** because at that moment you have the password just entered and verified by the user.
- **Require a password reset** for accounts that have not logged in for a long time or use an insecure/unverifiable format.
- **Add prefix metadata** to legacy data *if the stored algorithm is proven*, since that only adds routing info without changing the inner hash.

Do not rely on "rehashing the old hash" as an equivalent migration: that is not the value of the original password under the new algorithm.

## 9. Integrating PasswordEncoder with Spring Security Servlet

In a Servlet application, typical touchpoints:

~~~text
Form Login / HTTP Basic / password authentication mechanism
         |
AuthenticationManager / AuthenticationProvider
         |
UserDetailsService: load user + password_hash
         |
PasswordEncoder.matches(rawCredential, storedHash)
         |
Authentication succeeds or fails
         |
SecurityContext / authorization / response
~~~

Configure `PasswordEncoder` as a bean:

~~~java
package dev.example.auth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration
public class PasswordConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }
}
~~~

This file is **complete configuration code in a Spring Boot project with Spring Security**; when integrating into a real app, ensure there are no conflicting `PasswordEncoder` beans and that the active provider actually uses the declared bean.

An *illustrative* account creation example at the service layer:

~~~java
String raw = registrationForm.password();
String encoded = passwordEncoder.encode(raw);
userRepository.saveNewUser(registrationForm.username(), encoded);
~~~

The names `registrationForm` and `userRepository` here are **contextual Java pseudocode**, not a standalone compilable file. You must add validation, transactions, duplicate-username checks, personal data protection, and abuse prevention.

**Important:** the `PasswordEncoder` used at registration and at login must be **compatible**. If registration uses bcrypt directly while login uses `DelegatingPasswordEncoder`, `storedHash` lacks `{bcrypt}` and may error. Standardize on one `PasswordEncoder` bean/policy, and test the entire register → login → upgrade → login-again flow.

In Spring Security Servlet, login handlers should not manually verify passwords and bypass `AuthenticationManager`/`Provider`, as doing so can break `SecurityContext`, authentication events, account locking mechanisms, and related security policies.

## 10. Choosing algorithms and parameters: prefixes do not replace security policy

`DelegatingPasswordEncoder` is an implementation selection mechanism; actual security depends on **algorithms, parameters, input handling, account management, and operations**.

| Factor | What to consider |
| --- | --- |
| Algorithm | Prefer algorithms designed for passwords such as Argon2id, scrypt, bcrypt, or strongly configured PBKDF2; choose based on security requirements, support, and environment |
| Salt | Use random salts generated by the password hashing encoder; never reuse one fixed salt across all users |
| Work factor | Tune cost/iterations/memory based on latency benchmarks and offline attack resistance |
| Prefix id | Store the exact ID matching the configuration used to encode; do not edit ids arbitrarily |
| Column length | Large enough for `{id}` and the entire hash format of current/future algorithms; do not assume every hash is 60 characters long |
| Input password | Consistent Unicode, length, and input handling policy; note bcrypt has an input limit typically measured in bytes |
| Online guessing | Rate limiting, controlled lockout, MFA, anomaly detection, and generic error messages for bad credentials |
| Sensitive data | Do not log raw passwords, encoded hashes, tokens, or request bodies containing passwords; secure DB permissions, backups, and TLS |
| Migration | Test remaining ids, post-login upgrades, inactive account handling, backups, and rollback |

A `BCryptPasswordEncoder` with a cost so high that login requests enable a DoS attack against the system is also poor design. Raising cost requires measuring real performance, limiting authentication request rates, and testing under expected load.

**Pepper** (a shared secret managed outside the DB) is an optional addition in some designs, but never concatenate a pepper onto passwords without key management, rotation, and compatibility procedures. `PasswordEncoderFactories` does not manage a pepper for your application automatically.

With bcrypt, systems must pay attention to input limits (especially long passwords in UTF-8), library behavior, and Unicode normalization. Never silently truncate passwords and accept two different strings as the same password; establish a clear policy and test inputs consistently.

## 11. Common errors and how to handle them

### 11.1. Missing {id}, error "There is no PasswordEncoder mapped for the id null"

**Cause:** old hash data lacks a prefix or stored data lost its curly braces. **How to handle:** classify legacy formats, add the exact prefix when proven, or build an explicit migration flow. Do not disable password checking.

### 11.2. Changing idForEncode while deleting old mappings

**Cause:** old accounts still have `{bcrypt}`, but the new map only contains the encoder for the new id. **How to handle:** keep read mappings for ids still in the DB, implement upgrade-on-login, and monitor the count of records needing migration before removing old encoders.

### 11.3. Saving BCryptPasswordEncoder.encode() then verifying with the factory

**Cause:** direct `BCryptPasswordEncoder` only returns the bcrypt hash without prepending `{bcrypt}`. **How to handle:** use `DelegatingPasswordEncoder` from the start when saving new records, or perform a verified prefix migration.

### 11.4. Comparing two hashes instead of using matches()

**Wrong:** `encoder.encode(input).equals(stored)`. **Right:** `encoder.matches(input, stored)`. Algorithms like bcrypt use random salts, so two encodes of the same input usually do not produce the same string.

### 11.5. Dropping curly braces or mistyping the ID

Strings like `bcrypt$2a$...`, `[bcrypt]$2a$...`, or `{BCrypt}...` are not equivalent to `{bcrypt}$2a$...` unless you deliberately created such a mapping/format. The ID is a map key and must match the mapping exactly.

### 11.6. Using {noop} for new accounts because it is "easy to debug"

`NoOpPasswordEncoder` does not protect passwords. Legacy mappings exist only to provide a migration path in controlled environments. New user registration must use an appropriate password hashing algorithm and never return hashes in APIs.

### 11.7. Manually changing {bcrypt} to {argon2} in the database

Changing the prefix **does not transform** a hash into another algorithm. Once authenticated successfully with the raw password, re-encode with the new encoder and save the full output rather than replacing a few characters.

### 11.8. Calling encode() twice on a new hash

For example, the service layer encodes raw and then `UserDetailsPasswordService` encodes the already-encoded hash again: the record will hold a hash of a hash and the user cannot log in with the original password. Clearly distinguish variable names `rawPassword` and `encodedPassword`; test the flow end to end.

### 11.9. Seeing a valid prefix and concluding the password is secure

`{bcrypt}` is metadata; an overly low cost or a system allowing unlimited online brute force is still insecure. Proper work factor policies, monitoring, and rate limiting are required.

### 11.10. Skipping legacy data tests before deploying

A migration or Spring Security upgrade can change mappings, dependencies, or policies. Build a test fixture containing valid hashes from every active id, corrupted data, unknown ids, and prefix-less records, and test login/upgrades rather than waiting for user failures in production.

## 12. Production deployment checklist

Before changing password encoding mechanisms:

1. **Inventory existing ids:** count records by prefix without exporting hashes to logs or public dashboards.
2. **Verify mappings:** every active id must have a proper verification decoder; define clear policies for unknown ids and prefix-less records.
3. **Choose the new idForEncode:** configure benchmarked algorithm, work factor, and memory/iterations; store both prefix and hash.
4. **Test before rollout:** new encodes, matching new hashes, matching old data, wrong passwords, `upgradeEncoding`, and user password resets.
5. **Integrate with the real provider:** ensure `AuthenticationProvider` uses the compatible `PasswordEncoder`; configure `UserDetailsPasswordService` if rehash-on-login is desired.
6. **Write to the database safely:** ensure sufficient column length, proper transactions, concurrency control, backups, and rollback capability.
7. **Protect the login flow:** HTTPS, rate limiting, MFA as needed, and never log raw/encoded passwords.
8. **Monitor migration:** record counts per id, upgrade rates, unknown id errors; control removal of old mappings.
9. **Maintain compatibility:** during multi-instance rollouts, ensure all instances understand the new format before the first instance starts writing hashes with the new id.
10. **Control changes:** test across Spring Security upgrades; never assume factory maps and algorithm parameters never change.

### Self-practice questions

1. In `{bcrypt}$2a$10$...`, which part does `DelegatingPasswordEncoder` use to pick the encoder? Which part is the cost used by bcrypt?
2. If `idForEncode` is `bcrypt` and the DB contains `{pbkdf2}...`, does `matches()` use bcrypt or PBKDF2? Why?
3. Why should you not verify a password by calling `encode(raw)` and comparing strings?
4. Why can a prefix-less bcrypt string be valid with `BCryptPasswordEncoder` yet fail with `DelegatingPasswordEncoder`?
5. Does `upgradeEncoding(hash)` write to the database automatically? What role does `UserDetailsPasswordService` play?
6. If you change the algorithm for new passwords, must you change the prefix of every old hash?
7. Why is using `NoOpPasswordEncoder` as an unconditional fallback risky?
8. What must you do for a safe multi-instance rollout when starting to store a new id?
9. Why is merely replacing `{bcrypt}` with `{argon2}` not a migration?
10. If an old hash verified successfully but has a low cost, how do you upgrade it without asking the user to re-enter their password a second time?

## Conclusion

**DelegatingPasswordEncoder is not a new hashing algorithm.** It is a mechanism for **storing an id alongside the hash and routing to the corresponding `PasswordEncoder`**. On new encodes, `idForEncode` decides which algorithm to use; on `matches`, **the `{id}` of the stored data** decides which algorithm verifies it. This enables password upgrades across logins while preserving readability of old data during migration.

Always store the full **{id}encodedPassword** string, use **matches()** for verification, understand **upgradeEncoding()** as a signal rather than a DB update operation, and design migrations with testing, data protection, and clear version management.
# PasswordEncoder: password hashing differs from decryptable encryption

> **Scope:** Spring Security 6.x, Java 17+, Spring Boot 3.x applications on the Servlet stack. This lesson explains why passwords must be stored as a **password hash** rather than **reversible decryptable encrypted** data; the `salt` and `work factor` mechanisms; the `PasswordEncoder.encode`, `matches`, and `upgradeEncoding` APIs; and strategies for using `DelegatingPasswordEncoder` and upgrading algorithms over time.

## 1. Why doesn't the application need to decrypt passwords?

When a user creates a password, the application needs to verify whether the password entered on a subsequent login is correct. The application **does not need** to send the original password back to the user. If the database stores passwords in plaintext, anyone who can read the database can immediately use the passwords. If a password is encrypted with AES using a decryptable key, when that key is compromised, passwords can be recovered in bulk.

A standard flow is:

```text
REGISTRATION
  raw password
      |
      v
  PasswordEncoder.encode(rawPassword)
      |
      v
  encoded password (hash + salt + parameters)
      |
      v
  database stores encoded password, does not store raw password

LOGIN
  username -> read encoded password from database
  raw password from new request + stored encoded password
      |
      v
  PasswordEncoder.matches(rawPassword, encodedPassword)
      |
      +--> true: continue checking account / authentication
      +--> false: reject login
```

**There is no `decrypt(passwordHash)` operation.** Users who forget their password must go through a secure password reset flow, not a "view old password" feature.

Password hashing does not make every password impossible to guess. If an attacker obtains the hash database, they can still try dictionaries, previously leaked passwords, or **offline** brute force. A password hashing algorithm makes each attempt **intentionally computationally expensive**, in order to slow down candidate guessing. Strength also depends on password complexity and infrastructure.

## 2. Differences between encryption, fast hashing, and password hashing

| Technology | Characteristics | Suitable for storing login passwords? |
| --- | --- | --- |
| **Two-way encryption**, e.g. AES-GCM | Can decrypt plaintext with a valid key | **Not suitable** if only password verification is needed |
| **Fast hash**, e.g. direct SHA-256/SHA-512 | No decryption API, but computes very fast | **Insufficient** to resist offline password guessing |
| **Password hashing/KDF**, e.g. bcrypt, Argon2id, scrypt, PBKDF2 | Has salt and parameters to tune computation/memory cost | **Yes**, if the algorithm and parameters are appropriate |
| **HMAC** | Uses a secret key for message authentication | Not a default replacement for password hashing |

### Encryption requires a decryption key

```text
ciphertext = Encrypt(key, plaintext)
plaintext  = Decrypt(key, ciphertext)
```

Encryption is very useful for **data that needs to be read back** when authorized, but being able to recover old passwords is an unnecessary risk if the application only authenticates users. Do not use encryption just to implement a "resend password" feature.

### SHA-256(password) is not enough

SHA-256 is designed to be very fast for data hashing. This speed is undesirable when an adversary can test many passwords after obtaining a database dump. Even `SHA-256(salt || password)` does not turn into a password KDF with an appropriate work factor.

Do not build a custom password hashing scheme by iterating SHA-256 a few times or arbitrarily combining MD5/SHA. Use proven libraries and specialized algorithms.

### A password hash is not "undecryptable encryption"

A more accurate phrasing is that password hashing produces a **one-way verification value** designed to verify a candidate password, rather than ciphertext that can be reversed with a key. However, weak passwords can still be guessed with many attempts. There is no "decryption key" for a bcrypt hash analogous to an AES key.

## 3. Salt, work factor, and pepper

### Unique salt per hash generation

A **salt** is random data used in generating a password hash. Standard encoders typically generate a new salt on each `encode` call. Therefore, the same raw password can produce multiple different encoded strings, yet all of them `matches` the correct password.

```text
password = "study123"
salt A -> password hash A
salt B -> password hash B

hash A differs from hash B (with overwhelming probability)
matches("study123", hash A) -> true
matches("study123", hash B) -> true
```

Salt is **not a secret**; it is usually stored alongside the hash and used during verification. Salt prevents two users with the same password from having easily comparable hashes and reduces the effectiveness of precomputed tables. Do not use a fixed global salt for all accounts, do not use username/email instead of a random salt, and do not manage your own salt if the encoder already handles it properly.

### Work factor is the cost of an attempt

- **bcrypt:** cost determines the amount of computation.
- **PBKDF2:** iterations and PRF/parameters.
- **scrypt:** work/memory parameters.
- **Argon2id:** memory, time/iterations, and parallelism.

A low work factor lets attackers try many passwords quickly. An overly high work factor slows down the server, consumes CPU/RAM, and can make it vulnerable to DoS attacks via many login requests. Therefore, you must **benchmark on real infrastructure**, evaluate concurrency, latency, and the ability to raise cost over time; do not hardcode a cost number from a tutorial and assume it fits everywhere.

### Pepper is an additional secret, not a salt replacement

**Pepper** is a system-wide secret that may be added according to a reviewed design, typically kept separate from the database in a secret manager/KMS. Unlike salt, pepper must be protected and have a rotation plan. Pepper does not replace password hashing, salt, or work factor; nor does it provide the ability to decrypt hashes. Do not arbitrarily concatenate a pepper onto passwords without a clear key management and migration model.

## 4. Spring Security's PasswordEncoder

`org.springframework.security.crypto.password.PasswordEncoder` has three important methods:

```java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);
    boolean matches(CharSequence rawPassword, String encodedPassword);

    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
```

This is an **illustrative API signature**, not an interface you need to create yourself.

- `encode(rawPassword)`: produces a hash string for storage. The word "encode" does **not** mean it can be decoded to recover the password.
- `matches(rawPassword, encodedPassword)`: uses the newly received raw password and the stored hash to verify, according to the appropriate algorithm/salt/params.
- `upgradeEncoding(encodedPassword)`: indicates whether the old hash should be regenerated under the current policy. This method **does not automatically update the database**.

### Why not encode again and compare with equals?

```java
String stored = encoder.encode("study123");

// WRONG: a new encode call may generate a new salt.
boolean wrong = encoder.encode("study123").equals(stored);

// RIGHT: use the encoder's matching method.
boolean correct = encoder.matches("study123", stored);
```

This is an **illustrative snippet inside a method** that has an `encoder` variable of type `PasswordEncoder`. Two encodes of the same password usually differ because of the new salt. Each algorithm has its own verification rules; let `matches` handle it.

### PasswordEncoder does not replace full authentication

`UserDetailsService` provides the account and stored hash; `DaoAuthenticationProvider` may call `matches` to compare passwords; `AuthenticationManager` coordinates providers. After the password check, there are still account locked/disabled/expired status checks, roles/authorities, and other security policies. A correct password **does not mean** access to the endpoint is guaranteed.

## 5. Algorithms and encoders worth knowing

| API/Algorithm | Advantages | Notes |
| --- | --- | --- |
| `BCryptPasswordEncoder` | Built-in salt/cost, widely used, easy to integrate | Traditional bcrypt has an input limit around **72 bytes**; check Unicode/length and cost |
| `Argon2PasswordEncoder` / Argon2id | Memory-hard, tunable time, RAM, and parallelism | Requires appropriate dependency, some versions use Bouncy Castle; benchmark RAM and concurrency |
| `SCryptPasswordEncoder` | Memory-hard | Configure reasonable memory/CPU and login load |
| `Pbkdf2PasswordEncoder` | Broad compatibility, has iteration count | Increases computational cost; not memory-hard like Argon2id/scrypt |
| `DelegatingPasswordEncoder` | Selects encoder by `{id}` prefix, supports multi-generation hashes | Must manage mapping and legacy formats |
| `NoOpPasswordEncoder` | Does not hash | **Do not use to store production passwords** |

With bcrypt, the **byte** limit differs from the **Unicode character** limit; one Vietnamese character can occupy multiple UTF-8 bytes. Depending on implementation/version, long passwords may exhibit unexpected behavior. Do not automatically `trim()` passwords, do not truncate strings, and do not invent custom pre-hashing; establish a consistent policy and test it in practice.

Argon2id is often a strong modern choice if infrastructure and libraries support it; bcrypt remains widely used. Never claim that one algorithm/cost is "absolutely secure" at all times.

## 6. DelegatingPasswordEncoder and the {id} prefix

`PasswordEncoderFactories.createDelegatingPasswordEncoder()` creates an encoder that can use multiple algorithms to **verify** based on an identifier. In the Spring Security 6.x factory configuration shown in the example below, the `encode` method defaults to selecting bcrypt.

Typical data format:

```text
{bcrypt}$2a$10$<generated salt and hash>
|------|
    id
```

This is **not a complete valid hash**, only a format illustration. `{bcrypt}` is an identifier for `DelegatingPasswordEncoder` to look up the encoder. The actual salt and hash portion are randomly generated; the prefix is not a secret or an encryption layer.

```java
PasswordEncoder encoder =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();

String stored = encoder.encode("study123");
boolean valid = encoder.matches("study123", stored);
```

When `matches` receives `{bcrypt}...`, it reads the id, selects the mapped bcrypt encoder, and checks the raw password against the trailing hash portion. This design allows a system to verify both old and new hashes during an algorithm upgrade phase (if the corresponding encoders are still supported).

### When an old hash is missing the id

A database using legacy bcrypt often contains strings like `$2a$...` without the `{bcrypt}` prefix. If you pass this value directly to `DelegatingPasswordEncoder.matches` by default, the framework may throw `IllegalArgumentException` because id `null` is not mapped. This is a **data/encoder format** error, not evidence of a wrong password.

Safe handling approaches:

1. Verify that old records are truly valid bcrypt hashes. If all records have been accurately classified, you can batch-migrate them to `{bcrypt}` + the original hash string.
2. If multiple legacy algorithms exist, manage clear mapping/metadata and verify with the right algorithm.
3. Rehash after successful login under the new policy or use a password reset workflow when old data cannot be verified.
4. **Do not** set `NoOpPasswordEncoder` as the default fallback for all hashes missing an id just to "fix the error" quickly: that can create an insecure branch accepting plaintext.

Different Spring Security versions may use ids with suffixes/versions for some algorithms. Always verify the mapping of the running library; do not guess prefixes.

## 7. Runnable Java 17+ example: encode and matches

The example uses Spring Security Crypto from the Spring Boot 3.3.5 version family, Java 17, and Gradle 8.5. This is a **standalone console program**, requiring no servlet container, database, or web server.

### 7.1. File structure

```text
password-encoder-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/
    PasswordEncodingDemo.java
  src/test/java/demo/
    PasswordEncodingDemoTest.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'password-encoder-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencyManagement {
    imports {
        mavenBom 'org.springframework.boot:spring-boot-dependencies:3.3.5'
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-crypto'
    implementation 'org.springframework:spring-core'
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

application {
    mainClass = 'demo.PasswordEncodingDemo'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-security-crypto` contains `PasswordEncoder`, the factory, and bcrypt; `spring-core` provides the Spring dependencies needed for the console example. In a real Spring Boot web app, `spring-boot-starter-security` usually already includes the relevant parts.

### 7.2. Complete Main

`src/main/java/demo/PasswordEncodingDemo.java`:

```java
package demo;

import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class PasswordEncodingDemo {

    private PasswordEncodingDemo() {
    }

    public static void main(String[] args) {
        PasswordEncoder encoder =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        String rawPassword = "correct-horse-battery-staple!2026";
        String stored = encoder.encode(rawPassword);

        System.out.println("bcrypt id: " + stored.startsWith("{bcrypt}"));
        System.out.println("correct password: "
                + encoder.matches(rawPassword, stored));
        System.out.println("wrong password: "
                + encoder.matches("wrong-password", stored));
        System.out.println("stored plaintext: "
                + stored.equals(rawPassword));
    }
}
```

From the directory containing `build.gradle`, run:

```bash
gradle run
gradle test
```

If Gradle Wrapper is available, use `./gradlew run` and `./gradlew test` on macOS/Linux, or `.\gradlew.bat run` and `.\gradlew.bat test` on Windows.

**Four lines from `System.out.println`** (excluding Gradle logs):

```text
bcrypt id: true
correct password: true
wrong password: false
stored plaintext: false
```

The output is reproducible because the program **does not print random hash values**. In real products, you should also never log raw passwords, hashes, or sensitive authentication data.

### 7.3. JUnit 5 testing

`src/test/java/demo/PasswordEncodingDemoTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PasswordEncodingDemoTest {

    private static final String RAW =
            "correct-horse-battery-staple!2026";

    private final PasswordEncoder delegating =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();

    @Test
    void delegatingHashesAndMatches() {
        String stored = delegating.encode(RAW);
        assertTrue(stored.startsWith("{bcrypt}"));
        assertTrue(delegating.matches(RAW, stored));
        assertFalse(delegating.matches("wrong-password", stored));
        assertFalse(stored.equals(RAW));
    }

    @Test
    void rawBcryptVerifiesItsOwnHash() {
        BCryptPasswordEncoder bcrypt = new BCryptPasswordEncoder(10);
        String stored = bcrypt.encode(RAW);
        assertTrue(bcrypt.matches(RAW, stored));
        assertFalse(bcrypt.matches("wrong-password", stored));
    }

    @Test
    void delegatingRejectsLegacyWithoutIdByDefault() {
        BCryptPasswordEncoder bcrypt = new BCryptPasswordEncoder(10);
        String legacy = bcrypt.encode(RAW);
        assertThrows(IllegalArgumentException.class,
                () -> delegating.matches(RAW, legacy));
    }

    @Test
    void unknownIdIsNotSilentlyAccepted() {
        assertThrows(IllegalArgumentException.class,
                () -> delegating.matches(RAW, "{unknown}not-a-hash"));
    }
}
```

**Expected result with this configuration:** 4 JUnit tests PASS. The tests verify behavior rather than comparing hash bytes that contain a random salt. The latter two tests illustrate why legacy data without a prefix or with an unknown id must be handled via migration, not guessed automatically.

## 8. Integrating PasswordEncoder into Spring Security Servlet

In an application with `spring-boot-starter-security`, you can declare a shared `PasswordEncoder` bean for registration, password changes, and authentication:

```java
package demo;

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
```

This is a `@Configuration` class for a **Spring Context application**, not a file used in the console demo if you do not yet have the Spring Context dependency.

### Registration and password changes

```java
// Pseudocode: command and userRepository are domain types.
String rawPassword = command.password();
String encoded = passwordEncoder.encode(rawPassword);
userRepository.savePasswordHash(command.userId(), encoded);
```

Store only the encoded password and do not log the raw password. Do not return the hash in API responses. The DB column must be long enough for prefixes, parameters, and future hash formats.

### Login with DaoAuthenticationProvider

```text
Client sends username/raw password over HTTPS
             |
             v
AuthenticationManager -> DaoAuthenticationProvider
             |
             +--> UserDetailsService.loadUserByUsername(username)
             |            |
             |            +--> retrieve stored encoded hash
             |
             +--> PasswordEncoder.matches(rawPassword, storedHash)
                         |
                         +--> true: continue account status checks / authentication
                         +--> false: BadCredentialsException
```

This is a summary diagram: some account status checks happen before password comparison, and some after. `PasswordEncoder` does not replace locked/disabled checks, permissions, or CSRF; it only handles password verification.

## 9. Increasing work factor and safely migrating hashes

Algorithm versions and security parameters can change. `upgradeEncoding` is a signal supporting hash upgrades after a user logs in correctly. It **does not** automatically update the DB.

```text
Login -> load oldHash
      -> matches(rawPassword, oldHash)
         |
         +-- false -> reject
         |
         +-- true  -> upgradeEncoding(oldHash)?
                       |
                       +-- false -> keep existing hash
                       |
                       +-- true  -> encode(rawPassword)
                                   -> update hash safely
```

Pseudocode for a service (not a standalone Java class):

```java
if (!passwordEncoder.matches(rawPassword, oldHash)) {
    throw new BadCredentialsException("Invalid credentials");
}

if (passwordEncoder.upgradeEncoding(oldHash)) {
    String replacement = passwordEncoder.encode(rawPassword);

    // Hypothetical application API; not a Spring Security method.
    userRepository.replaceHashIfUnchanged(userId, oldHash, replacement);
}
```

You can perform compare-and-swap in the DB:

```sql
UPDATE users
SET password_hash = :new_hash
WHERE id = :user_id
  AND password_hash = :expected_old_hash;
```

The condition above prevents an older login request from overwriting a concurrent password change. The application needs to check affected rows and transactions. You must hash the **newly verified raw password**, not `oldHash`. When only the old hash is available without the raw password, you cannot generally convert to a new algorithm's hash; usually you must wait for a login or require a reset.

`DaoAuthenticationProvider` supports integrating `UserDetailsPasswordService` to update the hash in the corresponding configuration. Using this mechanism depends on the service and repository the application provides; do not assume every project automatically migrates passwords.

## 10. Safe operations in practice

1. **HTTPS/TLS:** protects raw passwords in transit.
2. **Rate limiting:** limits online guessing and CPU/RAM load from password hashing operations.
3. **MFA when appropriate:** reduces impact if passwords are leaked from other services.
4. **Database/backup protection:** hashes are still sensitive data; use least-privilege access and encrypt backups when needed.
5. **Do not log secrets:** do not write raw passwords, hashes, reset tokens, or credentials to logs/analytics.
6. **Verified password reset:** random, time-limited, single-use tokens; replace the hash and handle old sessions according to policy.
7. **Consistent Unicode and whitespace:** avoid automatic `trim()`; do not normalize differently between registration and login; check long passwords by byte length.
8. **Benchmark cost:** monitor latency and concurrency; Argon2id/scrypt have RAM cost, while bcrypt/PBKDF2 have CPU cost.
9. **Do not use hashes as session tokens:** a hash is not a bearer credential to send to the client.
10. **Review legacy formats:** identify `{id}`, legacy hash verification strategies, and a roadmap to phase out weak algorithms.

### When is two-way encryption appropriate?

Yes, if the data truly needs to be **read back** under controlled authorization. In that case, you must design encryption key management, rotation, nonce/IV, access control, and logging. But for ordinary login passwords, decryption capability brings no necessary benefit.

## 11. Common errors and how to fix them

| Error or misunderstanding | Why does it happen? | How to handle |
| --- | --- | --- |
| Same password, two encodes produce different results | New salt on each encode | Normal; use `matches` |
| `encode(raw).equals(stored)` is always false | Generates a new hash with a different salt | Use `matches(raw, stored)` |
| `There is no PasswordEncoder mapped for id "null"` | Hash is missing prefix or mapping | Classify/migrate old format |
| Direct BCrypt does not accept values with `{bcrypt}` | Raw encoder does not parse delegating prefix | Use the corresponding encoder |
| Changing encoder breaks login for old users | Old hash format is no longer supported | Controlled legacy verification, rehash, or reset |
| Long Unicode passwords cause surprises | Byte limit/normalization | Test and standardize policy |
| Slow login / high CPU | Cost too high or missing rate limit | Benchmark, control concurrency |
| Using SHA-256(password) | Hash is too fast for passwords | Use appropriate bcrypt/Argon2id/scrypt/PBKDF2 |
| Using `{noop}password` in production | Stores plaintext under NoOp identifier | Remove and migrate/reset |
| Trying to "decrypt hash to email password back" | Confusing password hashing with encryption | Use password reset |

## 12. Checklist and self-check questions

- [ ] Database only stores encoded passwords; does not store raw passwords or password decryption keys.
- [ ] Encoder uses a standard KDF algorithm, random salt, and benchmarked cost.
- [ ] Registration/password change uses `encode`; login uses `matches`.
- [ ] Understand the `{id}` prefix and how to migrate legacy hashes.
- [ ] Have a safe `upgradeEncoding`/rehash plan when raising cost or changing algorithms.
- [ ] Test correct/incorrect passwords, Unicode/whitespace, long inputs, legacy formats, and concurrency.
- [ ] Have HTTPS, rate limiting, secure password reset, and log/backup protection.

**Questions:**

1. **How does password hashing differ from encryption?** Password hashing aims to verify a candidate without decrypting; encryption has a key to recover plaintext.
2. **Why is standalone SHA-256(password) insufficient?** Because it is too fast for offline password guessing.
3. **Do two hashes of the same password need to be equal?** No. Random salt makes encoded strings usually differ; `matches` is still true.
4. **Is `{bcrypt}` a secret?** No, it is an id for `DelegatingPasswordEncoder` to choose the encoder.
5. **Does `upgradeEncoding` automatically save the new hash?** No, the application/integrated provider must perform the update.
6. **Can bcrypt treat 72 Unicode characters as equivalent to 72 bytes?** No, the limit must be understood at the byte/implementation level.
7. **Can hashes be decrypted to help users who forgot their password?** No, use a password reset flow.
8. **Does strong hashing replace rate limiting or HTTPS?** No, defense in depth is required.

**Remember:** Spring Security's `PasswordEncoder` is a **hash and verification** API, not an encryption API for decryption. On registration call `encode(rawPassword)`, on login call `matches(rawPassword, storedHash)`. Use a password KDF with appropriate salt/work factor, manage `{id}` and migration; do not store plaintext, and do not use SHA-256(password) or NoOp as a real password storage system.

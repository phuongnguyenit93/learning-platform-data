# DelegatingPasswordEncoder, Algorithm Prefixes, and Hash Upgrades

## 1. Context: Why Does an Application Need Multiple Password Hashing Algorithms?

In Spring Security Reactive (Spring WebFlux), username/password login must verify the password submitted by a user against a stored **one-way hash**. Account records can live for many years, while recommendations for hashing functions, computational parameters, and security requirements evolve over time.

For example, the same system might hold:
- A set of older accounts with BCrypt strings lacking a Spring Security prefix.
- A set of accounts stored in the format prefixed with `{bcrypt}`.
- PBKDF2, scrypt, or Argon2 hashes created by previous configurations.
- Some demo/legacy accounts that once stored `{noop}` (cleartext passwords; **insecure**, must be identified only to eliminate them).

If the entire system relies on a single `BCryptPasswordEncoder` and switches algorithms abruptly, the application can easily lock out existing users. Conversely, continuing to create new hashes with a weak algorithm for compatibility fails to improve security.

**`DelegatingPasswordEncoder`** lets you **create new hashes with the chosen algorithm** while **verifying old hashes with the exact algorithm originally used**, thanks to the identifier prefix at the start of the stored string. It also provides the `upgradeEncoding` API to indicate when a hash should be regenerated under the current configuration.

> **Security principle:** the prefix is merely metadata for selecting the verifier; it does not prove validity, does not encrypt plaintext, and does not automatically update stored passwords. Upgrades happen only when a valid raw password is available (typically after successful authentication) and a durable persistence mechanism exists.

Lesson objectives:
1. Understand the exact `{id}encodedPassword` format.
2. Distinguish `encode`, `matches`, `upgradeEncoding`, and **persisting the new hash to the user store**.
3. Use `PasswordEncoderFactories.createDelegatingPasswordEncoder()` or a controlled custom mapping.
4. Design migrations from prefixless hashes, weak hashes, or older parameters without breaking login.
5. Connect upgrades to `UserDetailsRepositoryReactiveAuthenticationManager` and `ReactiveUserDetailsPasswordService`.
6. Run a Java 17+ example with source code and tests, while recognizing common security mistakes.

## 2. What Contract Is PasswordEncoder?

Spring Security provides the interface:

~~~java
// Illustrative API signature; not a standalone Java program.
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);
    boolean matches(CharSequence rawPassword, String encodedPassword);
    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
~~~

Three distinct meanings:

| Method | Input | Result | What It Does Not Do |
| --- | --- | --- | --- |
| `encode(raw)` | Raw password, e.g., during registration/password change | A hash string matching the current encoder | Does not save to the database itself |
| `matches(raw, stored)` | User-submitted password and **stored** string | `true` or `false` when the hash/algorithm is valid | Does not decrypt the hash to recover the password |
| `upgradeEncoding(stored)` | **Stored** string | `true` if policy says a new hash should be generated | Does not re-hash or update the user itself |

Modern password hashing is a **one-way, computationally expensive** mechanism. The system must never "decrypt" a hash to learn the password; at login, it uses `matches` to verify the presented password against the stored hash. To upgrade, you need the verified raw password before you can call `encode(raw)` again under the new algorithm/policy.

A password hash differs from a **JWT token**, refresh token, or data encrypted for decryption. DelegatingPasswordEncoder only handles the **password** verification layer; it does not verify Bearer JWTs and does not replace WebFlux authentication/authorization steps.

## 3. Storage Format: `{id}encodedPassword`

General form of `DelegatingPasswordEncoder`:

~~~text
{id}encodedPassword
 ^^^ ^^^^^^^^^^^^^^^
  |        |
  |        +-- encoded output from the corresponding PasswordEncoder
  +----------- identifier used to look up the decoder/matcher
~~~

Illustrative examples:

~~~text
{bcrypt}$2a$10$dXJ3SW6G7P50lGmMkkmwe.20cQQubK3.HZWzG3YB1tlRy.fqvM/BG
{noop}temporary-demo-only
{pbkdf2@SpringSecurity_v5_8}<actual-encoded-value>
{argon2@SpringSecurity_v5_8}<actual-encoded-value>
~~~

The last two lines only show the **prefix shape**; `<actual-encoded-value>` is a placeholder, **not a valid hash usable for login**. `{noop}` is cleartext and should never exist in a production store.

Components:
- `{` and `}` delimit an `id` at the beginning of the string.
- `id` does not have to be just a raw algorithm name; it can include a policy version label such as `pbkdf2@SpringSecurity_v5_8`.
- Everything after the closing brace is passed to the encoder mapped to `id`.
- Formats like BCrypt store their own algorithm cost/salt **inside** the `encodedPassword` portion. `{bcrypt}` is not a salt and does not represent the cost.
- By default Spring Security uses curly braces; the `DelegatingPasswordEncoder` API has constructors to change the prefix/suffix if needed, though you should not alter them without a clear compatibility requirement.

### 3.1. The `encode` Process

If `idForEncode = "bcrypt"`, `encode("correct-password")` performs:
1. Look up the mapping `bcrypt -> BCryptPasswordEncoder`.
2. Call BCrypt to generate a new hash with a random salt.
3. Prepend `{bcrypt}` to the returned string.

Calling `encode` twice on the same password usually produces **different hashes** because of random salting. Therefore, never check with `newHash.equals(oldHash)`; always call `matches(raw, oldHash)`.

### 3.2. The `matches` Process

For `{bcrypt}...` data, the delegator:
1. Extracts `id = bcrypt`.
2. Selects `BCryptPasswordEncoder`.
3. Passes the hash portion after the prefix to `BCryptPasswordEncoder.matches(raw, hash)`.
4. Returns the password verification result; it never needs to know the original plaintext of the hash.

For `{pbkdf2@SpringSecurity_v5_8}...`, the mapping must contain this exact ID. Never assume the IDs `pbkdf2` and `pbkdf2@SpringSecurity_v5_8` share the same parameters.

### 3.3. When the ID Is Missing or Unregistered

If a hash lacks `{id}`, or carries `{unknown}...`, `DelegatingPasswordEncoder.matches` by default **throws `IllegalArgumentException`** because no matching encoder is found, rather than always returning `false`. There is a `setDefaultPasswordEncoderForMatches` API to alter this behavior, but misconfiguring it can open weak authentication paths or scheme confusion.

Distinguish clearly:
- **Wrong password against a valid hash:** `matches` normally returns `false`.
- **Hash with unknown ID:** may throw `IllegalArgumentException` by default.
- **Malformed hash:** handling depends on the specific encoder; monitor data errors and handle them safely without assuming every case simply returns `false`.

An exception thrown by the API signals **incorrect data or mapping**, not a request to permit a fallback login.

## 4. `PasswordEncoderFactories.createDelegatingPasswordEncoder()`

How to create an encoder with Spring Security's recommended mapping:

~~~java
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

PasswordEncoder encoder =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();
~~~

In the Spring Security 6.x version matching the example, the default encoder **creates new hashes with BCrypt** and prepends `{bcrypt}`. The verification mapping includes multiple IDs to support legacy data and other policies, covering BCrypt, PBKDF2, scrypt, Argon2, and several legacy algorithms. **Available mappings can change across library versions**, so check the Javadoc/deployed version rather than hardcoding a fixed list for all Spring Security versions.

The presence of a weak ID in the mapping **is not a recommendation to use that ID for new passwords**. For instance, `noop`, MD5, and SHA-1 may appear for legacy compatibility, not as safe choices for current users.

### 4.1. When Do You Need a Custom Encoder?

When an organization has its own policy for algorithms/cost or versioned IDs, you can instantiate an explicit mapping:

~~~java
// Java snippet that can be placed inside @Bean PasswordEncoder.
Map<String, PasswordEncoder> encoders = new HashMap<>();
encoders.put("bcrypt-v2", new BCryptPasswordEncoder(12));
encoders.put("bcrypt", new BCryptPasswordEncoder());

PasswordEncoder passwordEncoder =
        new DelegatingPasswordEncoder("bcrypt-v2", encoders);
~~~

This is a configuration snippet requiring imports `java.util.Map`, `java.util.HashMap`, `PasswordEncoder`, `BCryptPasswordEncoder`, and `DelegatingPasswordEncoder`. New strings carry `{bcrypt-v2}`; old `{bcrypt}` records still match because the old mapping remains present.

**Note:** a custom ID like `bcrypt-v2` must remain compatible across all instances and all deployments. Changing the implementation behind an existing ID to a different algorithm while old hashes exist is a migration bug. If changing parameters in a way that affects matching, use a new versioned ID or ensure the encoder can still safely read the old format.

Do not put `NoOpPasswordEncoder` into a new production mapping just to avoid login errors. If ultra-short-term legacy support is unavoidable, scope it tightly, measure progress, and plan its removal.

## 5. Password Hashing Requires Adaptive Algorithms and Proper Parameters

**BCrypt, PBKDF2, scrypt, and Argon2** are designed to raise password-guessing costs compared to fast digests like SHA-256/MD5. However, "using BCrypt" alone does not guarantee overall system security; password length/entropy, account management policies, rate limiting, MFA, data protection, and hash parameters also matter.

| Option | Characteristics | Operational Notes |
| --- | --- | --- |
| BCrypt | Work factor/cost, salt embedded in hash; widely supported | Measure and tune cost to infrastructure capacity and SLA |
| PBKDF2 | Configurable iterations per policy/version | Accurate verification requires knowing iteration count, PRF, salt, and format |
| scrypt | Has memory and time cost | Tune memory/CPU to avoid overload |
| Argon2 | Memory-hard design, multiple parameters | Verify dependencies and check resources before deployment |
| Plain MD5/SHA-1/SHA-256 | Fast digests | Never use directly as a new password-hashing scheme |
| `noop` | Cleartext passwords | Identify only in legacy/demos to eliminate; insecure |

A BCrypt hash might begin with `$2a$10$...`, where `10` is BCrypt's log cost. `{bcrypt}` is the **Spring Security** prefix, while `$2a$10$...` belongs to the **BCrypt** format. The two prefixes serve different purposes.

Never pick cost purely by gut feeling. Benchmark `encode`/`matches` timings on production-like setups (CPU/memory/traffic/concurrency), set time bounds, and enforce brute-force protections. Parameters should be revisited periodically as hardware and security requirements evolve.

## 6. `upgradeEncoding`: Detecting Upgrade Needs

The method:

~~~java
boolean shouldUpgrade = encoder.upgradeEncoding(storedHash);
~~~

lets the application ask: "Given that the user just authenticated successfully, should the stored hash be regenerated under the current policy?"

For `DelegatingPasswordEncoder`:
- If the stored hash's `id` **differs** from `idForEncode`, the result is usually `true`: the record uses an older scheme.
- If the `id` matches `idForEncode`, the encoder delegates the upgrade check to the corresponding implementation; for example, `BCryptPasswordEncoder` can request an upgrade when an old hash has a lower cost than configured.
- The return value is **a decision**, and no database write is performed.

Even when `upgradeEncoding` returns `true`, you cannot re-hash solely from the old hash string. The most common flow is **upgrading upon successful login**: the raw password was just supplied by the user and verified via `matches`.

### 6.1. Correct Upgrade Event Sequence

~~~text
POST /login (username, rawPassword)
       |
       v
Load user: storedPassword = {oldId}...
       |
       v
passwordEncoder.matches(rawPassword, storedPassword)
       |
       +--> false: reject, DO NOT update hash
       |
       +--> true:
                |
                v
        passwordEncoder.upgradeEncoding(storedPassword)
                |
          +-----+-----+
          |           |
        false        true
          |           |
     Keep current   encode(rawPassword) with new policy
        hash            |
                        v
               Persist new hash safely
                        |
                        v
                 Complete login
~~~

When upgrading:
1. Run only after password verification succeeds.
2. Call `encode(rawPassword)` to create a new hash (with a fresh salt if supported by the algorithm).
3. Write the new hash to the user store using a reliable update operation.
4. Never log raw passwords or full hashes.
5. In systems with concurrent requests, use optimistic locking/CAS so you do not overwrite a concurrent password change.
6. Handle persistence errors explicitly and never leave an ambiguous state ("login succeeded while silently assuming upgrade succeeded") when policy mandates the upgrade.

### 6.2. Upgrading Is Not Changing a Password

Upgrading a hash can keep the **same raw password** while changing the algorithm/cost/salt. Changing a password replaces the **authentication secret**; the two actions have different verification and auditing requirements.

If a password is suspected compromised or was previously stored in cleartext, rehashing after login **does not erase** past exposure risk. The organization may need to force users to set new passwords, check for credential compromise, and revoke sessions/tokens per incident policy.

## 7. Relation to Reactive Authentication in WebFlux

In Spring Security Reactive, `UserDetailsRepositoryReactiveAuthenticationManager` can use a `ReactiveUserDetailsService` to look up users and a `PasswordEncoder` to verify credentials. Its base class `AbstractUserDetailsReactiveAuthenticationManager` exposes two key configuration hooks:

~~~java
manager.setPasswordEncoder(passwordEncoder);
manager.setUserDetailsPasswordService(passwordService);
~~~

`ReactiveUserDetailsPasswordService` declares:

~~~java
// Abbreviated signature for readability; actual imports/interface are provided by Spring Security.
Mono<UserDetails> updatePassword(UserDetails user, String newPassword);
~~~

When wired into the appropriate authentication flow, the manager can perform password upgrades after successful authentication and invoke the service to **persist the new hash**. Without a persistence service wired in, merely seeing `upgradeEncoding=true` does not modify the database.

### 7.1. Components to Distinguish

| Component | Responsibility |
| --- | --- |
| `ServerAuthenticationConverter` or built-in Basic/form login converter | Extracts username/password from the request |
| `AuthenticationWebFilter` | Triggers/orchestrates authentication in the security chain |
| `UserDetailsRepositoryReactiveAuthenticationManager` | Looks up user, checks password and account flags |
| `PasswordEncoder` | Hashes, verifies, and evaluates hash upgrades |
| `ReactiveUserDetailsPasswordService` | Saves the regenerated hash to the user store |
| `ReactiveSecurityContextHolder` | Exposes the authenticated request's context downstream |
| Authorization | Checks roles/access permissions after identity is verified |

**`PasswordEncoder` itself is a synchronous API**: `encode` and `matches` consume CPU even inside a reactive application. That does not mean calling `block()` in a controller; the reactive manager schedules verification appropriately, and when writing a custom manager you must avoid letting heavy CPU hashing block the event loop. Do not work around this by spawning detached `subscribe()` calls or unbounded work.

### 7.2. How Does MapReactiveUserDetailsService Support the Demo?

`MapReactiveUserDetailsService` implements both `ReactiveUserDetailsService` and `ReactiveUserDetailsPasswordService`. Thus, it can power an **in-memory** upgrade example. In a real system, replace it with an implementation that reads/writes a non-blocking data store with versioning/CAS, auditing, and error policies.

Do not assume every `ReactiveUserDetailsService` can automatically update passwords: the user-lookup interface and the password-update interface **are two separate contracts**.

## 8. Runnable Java 17+ Project: Upgrading Hashes from `{noop}` to `{bcrypt}`

This is a **console demo using Reactor and Spring Security Core**, not an HTTP server. It illustrates the exact password-upgrade core that a WebFlux application uses. `block()` appears only at the **`main()` boundary of the console program** to wait for results before printing; never copy that into a WebFlux controller, WebFilter, or reactive service.

**Simulated legacy data:** user `learner` has password `{noop}legacy-pass`. This is intentionally insecure data to demonstrate migration, **definitely not how passwords should be stored in real deployments**.

Project structure:

~~~text
password-upgrade-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   └── PasswordUpgradeDemo.java
    └── test/java/demo/
        └── PasswordUpgradeTest.java
~~~

### 8.1. Gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'password-upgrade-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.security:spring-security-core'
    implementation 'org.springframework.security:spring-security-crypto'
    implementation 'io.projectreactor:reactor-core'

    testImplementation 'org.junit.jupiter:junit-jupiter'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

application {
    mainClass = 'demo.PasswordUpgradeDemo'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Gradle Platform uses the Spring Boot BOM to manage compatible versions of Spring Security, Reactor, and JUnit. No running Spring Boot web app is needed since the demo focuses strictly on hashing and reactive authentication. Requires a Java 17-compatible Gradle version with JDK 17+.

### 8.2. Complete Java Code

`src/main/java/demo/PasswordUpgradeDemo.java`:

~~~java
package demo;

import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class PasswordUpgradeDemo {

    private PasswordUpgradeDemo() {
    }

    public static void main(String[] args) {
        // LEARNING ONLY: legacy plaintext password, do not use outside demos.
        String legacyStoredHash = "{noop}legacy-pass";

        UserDetails legacyUser = User.withUsername("learner")
                .password(legacyStoredHash)
                .roles("USER")
                .build();

        MapReactiveUserDetailsService users =
                new MapReactiveUserDetailsService(legacyUser);

        PasswordEncoder encoder =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetailsRepositoryReactiveAuthenticationManager manager =
                new UserDetailsRepositoryReactiveAuthenticationManager(users);

        manager.setPasswordEncoder(encoder);
        // Allow the manager to save the upgraded hash after successful authentication.
        manager.setUserDetailsPasswordService(users);

        System.out.println("upgradeBefore="
                + encoder.upgradeEncoding(legacyStoredHash));

        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "learner", "legacy-pass");

        // Only at the console main() boundary; never use block() in WebFlux.
        Authentication verified = manager.authenticate(request).block();

        String updatedHash = users.findByUsername("learner")
                .map(UserDetails::getPassword)
                .block();

        System.out.println("authenticated="
                + (verified != null && verified.isAuthenticated()));
        System.out.println("prefixBcrypt="
                + (updatedHash != null
                        && updatedHash.startsWith("{bcrypt}")));
        System.out.println("passwordStillMatches="
                + encoder.matches("legacy-pass", updatedHash));
        System.out.println("upgradeAfter="
                + encoder.upgradeEncoding(updatedHash));
    }
}
~~~

Run command in the directory containing `build.gradle`:

~~~bash
gradle run --quiet
~~~

If the project uses a Gradle Wrapper, replace `gradle` with `./gradlew` on macOS/Linux or `gradlew.bat` on Windows.

**Expected stdout from the demo code:**

~~~text
upgradeBefore=true
authenticated=true
prefixBcrypt=true
passwordStillMatches=true
upgradeAfter=false
~~~

Explanation:
1. `upgradeBefore=true` because the default policy uses `bcrypt` for new hashes, whereas the old user has ID `noop`.
2. The manager authenticates the raw password `legacy-pass` against the stored legacy value.
3. With `ReactiveUserDetailsPasswordService` attached, the manager re-hashes and updates the user **in memory** after successful authentication.
4. The new hash starts with `{bcrypt}`, though its inner content varies on each run due to salting.
5. `matches` confirms the same password still logs in after migration.
6. With the new encoder's default work factor, `upgradeAfter=false` indicates the current policy requires no further upgrade.

Do not print the entire hash for snapshot assertions: BCrypt uses random salts, so **there is no fixed hash value**. The boolean lines above are the predictable comparison results. The program needs to download Gradle dependencies and may emit build-tool messages separate from the class's stdout.

**Demo limitation:** `MapReactiveUserDetailsService` only stores data in process memory. Restarting the program recreates the legacy user from source code. Production must persist the new hash to a real database or identity store; never log raw passwords and never treat in-memory storage as durable data migration.

## 9. Testing with JUnit 5 + Reactor StepVerifier

Tests must prove three things: right password authenticates and upgrades the hash, wrong password does not upgrade the hash, and unknown IDs are not silently accepted.

`src/test/java/demo/PasswordUpgradeTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PasswordUpgradeTest {

    private static final String LEGACY = "{noop}legacy-pass";

    @Test
    void successfulLoginUpgradesStoredPassword() {
        var users = new MapReactiveUserDetailsService(
                User.withUsername("learner")
                        .password(LEGACY).roles("USER").build());

        PasswordEncoder encoder =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        var manager =
                new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        manager.setUserDetailsPasswordService(users);

        StepVerifier.create(manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "learner", "legacy-pass")))
                .assertNext(authentication ->
                        assertTrue(authentication.isAuthenticated()))
                .verifyComplete();

        StepVerifier.create(users.findByUsername("learner"))
                .assertNext(user -> {
                    String hash = user.getPassword();
                    assertTrue(hash.startsWith("{bcrypt}"));
                    assertTrue(encoder.matches("legacy-pass", hash));
                    assertFalse(encoder.upgradeEncoding(hash));
                })
                .verifyComplete();
    }

    @Test
    void wrongPasswordDoesNotUpgrade() {
        var users = new MapReactiveUserDetailsService(
                User.withUsername("learner")
                        .password(LEGACY).roles("USER").build());

        PasswordEncoder encoder =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        var manager =
                new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        manager.setUserDetailsPasswordService(users);

        StepVerifier.create(manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "learner", "wrong")))
                .expectError(BadCredentialsException.class)
                .verify();

        StepVerifier.create(users.findByUsername("learner"))
                .assertNext(user -> assertEquals(LEGACY, user.getPassword()))
                .verifyComplete();
    }

    @Test
    void unknownIdIsNotSilentlyAccepted() {
        PasswordEncoder encoder =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        assertThrows(IllegalArgumentException.class,
                () -> encoder.matches(
                        "anything", "{notRegistered}some-hash"));
    }
}
~~~

Run:

~~~bash
gradle test
~~~

**Expected:** three tests PASS when built with the declared dependencies. This is a statement of logic and API verification, **not a report of an executed Gradle run**.

To interpret the tests accurately:
- The first test calls `setUserDetailsPasswordService(users)`, so a successful authentication has a mechanism to persist the new hash. Without that line, do not assume data changes.
- The second test verifies no upgrade happens when the user submits a wrong password.
- The third test verifies an unmapped ID does not silently pass through.
- `StepVerifier` subscribes to the manager's publisher and awaits completion; no manual `subscribe()` is needed in services.

## 10. Handling Legacy BCrypt Hashes **Without** `{bcrypt}`

This is a very common real-world migration problem:

~~~text
Previous data:
$2a$10$...BCryptPayload...

Spring Security DelegatingPasswordEncoder format:
{bcrypt}$2a$10$...BCryptPayload...
~~~

A hash may already be standard BCrypt yet lack the Spring Security prefix. In that case:
- Default `DelegatingPasswordEncoder` has no ID to select the algorithm.
- It is not a wrong raw password. It can be a **format migration** issue.
- If you confirm with certainty that an entire cohort is valid BCrypt, prepending `{bcrypt}` to the stored string is a **metadata operation** that does not alter the hash itself and does not require the raw password.
- However, **never** blindly prepend `{bcrypt}` to arbitrary unknown hashes: SHA, PBKDF2, or corrupted records would be mislabeled and fail verification.

Safe workflow for prefixless data:
1. Inventory schemas and origins to identify the true algorithms.
2. Check formats/costs and test representative samples in a controlled test environment.
3. Write an idempotent migration script targeting only positively identified cohorts.
4. Back up data, prepare a rollback plan, and monitor login errors after rollout.
5. For hashes of uncertain type, require password resets/investigation instead of guessing mappings.
6. After adding prefixes, you can use `upgradeEncoding` to upgrade further when users log in validly.

If temporary legacy-format support is required right during authentication, Spring Security offers:

~~~java
// Illustrative API, should not be applied broadly without controls.
delegating.setDefaultPasswordEncoderForMatches(legacyEncoder);
~~~

**Risk:** this is a fallback for **unmapped IDs, including missing or unknown IDs**. The fallback receives the **entire raw hash string**, including any `{unexpected}` prefix if present. An overly permissive fallback can mask data errors, enable downgrades, or let forged values route through a different scheme. It is better to normalize identifiable records via explicit migration; if an adapter is required, strictly validate the legacy format and reject any ID outside an approved allowlist.

Never "fix" missing-prefix errors by saving bare hashes as `{noop}...`: doing so turns a **hash** into a "plaintext password" in NoOpPasswordEncoder's eyes, causing wrong behavior and severe security risks.

## 11. Upgrading Algorithms vs. Upgrading Parameters: Two Migration Types

### 11.1. Switching ID to a New Algorithm

Suppose the data store contains `{bcrypt}...` hashes, while the new `idForEncode` is `argon2-policy-v2`. The mapping retains `bcrypt` to verify older accounts. When a user logs in validly, `upgradeEncoding(stored)` signals an upgrade is needed because the ID differs, and `encode(raw)` then creates a hash under `argon2-policy-v2`.

When changing algorithms, you must:
- Benchmark CPU/memory and allocate resources.
- Verify the actual library/dependencies of the new encoder.
- Retain old mappings until the share of un-upgraded accounts falls below policy thresholds and a reset plan is in place.
- Ensure every instance can read **both new and old IDs** before enabling writes of the new ID (rolling deploy).
- Monitor login results and storage updates post-deploy.

### 11.2. Keeping BCrypt While Increasing Work Factor

When using the same `bcrypt` ID, `BCryptPasswordEncoder.upgradeEncoding` can inspect the cost inside an old hash against the current strength. For example, raising policy to `new BCryptPasswordEncoder(12)` flags hashes with lower costs for upgrade. Strength 12 is only an **example**, not a universal target for every system.

Because the same ID already encodes the work factor inside its payload, you do not necessarily need `{bcrypt-v2}` just to raise cost if your encoder supports stable same-ID upgrades. However, if changing incompatible parameters or formats, a dedicated versioned ID can make migration clearer.

### 11.3. PBKDF2, scrypt, and Argon2 with Policy Versions

For algorithms depending on iterations, memory, parallelism, salt length, or encoding format, you must know the exact parameters used to produce old hashes. Some Spring Security IDs carry version labels, such as `pbkdf2@SpringSecurity_v5_8` or `argon2@SpringSecurity_v5_8`. This prevents accidentally remapping an old ID to a policy that cannot read older records.

Never rely solely on the name `pbkdf2` to assume two hashes share the same PRF/iterations/salt. During migration, preserve exact historical version mappings matching the library version that created the data.

## 12. Designing Durable Persistence for New Hashes in Reactive Environments

In real systems, `ReactiveUserDetailsPasswordService.updatePassword` should use a reactive data store such as R2DBC or an equivalent client. A safe update model requires:
- Writing the **hashed** password, never the raw password.
- Applying a condition matching the old hash or old version to prevent race conditions.
- Surfacing write errors on failure rather than returning an opaque `Mono.empty()`.
- Excluding sensitive information from responses, traces, and audit logs.
- Not starting a detached subscription outside the authentication pipeline owning the work.

Java-style pseudocode example:

~~~java
// ILLUSTRATIVE structure: UserEntity, repository, and mapper must be defined.
// This is not a standalone runnable Java program.

public Mono<UserDetails> updatePassword(UserDetails user, String newHash) {
    return userRepository.findByUsername(user.getUsername())
        .flatMap(current ->
            userRepository.updateHashIfCurrentMatches(
                    current.id(),
                    current.passwordHash(),
                    newHash)
                .flatMap(rowsUpdated -> {
                    if (rowsUpdated == 1) {
                        return userRepository.findByUsername(user.getUsername())
                                .map(this::toUserDetails);
                    }
                    return Mono.error(new IllegalStateException(
                            "Password changed concurrently"));
                })
        );
}
~~~

This is a **compare-and-swap (CAS)** pattern on the old hash, not a complete R2DBC example. A real repository must ensure `updateHashIfCurrentMatches` is an atomic database operation; never split checking and updating into two unconditional SQL statements.

In particular, if a user concurrently changes their password on another device, a login using the old password **must not** overwrite the new password's hash. CAS detects concurrent modifications; application policy decides whether to request a retry or re-login.

A practical rollout control is tracking user counts by **algorithm/version ID**, counting upgrade successes/failures, measuring latency, and monitoring the share of users still on weak hashes. Never send individual hashes or raw passwords to dashboards.

## 13. Common Mistakes with DelegatingPasswordEncoder

| Mistake | Why It Is Wrong | Fix |
| --- | --- | --- |
| Storing bare BCrypt hashes with default Delegating | Lacks `{id}` to select mapping | Controlled format migration or legacy adapter |
| Using `{noop}` for real users | Stores cleartext passwords | Use adaptive hashing; eliminate legacy records |
| `encode(raw).equals(stored)` | Hashes use random salts | Use `matches(raw, stored)` |
| Converter/controller builds an authenticated token before `matches` runs | Bypasses authentication | Let the manager verify before granting authentication |
| Calling `upgradeEncoding` and assuming DB updates automatically | Method only returns a boolean | Requires `encode(raw)` and a persistence service |
| Updating the hash even when raw password is wrong | Attackers can corrupt accounts | Upgrade only after successful authentication |
| Prepending `{bcrypt}` to every legacy hash blindly | Misidentifies algorithms | Inventory formats and migrate verified cohorts |
| Setting an overly broad fallback for unknown IDs | Masks corrupted data, enables downgrades | Restrict valid IDs, reject unknown formats |
| Deleting old mappings immediately after deploy | Un-upgraded accounts cannot log in | Rolling migration before narrowing mappings |
| Picking high cost without measuring | Login CPU/memory stalls, DoS risk | Benchmark under concurrency and SLAs |
| Running heavy encode/matches on the event loop | Degrades request handling capacity | Use a reactive manager/controlled scheduler |
| Logging hashes or passwords | Leaks secrets or user metadata | Log non-sensitive technical state only |
| Confusing Spring Security Reactive with Servlet | Misconfigured manager/user service | Use `ReactiveUserDetailsService` and `ReactiveUserDetailsPasswordService` |
| Calling `subscribe()` manually inside password update | Breaks error/cancellation/transaction flow | Return `Mono<UserDetails>` for the manager to compose |
| Treating hash upgrade as a password reset | Does not rotate a leaked secret | Define clear rules for forcing actual password changes |

A failure must be clearly classified: **wrong password**, **malformed/unknown-ID hash**, **unreachable data store**, **failed upgrade write**, and **locked account** are distinct causes. Public responses must avoid over-disclosure while internal observability needs enough detail to act on the true root cause.

## 14. Practical Phased Migration Process

### Phase A — Audit and Policy Definition

1. Identify all account sources and stored hash formats.
2. Count records by ID or format group without exposing passwords/hashes.
3. Choose the target algorithm/cost based on real benchmarks, security requirements, and operational capacity.
4. Identify accounts that cannot upgrade without logging in, alongside a reset policy.
5. Prepare monitoring, rollback, and concurrent-modification handling.

### Phase B — Deploy Readers First, Writers Second

6. Deploy code capable of reading **both old and new hashes** across all instances.
7. Add `PasswordEncoder` mappings and test both allowed and disallowed IDs.
8. Implement/configure `ReactiveUserDetailsPasswordService` with atomic updates.
9. Only after ensuring all instances can read the new ID, enable generating new hashes or opportunistic upgrades.
10. Measure authentication failures, update conflicts, latency, and hashing errors.

### Phase C — Gradual Upgrades and Cleanup

11. Valid logins upgrade hashes within the same trusted pipeline.
12. Long-inactive users follow a notification/password-reset program per policy.
13. Once no records require the legacy scheme, remove the weak mapping to shrink the attack surface.
14. Verify backups, restores, reporting, and admin tools also understand the new format.
15. Never assume "100% upgraded" just because `upgradeEncoding` is in code; measure actual data.

**For `{noop}` or very weak hashes that ever appeared in a real environment**, assess credential exposure risk and consider **forcing password changes**, rather than treating post-login rehashing as a complete remediation.

## 15. Test Cases Every WebFlux Application Should Have

| Case | Outcome to Verify |
| --- | --- |
| Newly registered / password-changed user | Stores only active policy's `{id}`; no plaintext |
| Legacy user with `{bcrypt}` and right password | Login succeeds; upgrades if policy/cost requires |
| Legacy user with another supported format | Login succeeds; persists new hash when eligible |
| Wrong password | Authentication fails; hash unchanged |
| Missing/unknown `{id}` | Fails safely on configuration/format error; no permissive fallback |
| Two concurrent logins | Updates do not overwrite each other or overwrite a password change |
| User changes password mid-upgrade | Old password is not restored |
| Database connection lost during update | Fails per policy, monitored, data uncorrupted |
| One old instance, one new instance in rolling deploy | Both read new format before new hashes are written |
| Password hash upgraded, yet role denied | Authorization remains independent; not a hash bug |
| High login load | Rate limiting, resource balance, no WebFlux event-loop blocking |
| Password reset after credential leak | Secret and session/token policy rotated, not just rehashed |

For end-to-end WebFlux testing, use `WebTestClient` with a proper security chain and a user store whose before/after state can be observed. Unit-testing `PasswordEncoder` alone is insufficient to validate endpoints, login filters, or database persistence.

### 15.1. How Do 401 and 403 Relate?

- **401 Unauthorized:** missing or unverifiable credentials (with APIs whose entry point returns 401).
- **403 Forbidden:** the user holds a valid authentication yet lacks the required permission.
- Hash upgrades affect **password verification**, never granting `ADMIN` or bypassing role/ownership checks.

If a user logs in yet still gets 403, do not change `PasswordEncoder` or inject extra authorities in a converter to "fix the error".

## 16. Self-Check Questions and Answers

**Question 1.** How do `{bcrypt}` and `$2a$10$...` differ?

> `{bcrypt}` is the `DelegatingPasswordEncoder` ID for selecting an encoder; `$2a$10$...` is the BCrypt-formatted payload holding algorithm-specific metadata such as cost and salt.

**Question 2.** Why shouldn't you compare `encoder.encode(input)` against the stored hash using `equals`?

> Adaptive password hashes normally generate a random salt on every encode call. `matches(raw, stored)` is the right verification API.

**Question 3.** When a hash has ID `{unknown}`, why can `matches` throw `IllegalArgumentException`?

> By default there is no corresponding encoder in the mapping. This differs from a wrong password against a validly formatted hash.

**Question 4.** Does `upgradeEncoding(stored)` returning `true` modify the database automatically?

> No. You must verify the raw password, generate a new hash via `encode(raw)`, and persist it via a reliable update mechanism.

**Question 5.** In Spring Security Reactive, which interface is responsible for persisting upgraded hashes?

> `ReactiveUserDetailsPasswordService`, typically configured on the reactive authentication manager. In demos, `MapReactiveUserDetailsService` implements this contract.

**Question 6.** Can an old BCrypt hash lacking `{bcrypt}` have the prefix added without the raw password?

> Only when there is reliable proof that the payload is valid BCrypt. That is metadata normalization, not creating a new hash.

**Question 7.** Why shouldn't `setDefaultPasswordEncoderForMatches(NoOpPasswordEncoder...)` be set system-wide?

> Because any missing/unknown ID could route through a dangerous fallback, masking data errors and allowing insecure credentials to be accepted.

**Question 8.** Does upgrading the hashing scheme fix a raw password that was already leaked in the past?

> No. Assess risk, and consider forcing a password reset, revoking sessions/tokens, and applying additional controls.

**Question 9.** Why shouldn't you upgrade hashes inside a background task spawned with manual `subscribe()`?

> Because it detaches authentication, data persistence, error/cancellation handling, and ordering guarantees. Compose the password service's publisher into the authentication flow.

**Question 10.** When migrating from `bcrypt` to a new Argon2 policy, in what order should mappings be rolled out?

> Ensure all instances can read both old and new IDs first; only then allow encoding with the new ID, monitor migration progress, and remove the old ID once remaining records are resolved.

## 17. Summary

`DelegatingPasswordEncoder` solves **multi-version password** support by separating the **algorithm used to create new hashes** from the **algorithms used to verify stored hashes**. The `{id}` prefix routes matching; it is not a salt, not encryption, and does not make passwords safe if the underlying algorithm is weak.

Three statements worth remembering:

~~~java
String newStoredHash = encoder.encode(rawPassword);
boolean passwordIsCorrect = encoder.matches(rawPassword, storedHash);
boolean needsUpgrade = encoder.upgradeEncoding(storedHash);
~~~

To complete migration in Spring Security Reactive, chain **successful authentication → upgrade evaluation → re-hashing → durable persistence via `ReactiveUserDetailsPasswordService`**, ensuring concurrent changes are not overwritten, avoiding hashing on the event loop, and maintaining a strategy for accounts that do not log in for long periods.

### Official Reference Documentation

- Spring Security Reference — Password Storage: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Spring Security Javadoc — DelegatingPasswordEncoder: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/DelegatingPasswordEncoder.html
- Spring Security Javadoc — PasswordEncoderFactories: https://docs.spring.io/spring-security/site/docs/6.4.5/api/org/springframework/security/crypto/factory/PasswordEncoderFactories.html
- Spring Security Javadoc — AbstractUserDetailsReactiveAuthenticationManager: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AbstractUserDetailsReactiveAuthenticationManager.html
- Spring Security Javadoc — ReactiveUserDetailsPasswordService: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/ReactiveUserDetailsPasswordService.html
- Spring Security Javadoc — MapReactiveUserDetailsService: https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/core/userdetails/MapReactiveUserDetailsService.html
- Spring Security Javadoc — BCryptPasswordEncoder: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/crypto/bcrypt/BCryptPasswordEncoder.html
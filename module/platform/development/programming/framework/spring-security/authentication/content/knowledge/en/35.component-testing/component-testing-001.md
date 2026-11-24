# Testing PasswordEncoder and Compatibility with Stored Password Hashes in Spring Security

## 1. Lesson Objectives

Java applications using Spring Security typically store **password hashes** in the database, not original passwords. After years of operation, the data may include different algorithm versions or parameters: bcrypt cost 10, bcrypt cost 12, legacy PBKDF2, Argon2, or some legacy records without an algorithm prefix.

A change in the `PasswordEncoder` bean can prevent **existing users from logging in**, even when the password they enter is completely correct. More dangerously, a "quick fix" using a `noop` fallback can inadvertently accept plaintext, weakening the security of the entire system.

The topic **"Testing PasswordEncoder and compatibility with stored password hashes"** requires testing all three directions:

1. **Generating new hashes:** `encode(rawPassword)` produces the format and algorithm according to the current policy.
2. **Verifying stored hashes:** `matches(rawPassword, storedEncodedPassword)` still handles permitted records properly, including older versions.
3. **Safe upgrading:** `upgradeEncoding(storedHash)` and `UserDetailsPasswordService` support rehashing after the **real password has been verified**, rather than changing hashes directly without knowing the raw password.

By the end of this lesson, you will be able to write JUnit 5 tests checking round-trip, salt, wrong passwords, prefixes, legacy hashes, versioned encoders, upgrades, `DaoAuthenticationProvider`, DB storage/retrieval, and error cases. Examples are compatible with **Java 17+ / Spring Security 6.x**. The lesson includes a Java 17 program run with `javac/java` to inspect data structure and a Maven project using Spring Security to test actual cryptographic matching.

> **Principle:** Do not test by comparing `encode(raw)` with a stored hash via `String.equals`. Salted algorithms produce different hashes for the same password. Always use `matches(raw, storedHash)` and execute the exact algorithm/version associated with the stored data.

## 2. Distinguishing encode, matches, and upgradeEncoding

The `org.springframework.security.crypto.password.PasswordEncoder` interface has three main operations:

~~~java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);
    boolean matches(CharSequence rawPassword, String encodedPassword);
    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
~~~

The snippet above illustrates the nature of the API, **not a source file for defining your own interface**. Import and use the interface from the Spring Security dependency.

### 2.1. `encode`: creating a storage representation

~~~text
rawPassword = "a-strong-password"
          |
          v
BCryptPasswordEncoder.encode(rawPassword)
          |
          v
"$2a$12$..."  (salt + cost embedded in the bcrypt format)
~~~

With `DelegatingPasswordEncoder`, the typical output is:

~~~text
{bcrypt}$2a$12$xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
^^^^^^^^  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  id                  bcrypt payload, including version/cost/salt/hash
~~~

The string above is only an **illustrative shape**, not a valid bcrypt hash to put into a database.

The hash **does not need to be identical** across two `encode` calls. BCrypt generates a random salt, so calling `encode("secret")` multiple times can yield different strings, yet every string must still verify against the same original password.

### 2.2. `matches`: verification, not decryption

~~~java
boolean ok = encoder.matches(rawSubmittedPassword, hashReadFromDatabase);
~~~

- `rawSubmittedPassword` is the credential the user just entered at login.
- `hashReadFromDatabase` is the string stored from a previous signup/password change.
- `matches` selects the algorithm, reads the salt/cost/parameters from the stored format, and checks it.
- There is no operation to "decrypt bcrypt back to the original password".

Correct test:

~~~java
String stored = encoder.encode("Correct-Horse-42!");
assertTrue(encoder.matches("Correct-Horse-42!", stored));
assertFalse(encoder.matches("Wrong-Horse-42!", stored));
~~~

Incorrect test:

~~~java
String stored = encoder.encode("Correct-Horse-42!");
// Do not use: salted bcrypt/PBKDF2 can generate a different hash each time.
assertEquals(stored, encoder.encode("Correct-Horse-42!"));
~~~

### 2.3. `upgradeEncoding`: a signal, not an automatic DB change

`upgradeEncoding(storedHash)` returns `true` when the encoder considers that the hash should be regenerated under the new policy. For example:
- old data has `{pbkdf2@SpringSecurity_v5_8}` while the new version generates `{bcrypt}`;
- a bcrypt hash has a lower cost than the current encoder's cost (implementation-dependent);
- the stored hash has an ID different from `idForEncode`.

**Do not assume that merely calling `upgradeEncoding()` changes the hash in the DB.** You need a mechanism that has the valid raw password (typically after a successful login), creates a new hash, and writes it back using `UserDetailsPasswordService` or an appropriate migration service.

## 3. Storage Format of DelegatingPasswordEncoder

Spring Security provides `PasswordEncoderFactories.createDelegatingPasswordEncoder()`. `DelegatingPasswordEncoder` stores data following the pattern:

~~~text
{id}encodedPassword
~~~

Examples:

| Hash stored in DB | Interpretation | Notes |
|---|---|---|
| `{bcrypt}$2a$10$...` | Bcrypt, cost 10 | Delegates to `BCryptPasswordEncoder` |
| `{bcrypt}$2b$12$...` | Bcrypt, cost 12 | Algorithm/cost checked during matches |
| `{pbkdf2@SpringSecurity_v5_8}...` | PBKDF2 with Spring Security 5.8 profile parameters | Requires matching the versioned ID |
| `{scrypt@SpringSecurity_v5_8}...` | scrypt with a specific versioned profile | Requires corresponding dependency/parameters |
| `{argon2@SpringSecurity_v5_8}...` | Versioned Argon2 profile | Requires supporting library, such as Bouncy Castle depending on build |
| `$2a$10$...` | Raw bcrypt **without** `{bcrypt}` prefix | Default delegating encoder may report unmapped ID `null` |
| `{unknown}...` | Unknown or unconfigured ID | Must reject, do not guess |
| `{noop}plaintext` | Plaintext record per legacy mapping | **Do not use as a production solution** |

**Critically important:** `PasswordEncoderFactories.createDelegatingPasswordEncoder()` in Spring Security 6.5 contains **historical** mappings for compatibility, including `noop`, MD4/MD5, and several legacy formats. That **does not mean those algorithms are safe for creating new passwords or should continue allowing logins forever**.

In systems requiring a strict allowlist, create a `DelegatingPasswordEncoder` with **only the approved IDs**, instead of using all default mappings. Identifiers and policies for legacy hashes must be based on **data inventory and a migration contract**, rather than trusting any prefix as valid merely because the library knows how to match it.

### 3.1. `{id}` is not a secret

Having the ID and cost/iteration parameters appear publicly in the hash is normal. Security does not rely on hiding the algorithm name; it relies on an appropriate algorithm, salt, work factor, password strength, and DB access protection.

### 3.2. How important are Versioned IDs?

For example, two PBKDF2 profiles within the same algorithm family can use different iteration counts, salt lengths, key lengths, or PRFs. If you change the mapping of an ID `pbkdf2` currently used in the DB to a new profile without changing the ID, old records may **no longer match**.

Appropriate pattern:
- `{pbkdf2@SpringSecurity_v5_8}` preserves the meaning of the old profile;
- new records use the current ID/algorithm;
- test fixtures cover both classes of data;
- after successful authentication, hashes can be rehashed to the new ID.

**The ID name is a storage contract**, not just a display label.

## 4. How Spring Security Checks Passwords in the Login Flow

In the Servlet stack, `DaoAuthenticationProvider` uses `UserDetailsService` to load the user and `PasswordEncoder` to verify the password:

~~~text
POST /login (raw password)
         |
         v
UsernamePasswordAuthenticationFilter
         |
         v
AuthenticationManager / ProviderManager
         |
         v
DaoAuthenticationProvider
         |
         +-- UserDetailsService.loadUserByUsername(username)
         |       |
         |       v
         |   UserDetails.getPassword()
         |       |
         |       v
         +-- PasswordEncoder.matches(raw, storedHash)
         |
         +-- check account status + policy
         |
         +-- is upgradeEncoding needed?
         |       |
         |       v
         |   UserDetailsPasswordService.updatePassword(user, newHash)
         |
         v
Authenticated principal or failure
~~~

In practice, the order of pre/post authentication checks and password upgrades depends on the provider implementation; the diagram shows **responsibilities** rather than the full call stack.

- If the password is wrong, the hash must not be updated.
- If the stored hash lacks a mapping or is invalid, it must not fall back to plaintext comparison.
- If the password is correct and upgrades are supported, the provider can generate a new hash and invoke `UserDetailsPasswordService`.
- Hash updates need transaction/concurrency protection (especially if the user just changed their password in another session).

**Spring Security does not automatically fix old data just because you add a PasswordEncoder bean.** In a real database, `UserDetailsPasswordService` must actually update the record; it cannot just return a mock `UserDetails` without persisting.

## 5. Why "Stored Hashes" Are Hard to Keep Compatible

Some common mistakes when upgrading or switching services:

1. **Missing prefix:** previously used `BCryptPasswordEncoder` directly, creating `$2a$...`; later switched to `DelegatingPasswordEncoder`, which expects `{bcrypt}`.
2. **Using the wrong ID:** data is bcrypt but `{pbkdf2}` is prepended, leading to a mismatched verifier.
3. **Truncation in the DB:** a `VARCHAR(60)` column once held 60-character raw bcrypt, but the `{bcrypt}` prefix makes it longer; versioned Argon2/scrypt are even longer.
4. **Changed algorithm profile:** same PBKDF2 name but different iterations/PRF/salt.
5. **Charset inconsistency:** a legacy encoder hashed bytes using a charset other than UTF-8; Java Unicode must be handled according to the contract.
6. **Canonicalization inconsistency:** Java/service A trims or normalizes passwords, while service B keeps the raw input. Passwords should normally be treated **as verbatim secrets**; do not automatically `trim()`/`toLowerCase()`.
7. **Malformed brace prefix:** `{bcrypt}`, `{BCRYPT}`, and `{bcrypt ` are not equivalent unless mappings are explicitly defined.
8. **Switching from password hashing to encryption:** these are two different approaches; you cannot decrypt bcrypt to migrate to a new algorithm.
9. **Missing pepper:** if legacy PBKDF2 used an external secret/pepper outside the DB and that secret is lost, old passwords cannot be verified from the hash alone.
10. **Different supporting libraries/algorithms:** Argon2 and scrypt may require different dependencies/providers and configurations.
11. **Long secret truncation:** traditional bcrypt limits effective input to about 72 bytes; long-password compatibility must be tested separately when migrating from bcrypt to another algorithm.
12. **Schema change without migrating user service:** the DB already has prefixed hashes, but the ORM/mapper strips `{...}` or uses the wrong column.

The solution is to **inventory and test with real approved fixtures** before changing configuration, rather than trying to guess the algorithm at login based on the password or allowing all fallbacks.

## 6. Minimum Test Matrix for PasswordEncoder

| Test case | Input and stored hash | Expectation |
|---|---|---|
| Round-trip | `raw` and `encode(raw)` | `matches` true |
| Wrong password | `otherRaw` vs storedHash | false |
| Salt | Encoding the same raw twice | Two different strings, both match true |
| New format | Newly encoded hash | Starts with an approved ID, e.g., `{bcrypt}` |
| Prefixed bcrypt legacy | `{bcrypt}` + bcrypt cost 10 | matches true |
| Unprefixed bcrypt legacy | `$2a$10$...` | matches true **only if migration policy allows** |
| Versioned PBKDF2 | `{pbkdf2@SpringSecurity_v5_8}` + valid payload | matches true |
| Unknown ID | `{evil}...` | Fail closed |
| Plaintext | `password123` | Fail closed |
| `{noop}` | `{noop}password123` | Fail closed with strict allowlist |
| Wrong prefix | `{pbkdf2}` + bcrypt payload | Fail closed |
| Truncated bcrypt | Stored hash missing tail | Fail closed |
| Legacy wrong algorithm | Raw MD5 tagged with bcrypt ID | Fail closed |
| Upgrade old ID | Stored PBKDF2, current encode bcrypt | `upgradeEncoding` true |
| Upgrade old cost | BCrypt cost 10, current strength 12 | `upgradeEncoding` true if provider supports it |
| No upgrade current | Current BCrypt cost 12 | `upgradeEncoding` false |
| Dao auth with legacy | UserDetails returns old hash and correct raw | Auth success, migration if configured |
| Dao auth wrong password | Old hash and wrong raw | Auth fail, **do not** change hash |
| Concurrent migration/reset | Two sessions update the same account | Do not overwrite newer password |
| Database round-trip | Serialize/deserialize hash through DB | String preserved verbatim, matches still true |

**Prioritize running both unit tests and integration tests.** Unit tests for the encoder help catch algorithm/mapping bugs; database integration tests reveal short columns, ORM trimming, collation, transactions, and update issues.

## 7. Standalone Java 17 Example: Inspecting Stored Data Structure

The following program **does not test passwords and does not use Spring**. It illustrates a safe inventory step: determining whether a string has a *structurally* valid `{id}` prefix or looks like raw bcrypt. This is **not cryptographic verification**, only classification for migration planning.

File `StoredHashInspector.java`:

~~~java
import java.util.regex.Pattern;

public final class StoredHashInspector {

    private static final Pattern BCRYPT_SHAPE = Pattern.compile(
            "^\\$2[aby]\\$(0[4-9]|[12][0-9]|3[01])\\$" +
            "[./A-Za-z0-9]{53}$");

    public static String classify(String stored) {
        if (stored == null || stored.isEmpty()) {
            return "EMPTY";
        }
        if (stored.startsWith("{")) {
            int closing = stored.indexOf('}');
            if (closing <= 1 || closing == stored.length() - 1) {
                return "MALFORMED_PREFIX";
            }
            String id = stored.substring(1, closing);
            String payload = stored.substring(closing + 1);
            if ("bcrypt".equals(id)) {
                return BCRYPT_SHAPE.matcher(payload).matches()
                        ? "PREFIXED_BCRYPT_SHAPE" : "MALFORMED_BCRYPT";
            }
            if ("pbkdf2@SpringSecurity_v5_8".equals(id)) {
                return "VERSIONED_PBKDF2_UNVERIFIED";
            }
            return "UNAPPROVED_ID";
        }
        return BCRYPT_SHAPE.matcher(stored).matches()
                ? "LEGACY_BCRYPT_SHAPE" : "UNRECOGNIZED";
    }

    public static void main(String[] args) {
        String illustrativeBcrypt = "$2a$10$"
                + "a".repeat(53);
        System.out.println(classify("{bcrypt}" + illustrativeBcrypt));
        System.out.println(classify(illustrativeBcrypt));
        System.out.println(classify("{noop}secret"));
        System.out.println(classify("secret"));
        System.out.println(classify("{bcrypt}broken"));
        System.out.println(classify(null));
    }
}
~~~

Compile/run:

~~~bash
javac StoredHashInspector.java
java StoredHashInspector
~~~

**Exact stdout:**

~~~text
PREFIXED_BCRYPT_SHAPE
LEGACY_BCRYPT_SHAPE
UNAPPROVED_ID
UNRECOGNIZED
MALFORMED_BCRYPT
EMPTY
~~~

The string `"a".repeat(53)` only simulates valid length/characters to check **structure**, not a hash generated from a real password. The program **cannot prove a hash is cryptographically valid**. Do not use `classify()` as `matches()` or as a condition for granting login.

## 8. Spring Security 6.5 Maven Project: Allowlist Encoder and JUnit Tests

The goal is to create **a component testing project without needing to start a web server**. `PasswordEncoderConfiguration` is a reusable configuration for a Spring Boot application; JUnit instantiates the configuration directly to test logic without running a servlet container.

### 8.1. Structure

~~~text
password-compatibility-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/password/
    │   └── PasswordEncoderConfiguration.java
    └── test/java/com/example/password/
        └── PasswordEncoderCompatibilityTest.java
~~~

### 8.2. Complete `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>password-compatibility-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

Spring Boot 3.5.x manages compatible Spring Security 6.5.x dependencies; use Maven/Java 17+. The POM file does not need `spring-boot-maven-plugin` because we are only running component tests here, **not packaging a Spring Boot main application**.

### 8.3. `PasswordEncoderConfiguration.java`: strict default

~~~java
package com.example.password;

import java.util.Map;
import java.util.regex.Pattern;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.DelegatingPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.crypto.password.Pbkdf2PasswordEncoder;

@Configuration
public class PasswordEncoderConfiguration {

    @Bean
    public PasswordEncoder passwordEncoder() {

        Map<String, PasswordEncoder> approved = Map.of(
                "bcrypt", new BCryptPasswordEncoder(12),
                "pbkdf2@SpringSecurity_v5_8",
                    Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8()
        );

        DelegatingPasswordEncoder encoder =
                new DelegatingPasswordEncoder("bcrypt", approved);

        // Only support inventoried legacy raw bcrypt,
        // DO NOT fall back to NoOp or any unknown ID.
        encoder.setDefaultPasswordEncoderForMatches(
                new LegacyBcryptOnly());
        return encoder;
    }

    private static final class LegacyBcryptOnly
            implements PasswordEncoder {

        private static final Pattern BCRYPT = Pattern.compile(
                "^\\$2[aby]\\$(0[4-9]|[12][0-9]|3[01])\\$"
                + "[./A-Za-z0-9]{53}$");

        private final BCryptPasswordEncoder bcrypt =
                new BCryptPasswordEncoder();

        @Override
        public String encode(CharSequence rawPassword) {
            throw new UnsupportedOperationException(
                    "Legacy encoder must never issue new hashes");
        }

        @Override
        public boolean matches(
                CharSequence rawPassword, String stored) {
            if (rawPassword == null || stored == null
                    || !BCRYPT.matcher(stored).matches()) {
                return false;
            }
            return bcrypt.matches(rawPassword, stored);
        }
    }
}
~~~

**Mechanism:**
- `idForEncode="bcrypt"` ⇒ all **new** passwords are encoded with bcrypt strength 12 and the `{bcrypt}` prefix.
- Hashes carrying `{bcrypt}` ⇒ matched by the BCrypt encoder, including previous cost 10 hashes (cost is embedded in the hash).
- `{pbkdf2@SpringSecurity_v5_8}` hashes ⇒ delegated to the exact PBKDF2 profile (since it is approved).
- Legacy hashes like `$2a$...` without a prefix ⇒ fallback accepts **only valid raw bcrypt structure** and performs real bcrypt verification.
- `{noop}secret`, `{unknown}...`, `plaintext` hashes ⇒ invalid, **fail closed**.
- `LegacyBcryptOnly.encode()` is forbidden; the fallback is a **one-way verification path**, not a path for issuing new credentials.

**Note on `setDefaultPasswordEncoderForMatches`:** the fallback receives the **entire** `encodedPassword` string when the ID has no mapping, not just the part after `{id}`. Therefore, it must strictly validate the raw bcrypt string itself. Do not set the fallback to `NoOpPasswordEncoder` or a BCrypt decoder that skips format validation if doing so could cause unknown IDs to be treated as valid.

In real production, if the DB has no legacy raw bcrypt, **no fallback is needed**: use an encoder with an allowlist and let unmatched IDs fail closed. If other legacy algorithms exist, add the exact required profiles during migration and remove them after upgrading.

### 8.4. JUnit 5: testing PasswordEncoder and compatibility

File `src/test/java/com/example/password/PasswordEncoderCompatibilityTest.java`:

~~~java
package com.example.password;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.Authentication;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.crypto.password.Pbkdf2PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

import static org.junit.jupiter.api.Assertions.*;

class PasswordEncoderCompatibilityTest {

    private final PasswordEncoder encoder =
            new PasswordEncoderConfiguration().passwordEncoder();

    private static final String RAW = "S3cret-for-tests-2026!";

    @Test
    void newPasswordHasApprovedPrefixAndMatches() {
        String stored = encoder.encode(RAW);

        assertTrue(stored.startsWith("{bcrypt}$2"));
        assertTrue(encoder.matches(RAW, stored));
        assertFalse(encoder.matches("wrong-password", stored));
    }

    @Test
    void saltMakesEncodedStringsDifferent() {
        String first = encoder.encode(RAW);
        String second = encoder.encode(RAW);

        assertNotEquals(first, second);
        assertTrue(encoder.matches(RAW, first));
        assertTrue(encoder.matches(RAW, second));
    }

    @Test
    void legacyBcryptWithoutPrefixStillMatches() {
        String legacy =
                new BCryptPasswordEncoder(10).encode(RAW);

        assertTrue(encoder.matches(RAW, legacy));
        assertFalse(encoder.matches("wrong-password", legacy));
        assertTrue(encoder.upgradeEncoding(legacy));
    }

    @Test
    void prefixedOldBcryptCostStillMatches() {
        String oldCost =
                "{bcrypt}" + new BCryptPasswordEncoder(10).encode(RAW);

        assertTrue(encoder.matches(RAW, oldCost));
        assertTrue(encoder.upgradeEncoding(oldCost));
    }

    @Test
    void versionedPbkdf2FromApprovedProfileStillMatches() {
        PasswordEncoder previous =
                Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8();

        String oldStored = "{pbkdf2@SpringSecurity_v5_8}"
                + previous.encode(RAW);

        assertTrue(encoder.matches(RAW, oldStored));
        assertFalse(encoder.matches("wrong-password", oldStored));
        assertTrue(encoder.upgradeEncoding(oldStored));
    }

    @Test
    void currentEncodingDoesNotRequireUpgrade() {
        String current = encoder.encode(RAW);

        assertTrue(encoder.matches(RAW, current));
        assertFalse(encoder.upgradeEncoding(current));
    }

    @Test
    void plaintextAndUnapprovedIdsMustFailClosed() {
        assertFalse(encoder.matches(RAW, RAW));
        assertFalse(encoder.matches(RAW, "{noop}" + RAW));
        assertFalse(encoder.matches(RAW, "{unknown}" + RAW));
        assertFalse(encoder.matches(RAW, "{md5}123"));
        assertFalse(encoder.matches(RAW, "{bcrypt}broken"));
    }

    @Test
    void legacyBcryptDoesNotAcceptWrongPrefix() {
        String bcrypt =
                new BCryptPasswordEncoder(10).encode(RAW);

        assertFalse(encoder.matches(
                RAW, "{pbkdf2@SpringSecurity_v5_8}" + bcrypt));
        assertFalse(encoder.matches(RAW, bcrypt.substring(0, 20)));
    }

    @Test
    void daoProviderCanUpgradeVerifiedLegacyPassword() {

        String legacy = new BCryptPasswordEncoder(10).encode(RAW);

        UserDetails user = User.withUsername("alice")
                .password(legacy)
                .roles("USER")
                .build();

        InMemoryUserDetailsManager store =
                new InMemoryUserDetailsManager(user);

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(store);
        provider.setPasswordEncoder(encoder);
        provider.setUserDetailsPasswordService(store);

        Authentication verified = provider.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "alice", RAW));

        assertTrue(verified.isAuthenticated());

        String updated = store.loadUserByUsername("alice")
                .getPassword();

        assertTrue(updated.startsWith("{bcrypt}"));
        assertTrue(encoder.matches(RAW, updated));
        assertNotEquals(legacy, updated);
    }

    @Test
    void badPasswordDoesNotTriggerMigration() {

        String old = new BCryptPasswordEncoder(10).encode(RAW);

        UserDetails user = User.withUsername("bob")
                .password(old)
                .roles("USER")
                .build();

        InMemoryUserDetailsManager store =
                new InMemoryUserDetailsManager(user);

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(store);
        provider.setPasswordEncoder(encoder);
        provider.setUserDetailsPasswordService(store);

        assertThrows(BadCredentialsException.class,
                () -> provider.authenticate(
                        UsernamePasswordAuthenticationToken
                                .unauthenticated("bob", "WRONG")));

        assertEquals(old, store.loadUserByUsername("bob")
                .getPassword());
    }
}
~~~

**Why are these tests more reliable than checking prefixes visually?**
- Executes `matches` against real bcrypt/PBKDF2, not fake verifiers.
- Verifies salting so two encoded strings differ while both still verify.
- Covers **unprefixed** legacy bcrypt and prefixed bcrypt cost 10.
- Disallows `{noop}`, plaintext, or unapproved IDs.
- Checks `upgradeEncoding` for legacy and current hashes.
- `DaoAuthenticationProvider` verifies the user's password and uses `InMemoryUserDetailsManager` (implementing `UserDetailsPasswordService`) to simulate upgrading the hash after login.
- Ensures a wrong password **does not trigger migration**.

Run:

~~~bash
mvn clean test
~~~

**Expectation:** Maven/JUnit runs **10 test methods** with zero failures/errors; exact statistics and execution time depend on the Maven Surefire version and hardware. Generated BCrypt/PBKDF2 hashes are randomized each run, so do not use literal hashes as expected stdout. Check the report in `target/surefire-reports/` and exit code 0. If adding integration tests, separate unit crypto tests from DB tests in the CI pipeline.

**Limitation:** the `DaoAuthenticationProvider` tests above use an **in-memory repository**, which does not prove that a real database can update `password_hash` inside a transaction or that queries match the right version/tenant. The next section covers what to test at the storage layer.

## 9. Why Must Legacy Fallbacks Be Restricted?

A common suggestion when encountering:

~~~text
java.lang.IllegalArgumentException:
  There is no PasswordEncoder mapped for the id "null"
~~~

is adding:

~~~java
delegating.setDefaultPasswordEncoderForMatches(
        NoOpPasswordEncoder.getInstance());
~~~

**This is dangerous in production** because it can accept unformatted records as plaintext passwords. If the DB is altered or has a faulty data import path, you could create a weak login bypass.

### Better options in priority order

1. **Investigate formats first:** gather statistics on stored hash shapes (ID, length, pattern; never log raw hashes) from an authorized data source and cross-check system history.
2. **If certain all raw hashes are bcrypt:** add the `{bcrypt}` prefix via a DB migration **after confirmation**; the bcrypt payload remains unchanged. This is a metadata operation, not a rehash.
3. **If the DB has multiple types:** use `DelegatingPasswordEncoder` with an allowlist mapping and fixtures for each ID; validate legacy raw strings with a very strict regex like in the example.
4. **If passwords were stored as plaintext or weak hashes:** plan deprecation, time-limit verification, and support reset/re-auth and risk-based migration; do not declare a weak factor safe just because it has a prefix.
5. **Unknown algorithm or lost pepper:** do not guess by randomly trying decoders; require a valid password reset/re-enrollment.

**Do not assign `{bcrypt}` to an arbitrary string that merely looks like Base64/hex**. Length, cost, and regex are only structural evidence; proper verification requires testing with an approved fixture password and the actual algorithm.

## 10. Compatibility When Changing the BCrypt Work Factor

BCrypt embeds version and cost information inside the hash:

~~~text
$2a$10$.....................................................
 ^   ^^
 |   └─ cost = 10
 └──── version identifier
~~~

If the application issues new passwords with cost 12, a compatible bcrypt verifier **can typically still verify cost 10 hashes**, because the record's cost and salt are embedded in the payload. `BCryptPasswordEncoder(12).upgradeEncoding(oldCost10)` can return true, whereas current cost 12 needs no further upgrade.

**Performance testing note:** cost grows exponentially; do not change cost 10→16 in production just because "higher is better". Measure p95/p99 latency, CPU, and load during peak logins/credential stuffing. Spring Security recommends tuning adaptive one-way functions to your hardware and threat model; roughly one second per verification is a documentation reference point, not an SLA for every system.

### 10.1. Hash length and DB column

Common raw BCrypt is 60 ASCII characters long; adding `{bcrypt}` makes it **68 characters**. If the current column is `VARCHAR(60)`, prefix migration or switching algorithms can cause errors or truncation.

Safe steps:
1. Check the schema and constraints of `password_hash`.
2. Expand to `VARCHAR(255)` or `TEXT` per application data standards, avoiding arbitrary small limits.
3. Deploy a reader that supports both old and new formats.
4. Migrate data in transactions/batches and record row counts.
5. Verify with fixtures after a database round-trip, not just in-memory.
6. Only enable the new writer after every replica can read the new format.

Do not blindly apply `LEFT(password_hash, 60)` or truncate strings to fit the schema; a truncated hash cannot verify properly.

## 11. PBKDF2, scrypt, and Argon2 Compatibility

BCrypt is a popular choice, but systems may have PBKDF2/scrypt/Argon2. The algorithm name alone **is not enough** to preserve compatibility:

| Type | Parameters to preserve | Common migration errors |
|---|---|---|
| PBKDF2 | PRF/HMAC, iteration count, derived key length, salt length, secret/pepper | Using a new mapping for old hashes; losing the pepper |
| scrypt | CPU/memory parameters, salt, output length | Using a different version profile or missing dependency |
| Argon2 | Argon2id/variant, memory, iterations, parallelism, salt, version | Changing parameters/version or missing Bouncy Castle |
| BCrypt | Version, cost, salt, input byte policy | DB string truncation or inconsistent long-password handling |

**Store the version ID** in the password hash field or metadata if the library's format does not self-encode all parameters. In Spring Security, versioned mappings like `pbkdf2@SpringSecurity_v5_8` illustrate how to retain an old verification profile while generating new hashes with a new algorithm/approach.

### 11.1. Cross-algorithm migration plan

A low-disruption approach:
- Read path: accept existing **approved** IDs.
- Write path: only `encode` using the current algorithm/profile.
- Successful login: check `upgradeEncoding`, rehash the just-verified raw password, and persist.
- Password reset/change: always use the new writer, never copy the old format.
- Once a large percentage of users have migrated, set a sunset date for legacy support and force a reset for un-upgraded accounts.
- Do not remove the old verifier before no records require it, or before an account recovery strategy is in place.

### 11.2. Why not rehash directly from the old hash?

Wrong:

~~~text
newHash = BCrypt( oldHash )
~~~

If that becomes the new stored password, then at login the user enters the raw password, the verifier checks BCrypt(rawPassword, newHash), and it **does not match**. You cannot obtain the raw password from the old hash. Only rehash when a valid password is supplied during login/change-password/reset. Otherwise, require the user to reset their password via a secure workflow.

### 11.3. Compatibility with data from other systems

A DB from PHP/Node/Python may use bcrypt but differ in:
- how Unicode is encoded into bytes;
- password trimming/normalization policy;
- the 72-byte bcrypt limit or pre-hashing;
- version prefix, cost, and salt;
- database column/serialization behavior.

Before migration, generate fixtures in the source system using **dummy passwords** covering ASCII, Unicode, and boundary lengths, then test Spring `matches`. Never transport real passwords or paste production hashes into public testing tools.

## 12. Database Integration Tests: Preventing Hash Loss from ORM or Schema

Illustrative PostgreSQL schema sample:

~~~sql
CREATE TABLE app_users (
    id               BIGSERIAL PRIMARY KEY,
    username         VARCHAR(150) NOT NULL UNIQUE,
    password_hash    TEXT NOT NULL,
    enabled          BOOLEAN NOT NULL DEFAULT TRUE,
    password_version BIGINT NOT NULL DEFAULT 0,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

This is an **illustrative business schema**. Production may require a tenant ID, audit fields, password-change timestamp, session invalidation mechanisms, and encryption at rest per policy.

### 12.1. Exact string reading and writing

DB tests should:
1. Insert a 60-character raw bcrypt hash and read it back verbatim.
2. Insert a longer `{bcrypt}` hash and read it back verbatim.
3. Insert PBKDF2/Argon2 hashes (if allowed) and read them back verbatim.
4. Never auto-trim, truncate, change case, or normalize characters.
5. Ensure the column does not coerce the hash to a number or apply brace-parsing logic that corrupts it.
6. Ensure proper unique username/tenant mapping without mixing up accounts.
7. Ensure the DB writer only accepts output from the configured `PasswordEncoder`.
8. Roll back if updating the password and audit/session state fails.

### 12.2. Compare-and-set to prevent overwriting a newer password

Suppose a user logs in with an old hash and the system wants to upgrade it. At the same time, they might change their password on another device. Do not execute this update:

~~~sql
UPDATE app_users
   SET password_hash = :newHash
 WHERE username = :username;
~~~

The statement above could overwrite a newer hash **set later by the user** with a hash derived from the old password, resurrecting the old password.

A compare-and-set pattern you can use:

~~~sql
UPDATE app_users
   SET password_hash = :newEncodedHash,
       password_version = password_version + 1,
       updated_at = CURRENT_TIMESTAMP
 WHERE id = :userId
   AND password_hash = :expectedOldEncodedHash
   AND password_version = :expectedOldVersion
   AND enabled = TRUE;
~~~

- If **1 row updated**: migration succeeded against the right version.
- If **0 rows updated**: the data changed or the account was disabled; **do not retry overwriting**, reload/check policy and consider rejecting the stale login session.
- All migration operations use tested transactions and concurrency rules.
- With case-insensitive DB collations, ensure `password_hash` comparison is **byte/case-exact** or rely on a trustworthy version field. A hash is sensitive to every single character.

`UserDetailsPasswordService.updatePassword(UserDetails user, String newPassword)` receives the **encoded newPassword**, while `user.getPassword()` and a business version can serve as CAS conditions. The service should update by the exact user ID/tenant, not merely a self-asserted username, and return the corresponding updated `UserDetails`. This is a SQL example, not a complete standalone Java repository.

## 13. Example UserDetailsPasswordService for a Real DB

This snippet depicts Spring JDBC using `username` and the old hash as conditions. For production, ensure username is unique within the namespace, add version/tenant, transaction, row mapper, and handle authentication success according to policy.

~~~java
// Illustrative snippet inside a @Service that already has JdbcTemplate.
// UserDetailsPasswordService is a Spring Security interface.

@Override
@Transactional
public UserDetails updatePassword(UserDetails user, String newHash) {
    int changed = jdbc.update("""
            UPDATE app_users
               SET password_hash = ?,
                   password_version = password_version + 1,
                   updated_at = CURRENT_TIMESTAMP
             WHERE username = ?
               AND password_hash = ?
               AND enabled = TRUE
            """, newHash, user.getUsername(), user.getPassword());

    if (changed != 1) {
        throw new IllegalStateException(
                "Password changed concurrently or user disabled");
    }

    return User.withUserDetails(user)
            .password(newHash)
            .build();
}
~~~

This is an **integration snippet**, not a standalone runnable file: you must import `@Transactional`, `JdbcTemplate`, `UserDetailsPasswordService`, `UserDetails`, `User`, and inject the repository/JDBC properly. A real application must handle transaction/security exceptions per UX requirements without exposing old/new hashes in logs or HTTP bodies.

**Warning about self-invocation:** if a `@Transactional` method is called directly within the same bean instead of through the Spring proxy, the transaction may not activate. Integration tests should verify actual rollback/concurrency behavior, especially across multi-node logins.

## 14. Rolling Out Password Hashing Configuration Changes Safely

A phased deployment strategy:

### Phase 1 — Inventory (read-only)

- Identify all storage formats from schema/metadata/anonymized stats: ratios of prefixed bcrypt, raw bcrypt, versioned PBKDF2, legacy IDs.
- Obtain fixtures from a test/legacy environment for each type, including Unicode and boundary-length passwords.
- Identify strong/weak algorithms, external pepper/secret dependencies, and library runtime support.
- Measure maximum `password_hash` length and DB/log access permissions.
- Record the count of accounts with unidentifiable formats; do not modify them yet.

### Phase 2 — Compatible Reader

- Deploy `DelegatingPasswordEncoder` with an allowlist of required formats and a strict legacy adapter.
- For a raw-bcrypt-only DB, you can run a `{bcrypt}` prefix migration after testing with fixtures and taking a backup.
- Write tests for both matching and non-matching cases, especially unknown ID/null/malformed.
- Add internal monitoring for the count of logins using legacy formats, **without logging raw hashes/passwords**.

### Phase 3 — New Writer + Rehash-on-Login

- Only generate new hashes using one approved algorithm/profile.
- If `upgradeEncoding` is true after a valid password, save the new hash via a service with CAS/transactions.
- Ensure every replica can **read the new format** before the writer begins issuing it.
- Password change/reset always uses the new writer and invalidates sessions/tokens when required by policy.

### Phase 4 — Cleaning Up Weak Formats

- Monitor migration success rates and dormant accounts.
- For overly weak hashes or ambiguous data, require a password reset rather than keeping `noop`/MD5 indefinitely.
- Remove legacy mappings only when **no** users still need verification under that format or a recovery plan is in place.
- Re-check unauthorized algorithms, rate limits, and performance metrics.

### Phase 5 — Rollback and Investigation

- Have an application rollback plan, but **do not roll back the reader** if the DB already contains hashes created by the new writer that the old reader does not understand.
- Safely log failure categories: unknown prefix, wrong password, disabled account, migration conflict, infrastructure error.
- Set alerts for unusual spikes in login failures right after release; never leak user existence via responses.

## 15. Security Tests to Run Separately from Compatibility Tests

Even when `PasswordEncoder` matches properly, the system can still be attacked:
- Brute force, password spraying, and credential stuffing: require rate limiting, MFA/passkeys, and monitoring.
- User enumeration: login messages/latency for nonexistent usernames vs wrong passwords.
- SQL injection in repository lookup/update: use prepared statements, never concatenate username into queries.
- Hash leakage via logs/exceptions/debugger: never log verbatim passwords/hashes.
- Database exfiltration: restrict access privileges and use adaptive hashing with an appropriate work factor.
- Compromised passwords: check breached passwords on create/change, without sending raw passwords to untrusted services.
- Session fixation/hijacking: protect cookies/sessions and revoke them on password change.
- Timing side-channels: avoid noticeably different behavior that lets attackers tell whether a username exists.
- Resource exhaustion: adaptive hashes consume CPU/memory; rate-limit logins before hashing and per account/source.
- Migration-induced DoS: do not simultaneously rehash millions of users on the request path or run unthrottled CPU-heavy batches.

**Testing that "the right password can log in" covers only part of authentication security.** Compatibility lets legitimate users keep using the service; preventing account takeover requires multiple other layers.

## 16. Failure Scenarios and Diagnosis

| Symptom | Likely cause | Safe resolution |
|---|---|---|
| `There is no PasswordEncoder mapped for id "null"` | Stored hash lacks `{id}` | Inventory, confirm algorithm, and add prefix or strict adapter |
| `There is no PasswordEncoder mapped for id "X"` | Unknown ID | Do not fall back to noop; configure mapping if approved or reset |
| Legacy login fails after PBKDF2 migration | Different version/secret parameters | Preserve exact profile ID and fixtures |
| Signup succeeds but login fails | Writer/reader config mismatch or DB truncation | Test encode→persist→read→matches |
| BCrypt hash length decreased | `VARCHAR` too short or ORM trimming | Expand column, restore from backup if corrupted |
| Only passwords with Vietnamese characters fail | Different encoding/normalization | Check UTF-8/legacy fixtures, do not auto-trim |
| User changed password but old login works again | Migration upgrade race overwrote hash | CAS/version check and session invalidation |
| Test passes only when run alone | Shared mutable state/repository, race | Isolate test fixtures, clean up DB, and test concurrency |
| `upgradeEncoding` does not update DB hash | `UserDetailsPasswordService` not configured | Enable service and test persistence |
| Hash upgraded but subsequent login fails | Service wrote wrong format/ID | Test second login and DB round-trip |
| Unknown ID gets authenticated | Overly broad/`noop` fallback | Strict allowlist, negative tests |
| Increasing bcrypt strength causes timeouts | Unmeasured work factor | Benchmark, tune capacity/rate limiting |

### Mistakes to avoid

1. Comparing `encode(raw).equals(storedHash)`.
2. Calling `encode()` to "verify" a password instead of using `matches()`.
3. Assigning a prefix by guessing before confirming the format.
4. Treating hashes like trivial strings: trimming/lowercasing/truncating.
5. Allowing accidental database truncation when adding `{bcrypt}`.
6. Using `NoOpPasswordEncoder` as a fallback for unprefixed data.
7. Accepting every `{id}` in the factory even when policy forbids it.
8. Changing PBKDF2 parameters while reusing the old versioned ID.
9. Letting new writer code issue hashes before all reader instances can read them.
10. Confusing `upgradeEncoding=true` with having written back to the DB.
11. Rehashing `oldHash` instead of a verified raw password.
12. Overwriting a newer password due to concurrent login/migration.
13. Writing tests with ASCII only, ignoring Unicode/boundary cases.
14. Testing DB behavior with SQLite/in-memory instead of PostgreSQL without testing against the real DB.
15. Reading production passwords or pasting real hashes into external web tools for testing.
16. Assuming login unit tests replace rate limiting/session/authorization checks.
17. Unfairly locking accounts when a migration format bug breaks login for everyone.
18. Lacking safe logs/metrics to detect broken rollbacks after a release.

## 17. CI/CD Matrix and Acceptance Criteria

Minimum checklist before upgrading `PasswordEncoder`:

- [ ] `encode/matches` unit tests: right/wrong passwords, random salt.
- [ ] Every existing stored format has **specific fixtures and tests**.
- [ ] Unknown/unapproved IDs, plaintext, and malformed hashes **fail closed**.
- [ ] Prefixed and legacy data are read using exact contract-compliant mappings.
- [ ] `upgradeEncoding` tested for old/current and does not upgrade invalid hashes.
- [ ] `DaoAuthenticationProvider` authenticates valid legacy credentials and rejects wrong raw passwords.
- [ ] `UserDetailsPasswordService` upgrades after successful login and does not upgrade on wrong password.
- [ ] DB integration test verifies **exact string round-trip** and sufficient column length.
- [ ] Concurrency test verifies migration does not overwrite a newer password change/reset.
- [ ] Performance test tracks login latency/CPU after work-factor changes.
- [ ] Security tests cover rate limiting, anti-enumeration, MFA/passkeys, and session controls.
- [ ] Reader→writer rollout executed in order, with a rollback plan.
- [ ] Never log raw passwords/hashes or test with production credentials.
- [ ] Communication and reset workflow prepared for records that cannot be upgraded.
- [ ] Algorithms/IDs/profiles/versions and legacy format deprecation dates documented.

### Pragmatic acceptance criteria

A release is considered ready when:
1. Logging in with the right password for **all supported data classes** continues to succeed.
2. Wrong logins and all unapproved formats are rejected.
3. New hashes use the current profile; legacy hashes are safely upgraded or have a clear reset path.
4. Data persisted through the DB retains exact bytes/Unicode/format without truncation.
5. No race conditions resurrect old passwords.
6. No passwords are changed erroneously and no credentials leak into logs, test reports, or metrics.
7. CI reliably reproduces the same fixtures and results across Java/Spring Security upgrades.

## 18. Key Takeaways

- **`encode` is for creating/changing passwords; `matches` is for login.** Salting makes two encodings differ while still matching.
- **`{id}hash` is the data contract of `DelegatingPasswordEncoder`.** Proper mappings allow reading multiple generations of password hashes.
- **Raw bcrypt records without a prefix do not mean plaintext.** Handle them only via verified migration or a strictly constrained legacy verifier.
- **Do not use `noop` or weak algorithm mappings as fallbacks.** Tests for unrecognized data must fail closed.
- **`upgradeEncoding` is a signal**; `UserDetailsPasswordService` and transactions/compare-and-set persist the new hash after a valid password.
- **You cannot switch algorithms from `oldHash` without knowing the raw password.** Rehash on successful login or require a password reset.
- **Compatibility must be tested across encoder, provider, and DB.** Testing in-memory alone can miss truncation, serializer issues, or password-overwrite races.

## 19. References

1. [Spring Security 6.5 — Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html): `DelegatingPasswordEncoder`, `{id}`, matching, upgrades, and legacy compatibility.
2. [Spring Security 6.5 — PasswordEncoderFactories Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/factory/PasswordEncoderFactories.html): list of mappings and default encoder.
3. [Spring Security 6.5 — DelegatingPasswordEncoder Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/DelegatingPasswordEncoder.html): `setDefaultPasswordEncoderForMatches`, `upgradeEncoding`.
4. [Spring Security 6.5 — PasswordEncoder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/PasswordEncoder.html): `encode`, `matches`, `upgradeEncoding`.
5. [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): provider and UserDetailsService/PasswordEncoder.
6. [Spring Security 6.5 — DaoAuthenticationProvider Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html): `setUserDetailsPasswordService` and password upgrades.
7. [Spring Security 6.5 — UserDetailsPasswordService API](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/core/userdetails/UserDetailsPasswordService.html): encoded updatePassword.
8. [Spring Security 6.5 — BCryptPasswordEncoder](https://docs.spring.io/spring-security/site/docs/6.5.2/api/org/springframework/security/crypto/bcrypt/BCryptPasswordEncoder.html): BCrypt cost, matches, and upgradeEncoding.
9. [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): adaptive hashes, work factor, migration, and password handling.
10. [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): login throttling, generic errors, reset, and reauthentication.

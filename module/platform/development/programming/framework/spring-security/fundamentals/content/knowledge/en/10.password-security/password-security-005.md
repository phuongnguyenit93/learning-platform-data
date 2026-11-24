# DelegatingPasswordEncoder and Algorithm Prefixes in Hashed Values

## Learning Objectives

An account management system often faces two seemingly conflicting requirements: **new passwords must be stored using a currently recommended secure hashing mechanism**, while **passwords stored by earlier versions must still verify during a transition period**. Spring Security solves the algorithm-selection problem via `DelegatingPasswordEncoder` and the **`{id}encodedPassword`** format.

Instead of guessing the algorithm from hash string length, the system writes an **algorithm identifier** at the start of the stored value, such as `{bcrypt}`. When receiving a user-supplied password, `DelegatingPasswordEncoder` reads the prefix to pick the matching `PasswordEncoder`. When creating a new password, a separate setting called **`idForEncode`** selects the active encoder. That lets **reading old hashes** differ from **creating new hashes**, while both work through the same interface.

This lesson uses **Java 17, Spring Boot 3.5.0, Spring Security 6.5.x, Spring MVC/Servlet**. The main example runs with Maven using `PasswordEncoderFactories.createDelegatingPasswordEncoder()`; the advanced section demonstrates upgrading an account with a legacy hash to bcrypt upon successful login. `{noop}` examples are strictly for analyzing legacy/test data—**never for storing passwords in new systems**.

After completing this lesson, you will:

1. Distinguish **raw passwords**, **stored hashes**, **salt/work factor**, and Spring Security's **`{id}` prefix**.
2. Explain `PasswordEncoder.encode`, `matches`, `upgradeEncoding`, and the role of `DelegatingPasswordEncoder`.
3. Understand `idForEncode`, `idToPasswordEncoder`, and algorithm-selection behavior during encode/match.
4. Read a `{bcrypt}$2a$10$...` string without confusing the prefix with a salt or proof of a valid password.
5. Know why unprefixed hashes or `{unknown}` throw errors on `matches` by default, and how to handle controlled migrations.
6. Recognize common mappings `bcrypt`, `pbkdf2@SpringSecurity_v5_8`, `scrypt@SpringSecurity_v5_8`, `argon2@SpringSecurity_v5_8`, and legacy `noop`/digests.
7. Build a consistent PasswordEncoder bean with `UserDetailsService` and `DaoAuthenticationProvider` in a Spring Boot app.
8. Design tests for right/wrong passwords, prefixes, unknown ids, legacy unprefixed BCrypt, upgrade-on-login, and HTTP 200/401/403.
9. Avoid plaintext storage, double hashing, comparing two bcrypt strings directly, global `noop` fallbacks, truncated DB columns, and leaking hashes/credentials.

## 1. Why Does DelegatingPasswordEncoder Exist?

### 1.1. Not Every Account Was Created at the Same Time

Imagine an application running for many years:

- Group A was originally stored using an older format.
- Group B moved to bcrypt.
- The system wants to raise the bcrypt cost as hardware evolves.
- The application will eventually need to transition to another algorithm depending on recommendations and infrastructure.

If `PasswordEncoder` only knows one algorithm, old records fail verification whenever you swap implementations. Trying to write ad-hoc length/regex checks easily produces ambiguous fallbacks or accidentally accepts untrusted data.

**`DelegatingPasswordEncoder` is a dispatcher**—it does not replace bcrypt/Argon2/PBKDF2 math itself. It takes a map of encoders keyed by `id` and routes calls:

```text
User enters raw password
         |
         v
DelegatingPasswordEncoder.matches(raw, stored)
         |
         +--> stored starts with "{bcrypt}"?
         |          -> BCryptPasswordEncoder.matches(raw, hashBody)
         |
         +--> stored starts with "{pbkdf2@SpringSecurity_v5_8}"?
         |          -> PBKDF2 encoder per registered mapping
         |
         +--> stored starts with "{noop}"?
         |          -> Legacy no-op encoder (UNSAFE for new storage)
         |
         +--> Missing id / unmapped id?
                    -> IllegalArgumentException by default
```

When creating new hashes:

```text
rawPassword
    |
    v
DelegatingPasswordEncoder.encode(rawPassword)
    |
    v
idForEncode = "bcrypt"
    |
    v
BCryptPasswordEncoder.encode(rawPassword)
    |
    v
"{bcrypt}" + bcryptHash
    |
    v
Store full string in database
```

**Authentication must still verify the raw password**; the prefix alone does not prove a user logged in successfully. `matches` returns true/false for valid inputs, or may throw an exception if the format/id is unsupported. Never treat the prefix as a digital signature, secret, or tamper-protection check on the record.

### 1.2. PasswordEncoder vs. AuthenticationManager

| Component | Role | What It Does Not Do |
| --- | --- | --- |
| `PasswordEncoder` | Hash raw passwords, compare raw vs. stored hash, signal rehash need. | Does not know which endpoints a user may access. |
| `DelegatingPasswordEncoder` | Select a specific encoder by `{id}` and `idForEncode`. | Does not manage user stores or HTTP sessions itself. |
| `UserDetailsService` | Load `UserDetails` including username, encoded password, account status, authorities. | Does not authenticate an HTTP request itself. |
| `DaoAuthenticationProvider` | Coordinate loading the user and calling `PasswordEncoder.matches` to verify passwords. | Does not open all URLs to the user. |
| `AuthenticationManager` / `ProviderManager` | Orchestrate providers and return a verified `Authentication` or throw an exception. | Does not replace object/tenant-level authorization. |
| `SecurityFilterChain` | Enforce authentication/authorization across HTTP requests. | Does not hash passwords on behalf of the database. |
| `UserDetailsPasswordService` | Allow updating a user's encoded password in flows like post-login rehashing. | Not an API for clients to change passwords without verification. |

Key takeaway: **encode on save**, **matches on authentication**, **authorization after authentication**. Never send the hash back to the client and ask the client to submit the hash as a password; doing so turns the hash into a replayable secret (pass-the-hash by bad design).

## 2. The {id}encodedPassword Format

The format published by Spring Security:

```text
{id}encodedPassword
```

Where:

- `{` opens the id and `}` closes the id, in the default format.
- `id` is the **mapping** name inside `DelegatingPasswordEncoder`, e.g. `bcrypt`.
- `encodedPassword` is the output produced by the corresponding encoder, which may embed salt, cost, version, or internal algorithm parameters.
- The entire string is the **stored password value in the user store**, not the original password.

Illustrative bcrypt value:

```text
{bcrypt}$2a$10$dXJ3SW6G7P50lGmMkkmwe.20cQQubK3.HZWzG3YB1tlRy.fqvM/BG
|------| |--| |-| |----------------------------------------------------|
   id   ver cost        salt + hash encoded in bcrypt format
```

**Two independent metadata layers:**

1. `{bcrypt}` is the **Spring Security DelegatingPasswordEncoder** prefix indicating which encoder mapping to use.
2. `$2a$10$...` is the **internal bcrypt format**. `$2a` is the version marker, `10` is the cost/work factor, and the rest encodes the salt and password hash in bcrypt format.

Do not misread `10` as “10 rounds of SHA-256” or “a 10-character salt”; it is the bcrypt work factor. Never slice the string by fixed offsets or Base64-decode the hash manually to check it. Use the vetted library encoder.

### 2.1. Representative Prefixes

| Prefix/id | Meaning in Spring Security Mapping | Notes |
| --- | --- | --- |
| `{bcrypt}` | `BCryptPasswordEncoder` | Default used for encoding new hashes by the factory in Spring Security 6.5. |
| `{pbkdf2}` | Legacy PBKDF2 factory mapping | Specific parameters differ from newer versioned ids; never swap ids blindly. |
| `{pbkdf2@SpringSecurity_v5_8}` | PBKDF2 with 5.8-generation configuration | Version in the id prevents misreading cost/salt/hash format. |
| `{scrypt}` | Legacy scrypt mapping | Distinct from the versioned mapping. |
| `{scrypt@SpringSecurity_v5_8}` | scrypt with corresponding parameter set | May require memory/cost evaluation on real infrastructure. |
| `{argon2}` | Older Argon2 mapping | Library dependencies and costs must be checked per version. |
| `{argon2@SpringSecurity_v5_8}` | Argon2 under 5.8-generation mapping | Some Spring Security Argon2 implementations rely on Bouncy Castle. |
| `{noop}` | NoOpPasswordEncoder | Plaintext, unsafe; strictly for learning or controlled migrations. |
| `{MD5}`, `{SHA-1}`, `{sha256}` | Legacy/digest mappings | Unsuitable for storing new passwords; vulnerable to offline cracking. |

The mapping list can change across releases. **Do not assume every algorithm in this table is enabled in a custom `DelegatingPasswordEncoder` built from a Map.** They reflect the factory mappings in the Spring Security 6.5 line; if you construct `DelegatingPasswordEncoder` manually, only ids explicitly placed in the map are recognized.

### 2.2. Prefix Is Not Arbitrary User-Supplied Input

`id` is read from the **stored hash value**, not from a client-supplied “algorithm” field on login. For a given input, encoder selection must follow server configuration and controlled stored records, never browser claims.

Even if a DB record were modified during an incident, the identifier does not dynamically download classes from the Internet or execute arbitrary code; it is a lookup key in the registered encoder map. Still, a system allowing arbitrary overwrites of password hashes/prefixes has a critical vulnerability: an attacker could replace a hash with one for a password they know and log in.

### 2.3. How Many Characters Should the Password Column Hold?

Never assume hashes are always 60 characters like raw bcrypt. Adding `{bcrypt}` makes them longer, and PBKDF2/scrypt/Argon2 formats vary further by cost, salt, and configuration. An overly short password column can **truncate the prefix or hash body**, causing widespread login failures or blocking algorithm migration.

In database design, typically use a text/`VARCHAR` column wide enough for all supported encoders, plus non-truncating validation, schema migrations, and driver-level data tests. Never promise one fixed length will fit every algorithm forever.

## 3. The Three Methods of PasswordEncoder

Core contract:

```java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);
    boolean matches(CharSequence rawPassword, String encodedPassword);
    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
```

This is a **simplified form** for study, not a file to create yourself. The real class/interface is provided by `org.springframework.security.crypto.password`.

### 3.1. encode(rawPassword): Creating a Stored Value

```java
PasswordEncoder encoder =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();

String stored = encoder.encode("spring-is-fun");
```

With the 6.5.x factory, `stored` begins with `{bcrypt}`. Because bcrypt generates a random salt, **encoding the same raw password twice normally does not yield identical output strings**:

```java
String first = encoder.encode("same-password");
String second = encoder.encode("same-password");

// Do not use equals(first, second) to claim passwords match.
```

That is by design; modern password hashing algorithms use salts and costs to defeat simple hash-comparison attacks, precomputed tables, and cheap bulk guessing.

### 3.2. matches(raw, encoded): Comparing, Not Decrypting

```java
String stored = encoder.encode("spring-is-fun");

boolean correct =
    encoder.matches("spring-is-fun", stored); // true

boolean incorrect =
    encoder.matches("wrong-password", stored); // false
```

There is no “decrypt bcrypt to recover the password” operation. `matches` hashes/verifies using the stored salt and parameters. During login, the raw password comes from the user's submission and the stored password comes from the server-side `UserDetailsService`.

**Avoid:**

```java
// WRONG: each bcrypt encode call usually uses a new salt.
boolean wrong =
    encoder.encode(submitted).equals(stored);
```

This is an anti-pattern snippet; `submitted` and `stored` would need declarations if pasted into a Java file. The right call is `encoder.matches(submitted, stored)`.

### 3.3. upgradeEncoding(encoded): Should It Be Rehashed?

`PasswordEncoder.upgradeEncoding` signals whether a stored value should be re-encoded under a newer mechanism or cost. The interface default returns `false`; certain encoders, including `DelegatingPasswordEncoder`, provide custom logic.

Expected logic example with the 6.5 factory:

```java
PasswordEncoder encoder =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();

String current = encoder.encode("secret-pass");

boolean currentNeedsUpgrade =
    encoder.upgradeEncoding(current); // usually false

boolean legacyNeedsUpgrade =
    encoder.upgradeEncoding("{noop}secret-pass"); // true
```

`upgradeEncoding` **does not modify the database itself**. It only returns a boolean. To actually rehash, you need the **raw password available during a successful authentication** and a persistence hook such as `UserDetailsPasswordService`, wired to `DaoAuthenticationProvider` or a trusted service.

If a hash's bcrypt cost is lower than the current configuration, the implementation may report an upgrade is needed even when the prefix is already `{bcrypt}`. Checking the prefix alone is not enough to know a password meets current strength settings.

## 4. How Does DelegatingPasswordEncoder Select an Algorithm?

### 4.1. Two Parameters Not to Confuse

`DelegatingPasswordEncoder` distinguishes:

- **`idForEncode`:** the id used for **every new `encode` call** on that instance.
- **`idToPasswordEncoder`:** the `id → PasswordEncoder` map used to **recognize and verify stored values**.

Constructed via the basic API constructor:

```java
DelegatingPasswordEncoder encoder =
    new DelegatingPasswordEncoder(
        "bcrypt",
        Map.of(
            "bcrypt", new BCryptPasswordEncoder(12),
            "pbkdf2@SpringSecurity_v5_8",
                Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8()
        )
    );
```

This is an **intentionally customized snippet** requiring imports for `java.util.Map`, `DelegatingPasswordEncoder`, `BCryptPasswordEncoder`, and `Pbkdf2PasswordEncoder`. With this setup:

- **New** passwords are hashed with BCrypt cost 12 and prefixed with `{bcrypt}`.
- Hashes with `{pbkdf2@SpringSecurity_v5_8}` verify via the registered PBKDF2 mapping.
- Hashes carrying `{noop}` are **absent from the map**, treated as unsupported ids, and throw an exception by default.
- This configuration does not automatically convert old PBKDF2 hashes to bcrypt in the database; a separate upgrade flow is required.

**Never arbitrarily change the id of an old hash.** For instance, an old PBKDF2 hash cannot “become bcrypt” by replacing `{pbkdf2}` with `{bcrypt}`. The prefix means choosing the verifier matching the **existing hash body**.

### 4.2. The Default Factory

Spring Security provides:

```java
@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
}
```

This snippet goes inside a `@Configuration` class with imports for `@Bean` and `PasswordEncoderFactories`. The factory registers multiple legacy-compatible mappings alongside modern ids, and selects **`bcrypt` as `idForEncode`** in the Spring Security 6.5 line. Thus creating a new password for a normal user produces a value like:

```text
{bcrypt}$2a$10$...actual-bcrypt-content...
```

The `...` here is **illustrative notation**, not a valid hash to store. Each run generates a salted bcrypt string that differs. To produce a valid hash, call `encoder.encode(rawPassword)`; **never manually prepend `{bcrypt}` to a dummy string**.

### 4.3. Why Does the Factory Allow Reading Old Formats?

`DelegatingPasswordEncoder`'s purpose is easing application upgrades: legacy accounts can verify using a mapped id, after which the application rehashes them with the current algorithm.

**Being able to read a weak format does not recommend creating new hashes in that format.** `{noop}` and weak digests should only exist during a bounded migration under strict policy: limited account scope, time window, safe logging, and forced resets where necessary. Keeping legacy support indefinitely preserves attack surface.

### 4.4. Ids Are Case-Sensitive

In the default mappings, `bcrypt` differs from `BCRYPT`, and `MD5` differs from `md5` if defined distinctly in the map. Preserve the exact registered id. Never bulk-lowercase stored records without checking mappings; changing case can turn a valid id into an unknown id.

## 5. Scenario Table: encode, match, and Errors

Using `PasswordEncoderFactories.createDelegatingPasswordEncoder()` in Spring Security 6.5:

| Stored Value | Raw Password Input | Expected Behavior | Reason |
| --- | --- | --- | --- |
| Real hash produced by `encoder.encode("secret")` | `secret` | `true` | `{bcrypt}` routes to bcrypt using the salt/cost in the hash body. |
| Same hash | `wrong` | `false` | Valid algorithm, but password does not match. |
| `{noop}legacy-demo` | `legacy-demo` | `true` per legacy mapping | Illustrates reading legacy plaintext only; **do not store like this in new systems**. |
| `{noop}legacy-demo` | `wrong` | `false` | Legacy NoOp compares raw values directly. |
| `{not-registered}whatever` | `whatever` | Throws `IllegalArgumentException` by default | Unmapped id. |
| `$2a$10$...` without `{bcrypt}` | `secret` | Throws `IllegalArgumentException` by default | Cannot parse a Spring Security id. |
| `{bcrypt}not-a-real-bcrypt-hash` | `secret` | Fails verification (typically false; may log format warning) | Prefix is present, but hash body is invalid. |
| `{pbkdf2@SpringSecurity_v5_8}...` with valid hash | Right raw password | Result from PBKDF2 mapping if present | Requires valid hash body format and matching configuration. |

Rows containing `...` are **structural examples**, not literal strings to paste into tests or databases. The `{noop}` rows intentionally depict unprotected legacy data, because you cannot learn safe migration if you mistakenly think a prefix turns plaintext into a hash.

### 5.1. Distinguishing Wrong Passwords from Wrong Formats

- **Wrong password**, valid hash body and mapped id: `matches` returns `false`.
- **Missing id** or **unmapped id**: `DelegatingPasswordEncoder` throws `IllegalArgumentException` by default; this typically indicates a data migration or configuration bug.
- **Corrupted/incompatible hash body:** individual encoders react differently (false, warning, or exception); do not assume a single error behavior across all algorithms.

During HTTP login, a format exception might surface as HTTP 500 or be wrapped depending on your security flow—**do not assume every hash error becomes 401**. Fix it by analyzing data formats and mappings in a safe environment; never switch the default matcher to `noop` just to “make login work.”

### 5.2. An Unknown Id Is Not an Invitation to Try Every Encoder

A dangerous design is “if `{id}` is unknown, try plaintext, bcrypt, MD5, and SHA-1 until one matches.” That makes authentication rules ambiguous, may accept unexpectedly weak formats, and makes migrations impossible to audit.

**Safe principle:** stored hashes must have a **declared format**, a finite set of allowed algorithms, and explicit verification configuration. If you must temporarily support unprefixed legacy values, do so only after **confirming** their exact format, scoping it tightly, and scheduling fallback removal.

## 6. Small Java Example: Observing Prefix and matches Directly

This is a standalone Java class with `main`, requiring the **Spring Security crypto dependency** from the Maven project in section 10.

### 6.1. PasswordFormatDemo.java

```java
package com.example.delegatingpassword;

import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

public class PasswordFormatDemo {

    public static void main(String[] args) {
        PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();

        String raw = "sample-pass";
        String stored = encoder.encode(raw);

        System.out.println(stored.startsWith("{bcrypt}"));
        System.out.println(encoder.matches(raw, stored));
        System.out.println(encoder.matches("wrong-pass", stored));
        System.out.println(encoder.matches(
            "legacy-pass", "{noop}legacy-pass"
        ));
        System.out.println(encoder.upgradeEncoding(
            "{noop}legacy-pass"
        ));
    }
}
```

With the default Spring Security 6.5 factory, this is expected to print **exactly these lines**:

```text
true
true
false
true
true
```

It does not print `stored` because the bcrypt hash has a random salt; asserting against a fixed hash string would make the demo non-deterministic. This example involves no Spring Boot startup; it uses only the crypto API.

### 6.2. Why Does {noop} Match?

By default `DelegatingPasswordEncoder` also knows `noop` from the factory mappings. When it sees `{noop}legacy-pass`, it passes the body `legacy-pass` to `NoOpPasswordEncoder` for direct comparison. **That demonstrates legacy compatibility, not password protection.**

For new registrations, always call `encoder.encode(raw)` to produce a strong hash; never store `{noop}...`. If a DB contains `{noop}`, schedule a migration or forced reset promptly.

## 7. Missing Prefix: Handling Each Case Properly

A very common situation when upgrading an older app:

```text
$2a$10$XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

This is only notation depicting a raw bcrypt body, not a guaranteed valid hash. `BCryptPasswordEncoder` can directly read a **valid raw bcrypt body**, whereas `DelegatingPasswordEncoder` needs an **id**. If the DB stores bcrypt **without `{bcrypt}`**, the default delegator finds no mapping and throws.

### 7.1. Preferred Approach: Prepend Prefix to Verified Bcrypt Values

Once you have confirmed a set of records are valid raw bcrypt hashes—and backed up/audited them—you can migrate:

```text
BEFORE
$2a$10$...bcrypt-body...

AFTER
{bcrypt}$2a$10$...bcrypt-body...
```

Adding the prefix only supplies **algorithm metadata**; the bcrypt body itself is unchanged, so `matches(raw, "{bcrypt}" + oldHash)` performs the exact same verification check as before.

**You must be sure of the format before bulk updates.** Never blindly prepend `{bcrypt}` to every value missing `{id}`; some rows might be legacy SHA-256 hashes, plaintext, or corrupted data. Use guarded migration scripts, sample validation, transactions/backups, and a rollback plan. Never expose raw hashes in reports or issue trackers.

### 7.2. When Values Carry {noop}

You cannot “turn” plaintext into bcrypt by editing `{noop}` to `{bcrypt}`. The body is still plaintext and will not verify as bcrypt. You must **rehash the original password in an authorized context**, or require a password reset.

A common upgrade path is letting legacy accounts log in **once via legacy verification**, then using the raw password from that login to create a new hash and update the store. Section 11 illustrates this with `DaoAuthenticationProvider` + `UserDetailsPasswordService`.

**Do not read plaintext passwords out of the database for bulk conversion** unless handling known legacy records under strict security controls; existing plaintext is a defect to remediate urgently, not a feature to rely on.

### 7.3. setDefaultPasswordEncoderForMatches: A Risky Migration Tool

`DelegatingPasswordEncoder` has the method:

```java
delegating.setDefaultPasswordEncoderForMatches(fallback);
```

It is invoked only when `id` has no mapping, including null/missing prefixes. **The fallback receives the full stored password string passed to `matches`, including `{id}` if present**; Spring Security does not strip the id when calling the fallback.

This is an API snippet where `delegating` is a `DelegatingPasswordEncoder` and `fallback` is a `PasswordEncoder` you designed. Never write:

```java
// DO NOT USE:
delegating.setDefaultPasswordEncoderForMatches(
    NoOpPasswordEncoder.getInstance()
);
```

An unrestricted NoOp fallback causes hashes with missing or unknown ids to be compared as plaintext. That creates a weak verification path, masks bad data, and makes migration impossible to control.

If you are forced to support unprefixed raw bcrypt briefly, the fallback should **only accept valid raw bcrypt syntax**, reject everything else, be monitored, and be removed once migration finishes. Most systems are safer and easier to audit when performing a **data migration to add prefixes** rather than keeping a long-lived runtime fallback.

## 8. Custom Mapping: Changing the Write Algorithm Without Breaking Old Data

You can construct `DelegatingPasswordEncoder` manually to write new hashes with algorithm X while still reading algorithm Y:

```java
import java.util.Map;

import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.DelegatingPasswordEncoder;
import org.springframework.security.crypto.password.Pbkdf2PasswordEncoder;

DelegatingPasswordEncoder encoder =
    new DelegatingPasswordEncoder(
        "bcrypt",
        Map.of(
            "bcrypt", new BCryptPasswordEncoder(12),
            "pbkdf2@SpringSecurity_v5_8",
                Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8()
        )
    );
```

This is a **snippet inside a Java class/method**, not a standalone Java file. It omits the rest of the factory mappings. New passwords are encoded with bcrypt cost 12; 5.8 PBKDF2 hashes verify under the matching key. Hashes carrying `{pbkdf2}` (without the version suffix) will **not be mapped automatically** here. To accept them, add the matching entry after verifying the data format.

### 8.1. Why Are Versioned Ids Useful?

Algorithms like PBKDF2, scrypt, and Argon2 carry parameters: iteration count, salt length, memory cost, parallelism, or combinations thereof. Reusing a single generic name like `pbkdf2` across eras risks misinterpreting old hashes under new parameters. Spring Security introduces ids like `@SpringSecurity_v5_8` to distinguish configurations.

**Never add or strip a version suffix** without checking the encoder implementation. A hash computed under different parameters may fail verification even though both share the name PBKDF2.

### 8.2. Bcrypt Cost and Strength Upgrades

If you configure `new BCryptPasswordEncoder(12)`, new hashes carry cost 12. When a user has a stored bcrypt cost 10 hash, the encoder's `upgradeEncoding` can report that it should be rehashed at the current strength; `matches` itself can still verify the cost 10 hash accurately.

Never raise cost arbitrarily high without benchmarking CPU, latency, and login load; password hashing must deter brute force, yet also consumes server resources under attack. You still need rate limiting, credential-stuffing controls, and performance observability.

### 8.3. Changing Algorithms Is Not Changing Prefixes

Changing `idForEncode` only affects **hashes produced by future `encode` calls**. Existing hashes keep their old ids and must remain mapped for `matches`. To rehash existing users, you normally need the raw password at a valid login or a reset flow. There is no mathematical operation to “translate” a bcrypt hash directly into an Argon2 hash without the raw password.

## 9. A Complete Spring Boot Project for Practice

The lab exposes three simple endpoints:

| HTTP endpoint | Policy | Result |
| --- | --- | --- |
| `GET /public/ping` | `permitAll()` | Anonymous callers receive 200. |
| `GET /api/me` | `authenticated()` | Requires HTTP Basic login; valid users receive their username. |
| `GET /admin/ping` | `hasRole("ADMIN")` | Only admin accounts can access. |
| Other requests | `denyAll()` | Denied by default. |

Two demo accounts are created with **encoded** passwords:

- `learner` / `learner-pass` → `ROLE_USER`.
- `admin` / `admin-pass` → `ROLE_USER`, `ROLE_ADMIN`.

The project exposes no browser endpoint for user creation or password reset. Migration/password-upgrade exercises use isolated unit tests rather than opening a legacy `{noop}` login door on the HTTP app. Passwords in source are strictly for **localhost/testing**, never real environments.

### 9.1. Project Structure

```text
delegating-password-lab/
├── pom.xml
└── src/
    ├── main/java/com/example/delegatingpassword/
    │   ├── DelegatingPasswordApplication.java
    │   ├── SecurityConfig.java
    │   ├── IdentityController.java
    │   └── PasswordFormatDemo.java
    └── test/java/com/example/delegatingpassword/
        ├── DelegatingPasswordEncoderTest.java
        ├── PasswordUpgradeTest.java
        └── PasswordHttpTest.java
```

### 9.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>delegating-password-lab</artifactId>
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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugins>
    </build>
</project>
```

The Spring Boot parent/BOM manages compatible dependency versions for Spring Security and JUnit. `3.5.0` is chosen as an API example; real projects must upgrade to an actively supported patched release. Do not add Spring WebFlux to this Servlet lab; WebFlux uses a different security configuration model.

### 9.3. DelegatingPasswordApplication.java

```java
package com.example.delegatingpassword;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DelegatingPasswordApplication {
    public static void main(String[] args) {
        SpringApplication.run(DelegatingPasswordApplication.class, args);
    }
}
```

The main class sits in the root package so component scan discovers `SecurityConfig` and `IdentityController`. `PasswordFormatDemo` is a separate entry point for observing the encoder, not part of web request handling.

### 9.4. SecurityConfig.java

```java
package com.example.delegatingpassword;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("learner")
                .password(encoder.encode("learner-pass"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .requestMatchers("/api/me").authenticated()
                .requestMatchers("/admin/ping").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .build();
    }
}
```

**Reading the configuration by responsibility:**

1. `passwordEncoder()` exposes a `PasswordEncoder` bean capable of encoding new passwords with bcrypt and matching by prefix.
2. `users(...)` calls `encoder.encode(...)` **before storing** users; thus `UserDetails#getPassword()` holds a `{bcrypt}`-prefixed hash.
3. `InMemoryUserDetailsManager` is a learning user store. On app restart, fresh hashes with fresh salts are generated, while the demo raw passwords remain the same.
4. `DaoAuthenticationProvider`, auto-configured by Spring Security/Boot in this flow, uses this `UserDetailsService` bean and `PasswordEncoder` bean to verify Basic credentials. There is no need to call `encoder.matches(...)` inside a controller.
5. `SessionCreationPolicy.STATELESS` keeps this per-request Basic example independent of login sessions; it does not make Basic safe over plain HTTP.
6. `httpBasic(...)` enables the authentication filter; form login is disabled so 401 responses are easy to observe. Default CSRF is left intact; all endpoints are read-only GETs, so no CSRF token is needed in these tests.
7. `anyRequest().denyAll()` guards undeclared routes. `hasRole("ADMIN")` checks the `ROLE_ADMIN` authority via the default role prefix.

**Do not think `createDelegatingPasswordEncoder` invents passwords:** raw demo strings remain in Java source, making this unsuitable for production. In real apps, passwords come from secure registration/password-change flows, stored hashed in a DB, never hardcoded.

### 9.5. IdentityController.java

```java
package com.example.delegatingpassword;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @GetMapping("/admin/ping")
    public String adminPing() {
        return "admin-only";
    }
}
```

The controller returns only the authenticated username, **never returning password hashes, credentials, or the full `Authentication` object**. Login and hash verification occur earlier in the security filters and providers.

### 9.6. Running and Testing HTTP

In the `delegating-password-lab` directory:

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

Open a new terminal:

```bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/me
curl -i -u learner:learner-pass http://localhost:8080/api/me
curl -i -u learner:wrong-pass http://localhost:8080/api/me
curl -i -u learner:learner-pass http://localhost:8080/admin/ping
curl -i -u admin:admin-pass http://localhost:8080/admin/ping
```

In PowerShell, use `curl.exe` when `curl` is aliased to `Invoke-WebRequest`.

Expected results:

| Request | HTTP status | Body on Success |
| --- | --- | --- |
| `GET /public/ping` anonymous | **200** | `pong` |
| `GET /api/me` anonymous | **401** | No identity disclosed |
| `GET /api/me` learner right password | **200** | JSON with `username=learner` |
| `GET /api/me` learner wrong password | **401** | No verified Authentication |
| `GET /admin/ping` learner | **403** | Missing ROLE_ADMIN |
| `GET /admin/ping` admin | **200** | `admin-only` |

This is **expected behavior** for you to verify, not logs from a server already run on your machine. HTTP Basic sends Base64-encoded username/password without **encrypting the transport**; use plain HTTP only locally in this lesson, and require HTTPS/TLS for real credentials.

## 10. JUnit Tests for Prefixes, Matching, and Unknown Ids

Create `src/test/java/com/example/delegatingpassword/DelegatingPasswordEncoderTest.java`. These tests need no Spring Boot application context; they use only the crypto API and JUnit.

```java
package com.example.delegatingpassword;

import org.junit.jupiter.api.Test;

import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class DelegatingPasswordEncoderTest {

    private final PasswordEncoder encoder =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();

    @Test
    void newPasswordIsStoredWithBcryptId() {
        String stored = encoder.encode("new-pass");

        assertThat(stored).startsWith("{bcrypt}");
        assertThat(stored).contains("$2");
        assertThat(encoder.matches("new-pass", stored)).isTrue();
    }

    @Test
    void correctRawMatchesButIncorrectRawDoesNot() {
        String stored = encoder.encode("correct-pass");

        assertThat(encoder.matches(
            "correct-pass", stored
        )).isTrue();
        assertThat(encoder.matches(
            "incorrect-pass", stored
        )).isFalse();
    }

    @Test
    void twoBcryptEncodesOfSamePasswordCanDiffer() {
        String first = encoder.encode("same-pass");
        String second = encoder.encode("same-pass");

        assertThat(first).isNotEqualTo(second);
        assertThat(encoder.matches(
            "same-pass", first
        )).isTrue();
        assertThat(encoder.matches(
            "same-pass", second
        )).isTrue();
    }

    @Test
    void legacyNoopCanBeVerifiedButNeedsUpgrade() {
        // Illustrates reading legacy plaintext only; DO NOT store like this.
        String oldStored = "{noop}legacy-pass";

        assertThat(encoder.matches(
            "legacy-pass", oldStored
        )).isTrue();
        assertThat(encoder.matches(
            "wrong-pass", oldStored
        )).isFalse();
        assertThat(encoder.upgradeEncoding(oldStored)).isTrue();
    }

    @Test
    void currentBcryptNormallyDoesNotNeedUpgrade() {
        String stored = encoder.encode("already-current");

        assertThat(encoder.upgradeEncoding(stored)).isFalse();
    }

    @Test
    void unknownIdIsRejectedByDefault() {
        assertThatThrownBy(() -> encoder.matches(
            "any-pass", "{not-registered}anything"
        )).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void missingIdIsRejectedByDefault() {
        String rawBcrypt =
            new BCryptPasswordEncoder().encode("legacy-pass");

        assertThatThrownBy(() -> encoder.matches(
            "legacy-pass", rawBcrypt
        )).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void knownRawBcryptCanBeMatchedAfterPrefixMigration() {
        String rawBcrypt =
            new BCryptPasswordEncoder().encode("legacy-pass");

        String prefixed = "{bcrypt}" + rawBcrypt;

        assertThat(encoder.matches(
            "legacy-pass", prefixed
        )).isTrue();
        assertThat(encoder.matches(
            "wrong-pass", prefixed
        )).isFalse();
    }

    @Test
    void wrongAlgorithmIdCannotTurnPlaintextIntoBcrypt() {
        assertThat(encoder.matches(
            "plaintext",
            "{bcrypt}plaintext"
        )).isFalse();
    }

    @Test
    void rawPasswordIsNotTheValueStoredInUserDetails() {
        String stored = encoder.encode("learner-pass");

        assertThat(stored).isNotEqualTo("learner-pass");
        assertThat(stored).startsWith("{bcrypt}");
        assertThat(encoder.matches(
            "learner-pass", stored
        )).isTrue();
    }
}
```

**10 test cases** demonstrating:

- New encodes use `{bcrypt}`.
- `matches` compares raw vs. hash, never two `encode` outputs.
- Bcrypt uses salts so outputs normally differ.
- Legacy `{noop}` is recognized by the factory yet marked for upgrade.
- Unknown/missing ids throw `IllegalArgumentException` by default.
- Unprefixed raw bcrypt matches once `{bcrypt}` is properly prepended.
- Changing the prefix to bcrypt when the body is plaintext **does not validate the password**.

The test checking two distinct bcrypt hashes relies on random salting; the theoretical collision probability is non-zero, yet with a proper CSPRNG and independent calls, collisions are extraordinarily unlikely. In strict production tests, prefer asserting `matches` over relying strictly on string inequality.

## 11. Migration-on-Login with UserDetailsPasswordService

In Spring Security username/password authentication, upgrading old passwords upon a valid login combines:

1. `DaoAuthenticationProvider` checks the raw password against the stored hash using `PasswordEncoder.matches`.
2. If the password is valid and `PasswordEncoder.upgradeEncoding(storedHash)` requests an upgrade, the provider computes a new hash with `encode(rawPassword)`.
3. A configured `UserDetailsPasswordService` persists the new encoded hash for the user.
4. Subsequent logins use the current hash without special-case controller code.

**Crucial requirement:** `UserDetailsPasswordService` must be wired into the provider; merely declaring a `DelegatingPasswordEncoder` does not auto-migrate the database. `InMemoryUserDetailsManager` supports the password-update API, though it only keeps data in RAM; the test uses an isolated instance.

### 11.1. PasswordUpgradeTest.java

```java
package com.example.delegatingpassword;

import org.junit.jupiter.api.Test;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class PasswordUpgradeTest {

    private final PasswordEncoder encoder =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();

    private InMemoryUserDetailsManager legacyUsers() {
        return new InMemoryUserDetailsManager(
            User.withUsername("legacy")
                .password("{noop}legacy-pass")
                .roles("USER")
                .build()
        );
    }

    private AuthenticationManager managerWithPasswordUpgrade(
            InMemoryUserDetailsManager users) {

        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);

        // Grant the provider permission to update the hash after successful authentication.
        provider.setUserDetailsPasswordService(users);

        return new ProviderManager(provider);
    }

    @Test
    void successfulLegacyLoginRehashesPasswordToBcrypt() {
        InMemoryUserDetailsManager users = legacyUsers();
        AuthenticationManager manager =
            managerWithPasswordUpgrade(users);

        String before =
            users.loadUserByUsername("legacy").getPassword();

        assertThat(before).isEqualTo("{noop}legacy-pass");

        Authentication result = manager.authenticate(
            UsernamePasswordAuthenticationToken.unauthenticated(
                "legacy", "legacy-pass"
            )
        );

        assertThat(result.isAuthenticated()).isTrue();
        assertThat(result.getName()).isEqualTo("legacy");

        String after =
            users.loadUserByUsername("legacy").getPassword();

        assertThat(after).startsWith("{bcrypt}");
        assertThat(after).isNotEqualTo(before);
        assertThat(encoder.matches(
            "legacy-pass", after
        )).isTrue();
        assertThat(encoder.upgradeEncoding(after)).isFalse();
    }

    @Test
    void wrongLegacyPasswordDoesNotTriggerUpgrade() {
        InMemoryUserDetailsManager users = legacyUsers();
        AuthenticationManager manager =
            managerWithPasswordUpgrade(users);

        assertThatThrownBy(() -> manager.authenticate(
            UsernamePasswordAuthenticationToken.unauthenticated(
                "legacy", "wrong-pass"
            )
        )).isInstanceOf(BadCredentialsException.class);

        assertThat(users.loadUserByUsername(
            "legacy"
        ).getPassword()).isEqualTo("{noop}legacy-pass");
    }

    @Test
    void rehashedPasswordStillAuthenticatesOnNextLogin() {
        InMemoryUserDetailsManager users = legacyUsers();
        AuthenticationManager manager =
            managerWithPasswordUpgrade(users);

        manager.authenticate(
            UsernamePasswordAuthenticationToken.unauthenticated(
                "legacy", "legacy-pass"
            )
        );

        Authentication again = manager.authenticate(
            UsernamePasswordAuthenticationToken.unauthenticated(
                "legacy", "legacy-pass"
            )
        );

        assertThat(again.isAuthenticated()).isTrue();
        assertThat(users.loadUserByUsername(
            "legacy"
        ).getPassword()).startsWith("{bcrypt}");
    }

    @Test
    void encoderOnlyDoesNotRewriteUserStore() {
        InMemoryUserDetailsManager users = legacyUsers();

        assertThat(encoder.matches(
            "legacy-pass",
            users.loadUserByUsername("legacy").getPassword()
        )).isTrue();

        assertThat(encoder.upgradeEncoding(
            users.loadUserByUsername("legacy").getPassword()
        )).isTrue();

        // Calling matches/upgradeEncoding alone does not write to the store.
        assertThat(users.loadUserByUsername(
            "legacy"
        ).getPassword()).isEqualTo("{noop}legacy-pass");
    }
}
```

**4 test cases** dedicated to migration:

- Successful legacy login → provider uses `PasswordEncoder` + `UserDetailsPasswordService` to update the hash.
- Wrong password → no upgrade or write occurs.
- After rehashing, the next login succeeds.
- Calling `matches`/`upgradeEncoding` alone does not alter the user store.

**Warning:** `{noop}` data in tests only simulates a transition phase. Never bring plaintext accounts into production apps. With large numbers of old records, consider forced password resets, time-limiting legacy verification, strengthening login defenses, and monitoring the percentage of un-upgraded accounts.

### 11.2. Why Is the Raw Password Needed for Migration?

Password hashes are one-way functions designed to resist recovery of the raw input. You **cannot** produce a bcrypt hash of the original password merely by “switching algorithms” on an MD5/legacy hash while preserving the `matches(raw, newHash)` contract—unless you obtain the raw password during a valid login or a reset flow.

The on-login flow is convenient because the user just submitted the raw password; after verifying it, the provider hashes it immediately in a trusted path. The raw password never needs to be persisted to a DB, queue, or log. For accounts that no longer log in, plan a reset/expiry policy rather than keeping weak hashes indefinitely.

### 11.3. Why Must the User Store Support updatePassword?

`UserDetailsService` is read-only for account lookup. A provider cannot update the database without a write API. `UserDetailsPasswordService.updatePassword(UserDetails, String newPassword)` provides the hook for rehashing, which managers like `InMemoryUserDetailsManager` or custom implementations can support.

A custom repository system can implement `UserDetailsPasswordService` with proper transactions, optimistic locking, and auditing. Across multiple nodes, account for cache invalidation and concurrent password updates. If a password was reset while an older login was in flight, a late rehash must **never overwrite the newer password**; use conditional compare-and-set updates on the hash/version or a consistent concurrency policy.

## 12. MockMvc: Ensuring PasswordEncoder Runs in Real Login

Unit-testing `encoder.matches` directly does not prove your web configuration actually uses the right encoder and user store. Add `src/test/java/com/example/delegatingpassword/PasswordHttpTest.java`:

```java
package com.example.delegatingpassword;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PasswordHttpTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void privateEndpointChallengesAnonymous() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void encodedPasswordWorksWithHttpBasicLogin() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("learner", "learner-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username")
                .value("learner"));
    }

    @Test
    void badPasswordIsRejectedEvenForExistingUser()
            throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("learner", "wrong-pass")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void learnerCannotAccessAdminEndpoint() throws Exception {
        mvc.perform(get("/admin/ping")
                .with(httpBasic("learner", "learner-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanAccessAdminEndpoint() throws Exception {
        mvc.perform(get("/admin/ping")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-only"));
    }
}
```

There are **6 HTTP tests**, making **20 tests** across all classes: 10 PasswordEncoder tests, 4 password migration tests, and 6 HTTP tests.

The value of the HTTP tests is confirming **hashed passwords and prefixes actually work in the real authentication flow**. `@WithMockUser` is helpful when testing authorization alone, but it skips raw-vs-hash checks; hence this lesson uses HTTP Basic with demo credentials to exercise the real encoder.

### 12.1. Running the Tests

```bash
mvn test
```

Tests are expected to pass when dependencies, code, and environment are properly set up. This is the **designed expectation**, not a claim that Maven was executed on the learner's machine. Random bcrypt salts will not break the tests because assertions use `startsWith("{bcrypt}")` and `matches` rather than comparing against fixed hashes.

## 13. Upgrading Password Hashes in Production: Recommended Process

Applying this to a real database requires more than configuring a factory. A well-managed migration typically proceeds in phases.

### Phase A — Inventory Accurately Without Leaking Secrets

1. Identify all existing password formats: unprefixed raw bcrypt, prefixed hashes, legacy plaintext, PBKDF2/SCrypt/Argon2, and corrupted records.
2. Count **records per format type** without putting raw hashes or passwords into dashboards or logs.
3. Audit schema column lengths, collations, trimming, character encodings, and import/export pipelines.
4. Assess risks of weak hashes or plaintext. For legacy plaintext, prioritize forced resets and shorten support windows.
5. Confirm all application nodes share the **same mappings** before writing any new hash values.

### Phase B — Establish the Current Target Format

1. Pick an encoder suited to password policy and server load; benchmark cost.
2. Configure `PasswordEncoder` consistently across authentication, registration, and password-change services.
3. Write `encoder.encode(rawPassword)` exclusively for new accounts/changes.
4. If the app previously stored unprefixed raw bcrypt, consider a guarded, backed-up migration prepending `{bcrypt}`.
5. Never build ambiguous “try every algorithm” mappings or use `noop` as a fallback for unrecognized values.

### Phase C — Controlled Upgrade on Login

1. When credentials are submitted, `DaoAuthenticationProvider` verifies via the encoder for the old id.
2. `upgradeEncoding(storedHash)` checks whether rehashing is needed.
3. `UserDetailsPasswordService.updatePassword(...)` persists the current hash inside a transaction/conditional update.
4. If caching `UserDetails`, refresh or invalidate per policy so stale hashes are not kept.
5. Never send raw passwords to event buses, analytics, message queues, or logs.
6. Handle retries and concurrency: a password reset can race with a legacy login.

### Phase D — Retire Legacy Support

1. Track remaining accounts on weak formats without logging password details.
2. At the policy deadline, require un-upgraded accounts to complete a password reset.
3. Remove unneeded legacy mappings or lock down legacy verification paths.
4. Test rolling deployments, backups/restores, active sessions, and any other consumers sharing the user table.
5. Ensure no forgotten job, script, or admin UI still writes passwords in the old format.

**`DelegatingPasswordEncoder` itself writes no migration reports.** Inventory tracking and observability are system/operational responsibilities. Keep hash-type metrics strictly separate from logs containing secrets.

## 14. Security and Operations: What Prefixes Do Not Solve

### 14.1. Prefixes Do Not Prevent Database Leaks

If the DB leaks, attackers can read `{bcrypt}...` and try passwords offline; strong bcrypt salts/work factors raise attack cost without guaranteeing absolute invulnerability. Securing databases, backups, privileges, audits, and breached-password lists remains critical. Enforce policies against weak passwords and use MFA where appropriate.

### 14.2. Hashing Does Not Replace TLS

When a user logs in, the **raw password** travels to the server over HTTPS/TLS. Having password hashes in the database does not make HTTP Basic over plain HTTP safe. Basic Base64 is not encryption. Never put raw passwords or encoded hashes in URL queries, logs, exceptions, or responses.

### 14.3. Prefixes Are Not Tamper-Proof Signatures

If an attacker gains UPDATE access to the password column, they can overwrite it with a hash of a password they know under a valid id unless other defenses prevent it. Enforce least privilege, auditing, and admin operation controls. Prefixes only provide **algorithm routing**, not record integrity verification.

### 14.4. Password Hashes Are Not Encryption

Encryption uses a key and allows decryption by anyone holding that key; password hashing is designed to be one-way with salts and cost. Never ask to “decrypt the password to email a reminder”; the proper flow is password reset, not recovering old passwords.

### 14.5. BCrypt Is Not the Only Password Hashing Algorithm

Argon2, scrypt, and PBKDF2 have different characteristics and cost profiles. Spring Security supports them in its crypto module; some need extra dependencies or proper hardware/benchmarking. Algorithm choice for new systems should follow current cryptographic guidance, organizational policy, FIPS rules if applicable, and real benchmarks. **Never switch prefixes just because “argon2 sounds newer.”**

### 14.6. Peppers, Secret Rotation, and Key Management

Some systems add a pepper (a server-side secret) alongside password hashing. That is a distinct architecture requiring a secret manager, rotation plan, multi-version pepper handling, and safeguards against locking out logins. Default `DelegatingPasswordEncoder` neither adds a pepper nor handles rotation. Never hardcode a pepper in source or bundle it with database dumps.

### 14.7. Repeated Failed Logins and Denial of Service

Adaptive hashing consumes CPU/memory. Attackers can flood login endpoints with wrong passwords to exhaust server resources. Apply rate limits, retry budgets, monitoring, credential-stuffing defenses, and proper capacity allocation. Never pick a weak cost just to speed up local tests and accidentally ship it to production.

## 15. Common Mistakes

### Mistake 1 — “Having {bcrypt} means the hash is definitely valid”

The prefix only selects the mapping; the body must be validly formatted, and the raw password must match. Never treat `startsWith("{bcrypt}")` as authentication success.

### Mistake 2 — “Just change {noop} to {bcrypt}”

If the body is plaintext, changing the prefix does not turn it into bcrypt. You need a fresh hash generated from a valid raw password or a reset flow.

### Mistake 3 — “DelegatingPasswordEncoder will auto-guess unprefixed hashes”

Missing ids throw `IllegalArgumentException` by default. Legacy unprefixed raw bcrypt needs proper prefix migration or a **very tightly scoped** temporary fallback scheduled for removal.

### Mistake 4 — “An unknown id always behaves like a wrong password”

False: `DelegatingPasswordEncoder.matches` throws an exception by default on unmapped ids, unlike returning `false` for a wrong password. Fix the mapping or data rather than relaxing authentication rules.

### Mistake 5 — “Use NoOpPasswordEncoder as default matches for all ids”

That creates a weak plaintext comparison path for missing/unknown ids. Never configure such a global fallback.

### Mistake 6 — “Two encode calls on the same raw password must produce identical strings”

Bcrypt uses a random salt. Call `encoder.matches(raw, stored)`, never `encode(raw).equals(stored)`.

### Mistake 7 — “Double-hashing passwords during import is harmless”

If a script calls `encoder.encode(storedHash)` instead of encoding the raw password, the system stores a hash of **the hash string**, making the original raw password fail to match forever. Verify whether input data is raw or already encoded.

### Mistake 8 — “PasswordEncoder upgrades every record automatically”

`upgradeEncoding` only returns a boolean; you need a flow like `DaoAuthenticationProvider` + `UserDetailsPasswordService` or an authorized migration script. It never alters the DB by itself.

### Mistake 9 — “Raising cost only requires changing the id”

Bcrypt cost lives inside the hash body and the BCrypt encoder configuration; the `bcrypt` id does not encode the work factor directly. Rehash with the new encoder/cost when a valid raw password is available.

### Mistake 10 — “Dropping @SpringSecurity_v5_8 makes no difference”

Versioned ids identify the exact parameter configuration for PBKDF2/scrypt/Argon2. Never alter suffixes on stored records unless you have proven the hash bodies are compatible.

### Mistake 11 — “Create a new PasswordEncoder bean while UserDetailsService keeps writing old-style hashes”

Keep write and read formats aligned across modules, nodes, scripts, and identity providers. Ensure new accounts always get the current format.

### Mistake 12 — “Use a plain BCryptPasswordEncoder bean when the database holds {bcrypt}...”

A direct `BCryptPasswordEncoder` expects a raw bcrypt body, not the delegating `{bcrypt}` prefix. Use `DelegatingPasswordEncoder` or verified mapping handling rather than ad-hoc string slicing.

### Mistake 13 — “The password column only needs 60 characters”

Bcrypt bodies have a fixed length, yet prefixes and many other algorithms require more space. Provision a sufficiently wide schema column and prevent silent truncation.

### Mistake 14 — “Return the password hash in /api/me for debugging”

Hashes are sensitive data even though they are not raw passwords. Never let clients, downloads, logs, or analytics collect password hashes.

### Mistake 15 — “Hardcode hashes in source to avoid needing a DB”

Hardcoded hashes for real accounts still fail to solve lifecycle, secret rotation, lockout, or revocation, and turn source history into sensitive credential material. Only local demos should use in-memory users.

### Mistake 16 — “Password hashing replaces authorization”

A successful login only proves identity per the mechanism; endpoint and per-object access still require `hasRole`/`hasAuthority`, ownership/tenant rules, and appropriate deny-by-default policies.

### Mistake 17 — “{id} is the algorithm chosen by the frontend”

Never trust a client to choose mappings on login; the server picks the encoder from stored records and policy. Never let clients write hashes or prefixes directly into `UserDetails`.

### Mistake 18 — “Homegrown salt/algorithm combinations beat libraries”

Rolling single-pass SHA-256, fixed salts, or Base64 passwords is no substitute for proper password hashing. Use vetted implementations and benchmarked work factors.

### Mistake 19 — “Upgrade-on-login is always safe against concurrent changes”

If a password reset and a rehash race, one can overwrite the newer value; use conditional updates, versioning, transactions, and concurrency tests.

### Mistake 20 — “Keep legacy mappings forever for convenience”

The goal of mappings is controlled migration, not prolonging weak-algorithm support indefinitely. Set a retirement deadline or force resets.

## 16. Knowledge Self-Check

**1. What is the standard format of DelegatingPasswordEncoder?**  
`{id}encodedPassword`. The prefix identifies the encoder mapping for the hash body and contains no raw password.

**2. What is idForEncode used for?**  
Selecting the encoder used **when generating new hashes** via `encode`.

**3. What is idToPasswordEncoder used for?**  
Looking up the `id` in stored hashes and selecting the matching encoder during `matches` and upgrade checks.

**4. Which algorithm does Spring Security 6.5's default factory use to encode new passwords?**  
Bcrypt, with the `{bcrypt}` prefix.

**5. Why can two calls to encoder.encode("same") produce different strings?**  
Bcrypt uses a random salt, so hash strings vary even for identical raw passwords.

**6. How should raw passwords be verified?**  
Use `encoder.matches(rawPassword, encodedPassword)`, never `encode(raw).equals(hash)`.

**7. When encountering an unprefixed hash, what does DelegatingPasswordEncoder do by default?**  
It typically throws `IllegalArgumentException` due to a null/unmapped id.

**8. When encountering {not-registered}, what does it do by default?**  
Throws an exception because the id is not registered in the map.

**9. Can you prepend {bcrypt} to every value missing an id?**  
No. You may only do so once you have verified the value is genuinely a valid raw bcrypt hash.

**10. Can you change {noop} to {bcrypt} while keeping the body?**  
No. You must generate a new bcrypt hash from a valid raw password or perform a reset.

**11. Does upgradeEncoding save the new hash automatically?**  
No, it only returns a boolean; a mechanism must write to the user store.

**12. Can DaoAuthenticationProvider rehash automatically on login?**  
Yes, when configured with a `PasswordEncoder` and an appropriate `UserDetailsPasswordService`, after authentication succeeds and an upgrade is needed.

**13. Does BCrypt cost 10 live inside {bcrypt} or inside the bcrypt body?**  
Inside the bcrypt body, e.g., the `$2a$10$...` segment.

**14. When switching to PBKDF2 or Argon2, is changing the id enough?**  
No. You must compute new hashes with the target algorithm, keep legacy mappings while needed, and plan migration.

**15. Should {noop} be used for newly registered accounts?**  
No. It stores plaintext and offers no protection if the DB leaks.

**16. What happens if the DB column is too short?**  
It can truncate the prefix or hash body, breaking logins and corrupting migration. Use a sufficiently wide schema.

**17. Does PasswordEncoder protect the HTTP Basic wire transport?**  
No. Raw passwords still travel to the server, so HTTPS/TLS is mandatory.

**18. Why must password hashes never be logged?**  
Because leaked hashes can be attacked offline and expose storage/configuration details; logs add another leak surface.

## 17. Production Deployment Checklist

- [ ] Inventory all existing hash types, prefixes, and unprefixed entries.
- [ ] Configure `PasswordEncoder` with the minimal required mappings; encode new hashes per current policy.
- [ ] Ensure the user store persists the full `{id}encodedPassword` string without truncating or stripping the prefix.
- [ ] Align configuration across signup, login, reset/change-password, and background jobs/admin scripts.
- [ ] Test valid raw passwords, wrong passwords, missing/unknown ids, malformed bodies, and migrations.
- [ ] Never allow clients to supply hashes, prefixes, or authorities to construct a verified identity.
- [ ] Enforce TLS, secret management, password policies, rate limits, brute-force defenses, and MFA where suitable.
- [ ] When supporting legacy formats, bound time and scope, and prepare forced resets.
- [ ] If using upgrade-on-login, wire `UserDetailsPasswordService` and test concurrency and caching.
- [ ] Ensure password hashes never appear in API responses, logs, traces, analytics, or exports.
- [ ] Benchmark bcrypt/Argon2/PBKDF2/scrypt costs and resource limits.
- [ ] Update documentation for schemas, backup/restore, rolling deployments, and rollbacks.
- [ ] Restrict write access to user tables; modifying password hashes enables account takeover.
- [ ] Enforce endpoint/service/tenant authorization after authentication with deny-by-default where appropriate.
- [ ] Keep Spring Boot/Security versions on supported security patches; test hashing/mappings before deploying.

## Conclusion

**`DelegatingPasswordEncoder` bridges multiple password hashing algorithms behind one unified `PasswordEncoder` contract.** The `{id}` prefix at the front of a stored value selects the right verifier during `matches(raw, stored)`; `idForEncode` selects the algorithm for creating new hashes. With Spring Security 6.5's default factory, new hashes typically look like `{bcrypt}...`. Prefixes **do not hash passwords themselves, do not prove login succeeded, cannot be decrypted, and do not replace authorization**.

A safe migration system knows exact hash formats, keeps only necessary mappings during transition, rejects unknown ids per policy, avoids broad `noop` fallbacks, and rehashes after valid authentication or password resets. `upgradeEncoding` is a signal; `UserDetailsPasswordService` paired with a trusted provider/service performs the user-store update. Outside the lab, safeguard TLS, write permissions on user records, hash costs, schemas, logs, sessions/tokens, and failure-path tests.

## Official References

- [Spring Security 6.5 — Password Storage, DelegatingPasswordEncoder, and the {id} format](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security 6.5 — Crypto module and PasswordEncoder](https://docs.spring.io/spring-security/reference/6.5/features/integrations/cryptography.html)
- [Spring Security 6.5 — PasswordEncoderFactories JavaDoc](https://docs.spring.io/spring-security/site/docs/6.5.3/api/org/springframework/security/crypto/factory/PasswordEncoderFactories.html)
- [Spring Security 6.5 — DelegatingPasswordEncoder JavaDoc](https://docs.spring.io/spring-security/site/docs/6.5.3/api/org/springframework/security/crypto/password/DelegatingPasswordEncoder.html)
- [Spring Security 6.5 — PasswordEncoder JavaDoc](https://docs.spring.io/spring-security/site/docs/6.5.3/api/org/springframework/security/crypto/password/PasswordEncoder.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 6.5 — UserDetailsPasswordService JavaDoc](https://docs.spring.io/spring-security/site/docs/6.5.3/api/org/springframework/security/core/userdetails/UserDetailsPasswordService.html)
- [Spring Security 6.5 — In-memory UserDetailsService](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/in-memory.html)
- [Spring Security 6.5 — Spring MVC Security Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html)

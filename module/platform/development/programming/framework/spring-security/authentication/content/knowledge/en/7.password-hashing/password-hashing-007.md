# PasswordEncoderFactories and DelegatingPasswordEncoder

**Module:** Spring Security – authentication. **Knowledge Group:** Password Hashing.

## 1. Real-World Problem: A System with Multiple Generations of Passwords

Imagine an application evolving over many years:

- Very old accounts have passwords stored in a historical format, e.g., `{noop}legacy-password` (for illustration only, **insecure**).
- Other accounts have PBKDF2, scrypt, or bcrypt hashes generated with different parameters.
- New accounts must use the current password-hashing algorithm/policy.
- The application does not know users' raw passwords to convert the entire database to the new format in one shot.

If you configure only `new BCryptPasswordEncoder()`, you may **fail to verify** strings stored as `{pbkdf2}...` or `{noop}...`. If you keep an old encoder so every account can log in, newly created passwords continue using an insufficiently secure algorithm.

Spring Security solves this with **`DelegatingPasswordEncoder`**, and provides the convenient factory **`PasswordEncoderFactories.createDelegatingPasswordEncoder()`**:

1. **Encode** new passwords using a chosen current standard encoder, defaulting to bcrypt in Spring Security 6.5.
2. **Match** submitted passwords against existing hashes using the encoder matching the `{id}` prefix of the **stored value**.
3. **Detect upgrade needs** when a hash uses an older algorithm or work factor so the app can upgrade once a valid raw password is known.
4. Allow historical formats to coexist during the transition period instead of forcing all users to reset immediately.

**Core point:** `PasswordEncoderFactories` is the **factory class** creating the encoder. `DelegatingPasswordEncoder` is the **actual encoder** routing by ID. Neither is a reversible encryption/decryption mechanism, neither is an authentication manager, and neither manages accounts by itself.

## 2. Remembering the PasswordEncoder Contract Accurately

The `org.springframework.security.crypto.password.PasswordEncoder` interface has these primary methods:

~~~java
String encode(CharSequence rawPassword);

boolean matches(CharSequence rawPassword, String encodedPassword);

boolean upgradeEncoding(String encodedPassword);
~~~

| Method | Input | Work Done | Result |
| --- | --- | --- | --- |
| `encode(raw)` | Password just created/changed by user | Generates a new hash value per encoder config | Storable `String` (includes `{id}` with DelegatingPasswordEncoder) |
| `matches(raw, stored)` | Raw password from login request and string stored in repo | Checks whether they match; **no decryption needed** | `true` or `false` when a matching encoder and valid format exist; invalid IDs may throw an exception |
| `upgradeEncoding(stored)` | Stored hash | Indicates whether the hash should be regenerated under the new policy | `boolean`; does not write data automatically |

Example of how you **should not** verify:

~~~java
// WRONG in most password encoders using random salts:
boolean valid = encoder.encode(rawPassword).equals(storedPassword);
~~~

Because two `encode` calls with the same raw password can produce **two different hashes** due to random salts. You must use:

~~~java
boolean valid = encoder.matches(rawPassword, storedPassword);
~~~

**Password hashing** is a one-way transformation with a salt and an appropriate work factor. Never use `Base64.getEncoder()`, decryptable AES, single-round MD5/SHA-256, or `String.hashCode()` as password storage methods. Leaked data is still vulnerable to offline password guessing, so slow algorithms and proper password policies are necessary.

## 3. What Does PasswordEncoderFactories Create?

Full API:

~~~java
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

PasswordEncoder passwordEncoder =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();
~~~

This is an **API illustration snippet**, requiring `spring-security-crypto` (and corresponding app dependencies); it is not a standalone Java program.

In Spring Security **6.5.11**, the factory returns a `PasswordEncoder` whose concrete instance is `DelegatingPasswordEncoder`, configured with:

- **`idForEncode = "bcrypt"`**: creates new passwords using `BCryptPasswordEncoder`.
- A `Map<String, PasswordEncoder>` (`id -> PasswordEncoder`): selects the encoder to **verify** historical hashes by ID.
- The `{id}encodedPassword` string format to identify the algorithm during verification.

**Important:** The return type of the factory method is the `PasswordEncoder` interface, so application code typically depends only on the interface. The factory is not where you call `matches` directly; you invoke it on the returned **instance**.

### Built-In Mappings in 6.5.11

| ID in stored value | Corresponding encoder | Meaning when reading data |
| --- | --- | --- |
| `bcrypt` | `BCryptPasswordEncoder` | **Default used to encode new hashes** in this factory |
| `pbkdf2` | PBKDF2 with Spring Security 5.5 parameters | Supports reading data from the historical parameter set |
| `pbkdf2@SpringSecurity_v5_8` | PBKDF2 with Spring Security 5.8 parameters | Distinguishes configuration by version |
| `scrypt` | scrypt with Spring Security 4.1 configuration | Reads hashes from the historical config |
| `scrypt@SpringSecurity_v5_8` | scrypt with Spring Security 5.8 parameters | Distinguishes version work factor/format |
| `argon2` | Argon2 with Spring Security 5.2 parameters | Supports older Argon2 format |
| `argon2@SpringSecurity_v5_8` | Argon2 with Spring Security 5.8 parameters | Supports updated parameters |
| `noop` | `NoOpPasswordEncoder` | Matches historical plaintext; **never use to store new passwords** |
| `ldap` | `LdapShaPasswordEncoder` | Compatibility for an older LDAP format |
| `MD4`, `MD5` | Corresponding message-digest encoders | Historical; insufficiently secure for new passwords |
| `SHA-1`, `SHA-256` | `MessageDigestPasswordEncoder` | Historical fast digests; **not recommended** for new passwords |
| `sha256` | Old `StandardPasswordEncoder` | Distinct from `SHA-256` above; legacy support only |

This list is taken from the Spring Security 6.5.11 factory Javadoc. Default mappings and encoding algorithms **can change across Spring Security releases**; never hardcode assumptions without checking your project's version.

**Legacy compatibility does not mean every algorithm is safe.** Having `noop`, MD5, or SHA-1 in the map only helps the app recognize/bridge a migration phase. Never use these IDs to create new accounts. Once no records require legacy encoders, evaluate narrowing the mapping or moving the system to a stronger policy.

## 4. What Is the Structure of `{id}encodedPassword`?

With the default factory, output can look like:

~~~text
{bcrypt}$2a$10$XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
└──────┘└──────────────────────────────────────────────────────────┘
   id              encodedPassword generated by BCrypt
~~~

The line above **is a structural diagram, not a real verifiable bcrypt hash**. Each `encode` usually uses a random salt so output varies. Never use the `X...` string as a real hash.

General syntax:

~~~text
{id}encodedPassword
~~~

- `{` and `}` delimit the **ID** at the **beginning of the string**.
- `id` is the encoder lookup key, e.g., `bcrypt`, `pbkdf2@SpringSecurity_v5_8`.
- `encodedPassword` keeps the format produced by that specific encoder; it may include salt, cost, digest, or internal algorithm metadata.
- IDs are **case-sensitive**: `{bcrypt}` and `{BCrypt}` are not treated as the same key.
- ID is not a secret/key and does not add secrecy by hiding the algorithm name; the secrets to protect remain raw passwords and related operational data.

Illustrative format examples:

~~~text
{bcrypt}$2a$10$...                          # bcrypt
{noop}legacy-password                      # plaintext, read-only during migration
{pbkdf2@SpringSecurity_v5_8}...             # PBKDF2 under 5.8 parameter set
{scrypt@SpringSecurity_v5_8}...             # scrypt under 5.8 parameter set
{argon2@SpringSecurity_v5_8}...             # Argon2 under 5.8 parameter set
~~~

The `...` markers are **illustrative only**, not valid hash values.

### Two Types of Information Often Confused

**Encoder ID:** `{bcrypt}` indicates the BCrypt implementation must be used for matching, and in the default factory it is also the ID for new creation.

**Bcrypt cost/salt:** The `$2a$10$...` portion holds bcrypt's own parameters, such as work factor. Changing `BCryptPasswordEncoder` strength **does not necessarily require** changing the ID name; the encoder reads cost from the stored bcrypt hash and can determine upgrade needs.

Do not strip `{bcrypt}` before saving to the DB if the application uses `DelegatingPasswordEncoder`. Never truncate part of a hash to "save column space" because verification will fail.

## 5. How Does DelegatingPasswordEncoder Select an Encoder?

### 5.1. Encode: Always Uses idForEncode

~~~text
rawPassword
    |
    v
DelegatingPasswordEncoder.encode(raw)
    |
    +--> idForEncode = "bcrypt"
                 |
                 v
          BCryptPasswordEncoder.encode(raw)
                 |
                 v
   "{bcrypt}" + bcryptEncodedPassword
~~~

Even though the map includes PBKDF2, scrypt, MD5, noop, etc., **that does not cause `encode` to vary per user**. Unless reconfigured, the current factory's `encode` method always uses bcrypt.

### 5.2. Matches: ID Is Taken from Stored Password

~~~text
rawPassword from form + storedPassword from DB
                          |
                          v
                 Parse {id} prefix
                          |
             +------------+-------------+
             |                          |
         {bcrypt}                   {pbkdf2}
             |                          |
             v                          v
  BCryptPasswordEncoder       Pbkdf2PasswordEncoder
             |                          |
             +------------+-------------+
                          |
                          v
                matches(raw, payload)
                          |
                          v
                     true / false
~~~

In this flow, **the client cannot choose the algorithm** via request body or query params. The system reads the **trusted stored encoded password** to know how to verify. If you allow a client to send `{noop}...` and treat it as the stored value to "authenticate", you have bypassed the trust boundary.

#### Example Outcomes by ID

| Stored value | What happens with the default factory |
| --- | --- |
| `{bcrypt}<valid-bcrypt-hash>` | Invokes BCrypt matches |
| `{noop}legacy-password` | Invokes NoOp matches against `legacy-password`; migration scenario only |
| `{pbkdf2@SpringSecurity_v5_8}<matching-hash>` | Invokes PBKDF2 version 5.8 |
| `$2a$10$...` **missing prefix** | Cannot find ID → throws `IllegalArgumentException` by default |
| `{unknown}<payload>` | ID not in mapping → throws `IllegalArgumentException` by default |
| `{bcrypt}non-bcrypt-string` | ID present but invalid payload → BCrypt may return false and log a security warning depending on implementation |

**Do not automatically assume** every format exception equals a user entering the wrong password. Wrong IDs/configs/DB schemas can be operational bugs needing investigation and audit. In particular, never return hash details, unsupported prefixes, or stack traces to unauthenticated clients.

## 6. Standalone Runnable Java 17 Demo: Create, Verify, Legacy Compatibility, and Unknown ID

The demo uses Gradle and **Spring Security 6.5.11**, requiring no Spring Boot, web server, or DB. The goal is deterministic output even though bcrypt uses random salts.

### 6.1. Project Structure

~~~text
password-delegation/
├── build.gradle
└── src/main/java/demo/PasswordDelegationDemo.java
~~~

**File `build.gradle`:**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'
    implementation 'org.springframework.security:spring-security-crypto:6.5.11'
}

application {
    mainClass = 'demo.PasswordDelegationDemo'
}
~~~

**File `src/main/java/demo/PasswordDelegationDemo.java`:**

~~~java
package demo;

import java.util.Map;

import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.DelegatingPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class PasswordDelegationDemo {

    public static void main(String[] args) {
        PasswordEncoder encoder =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        String raw = "learning-only-password";
        String stored = encoder.encode(raw);

        System.out.println("factory.type="
                + encoder.getClass().getSimpleName());
        System.out.println("new.hasBcryptPrefix="
                + stored.startsWith("{bcrypt}"));
        System.out.println("new.matchesCorrect="
                + encoder.matches(raw, stored));
        System.out.println("new.matchesIncorrect="
                + encoder.matches("wrong-password", stored));
        System.out.println("new.needsUpgrade="
                + encoder.upgradeEncoding(stored));

        // Only illustrates reading legacy {noop}; do not use to
        // create new passwords or as a production policy.
        String legacy = "{noop}old-learning-password";
        System.out.println("legacy.matches="
                + encoder.matches("old-learning-password", legacy));
        System.out.println("legacy.needsUpgrade="
                + encoder.upgradeEncoding(legacy));

        // Illustrates rehashing once the right raw password is known.
        String migrated = encoder.encode("old-learning-password");
        System.out.println("migrated.hasBcryptPrefix="
                + migrated.startsWith("{bcrypt}"));
        System.out.println("migrated.matches="
                + encoder.matches("old-learning-password", migrated));

        try {
            encoder.matches("guess", "unprefixed-legacy");
            System.out.println("missingPrefix=unexpected-success");
        } catch (IllegalArgumentException expected) {
            System.out.println("missingPrefix=IllegalArgumentException");
        }

        try {
            encoder.matches("guess", "{notMapped}payload");
            System.out.println("unknownId=unexpected-success");
        } catch (IllegalArgumentException expected) {
            System.out.println("unknownId=IllegalArgumentException");
        }

        // Narrow custom map configuration: only accepts bcrypt.
        PasswordEncoder bcryptOnly = new DelegatingPasswordEncoder(
                "bcrypt", Map.of("bcrypt", new BCryptPasswordEncoder())
        );
        System.out.println("custom.matchesBcrypt="
                + bcryptOnly.matches(raw, stored));

        try {
            bcryptOnly.matches("old-learning-password", legacy);
            System.out.println("custom.rejectsNoop=false");
        } catch (IllegalArgumentException expected) {
            System.out.println("custom.rejectsNoop=true");
        }
    }
}
~~~

Run from `password-delegation` with JDK 17+ and a compatible Gradle:

~~~bash
gradle -q run
~~~

If the project has a Gradle Wrapper, use `./gradlew -q run`; on Windows use `gradlew.bat -q run`. The first run downloads dependencies from Maven Central.

**Stdout printed by the program** (excluding separate Gradle/library logs if your environment configures any):

~~~text
factory.type=DelegatingPasswordEncoder
new.hasBcryptPrefix=true
new.matchesCorrect=true
new.matchesIncorrect=false
new.needsUpgrade=false
legacy.matches=true
legacy.needsUpgrade=true
migrated.hasBcryptPrefix=true
migrated.matches=true
missingPrefix=IllegalArgumentException
unknownId=IllegalArgumentException
custom.matchesBcrypt=true
custom.rejectsNoop=true
~~~

### 6.2. Detailed Output Explanation

- `factory.type=DelegatingPasswordEncoder`: the factory returns an instance implementing `PasswordEncoder`.
- `new.hasBcryptPrefix=true`: the encode ID chosen by factory 6.5.11 is `bcrypt`.
- `new.matchesCorrect=true` despite random hashes each time: `matches` reads salt/work factor from the hash and verifies the raw password.
- `new.matchesIncorrect=false`: a different raw password does not match the stored hash.
- `new.needsUpgrade=false`: bcrypt just generated at the same encoder's default cost does not yet need rehashing under that policy.
- `legacy.matches=true`: the factory **includes a legacy noop mapping**; this only illustrates transition compatibility and **is a risk if production still holds plaintext passwords**.
- `legacy.needsUpgrade=true`: the legacy ID differs from `idForEncode=bcrypt`, signaling migration is needed.
- `migrated.hasBcryptPrefix=true`: once a valid raw password is known, a new hash can be generated under current policy.
- `missingPrefix` and `unknownId`: no matching mapping exists; by default it does not silently fall back.
- `custom.matchesBcrypt=true` and `custom.rejectsNoop=true`: a map containing only bcrypt still verifies bcrypt, while actively rejecting noop; custom maps **do not automatically inherit mappings from the factory**.

**Do not compare literal bcrypt strings.** Random salts make specific hashes differ across runs, so the example prints only prefixes and predictable boolean conditions.

### 6.3. The Demo Does Not Automatically Migrate the Database

The example creates a `migrated` variable in memory; **no record has been updated**. A real application must only persist the new hash after verifying the raw password successfully and ensuring the request does not belong to a locked/disabled account. Updates must avoid overwriting newer passwords created by concurrent changes.

## 7. Upgrading Password Hashes Safely

### 7.1. Why Upgrade?

Optimal algorithms and costs evolve over time with hardware and security requirements. A system may want to:

- Move from `{noop}` or overly fast digests to properly configured bcrypt/Argon2/PBKDF2;
- Raise the bcrypt work factor as hardware gets faster;
- Migrate from older PBKDF2/scrypt/Argon2 parameters to newer ones;
- Add policies checking for weak/breached passwords per current guidance.

`DelegatingPasswordEncoder.upgradeEncoding(stored)` helps evaluate **whether to rehash**. With the default 6.5.11 factory, hashes with IDs other than `bcrypt` are usually upgrade candidates; bcrypt hashes may also need upgrading if their cost is lower than the current bcrypt config.

**This method does not decrypt passwords and does not write to the DB.** One-way hashes cannot be converted to new bcrypt without knowing the raw password. There are two standard paths: **rehash upon successful login** or **require a password reset** for users who have not returned.

### 7.2. Rehash-on-Login at the Proper Boundary

~~~text
POST /login: username + raw password
                |
                v
      AuthenticationManager / Provider
                |
         +------+------+
         |             |
      failure       success
         |             |
         v             v
       deny      matches(raw, stored) = true
                       |
                       v
                upgradeEncoding(stored)?
                       |
               +-------+-------+
               |               |
              no              yes
               |               |
               v               v
          keep hash      encode(raw) with new policy
                               |
                               v
                          write to DB
                      via compare-and-swap
                               |
                               v
                     audit event, evict cache
                               |
                               v
                      return auth result
~~~

**Important:** Rehash **only after both credentials and account status have been verified valid**. Never upgrade a hash for a fake username or wrong password attempt. Restrict logs from capturing raw passwords, new hashes, and credential lifetimes.

### 7.3. DaoAuthenticationProvider + UserDetailsPasswordService

Spring Security provides the `UserDetailsPasswordService` interface with the method:

~~~java
UserDetails updatePassword(UserDetails user, String newPassword);
~~~

Here `newPassword` is the **newly encoded password** produced by `PasswordEncoder.encode(...)`, not plaintext. When `DaoAuthenticationProvider` is configured with `UserDetailsPasswordService`, the provider can call `PasswordEncoder.upgradeEncoding(...)` after successful authentication and delegate persisting the new hash to that service.

**Integration config template, not a standalone class:**

~~~java
@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
}

@Bean
DaoAuthenticationProvider daoAuthenticationProvider(
        UserDetailsService userDetailsService,
        UserDetailsPasswordService passwordUpdater,
        PasswordEncoder passwordEncoder) {

    DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(userDetailsService);

    provider.setPasswordEncoder(passwordEncoder);
    provider.setUserDetailsPasswordService(passwordUpdater);
    return provider;
}
~~~

This template assumes the Spring Boot Servlet application already has `@Bean` imports, `UserDetailsService`/`UserDetailsPasswordService` beans, an account store, and proper `SecurityFilterChain` wiring. Merely copying these two beans into an app **does not automatically** route every login path through the provider or migrate the database.

Without a suitable `UserDetailsPasswordService` wired into the provider, **do not assume migrations happen automatically**. Calling `encoder.matches(...)` and `encoder.upgradeEncoding(...)` alone only checks conditions; no new password is written.

`UserDetailsPasswordService` differs from `UserDetailsManager.changePassword(oldPassword,newPassword)` for user-initiated password changes. One interface serves the provider **upgrading hashes after login**, while the other serves **account management operations**. Distinguish actor permissions, auditing, and raw password handling.

### 7.4. Concurrency Control During Upgrades

For example, request A logs in with the old password and starts rehashing; concurrently, request B resets the password to a new value. If A writes the new hash of the old password after B's reset, the system can **accidentally restore the old password**.

Do not simply use:

~~~java
// UNSAFE ILLUSTRATIVE CODE without concurrency checks:
repository.updatePasswordHash(userId, freshlyEncodedHash);
~~~

A safer design uses conditional updates, for example:

~~~sql
-- Illustrative SQL: concurrent changes are not overwritten.
UPDATE users
SET password_hash = :newHash,
    password_version = password_version + 1
WHERE id = :userId
  AND password_hash = :oldHash
  AND password_version = :oldVersion;
~~~

**The updated row count must be 1** to consider the upgrade successful. If 0, a concurrent change occurred; do not overwrite, handle the conflict or accept the newer hash according to verified auth logic. Depending on schema, version alone may suffice instead of comparing hashes; execution must fit your app's transaction/DB model.

After upgrading, evict relevant `UserDetails`/authentication caches, account for replica lag, and clear any username/tenant mappings. Never assume a hash upgrade automatically logs out sessions or revokes JWTs; that belongs to a separate session/token policy.

## 8. Legacy Data Without Prefixes: How to Handle It?

A common error when upgrading Spring Security:

~~~text
There is no PasswordEncoder mapped for the id "null"
~~~

This error appears when the DB stores raw bcrypt payloads directly:

~~~text
$2a$10$...
~~~

while the application switched to `DelegatingPasswordEncoder`, which looks for an ID at the **start of the stored value**, such as `{bcrypt}$2a$10$...`.

**Never fix this globally with `NoOpPasswordEncoder`.** Doing so weakens authentication, especially if the DB holds unprotected plaintext anywhere.

### Option A – Migrate Known-Algorithm Data to Accurate Prefixes

If you have verified that an **entire group of records** is bcrypt (valid format, trusted source, compliant policy), you can prepend `{bcrypt}` in a controlled migration.

~~~text
Before: $2a$10$<valid-bcrypt-hash>
After:  {bcrypt}$2a$10$<same-hash>
~~~

You do not need raw passwords because you are **only adding ID metadata**, without changing the underlying hash. However, if data is a mix of bcrypt, scrypt, SHA, etc., never prepend `{bcrypt}` across the board.

Practical steps: back up data, analyze stored formats actually present, test on a clone, run conditional SQL migration, verify column lengths and encoding, deploy with rollback, and monitor login failures. If the DB holds hashes of unknown origin, requiring resets may be safer than guessing formats.

### Option B – Controlled Fallback for a Defined Cohort

`DelegatingPasswordEncoder` has:

~~~java
void setDefaultPasswordEncoderForMatches(
        PasswordEncoder defaultPasswordEncoderForMatches);
~~~

This is a **configuration API** to use an alternative encoder when the stored ID is absent from the map (including missing IDs). By default Spring Security **throws IllegalArgumentException** in those cases.

**Risk:** A fallback can cause malformed data/unknown IDs to be interpreted by an unintended algorithm. Furthermore, the fallback encoder receives the **entire stored string**, including any unmapped `{id}`, without stripping prefixes automatically. Never blindly attach `NoOpPasswordEncoder` or a "try every algorithm until one matches" fallback for all users.

If a short-term fallback is truly unavoidable:

1. Restrict the cohort using verified migration metadata, never client-supplied data.
2. Write and test an explicit format parser; unknown IDs must be rejected.
3. Track migration metrics showing how many records still lack prefixes.
4. Force upgrades upon successful login or reset.
5. Remove the fallback once the cohort is cleared.

### Option C – Password Reset

When hash history is untrusted, algorithms are unsupported, or formats cannot be verified, require users to set a new password via a **verified recovery channel**. Never try to deduce raw passwords from hashes; properly designed password hashing has no decrypt function.

## 9. Configuring DelegatingPasswordEncoder Manually

You can call the constructor directly when you want a tightly controlled map:

~~~java
import java.util.Map;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.DelegatingPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

Map<String, PasswordEncoder> encoders = Map.of(
        "bcrypt", new BCryptPasswordEncoder(12)
);

PasswordEncoder encoder =
        new DelegatingPasswordEncoder("bcrypt", encoders);
~~~

This is an illustrative Java snippet, **not a standalone class**. It has these properties:

- The default ID for encoding is `bcrypt`, with strength 12 specified.
- When `matches` encounters `{bcrypt}`, the encoder can verify legacy-cost bcrypt hashes because cost metadata lives inside the hash.
- `{noop}...` or other IDs **are unsupported** because the map contains only bcrypt.
- Default factory mappings **are not inherited automatically**. If the system must read multiple legacy formats, declare the corresponding encoders per your migration policy.

**Do not raise strength arbitrarily** without benchmarking. BCrypt's work factor makes computation time grow rapidly; too high slows logins or causes CPU exhaustion under request floods. Too low leaves hashes more exposed to offline attacks. Weigh performance requirements, security policy, hardware capacity, rate limiting, and target login latency.

### IDs and Algorithms Do Not Have to Match Default Names

A system might want versioned IDs:

~~~java
Map<String, PasswordEncoder> encoders = Map.of(
        "bcrypt-v2", new BCryptPasswordEncoder(12),
        "bcrypt-v1", new BCryptPasswordEncoder(10)
);

PasswordEncoder encoder =
        new DelegatingPasswordEncoder("bcrypt-v2", encoders);
~~~

New encodings start with `{bcrypt-v2}`; when matching strings with `{bcrypt-v1}`, the map selects the corresponding implementation, and `upgradeEncoding(...)` normally flags old IDs differing from the new target.

**Note:** With BCrypt, hashes already embed cost so many systems keep a single `bcrypt` ID and tune strength via policy; whether to use versioned IDs is a data, deployment, and migration decision. Never rename IDs casually and lose track of map/DB history.

### When Choosing Argon2/PBKDF2/scrypt as the Primary Encoder

You can build a `DelegatingPasswordEncoder` with your chosen ID and encoder instead of relying on the factory's bcrypt default. However, verify:

- Algorithm version, cost/iteration/memory/concurrency settings, and required dependencies;
- Java/runtime compatibility and existing stored hash data;
- Benchmarks on production hardware, login load limits, and password reset flows;
- How `upgradeEncoding(...)` behaves and transition policies when parameters change;
- Internal/industry regulations (e.g., environments with specific compliance mandates).

**Do not assume** the default factory switches to Argon2 automatically just because an Argon2 ID appears in its map.

## 10. Integrating in a Spring Boot Servlet Application

### 10.1. Declaring a PasswordEncoder Bean

~~~java
@Configuration
class SecurityPasswordConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }
}
~~~

This is a **configuration fragment** in a Spring Boot app that already has dependencies and imports for `@Configuration`, `@Bean`, `PasswordEncoder`, and `PasswordEncoderFactories`. It contains no main class, repositories, providers, or routes, so it is not a standalone program.

In Spring Boot apps, manage Spring Security module versions via Boot's BOM/dependency management rather than mixing versions manually.

### 10.2. When Creating a User

~~~java
// Inside an authorized service; not a standalone class.
String passwordHash = passwordEncoder.encode(signupRawPassword);

UserDetails user = User.withUsername(validatedUsername)
        .password(passwordHash)
        .roles("USER") // server-side role, never from request
        .build();

userDetailsManager.createUser(user);
~~~

**Store the exact `{bcrypt}...` string** returned by `encode(...)` in the DB. Never call `encode` a second time before persisting, because double hashing breaks verification against the original password. Never hardcode "hashes are always 60 characters" since the `{id}` prefix and other algorithms have different lengths.

### 10.3. On Login

~~~text
UsernamePasswordAuthenticationFilter
               |
               v
AuthenticationManager / ProviderManager
               |
               v
DaoAuthenticationProvider
       |                |
       v                v
UserDetailsService   PasswordEncoder
   load hash         matches(raw, stored)
       |                |
       +--------+-------+
                |
         valid credential?
                |
        +-------+-------+
        |               |
       no              yes
        |               |
        v               v
 AuthenticationException   authenticated Authentication
                            |
                            v
                        SecurityContext
~~~

`DaoAuthenticationProvider` uses the configured `PasswordEncoder` to verify the user-submitted password against `UserDetails.getPassword()`. In Spring Security 6.5, if none is explicitly configured, the provider falls back to a default delegating encoder mechanism; in real systems, configure it explicitly **so password-creation and password-verification policies stay aligned**.

Write end-to-end tests through your app's actual filter chain/controller, because a valid bean ignored by another provider or filter can still cause bugs.

### 10.4. On Password Change

Self-service password change differs from rehash-on-login:

1. The user is already authenticated and may need re-authentication with the old password/MFA depending on risk.
2. Validate the new password policy and protect CSRF/session.
3. `passwordEncoder.encode(newRawPassword)` produces the `{id}...` value.
4. Update the account store for the exact user/tenant within a transaction and secure audit log.
5. Apply session/token invalidation policies as required.
6. Clear/refresh `UserDetails` caches and related authorization sources when auth data changes.

Never pass plaintext into a method expecting an **encoded password** hoping the manager will hash it automatically. `UserDetailsManager.changePassword` and custom implementations must have their exact contracts checked.

## 11. Data, Transactions, and Operational Rules

### 11.1. Column Length

A `password_hash VARCHAR(60)` column may fit classic bcrypt payloads, yet is **too short** for `{bcrypt}` + payload, and certainly offers no room for Argon2/PBKDF2 or future formats. Choose limits for supported algorithms and migration paths; e.g., `VARCHAR(255)` or larger **per schema design and actual storage**. Test insert/readback to ensure prefixes/salts are never truncated.

### 11.2. Hash Consistency

When upgrading hashes in environments with DB replication, multiple nodes, or caches:

- Update hash and password version atomically;
- Evict user-details caches **after commit**; avoid loaders repopulating stale values;
- During upgrading logins, guard against races with password resets/new passwords;
- Ensure all nodes recognize new `{id}` mappings before the DB writes the new format;
- During rolling deployments, never write hashes with IDs that older app versions cannot read yet;
- Monitor login failure rates from unknown IDs and migration success rates.

When rolling out a new encoder across multiple nodes, prefer **dual-read, single-write**: every node can read both old and new formats before any node starts writing the new format. Once all data is upgraded and the rollback window closes, old mappings can gradually be retired per policy.

### 11.3. Access Control for Hash Data

One-way hashes do not make the database public. Restrict SELECT permissions on password columns, backups, exports, logs, traces, Redis/caches, DBA/admin privileges, and data in transit. Never log entire `UserDetails` objects or hash values when `matches(...)` fails. Enforce TLS on login and apply proper rate limiting to protect hash computation resources.

### 11.4. Hashing Does Not Replace MFA or Breached-Password Checks

Slow password hashing reduces the effectiveness of offline attacks after a DB leak. It **does not stop** online password spraying, credential stuffing, or phishing. Pair it with rate limiting, anti-enumeration, MFA/passkeys where appropriate, session hygiene, and secure reset/recovery flows.

## 12. Common Failures and Diagnosing Root Causes

| Symptom | Common Cause | How to Check and Fix |
| --- | --- | --- |
| `There is no PasswordEncoder mapped for id "null"` | DB stores hashes missing `{id}`, or wrong prefix | Analyze stored formats; migrate to prepend accurate algorithm prefix |
| `There is no PasswordEncoder mapped for id "foo"` | `{foo}` is absent from the mapping | Check version, map, and data; never fall back casually |
| Registration succeeds yet login always fails | DB stored raw passwords where `{bcrypt}` was expected, or double-encoded | Inspect account creation/encoding path so it encodes once |
| Login fails after upgrade | User creation uses raw BCrypt while login uses Delegating or vice versa | Standardize encoder and data format everywhere |
| Truncated hash in DB | Column too short for new prefix/format | Widen schema, audit corrupted rows, reset passwords as needed |
| `matches(raw, encoded)` returns false | Wrong password, valid ID with mismatched payload, or corrupted data | Do not leak details to clients; inspect format/hash/encoder internally |
| `newHash.equals(oldHash)` false for same raw | Random salt | Use `matches(...)`, never compare hash strings |
| `upgradeEncoding` true yet DB unchanged | `UserDetailsPasswordService` not wired or write unimplemented | Wire upgrade pipeline and test storage readback |
| Old password restored after reset | Race between rehash-on-login and password reset | CAS/version check inside DB transaction |
| Custom bcrypt-only config locks out old users | Required legacy mapping dropped | Deploy dual-read migration first, then retire legacy |
| `{noop}` used for new accounts | Insecure algorithm chosen or test config leaked to prod | Default factory uses bcrypt; enforce per-environment security configs |
| Single-round SHA-256 used for passwords | Digest far too fast for password storage | Choose a password-hashing algorithm built for passwords |
| Old app nodes fail on new ID during rollout | Missing backward compatibility in multi-node deploy | Dual-read before single-write, with rollback plan |
| Auth fails and returns exception class/hash in JSON | Exposes credential policy and account internals | Generic public failure; detailed yet safe internal audit |
| Setting `setDefaultPasswordEncoderForMatches(NoOp...)` | Ignores untrusted IDs; overly broad fallback risk | Reject unknown ids; migrate cohorts safely |
| Treating `{id}` as salt or key | Confuses algorithm metadata with secrets/hashes | Separate prefix from algorithm payload |
| Raising bcrypt cost too high | Slow logins / CPU DoS | Benchmark, rate-limit, and tune cost per policy |

## 13. Deployment Testing Checklist

### Unit Tests for PasswordEncoder

- `encode(raw)` returns a hash prefixed with `{bcrypt}` when using the default 6.5.11 factory.
- `matches(raw, encode(raw))` returns true; `matches(other, encode(raw))` returns false.
- Two `encode` calls for the same raw password may differ due to random salt; assert prefix and `matches` only.
- `matches(raw, "{noop}" + raw)` may return true in legacy-compatibility mode; **never** treat that as a valid production algorithm.
- `matches(raw, storedWithoutId)` and unknown ids throw `IllegalArgumentException` by default.
- `upgradeEncoding(legacyHash)` returns true when the old ID differs from the encode ID; false on fresh hashes under unchanged policy.
- Custom mappings do not automatically support IDs you omitted from the map.

### Tests for Real Accounts/Logins

- Create a user via the actual registration flow, persist to DB, load `UserDetails.getPassword()`, and verify with the exact encoder.
- Log in with valid/invalid credentials through `AuthenticationManager` or the real filter chain; locked/disabled accounts remain rejected.
- Legacy user logs in successfully and upgrades hash **only** when `UserDetailsPasswordService` is wired; DB readback shows new prefix/cost.
- When password reset runs concurrently with login upgrade, the old password is not restored.
- All deployed nodes understand both old and new prefixes during rolling upgrades.
- `UserDetails` cache invalidates properly and does not wipe hashes in shared objects due to `ProviderManager.eraseCredentials()`.
- Unknown ID/format errors trigger internal metrics/audits without leaking details to unauthenticated callers.
- Inactive accounts are handled via reset policies, never plaintext recovery.

### Operational Testing

Measure `encode` and `matches` durations at target cost on realistic hardware and load scale. Authentication tests must not contain real passwords or production hashes. Test databases with Unicode usernames, non-ASCII passwords, wide columns, collations, and case-sensitive migration ids. Monitor login failures, CPU, upgrade rates, remaining legacy records, and version compatibility on every rollout.

## 14. Self-Check Questions

**Question 1.** Does `PasswordEncoderFactories.createDelegatingPasswordEncoder()` create MD5 hashes for new users because MD5 is in its map?  
**Answer:** No. In factory 6.5.11, `idForEncode=bcrypt`, so new encodings use bcrypt. Other encoders exist to match corresponding formats.

**Question 2.** Why does `{bcrypt}...` differ from `$2a$...` when using DelegatingPasswordEncoder?  
**Answer:** DelegatingPasswordEncoder uses `{id}` to select the implementation. Unprefixed hashes have `id=null` and are rejected by default, even when the payload is valid bcrypt.

**Question 3.** Calling `encoder.encode("abc")` twice yields two different strings. Is that a bug?  
**Answer:** No. Random salts produce different hashes; `matches("abc", stored)` is the right operation to verify.

**Question 4.** An app stores `{noop}password` and the default factory matches it. Does that mean password security is good?  
**Answer:** No. Plaintext storage is a major risk. The mapping exists only to read legacy records during migration; upgrade or reset them.

**Question 5.** If `{unknown}hash` appears, is adding a `NoOpPasswordEncoder` fallback a safe fix?  
**Answer:** No. That blurs format boundaries and can accidentally accept unverified strings; analyze and migrate data explicitly instead.

**Question 6.** After login, `encoder.upgradeEncoding(oldHash)` is true. Is the database updated automatically?  
**Answer:** Not yet. You must rehash from the verified raw password and persist it; in `DaoAuthenticationProvider` you can configure an appropriate `UserDetailsPasswordService`.

**Question 7.** Can old MD5 hashes be converted to bcrypt without knowing raw passwords?  
**Answer:** You cannot compute `bcrypt(raw)` from a one-way MD5 hash equivalently. You must rehash when a valid raw password is provided or require a reset.

**Question 8.** Why must all nodes understand the new ID **before** the first node writes new hashes?  
**Answer:** An older node might read a newly upgraded record and fail to find an encoder for the new ID, causing login failures. Deploy dual-read before single-write.

**Question 9.** Why can a `VARCHAR(60)` column break after switching to delegating?  
**Answer:** The new string adds the `{bcrypt}` prefix on top of the bcrypt payload, and other algorithms are even longer; truncation destroys data needed by `matches`.

**Question 10.** Is `PasswordEncoder` responsible for locking accounts, assigning roles, or managing sessions?  
**Answer:** No. It only encodes, matches, and evaluates upgrades. Providers manage auth, `UserDetails` supplies flags/authorities, web/security context handles login sessions, and account management sits in the business layer.

## 15. Official References

- [Spring Security 6.5 – Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html): password hashing history, `{id}encodedPassword` format, encode/matches, and upgrades.
- [Spring Security 6.5.11 – PasswordEncoderFactories Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/factory/PasswordEncoderFactories.html): `createDelegatingPasswordEncoder()`, default bcrypt ID, and all default mappings.
- [Spring Security 6.5.11 – DelegatingPasswordEncoder Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/DelegatingPasswordEncoder.html): constructors, ID parsing, `setDefaultPasswordEncoderForMatches`, and `upgradeEncoding`.
- [Spring Security 6.5.11 – PasswordEncoder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/PasswordEncoder.html): `encode`, `matches`, and `upgradeEncoding`.
- [Spring Security 6.5 – DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): coordinating `UserDetailsService` and `PasswordEncoder` in auth.
- [Spring Security 6.5.11 – UserDetailsPasswordService](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetailsPasswordService.html): persisting new password hashes via `updatePassword`.
- [OWASP – Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): salt, proper password-hashing algorithms, cost, and migrations.
- [OWASP – Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): defending against brute force, credential stuffing, and account management.

**Remember:** The **Factory** supplies default mappings, and **DelegatingPasswordEncoder** uses the stored hash's `{id}` to pick the encoder for matching while using `idForEncode` for new hashes. **`upgradeEncoding` is only a signal**: you need the verified raw password, conditional storage updates, and consistent security policy across all nodes. Never use legacy compatibility as an excuse to keep creating weak passwords.

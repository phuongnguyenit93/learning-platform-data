# Choosing a New Algorithm While Still Verifying Legacy Data

> **Context:** Spring Security → authentication → **Password upgrades**. In a system with existing real users, changing the password hashing algorithm is not just replacing `PasswordEncoder`. The system must continue **accurately verifying legacy hashes**, generate new hashes according to the current policy, upgrade gradually when valid password proof is presented, and avoid accidentally opening a weak login path. This article focuses on `DelegatingPasswordEncoder`, the `{id}encodedPassword` format, `upgradeEncoding`, `DaoAuthenticationProvider`, `UserDetailsPasswordService`, and safe migration rollout. Java 17 examples use Spring Security 6.5.11.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish between **the algorithm used to encode new passwords** and **the algorithms retained to verify legacy hashes**; explain why these two sets do not have to be identical.
2. Correctly read the `{id}encodedPassword` string of `DelegatingPasswordEncoder`; understand that the ID is metadata for selecting the hash decoder, **not a secret** and not proof of a valid password.
3. Choose new algorithms and parameters based on security policy, CPU/RAM resources, verification cost, and data compatibility.
4. Maintain verification for legacy bcrypt/scrypt/Argon2/PBKDF2 hashes when needed, while **never automatically accepting plaintext, MD5, or hashes of unknown origin**.
5. Understand `matches`, `encode`, `upgradeEncoding`, when to use `UserDetailsPasswordService.updatePassword`, and how `DaoAuthenticationProvider` supports upgrading hashes after successful login.
6. Handle legacy hashes **without an ID prefix**, malformed hashes, unsupported IDs, users who rarely log in, and concurrent password changes.
7. Run a complete Java 17 program demonstrating **legacy bcrypt → new Argon2id**, keeping login working, rehashing on login, testing wrong passwords, and rejecting hashes without an ID.
8. Design a multi-instance rollout plan: reading both formats before writing the new format; monitoring, rollback, constrained rollback, canarying, and security testing.

## 2. The Practical Problem: You Cannot Swap the Encoder and Assume Legacy Data Is Compatible

Suppose the database currently contains:

~~~text
users
---------------------------------------------------------
username   password_hash
lan        $2a$10$...              (legacy bcrypt, no ID)
minh       {bcrypt}$2a$12$...      (bcrypt with ID)
mai        {scrypt}$...            (scrypt with old parameters)
~~~

Each hash string is the output of an algorithm with its own salt/parameters; the raw password **is not stored**. The organization decides to use Argon2id for new passwords. If you only replace a single bean:

~~~java
@Bean
PasswordEncoder passwordEncoder() {
    return Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8();
}
~~~

then `Argon2PasswordEncoder` **does not automatically know how to verify legacy bcrypt/scrypt strings**. The login path using legacy hashes can fail even when users enter the right password. This is different from "the user entered the wrong password": the issue is that **the application lost the ability to read the legacy hash format**.

The architecturally sound approach:

- The output of **`encode(raw)`** uses the **new** algorithm/parameters.
- The input to **`matches(raw, storedHash)`** selects the encoder **matching the stored hash's metadata**.
- After a successful verification, you can **re-encode the just-entered raw password** using the new algorithm and update the record.
- Do not try to "directly convert" a bcrypt hash string into an Argon2 hash of the original password; password hashing functions are **one-way**.

### 2.1. A Different Answer for Three Questions

| Question | Responsibility |
| --- | --- |
| Which algorithm should new registrations/password resets use starting today? | `idForEncode` and the current policy encoder |
| On login, which algorithm generated the hash in the database? | Trusted ID/metadata of each record |
| After a successful login, does the legacy hash need upgrading? | `upgradeEncoding`, security policy, and `UserDetailsPasswordService`/DB logic |

**Key point:** supporting verification of legacy hashes does **not** mean continuing to generate new hashes with the old algorithm. Separate the **read/verify** path from the **write/encode** path so upgrading does not lock out existing users.

## 3. Password Hashes Are One-Way and Versioned Data

A suitable `PasswordEncoder` generates an adaptive salted hash. When verifying, the application uses the raw password **just submitted by the client through a valid authentication flow** and the hash stored in the account store.

~~~java
String encoded = passwordEncoder.encode(rawPassword);
boolean match = passwordEncoder.matches(candidatePassword, encoded);
~~~

With standard encoders, two `encode` calls on the same password usually return different strings because of random salts. Therefore, **do not** verify by doing:

~~~java
// WRONG: encode() generates a new salt; string comparison usually will not match.
boolean ok = passwordEncoder.encode(candidatePassword)
        .equals(storedHash);
~~~

### 3.1. Why Can't You Batch-Rehash Directly from Legacy Hashes?

A bcrypt string does not contain the raw password. You cannot do:

~~~text
Argon2id(bcryptHash)
~~~

and claim the result is:

~~~text
Argon2id(originalPassword)
~~~

The two inputs are **two different strings**. A "hash of a hash" also leads to a different verification contract and can create an error-prone migration path, rather than an equivalent password algorithm transition. A reliable migration requires **the raw password at the moment a user successfully authenticates**, or requiring users to reset their passwords through a verified workflow.

Do not store raw passwords in queues, logs, analytics, audit tables, or background jobs just to rehash later. You should upgrade the hash **right within the authentication boundary** before discarding the raw password data.

### 3.2. Parameters Are Also Versions

"Bcrypt" is not a single security level: bcrypt has a cost factor. "Argon2id" alone does not describe the CPU/RAM budget: it requires memory cost, iterations, and parallelism. Hash strings from encoders usually embed the data needed for `matches`; the metadata **selecting the algorithm** via `DelegatingPasswordEncoder`'s ID is still another layer.

When the algorithm stays the same but the work factor increases, the encoder can also signal that an upgrade is needed. That decision depends on the implementation's `upgradeEncoding` and application policy, not a cron job automatically reading passwords from hashes.

## 4. How Should You Choose the New Algorithm?

Some common options supported by Spring Security:

| Encoder | Category | Typical parameters | Migration notes |
| --- | --- | --- | --- |
| `BCryptPasswordEncoder` | Adaptive password hash | Cost/strength | Easy compatibility with legacy systems using bcrypt; just changing cost is already an upgrade |
| `SCryptPasswordEncoder` | Memory-hard adaptive KDF | `N,r,p` | CPU/RAM intensive; benchmark and limit concurrency |
| `Argon2PasswordEncoder` | Memory-hard (Argon2id in Spring Security's implementation) | Memory KiB, iterations, parallelism | Bouncy Castle on classpath; check resource budget |
| `Pbkdf2PasswordEncoder` | Adaptive KDF | Iterations, PRF, salt | May fit compliance constraints; need to specify preset version |
| Standalone MD5/SHA-1/SHA-256 | Fast hashes, unsuitable for new passwords | No adaptive work factor | Do not use as an upgrade target; handle legacy strictly and prioritize reset |

No choice is right just because the algorithm has a newer name. A decision should consider **threat model**, supported library versions, server memory limits and concurrency, verification latency on real hardware, database state, and the upgrade path. Examples use Argon2id for illustration, **which does not mean every application must migrate to Argon2id**.

### 4.1. Argon2id, scrypt, or a New bcrypt Cost?

- If the system mainly stores low-cost bcrypt, **increasing the bcrypt cost** can be simpler than migrating the entire algorithm, provided policy and performance allow it.
- If the organization chooses Argon2id to increase memory hardness, check dependencies, memory concurrency, and rollout capability across all instances.
- For systems using PBKDF2 due to compliance requirements, keep the appropriate format and parameters instead of switching algorithms just for trends.
- Choose **maintained** technology and benchmarked parameters; do not blindly copy a fixed number from a laptop onto production containers.

Spring Security documentation guides tuning the weight of a single password verification on the target system, often using around **one second** as a reference point. This is a **benchmarking guideline**, not an SLA applicable to every system. You must also test p95/p99 under concurrent login load.

### 4.2. Do Not Use "Longer Hash" as the Sole Security Criterion

A 64-byte hash is not necessarily safer than a 32-byte hash if the algorithm is fast or the password is weak. Random salt, adaptive algorithms, work factor, memory hardness, login controls, and the sensitivity of stored data together determine overall security.

## 5. DelegatingPasswordEncoder: One Encoder to Write New, Many Encoders to Read Old

Spring Security uses `DelegatingPasswordEncoder` to separate two goals:

~~~text
                    encode(raw)
                        |
                        v
          {current-id}currentEncodedHash

stored {id}hash ---- matches(raw, stored)
         |
         +--- id=bcrypt-v1 ----> BCryptPasswordEncoder
         |
         +--- id=scrypt-v1 ----> SCryptPasswordEncoder
         |
         +--- id=argon2-v58 --> Argon2PasswordEncoder
~~~

Constructor:

~~~java
DelegatingPasswordEncoder encoder =
        new DelegatingPasswordEncoder(
                "argon2-v58",
                Map.of(
                        "bcrypt-v1", new BCryptPasswordEncoder(10),
                        "argon2-v58",
                            Argon2PasswordEncoder
                                    .defaultsForSpringSecurity_v5_8()));
~~~

**Two roles of the configuration:**

- `"argon2-v58"` as the first argument is **`idForEncode`**: new hashes created by `encode` will have the `{argon2-v58}` prefix.
- The `Map` allows `matches` to pick the encoder corresponding to each **stored ID**. Records with `{bcrypt-v1}...` are still verified with bcrypt, even though it is no longer used for new encoding.

The IDs `bcrypt-v1` and `argon2-v58` in the example are **application-defined IDs**. They are not names forced by the standard factory; when changing IDs in configuration, you must update/maintain the mapping for corresponding legacy data.

### 5.1. Standard Storage Format

~~~text
{id}encodedPassword
~~~

Examples:

~~~text
{bcrypt-v1}$2a$10$...
{argon2-v58}$argon2id$v=19$m=16384,t=2,p=1$...
~~~

The ellipses here **only illustrate the format**, not complete hashes that can be verified. Real data must be the **intact** hash string generated by the encoder, including the salt and required algorithm components.

`DelegatingPasswordEncoder` reads the ID from the beginning of the string. If there is no prefix or the ID is not in the map, **by default `matches` throws `IllegalArgumentException`**, rather than trying every algorithm until one matches. This is a fail-safe behavior worth keeping.

### 5.2. Do Not Equate the ID with an Algorithm Inferred from the String

Even though bcrypt starts with `$2a$` or `$2b$`, `DelegatingPasswordEncoder` does not automatically detect all legacy formats when `{id}` is missing. It uses the **ID mapping that you configure**.

If the prefix is missing, the solution must rely on **trusted provenance metadata**: knowing which application version, column/tenant, and encoder created the record. Do not accept arbitrary unprefixed strings via a free-form guesser that could turn malformed data into a weak login path.

### 5.3. What Is in the Default Factory Mapping?

Spring Security provides:

~~~java
PasswordEncoder defaults =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();
~~~

According to Spring Security 6.5 documentation, the factory includes mappings for multiple formats such as bcrypt, pbkdf2, scrypt, argon2, and versioned preset variants. However, `idForEncode` **defaults to bcrypt** in this release; it does not automatically switch to Argon2id just because an Argon2 decoder is in the map.

Common factory IDs (in the 6.5 line) include `bcrypt`, `pbkdf2@SpringSecurity_v5_8`, `scrypt@SpringSecurity_v5_8`, `argon2@SpringSecurity_v5_8`, along with several legacy mappings. Having mappings to read legacy data **does not mean the old algorithms are still suitable for new hashes**.

Choose a custom map when you want exact control over accepted IDs and the new algorithm. **Do not create a map that omits `idForEncode`**, because the constructor requires the ID to be present with a corresponding encoder.

## 6. Migration Cycle at Successful Login Time

A typical processing flow:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant F as Authentication filter
    participant P as DaoAuthenticationProvider
    participant S as UserDetailsService
    participant E as DelegatingPasswordEncoder
    participant U as UserDetailsPasswordService
    participant D as Database
    C->>F: Username + raw password over HTTPS
    F->>P: Authentication request (via manager)
    P->>S: loadUserByUsername
    S->>D: Read hash + account status
    D-->>S: {bcrypt-v1}oldHash
    S-->>P: UserDetails
    P->>E: matches(raw, {bcrypt-v1}oldHash)
    E-->>P: true via BCrypt
    P->>P: Check account status and related requirements
    P->>E: upgradeEncoding(oldHash)
    E-->>P: true (ID differs from idForEncode)
    P->>E: encode(raw)
    E-->>P: {argon2-v58}newHash
    P->>U: updatePassword(user, newHash)
    U->>D: Safely update hash
    D-->>U: Confirm update
    U-->>P: Updated UserDetails
    P-->>F: Authenticated Authentication
~~~

The diagram focuses on the upgrade step inside the provider and condenses the filter/manager steps. In a real Servlet application, the filter calls `AuthenticationManager`, typically `ProviderManager`, which delegates to `DaoAuthenticationProvider`.

### 6.1. Correct Order: Verify First, Rehash After

1. The client submits credentials through a protected login mechanism (HTTPS).
2. `UserDetailsService` loads the correct hash and account status.
3. `PasswordEncoder.matches(raw, oldHash)` verifies using the **encoder matching the legacy ID**.
4. Account status checks and additional policies must be satisfied to allow authentication success.
5. `upgradeEncoding(oldHash)` indicates whether the current hash should be upgraded.
6. If needed, `encode(raw)` creates the current hash and persists it via `UserDetailsPasswordService`/repository.
7. The successful authentication is returned; filter components manage `SecurityContext` according to the configured mechanism.

**Never rehash and store the raw password when `matches` has not succeeded.** Doing so could replace the account's hash with a value supplied by an attacker, amounting to account takeover.

### 6.2. `upgradeEncoding` Does Not Automatically Update the Database

With `DelegatingPasswordEncoder`, when a hash has an ID different from `idForEncode`, `upgradeEncoding` usually returns `true`. When the ID matches the current encoder, it delegates the decision to that encoder to check work factor/parameters.

This is only a **signal**, not a write operation. Without an appropriate `UserDetailsPasswordService` or safe update logic, the account may keep the legacy hash after login even though `upgradeEncoding` returns true.

### 6.3. `UserDetailsPasswordService` Receives the **New Hash**, Not the Raw Password

Interface:

~~~java
public interface UserDetailsPasswordService {
    UserDetails updatePassword(UserDetails user, String newPassword);
}
~~~

The parameter name `newPassword` in the API easily misleads newcomers: in `DaoAuthenticationProvider`'s hash upgrade path, it is the **newly encoded string** produced by `PasswordEncoder.encode(raw)`. The repository implementation **must store that encoded string as-is**, without encoding it again.

Wrong:

~~~java
// WRONG: newPassword is already encoded; this will double-hash.
repository.savePassword(
        user.getUsername(),
        encoder.encode(newPassword));
~~~

Right in the API context:

~~~java
// Illustrative integration snippet; newPassword is the encoded hash.
repository.savePassword(user.getUsername(), newPassword);
~~~

The right snippet still needs transactions, synchronization, and handling of concurrent changes in a real repository.

## 7. Standalone Java 17 Example: Legacy bcrypt, New Argon2id, Automatic Hash Upgrade

We build a console Gradle project using **real encoders and provider**. The account store uses `ConcurrentHashMap` to simulate a database; `UserDetailsPasswordService` writes hashes into the map and counts upgrades.

Guarantees built into the demo design:

- Account `lan` stores legacy bcrypt with ID `{bcrypt-v1}`.
- Account `minh` already stores Argon2id with ID `{argon2-v58}`.
- The same demo raw password is used **solely for easy comparison**, not as a recommendation to share passwords in production.
- `DaoAuthenticationProvider` verifies the real password, then upgrades the legacy hash when needed.
- The wrong-password case does **not** upgrade the hash.
- Unprefixed hashes are not accepted automatically; the example only accepts them when tagged with **the right ID after provenance verification**.
- The code does not print raw passwords, salts, or hashes to stdout.

### 7.1. Project Structure

~~~text
password-migration-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/passwordmigration/
    └── PasswordMigrationDemo.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'password-migration-demo'
~~~

`build.gradle`:

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
    implementation 'org.bouncycastle:bcprov-jdk18on:1.86'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.passwordmigration.PasswordMigrationDemo'
}
~~~

`Argon2PasswordEncoder` uses Bouncy Castle in Spring Security; declaring this dependency is mandatory to avoid runtime errors when running Argon2. The versions here are used **to reproduce the demo**, not as a recommendation to freeze production on these versions; production systems must apply supported patches and verify BOM/dependency compatibility.

### 7.2. Complete Java File

Save at `src/main/java/example/passwordmigration/PasswordMigrationDemo.java`:

~~~java
package example.passwordmigration;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.InternalAuthenticationServiceException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsPasswordService;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.argon2.Argon2PasswordEncoder;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.DelegatingPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public class PasswordMigrationDemo {

    // In-memory store simulating a database, keeping encoded hashes intact.
    static final class Accounts
            implements UserDetailsService, UserDetailsPasswordService {

        private final Map<String, String> stored =
                new ConcurrentHashMap<>();
        private final AtomicInteger writes = new AtomicInteger();

        void seed(String username, String encodedHash) {
            stored.put(username, encodedHash);
        }

        String encodedOf(String username) {
            return stored.get(username);
        }

        int updateCount() {
            return writes.get();
        }

        @Override
        public UserDetails loadUserByUsername(String username)
                throws UsernameNotFoundException {

            String encoded = stored.get(username);
            if (encoded == null) {
                throw new UsernameNotFoundException("Account not found");
            }

            // Return a fresh UserDetails; prevent ProviderManager
            // eraseCredentials from mutating the stored record directly.
            return User.withUsername(username)
                    .password(encoded)
                    .authorities("profile.read")
                    .build();
        }

        @Override
        public UserDetails updatePassword(
                UserDetails user, String newPassword) {

            // newPassword IS ALREADY the encoded hash produced by the encoder.
            // Do not call encode(newPassword) again.
            String username = user.getUsername();

            stored.compute(username, (key, currentHash) -> {
                if (currentHash == null) {
                    throw new InternalAuthenticationServiceException(
                            "Account disappeared during upgrade");
                }

                // Prevent overwriting the hash if the password was already
                // changed by a concurrent request.
                if (!currentHash.equals(user.getPassword())) {
                    throw new InternalAuthenticationServiceException(
                            "Concurrent password change; retry login");
                }

                writes.incrementAndGet();
                return newPassword;
            });

            return loadUserByUsername(username);
        }
    }

    static boolean authenticates(
            AuthenticationManager manager,
            String username,
            String rawPassword) {

        try {
            Authentication request =
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            username, rawPassword);
            Authentication result = manager.authenticate(request);
            return result.isAuthenticated();
        }
        catch (AuthenticationException failure) {
            // Do not print raw credentials or user details.
            return false;
        }
    }

    public static void main(String[] args) {
        String demoRaw = "demo-pass-for-local-lab";

        PasswordEncoder legacy =
                new BCryptPasswordEncoder(10);
        PasswordEncoder current =
                Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8();

        DelegatingPasswordEncoder encoder =
                new DelegatingPasswordEncoder(
                        "argon2-v58",
                        Map.of(
                                "bcrypt-v1", legacy,
                                "argon2-v58", current));

        Accounts accounts = new Accounts();
        accounts.seed("lan", "{bcrypt-v1}" + legacy.encode(demoRaw));
        accounts.seed("minh",
                "{argon2-v58}" + current.encode(demoRaw));

        System.out.println("old-prefix-before="
                + accounts.encodedOf("lan").startsWith("{bcrypt-v1}"));
        System.out.println("old-match-before="
                + encoder.matches(demoRaw, accounts.encodedOf("lan")));
        System.out.println("old-upgrade-before="
                + encoder.upgradeEncoding(accounts.encodedOf("lan")));

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(accounts);
        provider.setPasswordEncoder(encoder);
        provider.setUserDetailsPasswordService(accounts);

        AuthenticationManager manager =
                new ProviderManager(List.of(provider));

        System.out.println("old-user-login="
                + authenticates(manager, "lan", demoRaw));
        System.out.println("new-prefix-after="
                + accounts.encodedOf("lan").startsWith("{argon2-v58}"));
        System.out.println("new-hash-matches="
                + encoder.matches(demoRaw, accounts.encodedOf("lan")));
        System.out.println("upgrade-after="
                + encoder.upgradeEncoding(accounts.encodedOf("lan")));
        System.out.println("writes-after-first="
                + accounts.updateCount());

        System.out.println("old-user-relogin="
                + authenticates(manager, "lan", demoRaw));
        System.out.println("writes-after-relogin="
                + accounts.updateCount());

        System.out.println("already-new-login="
                + authenticates(manager, "minh", demoRaw));
        System.out.println("writes-after-new-user="
                + accounts.updateCount());

        System.out.println("wrong-password="
                + authenticates(manager, "lan", "incorrect"));
        System.out.println("writes-after-wrong="
                + accounts.updateCount());

        // Default: missing ID => fail-safe, no auto-guess.
        String untaggedBcrypt = legacy.encode(demoRaw);
        try {
            encoder.matches(demoRaw, untaggedBcrypt);
            System.out.println("untagged=UNEXPECTED_ACCEPT");
        }
        catch (IllegalArgumentException rejected) {
            System.out.println("untagged=REJECTED");
        }

        // Only illustrates a record with verified provenance.
        // With a real DB, adding prefixes requires a separate data process.
        System.out.println("audited-legacy-match="
                + encoder.matches(
                        demoRaw, "{bcrypt-v1}" + untaggedBcrypt));

        System.out.println("new-registration-prefix="
                + encoder.encode("another-local-demo-password")
                        .startsWith("{argon2-v58}"));
    }
}
~~~

### 7.3. Running the Program

Inside the `password-migration-demo` directory, using JDK 17+ and a compatible Gradle version:

~~~bash
gradle run --quiet
~~~

If Gradle Wrapper is present, use `./gradlew run --quiet` (on Windows PowerShell: `.\gradlew.bat run --quiet`).

Lines produced by `System.out.println` (excluding Gradle/framework logs):

~~~text
old-prefix-before=true
old-match-before=true
old-upgrade-before=true
old-user-login=true
new-prefix-after=true
new-hash-matches=true
upgrade-after=false
writes-after-first=1
old-user-relogin=true
writes-after-relogin=1
already-new-login=true
writes-after-new-user=1
wrong-password=false
writes-after-wrong=1
untagged=REJECTED
audited-legacy-match=true
new-registration-prefix=true
~~~

**Why are these lines predictable?**

1. `lan` initially has ID `bcrypt-v1`; the mapping lets `matches` verify properly. Because `idForEncode` is `argon2-v58`, `upgradeEncoding` returns `true` for the legacy hash.
2. `DaoAuthenticationProvider` verifies the password and calls `UserDetailsPasswordService.updatePassword` when needed, so `lan`'s hash switches to the current ID and `updateCount=1`.
3. Re-logging in with the current hash no longer needs rehashing, because `Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8()` reports the hash already has sufficient memory/iterations per the preset.
4. `minh` already uses the current ID so login still succeeds without incrementing the update count.
5. Wrong password is rejected and is not allowed to rewrite the hash.
6. A bcrypt hash missing `{id}` is rejected by default; only after **verifying the exact algorithm provenance** and adding the ID in the example can `matches` use the legacy encoder.
7. A new hash from `encoder.encode` has the current ID. Random salt makes the **specific hash value** change between runs without changing these boolean results.

**Note on the in-memory record:** the demo uses `Map.compute` and hash comparison before writing to illustrate conditional updates. With a real database, you need **transactions/compare-and-swap with WHERE version/hash**, handling version conflicts and ensuring the update result reflects committed state. Console code does not replace a production repository.

### 7.4. Why Does the Update in the Demo Only Happen After Authentication?

`DaoAuthenticationProvider` is configured with:

~~~java
DaoAuthenticationProvider provider =
        new DaoAuthenticationProvider(accounts);
provider.setPasswordEncoder(encoder);
provider.setUserDetailsPasswordService(accounts);
~~~

This is the junction of three contracts:

- `UserDetailsService` loads the user and legacy hash.
- `PasswordEncoder` checks the legacy hash / encodes the new one.
- `UserDetailsPasswordService` **writes the new hash** and returns the updated `UserDetails` to the provider.

If you omit `setUserDetailsPasswordService(accounts)`, `DaoAuthenticationProvider` can still verify legacy hashes through the delegating encoder, but **has no path to write the new hash into this store**. Simply calling `upgradeEncoding` from controller code is not enough either; there must be a safe write operation and account policy checks.

## 8. Updating a Real Database: Avoiding Races When Users Reset Passwords Concurrently

### 8.1. Why Not Use an Unconditional UPDATE?

A dangerous scenario:

~~~text
T1: User logs in with old password; verified successfully against hash A.
T2: User changes password via recovery; DB stores hash B.
T1: Slow login rehash flow completes and writes hash C of the old password.
Result: new password is overwritten; old password becomes valid again.
~~~

If `UserDetailsPasswordService` only executes:

~~~java
// WRONG if there is no synchronization/race policy.
repository.updatePasswordByUsername(username, newEncodedHash);
~~~

then a rehash from an older login can **overwrite a newer credential change**. In practice, this also depends on isolation and update policy, but you should not rely on luck with request ordering.

### 8.2. Use Conditional Updates

An illustrative SQL approach:

~~~sql
UPDATE accounts
SET password_hash = :new_encoded_hash,
    credential_version = credential_version + 1
WHERE user_id = :user_id
  AND credential_version = :expected_version
  AND password_hash = :old_encoded_hash;
~~~

After the statement, you must check the updated row count:

- **1 row:** the update matched the verified snapshot (assuming transactions/conditions are implemented properly).
- **0 rows:** the credential/version changed or the row was deleted; **do not automatically allow login success using the stale snapshot if policy requires the current state**. You can require the user to log in again with the new password.
- **Database error:** preserve the infrastructure error; do not disguise it as a bad password or silently ignore it.

This is **illustrative SQL**; schema and bind parameter syntax depend on the database framework. `UserDetailsPasswordService.updatePassword(user, newPassword)` only receives `UserDetails` and the encoded hash; if you need CAS versioning, obtain the version from the principal/domain model or appropriate repository context. Do not expect the API to provide a built-in `credential_version` column.

### 8.3. Avoiding Duplicate Updates Across Multiple Requests

When multiple login requests for the same user run concurrently:

- Both requests read hash A, both verify, and both compute different new hashes due to salt.
- Both may attempt to change A → B1/B2.
- With CAS, only one request transitions A; the other detects that the version/hash no longer matches.
- Design safe retries (typically requiring re-authentication against the current state), rather than blind overwrites.

For already logged-in sessions or still-valid tokens, separate policies may apply. Rehashing a password hash in the database does not automatically refresh every `Authentication` in sessions, nor does it automatically revoke JWTs or guarantee user logout.

## 9. Legacy Hashes Without {id}: Handling Based on Provenance

A classic error when enabling `DelegatingPasswordEncoder`:

~~~text
java.lang.IllegalArgumentException:
There is no PasswordEncoder mapped for the id "null"
~~~

This happens when data lacks the `{id}` prefix and the encoder has no separate default matcher. **It is not proof that the user entered the wrong password**; it is a mapping/format error that must be handled systematically.

### 9.1. When All Records Are Verified to Be bcrypt

If the legacy system has **a column containing only bcrypt hashes** created by a verified application, you can run a **prefix-only** data migration:

~~~text
Before: $2a$10$... (valid, intact bcrypt hash)
After:  {bcrypt-v1}$2a$10$... (hash portion kept unchanged)
~~~

No raw password is needed for this **metadata-tagging operation**. Because the hash content does not change, verification with `BCryptPasswordEncoder` still works. However, **adding a prefix** does not mean upgrading the algorithm or increasing the work factor; the account still uses the old bcrypt cost until a future rehash.

Before running a batch, you must survey the **actual format distribution** and origin: are there LDAP user hashes, historical plaintext, SHA-1, NULL values, corrupted records, or columns with mixed formats? Do not apply one prefix to the entire database just because the first few samples look like bcrypt.

### 9.2. When Multiple Algorithms Are Mixed Without IDs

You need metadata external to the hash, such as the application version that created the record, source system, tenant, or a trusted algorithm column. If it cannot be determined accurately or no safe corresponding encoder remains, choose a **verified password reset flow** rather than trying every algorithm and accepting whichever matches.

Do not use:

~~~java
// DO NOT APPLY: guessing encoders sequentially on unknown-format input.
if (argon2.matches(raw, value)
        || bcrypt.matches(raw, value)
        || legacyNoOp.matches(raw, value)) {
    // ...
}
~~~

A guessing matcher cannot reliably distinguish ambiguous formats, increases fallback risks, drags in unsafe encoders, and widens the attack surface.

### 9.3. Why Not Set Up a NoOp Fallback?

`DelegatingPasswordEncoder.setDefaultPasswordEncoderForMatches(...)` allows changing the matcher when an ID is unmapped. Some tightly controlled legacy migration paths use that mechanism, but **you should not enable `NoOpPasswordEncoder` for all hashes missing an ID**.

Doing so could cause a malformed data string to be compared as plaintext, or be exploited by an attacker if there is any uncontrolled write path to `password_hash`. Prefer attaching the right ID to **verified data**, keeping legacy decoders for a governed window, and resetting unclassifiable records.

### 9.4. Rules for Unmapped IDs

| DB Format | Handling |
| --- | --- |
| `{argon2-v58}...` | Verify with the current encoder |
| `{bcrypt-v1}...` | Verify with legacy BCrypt if policy allows, then rehash |
| `{unknown}...` | Do not accept automatically; report format/triage error and route to recovery |
| No `{id}`, provenance verified as bcrypt | Attach matching ID via controlled data migration |
| No `{id}`, unknown algorithm | Do not guess arbitrarily; require verified reset |
| Malformed, truncated, or empty hash | Fail closed; remediate data and route to recovery |
| Passkey/OIDC-only account with no local password | Do not invent a password or fake hash; use the actual identity mechanism |

**Never store an ID chosen by client input.** Algorithm metadata must be generated/stored by a trusted system. If an attacker can alter `password_hash` or the ID in the DB, that is an account-store integrity/authorization issue and must be addressed separately.

## 10. Multi-Node Rollout Process Without Breaking Login

In systems running multiple pods/instances, unsynchronized deployments can produce **hashes that some nodes do not yet know how to verify**.

### 10.1. Three-Phase Plan: Expand → Switch Writers → Contract

~~~text
PHASE 1 — EXPAND READERS
  - Every node supports verifying both legacy and new hashes.
  - Encoding new hashes STILL uses the legacy ID or write flow is unchanged.
  - Run login tests against existing formats.
  - Ensure DB column length, constraints, and schema are compatible.

PHASE 2 — SWITCH WRITERS
  - Once all readers support the new format:
      + switch idForEncode to the current algorithm;
      + enable UserDetailsPasswordService / rehash-on-login;
      + start writing new hashes on registration, reset, and successful login.
  - Monitor migration rate, login errors, DB updates, and resources.

PHASE 3 — CONTRACT
  - Only when no legacy hashes remain to support (or a reset policy is in place):
      + consider removing legacy mappings via change management;
      + retain a recovery plan and audit rarely-logging-in accounts;
      + do not remove old decoders while valid legacy data remains.
~~~

**Rollback note:** After PHASE 2 has written Argon2 hashes, rolling back to an application version that **only understands BCrypt** can prevent new/migrated users from logging in. At a minimum, a safe rollback version must **still support reading/verifying both hash types**, even if writing new Argon2 hashes is temporarily turned off.

### 10.2. The Database Must Hold the New Hash

Verify:
- Maximum length of the `password_hash` column, avoiding truncation of encoded hashes.
- Encoding/collation; hashes include special characters such as `{ } $ / + =` and must not be "normalized" when stored.
- Indexes: you normally do not need an index on hash values, so avoid creating indexes that increase exposure and write cost.
- Backup/replica/CDC/logging topology; hashes must not be shipped to analytics systems that do not need access.
- Password update, user import, admin reset, and IdP sync flows share the same format rules.

You need a **real database round-trip** integration test: encode → persist → retrieve → matches. An in-memory unit test can pass green while a `VARCHAR(60)` DB column silently truncates longer Argon2 hashes.

### 10.3. Canary with Legacy Data

Test/canary accounts should represent:
- low- and high-cost bcrypt;
- legacy scrypt/PBKDF2/Argon2 presets if present;
- hashes with/without ID within verified scope;
- locked/disabled/expired users;
- users with active sessions;
- users performing concurrent login/password changes.

Testing only newly registered accounts (which always use the new hash) will **not verify backward compatibility**.

## 11. All Password Write Flows Must Enforce a Unified Policy

A system typically has multiple password creation/change points:

| Flow | Hash to use | Notes |
| --- | --- | --- |
| New user registration | Current encoder (`encode`) | Do not send raw password to logs/events |
| User password change | Current encoder | Verify appropriate proof, handle sessions/tokens, rate limit |
| Forgot password and reset | Current encoder | Single-use reset token, TTL, invalidation, audit |
| Admin temporary password issuance | Current encoder or invitation flow without exposing raw | Protect channel, force change when required |
| Successful login with legacy hash | Rehash only after successful `matches` and valid account policy | `UserDetailsPasswordService`/CAS |
| Import/migration from legacy system | Read exact provenance, may retain legacy hash with ID | Never treat a hashed password as raw input |
| OIDC/passkey account without local password | Do not generate fake hashes | Preserve the account's actual authentication mechanism |

**Common mistake:** registration switched to Argon2 while the reset-password service still encodes bcrypt or accidentally stores plaintext. An algorithm choice is only effective if **every password write path** complies together.

## 12. When Should You Force a Reset Instead of Continuing Legacy Verification?

Not all legacy data should remain accepted indefinitely.

**May keep legacy verifier during a governed window:** bcrypt/PBKDF2/scrypt hashes with older parameters whose contract is clear, with no compromise incident, and permitted by login policy, followed by immediate rehashing.

**Should consider mandatory reset:** plaintext hashes, MD5/SHA-1 without a password KDF, formats with unverifiable origin, compromised credentials, corrupted hashes, or mechanisms disallowed by risk/compliance. The reset workflow must verify the account via a trusted channel, rate-limit attempts, and avoid user enumeration.

A system with millions of accounts where only a few percent log in each month may take very long to finish migrating via login-only. You should **define a legacy support lifetime**, set a reasonable cut-off, and proactively send notifications/safe recovery flows to accounts that no longer log in frequently.

Do not schedule a cron job that reads old hashes and creates new hashes from those hashes. If you do not have raw passwords and do not want to accept legacy verifiers, **resetting is the right choice**.

## 13. Caches, Sessions, JWTs, and Permission Changes

Upgrading a hash updates **credential data in the account store**, not all existing authentication state.

### 13.1. UserDetails Cache

If a provider or `CachingUserDetailsService` caches `UserDetails`, after `updatePassword` writes the new hash you must ensure the cache does not return a snapshot containing the old hash. Evict the right key after commit and handle multi-node invalidation. Do not expect `DaoAuthenticationProvider` to automatically evict custom caches outside its configuration.

A cached `UserDetails` can also be affected by `ProviderManager.eraseCredentials()` if the same principal object is shared. Design copying/erasure and cache policy appropriately; do not disable credential erasure just because the cache breaks without evaluating security impact.

### 13.2. Sessions

A successful login with a legacy hash can simultaneously rehash the DB and create an `Authentication` in the session. There is no mandatory requirement to log out immediately just because the **hash format** changed, if it is merely a transparent upgrade and policy allows it. Conversely, resetting a password due to suspected compromise may require invalidating prior sessions.

Do not conflate "algorithm upgrade" with "password reset" or "permission change". They serve different business purposes.

### 13.3. JWTs and Refresh Tokens

Signed JWTs carry their own claims and expiration; changing the hash in the database does not automatically alter existing JWTs. If the hash upgrade is only to increase offline cost, token revocation may not be needed. If the password change involves an incident/credential compromise, consider token revocation, refresh-token rotation, and requiring re-login.

## 14. CPU/RAM Budgeting and Protecting the Login Endpoint

When migrating from bcrypt to Argon2id or increasing work factors, the cost of both successful and failed authentications can change significantly.

A few notes:

- `Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8()` uses `1 << 14` KiB memory (**16 MiB**), `2` iterations, `1` parallelism, `16`-byte salt, and `32`-byte hash.
- This is the **algorithm's configured memory per hash operation**, not actual measured RSS/heap.
- Eight concurrent verify/rehash operations with roughly 16 MiB working memory per operation can require around **128 MiB for memory-hard work**, before other overhead.
- Rehash-on-login can incur **two expensive operations** in the same request: verifying the legacy hash and then encoding the new hash. Without limits, an initial rollout wave with many legacy accounts can spike latency/CPU/RAM.
- Legacy BCrypt has CPU cost while Argon2 adds memory cost; do not compare security directly just by milliseconds or MiB across presets.

Operational measures: benchmark p50/p95/p99 and peak heap/RSS/GC, bound concurrent KDF operations, rate-limit login and reset, use bounded queues, alert on OOM/timeouts, and test under production-like load. Do not ignore the encode cost during the upgrade step.

### 14.1. Measuring Upgrade Impact with Large Legacy Volume

Suppose 200 valid legacy-user logins occur in one minute:
- Each login must verify the legacy hash.
- If most accounts have not migrated yet, most requests also need to encode a new hash and update the DB.
- These requests can generate **higher-than-normal load**, especially during the initial rollout.

A practical technique is rolling out by tenant/cohort, canarying, and enforcing rate/concurrency budgets. **Never push raw passwords into a queue to hash in the background**. If resources are insufficient to upgrade hashes, design fail-safe/load-shedding behavior according to policy rather than returning success and pretending the new hash was committed when it was not.

### 14.2. Password Length Controls and DoS

KDFs run on client-supplied input; the system should enforce reasonable request/credential size limits, apply normalization if policy specifies it, and use rate limiting. Do not silently trim or case-fold passwords during migration if legacy data did not do so: the exact same raw string must be processed consistently in `matches` and `encode`.

Do not accept cost/hash algorithm parameters from the client that allow them to force arbitrarily expensive verification. Read algorithm metadata from stored hashes **after ensuring data-store integrity**, while enforcing bounds and standardized accepted configurations.

## 15. Mandatory Testing: Old Still Logs In, New Uses the Right Algorithm

A migration test suite should cover **both read and write directions**:

| Test | Fixture | Expected |
| --- | --- | --- |
| Login with legacy bcrypt | `{bcrypt-v1}...` correct password | Succeeds; may upgrade hash |
| Login legacy bcrypt wrong password | Old hash, wrong password | Fails; **does not write new hash** |
| Login current Argon2 | `{argon2-v58}...` | Succeeds; does not increment rehash count |
| New registration | `encode(raw)` | New ID and parameters, `matches` succeeds |
| Missing ID | Unprefixed bcrypt hash | Fail-safe before metadata migration |
| Audited prefix | Hash known to be bcrypt and tagged with ID | `matches` succeeds |
| Unknown ID | `{unrecognized}...` | No auto-guess/noop; config/data error detected |
| Truncated hash | DB record with bad column limit | Does not succeed; telemetry reports error |
| Mixed algorithms | Bcrypt/scrypt/PBKDF2/Argon2 with valid IDs | Only policy-allowed formats verify |
| Param upgrade | Same ID, old work factor | `upgradeEncoding` reflects encoder policy if supported |
| Rehash-on-login | `UserDetailsPasswordService` invoked | New hash persisted, updated UserDetails returned |
| No updater | Password service not configured | Legacy verify works, DB does not auto-upgrade |
| Concurrent reset | Login upgrading hash while recovery changed password | Does not overwrite recovery; fail closed/CAS |
| Two app versions | New reader + old writer, then new writer | No node encounters unsupported hash |
| Rollback | Part of data already migrated to Argon2 | Rollback still **reads Argon2** |
| User rarely logs in | Legacy hash still present after cut-off | Safe recovery/reset |
| Account disabled/locked | Correct password, invalid account status | Does not succeed merely because hash matched |
| Session/JWT | Login before/after upgrade | Verify separate session/token policies |
| Concurrency load | Many simultaneous logins/rewrites | p95, memory, DB writes stay within budget |
| Privacy | Logger/audit | No raw/hash leakage, no account enumeration via errors |

### 15.1. Real Tests Through DaoAuthenticationProvider

Unit tests calling only `encoder.matches` prove hash/ID logic, but do not prove the rehash flow is wired into the provider properly. The demo in section 7 uses a real `DaoAuthenticationProvider` and `UserDetailsPasswordService` to verify **one login → verify → upgrade → persist**.

In Spring Boot Servlet apps, add integration tests traversing `SecurityFilterChain` and authentication filters to catch cases where the app accidentally uses a different `AuthenticationManager` than configured in unit tests. With `@WithMockUser`, the framework injects a mock user into the context and skips password hashing and rehash-on-login; do not rely on it alone to conclude migration works.

### 15.2. Verifying Data Against a Real Database

At minimum:
- Every hash format in use has an intact fixture verified by the right encoder.
- Schema does not truncate Argon2 prefixes/salts/hashes.
- Transaction/CAS updates return the expected row count and do not alter unrelated username/authorities/status columns.
- Password changes concurrent with rehashing are not overwritten.
- Replication/caches do not read/write stale hashes after commit.
- Monitoring counts hashes by **valid ID** and tracks failed rehash rates without logging intact hashes.

### 15.3. Comparing Public Error Messages

A user entering a wrong password against a legacy hash or a new hash should receive consistent public error messages per policy. If missing ID/unknown ID is an operational error, do not expose the raw `IllegalArgumentException` message to the client. Log only safe internal codes, without leaking raw hashes, usernames, or specific algorithms if doing so aids account attacks.

## 16. Observability: Tracking Migration Progress Without Collecting Secrets

Measure aggregate metrics:

- Record counts by `password_algorithm_id` (allowlisted IDs only).
- Login verification success/failure rates by **legacy/current hash group**.
- `password_rehash_attempted`, `password_rehash_succeeded`, `password_rehash_conflict`, `password_rehash_failed`.
- Latency of `matches` and `encode` by algorithm group, plus end-to-end auth p95/p99.
- Hashing concurrency, heap/RSS, GC pauses, and OOM/restarts.
- Count of accounts with unverifiable format (without logging hashes) and users needing recovery.
- Rollout progress: percentage of readers understanding the new ID, percentage of writers emitting the new ID, legacy hash burn-down rate.
- Reset-password event counts, distinguishing transparent rehashes from explicit user password changes.

Avoid putting usernames, emails, or password hashes into metric labels: this causes high cardinality and increases data exposure risk. If per-account auditing is needed, use internal IDs with strict access/retention policies; never push secrets into observability systems.

**The number of migrated accounts cannot be inferred solely from login counts**: one account may log in many times, or hashes may be upgraded during password change/reset. Querying a restricted-access DB by trusted prefix/metadata is far more accurate.

## 17. Common Mistakes in Real Projects

1. **Switching `PasswordEncoder` directly to Argon2 without keeping the bcrypt verifier.** Legacy users cannot log in.
2. **Assuming BCrypt hashes can be "decrypted" and batch-rehashed.** Hashes are one-way; use verified login or recovery.
3. **Calling `encoder.encode(raw)` and comparing to the stored hash.** Random salt breaks string equality; use `matches`.
4. **Forgetting the `{id}` prefix in the DB.** Delegating encoder cannot auto-select the right format.
5. **Tagging all legacy hashes with the same ID without surveying.** Can map the wrong algorithm or break accounts.
6. **Enabling `NoOpPasswordEncoder` as the default matcher for all unprefixed records.** Creates a dangerous weak compatibility path.
7. **Keeping legacy mappings while still encoding new passwords with the legacy ID.** Fails the upgrade goal.
8. **Calling `upgradeEncoding` and assuming the DB updates itself.** Requires `UserDetailsPasswordService` or an equivalent save flow.
9. **Double-hashing the `newPassword` parameter in `updatePassword`.** The API already passes the new hash, not raw password.
10. **Rehashing before the old password is verified.** Can overwrite the hash with attacker-supplied input.
11. **Updating the new hash without CAS/versioning.** A rehash can overwrite a concurrent password reset.
12. **Rolling out new writers before all readers support the new ID.** Logins fail randomly depending on which node handles them.
13. **Rolling back to an app version that only knows old hashes.** Migrated accounts cannot log in.
14. **DB hash column too short.** Truncates Argon2 strings, breaking verification only for new accounts.
15. **Forgetting admin/batch/import password-change paths.** Data ends up with unpredictable formats.
16. **Assuming changing hash format automatically revokes JWTs/sessions.** Those are two separate state layers.
17. **Increasing memory cost without bounding concurrency.** Can trigger OOM and login endpoint DoS.
18. **Logging encoded hashes to debug ID mappings.** Hashes are sensitive data that become valuable if the database leaks.
19. **Trying every encoder sequentially on hashes of unknown origin.** Increases ambiguity and risk of falling back to weak schemes.
20. **Ignoring users who rarely log in.** Login-only migration can leave weak hashes around for years.
21. **Not checking `UserDetailsService` caching and erasure behavior.** Stale snapshots can prevent clean refreshes.
22. **Treating `upgradeEncoding=false` as absolute security.** It only reflects a specific policy and implementation.
23. **Forcing a new algorithm from a blog post without benchmarking.** Can slow logins, cause bottlenecks, or exhaust memory.
24. **Changing password normalization during migration.** Existing passwords may stop matching even when users type them correctly.
25. **Conflating hash upgrade with password change:** upgrading a hash keeps the current raw password and does not fix compromised or weak passwords.

## 18. Self-Check Questions

**Question 1.** A system switches to Argon2, while `{bcrypt}...` remains in the DB. Can a standalone `Argon2PasswordEncoder` verify bcrypt hashes directly?  
**Answer:** No. You need `DelegatingPasswordEncoder`/a provider with the legacy ID mapping for bcrypt.

**Question 2.** `idForEncode="argon2-v58"` while the map also includes bcrypt. Which algorithm creates new hashes?  
**Answer:** Argon2id via the encoder bound to the current ID; bcrypt is only in the map to read/verify legacy hashes.

**Question 3.** A legacy hash lacks an ID, but provenance proves it is definitely bcrypt. Can you prepend `{bcrypt-v1}` without knowing the raw password?  
**Answer:** Yes, because that is **adding metadata**, not rehashing. The bcrypt hash body must stay intact and properly formatted.

**Question 4.** If the legacy algorithm cannot be determined, should you try BCrypt, SHA-1, and NoOp until one matches?  
**Answer:** No. You need trusted provenance or a verified password reset.

**Question 5.** `matches` succeeds on a legacy hash and `upgradeEncoding` returns true. Has the hash changed in the DB automatically?  
**Answer:** No. A write path is required, such as `DaoAuthenticationProvider` configured with `UserDetailsPasswordService`.

**Question 6.** In `UserDetailsPasswordService.updatePassword(user, newPassword)`, should you call `encoder.encode(newPassword)` again?  
**Answer:** No in the standard hash upgrade path; `newPassword` is already the newly encoded hash.

**Question 7.** Why not rehash every account from its existing bcrypt hash using Argon2(bcryptHash)?  
**Answer:** The output is not Argon2 of the original password, and raw passwords cannot be verified under the standard contract afterward.

**Question 8.** Why are conditional DB updates needed?  
**Answer:** To prevent a slow login rehash from overwriting a new password just reset/changed by another request.

**Question 9.** What condition is required to roll back an application after some accounts have been upgraded to Argon2?  
**Answer:** The rollback version must still know how to verify existing Argon2 hashes; you can turn off the new writer, but never remove the new reader.

**Question 10.** Why can legacy ID mappings be retained temporarily even when creating new hashes with that algorithm is discouraged?  
**Answer:** So users with legacy hashes can still log in per policy and then migrate; legacy reads and new writes are two distinct policies.

**Question 11.** Must every login after migration rehash the password again?  
**Answer:** Not necessarily. Once a hash uses the current ID and parameters, `upgradeEncoding` usually returns false; do not rewrite needlessly.

**Question 12.** Why can login-based hash upgrades cause a resource spike at the start of a rollout?  
**Answer:** One login with a legacy hash requires verifying the old hash and encoding the new one, adding CPU/RAM work and a DB write; benchmark and set a concurrency budget.

**Question 13.** Does `PasswordEncoderFactories.createDelegatingPasswordEncoder()` pick Argon2 for encoding by default in Spring Security 6.5?  
**Answer:** No; the default factory uses bcrypt as the write encoder in this line even though it includes an Argon2 mapping for reading.

**Question 14.** Does switching hashes from bcrypt → Argon2 automatically revoke already-issued access tokens?  
**Answer:** No. Sessions, JWTs, and refresh tokens have their own lifecycles and policies.

**Question 15.** How should an account that only logs in via OIDC/passkey with no local password be handled?  
**Answer:** Do not generate fake passwords or hashes; keep the user's actual login mechanism and metadata. If local passwords are enabled later, require verified enrollment.

**Question 16.** What could cause a new Argon2 hash to verify on node A but fail on node B?  
**Answer:** Node B has not deployed the new reader/ID mapping, is missing Bouncy Castle, has mismatched versions, truncated the hash, or has different configuration. Check rollout and dependencies.

## 19. Migration Handoff Checklist

- [ ] Survey formats and provenance of **each account cohort** (not just a few sample records).
- [ ] Select new algorithm/parameters based on security policy, compliance, and real benchmarks.
- [ ] Define the current `idForEncode` and all reader IDs to support; avoid default plaintext fallbacks.
- [ ] Test prefixed and unprefixed hashes, unknown-ID errors, and corrupted hashes.
- [ ] Verify DB columns, charsets, replication, and backups preserve the entire encoded string.
- [ ] Ensure every reader instance recognizes the new algorithm **before** writers start emitting the new format.
- [ ] Ensure registration, reset, password change, admin, and import flows follow the same new encoding rules.
- [ ] Configure `DaoAuthenticationProvider` with the right `UserDetailsService`, `PasswordEncoder`, and `UserDetailsPasswordService`.
- [ ] Ensure `UserDetailsPasswordService` stores the received encoded hash as-is without double-hashing.
- [ ] Perform DB updates with transactions/versioning/CAS so concurrent password resets are not overwritten.
- [ ] Rehash only after credentials and account status satisfy authentication requirements.
- [ ] Keep raw passwords, tokens, hashes, and salts out of logs and queues.
- [ ] Evict the `UserDetails` cache properly after commit and handle multi-node invalidation if applicable.
- [ ] Test legacy login, new login, wrong password, missing ID, unknown ID, and truncated hashes.
- [ ] Test fallbacks, concurrent password rotation, and existing sessions/tokens.
- [ ] Benchmark latency, CPU, memory, GC, and concurrency under migration-phase load.
- [ ] Have canaries, metrics, rollout stop thresholds, and a rollback **compatible with reading new hashes**.
- [ ] Define legacy support lifetime and recovery for users who rarely log in.
- [ ] Keep libraries, encoders, and patches updated per official advisories.

**Remember:** Upgrading a password hashing algorithm safely is a process of **adding the ability to read legacy hashes, switching the write encoder, and gradually migrating data as users prove they know their passwords**. `DelegatingPasswordEncoder` solves selecting the encoder by ID; `upgradeEncoding` signals when an upgrade is needed; `DaoAuthenticationProvider` and `UserDetailsPasswordService` can perform rehashing within the authentication flow. Yet the application itself must ensure **it never guesses hashes of unknown origin, never overwrites new passwords, rolls out in the right order, and maintains sufficient resources**.

### References

- Spring Security 6.5 — Password Storage: https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html
- Spring Security 6.5 — `DelegatingPasswordEncoder` Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/DelegatingPasswordEncoder.html
- Spring Security 6.5 — `PasswordEncoderFactories`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/factory/PasswordEncoderFactories.html
- Spring Security 6.5 — `DaoAuthenticationProvider`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html
- Spring Security 6.5 — `UserDetailsPasswordService`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetailsPasswordService.html
- Spring Security 6.5 — `Argon2PasswordEncoder`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/argon2/Argon2PasswordEncoder.html
- Spring Security 6.5 — `BCryptPasswordEncoder`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/bcrypt/BCryptPasswordEncoder.html
- OWASP Password Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html

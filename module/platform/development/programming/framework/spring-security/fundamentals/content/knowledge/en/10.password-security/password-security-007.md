# Upgrading Stored Hashes and Handling Legacy Password Data

An application that has existed for years may store passwords in multiple forms: some accounts use bcrypt without an identifying prefix; newer accounts use a stronger bcrypt configuration; a much older system may once have saved MD5, SHA-1, or even plaintext. If you swap `PasswordEncoder` to a new version and deploy immediately, many users may suddenly be unable to log in. Yet if you keep allowing insecure storage formats indefinitely, the system prolongs the risk of password exposure.

This lesson solves a real migration problem: **how do you verify legacy passwords during a transition period, upgrade hashes after users enter the right password, avoid locking out accounts, avoid granting wrong permissions, and retire weak algorithms cleanly?**

The scope focuses on **user password storage** and Spring Security's `PasswordEncoder` mechanism—do not confuse this with JWTs, digital signatures, data decryption, or migrating passwords between two SSO providers. The hands-on example targets **Java 17+** and Spring Security **7.1.2** as a standalone Gradle program. Spring Boot applications should let the **Boot BOM** manage Spring Security dependencies rather than pinning individual versions manually.

Expected outcomes:

- Understand why password hashing is **one-way** and why you cannot recover original passwords to “bulk rehash.”
- Know how to classify legacy data and add algorithm-identification metadata without altering cryptographic values where valid.
- Use `DelegatingPasswordEncoder` with the `{id}encodedPassword` format and migrate incrementally to the target configuration.
- Properly understand `PasswordEncoder.matches`, `upgradeEncoding`, `DaoAuthenticationProvider`, and `UserDetailsPasswordService.updatePassword`.
- Design safe updates under concurrent requests, caches, password changes/resets, inactive accounts, and database errors.
- Have a test matrix, deployment checklist, rollback plan, and explanations for commonly misunderstood cases.

## 1. Do Not Confuse “Hashing,” “Encryption,” and “Re-Encryption”

In password authentication, the server must never store plaintext. When creating or changing a password, it computes a **password hash** using an algorithm with intentionally high cost and an appropriate salt:

~~~text
User chooses password (raw secret)
         |
         v
PasswordEncoder.encode(raw)
         |
         v
Password hash with metadata / parameters / salt / output
         |
         v
Credential store (protected database)

Next login:
  newly entered raw password + stored hash
             |
             v
  PasswordEncoder.matches(raw, stored)
             |
        true or false
~~~

**Password hashing is one-way**, not symmetric encryption with a key for decryption. There is no valid `decode(storedHash)` operation to recover a password and then regenerate bcrypt/Argon2.

In Spring Security:

~~~java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);
    boolean matches(CharSequence rawPassword, String encodedPassword);
    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
~~~

This is a simplified conceptual signature based on the API (newer Java API releases include nullability annotations), not an interface for learners to define themselves. All three methods serve distinct roles:

| Method | Purpose | Do Not Infer |
| --- | --- | --- |
| `encode(raw)` | Generate a **new** hash from currently available plaintext during registration/change/reset/post-login rehash | That you can call `encode(oldHash)` to upgrade a user's password |
| `matches(raw, stored)` | Check whether a newly supplied raw password matches a stored hash | That it returns plaintext or means a password was “decrypted” |
| `upgradeEncoding(stored)` | Determine whether a stored hash should be upgraded per encoder policy | That it updates the database itself, or guarantees upgrades across all `PasswordEncoder` types |

In many implementations, `upgradeEncoding` defaults to `false`. For automatic upgrades, you must **choose an encoder with an appropriate upgrade policy** and **provide a component that updates the stored record**.

### A Wrong “Upgrade” Example

~~~java
// WRONG: only oldHash is available, not the raw password.
String newHash = new BCryptPasswordEncoder(12).encode(oldHash);
~~~

The code above hashes the **old hash string**, not the original password. When a subsequent login runs `matches(rawPassword, newHash)`, it will fail. A system might deliberately wrap old hashes in layers during a specialized transition, but that is a distinct verification protocol requiring dedicated design and review—**not a direct upgrade equivalent to rehashing the raw password**.

## 2. Inventory Legacy Data Before Changing PasswordEncoder

Do not start by swapping the bean and letting users discover they cannot log in. Step one is an **evidence-based inventory of current data**.

| Data Type Found | Format Example | Meaning | Handling Direction |
| --- | --- | --- | --- |
| Prefixed BCrypt | `{bcrypt}$2a$10$...` | Spring has metadata to pick the encoder | Can verify and evaluate work factor |
| Unprefixed BCrypt | `$2a$10$...` | Likely bcrypt from a legacy system | Confirm origin, then attach exact metadata or use a narrow temporary adapter |
| PBKDF2/SCrypt/Argon2 with metadata | `{pbkdf2...}...`, `{scrypt}...` | Has implementation-specific parameters/format | Keep compatible verifier; plan parameter upgrades |
| Unsalted SHA-1/MD5 | Relatively short hex string | Very fast hash, easily cracked offline if leaked | Prioritize forced resets; tightly bound legacy support if unavoidable |
| Plain SHA-256 | Possibly a 64-character hex string | Fast, not an adaptive password KDF | Move to adaptive KDF via login or reset |
| Plaintext | Readable password string | High risk and likely severe policy violation | Treat as security incident; remove and force resets per plan |
| Unknown origin/pepper/salt | String matching no known catalog | Cannot verify safely without a contract | Quarantine and require reset; do not guess |
| Authenticated by external IdP | No internal hash | SSO/OIDC delegates verification to another system | Never synthesize internal passwords from tokens/claims |

**String length alone is insufficient to identify an algorithm.** Two systems may use the same hash family with different salt encodings, charsets, Unicode normalization, or concatenation order. For unprefixed rows, cross-check the app version that wrote them, encoder configs, schema, migration history, controlled backups, and reliable metadata.

A useful inventory report tracks: account counts by format, credential update timestamps, recent login rate, long-dormant account rate, disabled/locked percentages, unidentifiable-format groups, and bulk-reset risk. Never export raw password hashes into dashboards or casual CSVs for reporting convenience.

### Classification Invariants

1. Never convert an arbitrary string to `{noop}` simply because the algorithm is unknown.
2. Never assume every unprefixed hash is bcrypt if the system ever used SHA-1, MD5, and bcrypt.
3. Never configure an overly broad “default encoder” for all missing or unknown ids.
4. Never take the algorithm choice from an HTTP request or user-supplied claims.
5. Never log raw password hashes in migration reports; record only **format groups, counts, and statuses**.

## 3. DelegatingPasswordEncoder and the {id}encodedPassword Format

Spring Security supports storing:

~~~text
{id}encodedPassword

Examples:
  {bcrypt}$2a$10$...
  {bcrypt10}$2a$10$...
  {bcrypt12}$2a$12$...
  {pbkdf2@SpringSecurity_v5_8}...
~~~

The `id` portion is application/Spring Security metadata used to pick the verifier; it is **not part of the underlying bcrypt hash**. `DelegatingPasswordEncoder` holds a map from id to `PasswordEncoder`, plus `idForEncode` to choose the algorithm **when writing new hashes**.

Explicit configuration example for a migration wave:

~~~java
PasswordEncoder oldBcrypt = new BCryptPasswordEncoder(10);
PasswordEncoder newBcrypt = new BCryptPasswordEncoder(12);

Map<String, PasswordEncoder> algorithms = Map.of(
    "bcrypt10", oldBcrypt,
    "bcrypt12", newBcrypt
);

DelegatingPasswordEncoder encoder =
    new DelegatingPasswordEncoder("bcrypt12", algorithms);
~~~

This is a **code snippet** using `org.springframework.security.crypto.password.PasswordEncoder`, `DelegatingPasswordEncoder`, `org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder`, and `java.util.Map`. On Spring Security 7.1.x, check the package import of `BCryptPasswordEncoder` against the actual module API; the runnable example in section 6 shows complete imports.

With the configuration above:

- `encoder.matches(raw, "{bcrypt10}...")` uses the old bcrypt verifier.
- `encoder.matches(raw, "{bcrypt12}...")` uses the new bcrypt verifier.
- `encoder.encode(raw)` **always produces** a value prefixed with `{bcrypt12}`, because `idForEncode="bcrypt12"`.
- `encoder.upgradeEncoding("{bcrypt10}...")` is expected to return `true` because the old id differs from the target id.
- `encoder.upgradeEncoding("{bcrypt12}...")` depends on the target encoder's `upgradeEncoding` policy; for a cost-12 hash created with the config above, no further upgrade is needed.

`bcrypt10` and `bcrypt12` here are **example-chosen IDs**, not built-in defaults in every Spring Security configuration. They encode work-factor policy in metadata. You can choose other IDs if your system has an established convention, as long as DB, encoder map, and migrations agree.

### idForEncode Does Not Decide How Old Hashes Are Checked

Suppose `idForEncode="bcrypt12"` and a record stores `{bcrypt10}...`. Spring Security does not hash with bcrypt12 and hope for a match. It reads the **record's prefix**, looks up the matching encoder, verifies against that format/parameters, and only then checks whether to rewrite using the target encoder.

This enables **gradual migration without forcing every user to reset their password at once**, provided old formats remain temporarily permissible and safely verifiable.

### What Happens When a Prefix Is Missing or an Id Is Unknown?

With default `DelegatingPasswordEncoder`, a hash lacking `{id}` or carrying an unmapped id typically throws `IllegalArgumentException` during verification; do not treat that as proof of a “definitely wrong password.”

Spring offers `setDefaultPasswordEncoderForMatches(...)` to set a fallback when no id matches. **This is not a safe way to guess across all legacy data.** Overly broad fallbacks can verify malformed records with the wrong algorithm or mask data corruption. Prefer normalizing metadata for verified data sources or writing a very narrow format-checked adapter with a firm removal deadline.

## 4. Can You Prepend a Prefix to Bare Bcrypt Without Plaintext?

**Yes, provided you have confirmed with certainty** that the values are compatible bcrypt hashes and missing metadata is the only issue.

Example from a legacy system:

~~~text
Before:
  stored_hash = $2a$10$[53 chars encoding salt+hash]

After metadata migration:
  stored_hash = {bcrypt10}$2a$10$[same 53 chars]
~~~

In this case, prepending `{bcrypt10}` **does not recompute bcrypt** and does not raise the work factor from 10 to 12; it only adds metadata so `DelegatingPasswordEncoder` selects the right verifier. This is **format normalization**, not **upgrading hash strength**.

Distinguish two phases:

~~~text
Phase A — metadata normalization:
  unprefixed bcrypt cost 10
          |
    inventory + confirm source/format
          |
    prepend {bcrypt10} keeping bcrypt body intact
          |
    still bcrypt cost 10

Phase B — real rehash when valid raw password is available:
  login with raw password
          |
    matches(raw, "{bcrypt10}...") -> true
          |
    encode(raw) with bcrypt cost 12
          |
    save "{bcrypt12}..." via safe update
          |
    next time uses bcrypt cost 12
~~~

Phase A can run offline if the format is trustworthy; Phase B can only happen when a **newly submitted raw password** is available during a valid authentication (or when the user sets a new password via a reset flow).

If the database holds multiple kinds of unprefixed hashes, **never run a blind table-wide UPDATE**. Scope updates to proven groups, run controlled sample checks, keep backups/rollbacks, and handle ineligible records separately. Even strings that look like bcrypt require checking their originating code and version.

### Why Must Legacy Plaintext Never Be Saved as {noop}?

`{noop}` corresponds to plain string comparison with no secure password hashing. Although Spring Security includes it for reading legacy/demo data in limited contexts, **wrapping plaintext in Delegating format does not make plaintext safe**. If plaintext still exists in a system, treat it as top-priority remediation: lock down data access, assess incident exposure, force password resets per policy, stop writing plaintext, and purge copies/backups per retention procedures.

Never present adding `NoOp` as a global production fallback as a “quickest fix.”

## 5. Rehash-on-Login: Where Valid Plaintext Briefly Exists

You cannot upgrade every password hash offline because hashing is one-way. However, when a user submits the **correct password**, the authentication provider briefly holds the plaintext **during request handling**. That is the moment a new hash can be generated.

Spring Security provides the hooks:

- `PasswordEncoder.matches(raw, stored)`: verifies right/wrong.
- `PasswordEncoder.upgradeEncoding(stored)`: encoder decides whether the stored hash needs an upgrade.
- `DaoAuthenticationProvider`: in username/password flows, can perform the upgrade after successful authentication if configured.
- `UserDetailsPasswordService.updatePassword(user, newPassword)`: contract to persist the **newly encoded hash** and return an updated `UserDetails`.

From an implementation perspective:

~~~text
Login request
  |
  v
DaoAuthenticationProvider
  |
  +--> UserDetailsService.loadUserByUsername("mai")
  |       stored="{bcrypt10}..."
  |
  +--> PasswordEncoder.matches(rawPassword, stored)
  |         |
  |      false --> reject login, DO NOT rehash
  |         |
  |      true
  |         v
  +--> check account/status conditions per provider
  |
  +--> PasswordEncoder.upgradeEncoding(stored)
            |
          false --> continue success, no DB write
            |
           true
            |
            v
      PasswordEncoder.encode(rawPassword)
      -> "{bcrypt12}..."
            |
            v
      UserDetailsPasswordService.updatePassword(user,newHash)
            |
            +--> DB/CAS write + return updated UserDetails
            |
            v
      Authentication succeeds, ProviderManager
      erases credentials per policy
~~~

This diagram illustrates **decision points**, not a guarantee of exact ordering across all providers or versions. Automatic upgrading in `DaoAuthenticationProvider` requires **wiring an appropriate `UserDetailsPasswordService`**; without a persistence service, `PasswordEncoder.upgradeEncoding` alone cannot modify the database.

**Upgrade only after valid credentials and account status pass policy.** Never take a raw password from an unauthenticated request and overwrite hashes for arbitrary usernames. Protect the update path against concurrent password changes.

### What Input Does UserDetailsPasswordService Receive?

Contract:

~~~java
UserDetails updatePassword(UserDetails user, String newPassword);
~~~

`newPassword` here is the **already newly encoded password hash**, not the raw password. Your implementation must persist it to durable storage and return a `UserDetails` reflecting the updated record.

A common mistake:

~~~java
// WRONG: newPassword is already a hash; encoding it again creates hash(hash).
String doubleEncoded = encoder.encode(newPassword);
repository.savePasswordHash(username, doubleEncoded);
~~~

The right approach is **saving the provided new hash string verbatim**, after verifying the update is authorized, targets the right user, and satisfies concurrency safety.

## 6. Runnable Example: Legacy bcrypt10 → bcrypt12 via DaoAuthenticationProvider

This example uses real Spring Security without an external database. A `ConcurrentHashMap` serves as the **credential store** so you can clearly observe before and after login; `UserDetailsService` constructs a **fresh `UserDetails` on each load**.

Learning scenario:

- Legacy: bcrypt cost 10 **with verified prefix** `{bcrypt10}`.
- New policy: bcrypt cost 12, id `{bcrypt12}`.
- Demo password: `demo-password` (never use on real accounts).
- After the first valid login, the stored hash switches to id `{bcrypt12}`.
- The second login still succeeds.
- A wrong password is rejected and **leaves the stored hash unchanged**.

In production, choosing work factors must rely on hardware benchmarks and threat modeling; bcrypt 10/12 here are two illustrative levels, not a claim that “12 is always enough” for every era or infrastructure.

### 6.1. Layout and build.gradle

~~~text
password-migration-lab/
  build.gradle
  src/main/java/PasswordMigrationDemo.java
~~~

Create `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:7.1.2'
    implementation 'org.springframework.security:spring-security-crypto:7.1.2'
}

application {
    mainClass = 'PasswordMigrationDemo'
}
~~~

In a Spring Boot project, do not copy those explicit Security versions; use starters and let the Boot BOM manage versions.

### 6.2. Complete Java File

Create `src/main/java/PasswordMigrationDemo.java`:

~~~java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsPasswordService;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.DelegatingPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class PasswordMigrationDemo {

    // Demo-only store. In a real product, this is a DB/credential service.
    static final class MemoryUsers
            implements UserDetailsService, UserDetailsPasswordService {

        private final ConcurrentMap<String, String> hashes =
                new ConcurrentHashMap<>();

        void put(String username, String encodedHash) {
            hashes.put(username, encodedHash);
        }

        String storedHash(String username) {
            return hashes.get(username);
        }

        @Override
        public UserDetails loadUserByUsername(String username) {
            String encoded = hashes.get(username);
            if (encoded == null) {
                throw new UsernameNotFoundException("Unknown account");
            }

            // Create a NEW object rather than returning a shared mutable cached User.
            return User.withUsername(username)
                    .password(encoded)
                    .roles("USER")
                    .build();
        }

        @Override
        public UserDetails updatePassword(
                UserDetails user, String newPassword) {

            String previousHash = user.getPassword();
            if (previousHash == null || newPassword == null ||
                    !hashes.replace(
                        user.getUsername(), previousHash, newPassword)) {
                // CAS failed: another request may have reset/changed
                // the password while this login was running.
                throw new AuthenticationServiceException(
                        "Password changed during upgrade");
            }

            // Return a new UserDetails with the new hash; do not encode again.
            return User.withUserDetails(user)
                    .password(newPassword)
                    .build();
        }
    }

    private static Authentication authenticate(
            AuthenticationManager manager,
            String username,
            String rawPassword) {

        var input = UsernamePasswordAuthenticationToken
                .unauthenticated(username, rawPassword);
        try {
            return manager.authenticate(input);
        } finally {
            // Clear credential references on the caller-created input.
            input.eraseCredentials();
        }
    }

    private static String idOf(String encodedHash) {
        int closing = encodedHash.indexOf('}');
        if (!encodedHash.startsWith("{") || closing < 0) {
            throw new IllegalArgumentException("Missing password id");
        }
        return encodedHash.substring(0, closing + 1);
    }

    public static void main(String[] args) {
        PasswordEncoder bcrypt10 = new BCryptPasswordEncoder(10);
        PasswordEncoder bcrypt12 = new BCryptPasswordEncoder(12);

        DelegatingPasswordEncoder encoder =
                new DelegatingPasswordEncoder(
                    "bcrypt12",
                    Map.of("bcrypt10", bcrypt10, "bcrypt12", bcrypt12)
                );

        MemoryUsers users = new MemoryUsers();

        // Simulate unprefixed legacy bcrypt data from a verified source:
        String oldBareHash = bcrypt10.encode("demo-password");

        // Only attach {bcrypt10} metadata; not rehashed yet.
        String verifiedLegacyHash = "{bcrypt10}" + oldBareHash;
        users.put("mai", verifiedLegacyHash);

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        provider.setUserDetailsPasswordService(users);

        AuthenticationManager manager = new ProviderManager(provider);

        System.out.println("before=" + idOf(users.storedHash("mai")));
        System.out.println("upgrade-needed-before="
                + encoder.upgradeEncoding(users.storedHash("mai")));

        Authentication first =
                authenticate(manager, "mai", "demo-password");
        System.out.println("first-login=" + first.isAuthenticated());

        String upgradedHash = users.storedHash("mai");
        System.out.println("after=" + idOf(upgradedHash));
        System.out.println("stored-hash-changed="
                + !verifiedLegacyHash.equals(upgradedHash));
        System.out.println("upgrade-needed-after="
                + encoder.upgradeEncoding(upgradedHash));

        Authentication second =
                authenticate(manager, "mai", "demo-password");
        System.out.println("second-login=" + second.isAuthenticated());

        String beforeWrong = users.storedHash("mai");
        boolean rejected = false;
        try {
            authenticate(manager, "mai", "wrong-password");
        } catch (BadCredentialsException expected) {
            rejected = true;
        }
        System.out.println("wrong-password-rejected="
                + (rejected && beforeWrong.equals(users.storedHash("mai"))));
    }
}
~~~

### 6.3. Running and Reading Output

With JDK 17 or newer and Gradle able to download dependencies from Maven Central:

~~~bash
java -version
gradle --version
gradle run --quiet
~~~

Lines printed by the program in order:

~~~text
before={bcrypt10}
upgrade-needed-before=true
first-login=true
after={bcrypt12}
stored-hash-changed=true
upgrade-needed-after=false
second-login=true
wrong-password-rejected=true
~~~

The output prints no raw passwords or hash values; `BCryptPasswordEncoder` uses a random salt so **specific hash strings differ on every run**, while the ids and booleans above are deterministic.

Step-by-step walkthrough:

1. `oldBareHash` is an **already-hashed** bcrypt cost-10 string generated from the demo password to simulate a legacy system.
2. `verifiedLegacyHash` merely prepends `{bcrypt10}`; the same old hash still verifies the password.
3. `DelegatingPasswordEncoder` has `idForEncode="bcrypt12"`, so `upgradeEncoding` on id `bcrypt10` returns `true`.
4. `DaoAuthenticationProvider` verifies the password and uses `UserDetailsPasswordService` to write the new hash via `updatePassword`.
5. `ConcurrentHashMap.replace(username, oldHash, newHash)` is a **compare-and-set**: it swaps only if the current value still equals what this request verified.
6. `User.withUserDetails(user).password(newPassword).build()` returns the updated object for the provider to continue; it does not rehash `newPassword`.
7. By default `ProviderManager` may erase credentials on the resulting Authentication after verification. The store keeps independent hash strings rather than a shared mutable `User`.
8. The second login uses id `bcrypt12`, needs no further rehash, and still verifies cleanly.
9. With `wrong-password`, the provider throws `BadCredentialsException` and performs no hash update; the final check confirms the stored value stayed unchanged.

**The demo exercises Spring Security's real provider and password service**, unlike a script that only calls `encoder.matches` directly and fakes a migration. Still, this is an in-memory learning setup and does not replace testing HTTP, DB transactions, and concurrency in production.

### 6.4. Why Does CAS Matter?

If two login requests arrive simultaneously:

~~~text
T1 reads old hash A
T2 reads old hash A

T1 verifies password and writes new hash B
T2 tries to write new hash C based on A

CAS:
  T1: A -> B  (succeeds)
  T2: A -> C  (fails, because DB now holds B)
~~~

For a bcrypt rehash migration, if the second request fails CAS only because the first request just upgraded the **same password**, the application can implement a controlled retry flow. However, **if T2 failed because the user just changed or reset their password in another session**, T2 must never “force overwrite” or issue an Authentication from a superseded credential.

This demo chooses to fail closed with `AuthenticationServiceException` when a concurrent update fails. In production, you can reload the record and re-evaluate all policy conditions before deciding whether to retry—never retry indefinitely with sensitive credentials.

## 7. Connecting UserDetailsPasswordService to a Real Database

In an SQL database, never simply run:

~~~sql
-- UNSAFE under concurrent updates:
UPDATE account_credentials
SET password_hash = :new_hash
WHERE username = :username;
~~~

A login request holding an old hash could overwrite a brand-new password reset. Beyond losing a legitimate change, that risks restoring access with an old revoked password.

A better **compare-and-swap** pattern:

~~~sql
UPDATE account_credentials
SET password_hash = :new_hash,
    password_algorithm = :new_algorithm,
    password_updated_at = CURRENT_TIMESTAMP
WHERE account_id = :account_id
  AND password_hash = :old_hash
  AND password_algorithm = :old_algorithm;
~~~

Placeholders with `:` are named-parameter pseudo-SQL; standard `JdbcTemplate` uses `?`, whereas `NamedParameterJdbcTemplate` supports named parameters. Adapt SQL to your exact schema and prefix storage method; avoid storing two redundant algorithm columns that could drift out of sync.

If the password column stores the full `{id}hash` string, a separate `password_algorithm` column may be unnecessary. If both exist, update them in the **same transaction** and guarantee consistency. An immutable internal `account_id` is more reliable than mutable usernames or emails.

### Java JDBC Fragment

~~~java
// Fragment in a service that already has JdbcTemplate; requires a real repository, transaction,
// mapper, and UserDetails class. Not a standalone program.
@Override
@Transactional
public UserDetails updatePassword(UserDetails user, String newEncoded) {
    if (newEncoded == null || user.getPassword() == null) {
        throw new AuthenticationServiceException(
                "Missing password during upgrade");
    }

    int updated = jdbc.update(
        "UPDATE app_accounts SET password_hash = ? " +
        "WHERE username = ? AND password_hash = ?",
        newEncoded, user.getUsername(), user.getPassword()
    );

    if (updated != 1) {
        throw new AuthenticationServiceException(
                "Password was updated concurrently");
    }

    return User.withUserDetails(user)
               .password(newEncoded)
               .build();
}
~~~

In production prefer an **internal ID** over username, add a version column condition if needed, and ensure status/membership cannot change unintentionally. If the outer transaction is read-only, the UPDATE will fail to behave as intended; configure transaction boundaries properly. `updated==1` is the required proof that the update took effect.

**Order of persistence and return:** the service must return `UserDetails` with the new hash only after the database update succeeds. If the update fails yet an authenticated result is still returned, application state diverges and credential-revocation policies may be violated.

### Separate Migration from User-Initiated Password Changes

At least three paths modify a stored hash:

1. The user enters the valid old password and the provider upgrades the hash **without changing the password**.
2. The user changes their password through an authenticated/step-up flow.
3. The user resets their password via a separate recovery token/proof.

These three flows do not carry identical assurance levels and should not share a blind DB write function that skips auditing. Every hash change must be minimally audited—**without logging passwords or hashes**.

## 8. Choosing a Strategy for Each Legacy Group

No single converter handles every kind of legacy data. Build a decision table:

| Legacy Group | Can Verify Temporarily? | Can Auto-Upgrade on Login? | Operational Direction |
| --- | --- | --- | --- |
| Low-cost bcrypt with prefix | Yes, if still acceptable under policy | Yes, once `matches` succeeds | Rehash-on-login, track progress |
| Unprefixed bcrypt with verified origin | Yes, after metadata normalization or narrow adapter | Yes, after login | Normalize prefixes and upgrade cost |
| Legacy PBKDF2/scrypt/Argon2, known params | Yes, requiring exact version/params | Yes, if encoder is compatible and user logs in | Use version-specific ids; rehash |
| Custom salted SHA-1/MD5 | Consider only within a risk-assessed transition window | Technically possible when raw matches, though algorithm is weak | Prioritize forced reset; firm sunset and monitoring |
| Weak unsalted hash | High risk | Can verify and rehash, but do not prolong | Priority reset to cut exposure |
| Plaintext | Should not sustain logins from exposed data | Raw is present, yet system is already at risk | Incident handling and mandatory change/reset |
| Unknown algorithm/pepper/charset | No trustworthy verifier | No | Block affected login path and reset safely |
| Long-inactive accounts | May hold very old hashes | No raw password without login | Reset/expiration campaign; do not wait forever |
| SSO accounts with no local password | No hash to upgrade | No | Delegate to IdP; never synthesize local passwords |

**Key rule:** “can verify old format” does not mean “safe to keep accepting forever.” For weak hashes, set an expiration date on legacy verifiers and a reset flow for unconverted users; depending on severity, block legacy logins immediately.

### When an Old Hash Cannot Be Verified

Never guess original passwords or “upgrade” by hashing the old hash itself. A secure reset flow is the right path: verify ownership via a trusted channel, issue a short-lived single-use reset token, store a hash of the token if persisted server-side, enforce TTL and replay checks, then compute a new hash from the password the user sets.

Specifically, **never email a new plaintext password**, never send an old hash so “the user can recover it,” and never assign the same default password to a batch of accounts.

## 9. Work Factor: Choosing a New Operable Level

Modern password hashing algorithms use **intentionally high computational cost**. With bcrypt, `strength` or `cost` is the log2 rounds exponent: cost grows rapidly as you increment it.

Example:

~~~java
PasswordEncoder bcrypt10 = new BCryptPasswordEncoder(10);
PasswordEncoder bcrypt12 = new BCryptPasswordEncoder(12);
~~~

Cost 12 normally requires much more work than cost 10; this does **not** mean “exactly four times more secure” on some universal linear scale across all hardware. The goal is making offline password guessing resource-heavy while keeping enough capacity to serve legitimate login traffic.

Spring Security documentation recommends tuning work factors based on actual verification latency on your target system (citing a reference target around one second for verification), rather than picking one hardcoded number for every machine. Measure:

- P50/P95/P99 latency for `PasswordEncoder.matches` and `encode`.
- Concurrent login volume, CPU/memory, and queueing—especially under brute-force traffic.
- Added rehash-on-login cost during migration (each legacy login performs an extra hash).
- Traffic surges when users log in en masse post-deploy, and autoscaling behavior.
- Request/rate limits, timeouts, circuit breakers, and compromised-password checks if integrated.

**Never weaken cost just to pass a load test**, yet never push cost so high that an attacker flooding login requests exhausts authentication capacity. Combine multi-layer rate limiting with system monitoring.

### If Choosing Argon2, scrypt, or PBKDF2

You must also explicitly document **implementation version, parameters, salt, output format, and required dependencies**. Never change the `{id}` of a bcrypt hash to `{argon2}` without recomputing from the raw password. `{id}` is a selector, not a cryptographic conversion.

A migration from bcrypt to Argon2 can use `DelegatingPasswordEncoder` with both verifiers, set the new `idForEncode`, rehash-on-login, and reset dormant accounts. Selecting Argon2 also depends on organizational policy, runtime support, and library provenance, so review dependencies and security guidance for your exact release.

## 10. Bcrypt Pitfalls: Length Limits and Unicode Normalization

**Traditional bcrypt has a byte-level input limit**, typically around 72 bytes. Implementations may truncate or reject inputs exceeding that boundary, and how `String` converts to bytes affects behavior. For passwords containing emoji or Unicode characters, 72 **bytes** is not 72 **characters**.

During migration, verify:

1. Which character encoding did the legacy system use to convert passwords to bytes?
2. Were long passwords truncated, and before or after UTF-8 encoding?
3. Did it apply `trim`, lower-casing, or Unicode normalization before hashing?
4. When changing bcrypt libraries, does the new version handle `$2a`, `$2b`, and `$2y` identically?
5. Do any accounts use very long passphrases or multi-byte characters?

**Never silently change password normalization during a rehash wave**; the same user-typed password could verify differently across implementations. If fixing an unsafe legacy password-handling contract, execute an explicit transition/reset plan—never “auto-truncate” new passwords to match legacy behavior.

The example in this lesson uses short ASCII passwords to focus on the upgrade mechanism; that does not imply every legacy password in the wild is automatically compatible.

## 11. Pepper, Salt, and Rotating External Keys

- **Salt** varies per password hash, can normally be stored alongside the hash, and is not secret. Bcrypt embeds salt and parameters in its format.
- **Pepper** is an additional secret managed by the application/organization (if used by design), kept in a secret manager/HSM or dedicated store—never inside the same DB as password hashes.
- **Hash work factor** controls computational cost and does not replace salt or pepper.

When migrating a system that used a pepper, you must know the **pepper version**, combination order (before or after hashing), encoding, and storage location. If the pepper for old hashes is lost, verifying old passwords may become impossible even with hashes still in the DB; recovery usually requires password resets.

Never put a pepper in source code, committed `application.properties`, migration logs, or message queues. If your system rotates peppers, support explicit versioning or rotation procedures. Rotating a pepper cannot be solved merely by renaming `{id}` unless the format includes a verifier compatible with that version.

### Should You “Wrap-Hash” to Patch Legacy SHA-1 Quickly?

A `bcrypt(sha1(password))` construction can be considered as a **temporary wrapper in a specialized design** while raw passwords are unavailable, yet it is not equivalent to `bcrypt(password)`. If old SHA-1 hashes leaked previously, an attacker already holds the inner input to test or precompute against the wrapper. It also preserves all legacy weaknesses (encoding, truncation, normalization, missing salt). Therefore **never treat wrap-hashing as a finished migration**; plan direct replacement from verified raw passwords or policy-driven resets.

## 12. Controlled Rollout Across Multiple Application Versions

A sound migration follows clear phases:

| Phase | Action | Gate to Advance |
| --- | --- | --- |
| Inventory | Count formats/algorithms/work factors and active user ratios | Zero “unknown” groups without a policy |
| Schema preparation | Column wide enough for new prefixes/hashes, unique/constraints, backups | Read/write tests show zero truncation |
| Compatibility read | Deploy encoders able to verify **all approved ids** | Valid legacy users can still log in |
| Normalization | Prepend prefixes to verified legacy hash groups | Sample verification and migration audit pass |
| New writes | All registrations, changes, and resets hash under the new policy | Zero new rows created in old formats |
| Rehash-on-login | Enable `UserDetailsPasswordService`, CAS, metrics | Legacy logins upgrade safely, no privilege escalation |
| Sunset | Remove weak verifiers after policy window; reset unconverted users | Legacy ratio drops below approved threshold |
| Cleanup | Remove flags, legacy adapters, and retired secrets/peppers | Audits/metrics confirm no fallback paths remain |

### Expand → Migrate → Contract

When deploying multiple nodes or rolling updates, plan for **two-way compatibility**:

~~~text
Node V1: understands {bcrypt10}, does not understand {bcrypt12}
Node V2: understands {bcrypt10} and {bcrypt12}, writes {bcrypt12}

If V2 starts writing too early:
  user logs into V2 -> DB upgraded to {bcrypt12}
  user hits V1 next -> V1 cannot verify the new hash
~~~

To avoid this failure:

1. **Expand:** first deploy all nodes able to **read both old and new**.
2. **Migrate:** only once the entire fleet reads both, enable writing/rehashing new hashes.
3. **Contract:** after legacy share drops and reset deadlines pass, retire old algorithm readers.

This also governs rollbacks: rolling back to a V1 that cannot read new hashes locks out upgraded users. Prepare a rollback build **that still understands the new format**, or verify compatibility before advancing phases; never treat restoring an old DB backup as an easy rollback, as it can resurrect changed or revoked credentials.

### Separate Feature Flags for Old Reads and New Writes

Two toggles can be managed independently:

~~~text
password.allowLegacyVerification = true/false
password.writeTargetAlgorithm = bcrypt12
password.upgradeOnSuccessfulLogin = true/false
~~~

These are **hypothetical policy names**, not built-in Spring Boot properties. Implement them under strict controls in code/config if needed. Never allow end users or query parameters to alter flags.

## 13. Error Handling and Fail-Safe Behavior When Migration Fails

During a login request:

| Error | Internal Classification | Response |
| --- | --- | --- |
| Wrong raw password | `BadCredentialsException` | Do not rehash; return safe login failure response |
| Nonexistent username | Usually masked by provider as bad credentials | Do not disclose account existence |
| Missing or unmapped hash id | Incompatible data/config bug; may throw `IllegalArgumentException` | Fail closed, classify, and remediate; never add loose fallbacks |
| Valid hash where `upgradeEncoding` detects new policy | Not an error | Encode raw password and update with CAS |
| Concurrent password change causes CAS failure | Credential update race | Do not overwrite; recheck policy or fail closed |
| Transient DB outage | Service failure | Never grant login, never record as wrong password |
| `UserDetailsPasswordService` unconfigured | Upgrade skipped despite encoder signal | Alert via metrics; fix wiring per design |
| Account disabled/locked/expired | Account status | Never let rehashing bypass status checks |
| New cost causes timeouts | Capacity/performance issue | Measure and tune safely; never disable authentication |
| Legacy verifier already sunset | Legacy format retired | Require verified reset rather than reopening weak algorithms |

Always **fail closed**: without proof of a valid password, never issue a valid `Authentication`. Failing closed does not mean collapsing every incident into “wrong password” internally; internal logs and metrics must distinguish infrastructure outages, malformed legacy records, expired policies, and actual credential mismatches.

### Supporting Users Safely

Never email an unverified address saying “account abc has an old SHA-1 password.” An outsider could use that to confirm account existence or credential weakness. Login UIs should return safe generic responses, while detailed reset/activation paths must require proper verification.

## 14. Measuring Migration Progress Without Exposing Password Hashes

Export only **aggregated metrics** by policy/algorithm, for example:

~~~text
password_hash_inventory{policy="bcrypt10"}  12400
password_hash_inventory{policy="bcrypt12"}  38500
password_migration_success_total              710
password_migration_cas_conflict_total           3
password_migration_unknown_format_total         8
password_login_latency_bucket{...}             ...
~~~

These numbers are **illustrative only**, not real telemetry. When designing metrics:

- Never attach full usernames/emails or raw hashes as metric labels.
- Internal audit logs with restricted access and retention may record account IDs if needed.
- Never put raw passwords, password hashes, bearer tokens, DB secrets, or peppers into logs.
- Avoid turning migration logic into an account/algorithm enumeration oracle via public responses or timing.
- Distinguish `login_success` from `rehash_success`: successful logins do not mean hashes upgraded if the password service is missing.
- Track long-dormant and disabled/locked users; handle them via reset policies.

### A KPI Never to Rely On Alone

“100% of today's logins used bcrypt12” does **not** mean “100% of accounts are upgraded”: inactive accounts may still hold old hashes. Measure both **credential record share by id** and **last-authentication age**. When the legacy support deadline arrives, un-upgraded accounts must go through resets.

## 15. Technical Test Matrix

A trustworthy migration must test encoder, provider, storage, and web layers together. Minimum scenarios:

| Scenario | Expected Outcome |
| --- | --- |
| bcrypt10 user enters right password | Login succeeds, stored hash upgrades to `{bcrypt12}` |
| bcrypt12 user enters right password | Login succeeds, no rewrite needed since policy is satisfied |
| bcrypt10 user enters wrong password | Login fails, stored hash stays unchanged |
| Unknown username | No user auto-created, no account existence leaked |
| Unprefixed hash outside verified group | Fails closed; never tries `NoOp` or guesses format |
| Bare bcrypt with verified origin | Prefix attached, `matches` succeeds, then rehashes on login |
| Malformed/truncated hash | Access denied, internal format error reported |
| Disabled/locked/expired user | Login denied even if password matches |
| Two concurrent logins upgrading the same hash | One CAS succeeds; the other handles conflict per policy |
| User changes/resets password during legacy login | Migration does not overwrite the new hash |
| DB unavailable during update step | Never silently claims upgrade succeeded; clear fail-closed/retry policy |
| `UserDetailsPasswordService` absent | Login may succeed while hash stays un-upgraded; metric/alert fires |
| Shared mutable `UserDetails` in cache | Password hash in cache not wiped by credential erasure |
| Unicode, long passwords, legacy charsets | Verifier compatibility or explicit reset path |
| Retired pepper/key missing | Never guesses secret; safe reset |
| Rolling deploy V1/V2 | All active nodes read new hashes before writes begin |
| Rollback build | Still reads upgraded hashes; never restores revoked credentials |
| Inactive user past deadline | Legacy path disabled/reset per policy; never waits indefinitely |
| Rate limits and high load | Login throughput, P95/P99, CPU/memory meet SLOs |
| API failure handler | Never leaks algorithm, plaintext, hash, stack trace, or DB details |

**Note on `@WithMockUser`:** this annotation builds a pre-authenticated `Authentication` for authorization tests and usually **bypasses** `DaoAuthenticationProvider` and `PasswordEncoder`. To prove post-login hash upgrading really works, invoke `AuthenticationManager.authenticate` or submit credentials through the login filter in integration tests. Section 6 invokes the real manager.

### Test Properties, Not Fixed Bcrypt Strings

Bcrypt uses a random salt, so two `encode("demo-password")` calls normally produce different strings. Never assert hash bytes against a fixed literal unless controlling the salt explicitly. Instead, assert:

~~~java
// Test fragment assuming encoder and an already-created actualHash.
assertTrue(encoder.matches("demo-password", actualHash));
assertTrue(actualHash.startsWith("{bcrypt12}"));
assertFalse(encoder.upgradeEncoding(actualHash));
~~~

You will need JUnit static imports and an appropriate test setup. The snippet above shows assertions, not a standalone program. For end-to-end login, assert the DB hash changed yet still `matches` the same raw password, and that a wrong password leaves it unchanged.

## 16. Common Mistakes to Avoid

1. **“Old hashes can be decrypted—just grab plaintext and re-encrypt.”** False for true password hashing.
2. **“Calling `encode(oldHash)` is an upgrade.”** False: it hashes the old hash rather than the raw password.
3. **“Prepending `{bcrypt12}` to a cost-10 hash increases security.”** False: it only edits metadata without changing hash cost.
4. **“Ids `bcrypt10` and `bcrypt12` are built-in Spring Security defaults.”** In this lesson they are custom ids registered in a map.
5. **“Changing `idForEncode` automatically upgrades all rows.”** No: it only affects new encodes; login or reset is needed for raw passwords.
6. **“Using `setDefaultPasswordEncoderForMatches(NoOp)` fixes all legacy records.”** Extremely dangerous; widens accepted inputs unsafely.
7. **“Every unprefixed string is bcrypt.”** False; you must verify origin and format.
8. **“`upgradeEncoding=true` writes to the DB automatically.”** No; you need `UserDetailsPasswordService` or a transactional updater.
9. **“`updatePassword` receives the raw password.”** No; its argument is the newly encoded hash per policy.
10. **“`updatePassword` should encode it again just to be safe.”** No; that causes double hashing.
11. **“Wrong passwords can still trigger an upgrade.”** No; no verified raw password exists.
12. **“Sharing a `UserDetails` authority means all accounts upgraded.”** No; migration happens per credential and policy.
13. **“An unconditional UPDATE by username is enough.”** That can overwrite a concurrent password reset; use CAS/versioning.
14. **“If CAS fails, just run a second UPDATE to overwrite.”** That risks restoring an old revoked credential.
15. **“Database hashes can be logged because they aren’t plaintext.”** Hashes remain sensitive and vulnerable to offline cracking if leaked.
16. **“Keeping MD5/SHA-1 verifiers forever is fine with rate limiting.”** If the DB is stolen, online rate limits cannot stop offline cracking.
17. **“Inactive accounts upgrade automatically.”** No: without raw passwords, they need resets or a dedicated design.
18. **“Bcrypt cost 12 is an eternal answer.”** Benchmark and update policies as hardware and threats evolve.
19. **“Changing one `PasswordEncoder` bean in Boot covers every custom provider.”** Custom providers may hold their own encoder; verify actual wiring.
20. **“Having a `UserDetailsPasswordService` bean means every Spring Security version/flow uses it automatically.”** Verify the specific provider is wired to call it and write tests.
21. **“After an upgrade, users don’t need to change breached passwords.”** Rehashing does not make an exposed password secret again; force resets on leaks.
22. **“Changing a hash revokes old sessions/JWTs.”** Not by default; sessions and tokens have separate lifecycles.
23. **“Once using BCrypt, Unicode and byte limits don’t matter.”** False; check format compatibility before and after migration.
24. **“Rolling deploys don’t need to worry about old-node code.”** Old nodes may fail to read new formats.
25. **“Restoring an old DB snapshot is a safe migration rollback.”** It can bring back changed or revoked passwords; plan controlled rollbacks.

## 17. Self-Check Questions

**Question 1.** Why can’t a stored SHA-1 hash be converted to an equivalent bcrypt hash with a single SQL batch?

*Answer:* You do not have the raw password. `bcrypt(SHA-1(password))` differs from `bcrypt(password)`. To create a direct hash from the raw password, you need the user to submit a valid password at login or reset.

**Question 2.** How does `{bcrypt10}$2a$10$...` differ from `{bcrypt12}$2a$10$...` if the rest of the string stays identical?

*Answer:* Only the metadata differs; **the internal bcrypt cost is still 10**. Never mislabel ids to pretend the work factor increased; only rehashing into a real cost-12 hash upgrades strength.

**Question 3.** Can `DelegatingPasswordEncoder` verify old bcrypt and write new bcrypt within the same application?

*Answer:* Yes. Map both old and new ids to their respective verifiers, set the new `idForEncode`, and persist new hashes after `matches` succeeds.

**Question 4.** Why is `UserDetailsPasswordService` required in certain automatic upgrade flows?

*Answer:* `PasswordEncoder.upgradeEncoding` only returns a boolean and does not write data. `DaoAuthenticationProvider` uses the password service to persist the new encoded hash after authentication.

**Question 5.** A user changes their password while another login is rehashing an older hash. What must you guard against?

*Answer:* Never overwrite the new hash using stale state from the old hash. Use CAS/versioning, handle races per policy, and fail closed when evidence is no longer valid.

**Question 6.** When legacy data is unprefixed bcrypt, can you add `{bcrypt10}` without plaintext?

*Answer:* Only after verifying the true hash type and ensuring consistent ID policy. That is metadata normalization; raising the work factor via rehashing still requires the raw password at login or reset.

**Question 7.** Why should `{noop}` never be used as a fallback for all legacy passwords?

*Answer:* NoOp permits plaintext comparison and provides no secure password hashing. Broad fallbacks can silently accept malformed or weak data.

**Question 8.** Across multiple app nodes in a rolling deploy, should reading or writing new hashes be enabled first?

*Answer:* Every node must **understand reading the new hash** before any node begins writing new hashes; otherwise rollbacks or routing to older nodes breaks logins.

**Question 9.** How do you know a migration campaign is done when 20% of accounts haven’t logged in for 2 years?

*Answer:* Measure inventory by credential records, not just login traffic; enforce deadlines and password resets for accounts that cannot upgrade via login. Retire legacy verifiers only once safety and communication criteria are met.

**Question 10.** Why is rehashing an incomplete response when passwords were leaked?

*Answer:* Third parties may already know the raw password. Changing the server-side hash does not make that raw password secret again; force password changes/resets, consider revoking sessions/tokens, and monitor accounts per policy.

**Question 11.** Long Unicode passwords fail login after migration even though users insist they typed them right. What should you inspect?

*Answer:* Character encoding, Unicode normalization, bcrypt byte-limit handling, legacy trim/truncate rules, and hash/pepper formatting; never arbitrarily lower-case user passwords.

**Question 12.** If `upgradeEncoding("{bcrypt12}...")` returns false, does that mean the hash will never need upgrading again?

*Answer:* No. It only reflects the current encoder policy; when threat models or target costs rise, policy and `idForEncode` can be upgraded again.

## 18. Production Application Checklist

- [ ] Inventoried legacy hash formats accurately by origin and metadata, never guessing by length.
- [ ] New schema has sufficient room for `{id}`, salt/params/hash; migration backed up and tested.
- [ ] Every legacy record has a known algorithm/charset/pepper or a safe reset path.
- [ ] Zero plaintext stored, no global NoOp fallback, no hashes/tokens/passwords logged.
- [ ] Encoder map contains only approved algorithms, and `idForEncode` reflects the new write policy.
- [ ] If prepending prefixes to bare bcrypt, hash origin is verified; prefixing is not mistaken for rehashing.
- [ ] Registration, password change, and reset flows all create hashes under the new policy.
- [ ] Provider actually uses the configured `PasswordEncoder` and wires `UserDetailsPasswordService` where needed.
- [ ] Rehashes **only after successful authentication**, never `encode(oldHash)` and never double-encoded.
- [ ] `UserDetailsPasswordService` updates hashes using CAS/versioning or proper transactions, never overwriting concurrent resets.
- [ ] `UserDetails` cache does not share mutable principals wiped by credential erasure.
- [ ] Failed logins, disabled/locked accounts, and DB errors never trigger hash updates.
- [ ] Work factor benchmarked on real infrastructure, with overload/rate-limit controls during migration.
- [ ] Tests cover old/new bcrypt, wrong passwords, concurrent updates, unknown IDs, Unicode/long passwords, and DB failures.
- [ ] Rollout follows expand-read, migrate-write, contract-remove; older nodes never break on new hashes.
- [ ] Rollback never resurrects revoked passwords or restores weak algorithms indefinitely.
- [ ] Migration metrics track **credential record counts**, not login counts alone.
- [ ] Deadlines and reset plans exist for dormant accounts, very weak hashes, and incompatible formats.
- [ ] Post-migration, legacy verifiers/flags removed and operational docs/alerts updated.
- [ ] If a password leak occurs, reset/revocation workflows run rather than rehashing alone.

### Summary

**Upgrading password hashes is a process of updating how authentication evidence is stored, not decryption.** Metadata can be added to a accurately identified legacy hash without the raw password. Yet to genuinely strengthen protection, the system must verify a user's valid password and generate a **new hash from the raw password**, or have the user set a new password through a secure reset flow.

In Spring Security, the trio `DelegatingPasswordEncoder` – `DaoAuthenticationProvider` – `UserDetailsPasswordService` provides the foundation for rehash-on-login; the application must still handle database CAS, concurrency, caching, observability, rolling deployments, and legacy retirement dates. Executing the entire lifecycle lets you migrate without locking out users or preserving legacy vulnerabilities.

### Official Documentation

- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html)
- [Spring Security — PasswordEncoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/crypto/password/PasswordEncoder.html)
- [Spring Security — DelegatingPasswordEncoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/crypto/password/DelegatingPasswordEncoder.html)
- [Spring Security — BCryptPasswordEncoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/crypto/bcrypt/BCryptPasswordEncoder.html)
- [Spring Security — DaoAuthenticationProvider API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html)
- [Spring Security — UserDetailsPasswordService API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetailsPasswordService.html)
- [Spring Security — UserDetails and Credentials Management](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details.html)
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)

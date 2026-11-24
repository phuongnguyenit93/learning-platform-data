# Upgrading Password Hashes Without Forcing Every User to Reset at Once

> **Capstone Practice — Spring Security Authentication (Java 17+, Spring Boot 3.x / Spring Security 6.x).** When an application already stores hundreds of thousands of password hashes using an older algorithm or work factor, you do not necessarily have to force every user to change their password on a single day. You can perform a **lazy rehash**: continue verifying explicitly recognized legacy hashes, and as soon as a user signs in with the right password, use that just-verified password to compute a hash under the new policy and persist it with an atomic update. This reduces disruption, but requires a plan for inactive accounts, protection against races with password resets, and ensuring all application versions can read the new hash.

## 1. Understanding the Requirements Properly

Three problems must be solved simultaneously:

1. **Security:** New hashes use an appropriate algorithm and benchmarked cost; legacy hashes must never be used to write new credentials.
2. **User experience:** Users sign in normally without a mass forced reset.
3. **Consistency:** A password change/reset concurrent with a lazy rehash must never re-enable the old password; rollout/rollback must not cause different nodes to accept different formats.

A password hash is a **one-way** output. There is no reliable computation that turns `hash_old(password)` into `hash_new(password)` without the original password. Running `bcrypt(oldHash)` across every row only produces a hash of the old hash string, **not** a hash of the user's actual password; unless you design a completely different verifier, users will be unable to sign in.

Therefore, the proper workflow is:

~~~text
User sends password to server over TLS
  -> Load current password hash and account status
  -> Verify password with that hash's algorithm/parameters
  -> Wrong: reject, DO NOT modify hash
  -> Correct: check whether hash needs upgrade
            |
            +-- No: complete authentication per policy
            |
            +-- Yes: encode(just-verified password) with new scheme
                    -> CAS update stored hash/version
                    -> reload/return updated UserDetails
                    -> complete authentication if account/MFA remains valid
~~~

**Lazy** means upgrading only when the user supplies the correct password. No password is temporarily buffered in a queue/job or pulled from logs. **Rehash** means regenerating the hash from the just-verified raw password, **not** swapping labels or re-hashing the old digest.

## 2. Why Upgrade the Algorithm or Work Factor?

Hashes suitable for storing passwords must resist offline guessing after a database breach. Plain SHA-256/MD5/SHA-1 compute far too quickly; attackers can test huge numbers of passwords per second. Modern password algorithms such as Argon2id, bcrypt, or PBKDF2 incorporate cost parameters (CPU, memory, iterations) and a unique salt per hash.

| Component | Meaning | Migration Note |
| --- | --- | --- |
| Algorithm | bcrypt, Argon2id, PBKDF2, or older legacy | The verifier must select the exact algorithm for each record |
| Unique salt | Random value unique to each hash | Usually embedded in the hash string, not a secret |
| Work factor | bcrypt cost, PBKDF2 iterations, Argon2 memory/time | Newer versions may raise parameters |
| Password hash format | Layout storing salt/parameters/digest | Never truncate or alter encoding |
| `{id}` | Encoder routing label in Spring | Allows multiple formats to coexist |
| Pepper | Secret kept outside the DB if required by threat model | Plan KMS rotation; never mix schemes improperly |
| Credential version | Version incremented on every hash/secret change | Prevents overwrites when login and reset race |
| PasswordEncoder | Component for `encode`, `matches`, `upgradeEncoding` | Use the proper APIs, never assemble hashes manually |

**Salted hashes do not produce two identical strings for the same password.** Encoding the same password twice with bcrypt/Argon2 typically produces different hashes because of fresh salts. `matches(raw, storedHash)` is the only valid comparison.

Work factor selection must rely on OWASP guidance, runtime environment, account sensitivity, compliance requirements, and **p95/p99 benchmarks under realistic load**. Setting the cost too high makes it easy to trigger CPU/memory exhaustion during credential stuffing. Place rate limits/bulkheads in front of password verification.

## 3. Common Migration Patterns

| Scenario | Old Hash | Target Hash | Transition Approach |
| --- | --- | --- | --- |
| Raising bcrypt cost | bcrypt cost 10 | bcrypt cost 12 | `matches` old hash, `upgradeEncoding`, encode from just-entered password |
| Switching schemes | Legacy PBKDF2 format | Argon2id or new bcrypt | `DelegatingPasswordEncoder` maps both by ID |
| Adding format label | Bcrypt `$2a$...` missing prefix | `{bcrypt}$2a$...` | Metadata-only prefix update after verification |
| Rotating pepper | Old key/pepper | New pepper in KMS | Verify old then upgrade on login; inactive accounts need a plan |
| Unsalted legacy SHA-256 | SHA-256 digest | New adaptive KDF | Verify only exact legacy format during transition, rehash immediately on valid login |
| SSO/LDAP | Password at IdP/directory | No local hash | Cannot migrate in the app; the credential-owning source must handle it |

**A metadata-only prefix update differs from a cryptographic upgrade.** Adding `{bcrypt}` to an existing bcrypt hash only helps Spring select the verifier; the hash's cost remains unchanged. A lazy rehash must follow afterward to actually increase protection.

If a legacy hash's salt, pepper, encoding, or layout cannot be determined, **do not guess the algorithm**. Some accounts will need a secure reset/re-enrollment; the goal is to avoid mass forced resets, not to promise that zero users will ever need a reset.

## 4. Success Criteria and Invariants

A migration plan is sound when:

- Old hashes are **read and verified** only when the scheme is explicitly permitted and precisely known.
- All **new registrations/password changes/resets** write using the current encoder.
- Wrong passwords, unknown users, disabled/locked accounts, or LDAP/DB errors **never** write a new hash.
- A user with a legacy hash logs in validly -> the new hash is written to the DB **only for the exact account/version/hash**.
- Two concurrent logins cannot overwrite a password reset and cannot re-enable a disabled account.
- Once a hash is at the target cost/algorithm, subsequent logins **do not keep rehashing forever**.
- Nodes across deployed regions/versions can verify **both old and new hashes** during rolling deployments.
- Metrics exist for scheme distribution, migration progress, CAS conflicts, login errors, CPU, and legacy retirement.
- Hashes/passwords never appear in logs, metric labels, events, tickets, or queues.

Do not merely test "login succeeds" and consider it done; you must **read back the DB** and prove the next login verifies the new hash, with **no path that accidentally re-accepts the old password after a reset**.

## 5. Inventorying Data and Designing Columns Before Writing

You do not need original passwords to gather statistics:

- Account counts by algorithm/prefix and work factor; count of malformed/unrecognized records.
- Whether each record has a local password or only uses LDAP/OIDC/passkeys.
- How many accounts carry legacy hashes yet are inactive or disabled.
- Current hash length, target hash length, character set, and collation.
- Password/credential version, account status, stable tenant ID, and hash last-upgraded timestamp.
- Whether old peppers/keys are still retained and accessed under policy.
- Write paths outside form login: API login, reset, admin, mobile, batch provisioning.

**Never dump plaintext or stored hashes into logging.** You may report `scheme=PBKDF2_V1`, `cost_bucket=low`, and cohort counts/ages, but never put raw hashes or emails into Prometheus labels.

### Suggested Schema

~~~sql
CREATE TABLE account_credentials (
    account_id          VARCHAR(64) PRIMARY KEY,
    tenant_id           VARCHAR(64) NOT NULL,
    password_hash       VARCHAR(512),
    credential_version  BIGINT NOT NULL DEFAULT 0,
    account_status      VARCHAR(32) NOT NULL,
    password_updated_at TIMESTAMP WITH TIME ZONE,
    hash_upgraded_at    TIMESTAMP WITH TIME ZONE
);
~~~

The SQL above is an **illustrative PostgreSQL-style schema**; real projects must include unique constraints/foreign keys, nullability policies, and proper account status definitions. Use a column wide enough for target hashes, ensure the DB never silently truncates, and never alter the casing of base64 or prefixes. Hash strings must be stored and read back **verbatim**.

In multi-tenant systems, an account ID may only be unique within a tenant; updates must key on `(tenant_id, account_id)`. A username/email sent by the browser is **not** sufficient as a password update key; use a stable ID resolved by the repository.

## 6. How Spring Security Recognizes Multiple Hashes with DelegatingPasswordEncoder

`DelegatingPasswordEncoder` uses the format:

~~~text
{id}encodedPassword

{bcrypt}$2a$10$...         -> bcrypt cost 10
{bcrypt}$2a$12$...         -> bcrypt cost 12
{pbkdf2-v1}...             -> legacy PBKDF2 verifier
{argon2id-v2}...           -> new Argon2id verifier
~~~

`idForEncode` determines the algorithm for **new writes**; the `id -> PasswordEncoder` map determines the algorithm for **reading/verifying**. When legacy data carries an `id` different from the current id, `upgradeEncoding` can return true. When the ID matches yet the work factor is lower, the corresponding encoder can request an upgrade.

### Illustrative Spring Security 6 Configuration: Raising Bcrypt Cost

~~~java
package example.migration;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.DelegatingPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration
public class PasswordEncodingConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        // 12 is an example, not the optimal cost for every system.
        return new DelegatingPasswordEncoder(
                "bcrypt",
                Map.of("bcrypt", new BCryptPasswordEncoder(12)));
    }
}
~~~

Given a `{bcrypt}$2a$10$...` record, the encoder uses bcrypt to verify the password. When the user enters the right password, `upgradeEncoding` detects that the old cost is lower than the new configuration and requests a rehash. The new hash uses the current cost and a fresh salt, still carrying the `{bcrypt}` prefix.

**The configuration above DOES NOT support** a `$2a$10$...` record lacking `{bcrypt}` or an unmapped `{pbkdf2-v1}` record. When migrating multiple algorithms, you must provide an exact v1 verifier (including salt layout, pepper, iterations, Unicode policy), rather than merely adding an ID and using the wrong default factory.

### Mistake: Arbitrary Fallback for Unknown IDs

By default `DelegatingPasswordEncoder` errors on missing prefixes or unmapped IDs. You can configure `setDefaultPasswordEncoderForMatches`, but broad fallbacks—especially `NoOpPasswordEncoder` or "try every algorithm"—risk opening unintended authentication paths. Better practice:

1. Validate and label legacy records in a controlled manner via DB metadata/format checks.
2. Register only explicitly verified legacy verifiers.
3. Unknown hash ID: fail closed, alert, and route the account to recovery if unrecognizable.
4. Never accept plaintext passwords stored in the DB under any arbitrary ID.

## 7. Two Upgrade Hooks in Spring

Core APIs:

~~~java
String encode(CharSequence rawPassword);
boolean matches(CharSequence rawPassword, String storedHash);
boolean upgradeEncoding(String storedHash);
~~~

`PasswordEncoder.matches(...)` **proves** the entered password matches the current encoded password. `PasswordEncoder.upgradeEncoding(...)` only **decides** whether the hash needs rehashing; it does not write to the DB itself. `encode(rawPassword)` generates the new hash from the verified raw password.

`DaoAuthenticationProvider` can use both settings below:

~~~java
provider.setPasswordEncoder(encoder);
provider.setUserDetailsPasswordService(passwordService);
~~~

`UserDetailsPasswordService.updatePassword(UserDetails user, String newPassword)` receives the **already-encoded `newPassword`**, must replace the hash in the persistent store, and must return the updated `UserDetails`.

**Easy-to-miss detail:** If a developer raises `BCryptPasswordEncoder` from cost 10 to 12 without configuring `UserDetailsPasswordService`, the provider will keep verifying cost-10 hashes **forever** without ever writing new hashes. Write tests proving the DB actually updates. If you configure a custom `AuthenticationProvider` or JSON login outside `DaoAuthenticationProvider`, this automatic logic may not be invoked.

## 8. Authentication and Rehash Flow in a Web Application

~~~text
POST /login over TLS
   |
   +-- CSRF (if browser form), rate limit, session safeguards
   |
   v
AuthenticationManager -> DaoAuthenticationProvider
   |
   +-- UserDetailsService loads account + version + storedHash
   |
   +-- Check account status: enabled, locked, expired
   |
   +-- PasswordEncoder.matches(raw, storedHash)
           |-- false -> BAD_CREDENTIALS; DO NOT rehash
           |
           +-- true -> check upgradeEncoding(storedHash)
                             |-- false -> normal authentication
                             |
                             +-- true:
                                   newHash = encode(raw)
                                   UserDetailsPasswordService.updatePassword(
                                        user, newHash)
                                   DB CAS oldHash/version -> newHash
                                   return updated UserDetails
   |
   +-- MFA if configured, session persistence, success handling
~~~

Never pass passwords into an `AuthenticationSuccessHandler` or event listener just to rehash. Spring may have already erased credentials from `Authentication`; handlers are not the place to hold secrets. Never log or cache passwords to rehash later in the background.

**MFA:** A successful password provider may upgrade the hash **before** TOTP/WebAuthn completes in a multi-factor flow. That **does not** prove MFA succeeded or justify granting a full session. If a product requires rehashing only after MFA, design a separate flow with explicit trust boundaries and password lifecycles—never store plaintext in the session.

## 9. CAS: Never Let a Lazy Upgrade Overwrite a Password Reset

The hardest race involves an authentication holding a stale snapshot:

~~~text
10:00:00 Login A reads hash=H_old, credential_version=7
10:00:01 Password reset B writes hash=H_reset, version=8
10:00:02 Login A verifies old password matches H_old
10:00:03 Login A rehashes old password -> H_upgraded_old
10:00:04 UPDATE account SET hash=H_upgraded_old WHERE account_id=A
Wrong result: old password is restored even though the user already reset it!
~~~

**Never use** an unconditional update by account ID. Use compare-and-swap inside a transaction:

~~~sql
UPDATE account_credentials
SET password_hash = :new_encoded_hash,
    credential_version = credential_version + 1,
    hash_upgraded_at = CURRENT_TIMESTAMP
WHERE tenant_id = :tenant_id
  AND account_id = :account_id
  AND password_hash = :expected_old_hash
  AND credential_version = :expected_version
  AND account_status = 'ACTIVE';
~~~

- **1 row updated**: upgrade succeeded.
- **0 rows updated**: password/status/version changed; refuse to overwrite and handle the conflict per policy.
- **DB timeout/exception**: infrastructure error, not wrong password; do not falsely increment lockout counters.
- **Transaction rollback**: never report upgraded if the DB did not commit.

**Why check both version and hash?** If every password reset/change increments `credential_version`, the version blocks stale writes; the expected hash adds a guard preventing accidental updates if code elsewhere forgot to bump the version. Ensure account status has corresponding guard conditions.

### Two Concurrent Valid Logins

~~~text
Login 1 reads H_old/v3, verifies match, encodes H1 with salt1.
Login 2 reads H_old/v3, verifies match, encodes H2 with salt2.
Login 1 CAS succeeds -> H1/v4.
Login 2 CAS 0 rows -> must not write H2 via an unconditional update.
~~~

This may simply be a **benign race**, or it could be a password reset from another actor. When you cannot tell them apart, the conservative policy is to **return a retry request** and reload the current credential to re-verify, rather than issuing a session from a stale snapshot. If metadata distinguishes a reset from a competing rehash, a finer-grained path can be designed, provided you prove it cannot resurrect old passwords.

**Never hold a DB row lock while running bcrypt/Argon2**: hashing is CPU-intensive; compute outside the transaction and then CAS on the version inside a short transaction.

## 10. Integrating UserDetailsPasswordService with the Data Store

This is a **code fragment for a Spring project**, using a repository interface and versioned app principal. It is not a standalone `javac` file; the DB implementation must provide an atomic update.

~~~java
package example.migration;

import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsPasswordService;

public final class CasPasswordUpgradeService
        implements UserDetailsPasswordService {

    private final PasswordHashStore store;

    public CasPasswordUpgradeService(PasswordHashStore store) {
        this.store = store;
    }

    @Override
    public UserDetails updatePassword(UserDetails user, String newPassword) {
        if (!(user instanceof VersionedUserDetails principal)) {
            throw new AuthenticationServiceException(
                    "Unversioned account cannot be upgraded");
        }

        int rows = store.replaceIfCurrent(
                principal.accountId(),
                principal.credentialVersion(),
                principal.getPassword(),
                newPassword);
        if (rows != 1) {
            throw new AuthenticationServiceException(
                    "Credential state changed; retry authentication");
        }

        return principal.withPasswordAndVersion(
                newPassword, principal.credentialVersion() + 1);
    }

    public interface PasswordHashStore {
        int replaceIfCurrent(String id, long expectedVersion,
                String oldHash, String newEncodedHash);
    }

    public interface VersionedUserDetails extends UserDetails {
        String accountId();
        long credentialVersion();
        UserDetails withPasswordAndVersion(String encoded, long newVersion);
    }
}
~~~

**What this code guarantees:**

- `newPassword` is **the new hash string already generated by PasswordEncoder**, not the raw password. Do not hash `newPassword` a second time.
- `replaceIfCurrent` must execute CAS in the DB for the exact account/tenant/status; the demo interface uses a single ID, while a real repository must include tenant scope when applicable.
- If 0 rows are affected, throw a service exception so you **never grant session success from a stale credential** under a conservative policy.
- `withPasswordAndVersion` must preserve account status and authorities accurately; never auto-enable a user when updating a hash.
- Never log the new hash, `oldHash`, passwords, sensitive SQL bind params, or `Authentication.toString()`.
- If an account is disabled mid-verification, update the hash only if policy allows and freshness was checked; already-issued sessions may also require revocation/freshness checks.

### Wiring into DaoAuthenticationProvider

~~~java
package example.migration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration
public class LoginProviderConfiguration {

    @Bean
    DaoAuthenticationProvider daoProvider(
            UserDetailsService users,
            PasswordEncoder encoder,
            CasPasswordUpgradeService passwordUpgrade) {
        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        provider.setUserDetailsPasswordService(passwordUpgrade);
        return provider;
    }
}
~~~

In a real application, register `CasPasswordUpgradeService` (for instance via `@Service`) and the CAS repository bean, and wire the provider into `SecurityFilterChain`. Never register an extra username/password provider that skips migration or uses an old encoder, creating an accidental bypass. Specific Spring Boot/Security versions must be pinned by a compatible BOM.

## 11. Standalone Java 17: Rehashing Only After a Valid Password

This program simulates a store and transition mechanism:

- The **legacy fixture** hash uses unsalted SHA-256 **strictly to illustrate an insecure legacy format**; never generate new hashes this way.
- The new hash uses PBKDF2-HMAC-SHA256 with a 16-byte salt from SecureRandom and 600,000 iterations **for illustration**; benchmark if a real app uses PBKDF2.
- Wrong passwords leave the store untouched; the first valid login upgrades the hash; subsequent valid logins do not upgrade again.
- A stale CAS after a reset is rejected, and the old password is not re-accepted.
- Never print passwords or digests; stdout only prints booleans/statuses.

File `PasswordMigrationDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import java.util.HexFormat;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public final class PasswordMigrationDemo {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final int ROUNDS = 600_000;
    private static final String LEGACY = "{legacy-sha256}";
    private static final String MODERN = "{pbkdf2-v2}$";

    static String oldHashForTest(String raw) throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(raw.getBytes(StandardCharsets.UTF_8));
        return LEGACY + HexFormat.of().formatHex(digest);
    }

    static byte[] derive(String raw, byte[] salt, int rounds)
            throws Exception {
        char[] chars = raw.toCharArray();
        PBEKeySpec spec = new PBEKeySpec(chars, salt, rounds, 256);
        try {
            return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
                    .generateSecret(spec).getEncoded();
        } finally {
            spec.clearPassword();
            Arrays.fill(chars, '\0');
        }
    }

    static String modernHash(String raw) throws Exception {
        byte[] salt = new byte[16];
        RANDOM.nextBytes(salt);
        return MODERN + ROUNDS + "$"
                + Base64.getEncoder().encodeToString(salt) + "$"
                + Base64.getEncoder().encodeToString(
                        derive(raw, salt, ROUNDS));
    }

    static boolean matches(String raw, String stored) throws Exception {
        if (stored.startsWith(LEGACY)) {
            byte[] expected = HexFormat.of()
                    .parseHex(stored.substring(LEGACY.length()));
            byte[] actual = MessageDigest.getInstance("SHA-256")
                    .digest(raw.getBytes(StandardCharsets.UTF_8));
            return MessageDigest.isEqual(expected, actual);
        }
        if (!stored.startsWith(MODERN)) {
            return false;
        }
        String[] f = stored.split("\\$", -1);
        if (f.length != 4) {
            return false;
        }
        int rounds = Integer.parseInt(f[1]);
        if (rounds < 100_000 || rounds > 2_000_000) {
            return false;
        }
        byte[] salt = Base64.getDecoder().decode(f[2]);
        byte[] expected = Base64.getDecoder().decode(f[3]);
        if (salt.length != 16 || expected.length != 32) {
            return false;
        }
        return MessageDigest.isEqual(
                expected, derive(raw, salt, rounds));
    }

    static final class Store {
        private String hash;

        Store(String hash) {
            this.hash = hash;
        }

        synchronized String read() {
            return hash;
        }

        synchronized boolean cas(String expected, String next) {
            if (!hash.equals(expected)) {
                return false;
            }
            hash = next;
            return true;
        }
    }

    static String login(Store store, String password)
            throws Exception {
        String previous = store.read();
        if (!matches(password, previous)) {
            return "DENIED";
        }
        if (previous.startsWith(LEGACY)) {
            String next = modernHash(password);
            return store.cas(previous, next)
                    ? "AUTHENTICATED_AND_UPGRADED"
                    : "RETRY_REQUIRED";
        }
        return store.read().equals(previous)
                ? "AUTHENTICATED"
                : "RETRY_REQUIRED";
    }

    public static void main(String[] args) throws Exception {
        Store store = new Store(oldHashForTest("demo-secret"));
        System.out.println("initial legacy: " +
                store.read().startsWith(LEGACY));
        System.out.println("wrong password: " +
                login(store, "wrong"));
        System.out.println("first correct: " +
                login(store, "demo-secret"));
        System.out.println("modern now: " +
                store.read().startsWith(MODERN));
        System.out.println("second correct: " +
                login(store, "demo-secret"));

        String stale = store.read();
        store.cas(stale, modernHash("reset-secret"));
        System.out.println("stale CAS accepted: " +
                store.cas(stale, modernHash("demo-secret")));
        System.out.println("old after reset: " +
                login(store, "demo-secret"));
        System.out.println("new after reset: " +
                login(store, "reset-secret"));
    }
}
~~~

Compile and run with JDK 17+ (no Spring required):

~~~bash
javac PasswordMigrationDemo.java
java PasswordMigrationDemo
~~~

**Exact stdout** regardless of the random salt:

~~~text
initial legacy: true
wrong password: DENIED
first correct: AUTHENTICATED_AND_UPGRADED
modern now: true
second correct: AUTHENTICATED
stale CAS accepted: false
old after reset: DENIED
new after reset: AUTHENTICATED
~~~

**Explanation:** New hashes differ on every encode due to the random salt, yet `matches` reads the salt/iterations stored alongside the digest so the right password still matches. `stale CAS accepted: false` proves an upgrade starting from a stale snapshot cannot overwrite a reset.

**Limitations of the demo:**

- Legacy SHA-256 is generated strictly in the fixture to simulate weak data; **never use it** in new systems.
- The store lives in a single JVM and CAS compares hash strings; production needs DB transactions with credential versions, account/tenant IDs, and statuses.
- The sample parser does not catch all malformed formats/`NumberFormatException`/Base64 errors; real adapters must validate/handle errors fail-closed and never turn parse errors into authenticated states.
- Does not cover HTTP, MFA, sessions, rate limits, IdP credential resets, or authorization; the demo does not replace `DaoAuthenticationProvider`.
- `PBEKeySpec.clearPassword` shortens the lifetime of the `char[]` copy, though the input Java `String` password can linger on the heap. Never write it to logs/queues or retain it for background jobs.
- Reading the version after verification only narrows the race in a simplified model; production must enforce state/freshness in transactions and session issuance per policy.

## 12. Prefixless Old Hashes: Labeling Procedure Without Raw Passwords

Suppose DB rows store bcrypt `$2a$10$...` while `DelegatingPasswordEncoder` expects `{bcrypt}$2a$10$...`. If you know with certainty from metadata and format that it is bcrypt, you can prepend the prefix in the DB **without altering the digest**:

~~~sql
-- Illustrative PostgreSQL; not a standalone production script.
UPDATE account_credentials
SET password_hash = '{bcrypt}' || password_hash
WHERE hash_scheme = 'BCRYPT'
  AND password_hash LIKE '$2%'
  AND password_hash NOT LIKE '{bcrypt}%';
~~~

Before running it:

1. Dry run, count affected rows, and verify exact bcrypt structure/cost/version.
2. Back up/canary; avoid long table locks by batching by PK.
3. **Expand readers** first: old and new nodes must verify both prefixed and unprefixed forms so undeployed pods cause no login outage.
4. Never rely on string length or `LIKE '$2%'` alone as proof of valid format.
5. Verify exact readback, both format and collation, without double-prefixing.
6. Once prefixed, bcrypt cost is still low; lazy rehash will raise the cost on the next valid login.

If you choose an adapter that adds a "virtual" prefix on read, you must **preserve the raw DB hash for CAS**. Using the virtually prefixed value in `WHERE password_hash=:expected_hash` will fail to match the DB value and cause upgrades to fail forever. You can store `storedHashRaw`/scheme/version in a custom UserDetails and ensure the repository matches the exact stored record.

Never turn unknown hashes into `{noop}` or assume plaintext. When the legacy schema is unknown, use recovery rather than opening an overly permissive verifier.

## 13. Registration, Password Change, and Reset Must Write with the New Scheme

Lazy upgrade is a **supplementary path** for old hashes. Operations creating new passwords must use the current encoder immediately:

- Local password registration.
- Password changes when authenticated and policy requires reauthentication.
- Setting a password via a short-lived, single-use, rate-limited reset token with owner verification.
- Admin provisioning of a temporary credential via a dedicated workflow if policy permits.
- Enabling a local password for an account that previously used only OIDC/SSO.

Password reset/change workflow:

~~~text
Verified user / verified recovery token / MFA (per risk)
   -> password policy & breached-password check
   -> currentEncoder.encode(newRawPassword)
   -> UPDATE password_hash + credential_version atomically
   -> audit PASSWORD_CHANGED/RESET (never log hash)
   -> session/refresh-token/remember-me invalidation per policy
~~~

Never use cached old passwords or support-known passwords to "reset everyone". Never store extra copies of weak hashes in a `legacy_backup` column for rollback unless governed by a strictly protected, time-bounded backup workflow; leftover weak hashes are an attack target.

If a user resets while an old login is rehashing, CAS must guarantee the old password **cannot come back to life**. After a reset, test both that logging in with the old password is rejected and logging in with the new password succeeds.

## 14. Inactive Accounts: The Hard Limit of Lazy Migration

Users who do not sign in **never enter their password**, so the system cannot upgrade their hashes from one-way data. Therefore, you cannot claim "100% upgraded with zero resets" for dormant users, unrecognized hashes, or lost legacy peppers.

| Cohort | Strategy |
| --- | --- |
| Regularly active users | Upgraded on first valid login with zero UX change |
| Long-lived remember-me users | Require fresh password reauthentication when needed per policy |
| Users inactive for months | Track cohorts and sunset milestones, avoiding immediate mass resets |
| Very weak or suspected leaked legacy hashes | Prioritize reset/recovery even with UX impact |
| Unknown format / lost legacy pepper | Cannot verify safely; guide through verified recovery |
| LDAP/SSO-only without local password | Out of scope for local hash migration |
| Service accounts / headless clients | Rotate secrets or adopt workload identity; do not wait for interactive login |
| Disabled/expired accounts | Never re-enable just to rehash |

Set a **sunset date** based on risk, legal/policy requirements, and activity windows; past that date, accounts still holding weak hashes can be forced through recovery **when they return**, rather than emailing "everyone must change today". Never promise zero resets if the legacy scheme is already compromised.

**Avoid phishing:** Migration notices must never ask users to email passwords or follow unfamiliar login links. When reauthentication is needed, direct users to official domains/channels without exposing account existence.

## 15. Bcrypt Input Length, Unicode, Pepper, and Compatibility Policies

- Standard bcrypt truncates password input around **72 bytes**; long Unicode strings can exceed that byte limit. When moving from bcrypt to another algorithm, the password entered during the upgrade becomes the full input to the new scheme; evaluate users who previously had suffixes ignored by bcrypt.
- Do not automatically `trim` leading/trailing spaces or lowercase passwords if the old version did not do so.
- Never change Unicode normalization/charset during migration without test vectors, especially if the previous system pre-hashed on the client.
- Legacy peppers can make hashes unverifiable if keys are lost. Never skip the pepper or substitute the wrong pepper and still allow authentication.
- Pepper rotation typically requires a fresh password entry; stored hashes cannot "swap peppers" offline without the raw password.
- Never allow DB collations or ORM mappings to fold casing on stored hashes; base64 and prefixes are case-sensitive.
- Do not immediately purge existing sessions just because a user logged in with a weak hash unless policy requires it: mass session invalidation can trigger an availability incident. If compromise is evidenced, session revocation is an incident-response decision.

**Combining with MFA:** Having the password factor verified and rehashed does not mean the user cleared TOTP/WebAuthn; protected routes requiring full MFA must remain blocked. Never use an OTP or JWT as input to upgrade a local password hash.

## 16. Logins Outside DaoAuthenticationProvider

Multiple login entry points exist:

| Mechanism | Is a raw local password verified? | Recommended Handling |
| --- | --- | --- |
| Spring form login + DaoAuthenticationProvider | Yes | Register `UserDetailsPasswordService` for auto-upgrade |
| Custom JSON login with AuthenticationManager | Yes, if using the proper provider | Verify auto-upgrade is triggered |
| Custom-written AuthenticationProvider | Possibly | Must wire `matches/upgradeEncoding/CAS` safely |
| LDAP BindAuthenticator / Active Directory | Does not own password hashes in app DB | Directory owns password policy |
| OAuth2/OIDC/SAML login | No | Never hash ID tokens/subjects as local passwords |
| Passkey/WebAuthn | No local password in flow | Manage public key credentials separately |
| Remember-me cookie | No | Never use cookies to derive raw passwords |
| Stateless JWT/Bearer requests | No | Separate token validation; never runs password rehash |
| Password reset with new password | Yes, newly created | Current encoder directly, not lazy upgrade |

In systems with multiple `SecurityFilterChain` beans, verify form/API login uses the right provider bean. If a custom filter sets `SecurityContextHolder` directly and bypasses `AuthenticationManager`, policies for account state, password upgrades, compromised passwords, auditing, or MFA may be skipped.

## 17. Migration Costs on CPU, RAM, and Latency

A legacy user's first login performs **two KDF operations** instead of one: verifying the old hash, then encoding the new hash. Going from bcrypt cost 10 to cost 12 can significantly spike CPU on that first login (plus the SQL CAS), while subsequent logins only verify the new hash.

~~~text
Before rollout:
  login -> verify bcrypt(cost=10) -> session

First login after rollout:
  login -> verify bcrypt(cost=10)
        -> encode bcrypt(cost=12)
        -> UPDATE CAS
        -> session

Subsequent logins:
  login -> verify bcrypt(cost=12) -> session
~~~

Run **real** load benchmarks with login bursts, especially if a deployment forces users to sign in again or expires sessions together. Risk mitigations:

- Independent rate limits per account and IP/network, plus global edge quotas.
- Bound concurrent hashing operations (bulkhead); budget memory explicitly for Argon2id.
- Emit duration/p95/p99 metrics for verify, upgrade, and DB CAS; never record passwords/hashes.
- Canary rollouts and a feature flag that can **pause upgrades** under overload while still verifying both new and old hashes.
- Do not arbitrarily downgrade the new KDF under overload; preserve the write-new policy per risk decisions.
- Never retry rehashes infinitely on CAS conflicts, and never hold transaction locks while hashing.
- Never batch hundreds of thousands of accounts into a background job reading passwords from caches/logs.

**Note:** Spring's `PasswordEncoderFactories.createDelegatingPasswordEncoder()` provides default mappings for compatibility, which does not mean default parameters represent optimal security targets across all years. Use explicit, benchmarked configurations with an update plan.

## 18. Rolling Deployment and Rollback Without Breaking Logins

With two versions running concurrently, the new writer **must never emit hashes that old readers cannot understand**. Compatibility roadmap:

1. **Expand schema:** Ensure hash column is long enough, with version/metadata and indexes ready.
2. **Expand readers:** Release code capable of verifying all old and new schemes across every pod/region, without writing the new scheme yet while unsupported old nodes remain.
3. **Verify mixed fleet:** Test the same account across node A and node B sequentially, covering sign-in, reset, and change paths.
4. **Switch writer:** Enable the current encoder for new passwords, then roll out lazy rehash by cohort/canary.
5. **Observe:** Monitor upgrade successes, unknown IDs, CAS conflicts, CPU, DB writes, and login failures.
6. **Contract:** After dormant accounts are handled, disable legacy verifiers per deadline and release policy.

**Rollback:** If the older version cannot verify new hashes, a full rollback after upgrades begin can cause a login outage. Maintain a **compatible rollback reader** or keep new-hash verification in the recovery release. Never restore old hashes from backup to "undo" upgrades for users who changed passwords, as that can resurrect old passwords.

Especially for batch-prefixing `{bcrypt}`, ensure both old and new app versions understand the prefix during node-by-node rollouts. Raising bcrypt cost normally keeps the same bcrypt format, yet you must test older library versions rather than assuming universal compatibility unconditionally.

## 19. Observability, Auditing, and Success Metrics

| Metric/category | Purpose |
| --- | --- |
| `password_hash_inventory{scheme,cost_bucket}` | Track legacy vs. current ratio |
| `password_upgrade_attempts_total{scheme}` | Valid authentications needing upgrade |
| `password_upgrade_success_total{scheme}` | Successful CAS updates |
| `password_upgrade_conflict_total` | 0-row CAS conflicts |
| `password_upgrade_error_total{reason}` | DB errors, unsupported schemes, malformed hashes |
| `password_upgrade_duration_seconds` | Rehash latency |
| `login_results_total{outcome}` | Bad credentials, locked, disabled, infra error |
| `password_reset_change_total{method}` | All new write paths |
| `legacy_inactive_accounts_bucket` | Accounts needing recovery at sunset |

Names above are illustrative, not built-in Spring metrics. **Never use user ID, email, raw hash, token, session ID, IP, or password as metric labels** due to privacy and cardinality. Separate audit logs can record event ID, pseudonymized account ref, before/after scheme, version, UTC time, CAS result, and request ID under RBAC/retention—never logging actual hashes.

Alert when: login failures spike post-deploy; legacy counts stop dropping despite valid logins; mass CAS conflicts occur; KDF p99 latency spikes abnormally; DB truncation happens; unknown hash IDs climb; or upgrades must be disabled due to saturation. These signals surface misconfigurations before an unintended system-wide lockout occurs.

## 20. Automated Test Matrix

### PasswordEncoder Tests

- [ ] Correct password against legacy hash -> `matches=true` and `upgradeEncoding=true`.
- [ ] Wrong password -> `matches=false`, zero writes.
- [ ] Older low-cost bcrypt still verifies under new-cost encoder and flags upgrade.
- [ ] Current hash verifies cleanly with `upgradeEncoding=false`, no endless rehashing.
- [ ] Two encodes of the same password use different salts; both verify.
- [ ] Unknown ID / malformed hash fails closed without `NoOp` fallback.
- [ ] Legacy prefix/metadata matches exact DB format with no double-prefixing.
- [ ] Unicode, whitespace, long passwords, byte lengths, and peppers pass test vectors.
- [ ] Hash column round-trips without truncation, case-folding, or encoding corruption.

### Spring Security Integration

- [ ] DaoAuthenticationProvider uses the proper `PasswordEncoder`/`UserDetailsPasswordService`.
- [ ] Valid legacy login -> persists new hash and increments credential version; next login does not upgrade.
- [ ] Wrong password or locked/disabled/expired/unknown account -> writes no new hash.
- [ ] New registrations/changes/resets always produce the current scheme.
- [ ] CAS conflict from a password reset between matches and update: **never overwrites the reset**, never issues a stale session.
- [ ] Two concurrent valid logins: only one CAS succeeds, conflict handled safely.
- [ ] DB exceptions during upgrade are not misclassified as wrong passwords or increment lockout counters.
- [ ] With MFA logins, password upgrade does not let the user reach MFA-protected routes before verification completes.
- [ ] Custom API logins / multiple providers do not bypass the policy.
- [ ] After hash migration, the same user can log in via both compatible old pods and new pods.

### Storage, Load, and Operations

- [ ] Repository CAS checks row count and version inside a transaction, verifying tenant/status.
- [ ] UserDetails cache invalidates/reloads properly after upgrade instead of serving the old hash indefinitely.
- [ ] DB outages, rollbacks, duplicate requests, lost writes, and read-replica lag never yield false successes.
- [ ] p95/p99 authentication cost, CPU, memory, pools/threads, and DB lock times under burst load.
- [ ] Canary/feature flag disables rehashing without disabling verification of new hashes.
- [ ] Post-sunset, unmigrated legacy accounts are forced into recovery rather than weak fallback.
- [ ] Rollback code remains compatible with newly written hashes and never restores weak hashes.

## 21. Runbook When Rollout Goes Wrong

**Symptom: many users report valid passwords failing to log in.**

1. Check `hash_scheme`/prefix distribution and error categories: unknown `{id}`, bad credentials, malformed hash, DB outage, or CAS conflict.
2. Reproduce with **test accounts** for each scheme; never ask users to email passwords.
3. Verify all nodes can read current hashes; does the rolling deployment still have legacy-only nodes?
4. Inspect column length, encoding, ORM mapping, legacy PBKDF2 salt/pepper, and work factor.
5. If CAS updates fail, inspect version/status/races with password resets—never switch to an unconditional UPDATE.
6. If latency/CPU spikes, throttle traffic/canary and pause auto-upgrade if policy allows; **still keep the current encoder for new passwords**.
7. Never log raw credentials/hashes to debug; log reason codes and pseudonymized IDs.
8. Test the rollback reader before deploying, and monitor login outcomes after remediation.

**Symptom: legacy hash count is not decreasing.**

- Verify `DaoAuthenticationProvider.setUserDetailsPasswordService` is wired on the active bean and right filter chain.
- Verify `upgradeEncoding` actually returns true for test legacy hashes.
- Check whether a custom UserDetailsService exposes the right hash ID/cost and whether CAS matches the real DB value.
- Check whether repository transactions commit, versions/row counts update, and caches go stale.
- Account for inactive users: you cannot promise migration if passwords are never entered.
- Never re-enable legacy write paths just to "keep numbers moving" during an incident.

## 22. Transition Plan for an Example System

Assumed inventory (illustrative numbers only):

~~~text
45% {bcrypt} cost 12
40% {bcrypt} cost 10
15% {pbkdf2-v1} legacy
~~~

**Rollout week 1:** Standardize schema, validate the PBKDF2 v1 verifier with test vectors, and roll out all readers supporting all three formats. Test across pods with a compatible rollback ready.

**Canary phase:** Enable the current writer for new accounts/resets/changes; route a small percentage of traffic to lazy upgrades. Verify 1 valid login upgrades the hash, 1 invalid login leaves the DB untouched, every CAS checks version, and the next login does not rehash again.

**Expansion phase:** Ramp up traffic as p99/CPU/CAS/DB metrics stay within budget, keeping anti-bot protections and bulkheads active. Legacy weak-hash accounts upgrade gradually through real logins. Watch for regressions across browser forms, APIs, MFA, and user caches.

**Dormant phase:** Segment long-inactive users; send official notices and design reset/recovery upon return based on the legacy hash's risk. Never open a "password fallback" to avoid resets.

**Retirement phase:** Set a cutoff to drop weak verifiers, test recovery and support impact, then remove old parsers/secrets. Audit logs to verify no hashes leaked, and purge old backups/caches per retention and legal policies.

**Accurately communicating the outcome:** The goal is **avoiding forcing everyone to change passwords simultaneously**, not guaranteeing every record upgrades offline. Inactive accounts may still require a reset when reactivated past the sunset date.

## 23. Common Mistakes and Checklist

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Rehashing `oldHash` itself | Users can no longer verify their passwords | Rehash only the raw password after `matches` |
| Switching writer before all readers support the new format | Logins fail depending on pod/region | Expand readers first |
| Unknown prefix falls back to plaintext | Credential bypass | Whitelist schemes, fail closed |
| Saving new hash without bumping version | CAS fails to block concurrent resets | Increment version on every secret change |
| UPDATE by account ID without expected hash | Old password overwrites password reset | CAS on expected hash/version/status |
| Granting login with stale user on CAS conflict | Security breach after reset/disable | Safe retry/re-verification |
| Failing to configure UserDetailsPasswordService | Old hashes persist forever | Wire into provider, test DB readback |
| Treating `newPassword` from service as raw | Double-hashed or secret leak | `newPassword` in the service is already encoded |
| Picking a very high bcrypt cost without benchmarking | Login CPU saturation/DoS | Canary, rate limits, p99/peak load tests |
| Background job upgrading hashes from password cache | Severe secret exposure | Upgrade strictly inside auth trust boundary |
| Migrating local hashes during SSO login | No raw local password exists | Do not do this; manage at IdP |
| Deleting legacy verifiers immediately | Dormant users locked out | Cohort sunset + recovery |
| Keeping legacy verifiers forever | Risk reduction never finishes | Set deadlines and ownership |
| Rolling back with old hashes from backup | Can resurrect reset passwords | Compatible rollback reader |
| Putting hashes/usernames into metrics | Data leak and cardinality explosion | Aggregate metrics, RBAC-protected audits |
| Changing `trim`/UTF-8 handling unexpectedly | User passwords stop verifying | Preserve policy, verify with test vectors |
| Forgetting password reset / alternate write paths | Keeps writing old hashes | Inventory every create/change/reset path |

**Implementation checklist:**

- [ ] Inventory exact legacy schemes/params, current schemes/params, and account types.
- [ ] Accurate prefixes/metadata, sufficiently wide columns, safe DB collation.
- [ ] `DelegatingPasswordEncoder` configured with legacy mappings and current writer; unknown IDs fail closed.
- [ ] `DaoAuthenticationProvider` wires `setUserDetailsPasswordService` on the active filter chain.
- [ ] Repository CAS checks account/tenant/version/oldHash/status; tested against reset races and concurrent logins.
- [ ] Wrong passwords and disabled/locked/unknown users trigger zero updates.
- [ ] Registration/reset/change produce current hashes; password resets cannot be overwritten by stale rehashes.
- [ ] No raw passwords retained in logs/queues/caches, no hashes exported to metrics.
- [ ] Benchmarked work factors, concurrency, rate limits, p99, and DB cost, with canary and rollback ready.
- [ ] All reader nodes/versions are compatible before enabling the new writer.
- [ ] Plan exists for dormant users and legacy sunset; recovery tested for inactive users.
- [ ] MFA, SSO, remember-me, and token flows are never assumed to supply raw passwords.
- [ ] Integration/chaos/rollback QA passed, and audits leak zero credentials.

**Conclusion:** Upgrading hashes without forcing everyone to reset at once means **verify legacy hash → check `upgradeEncoding` → compute new hash from just-verified raw password → CAS update the exact credential**. Spring Security supplies `DelegatingPasswordEncoder`, `DaoAuthenticationProvider`, and `UserDetailsPasswordService`, while your application must complete transactions, versioning, caching, rollout, observability, and recovery. It is a controlled transition as users return, **not a bulk hash transformation without knowing passwords**.

## Official References

- [Spring Security 6.5 — Password Storage and DelegatingPasswordEncoder](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security — UserDetailsPasswordService API](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/core/userdetails/UserDetailsPasswordService.html)
- [Spring Security — PasswordEncoder interface](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/crypto/password/PasswordEncoder.html)
- [Spring Security — BCryptPasswordEncoder API](https://docs.spring.io/spring-security/site/docs/6.5.2/api/org/springframework/security/crypto/bcrypt/BCryptPasswordEncoder.html)
- [Spring Security — Cryptography and work factor](https://docs.spring.io/spring-security/reference/6.5/features/integrations/cryptography.html)
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [NIST SP 800-63B-4 — Authentication and Authenticator Management](https://pages.nist.gov/800-63-4/sp800-63b.html)
- [Java SE 17 — PBEKeySpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/PBEKeySpec.html)
- [Java SE 17 — SecretKeyFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/SecretKeyFactory.html)
- [Java SE 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html)

# Handling Hashes Missing a Prefix or Using Disallowed Algorithms

A Spring Security application migrates from a legacy password store to `DelegatingPasswordEncoder`. Some users have `password_hash` values like `$2a$10$...` (bcrypt without `{bcrypt}`), some records use `{sha256}...` or `{noop}...`, and others carry a prefix the system does not recognize. After deployment, logins fail with an error like:

```text
java.lang.IllegalArgumentException:
There is no PasswordEncoder mapped for the id "null"
```

This **does not necessarily mean the user entered the wrong password**. Very likely the database stores a verifier lacking an algorithm identifier under the current encoder's contract. Conversely, a record with a syntactically valid `{id}` **does not mean the organization permits that algorithm**. If you fix the error by enabling `NoOpPasswordEncoder` or an arbitrary fallback for every unrecognized hash, the system may trade authentication integrity for an "error-free" login.

This article belongs to the **Password Upgrades** group of *Spring Security - authentication* and addresses two primary situations:

1. **Missing prefix or malformed format:** a hash that likely uses a valid algorithm but lacks `{id}`, has broken braces, whitespace, mismatched identifiers, or corrupted data.
2. **Disallowed algorithm:** a verifier declaring `{noop}`, `{sha256}`, an outdated/weak scheme, a scheme absent from the organization's allowlist, or cost/parameters below policy.

**Safety principle:** determine the **actual format and provenance** before fixing; prepend `{id}` only when the algorithm is proven; never try to decrypt/re-hash passwords without the raw password; reject/reset passwords for dangerous or unknown formats; if temporary transition support is needed, tightly constrain legacy types and **upgrade after a successful authentication**.

Examples use **Java 17+, Spring Security Crypto 6.5.x, and Gradle**. They include a runnable standalone program with commands and deterministic boolean stdout; subsequent Spring Boot/provider/SQL configurations are clearly marked as integration samples, not a complete application without wiring to a user store.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Read the `{id}encodedPassword` storage format, distinguishing `idForEncode` from the `idToPasswordEncoder` list permitted for *matches*.
2. Explain the cause of `id=null`, unmapped `id`s, and the difference between configuration/format exceptions and password mismatches.
3. Understand why `PasswordEncoderFactories.createDelegatingPasswordEncoder()` carries mappings for legacy algorithms, yet **is not the organization's allowlist**.
4. Build a `DelegatingPasswordEncoder` with an explicit allowlist (e.g., policy-compliant bcrypt only), avoiding `NoOp` fallbacks.
5. Repair unprefixed bcrypt records only after accurately verifying algorithm and provenance; distinguish **adding metadata** from **strengthening hashes**.
6. Build an online legacy migration strategy: verify raw password under a known scheme → encode with the new scheme → persist safely → narrow/remove the old scheme.
7. Know when to force a password reset or quarantine records instead of guessing algorithms from untrusted data.
8. Design tests that reject out-of-policy algorithms, prevent downgrades, and ensure users do not hit unnecessary HTTP 500 errors.

## 2. Four Concepts You Must Not Confuse

| Term | Meaning | Example |
| --- | --- | --- |
| **Raw password** | Secret entered by the user during login/password change, existing only transiently. | String submitted by a login form over HTTPS. |
| **Encoded password / verifier** | Output from a salted/parameterized one-way function, used to verify passwords without storing raw values. | Bcrypt hash containing cost and salt. |
| **Algorithm identifier (`id`)** | Leading label telling Spring which `PasswordEncoder` reads the verifier. | `bcrypt` in `{bcrypt}...`. |
| **Password policy / allowlist** | Rules governing permitted algorithms, work factors, formats, and legacy allowances. | Bcrypt only with a minimum environment-specific cost. |

A prefix is **encoder-routing metadata**, not a salt and not proof of a secure hash. A low-cost bcrypt hash is still bcrypt; putting `{bcrypt}` in front of a non-bcrypt string does not turn it into a bcrypt verifier. The original password **cannot be validly recovered** from a password hash to generate new hashes offline.

### Hashing Differs from Reversible Encryption

`PasswordEncoder.encode(raw)` performs a one-way transformation, while `matches(raw, stored)` checks raw against the stored verifier. There is no `decode(stored)` for passwords. If migrating from SHA-1/MD5 to bcrypt when you only have old hashes, **you cannot simply decode and re-encode the password**. You must have the user re-supply the raw password through a valid authentication, or force a reset. Approaches like "bcrypt(MD5(password))" built on top of old hashes create a new scheme requiring careful risk analysis; do not treat it as equivalent to bcrypt directly over the password or adopt it by default.

### A "Supported" Algorithm Is Not an "Allowed" Algorithm

A library may ship encoders for legacy schemes to assist transitions. `PasswordEncoderFactories.createDelegatingPasswordEncoder()` registers more mappings than a "current bcrypt only" target; some legacy encoders exist for compatibility rather than being recommended for new passwords. System policy must explicitly decide **which scheme creates new hashes, which schemes are temporarily accepted for verification and upgrade, and which schemes are banned outright**.

## 3. How Does DelegatingPasswordEncoder Read {id}?

Spring Security uses a uniform format:

```text
{id}encodedPassword
  |        |
  |        +--> Verifier part understood by the target encoder.
  +------------> Label selecting PasswordEncoder in the mapping.
```

Examples:

```text
{bcrypt}$2a$12$......         Has bcrypt ID; remainder is the bcrypt hash.
$2a$12$......                 Shows bcrypt signs but missing {id}.
{sha256}abcdef...             Explicit ID, though policy may forbid raw SHA-256.
{noop}password                 Raw password under noop label: UNSAFE.
{unknown}abcdef...            Unmapped ID.
{BCRYPT}$2a$12$......         Wrong case if mapping only has "bcrypt".
{bcrypt}not-a-bcrypt-hash     Known ID but invalid data after prefix.
bcrypt}$2a$12$......          Malformed ID syntax.
```

The lines above merely **illustrate formatting**; `......` is not a real bcrypt verifier. A genuine bcrypt verifier contains a structured salt/hash string of the expected character count. Never copy illustrative strings into a database expecting logins to work.

### 3.1 `idForEncode` and `idToPasswordEncoder`

`DelegatingPasswordEncoder` is typically constructed via:

```java
String idForEncode = "bcrypt";
Map<String, PasswordEncoder> idToPasswordEncoder = Map.of(
        "bcrypt", new BCryptPasswordEncoder(12));

PasswordEncoder encoder = new DelegatingPasswordEncoder(
        idForEncode, idToPasswordEncoder);
```

This is a configuration snippet requiring imports for `java.util.Map` and the corresponding `org.springframework.security.crypto.password` classes. Meaning:

- `idForEncode="bcrypt"`: calling `encode(raw)` creates a new verifier with bcrypt and prepends `{bcrypt}`.
- Map contains `"bcrypt"`: calling `matches(raw, "{bcrypt}...")` routes to the BCrypt encoder.
- Without `"noop"`/`"sha256"`: those prefixes are not accepted in this configuration, even though Spring libraries include encoder classes for them.
- Legacy schemes may be allowed **only during an approved migration window**, bounded by target cohort/dataset, deadline, and removal plan.

### 3.2 PasswordEncoderFactories Is a Convenience Helper, Not a Policy Substitute

Common setup:

```java
PasswordEncoder encoder =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();
```

The factory picks an encoder for creating new hashes and registers several encoders for reading legacy formats. This helps systems transition, yet **does not replace deciding "which schemes are allowed"**. If policy bans `{noop}`/fast digests, use a custom allowlist or a policy layer checking before calling the encoder—never treat the factory's registered encoders as permission to accept every ID.

### 3.3 Branches of matches()

| Stored data | Result with strict bcrypt-only map | Reason |
| --- | --- | --- |
| `{bcrypt}` + valid bcrypt hash, right raw password | `true` | Target encoder verifies successfully. |
| `{bcrypt}` + valid bcrypt hash, wrong raw password | `false` | Credentials do not match. |
| Bcrypt hash without `{bcrypt}` | Default `IllegalArgumentException` for id `null` | No ID found at start of string. |
| `{unknown}...` | Default `IllegalArgumentException` | No mapping for the ID. |
| `{sha256}...` or `{noop}...` | Default `IllegalArgumentException` in strict map | ID excluded from allowlist. |
| `{bcrypt}` + non-bcrypt body | Typically `false`/rejected by BCrypt validator | Body invalid format or mismatch. |
| Empty/missing password verifier | Must not be used to authenticate | Corrupted data or passwordless account. |

Important note: `DelegatingPasswordEncoder` does not return `false` by default for unrecognized IDs; Spring Security docs specify **`IllegalArgumentException`**. If that exception escapes the authentication flow unhandled, the application can surface an HTTP 500 error. Never "fix" it by always accepting passwords or bypassing `matches`.

## 4. Diagnose Errors Before Changing Configuration

### 4.1 Reading the Error in Context

Classic error:

```text
There is no PasswordEncoder mapped for the id "null"
```

Usually this means the encoded verifier **does not start with a properly formatted `{...}` prefix**. It neither confirms that the password is absent nor proves the record is bcrypt. Situations that can look identical:

- Database stores bare `$2a$...` bcrypt hashes from an older application.
- The `password` column actually holds plaintext from before encoders were used.
- A migration stripped the leading character or imported data with leading whitespace.
- Accounts from LDAP/other legacy schemes that do not use the `{id}...` format.
- Reading the wrong column (e.g., username/email instead of verifier), bad string concatenation, or wrong ORM mapping.
- Some records were created by `BCryptPasswordEncoder` directly and others by `DelegatingPasswordEncoder`.

Never log full hashes or tokens while debugging; useful diagnostics include record counts, recognized prefix categories, string lengths, and standardized error codes. Hashes themselves are sensitive data because leaked hashes enable offline password cracking.

### 4.2 Distinguish Unmapped IDs from Disallowed IDs

`{sha256}...` is not necessarily "unknown" to the default factory, yet it may be **forbidden by internal security policy**. Conversely, `{external-kdf-v1}...` might be a strong scheme in another system that this app lacks a decoder/mapping for yet; you cannot assume it is safe without verification.

To diagnose accurately, separate two states:

1. **Unsupported format:** unknown ID/metadata or no deterministic way to read the scheme.
2. **Disallowed format:** known scheme/format that current policy forbids verifying with.

Both must result in **denying login** for normal requests until an appropriate remediation workflow runs. They differ only in the fix: controlled metadata/compatibility adjustment vs. resetting/migrating off a banned scheme.

### 4.3 Layer-by-Layer Quick Checks

1. **Data:** Which exact verifier column does `UserDetails.getPassword()` return? Could it have been double-encoded, trimmed/re-encoded, padded with spaces, or stripped of its prefix?
2. **Configuration:** Which `PasswordEncoder` bean is actually wired into `DaoAuthenticationProvider`? Are there custom managers/filters?
3. **Format:** Does the prefix start at character 0? Is `id` in the map? Does the bcrypt body match valid syntax?
4. **Policy:** Is that scheme allowed for new creation, temporarily verified for upgrades, or rejected?
5. **Data source:** Is it scoped by tenant/identity provider/schema/version? The same username in two tenants could pull the wrong verifier.
6. **Writes:** Do registration/reset/password-change flows call `encoder.encode(raw)`, or are they saving raw strings/hardcoding `{noop}`?
7. **Observability:** Are encoder exceptions/stack traces leaking to clients? Are rejected-login metrics broken down by format group (without raw secrets)?

## 5. Classifying Records and Deciding Actions

Practical decision table:

| Verifier shape in DB | Likely assessment | Recommended handling |
| --- | --- | --- |
| `{bcrypt}` + bcrypt hash within allowed parameters | Mapped, approved | Verify with bcrypt; check `upgradeEncoding` if policy raised work factor. |
| Bare bcrypt `$2a$...` with certain provenance | Missing `{bcrypt}` metadata | Add prefix **in a controlled way**, then consider raising cost when raw password is validly submitted. |
| Bare hash of unknown algorithm | Cannot infer accurately | Quarantine/flag for inspection; require reset if no approved legacy verification exists. |
| `{bcrypt}` with malformed body | Damaged/corrupt | Do not "guess" the body; fail closed, audit, and reset per workflow. |
| `{BCRYPT}` or typo in ID | Malformed metadata | Verify verifier origin and nature before normalizing; avoid loose case-insensitive mapping. |
| `{noop}password` | Prefixed plaintext | Reject under production policy; treat as credential exposure, force reset/migration per security plan. |
| `{sha256}...` or fast unsalted MD5/SHA-1 | Weak hash | Disallow for normal password auth if banned by policy; reset or strictly bounded legacy migration per security sign-off. |
| Unfamiliar prefix of documented but uninstalled scheme | Unsupported | Add verifier only if evaluated/approved; never fall back to an arbitrary encoder. |
| Hash with valid prefix but cost too low | Needs work-factor increase | Verify via matching scheme, then re-encode raw password after successful login with atomic write. |
| Non-standard prefix from buggy DB migration | Integrity issue | Restore from trusted source, inspect affected rows; avoid blind regex mass-edits without proof. |

**Never use the same reaction for every case.** When the true algorithm is confirmed to be bcrypt, **prepending a prefix** is a metadata repair. When the algorithm is weak or unknown, **prepending a fake prefix** does not improve security and can open an invalid auth path.

## 6. Strict Configuration: Bcrypt Allowlist, No Automatic Fallback

A simple policy might look like:

- Valid stored data for password auth: only `{bcrypt}` and a bcrypt body.
- New hashes: bcrypt with an organization-evaluated work factor (the sample below picks 10 for demo purposes; not claiming it is optimal for production).
- Reject `{noop}`, `{sha256}`, unknown IDs, and unprefixed verifiers during normal logins.
- If the system plans to migrate from legacy formats: handle it as a **separate policy-documented workflow**, not a default fallback on every request.
- Unknown/invalid format → generic authentication failure, no access granted, no automatic data re-encoding.

For basic enforcement, build a strict delegate:

```java
PasswordEncoder bcrypt = new BCryptPasswordEncoder(10);

DelegatingPasswordEncoder delegate =
        new DelegatingPasswordEncoder(
                "bcrypt",
                Map.of("bcrypt", bcrypt));
```

Calling `delegate.matches(raw, stored)` directly when `stored` lacks `{id}` or has an unmapped ID throws `IllegalArgumentException`. For consistent login responses, a **policy adapter** should validate format first, delegate verification, and fail safely on bad data. Never map a fallback to `NoOpPasswordEncoder`.

### 6.1 Why Not Use setDefaultPasswordEncoderForMatches Arbitrarily?

The `DelegatingPasswordEncoder.setDefaultPasswordEncoderForMatches(...)` API changes how unmapped IDs are handled. The danger is that **the fallback encoder receives the entire stored string as-is, potentially including `{id}...`**. An overly broad fallback can accidentally accept data with unfamiliar prefixes or create an unvetted policy, especially if passed verbatim to a custom verifier.

Do not configure:

```java
// ANTI-PATTERN: illustrates policy mistake, do not run in production.
delegate.setDefaultPasswordEncoderForMatches(
        NoOpPasswordEncoder.getInstance());
```

Even if your aim is fixing `id=null`, this routes all unmapped data into plaintext comparison. In real environments, **classify records by trusted provenance**, enable only approved legacy schemes, and set a retirement date. Never fix errors by "trying every encoder when unsure".

### 6.2 Configuration Policy vs. SQL Queries

A `UserDetailsService` may return the exact hash from the DB, yet if `PasswordEncoder` carries too many mappings, a `{noop}...` record can still authenticate at the auth layer. Conversely, valid bcrypt hashes in the DB will fail if the encoder bean only accepts `{argon2}`. **Storage, password policy configuration, and authentication execution must align**.

For multi-tenant users, make sure the exact account record matches before verifying passwords; never let an encoder accept tenant A's hash and issue a principal belonging to tenant B.

## 7. Runnable Java 17+ Program Covering Every Branch

The example uses Spring Security Crypto 6.5.6, creates randomly salted bcrypt hashes, and tests: approved, wrong password, bare bcrypt, verified bare bcrypt with prefix added, unknown ID, `noop`, broken body, and outdated work factor. Never log password hashes; print only deterministic booleans.

### 7.1 Structure

```text
password-policy-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/PasswordPolicyDemo.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'password-policy-demo'
```

File `build.gradle`:

```groovy
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
    implementation 'org.springframework.security:spring-security-crypto:6.5.6'
}

application {
    mainClass = 'demo.PasswordPolicyDemo'
}
```

### 7.2 Complete Java File

File `src/main/java/demo/PasswordPolicyDemo.java`:

```java
package demo;

import java.util.Map;

import org.springframework.security.crypto.password.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.DelegatingPasswordEncoder;

public final class PasswordPolicyDemo {

    private static final String RAW = "training-password-2026";

    private PasswordPolicyDemo() {
    }

    public static void main(String[] args) {
        BCryptPasswordEncoder bcrypt = new BCryptPasswordEncoder(10);

        // Allow bcrypt only; do not map noop/sha256.
        DelegatingPasswordEncoder strict =
                new DelegatingPasswordEncoder(
                        "bcrypt", Map.of("bcrypt", bcrypt));

        String current = strict.encode(RAW);
        String bare = bcrypt.encode(RAW);
        String lowerCost = new BCryptPasswordEncoder(4).encode(RAW);

        System.out.println("new-has-prefix="
                + current.startsWith("{bcrypt}"));

        System.out.println("new-matches="
                + approvedMatch(strict, RAW, current));

        System.out.println("wrong-password="
                + approvedMatch(strict, "wrong", current));

        System.out.println("bare-rejected="
                + !approvedMatch(strict, RAW, bare));

        // Only illustrates the case ALREADY verified that bare is genuine bcrypt.
        System.out.println("verified-prefix-matches="
                + approvedMatch(strict, RAW, "{bcrypt}" + bare));

        System.out.println("unknown-id-rejected="
                + !approvedMatch(strict, RAW, "{madeup}value"));

        System.out.println("noop-rejected="
                + !approvedMatch(strict, RAW, "{noop}" + RAW));

        System.out.println("broken-body-rejected="
                + !approvedMatch(strict, RAW, "{bcrypt}not-a-hash"));

        System.out.println("old-cost-needs-upgrade="
                + strict.upgradeEncoding("{bcrypt}" + lowerCost));

        // Default behavior when calling delegate without the policy guard.
        try {
            strict.matches(RAW, bare);
            System.out.println("unmapped-id-throws=false");
        } catch (IllegalArgumentException expected) {
            System.out.println("unmapped-id-throws=true");
        }
    }

    private static boolean approvedMatch(
            DelegatingPasswordEncoder strict,
            String rawPassword,
            String storedHash) {

        // Never let unknown / missing IDs fall into a fallback.
        if (storedHash == null || !storedHash.startsWith("{bcrypt}")) {
            return false;
        }

        try {
            return strict.matches(rawPassword, storedHash);
        } catch (IllegalArgumentException badStoredFormat) {
            // Treat strictly as invalid; never let it pass.
            // Do not log storedHash or rawPassword.
            return false;
        }
    }
}
```

**Explaining each scenario:**

- `strict.encode(RAW)` generates a new hash with `{bcrypt}`, whose body changes on each run due to random salt.
- Right raw password against the new hash returns `true`; wrong password returns `false`.
- Bare bcrypt `bare` **is rejected** by the policy guard; once clear evidence proves it is genuinely bcrypt, prepending `{bcrypt}` lets the delegate route properly. **The code only simulates verified data; it does not auto-fix a real DB.**
- `{madeup}...`, `{noop}...`, and malformed-body verifiers are all rejected.
- `upgradeEncoding("{bcrypt}" + lowerCost)` reports that the hash has a lower cost than the configured encoder and needs re-encoding after valid user authentication.
- Calling `strict.matches(RAW,bare)` directly demonstrates the default exception behavior for `null` ID. It is caught explicitly for the demo rather than turning an exception into success.

### 7.3 Running and Exact Stdout

If Gradle Wrapper is present:

```bash
./gradlew run --console=plain
```

If no wrapper is present but a compatible Gradle is installed:

```bash
gradle run --console=plain
```

Windows PowerShell uses `.\gradlew.bat run --console=plain` when a wrapper exists. Running `javac PasswordPolicyDemo.java` **is not enough** without adding Spring Security Crypto to the classpath. When using Gradle, dependencies resolve from Maven Central.

**Stdout from the Java program** (excluding Gradle progress logs and logging implementation warnings):

```text
new-has-prefix=true
new-matches=true
wrong-password=false
bare-rejected=true
verified-prefix-matches=true
unknown-id-rejected=true
noop-rejected=true
broken-body-rejected=true
old-cost-needs-upgrade=true
unmapped-id-throws=true
```

**Reliable testing** checks booleans rather than comparing concrete bcrypt hash strings because of random salts. Cost `4` in the test is solely to simulate a weak hash; such a low cost is not recommended for real passwords.

## 8. Spring Boot Configuration Pattern: Blocking Out-of-Policy IDs Before Calling the Provider

In Spring Boot 3.x / Spring Security 6.x applications, you can provide a `PasswordEncoder` bean enforcing an allowlist. **The snippet below is a configuration class to plug into a Boot app that already has `UserDetailsService`, `SecurityFilterChain`, and dependencies; it is not a standalone program runnable via `javac` alone.**

```java
package demo;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.password.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.DelegatingPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration
public class PasswordPolicyConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        DelegatingPasswordEncoder delegate =
                new DelegatingPasswordEncoder(
                        "bcrypt",
                        Map.of("bcrypt", new BCryptPasswordEncoder(12)));

        return new PasswordEncoder() {
            @Override
            public String encode(CharSequence rawPassword) {
                return delegate.encode(rawPassword);
            }

            @Override
            public boolean matches(
                    CharSequence rawPassword,
                    String encodedPassword) {
                if (encodedPassword == null
                        || !encodedPassword.startsWith("{bcrypt}")) {
                    return false;
                }
                try {
                    return delegate.matches(rawPassword, encodedPassword);
                } catch (IllegalArgumentException invalidStoredVerifier) {
                    return false;
                }
            }

            @Override
            public boolean upgradeEncoding(String encodedPassword) {
                // When scheme is outside policy, login is usually
                // rejected before reaching the upgrade step.
                if (encodedPassword == null
                        || !encodedPassword.startsWith("{bcrypt}")) {
                    return true;
                }
                return delegate.upgradeEncoding(encodedPassword);
            }
        };
    }
}
```

Effect: the username/password provider calls `matches(raw, UserDetails.getPassword())`. If the hash lacks a prefix or uses `{noop}`, the wrapper returns `false`; the provider can convert this into a normal authentication failure instead of letting an unexpected `IllegalArgumentException` escape. **Returning false does not mean "the DB is fixed"**: you still need a separate migration/reset workflow so users with bad credentials can safely recover their accounts.

**Caution:** The wrapper is a simple policy layer; in production you must define handling for nulls, overly long strings, malformed encoder bodies, CPU resource exhaustion, logging, rate limits, timing, and passwordless principal types. If the app has multiple `AuthenticationManager`/`SecurityFilterChain` beans, verify that the right bean is wired into the `DaoAuthenticationProvider` handling requests. Never assume adding a bean makes every manager adopt the same policy.

### 8.1 Why Not Catch Every Exception and Return Success?

Never write:

```java
// WRONG: severe anti-pattern example.
try {
    return passwordEncoder.matches(raw, stored);
} catch (Exception ignored) {
    return true; // Never do this.
}
```

When data is malformed, the rule is **fail closed**. To avoid unnecessary 500 responses, catch format errors at a controlled boundary and convert them into authentication denial; log sanitized error categories for operations. Never replace password verification with arbitrary raw-string comparison against stored values.

### 8.2 Should Exceptions Be Hidden from Clients?

You can return HTTP 401 or a generic login error to users without disclosing that the account holds a weak hash or unknown ID. Internally, maintain metrics and a remediation route. Never return full stack traces or verifiers in HTTP bodies, emails, or logs. Likewise, never lump every DB access error into "wrong password" in audit logs, as that masks operational outages; separate internal diagnostics from public messages.

## 9. Fixing Unprefixed Bcrypt Hashes: Only When Proven Certain

Spring Security docs show converting:

```text
Before: $2a$10$........
After:  {bcrypt}$2a$10$........
```

**Prepending `{bcrypt}` changes neither the algorithm nor the cost**. It merely fixes metadata so `DelegatingPasswordEncoder` picks `BCryptPasswordEncoder`. For properly generated bcrypt hashes, once provenance is verified, adding the prefix restores password verification without needing the raw password.

### 9.1 Prerequisites

Do not run `UPDATE ... CONCAT('{bcrypt}', password_hash)` across every row just because hashes "look like bcrypt". Consider converting only when:

1. You confirmed the legacy schema/application directly used `BCryptPasswordEncoder` or a compatible encoder **for that exact account set**.
2. You validated hash structure samples (variants like `$2a$`/`$2b$`/`$2y$` supported by your library) and lengths/formats; data is not trimmed or corrupted; format matching alone is not sole proof.
3. You scoped exact account IDs/tenants/datasets and excluded already-prefixed rows or rows from other schemes.
4. You verified login behavior using test passwords from verified data in a secure environment. Never log or export raw passwords.
5. You have controlled backups, a transaction/rollback plan, and tested on an isolated copy.
6. The change is idempotent, audited, and row counts are verified before/after; avoid double-prefixing `{bcrypt}{bcrypt}...`.
7. You test login and `upgradeEncoding` after migration; if cost is weak, plan rehashing with raw passwords on subsequent valid authentications.

### 9.2 Illustrative Conditional SQL, Not a Blind Bulk Command

Suppose the organization already has a trusted `password_scheme` column from an older migration and confirmed `BARE_BCRYPT_V1` rows are genuinely bcrypt:

```sql
-- Illustrative PostgreSQL-style SQL; requires review/migration tool,
-- do not run before verifying provenance/dataset.
UPDATE account_credentials
SET password_hash = '{bcrypt}' || password_hash,
    password_scheme = 'BCRYPT_PREFIXED'
WHERE password_scheme = 'BARE_BCRYPT_V1'
  AND password_hash NOT LIKE '{%'
  AND password_hash LIKE '$2%';
```

This statement only illustrates **using trusted metadata and idempotency guards**. `LIKE '$2%'` alone is insufficient for cryptographic proof; do not run it unless the original encoder is certain. Production requires account/tenant scoping, affected row-count checks, transactions, backup verification, exception handling, and tested format validation. SQL concatenation/escaping depends on database dialect.

### 9.3 Why Not Auto-Prepend Prefixes for SHA-256/MD5?

A fast digest hash tagged with `{bcrypt}` is still not bcrypt, so the bcrypt verifier rejects it. Tagging `{sha256}` may cause the default factory to verify a weak scheme in violation of a ban policy; even if the user logs in, the hash remains weak until rehashed with the raw password. For genuinely banned schemes, only a reset/re-enrollment workflow or a strictly bounded, separately governed migration solves the problem properly.

## 10. Upgrading Hashes After Successful Authentication

Two cases must be distinguished:

- **Format repair**: a good bcrypt hash missing `{bcrypt}`. Repairing metadata may not require the raw password once provenance is verified.
- **Cryptographic upgrade**: a hash using a cost/algorithm below current policy. A true upgrade requires **a valid raw password** at an authentication/password-change event, followed by `encode(raw)` with the new scheme and writing the new hash.

### 10.1 Role of upgradeEncoding()

`PasswordEncoder.upgradeEncoding(encodedPassword)` indicates whether a verifier **should be re-encoded** based on the encoder's capabilities/criteria. With `DelegatingPasswordEncoder`, a legacy ID differing from `idForEncode` or target encoder parameters can trigger an upgrade signal. **This is only a signal**; it does not write to the database itself. A hash with a disallowed ID might also report needing an upgrade, yet login with it must not be permitted solely to reach the upgrade step.

A safe flow:

```text
1. Client sends username + raw password over HTTPS.
2. Account lookup retrieves the exact password verifier and status on the server.
3. Check legacy/approved scheme policy (reject unknown schemes).
4. matches(raw, storedVerifier) must succeed.
5. If upgradeEncoding(storedVerifier) or policy requires:
     newVerifier = encoder.encode(raw)  // currently allowed scheme
     conditional/transactional update, never overwriting concurrent changes
6. Login succeeds with trusted principal/authorities.
7. Clear/minimize raw password lifetime, audit sanitized metadata.
```

If the verifier fails or the scheme is banned, **never rehash using the raw password the user just tried** and treat the login as successful. Typing a password once does not prove ownership unless verified by a trusted scheme.

### 10.2 UserDetailsPasswordService in Spring Security

`DaoAuthenticationProvider` supports `setUserDetailsPasswordService(UserDetailsPasswordService)`. When properly configured and a valid upgrade occurs, this service receives **the new encoded password** to persist. Condensed interface:

```java
public interface UserDetailsPasswordService {
    UserDetails updatePassword(
            UserDetails user,
            String newPassword);
}
```

The `newPassword` parameter in this contract is normally **an already-encoded value**, not a raw password. Always check the actual version/provider contract; never call `encoder.encode(newPassword)` again when saving, because double-hashing breaks subsequent logins.

Illustrative configuration for Spring Security 6.x (requires real beans/services/repositories):

```java
@Bean
DaoAuthenticationProvider daoAuthenticationProvider(
        UserDetailsService users,
        PasswordEncoder passwordEncoder,
        UserDetailsPasswordService passwordUpdates) {

    DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(users);
    provider.setPasswordEncoder(passwordEncoder);
    provider.setUserDetailsPasswordService(passwordUpdates);
    return provider;
}
```

This **is not a standalone Java file**; it requires annotation/class imports, `SecurityFilterChain` setup, and a transactional DB updater implementation. Merely declaring a `UserDetailsPasswordService` does not guarantee every authentication path upgrades: the provider must use the right encoder/service, the user must authenticate successfully, the scheme must pass policy, and the active mechanism must actually invoke the upgrade.

### 10.3 Conditional Updates to Avoid Overwriting Fresh Password Resets

In account stores handling concurrent requests, prevent this scenario:

1. Login A reads the old hash.
2. User resets their password in request B and persists the new hash.
3. Login A finishes and accidentally overwrites the new hash with a rehash of the old password.

The solution is **compare-and-swap** or optimistic locking on record version, checking the affected row count:

```sql
UPDATE accounts
SET password_hash = :new_encoded,
    password_version = password_version + 1
WHERE account_id = :account_id
  AND password_hash = :expected_old_encoded
  AND password_version = :expected_version;
```

If updated rows = 0, the session/record changed; **do not overwrite**, and re-evaluate authentication/session per policy. When rotating credentials, consider revoking old sessions/tokens and aligning auth versions. Never log raw passwords or full verifiers in audit trails.

### 10.4 Do Not Keep Weak Schemes Forever Just Because a "Migration Path Was Added"

A complete migration plan requires:

- Criteria for enabling legacy verifiers and who approves it.
- Which accounts/tenants/schemes are permitted, tagged with server-side metadata.
- Rate limits, monitoring, anti-enumeration, and brute-force responses.
- A sunset deadline for legacy scheme support, rehash/reset progress tracking, and user communication.
- Disallowing legacy schemes for new accounts or new password resets.
- Metric verification: account counts by scheme, upgrade successes/failures, remaining resets needed, login failure rates.
- At end-of-window, **removing legacy mappings from runtime**, deleting unused fallback code, and confirming no accounts were left behind.

## 11. Unattributed Records or Banned Algorithms: Force Resets When Necessary

Not every hash can be "silently upgraded" when a user logs in:

- If a hash's scheme is unknown, **there is no trusted verifier** to check raw passwords against.
- If a hash is plaintext/`{noop}` in a production database, treat it as exposed secret material; merely changing the text to another prefix does not undo exposure.
- If a hash is MD5/SHA-1/fast digest on a banned list, allowing logins with it may violate policy; security owners must decide on resets or tightly bounded transitions.
- If the body is truncated, the valid hash cannot be reconstructed from the broken string; restore from safe backups or reset the password.
- If the user belongs to an external IdP, the app may **not store a local password verifier at all**. Never invent fake passwords and enable noop to "look like a normal account".

### 11.1 Resets Must Not Become an Account Takeover Vector

The reset flow must verify the requester's ownership using independent, risk-appropriate factors; use single-use, high-entropy, short-TTL tokens with brute-force/replay defenses, rate limits, anti-enumeration, and TLS. Never email raw passwords, never send DB hashes to users, and never rely on weak "secret questions" as the sole factor unless policy permits.

Upon successful reset:

1. Encode the new password with the current scheme and store the standard prefix.
2. Increment password/security version if policy requires revoking old sessions.
3. Revoke related sessions, refresh tokens, and remember-me tokens per policy.
4. Audit actor, timestamp, and account ID without logging tokens/passwords.
5. Ensure the record leaves the malformed-legacy cohort; update source metadata and metrics.

### 11.2 Do Not Infer Algorithm Solely from Hash Length

A 64-hex-character string might be SHA-256, HMAC, or something else; length alone proves neither algorithm nor salt/pepper usage. Bcrypt carries version and cost markers, yet still requires provenance. Never run multiple encoders in sequence until one matches without a trusted boundary; doing so enables downgrades, wastes CPU, and complicates auditing.

## 12. Integration with UserDetailsService and DaoAuthenticationProvider

A normal username/password request follows this path:

```text
Login request (username + raw password)
  |
  v
AuthenticationFilter
  |
  v
AuthenticationManager / ProviderManager
  |
  v
DaoAuthenticationProvider
  +--> UserDetailsService.loadUserByUsername()
  |         |
  |         +--> DB account: username, encoded password, status, authorities
  |
  +--> PasswordEncoder.matches(raw, stored)
           |
           +--> id approved + body match: true
           +--> id approved + wrong password: false
           +--> id absent/unapproved: fail closed, migration/reset flow
  |
  v
Authentication success / authentication failure
```

**Key point:** `UserDetailsService` should not verify raw passwords itself; it returns the stored verifier. `DaoAuthenticationProvider` verifies credentials via `PasswordEncoder`. An application-wide custom encoder that "patches formats" must be reviewed carefully because it affects every user of that provider, including other tenants.

### 12.1 Misconfigured Beans and Manager Routing

Another common cause of errors is declaring a strict `PasswordEncoder` bean while manually instantiating a `DaoAuthenticationProvider` with a different encoder, or having two `SecurityFilterChain` beans with separate authentication managers. To diagnose properly, check:

- Which filter constructs `UsernamePasswordAuthenticationToken`?
- Which manager is invoked?
- Which provider supports that token type?
- Which `PasswordEncoder` instance does that provider use?
- Does `UserDetailsService` fetch the right record/schema/tenant?
- Does the password-update pipeline follow the same format/policy as the login pipeline?

Never infer from "a PasswordEncoder bean exists" that every login path uses it.

### 12.2 Prevent Encoded Passwords from Leaking into Responses or Logs

`Authentication.getPrincipal()` after username/password login often holds a `UserDetails`. Never serialize `UserDetails` directly to JSON, as `getPassword()` may return the verifier if not yet erased. Use allowlisted response DTOs: account ID, display name, and necessary authorities; keep hashes and raw credentials inside security boundaries. `ProviderManager` includes credential erasure, though that does not guarantee all secret copies in DB caches, heaps, or logs are wiped.

## 13. Boundary Between "Missing Prefix" and "Missing Password"

A `UserDetails` with `getPassword()==null` can reflect an OIDC/passkey account, unactivated password auth, or corrupted data. **Never fix it by picking NoOpPasswordEncoder or inserting an empty hash**.

Define clear policies:

- Local-password account: verifier must follow an accepted format, never null/empty.
- External-only account: password login unsupported; redirect to configured IdP/passkey mechanism.
- Account pending reset: password login denied until verified reset completes.
- Imported legacy account: carries explicit migration state (verified bare bcrypt / unknown / blocked) rather than guessing on every request.
- Locked/disabled account: status checks remain enforced; a matching password never overrides status.

Separating `credential_type` and `credential_scheme` from `password_hash` in the data model can aid migration when provenance is clear. However, metadata must be set/maintained by an **authoritative source**, never from client claims.

## 14. Common Errors and Remedies

| Symptom | Possible cause | Action |
| --- | --- | --- |
| `There is no PasswordEncoder mapped for the id "null"` | Missing `{id}` or malformed verifier structure | Check origin/format; prepend prefix only for proven hashes, or reset. |
| `There is no PasswordEncoder mapped for the id "sha256"` | Strict encoder does not map that scheme | Check policy; do not add the mapping just to silence errors if the scheme is banned. |
| `BadCredentialsException` | Wrong raw password or policy adapter returned false on bad scheme | Diagnose internally, return generic client message; inspect verifier and status. |
| Legacy logins start working after switching from strict to factory default | Factory includes legacy mappings outside allowlist | Build strict map/policy; test against disallowed-ID table. |
| Login fails after prefix repair | Corrupted/truncated hash body or non-bcrypt original scheme | Restore clean data from trusted source or reset; do not stack another prefix. |
| Hash has `{bcrypt}` but weak cost | Valid prefix, low work factor | Use `upgradeEncoding` and re-encode after successful auth. |
| Hash becomes `{bcrypt}{bcrypt}$2a$...` | Repeated migration runs or double-prefixing | Guard idempotency, verify row counts, roll back/fix per provenance. |
| New password fails after update | Double-hashed or raw/`newPassword` contract mismatch | Distinguish `updatePassword` receiving encoded verifier from `PasswordEncoder.encode(raw)`. |
| Some tenants log in while others fail | Different schemas/encoders/namespaces or wrong record lookup | Check account/tenant-scoped stores and per-dataset migration policies. |
| Old sessions survive password reset | Resetting the hash does not auto-invalidate sessions/JWTs | Enforce password/auth version and revocation/expiry policies. |
| API returns HTTP 500 for malformed-hash accounts | Unhandled `IllegalArgumentException` at boundary | Fail closed via adapter/handler, audit internally without leaking verifiers. |
| Legacy map stays enabled forever | No migration sunset | Set sunset date, track remaining counts, force resets, remove legacy mapping. |

### A "Null ID Error" Does Not Always Mean Changing Code Immediately

The new code may be completely right while the database holds out-of-contract data. If data provenance is clear, **controlled data repair** is better than relaxing the encoder. If provenance is unclear, **do not force logins to work at any cost**; treat it as a data-integrity issue or require a reset.

## 15. Security and Correctness Testing

| Test | Expected result |
| --- | --- |
| New hash created via `encode` | Has `{bcrypt}`, valid body, meets policy cost. |
| Right password against new hash | `matches` is true. |
| Wrong password against new hash | False; no authentication granted. |
| Unmigrated bare bcrypt | Normal login blocked; never tries no-op. |
| Verified bare bcrypt with prefix added | Matches properly without changing raw secret. |
| Unknown ID `{madeup}` | Rejected; no weak fallback invoked. |
| `{noop}` ID in production | Rejected by allowlist. |
| `{sha256}` ID in strict map | Rejected, even if factory default might accept it. |
| Wrong-case ID `{BCRYPT}` | Rejected unless controlled metadata migration applies. |
| `{bcrypt}` with invalid body | Rejected; never falls through to another encoder. |
| Duplicate prefix `{bcrypt}{bcrypt}...` | Must not silently "try a second time". |
| Low legacy bcrypt cost | `upgradeEncoding` detects upgrade need; upgraded after valid login. |
| Hash of unknown origin | No guessing; routed to reset/forensics per policy. |
| `UserDetailsPasswordService` updates password | Persists encoded verifier once; CAS/transaction safe. |
| Concurrent login/reset | Never overwrites new hash with rehash from old session. |
| Policy algorithm switch | No downgrade path; new accounts use current scheme. |
| Public failure message | Never leaks account existence, stored hash, encoder map, or internal error text. |
| Logging | Contains no raw passwords, encoded hashes, bearer tokens, or unnecessary secrets. |
| New account creation post-migration | Never produces bare hashes, `{noop}`, or banned schemes. |
| Disabled/locked account with valid hash | Still cannot log in; valid format never bypasses account status. |
| Cached UserDetails with stale hash | Cache is invalidated/updated properly on upgrade/reset. |
| Post-sunset date | Legacy mappings removed and all remaining accounts handled. |

**Migration testing is more than counting rows.** Include samples with verified provenance, right/wrong login tests, corrupted data, concurrent updates, and provider behavior over HTTP. In multi-tenant apps, verify account IDs/namespaces, not just usernames. With adaptive hashing, measure latency under real load so raising cost does not trigger DoS.

## 16. Anti-Patterns to Avoid

### 16.1 Enabling NoOpPasswordEncoder to Silence Errors Quickly

```java
// WRONG in production
PasswordEncoder encoder = NoOpPasswordEncoder.getInstance();
```

This makes the system expect plaintext, breaking one-way password storage policies. Compatibility APIs in docs may serve controlled demos/migrations, yet **never pick no-op as a production error fix**.

### 16.2 Using a Fallback for Every Unknown Prefix

```java
// WRONG: treats every unrecognized format as legacy.
delegate.setDefaultPasswordEncoderForMatches(someWideFallback);
```

There is no proof that such schemes are permitted. Fallbacks can widen acceptance unintentionally; rely on scheme allowlists and provenance rather than "trying to see what matches".

### 16.3 Prepending {bcrypt} to All Unprefixed Strings

```text
WRONG:
  if (!hash.startsWith("{")) {
      hash = "{bcrypt}" + hash;
  }
```

Unprefixed rows might be plaintext, MD5, SHA-1, or corrupted. Adding the wrong label does not turn data into bcrypt and can mask data corruption. Fix only when source algorithm is certain and tested.

### 16.4 Rehashing the Hash String Itself as a Raw Password

```java
// WRONG: encodedPassword is not rawPassword.
String bad = encoder.encode(userDetails.getPassword());
```

That creates a **hash of a hash**, not a verifier for the user's entered password. Encode the raw secret only after valid authentication/password change, and never double-hash the `newPassword` argument already passed to `UserDetailsPasswordService`.

### 16.5 Blocking Even Valid Formats Because Migration Is Incomplete

A strict policy still needs an operational plan that avoids locking out legitimate users permanently. For batches with proven bare bcrypt, repair metadata safely offline for scoped sets; for banned/unknown schemes, provide an enumeration-resistant recovery/reset flow. **Availability never justifies skipping authentication**, yet recoverability must still be engineered.

## 17. Self-Check Exercises and Answers

**Question 1.** Spring Security reports `id "null"` for a hash starting with `$2a$...`. Must you enable `NoOpPasswordEncoder`?

**Answer:** No. The hash shows signs of bare bcrypt missing `{bcrypt}`. Verify provenance and format; if proven, prepend the prefix in a controlled manner. `NoOp` is the wrong tool.

**Question 2.** The database stores `{sha256}...`; `PasswordEncoderFactories` can read it, yet policy forbids fast digests. Should you keep the mapping so users are unaffected?

**Answer:** Never override policy unilaterally. You need a reset plan or an approved time-bounded legacy migration; encode new hashes with a strong scheme and remove old mappings. "Has a mapping" does not mean "is permitted".

**Question 3.** Can you convert all MD5 hashes to bcrypt by calling `encoder.encode(md5Hash)` without users entering passwords?

**Answer:** The result cannot be treated as bcrypt of the raw password. It merely hashes an old verifier, changing semantics and potentially yielding a weak scheme. You need verified raw passwords or a policy-compliant reset.

**Question 4.** Does `{bcrypt}` + a cost 4 bcrypt hash still need an upgrade?

**Answer:** Likely yes. A valid prefix does not prove the cost meets requirements; `upgradeEncoding` and work-factor policy determine whether rehashing is needed after raw password verification succeeds.

**Question 5.** After migrating a row to `{bcrypt}$2a$...`, the app still reports wrong password. Should you try every other encoder and pick whichever returns true?

**Answer:** No. Check whether the hash body was truncated/altered, whether the original encoder was truly bcrypt, whether migration double-prefixed it, or whether the wrong account was read. Never build an uncontrolled multi-algorithm fallback.

**Question 6.** When `UserDetailsPasswordService.updatePassword(user,newPassword)` is called, should you encode `newPassword` once more?

**Answer:** No if the provider passed the **new encoded verifier** per contract. Double-hashing causes subsequent logins to fail. Store it verbatim using conditional/transactional updates.

**Question 7.** Why are conditional update locks needed when rehashing after login?

**Answer:** Logins and password resets can run concurrently; without compare-and-swap/versioning, rehashing the old password can overwrite a fresh hash from a reset. If the update fails because the row changed, handle per policy without overwriting.

**Question 8.** Does configuring a fallback that returns `false` for unknown IDs migrate the data?

**Answer:** No. It only turns malformed formats into safe failures; the database still requires repair, migration, or reset.

**Question 9.** A user can log in with `{noop}password` because the default library includes a mapping. Does that mean the hash is organization-approved?

**Answer:** No. Mappings for compatibility/demos do not prove policy approval; apply strict configuration and audit data/provenance.

**Question 10.** After changing a password to new bcrypt, do old sessions/JWTs expire automatically?

**Answer:** Not by default. Session, refresh token, and access token lifecycles can be independent; if policy requires revocation on password change, implement explicit version/session/token invalidation.

## 18. Production Deployment Checklist

1. **Inventory:** tally records by prefix/schema/dataset without exporting raw hashes; identify owners and algorithm provenance.
2. **Policy:** define creation schemes, temporary verification schemes, banned schemes, and minimum cost parameters with security sign-off.
3. **Strict encoder:** `DelegatingPasswordEncoder` with a true allowlist; omit `noop` or weak legacy mappings outside controlled windows.
4. **Error handling:** missing/unknown/malformed IDs must fail closed with generic public responses and secret-free internal metrics.
5. **Data migration:** when only metadata is missing, repair exact scoped sets with backups, transactions, idempotency, and audits; never edit all rows blindly.
6. **Crypto migration:** rehash only after verified raw-password authentication or safe reset; never encode hashes as raw input.
7. **Update concurrency:** CAS/optimistic locking prevents login rehashes from overwriting password resets; check affected row counts.
8. **Account state:** keep enabled/locked/expired and tenant-identity checks enforced; valid hashes never bypass account policy.
9. **Credential lifecycle:** rotate/revoke sessions, remember-me, refresh grants, and access tokens per threat model on reset.
10. **Security testing:** unknown ID, uppercase ID, double prefix, corrupted body, low salt/cost, wrong password, concurrent resets, migration audits.
11. **Performance:** measure adaptive hashing cost and enforce login rate limits under load; avoid unbudgeted CPU bottlenecks.
12. **Cleanup:** set a legacy sunset date, remove fallbacks and old code, track accounts still needing reset, and conduct a post-rollout review.

## 19. Official Sources and Further Reading

- [Spring Security 6.5 — Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html): `{id}encodedPassword` format, building encoders, `id=null` errors, adding prefixes for known bcrypt, algorithms, and NoOp caveats.
- [Spring Security — DelegatingPasswordEncoder Javadoc](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/crypto/password/DelegatingPasswordEncoder.html): constructors, `matches`, `upgradeEncoding`, and `setDefaultPasswordEncoderForMatches`.
- [Spring Security — PasswordEncoder API](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/crypto/password/PasswordEncoder.html): `encode`, `matches`, `upgradeEncoding`.
- [Spring Security — PasswordEncoderFactories](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/crypto/factory/PasswordEncoderFactories.html): factory mappings and default encoding scheme per version.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): verifying passwords from `UserDetailsService`.
- [Spring Security — DaoAuthenticationProvider Javadoc](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html): configuring `PasswordEncoder`, `UserDetailsPasswordService`, and the provider.
- [Spring Security — UserDetailsPasswordService API](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/core/userdetails/UserDetailsPasswordService.html): API for updating encoded verifiers on upgrade.
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): password hashing, salts/work factors, migration, and risks of fast hashes.
- [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): enumeration- and replay-resistant reset flows.

**Takeaway:** **A missing `{id}` error is a format/verifier identification issue, not a reason to skip password checks.** The right prefix selects the right encoder, yet **does not strengthen the hash by itself**. For banned or unknown algorithms, fail closed and remediate via controlled migration or reset. Perform true cryptographic upgrades only after obtaining a verified raw password or through safe recovery; ensure every new hash follows policy with no downgrade paths left open.
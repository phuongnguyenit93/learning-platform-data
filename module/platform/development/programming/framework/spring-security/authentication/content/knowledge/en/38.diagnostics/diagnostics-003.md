# Correct Password Fails Verification Due to Encoder, Prefix, or Hash Data

A common source of confusion in **Spring Security - authentication**: the user insists they entered the right password, yet the system still returns "Bad credentials", HTTP 401, or redirects to `/login?error`. Sometimes the logs say `There is no PasswordEncoder mapped for the id "null"`, sometimes `PasswordEncoder.matches(...)` simply returns `false`, and sometimes the authentication flow never even reaches the password check.

The cause may not be a user typo: **the selected encoder does not match the stored hash data**, the algorithm prefix `{id}` is missing or wrong, the hash was truncated when saved to the database, the password was transformed differently between registration and login, or the authentication flow loaded the wrong account/hash.

This lesson belongs to the **Diagnostics** section, using **Java 17+, Spring Boot 3.x, and Spring Security 6.x (prioritizing 6.5 documentation)**. Topics include `DaoAuthenticationProvider`/`PasswordEncoder` mechanics; the meaning of `{bcrypt}` and other IDs; a diagnostic tree without credential leaks; runnable examples; JUnit/Spring Security tests; safe legacy hash handling; and a checklist to avoid breaking logins during upgrades.

> **Overarching Security Rule:** Never ask users to send passwords, hashes, access tokens, or user table dumps in chat/tickets. Never log raw passwords, `UserDetails.getPassword()`, full `Authentication` objects, or SQL queries containing passwords. When investigating, collect **hash type code, length, status, encoder version, and event ID** in a controlled environment; never record full hash values.

## 1. First, Pinpoint Where the "Failure" Happens

A typical Servlet `formLogin` password login request:

~~~text
Browser/HTTP client
   │
   ├── POST /login + username/password + CSRF token
   ▼
Spring Security FilterChain
   │
   ├── CsrfFilter: is token valid?
   │       └─ No → 403 (password not checked yet)
   ▼
UsernamePasswordAuthenticationFilter
   │
   ▼
AuthenticationManager (typically ProviderManager)
   │
   ▼
DaoAuthenticationProvider
   │
   ├── UserDetailsService.loadUserByUsername(username)
   │       ├── User does not exist / data source error
   │       └── Returns UserDetails: getPassword() = encoded password
   │
   ├── Account pre-checks: enabled / locked / expired
   │
   ├── PasswordEncoder.matches(rawFromRequest, encodedFromStore)
   │       ├── true  → password accepted
   │       ├── false → BadCredentialsException
   │       └── config/hash error → may throw exception
   │
   └── Post-checks, additional MFA/policy, success or failure
   ▼
Form success/failure handler or Basic authentication entry point
   │
   ├── Form: usually 302 redirect to /login?error
   └── HTTP Basic: usually 401 with WWW-Authenticate
~~~

**Do not see HTTP 403 or 302 and immediately conclude "wrong encoder".** A 403 on `POST /login` can be CSRF; a 403 after successful login can be a missing role; a 302 can be a normal form-login redirect; and a 401 Basic can also come from a disabled user or an unconfigured provider.

### 1.1. The Two Arguments of `PasswordEncoder.matches`

The most important method:

~~~java
boolean accepted = encoder.matches(rawPassword, storedEncodedPassword);
~~~

- `rawPassword`: the user-entered value, **unhashed**, after any normalization steps confirmed by policy to be consistent.
- `storedEncodedPassword`: **the stored hash string** (which may include an `{id}` prefix), retrieved from the user repository.
- `PasswordEncoder.matches` selects the algorithm, computes the check using the salt/parameters embedded in the hash, and compares appropriately.

**Common mistake:** passing `encoder.encode(rawPassword)` as the first argument, then comparing against the stored hash. Many algorithms use a random salt, so a newly generated hash of the same password differs from the old hash; that is not how verification works.

~~~java
// CORRECT: raw + stored encoded
encoder.matches(rawPassword, storedEncodedPassword);

// WRONG: re-encoding before matches
encoder.matches(encoder.encode(rawPassword), storedEncodedPassword);

// WRONG: comparing two independently generated hashes
encoder.encode(rawPassword).equals(storedEncodedPassword);
~~~

Encoding the same password twice can produce **two different hashes** due to salt; two different hash strings **do not prove the passwords differ**.

### 1.2. What Is `DaoAuthenticationProvider`'s Role?

Per the Spring Security 6.5 documentation, `DaoAuthenticationProvider`:

1. Receives username/password in a `UsernamePasswordAuthenticationToken`.
2. Calls `UserDetailsService` to fetch the corresponding `UserDetails`.
3. Uses `PasswordEncoder` to verify the raw password against `userDetails.getPassword()`.
4. Checks appropriate account status flags and returns a successful `Authentication` when all conditions pass.

The encoder can be configured as an application-wide bean or directly on a provider. If the application has **multiple `SecurityFilterChain`s, multiple authentication managers/providers, or separate test configs**, do not just find a `PasswordEncoder` bean and assume every login path uses it. You must identify **the actual provider selected for the real endpoint and user repository**.

In Spring Security 6.5, the recommended constructor API is:

~~~java
DaoAuthenticationProvider provider =
        new DaoAuthenticationProvider(userDetailsService);
provider.setPasswordEncoder(passwordEncoder);
~~~

This is a **snippet inside a method/config bean** where `userDetailsService` and `passwordEncoder` variables are already supplied. Imports belong to `org.springframework.security.authentication.dao.DaoAuthenticationProvider`, `org.springframework.security.core.userdetails.UserDetailsService`, `org.springframework.security.crypto.password.PasswordEncoder`. Do not add another provider like this to a running project just to fix an error without understanding the current wiring.

## 2. Password Storage Format with `DelegatingPasswordEncoder`

Spring Security uses `DelegatingPasswordEncoder` to allow **encoding new passwords with a current algorithm while still verifying old hashes using each record's own algorithm**.

Storage syntax:

~~~text
{id}encodedPassword
~~~

Bcrypt example:

~~~text
{bcrypt}$2a$10$.....................................................
│       └─ BCrypt encoded hash containing version, cost, salt, and checksum
└─ ID for DelegatingPasswordEncoder to pick the right encoder
~~~

The dots in the diagram are **illustrative placeholders**, not a valid hash. A valid compact bcrypt hash is typically **60 characters** long; the `{bcrypt}` prefix is **8 characters** long, so the prefixed form is typically **68 characters** long.

| Stored String | Meaning | Expected Encoder |
| --- | --- | --- |
| `{bcrypt}$2a$10$...` | Prefixed bcrypt | `BCryptPasswordEncoder` mapped under key `bcrypt` |
| `$2a$10$...` | **Raw** bcrypt, missing Spring prefix | Use BCrypt directly; default Delegating reports missing ID |
| `{pbkdf2@SpringSecurity_v5_8}...` | PBKDF2 configured for Spring 5.8 defaults | `Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8()` |
| `{pbkdf2}...` | A legacy PBKDF2 configuration in default mapping | Do not arbitrarily change ID to `pbkdf2@SpringSecurity_v5_8` |
| `{scrypt@SpringSecurity_v5_8}...` | SCrypt with parameter set for specific ID | Corresponding SCrypt encoder |
| `{argon2@SpringSecurity_v5_8}...` | Argon2 per matching Spring config | Corresponding Argon2 encoder and required dependencies |
| `{noop}plaintext` | Legacy/no-op, unhashed | **Never use for new passwords in production** |
| `{unknown}...` | Unmapped ID | Default Delegating throws exception |
| `$2y$...` or `$2b$...` without prefix | Raw bcrypt variant from another system | Must verify library compatibility then migrate |
| `bcrypt:...` | Not the default `{id}...` format | Needs adapter/migration, do not guess |

**The `{id}` tag is algorithm-selection metadata**, not a salt, not the bcrypt algorithm, and not a string to prepend to the **raw password**. With `DelegatingPasswordEncoder.matches(raw, "{bcrypt}"+bcryptHash)`, Spring strips `{bcrypt}` and passes **the trailing hash** to `BCryptPasswordEncoder`.

Do not conclude "valid bcrypt" just because a hash starts with `$2`: you must verify valid format/length/version and check with the proper encoder without logging or exposing the value.

### 2.1. Creating the Default Encoder

~~~java
PasswordEncoder encoder =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();
~~~

Imports:

~~~java
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
~~~

According to 6.5 docs, the default factory **encodes new passwords with `bcrypt`**, returning strings starting with `{bcrypt}`, and includes mappings for legacy formats such as PBKDF2, SCrypt, Argon2, and legacy IDs. **Supporting verification of a legacy format does not mean legacy algorithms should still be used to create new passwords.**

If a system originally used `new BCryptPasswordEncoder()`, `encode(...)` generated `$2a$...` strings without `{bcrypt}`. Later switching the bean to `PasswordEncoderFactories.createDelegatingPasswordEncoder()` without **migrating the older stored values** causes users entering the right password to hit prefix errors.

### 2.2. `idForEncode` Differs from the ID of the Hash Being Checked

In `DelegatingPasswordEncoder`:

- `idForEncode` determines the algorithm when **encoding new passwords**.
- `{id}` in each stored hash determines the algorithm during **`matches`**.
- Old `{bcrypt}...` hashes can still verify while new passwords are encoded with PBKDF2/Argon2 (if all mappings are configured properly).
- Never prepend a new algorithm prefix onto **an old hash tail belonging to a different algorithm**; doing so only changes the label, not the algorithm.

Example of a broken migration:

~~~text
Before: {bcrypt}$2a$10$...
Wrong:  {pbkdf2@SpringSecurity_v5_8}$2a$10$...
~~~

The tail is still bcrypt; PBKDF2 cannot verify a bcrypt hash just because the prefix changed. To switch algorithms, you must **verify the user's current password and then re-encode with the new encoder**, or require a password reset through a trusted flow.

## 3. Error: "There is no PasswordEncoder mapped for the id null"

This is a classic case:

~~~text
java.lang.IllegalArgumentException:
There is no PasswordEncoder mapped for the id "null"
~~~

This message is a **diagnostic signal** in Spring Security 6.5 documentation; exact exception wording may vary by version. It typically means `DelegatingPasswordEncoder` found no `{id}` at the start of `storedEncodedPassword`. It is **not** evidence that the entered password was wrong.

Example:

~~~java
BCryptPasswordEncoder legacy = new BCryptPasswordEncoder();
String rawBcryptHash = legacy.encode("lab-password-2026");

PasswordEncoder delegating =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();

delegating.matches("lab-password-2026", rawBcryptHash);
// Typically throws IllegalArgumentException because rawBcryptHash lacks {id}.
~~~

This is a **method-body snippet**; it needs imports for `BCryptPasswordEncoder`, `PasswordEncoder`, and `PasswordEncoderFactories`. Never use real passwords in snippets/console output.

### 3.1. The Right Fix When You Are Sure the Format Is Bcrypt

If an administrator has **verified via an audited migration inventory** that a cohort of records are valid raw bcrypt (e.g., compact `$2a$...` strings), you can prepend `{bcrypt}` in storage **without knowing the plaintext**:

~~~java
// Run only in a validated migration with backups and ownership checks.
String updated = "{bcrypt}" + verifiedLegacyRawBcryptHash;
~~~

Then with `DelegatingPasswordEncoder`:

~~~java
boolean accepted = delegating.matches(
        userEnteredRawPassword,
        "{bcrypt}" + verifiedLegacyRawBcryptHash);
~~~

Safeguards required:

1. Confirm the hashes actually belong to bcrypt, not merely by checking one leading character or guessing from email.
2. Check hash integrity, length, and format before migration.
3. Do not alter prefixes on records that already have `{id}`.
4. Store the full `{bcrypt}...` string in a wide enough column, not truncated by `VARCHAR(60)`.
5. Use a **transaction/backup**, count affected rows, and prepare a rollback plan.
6. In production, never log full hashes or raw password values.
7. Test with synthetic sample data and verify post-migration login through a safe process.
8. Do not add prefixes to records whose format **cannot be determined**; require password reset or a verified legacy adapter.

**Do not** fix this by prepending `{noop}` before a bcrypt hash: that makes `NoOpPasswordEncoder` compare the entered password against the literal hash string and is an insecure configuration.

### 3.2. When an ID Exists, but Is Not Mapped

If the stored value is `{pbkdf2@SpringSecurity_v5_8}...` while the application only configures a `bcrypt` map, the error is **unknown/unmapped ID** even though the prefix is valid. Add the matching encoder **if the app genuinely stored that format previously**. Do not build a "try every hash" fallback across all accounts, and do not silently allow unrecognized formats.

Example configuring only two approved formats:

~~~java
Map<String, PasswordEncoder> encoders = new HashMap<>();
encoders.put("bcrypt", new BCryptPasswordEncoder());
encoders.put("pbkdf2@SpringSecurity_v5_8",
        Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8());

PasswordEncoder delegating =
        new DelegatingPasswordEncoder("pbkdf2@SpringSecurity_v5_8", encoders);
~~~

The snippet above belongs **inside a bean method**, needing imports `java.util.Map`, `java.util.HashMap`, and `org.springframework.security.crypto.password.*`. It encodes new hashes with the Spring 5.8 PBKDF2 prefix while **verifying prefixed bcrypt**. Unprefixed raw bcrypt data **is still unhandled**: you need a migration or a separate strict legacy strategy.

### 3.3. Why `setDefaultPasswordEncoderForMatches` Is Not a Universal Fix Button

`DelegatingPasswordEncoder#setDefaultPasswordEncoderForMatches(PasswordEncoder)` lets you supply a fallback encoder when a stored ID is unmapped. However, the Javadoc warns: **the `encodedPassword` passed to the fallback is the ENTIRE stored value, including any unrecognized prefix**.

If you set the fallback to `BCryptPasswordEncoder` and encounter `{unknown}$2a$...`, it will not strip `{unknown}` automatically. If you set the fallback to `NoOpPasswordEncoder` or an overly permissive encoder, it can introduce **insecure** behavior. Therefore:

- Do not use an "accept any password" fallback or `NoOpPasswordEncoder`.
- Do not blindly strip unknown prefixes and brute-force all algorithms.
- Do not leave a generic fallback in place permanently without metrics and a migration deadline.
- Prefer inventorying hash formats, storing proper metadata, and running conditional backfills/migrations.

## 4. Distinguishing Exceptions, `false`, and Other Authentication Errors

| Symptom | Usually Indicates | First Investigation Step |
| --- | --- | --- |
| `There is no PasswordEncoder mapped for the id "null"` | Stored hash lacks `{id}` or has invalid format | Check hash type and DB source; do not verify via plaintext password in logs |
| `There is no PasswordEncoder mapped for the id "..."` | Stored ID is not registered in encoder map | Compare map config and stored prefix; check typos/casing/version |
| `matches(raw, encoded) == false` | Different password, corrupted hash, mismatched encoder/params, altered raw value | Test with controlled fixture; check migration/storage history |
| BCrypt warning "Encoded password does not look like BCrypt" | Trailing string after prefix is not valid BCrypt format, truncated, or wrong type | Check column metadata and prefix/encoded tail |
| `BadCredentialsException` | Provider rejected credentials; may mask user-not-found | Separate user lookup vs encoder using safe log categories |
| `UsernameNotFoundException` | `UserDetailsService` found no user | Check username normalization, tenant, repository, cache; do not leak existence |
| `DisabledException` / `LockedException` / `AccountExpiredException` | Account is not permitted to log in | Check account flags; do not reset hash arbitrarily |
| `CredentialsExpiredException` | Credential is marked expired | Check expiration/password-change flow |
| POST form login returns 403 | Likely missing/invalid CSRF | Check `CsrfFilter`; do not touch password encoder yet |
| Protected GET returns 403 after login | Likely missing role/authority | Check authorization, not hash |
| Basic returns 401 | Wrong credentials, account state, provider config, or entry point | Compare Basic flow vs form login in tests |
| Form returns 302 `/login?error` | Failure handler ran | Check sanitized audit category; do not infer algorithm from status |
| Users cannot log in after every restart | In-memory user store, unstable salt/secret params, DB pointing to wrong env | Check datasource, deployment env, encoder parameters, migration |
| Only some users fail after deploy | Legacy/mixed ID cohort, truncation, or encoding differences over time | Classify records by metadata without reading full values |
| Correct password still blocked on new logins | MFA, account lock, session policy, compromised-password checker | Inspect each authentication layer and policy for that request |

**Security point:** public system responses should usually stay generic ("Invalid credentials") to prevent user enumeration. Internally, audits can classify `ENCODER_ID_MISSING`, `ENCODER_ID_UNSUPPORTED`, `STORED_HASH_MALFORMED`, `ACCOUNT_DISABLED`, `CSRF_REJECTED`, etc., using only allowlisted values and never placing raw usernames/passwords/hashes in logs.

## 5. Verifiable Diagnostic Tree Without Blindly Editing the Database

~~~text
User: "Password is definitely right, but login fails"
       │
       ▼
1. Does the request reach AuthenticationProvider?
       ├─ No: CSRF, filter-chain match, URL, HTTP method,
       │      session, reverse proxy, authorization
       └─ Yes
           │
           ▼
2. Does UserDetailsService load the right account and password hash?
       ├─ No: username/tenant/email lookup, DB, cache, locked
       └─ Yes
           │
           ▼
3. Does stored encoded value have a valid {id}?
       ├─ No: inventory legacy format / missing prefix
       ├─ Unknown ID: Delegating map config differs from data
       └─ Yes
           │
           ▼
4. Is the encoded tail intact with valid format/length?
       ├─ No: VARCHAR/CHAR, truncation, migration, encoding
       └─ Yes
           │
           ▼
5. Did the raw password undergo any transformation?
       ├─ Yes: trim, lowercase, NFC/NFD, charset, Base64,
       │       double-encoding, form/client transforms
       └─ No
           │
           ▼
6. Do encoder params/secret/version match creation time?
       ├─ No: PBKDF2 secret/iterations, Argon2/scrypt params,
       │      or custom encoder changed
       └─ Yes
           │
           ▼
7. What does matches() return on a test fixture?
       ├─ Throws: format/mapper/implementation exception
       ├─ False: hash does not match raw under current pipeline
       └─ True: recheck account flags, provider, MFA,
                authorization, session, response handling
~~~

For any specific user, **never request or extract their real password** to test down this tree. Instead use a dedicated fixture account, category-coded logs, and non-sensitive hash metadata; to recover an account whose hash cannot be determined, provide a secure password reset.

### 5.1. Knowing What the DB Stores Without Exposing Secrets

Record metadata in an authorized environment:

- User table/repository source **for the right tenant** (never return this info to users).
- Allowed algorithm ID prefix, such as `bcrypt` or `pbkdf2@SpringSecurity_v5_8`.
- Stored hash string length (code units/characters/bytes depending on DB).
- Signs of truncation or trailing spaces from `CHAR` padding.
- When the hash was updated and by which application/encoder version.
- The `PasswordEncoder`/`AuthenticationProvider` actually used by that request.
- User flags `enabled/accountNonLocked/credentialsNonExpired`.
- Recent changes to serializers, ORMs, database migrations, or Unicode policies.

**Do not** obtain the prefix by logging all 60 bcrypt characters; also do not store/reveal a SHA-256 of the password for "comparison". When reporting errors, use a server-generated random correlation ID, not a session ID/token/raw credential.

### 5.2. A Query That Reveals Length Bugs Without Printing Hashes

An **example PostgreSQL** SQL query — adjust table/column names to match your project schema:

~~~sql
-- Summarize total record counts by length only.
-- Do NOT SELECT password_hash and do NOT export individual user_ids.
SELECT char_length(password_hash) AS stored_chars, count(*) AS users
FROM app_users
WHERE password_hash IS NOT NULL
GROUP BY char_length(password_hash)
ORDER BY stored_chars;
~~~

Results may group into 60, 68, or other PBKDF2/Argon2 lengths. **Length alone is insufficient to confirm valid format**; statistics only help detect widespread truncation. Never include real user figures in articles/tickets unless authorized.

With a `VARCHAR(60)` column, a raw bcrypt hash fits; however, `{bcrypt}` + bcrypt at 68 characters **will not fit**. Depending on the DB, inserts may be rejected or silently truncated/mangled by code/migrations. `VARCHAR(255)` is often a reasonable starting point for many hash formats, though you **must check actual maximum sizes** of the encoders in use; do not treat 255 as a guarantee for all future formats.

### 5.3. `CHAR` Padding, Trimming, and Storage Types

- `CHAR(n)` columns can right-pad spaces, making the retrieved string differ from the encoded value.
- Mappers/JPA converters might `trim()`/`strip()` or turn `null` into `""`.
- Serializers might strip `{...}`, escape JSON, or alter encoding.
- Password hashes contain special characters (`$`, `{`, `}`, `/`, `+`, `=`) depending on the algorithm; never double-escape or URL-decode them on storage.
- Use an appropriate `String`/`VARCHAR` column rather than converting binary digests to strings arbitrarily with the platform default charset.
- If stored as `VARBINARY`, know precisely whether Base64/hex encoding occurred before or after hashing; **never** take raw bytes of unknown format and call default `new String(bytes)`.

Do not blindly "fix" data by running `trim()` across the whole table. Dropping or altering even one byte of a hash breaks verification; identify the format first and run a dedicated migration with backups.

## 6. Very Common Real-World Data Bugs

### 6.1. User Created with BCrypt, Login Uses Delegating

~~~text
Registration:
  BCryptPasswordEncoder.encode(raw)
  → "$2a$10$..." (no {id})

Login after refactor:
  PasswordEncoderFactories.createDelegatingPasswordEncoder()
  → matches(raw, "$2a$10$...")
  → cannot find id → error
~~~

Fix: verify all legacy rows are genuinely bcrypt and backfill `{bcrypt}`, or use a tightly scoped/time-boxed compatibility adapter. **Do not switch to `NoOpPasswordEncoder`.**

### 6.2. User Created with Delegating, Login Uses BCrypt Directly

~~~text
Registration:
  DelegatingPasswordEncoder.encode(raw)
  → "{bcrypt}$2a$10$..."

Login:
  new BCryptPasswordEncoder().matches(raw, "{bcrypt}$2a$10$...")
  → hash does not start with compact bcrypt format
~~~

Fix: use Delegating for prefixed stored formats or migrate properly. **Do not create a new BCrypt bean just because you see `$2a$` in the hash** when the stored value has `{bcrypt}`.

### 6.3. Double-Hashing on Storage

~~~text
rawPassword
   │
   └─ encode(...) → {bcrypt}$2a$...
                          │
                          └─ encode(...) again → {bcrypt}$2a$...
                                        (hash of the first hash string)
~~~

When login runs `matches(rawPassword, hash2)`, it fails. Typical causes: the controller encodes first and then `UserService.saveNewPassword(...)` encodes again, or a database callback/mapper re-encodes. Designate **one layer responsible for hashing**, taking the raw password at the right boundary and storing it encoded once.

**You cannot recover the raw password from `hash2`**. If no valid verification path exists, trigger a password reset rather than trying to "decode the hash".

### 6.4. Saving to the Wrong Column / Returning the Wrong `UserDetails.getPassword()`

An entity may have multiple fields:

~~~text
users.password_hash
users.previous_password_hash
users.password_reset_hash
users.temporary_hash
~~~

`UserDetailsService` might accidentally return `previous_password_hash` or `password_reset_hash`, or query the wrong tenant/account. A password "correct for right now" still fails to match. Check migrations/mappers/projections and cache invalidation; **never** allow login using a reset-token hash.

### 6.5. Changing PBKDF2/SCrypt/Argon2 Parameters Without Keeping Metadata

PBKDF2 has a hash function, salt length, iterations, and possibly an external secret/pepper outside the DB. SCrypt/Argon2 have memory/iteration/parallelism/output layout parameters. If a custom encoder or versioned config **no longer knows the parameters used for the original hash**, even the same raw password may fail to verify.

Therefore each hash must be self-describing or have a **stable version/ID mapping**. Spring provides IDs such as `pbkdf2@SpringSecurity_v5_8` and `argon2@SpringSecurity_v5_8` to distinguish parameter sets. Never strip prefixes or overwrite everything to `{pbkdf2}` simply because you upgraded Spring.

For encoders using an out-of-DB **pepper/secret**, if the secret is lost or misconfigured across environments during deployment, every affected hash can fail to match. Manage key versions, backups, and rotation plans; never log secrets.

### 6.6. Transforming the Password Before `encode`/`matches`

Common mistakes:

~~~java
// WRONG if registration did not apply the exact same rule:
String toCheck = rawPassword.trim().toLowerCase();
encoder.matches(toCheck, storedHash);
~~~

- Forms/frontends might strip trailing spaces, alter Unicode forms, or change letter casing.
- Registration might apply `Normalizer.Form.NFC` to new passwords while login does not, or vice versa.
- UTF-8 JSON converted with the wrong charset can corrupt Vietnamese characters.
- One service encodes raw passwords; another Base64-encodes before hashing.
- Password managers insert whitespace/newlines and the application handles them inconsistently.
- Legacy BCrypt has input byte limits; a system that previously truncated long passwords may exhibit different semantics after an update.

When changing Unicode policies, **do not apply them retroactively to all old accounts blindly**. Use a versioned pipeline/migration: if old hashes came from unnormalized raw input, applying NFC before `matches` can break logins; test synthetic accounts with combining characters and plan safe transitions.

## 7. Standalone Java 17 Program: Classifying Hash Shape Without Verifying Passwords

This illustrative tool **relies only on synthetic test strings**, uses no real credentials, and exposes no hashes. It detects the difference between raw bcrypt and `{bcrypt}`-prefixed bcrypt, yet **does not prove a string is a valid hash**. A string of the right length can still have a bad salt/checksum.

File `HashShapeInspector.java`:

~~~java
public class HashShapeInspector {

    static String classify(String stored) {
        if (stored == null || stored.isBlank()) {
            return "EMPTY";
        }
        if (stored.startsWith("{bcrypt}$2") && stored.length() == 68) {
            return "PREFIXED_BCRYPT_SHAPE";
        }
        if (stored.startsWith("$2") && stored.length() == 60) {
            return "RAW_BCRYPT_SHAPE";
        }
        if (stored.startsWith("{")) {
            return "PREFIXED_OTHER_OR_MALFORMED";
        }
        return "UNKNOWN_NO_PREFIX";
    }

    public static void main(String[] args) {
        // Synthetic shape data ONLY; not a valid BCrypt hash.
        String fakeRaw = "$2a$10$" + "x".repeat(53);

        System.out.println(classify("{bcrypt}" + fakeRaw));
        System.out.println(classify(fakeRaw));
        System.out.println(classify("{argon2}fixture"));
        System.out.println(classify(""));
    }
}
~~~

Compile and run with **JDK 17+**, no Spring required:

~~~bash
javac --release 17 HashShapeInspector.java
java HashShapeInspector
~~~

**Exact stdout:**

~~~text
PREFIXED_BCRYPT_SHAPE
RAW_BCRYPT_SHAPE
PREFIXED_OTHER_OR_MALFORMED
EMPTY
~~~

Why: `"$2a$10$"` is 7 characters and `"x".repeat(53)` makes 60; adding `"{bcrypt}"` (8 characters) makes 68. The function only checks prefix/length; it **does not replace `PasswordEncoder.matches` or verify real data integrity**. Never adapt `HashShapeInspector` to print or export real hashes to the console.

## 8. Spring Boot 3.5 / Spring Security 6.5: Complete Example Using One Encoder

This example builds a small Servlet application with:

- One unified `PasswordEncoder` bean: `PasswordEncoderFactories.createDelegatingPasswordEncoder()`.
- An in-memory `UserDetailsService` containing a lab user; the hash is encoded **once** on startup.
- Form login and HTTP Basic demonstrating both request types passing through the provider.
- Protected endpoint `GET /api/me` verifying the authenticated account.
- JUnit tests showing missing-prefix, wrong-password, double-encoding, and truncated hashes.

**Not a production account application:** passwords in the example are **synthetic local/test-only credentials**, with no database, reset/MFA/rate limiting. Use HTTPS and a secrets manager in real products. Never deploy the lab accounts and passwords below to an Internet-facing environment.

### 8.1. Gradle Dependencies

In `build.gradle` of a **Spring Boot 3.5.x** project, Java 17+ and the Boot BOM manage versions:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Do not mix a `spring-security-crypto` version different from the Spring Security runtime. If multiple dependencies override versions, check `./gradlew dependencyInsight` for the relevant module to avoid mixing 6.3/6.5 artifacts.

### 8.2. Application Configuration

File `src/main/java/example/encdiag/PasswordDiagnosticsApplication.java`:

~~~java
package example.encdiag;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PasswordDiagnosticsApplication {
    public static void main(String[] args) {
        SpringApplication.run(PasswordDiagnosticsApplication.class, args);
    }
}
~~~

File `src/main/java/example/encdiag/PasswordSecurityConfig.java`:

~~~java
package example.encdiag;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class PasswordSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        // Every registration/password change must also use this encoder.
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService labUserDetails(PasswordEncoder encoder) {
        // Lab data only; encode exactly once before storing.
        String encoded = encoder.encode("lab-only-correct-password-2026");

        UserDetails user = User.withUsername("student")
                .password(encoded)
                .roles("USER")
                .build();

        return new InMemoryUserDetailsManager(user);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated());

        http.formLogin(Customizer.withDefaults());
        http.httpBasic(Customizer.withDefaults());

        // Do not disable CSRF for form login; use HTTPS for Basic in production.
        return http.build();
    }
}
~~~

File `src/main/java/example/encdiag/WhoAmIController.java`:

~~~java
package example.encdiag;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/api/me")
    public String me(Authentication authentication) {
        return "me:" + authentication.getName();
    }
}
~~~

On startup, user `student` gets a hash generated by **`DelegatingPasswordEncoder`**; the string starts with `{bcrypt}`, though the bcrypt portion **varies across runs** due to the random salt. Do not hard-code a fixed sample hash as expected stdout.

### 8.3. Running and Testing with HTTP Basic

Run using the Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Windows: `gradlew.bat bootRun`. Call the public endpoint:

~~~bash
curl -i http://localhost:8080/public
~~~

Body:

~~~text
public
~~~

With **lab** Basic credentials:

~~~bash
curl -i -u student:lab-only-correct-password-2026 \
  -H "Accept: application/json" \
  http://localhost:8080/api/me
~~~

Successful response body:

~~~text
me:student
~~~

If the password is wrong, Basic typically returns HTTP **401**; with form login at `/login`, a wrong password typically redirects to `/login?error`. **Do not** log the `Authorization: Basic ...` header: Base64 trivially decodes back to username/password. Run commands containing these synthetic passwords only on localhost, never put real secrets in shell history.

## 9. JUnit: Distinguishing Missing ID, Right Encoder, Truncated Hash, and Double-Encoding

File `src/test/java/example/encdiag/PasswordEncodingDiagnosisTest.java`:

~~~java
package example.encdiag;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.crypto.password.Pbkdf2PasswordEncoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class PasswordEncodingDiagnosisTest {

    private static final String RAW =
            "synthetic-password-for-tests-2026";

    @Autowired
    MockMvc mvc;

    @Autowired
    PasswordEncoder appEncoder;

    @Test
    void delegatedBcryptHashContainsIdAndMatches() {
        String encoded = appEncoder.encode(RAW);
        assertTrue(encoded.startsWith("{bcrypt}"));
        assertTrue(appEncoder.matches(RAW, encoded));
        assertFalse(appEncoder.matches("wrong-password", encoded));
    }

    @Test
    void legacyRawBcryptNeedsFormatMigration() {
        BCryptPasswordEncoder legacy = new BCryptPasswordEncoder();
        String oldHash = legacy.encode(RAW);
        assertEquals(60, oldHash.length());
        assertTrue(legacy.matches(RAW, oldHash));

        PasswordEncoder delegated =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        // Default Delegating cannot find {id}.
        assertThrows(IllegalArgumentException.class,
                () -> delegated.matches(RAW, oldHash));

        // After confirming oldHash is valid bcrypt,
        // add proper {bcrypt} metadata in test data.
        assertTrue(delegated.matches(RAW, "{bcrypt}" + oldHash));
    }

    @Test
    void truncatedBcryptHashDoesNotVerify() {
        String full = appEncoder.encode(RAW);
        String truncated = full.substring(0, full.length() - 4);

        // Do not do this to production hashes; test uses fake data only.
        assertFalse(appEncoder.matches(RAW, truncated));
    }

    @Test
    void doubleEncodingIsNotTheSameAsEncodingRawOnce() {
        String once = appEncoder.encode(RAW);
        String twice = appEncoder.encode(once);

        assertTrue(appEncoder.matches(RAW, once));
        assertFalse(appEncoder.matches(RAW, twice));
        assertTrue(appEncoder.matches(once, twice));
    }

    @Test
    void pbkdf2VersionedIdMustMapToMatchingEncoder() {
        var pbkdf2 = Pbkdf2PasswordEncoder
                .defaultsForSpringSecurity_v5_8();

        String pbkdf2Hash = pbkdf2.encode(RAW);
        PasswordEncoder delegated =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        assertTrue(delegated.matches(
                RAW, "{pbkdf2@SpringSecurity_v5_8}" + pbkdf2Hash));
    }

    @Test
    void correctPasswordAuthenticatesWithHttpBasic()
            throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic(
                        "student", "lab-only-correct-password-2026"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(authenticated().withUsername("student"))
            .andExpect(content().string("me:student"));
    }

    @Test
    void wrongPasswordFailsHttpBasic()
            throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("student", "incorrect"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void sameHashWorksForFormLogin() throws Exception {
        mvc.perform(formLogin()
                .user("student")
                .password("lab-only-correct-password-2026"))
            .andExpect(status().is3xxRedirection())
            .andExpect(authenticated().withUsername("student"));
    }
}
~~~

There are **8 test methods**: five local `PasswordEncoder` checks and three HTTP tests through `SecurityFilterChain`. With the required dependencies/versions, all are expected to pass; do not claim Gradle ran in another environment without executing it.

Run tests:

~~~bash
./gradlew test --tests example.encdiag.PasswordEncodingDiagnosisTest
~~~

**What does each test prove?**

| Method | Proves | Does Not Prove |
| --- | --- | --- |
| `delegatedBcryptHashContainsIdAndMatches` | Current bean produces `{bcrypt}` and verifies that hash | Hashes in the real DB are not truncated |
| `legacyRawBcryptNeedsFormatMigration` | Raw BCrypt without prefix errors under Delegating; right prefix restores verification | Every raw production record is BCrypt |
| `truncatedBcryptHashDoesNotVerify` | Dropping the last 4 characters makes the test hash fail to match | Your DB actually suffered truncation |
| `doubleEncodingIsNotTheSameAsEncodingRawOnce` | Double-hashing makes raw input fail to verify like a single hash | Your real software double-encoded |
| `pbkdf2VersionedIdMustMapToMatchingEncoder` | Factory recognizes PBKDF2's versioned ID | Real system's custom PBKDF2 parameters match defaults |
| `correctPasswordAuthenticatesWithHttpBasic` | Demo provider/encoder + user store work via Basic | Production form, session, and DB are right |
| `wrongPasswordFailsHttpBasic` | Negative Basic credential test | All Basic errors are wrong passwords |
| `sameHashWorksForFormLogin` | Demo form login verifies hash through the filter | Cookies/redirects in a real browser work properly |

### 9.1. Why Not Create a `GET /debug/hash` Endpoint?

Some debugging shortcuts are convenient yet dangerous:

~~~java
// WRONG: never expose hashes on an endpoint, even if assumed internal.
@GetMapping("/debug/hash")
String getHash() {
    return userDetailsService.loadUserByUsername("student")
            .getPassword();
}
~~~

Even though a hash is not plaintext, it can be attacked offline and reveals algorithm/cost metadata. Account debugging must happen over secure channels with synthetic test data, without exposing hashes in responses, logs, or tickets. If you need to audit a real table, use an **aggregate** report returning only counts/lengths/algorithm IDs under controlled access.

### 9.2. Testing Real Hash Bugs Without Needing User Passwords

A practical staging approach:

1. Create a **canary account** with a synthetic test-only password.
2. Register through the real HTTP/Service path rather than creating hashes directly in tests bypassing the DAO.
3. Read metadata (algorithm ID/length) from the DB **without printing the hash**.
4. Verify login via form/Basic using the known canary password.
5. Restart the app and log in again against the same DB to confirm persistence.
6. Change work factor or deploy a version simulating migration; check backward compatibility.
7. Induce controlled faults on one canary record (drop prefix/truncate), restore the fixture, and verify tests fail for the right reason.
8. Confirm logs/traces contain no raw passwords, hashes, or full credentials.

**Never modify or "break" real users' records to test.** Every negative test needs fixtures and an isolated database; copying a production DB containing hashes/PII into local tests is a serious risk.

## 10. Migrating Safely From Old Hashes to `DelegatingPasswordEncoder`

There are three distinct data groups:

| Data Group | Strategy |
| --- | --- |
| Modern hashes **that already have the right ID** | Keep as-is, ensure matching map entry; plan rehash on successful login if needed |
| Unprefixed raw bcrypt **verified as valid** | Audited `{bcrypt}` metadata migration without plaintext; check column capacity |
| Unknown/corrupt/missing-pepper hashes | Never guess a prefix; need a verified legacy adapter or secure password reset |

### 10.1. Inventory Phase (Read-Only)

1. Summarize by length and prefix shape **without exporting full hashes**.
2. Review Spring versions and encoder configs used across historical phases.
3. Inspect DB schema, persistence mappings, collations, password columns, and ORM converters.
4. Identify affected accounts and a notification/recovery plan.
5. Check other legacy data sources: LDAP, JDBC, custom SSO, password reset services, mobile APIs.
6. Prepare a rollback plan and confirm nothing else writes hashes concurrently outside the migration.

### 10.2. Controlled Migration Phase

For a record **verified as raw bcrypt**:

~~~text
before = "$2a$10$..."        (60 chars)
after  = "{bcrypt}$2a$10$..." (68 chars)
~~~

This is **adding metadata**, not decrypting/re-hashing. Require a database transaction, backup, `WHERE` condition matching only the right records, row count verification, and canary validation. **Never run a single UPDATE across every non-null `password_hash` row**, because in a mixed-format system that corrupts users on PBKDF2/Argon2.

If a hash is legacy custom PBKDF2 with non-default secret/cost/salt, prepending `{pbkdf2@SpringSecurity_v5_8}` **just because it is named PBKDF2** does not guarantee verification; you need an adapter matching those exact parameters.

### 10.3. Online Rehash Phase to Upgrade Algorithm/Cost

When a user logs in successfully, the application holds the raw password in RAM for the **current request**. You can use `PasswordEncoder.upgradeEncoding(encodedPassword)` with Spring Security's `UserDetailsPasswordService` to update the hash under the new policy.

Spring Security 6.5 Javadoc includes:

- `PasswordEncoder.upgradeEncoding(String encodedPassword)`: asks the encoder whether the hash needs an upgrade.
- `UserDetailsPasswordService.updatePassword(UserDetails user, String newPassword)`: updates the user's encoded password.
- `DaoAuthenticationProvider#setUserDetailsPasswordService(UserDetailsPasswordService)`: attaches the service so the provider can upgrade password hashes after successful authentication per the implementation.

However, this does **not** mean merely defining a new `PasswordEncoder` bean upgrades every user's hash automatically. You need:

1. `DaoAuthenticationProvider` actually using the right encoder and password service.
2. The password service able to update the DB by **exact account ID**, with transactions/optimistic versioning where needed.
3. Separation between verifying old hashes and encoding new hashes.
4. Rehashing only after the password verifies, never trusting an email/account ID from the client.
5. Concurrency protection so concurrent logins do not overwrite a fresh password change.
6. No logging of raw passwords/hashes; audit logs record only event code `PASSWORD_HASH_UPGRADED` and algorithm version (when policy allows).

**If a password fails to verify**, online rehash cannot "guess" the raw password; fix the format metadata properly (if possible) or let the user reset it.

### 10.4. What About "Unknown Algorithm" Hashes?

Do not try every encoder arbitrarily and accept the first `true` result, as that creates an uncontrolled verification surface. Never switch to NoOp/unhashed storage to "stop the errors". Safe workflow:

- Flag affected records as `LEGACY_UNKNOWN`.
- Audit source/version/migration history and verify samples with canary data.
- If the algorithm/parameters are identified, write a unit-tested adapter.
- Otherwise, require a password reset via a single-use random token with appropriate identity checks.
- Track conversion rates and remove compatibility code once migration finishes.

## 11. BCrypt Parameters and Long-Input Warnings

BCrypt is a cost-adjustable password hashing algorithm. `BCryptPasswordEncoder` stores salt/cost inside the compact hash; changing `strength` for new encodes **does not necessarily** break verification of older hashes. Thus when a bcrypt user fails after a deploy, **do not rush to blame changing cost from 10 to 12**: check prefix, hash integrity, provider wiring, and password transformations.

### 11.1. Long-Input Limits and CVE-2025-22228

BCrypt has traditional input processing limits; Java/Spring implementations have version-specific behaviors. Spring published **CVE-2025-22228** on **March 19, 2025**: certain older `BCryptPasswordEncoder.matches` versions did not enforce the length cap properly, potentially allowing passwords sharing the same prefix to be treated as matching.

Advisory-affected versions include Spring Security 6.4.0–6.4.3, 6.3.0–6.3.7, and some older branches; open-source fixes include **6.4.4 and 6.3.8**. For 6.5, do not assume 6.5 is vulnerable by default; always inspect the actual advisory and dependency tree.

Key diagnostic points:

- Inputs exceeding the algorithm's processing/byte threshold can behave differently across libraries/versions.
- A single Unicode character can take multiple UTF-8 bytes.
- Never manually truncate passwords before hashing/verifying.
- If policy permits long passphrases, choose an appropriate encoder/config and test boundaries/surrogate pairs, not just `String.length()`.
- When upgrading Spring Security, run login tests for long passwords to detect semantic shifts and legacy risks.
- Rather than weakening checks to "let users log in", apply security patches and design safe password resets/migrations.

Consult the official advisory at the end of this lesson; do not use "72 characters" and "72 bytes" interchangeably, since charset/implementation affects behavior.

## 12. When the Password Is Right, but the Error Is Unrelated to the Encoder

### 12.1. Account Flags

`UserDetails` provides:

~~~java
boolean enabled = user.isEnabled();
boolean notLocked = user.isAccountNonLocked();
boolean credentialsValid = user.isCredentialsNonExpired();
boolean accountValid = user.isAccountNonExpired();
~~~

This snippet belongs in a method with a `UserDetails user` variable. If any required flag is false, the provider can reject login even when `PasswordEncoder.matches` would return true. Distinguish internal reasons and show only a generic message to unauthenticated clients.

### 12.2. Loading the Wrong Account via Username/Tenant

A multi-tenant app may have usernames that are not globally unique. If `UserDetailsService.loadUserByUsername` omits tenant scoping or looks up emails with inconsistent case-insensitivity, the provider loads **someone else's hash**. Check internal keys/canonical usernames, tenant-scoped lookups, and DB unique constraints; do not "fix" by changing encoders.

### 12.3. Different Security Filter Chains

An app may have:

- `/login` via form login.
- `/api/**` via Basic or Bearer.
- Admin endpoints via SSO.
- Multiple `AuthenticationManager` and `DaoAuthenticationProvider` beans.

A passing `PasswordEncoder.matches` unit test **does not prove** HTTP requests reach the right provider/encoder. To debug, test with `MockMvc` and Security filters enabled; verify the real endpoint's behavior and avoid `@WithMockUser` because it bypasses password checks.

### 12.4. CSRF, Authorization, MFA, and Sessions

When a form returns 403 due to missing CSRF, `DaoAuthenticationProvider` may not have been called. When the password verifies but MFA has not completed, the app must not grant full access. When login succeeds but a protected resource returns 403, the cause may be a missing role. When login redirects yet the next request returns to `/login`, it may be cookies/sessions/context persistence. Each failure needs an appropriate test; never alter a user's hash to work around a session bug.

## 13. Test Matrix to Verify Exact Failure Types

| ID | Scenario | Expected Result |
| --- | --- | --- |
| D01 | Correct raw password + valid `{bcrypt}` hash | `matches=true` |
| D02 | Wrong raw password + valid `{bcrypt}` hash | `matches=false` |
| D03 | Unprefixed raw bcrypt `$2a$...` with default Delegating | Missing `{id}` error |
| D04 | Same verified raw bcrypt with `{bcrypt}` added | Delegating verifies |
| D05 | Unmapped `{unknown}` prefix | Unmapped ID exception, no NoOp fallback |
| D06 | Right `{pbkdf2@SpringSecurity_v5_8}` prefix + matching PBKDF2 data | Verifies |
| D07 | PBKDF2 prefix prepended to a BCrypt tail | Rejected/format error; ID not treated as actual algorithm |
| D08 | Bcrypt hash truncated by 4 characters | `matches=false` |
| D09 | DB column `VARCHAR(60)`, app writes 68-char `{bcrypt}` | Blocked/truncated; migration must widen column |
| D10 | `CHAR(n)` pads spaces or mapper trims encoded hash | Detects roundtrip mismatch before/after DB |
| D11 | Password double-encoded | Raw password fails to verify `hash2` |
| D12 | Registration applies NFC, login does not | Test password with combining marks shows inconsistent results |
| D13 | Raw password trimmed/casefolded on one side | Can mismatch; do not fix by trimming blindly |
| D14 | `UserDetailsService` returns another tenant's hash | User mapping bug, not encoder |
| D15 | Account disabled/locked while password matches | Authentication rejected by account flags |
| D16 | `POST /login` missing CSRF | 403 before password check |
| D17 | Basic correct password + right hash | HTTP 200 protected |
| D18 | Basic wrong password | HTTP 401 (in matching chain) |
| D19 | Form correct password | Success redirect, principal authenticated |
| D20 | Test using `@WithMockUser` | Must not count as password verification |
| D21 | PBKDF2 pepper/iterations changed without versioning | Mismatch; needs adapter/version |
| D22 | BCrypt strength changed while old hashes stay intact | Verify backward compatibility rather than assuming failure |
| D23 | Hash overwritten during concurrent password change | Must not overwrite newer data; use optimistic locking |
| D24 | Deploy to node with different encoder config than another node | Detects inconsistent auth path |
| D25 | Cache holds stale `UserDetails` after password change | Login with new password may fail until invalidation |
| D26 | Password reset updates wrong column / uncommitted tx | Hash does not match new request |
| D27 | Unidentifiable legacy hash | Route to password-reset flow, never set NoOp |
| D28 | Logs contain raw password/hash from failed test | QA FAIL, remove sensitive data |
| D29 | Library upgraded past BCrypt long-input patch | Test boundaries/long passwords and plan migration |
| D30 | Canary tested via REST and same account via form | Expected behavior per chain; do not infer from `matches` alone |

The goal is not to force every user login to succeed at all costs, but to **locate the exact root cause and restore correctness without lowering security**.

## 14. Symptom-Based Troubleshooting

| Symptom | What to Check | Remediation Direction |
| --- | --- | --- |
| `id "null"` after deploy | Do legacy hash strings start with `{id}`? | Inventory; prefix-only migration for verified formats |
| `id "pbkdf2@SpringSecurity_v5_8"` unmapped | Does the versioned encoder map entry exist? | Add the exact mapping; check dependencies |
| `Encoded password does not look like BCrypt` | Does the tail after prefix match bcrypt shape/length? | Check `VARCHAR`/`CHAR`, wrong prefix, double encoding |
| Right password gives `matches=false` on canary | Double-encoded, different normalization, truncated hash? | Test across registration/DB/login; fix pipeline |
| All users fail after bean change | Switched from BCrypt to Delegating or vice versa? | Restore compatible config, run audited migration |
| Only legacy users fail | Mixed hash formats and missing IDs? | Segment cohorts, migrate/upgrade per group |
| Only Unicode passwords fail | Charset/normalization/trimming differs across ends | Define unified policy and legacy migration |
| User changed password yet old password still works | User store cache, uncommitted transaction, concurrent update | Check cache invalidation/DB versioning and audit |
| User changed password and **cannot** log in with new one | Hash written to wrong column, encoder mismatch, mapper truncation | Trace canary through service/repository without logging secrets |
| One replica logs in, another replica fails | Different encoder secret/config/BOM/datasource | Compare config versions, secrets, shared DB |
| `encoder.matches` test passes but form login fails | Different `UserDetailsService`/account state/provider chain | Test HTTP on real path + filter chain |
| Right password, yet POST login returns 403 | Missing CSRF, access denied | Check CSRF and HTTP method |
| Right password, yet API returns 403 after login | Missing authority/role | Check authorization, do not reset hash |
| Error disappears when using `{noop}` | Bypassing hash security rather than fixing config | Remove NoOp, perform migration/reset |
| Cannot decrypt hash back to old password | One-way hashing working as designed | Reset/re-encode when a valid password is supplied |

## 15. Production Remediation Checklist

- [ ] Identify the actual endpoint, filter chain, provider, and `UserDetailsService` executing.
- [ ] Distinguish 401/403/302 from missing-prefix exceptions and `matches=false`.
- [ ] Never ask users for raw passwords/hashes; never log secrets/`Authentication` objects.
- [ ] Have one clear new-encoding configuration and clear legacy verification mappings.
- [ ] DB column is wide enough with no silent truncation/padding; serializers preserve hashes across roundtrips.
- [ ] `{id}` prefix matches the tail algorithm; never swap IDs to "change algorithms".
- [ ] Never use `NoOpPasswordEncoder`/fallbacks for unknown production hashes.
- [ ] For legacy raw bcrypt: add `{bcrypt}` only after verifying cohort/format, with backups and rollback.
- [ ] For PBKDF2/scrypt/Argon2: preserve exact parameters/secrets/IDs from encode time.
- [ ] Registration, password change, reset, and login share consistent normalization/password handling.
- [ ] Never double-encode; `UserDetails.getPassword()` returns the right encoded field.
- [ ] Canary tests pass over HTTP, DB persistence, restarts, multiple nodes, and migrations.
- [ ] Account flags, tenant lookups, CSRF/MFA/authorization/sessions verified independently.
- [ ] Have a `UserDetailsPasswordService`/`upgradeEncoding` process when online rehashing is desired.
- [ ] Provide secure password reset if hashes cannot be recovered/identified.
- [ ] Test Unicode/long passwords and handle BCrypt versions and security advisories properly.
- [ ] Logs/audits record only category codes and correlation IDs, never credentials or hashes.

## 16. Self-Check Questions

1. Which argument position of `PasswordEncoder.matches` takes the raw password?
2. Why is `encoder.encode(raw).equals(storedHash)` usually wrong?
3. Is `{bcrypt}` part of the bcrypt salt or Spring Delegating metadata?
4. Raw bcrypt starts with `$2a$10$`; why can default Delegating report `id "null"`?
5. Why can a `VARCHAR(60)` column hold raw bcrypt yet fail to hold `{bcrypt}` + bcrypt?
6. Why does prepending `{pbkdf2}` to a bcrypt tail not turn it into PBKDF2?
7. In what scenario does `setDefaultPasswordEncoderForMatches` introduce risk?
8. If `PasswordEncoder.matches` is true yet form login still fails, what do you check next?
9. Does adding a prefix to a verified legacy hash require knowing the raw password?
10. What does migrating from bcrypt to Argon2/PBKDF2 **actually** require?
11. Why must you check both Unicode normalization and password byte length?
12. Does `UserDetailsPasswordService` start working automatically just from creating a `PasswordEncoder` bean?
13. In production, when a hash cannot be identified, what is the safe recovery path?
14. Does a 200 response from a `@WithMockUser` test prove the password encoder works?
15. Should you log encoded passwords to compare two failed login attempts?

**Suggested Answers:** (1) first argument; (2) random salt; (3) metadata; (4) missing `{id}`; (5) 60 vs 68 characters; (6) changes only the label, not the algorithm; (7) NoOp/unvalidated format fallback; (8) account state, provider, MFA, session, CSRF; (9) no, once the format is verified; (10) verify the raw password then re-encode, or reset; (11) characters/code points/bytes differ and affect hashing; (12) no, provider and service must be configured properly; (13) trusted password reset; (14) no, mock user skips password checking; (15) no.

## 17. References

- [Spring Security 6.5 — Password Storage / DelegatingPasswordEncoder](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 6.5 — DelegatingPasswordEncoder API](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/DelegatingPasswordEncoder.html)
- [Spring Security 6.5 — PasswordEncoderFactories API](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/crypto/factory/PasswordEncoderFactories.html)
- [Spring Security 6.5 — DaoAuthenticationProvider API](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html)
- [Spring Security 6.5 — UserDetailsPasswordService API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetailsPasswordService.html)
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 — Testing Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/form-login.html)
- [Spring Security 6.5 — Testing HTTP Basic](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html)
- [Spring Security — CVE-2025-22228 / BCryptPasswordEncoder input length](https://spring.io/security/cve-2025-22228/)
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)

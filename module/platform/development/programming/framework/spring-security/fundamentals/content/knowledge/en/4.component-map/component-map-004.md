# PasswordEncoder in Password Storage and Verification

Imagine a Spring Security application with account registration and username/password login. When Mai registers, the server receives the password she just entered. Later, Mai logs in using that password. The server needs to check whether the information Mai provides is correct, yet **must not store the raw password in the database**.

`PasswordEncoder` is Spring Security's contract for this job: **converting a password into a stored value using an appropriate one-way function**, and **checking a user-submitted password against the stored value**. The result is commonly called a *password hash*, although modern password-storage algorithms also incorporate a salt and computational parameters.

To understand it properly, separate three stages:

- **Registration or password change:** call `encode(rawPassword)` to generate the value to store.
- **Login:** call `matches(rawPassword, encodedPassword)` to verify, where `encodedPassword` comes from trusted storage.
- **Upgrading storage:** evaluate `upgradeEncoding(encodedPassword)` right after the user has proven the password is valid, then generate a new hash if policy allows.

`PasswordEncoder` is not a login controller, does not mint JWTs, does not assign authorities itself, and does not directly decide which URLs a user may access. It provides password protection/verification operations for authentication components.

## 1. Why Not Store Raw Passwords?

If a user table stores:

~~~text
username | password
---------+----------------
mai      | MySecret@2026
an       | AnotherSecret!
~~~

then anyone or any breach that reads that table sees every password. Risk also spreads to other services if users reuse passwords.

The design to aim for is:

~~~text
username | password_hash
---------+-------------------------------------------------
mai      | {bcrypt}$2a$...<hash and required metadata>
an       | {bcrypt}$2a$...<hash and required metadata>
~~~

The strings above merely **illustrate the data shape**, not valid hashes for production use. In reality, the encoder generates a salt and hash value with its own format.

### Password Hashing Differs from Reversible Encryption

| Approach | Goal | Reversible with a key? | Suitable for storing login passwords? |
| --- | --- | --- | --- |
| Storing plaintext | Keep exact text | No decryption needed | **No** |
| Base64/hex | Change representation | Trivial to recover | **No** |
| Symmetric encryption | Let a key holder decrypt | Yes | Usually **unnecessary** for user passwords |
| Plain SHA-256 | Fast hash function, useful for other tasks | No direct decryption | **Should not** be used alone to store passwords |
| Adaptive password hashing such as bcrypt, scrypt, Argon2id, or PBKDF2 with proper parameters | Make guessing passwords expensive | No normal decryption | **Yes**, when configured properly |

Even though a one-way hash cannot be "decrypted" like ciphertext, an attacker can still **guess** passwords and test each candidate locally. That is why picking any arbitrary hash function is not enough: the algorithm must be **deliberately resource-intensive** to slow down bulk guessing.

Fast hashes such as SHA-256 have valid uses in integrity checks, signatures, and content addressing. The problem is **excessive speed** when used directly to protect a human-chosen secret.

## 2. Where PasswordEncoder Sits in the Spring Security Map

A servlet password-authentication flow can be understood as follows:

~~~text
       REGISTRATION                              LOGIN
              |                                    |
     User enters password                 User enters password
              |                                    |
              v                                    v
   App validates policy                  Authentication request
              |                                    |
              v                                    v
     PasswordEncoder.encode               AuthenticationManager
              |                                    |
              v                                    v
      password_hash string               DaoAuthenticationProvider
              |                                    |
              v                            +-------+-------+
       Save in database                    |               |
                                      UserDetailsService   PasswordEncoder
                                      loads UserDetails    .matches(raw, hash)
                                      and password hash    |
                                                   +-------+
                                                   |
                                           Verification succeeded?
                                              /           \
                                            Yes            No
                                             |              |
                                      Trusted          Authentication
                                      Authentication   failure (usually exception)
                                             |
                                             v
                                      Check authorization
                                      for action/resource
~~~

Roles of each piece:

- **`PasswordEncoder`:** performs `encode` and `matches`; does not know which roles a user has.
- **`UserDetailsService`:** looks up user information from a trusted source, including the **stored hash**; this interface itself is not responsible for verifying passwords.
- **`DaoAuthenticationProvider`:** implements `AuthenticationProvider`, using `UserDetailsService` and `PasswordEncoder` to authenticate a username/password pair.
- **`AuthenticationManager`**, commonly implemented by `ProviderManager`: coordinates configured providers.
- **`Authentication`:** represents an authentication request or result.
- **Authorization:** after authentication, the system evaluates permissions such as `ROLE_USER`, `DOC_READ`, data policies, etc.

When a user enters the wrong password, the `matches` step fails to verify it. In a standard flow, the provider reports failure via an `AuthenticationException`, such as `BadCredentialsException`; do not picture `PasswordEncoder` returning an HTTP 401 response or redirecting to a login page by itself. That responsibility belongs to the request/authentication handling layers.

`PasswordEncoder` is used when a mechanism **actually authenticates using passwords**. An API that only verifies a JWT or digital certificate may use other authentication components and never call `PasswordEncoder` per request.

## 3. The PasswordEncoder Contract: Three Methods

This key interface lives in package `org.springframework.security.crypto.password.PasswordEncoder`:

~~~java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);
    boolean matches(CharSequence rawPassword, String encodedPassword);
    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
~~~

This is an **abbreviated signature for learning the API**, not a full source copy for every version. Distinguish its methods:

| API | Input | Result | When to use |
| --- | --- | --- | --- |
| `encode(raw)` | Unhashed password | String to store, typically containing salt/metadata per algorithm format | Registration, password change/reset, valid rehash |
| `matches(raw, stored)` | Newly submitted password and **stored string** | `true` if matched, `false` otherwise; misconfiguration may throw an exception | Verifying the current password |
| `upgradeEncoding(stored)` | Stored string | `true` if the implementation advises re-encoding for stronger protection | Assessing upgrade need after the password is verified |

**Crucial: the parameter order of `matches`.** First is the **raw password just submitted by the user**, second is the **encoded password from the database**:

~~~java
boolean ok = passwordEncoder.matches(submittedPassword, storedHash);
~~~

Common mistakes:

~~~java
// WRONG: never compare two encode calls with equals.
boolean ok = passwordEncoder.encode(submittedPassword).equals(storedHash);

// WRONG: reversed parameter order.
boolean ok2 = passwordEncoder.matches(storedHash, submittedPassword);
~~~

Why the first one fails: a modern `PasswordEncoder` can generate a **random salt on every encode call**. The same raw password can yield two different hash strings that are both valid; `matches` knows how to parse the stored format and apply the right salt and parameters to verify.

### `matches` Does Not Decrypt the Password

Conceptual model:

~~~text
User enters:          "MySecret@2026"
Database holds:       "{bcrypt}$2a$..."
PasswordEncoder:
  - reads format/salt/parameters from the stored value
  - runs verification algorithm against the submitted password
  - determines match/mismatch

Returns: true or false
~~~

`matches` does not recover the original password from the hash. Therefore, when a user forgets their password, the application **never sends back the old password**: it needs a reset flow with proper proof and token, then calls `encode` on the new password.

## 4. How Salt and Work Factor Protect Password Hashes

A strong password-storage algorithm typically includes two factors:

**Salt:** a different random value for each hashing operation, ensuring two users with the same password receive different hashes and defeating precomputed lookup tables. The salt is normally stored alongside the hash output according to the algorithm's format. **A salt does not need to be kept secret like a password**, though it must be random and unique with high probability.

**Work factor (computational cost):** parameters making encoding and verification deliberately consume time or memory. An attacker holding the hash database finds it much harder to test massive candidate lists. Settings must be chosen by benchmarking on real servers to balance security, login latency, and overload/DoS risk.

For example with bcrypt, the output typically includes version, cost, salt, and hash body. In `$2a$10$...`, `10` represents the cost factor. Spring Security's `BCryptPasswordEncoder` supports setting strength/cost within the range defined by that class; raising cost makes verification more resource-intensive. You do not need to generate and store a separate salt for standard `BCryptPasswordEncoder`: the encoder handles that for you.

When choosing an algorithm, consider current security guidance and system constraints:

| Algorithm | Key properties | Implementation notes |
| --- | --- | --- |
| Argon2id | Configurable time and memory parameters; well suited against parallel hardware attacks | Requires compatible libraries/implementations; verify config and real cost |
| scrypt | Configurable memory and computational cost | Balance memory usage against concurrent requests |
| bcrypt | Widely adopted, uses salt and cost, used by many existing applications | Watch out for the ~**72-byte** input limit in many implementations; define a clear password/migration policy |
| PBKDF2 | Based on iterated PRF rounds such as HMAC | Choose appropriate variant and iteration count, especially for FIPS compliance |

In Spring Security, `DelegatingPasswordEncoder` lets you use one algorithm for new passwords while still recognizing verified legacy hash formats. **Do not equate Spring Security supporting an algorithm with every default setting being optimal for your application.** Evaluate security requirements, framework version, and deployment environment characteristics.

**On bcrypt and Unicode:** user passwords may contain multi-byte UTF-8 characters. A byte-based limit differs from a "character count" limit. If your system must support long passwords, verify how the library and algorithm handle input bytes and set an appropriate policy upfront.

## 5. Registration Flow: Hash Immediately Before Saving

Suppose a registration API receives:

~~~http
POST /api/register HTTP/1.1
Content-Type: application/json

{"username":"mai","password":"MySecret@2026"}
~~~

Processing model:

1. Receive input over HTTPS and validate reasonable constraints: length, breached-password lists if available, business rules, and resource limits.
2. Never put the raw password into logs, error messages, monitoring events, response bodies, or `toString()` outputs.
3. Call `passwordEncoder.encode(rawPassword)` in a trusted service layer.
4. Save **only the encoded/hash string** in the password column, associated with the user identifier.
5. Never return the hash to the client. Return account creation status or trigger verification flow according to policy.

A basic schema could look like:

~~~sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    username VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL
);
~~~

This is an example schema for understanding the flow, omitting auto-generated keys, email, account status, and other columns. The capacity of `password_hash` must fit the **actual algorithm and format**, including any `{id}` prefix; when changing algorithms, re-verify the column length limit.

Illustrative logic inside a Spring service injected with `PasswordEncoder` and a repository:

~~~java
// Illustrative snippet inside a service, not a standalone runnable class.
public void register(String username, String rawPassword) {
    validatePasswordPolicy(rawPassword);
    ensureUsernameAvailable(username);

    String encoded = passwordEncoder.encode(rawPassword);
    accountRepository.save(new Account(username, encoded));
}
~~~

`validatePasswordPolicy`, `ensureUsernameAvailable`, `accountRepository`, and `Account` are **application-defined** components. The key point is never storing raw passwords or manually using SHA-256/Base64 where `PasswordEncoder` belongs.

If the application creates accounts via batch imports, admin tools, or seed scripts, **every password-creation path must follow the same policy**. Even a few `password_hash` rows containing plaintext break login consistency and security.

## 6. Login Flow: Load Hash and Call `matches`

For account `mai`, the database holds the `{bcrypt}...` value created during registration. When Mai submits `POST /login`:

~~~text
Browser sends username + rawPassword
             |
             v
UsernamePasswordAuthenticationFilter or equivalent
             |
             v
AuthenticationManager
             |
             v
DaoAuthenticationProvider
   |                         |
   +--> UserDetailsService --> UserDetails.getPassword()
   |                          must hold encoded/hash from DB
   |
   +--> PasswordEncoder.matches(rawPassword, storedHash)
             |
       +-----+-----+
       |           |
     true         false
       |           |
Create result     Report auth failure
Authentication    and handle via security flow
~~~

Key takeaway when writing your own `UserDetailsService`: `UserDetails#getPassword()` must return the **stored hash** matching `PasswordEncoder`. Never call `encode` every time a user is queried, as that would hash the old hash or break authentication.

Snippet illustrating only the mapped data:

~~~java
// Inside an application-implemented UserDetailsService.
Account account = accountRepository.findByUsername(username)
        .orElseThrow(() -> new UsernameNotFoundException("User not found"));

return User.withUsername(account.getUsername())
        .password(account.getPasswordHash()) // Already hashed; DO NOT re-encode.
        .authorities("ROLE_USER")
        .build();
~~~

`Account` and `accountRepository` in this snippet are application-defined; `User` is `org.springframework.security.core.userdetails.User`. The role is only an example; not every account has `ROLE_USER`.

**Do not return overly detailed errors to the client.** Distinguishing "username does not exist" from "wrong password" can leak account existence. Design uniform login error handling with rate limiting and guessing detection.

### When `matches` Returns `false`

`matches` checks the password against the stored string according to the configured algorithm. `false` means mismatch, **not** a hint that the server should re-hash and overwrite the database. Only after successful verification with a clear upgrade reason should the application consider replacing the old hash.

If the stored hash is corrupted, has the wrong prefix, or lacks a matching algorithm, some implementations (especially `DelegatingPasswordEncoder`) may throw an exception. Investigate the data/config mismatch; never "fix login errors" with `NoOpPasswordEncoder` in production.

## 7. DelegatingPasswordEncoder: Recognizing Algorithms via Prefix

Spring Security supports `DelegatingPasswordEncoder` to **read older formats** while **generating new hashes with the selected algorithm**. A common configuration can be obtained via:

~~~java
PasswordEncoder encoder =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();
~~~

Imports are `org.springframework.security.crypto.password.PasswordEncoder` and `org.springframework.security.crypto.factory.PasswordEncoderFactories`.

General storage format:

~~~text
{id}encodedPassword

Spring Security examples:
{bcrypt}$2a$10$...
{pbkdf2}...
{scrypt}...
{argon2}...
~~~

**`{id}` is the algorithm label used to select the delegate**, and the remainder is formatted per the corresponding algorithm. `{bcrypt}` is not a salt, not a role, and must not be understood as "an encrypted password that can be decrypted".

With `PasswordEncoderFactories.createDelegatingPasswordEncoder()` in the Spring Security 6.5 branch, the default encoder uses **bcrypt to encode new passwords**, so outputs start with `{bcrypt}`. When verifying, `DelegatingPasswordEncoder` reads `{id}` from the old hash and selects the matching implementation to compare.

Interpretation examples:

| String in database | Encoder that may be chosen | Condition |
| --- | --- | --- |
| `{bcrypt}$2a$...` | `BCryptPasswordEncoder` | Mapping includes id `bcrypt` |
| `{pbkdf2}...` | `Pbkdf2PasswordEncoder` | Mapping includes matching id `pbkdf2` |
| `{noop}demo-only` | `NoOpPasswordEncoder` | **Only for reading sample/legacy data**; strictly never create new entries like this in production |
| `$2a$10$...` without `{bcrypt}` | Default id unknown | May throw `IllegalArgumentException` due to `id="null"` |

Legacy bcrypt hashes lacking `{bcrypt}` are a common migration issue. Once you have verified with certainty that every record in that dataset is genuinely a bcrypt hash, you can plan to **prepend the exact prefix** on verified records or configure compatibility reading during the transition period. Never blindly prepend `{bcrypt}` to strings of unknown origin, and never leave an uncontrolled fallback for arbitrary unknown hash types.

Remember: `PasswordEncoderFactories` supports certain **legacy** formats to aid migration. The fact that an encoder can `matches` against `{noop}` does not make storing plaintext passwords safe. After valid authentication, migrate gradually to a strong hashing function.

## 8. Runnable Java 17+ Example: `encode`, `matches`, and Detecting Legacy Hashes

The following example uses Spring Security classes directly. To produce deterministic output, the program **does not print random hash strings**; it prints only the prefix check, `matches` results, and detection of data needing upgrade.

Create `build.gradle` in a standalone Gradle practice directory:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'
}

application {
    mainClass = 'PasswordEncoderDemo'
}
~~~

`spring-security-core` pulls in `spring-security-crypto`, which contains `PasswordEncoder`. Version 6.5.11 pins the standalone example. In real Spring Boot projects, use `spring-boot-starter-security` and let Spring Boot manage compatible versions.

Create `src/main/java/PasswordEncoderDemo.java`:

~~~java
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

public class PasswordEncoderDemo {

    public static void main(String[] args) {
        PasswordEncoder encoder =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        String submitted = "Demo-password@2026";
        String stored = encoder.encode(submitted);

        // Never print rawPassword or stored hashes to real logs.
        System.out.println("bcrypt prefix=" + stored.startsWith("{bcrypt}"));
        System.out.println("raw stored=" + submitted.equals(stored));
        System.out.println("correct password=" + encoder.matches(submitted, stored));
        System.out.println("wrong password="
                + encoder.matches("not-the-password", stored));

        // Legacy data ONLY to demonstrate migration capability.
        // Never store new passwords in {noop} form.
        String legacy = "{noop}migration-only-demo";
        System.out.println("legacy matches="
                + encoder.matches("migration-only-demo", legacy));
        System.out.println("legacy needs upgrade="
                + encoder.upgradeEncoding(legacy));
    }
}
~~~

Run with JDK 17+ and Gradle installed, from the directory containing `build.gradle`:

~~~bash
gradle run --quiet
~~~

Output from `println`:

~~~text
bcrypt prefix=true
raw stored=false
correct password=true
wrong password=false
legacy matches=true
legacy needs upgrade=true
~~~

Explanation:

1. `createDelegatingPasswordEncoder()` chooses bcrypt to generate new hashes, labeled `{bcrypt}`.
2. The stored string differs from the original password, yet `matches(submitted, stored)` still succeeds using the embedded algorithm/salt.
3. Given the wrong password, `matches` returns `false`.
4. The legacy `{noop}...` example can still be read via its matching mapping, and `upgradeEncoding` signals an upgrade is needed because the old id is not the encoder used for new hashes.

This illustration **has no account registration, no real user authentication, no database storage, and no authorization**. It isolates the three core operations of `PasswordEncoder` for study. Accepting `{noop}` here only demonstrates reading legacy data; it is strictly not a recommendation to use `{noop}` in production.

Every `encode` call with a random salt can produce a different output. Therefore, **never copy a specific sample hash and expect the program to reproduce it character-for-character**.

## 9. Configuring PasswordEncoder in a Spring Boot Application

In a Spring Boot project with `spring-boot-starter-security`, a bean declaration can look like:

~~~java
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
~~~

A shared bean ensures hashing logic and authentication logic adhere to the same format contract. Avoid creating three incompatible encoders in different places: for example, a registration API hashing with plain `BCryptPasswordEncoder` without prefixes while the login provider uses `DelegatingPasswordEncoder` expecting `{id}`. Both sides must be designed/mapped consistently.

With Spring Security servlet 6.5, `DaoAuthenticationProvider` can use the configured `UserDetailsService` and `PasswordEncoder` during authentication. Example of a **non-standalone** configuration fragment inside a `@Configuration` when assembling `AuthenticationManager` manually:

~~~java
@Bean
AuthenticationManager authenticationManager(
        UserDetailsService userDetailsService,
        PasswordEncoder passwordEncoder) {

    DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(userDetailsService);
    provider.setPasswordEncoder(passwordEncoder);

    return new ProviderManager(provider);
}
~~~

`DaoAuthenticationProvider`, `ProviderManager`, `AuthenticationManager`, and `UserDetailsService` belong to their corresponding Spring Security packages. The code still needs imports, beans/repositories, and application security config. Most Spring Boot projects let Spring Security auto-configure the provider; you do not always need to declare `AuthenticationManager` manually.

### Why Can BCryptPasswordEncoder and DelegatingPasswordEncoder Cause Confusion?

These two lines do not produce the same **stored string**:

~~~java
String a = new BCryptPasswordEncoder().encode("secret");
String b = PasswordEncoderFactories.createDelegatingPasswordEncoder()
        .encode("secret");
~~~

`a` normally starts with `$2a$`, `$2b$`, or `$2y$` depending on the algorithm version; `b` has the **`{bcrypt}` prefix** prepended to the bcrypt output. Both may use bcrypt under the hood, yet require a compatible encoder when verifying.

Do not expect `a.equals(b)` because of random salts; never use a hash string as a password lookup key.

## 10. Password Change, Password Reset, and Hash Upgrades

### Changing Password When the User Knows Their Current Password

A secure password-change flow typically includes:

1. Ensuring the request comes from an authenticated account and passes CSRF checks if cookies are sent automatically.
2. Verifying the current password via `matches(oldRaw, storedHash)` or performing an equivalent identity re-verification per policy.
3. Validating the new password against policy (length, breached passwords, disallowing reuse of the old password if required).
4. Calling `encode(newRaw)` and saving the new hash within an appropriate transaction.
5. Invalidating active sessions/tokens on other devices if policy requires, sending a security notification, and logging an audit event **containing no password**.

Forgot-password is a separate flow: verify the requester with a **random, short-lived, single-use** reset token, then let them set a new password; there is no "decrypt hash to email back the old password" operation.

### `upgradeEncoding` Helps Migrate Without Knowing the Prior Password

Suppose the database still holds hashes created with older parameters. When a user logs in successfully, the server momentarily holds the raw password *briefly* from a valid request. That is the right moment to:

~~~java
// Pseudocode inside an already-succeeded authentication flow.
if (passwordEncoder.matches(rawPassword, storedHash)
        && passwordEncoder.upgradeEncoding(storedHash)) {

    String upgradedHash = passwordEncoder.encode(rawPassword);
    accountRepository.updatePasswordHashIfUnchanged(
            userId, storedHash, upgradedHash);
}
~~~

This is an **illustrative snippet**: the application must define `accountRepository`, protect transactions, and update conditionally so a password changed concurrently in another request is not overwritten. Remember to handle the raw password sensitively and never retain it longer than needed.

`upgradeEncoding` only **signals the need**; it does not mean the framework always updates the database automatically when called. With `DaoAuthenticationProvider`, Spring Security has built-in hash-upgrade support when a suitable `UserDetailsPasswordService` is provided; configure and test that path explicitly. If you write a custom authentication mechanism, you are responsible for upgrading safely yourself.

### Migration Plan for Legacy Data

- **Classify and verify** existing hash formats: unprefixed bcrypt, legacy PBKDF2, internal formats, or unprotected data.
- **Configure compatible matching** during the transition window, strictly scoping which types may be read; never open arbitrary fallbacks.
- **New passwords** are always created using the current policy. **Old passwords** are upgraded when users prove the right password, or reset when there is no safe way to verify them.
- **Track migration progress with non-sensitive metadata**, such as algorithm version, never logging raw passwords or hashes.
- **Monitor login failure rates** during rollout; never fix `There is no PasswordEncoder mapped for the id "null"` by forcing all passwords into `noop`.

When old hashes were created by a one-way function, you cannot recover raw passwords in bulk to re-encode offline. Standard practice is upgrading upon successful authentication or via verified reset flows.

## 11. Security Requirements Beyond PasswordEncoder

Using the right algorithm is **not enough** to secure an entire login system. Several risks exist at other layers:

| Risk | Appropriate mitigation |
| --- | --- |
| High-volume online password guessing | Rate limiting, monitoring, sensible lockout/backoff policies, and MFA where required |
| Database hash leak | Adaptive password hashing with salt and strong parameters; restrict read access, encrypt backups, and monitor |
| Password leaked via logs/traces | Never log login/register request bodies; filter sensitive fields |
| Improper HTTPS usage | Enable properly configured TLS to mitigate password eavesdropping in transit |
| Hash exposed via API | Never return `passwordHash` in DTOs/JSON, exceptions, or audit logs |
| Weak legacy password data | Migrate/re-hash upon verification; secure reset if necessary |
| Password processing exhausts CPU/RAM | Benchmark hashing cost and limit concurrent authentication attempts; detect abuse |
| Authenticated account accessing unauthorized data | Dedicated authorization rules for URLs, methods, objects, and tenant boundaries |

An advanced technique is a **pepper**, a shared secret managed **separately from the database** to add defense-in-depth if the hash database leaks. A pepper is not a salt. Adding a pepper requires a vetted design, secure secret storage, and a rotation plan; **never concatenate a hardcoded string to passwords** and assume it replaces adaptive hashing.

If specific compliance standards or heavy throughput requirements apply, consult current password guidelines and benchmark on your target environment before choosing Argon2id/scrypt/bcrypt/PBKDF2 and their parameters.

## 12. Common Mistakes

1. **Storing raw passwords to compare later.** Anyone with database read access can see passwords; unacceptable.
2. **Thinking Base64 is password encryption.** Base64 is reversible encoding; not password hashing.
3. **Using plain SHA-256 directly to store user passwords.** It is far too fast for resisting offline password guessing.
4. **Comparing `encode(raw).equals(stored)`.** With random salts, two encode calls differ; always use `matches`.
5. **Swapping `matches` arguments.** The right order is `matches(rawPassword, storedEncodedPassword)`.
6. **Calling `encode` on the DB hash every time a user is loaded.** Stored hashes must not be re-encoded; `UserDetails` must carry the original DB hash.
7. **Mixing plain `BCryptPasswordEncoder` with `DelegatingPasswordEncoder` without handling `{id}`.** Storage formats differ; plan compatibility explicitly.
8. **Using `NoOpPasswordEncoder` in production.** Storing unprotected passwords is wrong; legacy mapping is strictly for migration.
9. **Assuming `upgradeEncoding=true` updates the database automatically.** You must have a safe update flow/configuration.
10. **Cranking strength too high without benchmarking.** Can cause severe latency or CPU exhaustion; tune parameters on real hardware.
11. **Keeping hashes on the frontend for "fast verification".** Hashes remain sensitive data, and the client must never make authentication decisions for the server.
12. **Assuming a valid login grants access to all data.** `PasswordEncoder` only verifies passwords; authorization handles permissions.
13. **Copying hardcoded demo passwords into production.** Teaching samples are not how real apps obtain or manage secrets.
14. **Writing custom salt + hash routines instead of using vetted libraries.** Easy to get formats, byte handling, constant-time comparison, and upgrade paths wrong.

## 13. Password Lifecycle Testing Checklist

| Scenario to test | Expectation |
| --- | --- |
| Successful registration | Database stores only a valid hash/format, never the raw password |
| Two accounts with the same password | Can receive different hashes due to salting |
| Login with right password | `matches` returns true; authentication succeeds when account status is valid |
| Login with wrong password | No trusted `Authentication` is created |
| Empty/null password or exceeding allowed limits | Handled per input and API policy without leaking information |
| Corrupted hash or missing `{id}` with Delegating | Controlled error handling with a migration plan |
| Successful password change | New hash replaces old hash; old password can no longer log in |
| Password reset | Reset token valid within window, single-use; new hash uses current policy |
| Legacy hash flagged for upgrade | Upgraded after verification via conditional update |
| Accessing another user's account despite valid login | Still denied when lacking resource-level authorization |
| Inspecting logs/request traces in test environment | No raw passwords, reset tokens, or sensitive hashes appear |

Testing note: because hashes use random salts, tests should never assert an exact hardcoded bcrypt string returned by `encode`. Assert the expected format, that `matches(raw, encoded)` succeeds, and that `matches(wrong, encoded)` fails.

## 14. Self-Check Questions

**Question 1.** Two users enter the same password. Why can the hashes stored in the database differ?

*Answer:* Because modern password hashing uses a random salt per encode operation; the verifier knows how to read the salt from the stored string to check it.

**Question 2.** During login, should the program call `passwordEncoder.encode(raw).equals(storedHash)` or `passwordEncoder.matches(raw, storedHash)`?

*Answer:* Call `matches(raw, storedHash)`. That is the API with the right verification contract for stored hashes/salts.

**Question 3.** When `DelegatingPasswordEncoder` sees `{bcrypt}$2a$...`, what does `{bcrypt}` mean?

*Answer:* It is the id selecting the appropriate delegate; the remainder is parsed in bcrypt format. It is not a decryptable password.

**Question 4.** The database holds legacy bcrypt strings without `{bcrypt}`. Why might a default `DelegatingPasswordEncoder` report `id="null"`?

*Answer:* It needs the `{id}` prefix to choose an encoder. Migration must rely on verified actual formats; never enable blanket fallbacks for arbitrary unknown strings.

**Question 5.** When `upgradeEncoding(hash)` returns true, what should you do to upgrade?

*Answer:* Only after the user's password has been validly verified, use the raw password briefly to generate a new hash and update safely; `UserDetailsPasswordService` can integrate this with `DaoAuthenticationProvider`.

**Question 6.** If hashes are one-way, why is a leaked database still dangerous?

*Answer:* Attackers can test candidate passwords against leaked hashes. Salts and adaptive hashing make this much costlier, yet do not eliminate all risk, especially for weak passwords.

**Question 7.** `PasswordEncoder` verification succeeds. Does that mean the user can edit every document?

*Answer:* No. That is one step in password authentication; the system must still check account status, authorities, and per-resource access permissions.

### References

- [Spring Security 6.5 — Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security — PasswordEncoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/crypto/password/PasswordEncoder.html)
- [Spring Security — Password Storage and Crypto Module](https://docs.spring.io/spring-security/reference/features/integrations/cryptography.html)
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)

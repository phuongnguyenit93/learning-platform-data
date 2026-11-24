# NoOpPasswordEncoder and the Limits of Illustrative Configurations

## 1. Purpose of This Lesson

In Spring Security examples, you may encounter configurations allowing an account to log in using a password written directly in source code or via `{noop}demo-password`. That keeps tutorials short and easy to run, yet can also create a dangerous misconception: **a successful login does not mean the password is stored securely**.

`NoOpPasswordEncoder` is a `PasswordEncoder` implementation that **performs no hashing, adds no salt, and does not make passwords harder to guess**. With direct storage, the output of `encode(rawPassword)` is essentially still the exact password the user entered. `matches(raw, stored)` checks whether the two strings are identical. Spring Security marks this class **`@Deprecated`** and designates it strictly for legacy or testing scenarios, offering no security guarantee for storing real passwords.

This article focuses on:

1. What `NoOpPasswordEncoder` does and **does not do**.
2. The difference between `NoOpPasswordEncoder.getInstance()`, `{noop}...` strings, and `DelegatingPasswordEncoder`.
3. Why a runnable demo configuration must not be treated as a production configuration.
4. A runnable Java 17+ example with Spring Security 6.5.11 showing both the insecure behavior and replacing it with BCrypt.
5. How to write tests, handle encoder error messages, and migrate plaintext/legacy data to proper hashes without accidentally opening vulnerabilities.

The scope belongs to the **Password Hashing** group of Spring Security. Authentication steps through `DaoAuthenticationProvider` are introduced only to show that a plaintext password can still be verified by the framework, not to build a complete login system with sessions, CSRF, and a web UI.

## 2. How Does a Plaintext Password Differ from a Hash?

Suppose the demo password is `DemoPass123!`. With a strong salted encoder like BCrypt, the stored value is a **one-way password verifier**. With NoOp, the stored value remains a human-readable string.

| Criterion | `NoOpPasswordEncoder` | `BCryptPasswordEncoder` or suitable adaptive encoder |
| --- | --- | --- |
| `encode("DemoPass123!")` | Returns `DemoPass123!`. | Returns a structured salted password hash that changes on each `encode`. |
| Adds random salt | **No**. | Yes, per the corresponding algorithm. |
| Configurable computational cost (work factor) | **No**. | Verification cost can be tuned. |
| Recovering password from DB data | The password itself is already sitting there. | No direct decryption operation; still requires offline guessing defenses. |
| If the DB is leaked | Passwords are exposed immediately. | Attackers see hashes and must run password-guessing attacks; protection depends on password/algorithm/work factor. |
| Production use | **Unsuitable**. | Suitable when parameters and operations are properly chosen. |
| Tiny quick tests | Can be used when intentionally exercising a flow with dummy data, never deployed externally. | Still recommended when tests relate to real password behavior. |

**What NoOp does not do:** no reversible encryption, no SHA-256, no BCrypt, no PBKDF2, no salt, and no protection against a data dump. Calling a method named `encode` does not turn a password into secret data.

There are three very real risks:

- If a `users` table has a `password_hash` column that actually stores plaintext, **the column name does not make the data safe**.
- If accounts reuse passwords on external services, anyone obtaining the plaintext can attempt account takeovers beyond your app.
- If a demo environment is accidentally enabled in production or reachable from the Internet, hardcoded usernames/passwords become an abusable login path.

Dummy demo data must still be isolated from real data. Never ship high-privilege sample accounts, shared passwords, or debug endpoints to public environments.

## 3. The `PasswordEncoder` Contract and NoOp Behavior

`PasswordEncoder` is an interface in `org.springframework.security.crypto.password`. Two core methods:

```java
String encode(CharSequence rawPassword);

boolean matches(CharSequence rawPassword, String encodedPassword);
```

- `encode`: creates a storable value from the input password.
- `matches`: checks whether the user-submitted password matches the stored value.
- `upgradeEncoding(String encodedPassword)`: helper method assessing whether storage needs upgrading; usefulness depends on the encoder and wrapper.

For NoOp, we can illustrate simply:

```java
PasswordEncoder noop = NoOpPasswordEncoder.getInstance();

String stored = noop.encode("DemoPass123!");
System.out.println(stored.equals("DemoPass123!")); // true

System.out.println(noop.matches("DemoPass123!", stored)); // true
System.out.println(noop.matches("wrong-password", stored)); // false
```

This is an **excerpt** requiring imports for `PasswordEncoder` and `NoOpPasswordEncoder`. What matters is not the three booleans, but that the **original password was stored verbatim**. That very simplicity helps explain the API while making this usage insecure.

### 3.1. Obtaining the Instance via the Proper API

`NoOpPasswordEncoder` is a singleton; the documented way to obtain it:

```java
@SuppressWarnings("deprecation")
PasswordEncoder noop = NoOpPasswordEncoder.getInstance();
```

`@SuppressWarnings("deprecation")` only silences the compiler warning at one call site. It **does not fix the security flaw**, does not make NoOp production-ready, and offers no reason to suppress warnings in real applications.

Do not subclass it or look for `new NoOpPasswordEncoder()`. The class in Spring Security 6.5.11 is `final` with a non-public constructor; use `getInstance()`.

### 3.2. Character-Sensitive Comparison

NoOp compares strings, so `DemoPass123!` and `demopass123!` are two distinct values. Do not auto-lowercase or trim passwords to make tests pass: a password is a **credential**, not a username needing canonicalization.

```java
PasswordEncoder noop = NoOpPasswordEncoder.getInstance();

boolean ok = noop.matches("DemoPass123!", "DemoPass123!");
boolean bad = noop.matches("demopass123!", "DemoPass123!");
```

However, **comparing plaintext strings** does not mean this mechanism provides a cost-appropriate password verifier or resists offline attacks. `matches` can return `true` while the decision to store plaintext was wrong from the start.

## 4. What Is `{noop}`, and Does It Encrypt Passwords?

Spring Security supports `DelegatingPasswordEncoder`, allowing passwords to be stored with the structure:

```text
{id}encodedPassword
```

`id` is the **name of the selected encoder**; what follows is that encoder's data. For example:

```text
{noop}DemoPass123!
{bcrypt}$2a$...
{pbkdf2@SpringSecurity_v5_8}...
```

In the first string:

- `{noop}` is a **routing label**.
- `DemoPass123!` remains a **plaintext password**.
- There is no salt, hash, or mechanism making password guessing harder.
- `DelegatingPasswordEncoder` reads `id=noop` and forwards the password portion to `NoOpPasswordEncoder` for verification.

**Critical boundary:** `NoOpPasswordEncoder` itself **does not strip the `{noop}` prefix under delegate syntax**. If used directly:

```java
PasswordEncoder noop = NoOpPasswordEncoder.getInstance();

noop.matches("DemoPass123!", "DemoPass123!");       // true
noop.matches("DemoPass123!", "{noop}DemoPass123!"); // false
```

Yet with the encoder created by Spring Security 6.5's default factory:

```java
PasswordEncoder encoder =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();

encoder.matches("DemoPass123!", "{noop}DemoPass123!"); // true
```

`DelegatingPasswordEncoder` recognizes the prefix, takes the right-hand portion, and invokes the matching encoder. Nothing here transforms `{noop}DemoPass123!` into a hash.

### 4.1. Why Does the Framework Still Support `{noop}`?

Historically in Spring Security, prior to version 5.0, the default configuration used NoOp. When storage recommendations changed, many systems already held password data in older formats. The framework could not abruptly drop all legacy mechanisms without breaking login capability.

`DelegatingPasswordEncoder` enables:

1. **Reading old data** using the encoder matching the old ID.
2. **Writing new data** using a stronger current encoder.
3. **Upgrading gradually** when a valid authentication succeeds and a hash-updating service is configured.

Supporting backward compatibility **does not** mean Spring Security encourages storing new plaintext. In Spring Security 6.5 documentation, the default factory typically **encodes new passwords with BCrypt** while still able to **match `{noop}`** for legacy/demos.

### 4.2. Prefix Rules in Practice

| Value in DB | Direct encoder | Default delegating encoder | Assessment |
| --- | --- | --- | --- |
| `DemoPass123!` | NoOp can match the plaintext string. | No `{id}`: usually throws `IllegalArgumentException` due to null id. | Legacy plaintext; high risk. |
| `{noop}DemoPass123!` | Direct NoOp treats the prefix as part of the string, so raw mismatches. | Strips `id=noop` and checks plaintext. | Equally insecure despite the prefix. |
| `{bcrypt}$2a$...` | Direct NoOp cannot verify hashed passwords. | Strips `id=bcrypt`, uses BCrypt. | Can align with current policy. |
| `{argon2}...` | NoOp does not understand the algorithm. | Works only if the registry has the matching encoder/format. | Depends on config and parameters. |
| `{unknown}...` | NoOp has no routing mechanism. | By default reports no encoder mapped. | Must handle format/version; never guess blindly. |

The prefix is **algorithm-selection metadata**, not a security layer of its own. Prepending `{noop}` to plaintext data even makes a multi-algorithm encoder recognize and keep accepting plaintext, **without fixing storage risk**.

## 5. `User.withDefaultPasswordEncoder()` Is Not the Same as NoOp

Another Spring Security learning snippet often appears:

```java
UserDetails learner = User.withDefaultPasswordEncoder()
    .username("learner")
    .password("DemoPass123!")
    .roles("READER")
    .build();
```

The method name can be misleading. In Spring Security 6.5.11:

- `User.withDefaultPasswordEncoder()` uses the encoder created by `PasswordEncoderFactories.createDelegatingPasswordEncoder()`.
- The password record produced by the builder is typically in **`{bcrypt}...`** form, not `{noop}DemoPass123!`.
- However, the original password `DemoPass123!` **still appears in source code** and enters memory at startup.
- Hence the API is marked **deprecated/unsafe for production**, intended solely for getting-started guides or demos.

Thus there are **two distinct forms of danger**:

1. `NoOpPasswordEncoder`: the stored data itself is plaintext.
2. `User.withDefaultPasswordEncoder()`: the stored data is hashed, yet the **plaintext is hardcoded in the program/source**.

Never conclude "it uses BCrypt, so it's secure" when passwords are default, hardcoded, or extractable from source/decompiled artifacts. The proper production approach is generating password hashes outside startup/demo config, managing secrets securely, and never exposing publicly accessible sample accounts.

## 6. Safer Practice Example: Write with BCrypt, Never Use NoOp

Spring Security recommends one-way adaptive password hashing with work factors tuned on real infrastructure. A simple example:

```java
PasswordEncoder encoder = new BCryptPasswordEncoder();

String storedHash = encoder.encode("DemoPass123!");

// Always verify passwords via matches; do not re-encode and compare strings.
boolean accepted = encoder.matches("DemoPass123!", storedHash);
boolean rejected = encoder.matches("wrong", storedHash);
```

With BCrypt:

- `storedHash` is a salted verifier, not the original password.
- Each `encode` call usually produces a different string due to random salt.
- `matches` uses the parameters inside the hash format to verify.
- Computational cost is tunable and should be benchmarked appropriately.
- Never log raw passwords or return hashes over APIs.

**Important:** using `BCryptPasswordEncoder` directly produces DB values like `$2a$...`/`$2b$...` **without the `{bcrypt}` prefix**. When using `DelegatingPasswordEncoder` to write, strings carry the `{bcrypt}...` prefix to pick the right encoder. The two formats **cannot be swapped arbitrarily**; storage format and verification bean/registry must stay aligned.

Even with adaptive hashing, you still need anti-credential-stuffing controls, rate limiting, password change/reset flows, MFA where appropriate, least privilege, and login monitoring. A password encoder solves **data-at-rest security**, not all of login security.

## 7. Runnable Java 17+ Example: NoOp, `{noop}`, and BCrypt in One Program

This is a **standalone console** program with **Java 17+**, Gradle, and Spring Security **6.5.11**, letting you observe both NoOp behavior and the better alternative.

**Run only in an isolated learning/test environment.** Passwords and users in code are dummy data; never place them into production product sources. The code intentionally includes insecure cases so learners recognize and address them.

### 7.1. Directory Structure

```text
noop-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/NoOpDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'noop-demo'
```

`build.gradle`:

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
    implementation 'org.springframework.security:spring-security-core:6.5.11'
    implementation 'org.springframework.security:spring-security-crypto:6.5.11'
}

application {
    mainClass = 'demo.NoOpDemo'
}
```

### 7.2. File `src/main/java/demo/NoOpDemo.java`

```java
package demo;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.NoOpPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

public final class NoOpDemo {

    // Dummy value solely for demo. Never use hardcoded credentials
    // like this for real users or in public environments.
    private static final String DEMO_PASSWORD = "DemoPass123!";

    @SuppressWarnings("deprecation")
    public static void main(String[] args) {
        PasswordEncoder noop = NoOpPasswordEncoder.getInstance();

        // 1. NoOp keeps the password unchanged; no hash, salt, or work factor.
        String unsafeStored = noop.encode(DEMO_PASSWORD);

        System.out.println("noop.storesPlaintext="
                + unsafeStored.equals(DEMO_PASSWORD));
        System.out.println("noop.matchesCorrect="
                + noop.matches(DEMO_PASSWORD, unsafeStored));
        System.out.println("noop.matchesWrong="
                + noop.matches("wrong-password", unsafeStored));
        System.out.println("noop.acceptsPrefixDirectly="
                + noop.matches(DEMO_PASSWORD, "{noop}" + DEMO_PASSWORD));

        // 2. DelegatingPasswordEncoder reads ID, yet writes new hashes with bcrypt.
        PasswordEncoder delegating =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        String legacyStored = "{noop}" + DEMO_PASSWORD;
        System.out.println("delegate.acceptsLegacyPlaintext="
                + delegating.matches(DEMO_PASSWORD, legacyStored));
        System.out.println("delegate.rejectsWrongPlaintext="
                + delegating.matches("wrong-password", legacyStored));
        System.out.println("delegate.legacyNeedsUpgrade="
                + delegating.upgradeEncoding(legacyStored));

        String modernStored = delegating.encode(DEMO_PASSWORD);
        System.out.println("delegate.newIsBcrypt="
                + modernStored.startsWith("{bcrypt}"));
        System.out.println("delegate.matchesNew="
                + delegating.matches(DEMO_PASSWORD, modernStored));

        // A string without {id} prefix leaves default delegating unable to tell
        // which encoder to use; NEVER fix by enabling NoOp globally.
        try {
            delegating.matches(DEMO_PASSWORD, DEMO_PASSWORD);
            System.out.println("delegate.noId=unexpected-success");
        } catch (IllegalArgumentException ex) {
            System.out.println("delegate.noId=IllegalArgumentException");
        }

        // 3. The provider can still authenticate a legacy {noop} user if the registry
        // keeps that decoder. This does NOT mean plaintext is protected.
        UserDetails legacy = User.withUsername("legacy")
                .password(legacyStored)
                .roles("READER")
                .build();

        UserDetails modern = User.withUsername("modern")
                .password(modernStored)
                .roles("READER")
                .build();

        InMemoryUserDetailsManager store =
                new InMemoryUserDetailsManager(legacy, modern);

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(store);
        provider.setPasswordEncoder(delegating);

        AuthenticationManager manager = new ProviderManager(provider);

        Authentication legacyResult = manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "legacy", DEMO_PASSWORD));

        System.out.println("provider.legacyAuthenticated="
                + legacyResult.isAuthenticated());

        try {
            manager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "modern", "wrong-password"));
            System.out.println("provider.wrongPassword=unexpected-success");
        } catch (BadCredentialsException ex) {
            System.out.println("provider.wrongPassword=BadCredentialsException");
        }

        Authentication modernResult = manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "modern", DEMO_PASSWORD));

        System.out.println("provider.modernAuthenticated="
                + modernResult.isAuthenticated());

        boolean readerAuthority = modernResult.getAuthorities().stream()
                .anyMatch(a -> "ROLE_READER".equals(a.getAuthority()));
        System.out.println("provider.modernReaderRole=" + readerAuthority);
    }
}
```

**Compiler note:** `NoOpPasswordEncoder` and `getInstance()` are deprecated; `@SuppressWarnings("deprecation")` in the demo only keeps output focused and does not make the code secure.

### 7.3. Running the Program

Requires JDK 17+ and a Gradle version supporting Java 17 or a compatible Gradle Wrapper. From the directory containing `build.gradle`:

```bash
gradle run --quiet
```

**Stdout lines from the program** under Spring Security 6.5.11, excluding Gradle logs:

```text
noop.storesPlaintext=true
noop.matchesCorrect=true
noop.matchesWrong=false
noop.acceptsPrefixDirectly=false
delegate.acceptsLegacyPlaintext=true
delegate.rejectsWrongPlaintext=false
delegate.legacyNeedsUpgrade=true
delegate.newIsBcrypt=true
delegate.matchesNew=true
delegate.noId=IllegalArgumentException
provider.legacyAuthenticated=true
provider.wrongPassword=BadCredentialsException
provider.modernAuthenticated=true
provider.modernReaderRole=true
```

BCrypt hash values are not printed because their random salts change across runs. The output above checks **stable properties** (true/false, prefix, exception class names).

### 7.4. Why Are These the Results?

- **`noop.storesPlaintext=true`:** NoOp's `encode` returns the original value itself; no password hashing happens.
- **`noop.matchesCorrect`/`matchesWrong`:** NoOp only compares strings, without hash verification.
- **`noop.acceptsPrefixDirectly=false`:** the `{noop}` prefix is only understood by delegating encoders; direct NoOp does not strip prefixes.
- **`delegate.acceptsLegacyPlaintext=true`:** the default factory still supports ID `noop` to read legacy/demo data; do not confuse this with **writing** with NoOp by default.
- **`delegate.legacyNeedsUpgrade=true`:** the old ID differs from the write ID `bcrypt` so the wrapper flags an upgrade, though no DB write occurs automatically.
- **`delegate.newIsBcrypt=true`:** the default factory's write encoder uses BCrypt and prepends `{bcrypt}`.
- **`delegate.noId=IllegalArgumentException`:** when a record has no `{id}` and no fallback is configured, delegating cannot pick an encoder. This is a data/config signal needing investigation.
- **`provider.legacyAuthenticated=true`:** `DaoAuthenticationProvider` can still grant authentication after a legacy password matches via NoOp. Being "able to log in" **never proves passwords are stored safely**.
- **`provider.wrongPassword=BadCredentialsException`:** the modern account has a proper hash, yet the wrong password is rejected by the provider.
- **`provider.modernReaderRole=true`:** authorities come from system-provided `UserDetails`, never from client-asserted roles.

This demo **creates no HTTP session** or login endpoint. In web applications, filters and `SecurityContext` configuration handle requests, state updates, and access policies; `PasswordEncoder` does not manage those parts.

## 8. Only Use NoOp Within Controlled Illustrative Boundaries

You may see these patterns in learning materials:

```java
// Intentionally INSECURE example, solely to understand the mechanism:
@Bean
PasswordEncoder passwordEncoder() {
    return NoOpPasswordEncoder.getInstance();
}
```

Or:

```java
UserDetails demoUser = User.withUsername("student")
        .password("{noop}DemoOnly123!")
        .roles("READER")
        .build();
```

**Do not copy either snippet straight into production.** The first applies plaintext storage to every user routed through that bean; the second stores a password readable at a glance if data leaks. Even a learning project on `localhost` can get exposed via tunnels, reverse proxies, IDE sharing, or accidental deployment.

If a very short illustration is needed, you should:

1. Use dummy users and passwords strictly within the specific lesson/unit test.
2. Isolate configuration in test sources/test profiles, never in the default production profile.
3. Even better, build fixtures with `BCryptPasswordEncoder` or `DelegatingPasswordEncoder` so tests mirror reality.
4. Never grant default administrator privileges to demo accounts.
5. Never reuse demo passwords on any real system.
6. Ensure CI/CD cannot accidentally activate test profiles, and scan artifacts/configs before release.
7. Include a production config test asserting the password encoder is not NoOp and new passwords are never stored in plaintext.

### Profiles in Spring Boot Are Not a Security Wall

For example, `@Profile("test")` can isolate a NoOp bean, yet **does not guarantee safety** if the profile is accidentally activated in a public environment:

```java
// WARNING excerpt ONLY, not a recommended configuration:
@Configuration
@Profile("test")
class InsecureOnlyForTests {

    @Bean
    PasswordEncoder passwordEncoder() {
        return NoOpPasswordEncoder.getInstance();
    }
}
```

If a project needs to test the safety of real configurations, it is better to use an **adaptive encoder in integration tests**, picking a cost factor/test fixtures fast enough for tests without turning production config insecure.

**Never use NoOp solely to speed up all tests** if those tests verify hashing, migration, account state, or security policies. Such tests must exercise the real encoder to be meaningful.

## 9. Three Testing Scenarios That Must Be Distinguished

| Test Type | Calls real `PasswordEncoder.matches`? | Is NoOp appropriate? | What the Test Proves |
| --- | --- | --- | --- |
| `@WithMockUser` / `.with(user(...))` | Usually **no**; security context is mocked. | NoOp is unnecessary. | Tests authorization/controllers with a pre-supplied principal. |
| Isolated unit test of routing/adapter logic ignoring hashes | Possibly not, or uses a fake. | Can illustrate, if strictly scoped. | Business/lookup contract; does not prove password storage safety. |
| Login test through real `DaoAuthenticationProvider` / `AuthenticationManager` | **Yes**. | Using NoOp skips testing the real production encoder. | Authentication mechanics and account state under test config. |
| HTTP login via `MockMvc` with Spring Security filter chain | Yes, if routed through the real configured provider. | Should use production encoder or a realistic test profile. | End-to-end HTTP-to-provider behavior, failures, authorities, and status codes. |

### What Can a "Passing" Test Prove?

If a test has:

```java
assertTrue(NoOpPasswordEncoder.getInstance()
        .matches("test123", "test123"));
```

it only proves **two strings are equal**. It **does not** prove the application has secure password hashing. Nor does it prove the auth endpoint defends against brute force, account lockout, MFA, or hash upgrade policies.

A more useful test verifies the security invariant of code used to **write new passwords**:

```java
// JUnit excerpt inside a test class that already has PasswordEncoder encoder.
String encoded = encoder.encode("DemoOnly123!");

assertNotEquals("DemoOnly123!", encoded);
assertTrue(encoder.matches("DemoOnly123!", encoded));
assertFalse(encoder.matches("wrong", encoded));
```

If using `DelegatingPasswordEncoder`, test that the ID prefix belongs to the policy's allowed-algorithm list instead of merely checking `encoded != raw`; a weak encoder could still prepend a prefix without hashing. With BCrypt and random salts, never assert a fixed literal hash.

### Testing Production Without NoOp

You can write a test checking configuration when the application context starts:

```java
// Spring Boot integration test excerpt: PasswordEncoder already injected.
@Test
void productionEncoderMustNotStorePlaintext() {
    String raw = "RandomTestPassword!42";
    String stored = passwordEncoder.encode(raw);

    assertNotEquals(raw, stored);
    assertTrue(passwordEncoder.matches(raw, stored));
    assertFalse(passwordEncoder.matches("wrong-password", stored));
}
```

This snippet **does not yet check full security** because a weak encoder could still add a prefix. Add checks for `{id}` against an allowlist or adaptive hash properties, and test real password updates through services/repositories. If the app allows reading legacy `{noop}`, tests must distinguish **legacy read capability** from **strictly banning NoOp for new writes**.

## 10. Handling "There is no PasswordEncoder mapped for the id null"

A common situation when upgrading Spring Security:

```text
java.lang.IllegalArgumentException:
There is no PasswordEncoder mapped for the id "null"
```

The typical cause is a database storing:

```text
DemoPass123!
```

while the application uses `DelegatingPasswordEncoder`, which needs an `{id}` prefix to tell which algorithm produced the data.

**Wrong approach:** adding a global `NoOpPasswordEncoder` bean or configuring a NoOp fallback just to make logins work again, without understanding the old data. That can make the whole authentication system accept plaintext or cause new code to keep writing plaintext passwords.

**Right sequence of steps:**

1. Identify the actual encoder config running on each application/instance.
2. Inventory **data formats** in the DB: plaintext, BCrypt, PBKDF2, other IDs, or corrupted rows.
3. Classify accurately. For instance, an unprefixed BCrypt hash starting with `$2a$...` differs from plaintext; never conflate them.
4. Define a decoder registry compatible with old data and a strong encoder for all new records.
5. Migrate data under a clear plan with backups, minimal logging, and multi-version testing.
6. If legacy plaintext exists, treat it as **an exposure risk**: restrict access, determine window and scope of exposure, and consider forced password resets.
7. Test login and update/reset flows in staging with test data, never dumping production plaintext into logs or docs.
8. Plan to remove NoOp/legacy format support once no records need verification.

### Why Is `setDefaultPasswordEncoderForMatches(NoOpPasswordEncoder...)` Risky?

`DelegatingPasswordEncoder` lets you specify a fallback when an ID is unrecognized. If the fallback is NoOp:

- Data **without an ID** can be compared as plaintext.
- Malformed data can be accepted unintentionally.
- Configuration/data bugs are masked instead of detected.
- Systems spanning multiple apps and databases can drift into inconsistent policies.

Treat fallback strictly as a legacy compatibility tool **with clear limits on time, data scope, testing, and access control** — never as a default setting to silence encoder errors. For systems with complex data, build a **controlled per-record/profile migration path** rather than trying arbitrary unknown encoders.

## 11. Migrating `{noop}`/Plaintext Data to Costed Hashes

Two common legacy data forms exist:

```text
A. Unprefixed plaintext:
   password_column = "DemoPass123!"

B. Prefixed plaintext:
   password_column = "{noop}DemoPass123!"
```

Both hold **readable passwords**; the prefix makes no difference to storage security. The goal is moving to a strong hash format, for example:

```text
C. New form:
   password_column = "{bcrypt}$2a$..."
```

There are two separate conversion paths to consider.

### 11.1. Upgrading on Successful Login

When the system can still read old records via `DelegatingPasswordEncoder`, after a valid password verification the program has temporary access to the raw password inside the authentication flow. At that moment it can **re-encode with the current algorithm** and update the record.

With `DaoAuthenticationProvider`, you can configure `UserDetailsPasswordService`:

```java
// Integration code, not a standalone console program.
// users: UserDetailsService querying the account store;
// updater: UserDetailsPasswordService updating the hash in the store;
// encoder: DelegatingPasswordEncoder with legacy decoder registry and new encoder.
DaoAuthenticationProvider dao = new DaoAuthenticationProvider(users);
dao.setPasswordEncoder(encoder);
dao.setUserDetailsPasswordService(updater);
```

Conceptual sequence:

```text
User enters username/password
    |
    v
DaoAuthenticationProvider loads UserDetails
    |
    v
encoder.matches(rawPassword, oldStored)
    |
    +-- False: do not upgrade, reject login
    |
    +-- True:
          |
          +--> encoder.upgradeEncoding(oldStored) ?
                 |
                 +-- false: keep suitable hash
                 |
                 +-- true:
                       newStored = encoder.encode(rawPassword)
                       UserDetailsPasswordService.updatePassword(
                           user, newStored)
                       |
                       v
                 Persist new hash in safe transaction
```

**`upgradeEncoding(...) == true` does not automatically update the database.** The provider must have a suitable update service, and the application must ensure concurrency safety, transactions, revocation/expiry, and safe logging.

If multiple sessions or concurrent password resets happen, a stale login must not overwrite a newly reset password. Use optimistic locking/versioning or conditional updates checking the old hash/version. During rolling deploys, every running node must understand the new hash ID.

### 11.2. Processing Plaintext Offline

Unlike bcrypt, legacy plaintext data **can be converted into new hashes without waiting for users to log in**, because raw passwords are already present. However, that is **not an advantage to preserve**: having plaintext passwords in a database is a hazardous state, and data may have been read prior to migration.

If choosing a batch rehash:

1. Restrict access to the DB and backups holding plaintext, running only inside secure environments and procedures.
2. Verify which fields are genuinely plaintext vs. prefixed/unprefixed hashes; never mistakenly re-encode a hash as raw input.
3. Generate new hashes with the current encoder and write atomically, preserving valid rollback without creating extra plaintext copies.
4. Log counts of converted records and error states, **never logging raw passwords**.
5. Scrub temporary files, dumps, traces, and accessible plaintext backups per security and retention policies.
6. Consider forcing password resets for users, especially if exposure is suspected or cannot be ruled out.

Offline rehashing **cannot revoke passwords that may already have leaked**. Incident evaluation and user notifications per organizational policy may need to happen alongside it.

### 11.3. Never Alter Prefixes Without a Plan

Some mistakes:

- Changing `DemoPass123!` to `{bcrypt}DemoPass123!` without running BCrypt: guaranteed invalid format.
- Adding `{noop}` to every record when the DB holds both BCrypt and PBKDF2: breaks verification of valid passwords.
- Stripping `{noop}` and treating the remainder as a hash: the remainder is plaintext.
- Reusing the same `bcrypt` ID for incompatible profiles: makes old data unreadable.
- Hashing once and then hashing **the encoded hash as a raw password** during updates: breaks authentication against the original password.
- Changing the production password encoder without updating registration, password change, password reset, and login consistently.

**A sound migration preserves authentication correctness**, handles concurrent writes, and phases out plaintext rather than keeping legacy alive forever.

## 12. Illustrative Spring Boot Configurations and Better Alternatives

### 12.1. Never Use a Global NoOp Bean

**Pattern to avoid in production:**

```java
@Configuration
class UnsafePasswordConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return NoOpPasswordEncoder.getInstance();
    }
}
```

The snippet above is an **excerpt** from a project that already has imports/configuration, not a standalone program. It can cause newly created passwords to keep being saved as plaintext whenever services call this bean to encode.

### 12.2. Bean Aligned with Modern Policy

Typical example for an app running Spring Security 6.5:

```java
@Configuration
class SafePasswordConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }
}
```

This bean normally writes new passwords with the `{bcrypt}` prefix and supports multiple legacy IDs for matching, including `noop` if the default registry includes it. **Having a "safe" bean does not mean all DB records are safe**, because the system may still hold `{noop}...` rows. After migration, plan to remove acceptance of plaintext IDs from production paths per policy instead of relying only on new writes.

This configuration is a **Spring Boot excerpt**, requiring imports for `Configuration`, `Bean`, `PasswordEncoder`, `PasswordEncoderFactories`, and suitable user store/security chain beans. It does not create login REST endpoints by itself.

### 12.3. Registry Without `noop` Once Migration Completes

Once zero legacy plaintext records remain, you can construct a registry containing **only approved encoders**:

```java
PasswordEncoder encoder = new DelegatingPasswordEncoder(
        "bcrypt",
        Map.of("bcrypt", new BCryptPasswordEncoder()));
```

Requires imports for `Map`, `PasswordEncoder`, `DelegatingPasswordEncoder`, and `BCryptPasswordEncoder`. Then `{noop}...` values are rejected due to the missing `noop` mapping. **Apply this only after verifying data and confirming other apps are compatible**; do not remove the decoder while unmigrated users remain.

This is a minimal registry example, not claiming only BCrypt is safe. Applications may use Argon2id, scrypt, or PBKDF2 depending on policy/real infrastructure. If supporting multiple algorithms, each ID must have clear, stable semantics; only approved algorithms may be used for new passwords.

## 13. Demo Correctness and Security Boundaries

One reason NoOp still gets mentioned is **speed and simplicity**: learners avoid generating hashes just to understand `UserDetailsService` and `AuthenticationManager`. Yet that convenience is valid only in **strictly bounded environments**.

A demo can pass functional verification:

```text
client credentials = "learner / demo-password"
UserDetailsService returns user with password = "{noop}demo-password"
DelegatingPasswordEncoder selects "noop"
NoOpPasswordEncoder string comparison succeeds
DaoAuthenticationProvider returns authenticated Authentication
```

Authentication outcome is **correct per configuration**; the configuration is **unsafe for real accounts**.

Distinguish three properties:

| Property | Question | Does NoOp satisfy it? |
| --- | --- | --- |
| **Functional correctness** | Do demo username and password pass through the provider, and are wrong passwords rejected? | Potentially yes. |
| **Password storage security** | If the DB leaks, are passwords protected by one-way adaptive hashing? | **No**. |
| **Application security** | Are TLS, proper CSRF/rate limiting, MFA, session protection, authorization checks, and auditing present? | **NoOp handles none** of those mechanisms. |

A system cannot treat "login test passed" as proof that all security layers pass. Testing and configuration must match their intended scope.

### Does Using HTTP Basic in a Demo Make NoOp Safer?

No. HTTP Basic sends credentials in a header with Base64 encoding (not cryptographic encryption), typically requiring HTTPS for transport protection. Even if the connection uses proper TLS, **passwords still sit in plaintext in the database** when using NoOp. Protecting data in transit and protecting passwords at rest are **two separate problems**.

### Is a Localhost-Only Demo Completely Safe?

No. Localhost limits exposure in many cases, yet risks remain from sample accounts committed to repositories, accidental auto-deployments, exposed container ports, captured logs, or future developers copying sample code. Learning guides need explicit warnings, and real applications need configuration safeguards preventing NoOp from being enabled accidentally.

## 14. Common Mistakes

1. **"`encode` means the password is hashed."** False with NoOp: output is still the raw password.
2. **"`{noop}` is encryption."** False: it is an encoder-selection ID; the password after the prefix remains plaintext.
3. **"We use `DelegatingPasswordEncoder`, so the database only has strong hashes."** False: the factory can still match legacy `{noop}` data.
4. **"`NoOpPasswordEncoder.getInstance()` is the modern Spring Security default."** False: it is strictly for legacy/testing; the default factory since Spring Security 5+ delegates and uses a modern encoder for writes.
5. **"Using `User.withDefaultPasswordEncoder()` is the same as NoOp."** False: the builder hashes via `DelegatingPasswordEncoder`; yet it remains unsuitable for production due to hardcoded raw passwords.
6. **"Data prefixed `{bcrypt}` is guaranteed to be a BCrypt hash."** Not if data was malformed manually; it must actually be produced by the matching encoder.
7. **"Direct NoOp understands `{noop}`."** False: the prefix is handled by delegating; NoOp compares the underlying string.
8. **"There is only one demo account, so there's nothing to worry about."** Even one privileged user is an entry point if deployed publicly.
9. **"Suppressing `@Deprecated` warnings with an annotation makes it safe."** False: annotations affect compiler warnings only.
10. **"Switching the bean to BCrypt automatically converts all old passwords."** False: you need matching profile decoders and a migration/update plan.
11. **"Raw passwords are in the DB, but HTTPS covers everything."** HTTPS protects transport, not data stored at rest.
12. **"Allowing NoOp fallback for all ID-less hashes to quickly fix errors."** Can accept malformed data as plaintext and mask incidents.
13. **"Using `@WithMockUser` proves the password encoder works."** False: mocks typically bypass the provider and password matching.
14. **"`UserDetailsService` found the right user, so the password is verified."** No: the service loads the record; the provider/encoder verifies it.
15. **"Successfully logging in means the user can access all resources."** No: authentication and authorization are distinct steps.
16. **"We can reuse the demo password as an admin password."** No: sample credentials must never be used for real accounts.
17. **"Password hashes in logs are fine because they aren't plaintext."** No: hashes are sensitive password verifiers enabling offline guessing attacks if leaked.
18. **"Storing plaintext now and hashing later causes no harm."** Exposure risk exists from day one; later rehashing cannot undo past leaks.
19. **"Swapping the prefix once completes migration."** No: the prefix must accurately reflect the algorithm that generated the stored value.
20. **"NoOp can be used as the encoder for all integration tests."** If tests target security/hashing/migration, NoOp fails to validate the production system.
21. **"Enabling the test profile isolates all demo secrets."** Profiles can be activated accidentally; deployment gates and verification tests are still required.
22. **"BCrypt guarantees every password is strong."** Weak passwords remain easy to guess; combine with password policies, anti-credential-stuffing, and MFA where appropriate.

## 15. Self-Check Questions

**Question 1.** What does `NoOpPasswordEncoder.encode("abc123")` return? Why is it insecure?

**Answer:** Essentially it returns `abc123` itself. Anyone obtaining the DB record reads the password immediately without brute-forcing a hash.

**Question 2.** How does `{noop}abc123` differ from `abc123`?

**Answer:** The `{noop}` prefix tells `DelegatingPasswordEncoder` which decoder to pick. Both still contain the raw password; the prefix provides no cryptographic protection.

**Question 3.** Why does `noop.matches("abc123", "{noop}abc123")` return false while delegating can return true?

**Answer:** Direct NoOp compares the entire string; delegating strips `{noop}` and passes `abc123` to NoOp.

**Question 4.** After switching to the delegating factory, are `{noop}abc123` records automatically rejected?

**Answer:** No. The default registry may still support `noop` for reading legacy records; only writing new passwords uses BCrypt. Eliminating plaintext requires migration and narrowing the registry per policy.

**Question 5.** Is `User.withDefaultPasswordEncoder()` equivalent to NoOp?

**Answer:** No. It encodes using `DelegatingPasswordEncoder` (typically BCrypt in Spring Security 6.5). However, raw passwords are hardcoded in source, so the API is not for production.

**Question 6.** If "There is no PasswordEncoder mapped for the id null" appears, should `NoOpPasswordEncoder` be enabled system-wide?

**Answer:** No. Verify DB formats, classify hashes vs. legacy records, and execute a migration plan. Enabling NoOp globally risks accepting or continuing to write plaintext.

**Question 7.** Does `upgradeEncoding("{noop}abc123")` returning true update the DB automatically?

**Answer:** No. It is an upgrade signal; you need a successful authentication flow, a new encoder, and a hash-writing service with transaction/concurrency control.

**Question 8.** When legacy plaintext is sitting in the DB, can it be hashed offline?

**Answer:** Yes, though the prior existence of plaintext is a risk whose potential exposure cannot be undone retroactively. Secure the migration process, assess exposure risk, and enforce password resets as needed.

**Question 9.** Does a green `@WithMockUser` unit test prove `BCryptPasswordEncoder` ran?

**Answer:** No. It sets the security context directly; password tests must go through the real provider/encoder.

**Question 10.** Why is HTTPS insufficient to make `NoOpPasswordEncoder` secure?

**Answer:** HTTPS protects credentials in transit over the network. NoOp still stores passwords verbatim in the DB, which is a separate data-at-rest protection problem.

**Question 11.** What should be verified before removing the `noop` decoder?

**Answer:** Zero remaining plaintext records in use, every application node can read the new format, rollback plans exist, and inactive accounts plus reset/update flows are handled.

**Question 12.** When a demo genuinely needs simplicity, what should you do?

**Answer:** Generate password hashes with BCrypt/`DelegatingPasswordEncoder` for fixtures or keep a tightly isolated NoOp config strictly for learning tests, never letting it reach public environments.

## 16. Official References

- [Spring Security 6.5.11 — NoOpPasswordEncoder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/NoOpPasswordEncoder.html): deprecated class, `getInstance()` singleton, legacy/testing only.
- [Spring Security 6.5 — Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html): NoOp history, adaptive password hashes, `DelegatingPasswordEncoder`, `{id}`, and plaintext config warnings.
- [Spring Security 6.5 — In-Memory Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/in-memory.html): `InMemoryUserDetailsManager`, `User.withDefaultPasswordEncoder()`, and demo limits.
- [Spring Security 6.5.11 — PasswordEncoder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/PasswordEncoder.html): `encode`, `matches`, and `upgradeEncoding`.
- [Spring Security 6.5.11 — DelegatingPasswordEncoder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/DelegatingPasswordEncoder.html): versioned IDs, registry, default fallback, and upgrade.
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): how the provider loads `UserDetails` and verifies passwords.
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): adaptive password-storage algorithms, work factors, salts, and migrations.
- [Spring Security 6.5.11 — User API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/User.html): `withDefaultPasswordEncoder` builder and hardcoded raw-password warnings.

**Conclusion:** `NoOpPasswordEncoder` exists for backward compatibility and simplifying certain demos, yet **performs no protection of passwords at rest**. The `{noop}` prefix only routes to this mechanism; it is not a hash. In real applications, use an adaptive encoder with consistent formats/versions, test real login paths, manage legacy upgrades, and phase out plaintext acceptance under a safe plan.
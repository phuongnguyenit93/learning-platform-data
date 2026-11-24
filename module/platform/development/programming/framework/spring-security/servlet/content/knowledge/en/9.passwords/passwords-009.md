# Why NoOpPasswordEncoder and Plaintext Passwords Are Only Suitable for Illustrative Demos

## 1. Core issue: working authentication does not equal secure password storage

In Spring Security **Servlet**, applications typically receive a username and password via a login interface and compare the user-supplied password against the **stored value** for that account. `PasswordEncoder` determines how that stored value is represented and verified.

When starting to learn, you sometimes encounter:

```java
PasswordEncoder encoder = NoOpPasswordEncoder.getInstance();
```

Or see user data looking like:

```text
username: alice
password: password123
```

The two examples above **only help describe the login flow in an isolated learning environment**. They are **not secure enough to hold real users' passwords**. `NoOpPasswordEncoder` lets a program authenticate, yet it performs no password hashing, generates no salt, adds no slowdown to password guessing, and provides no protection if the storage backend is read without authorization.

To understand that boundary, distinguish:

- **Authentication:** does the checked password match the account?
- **Password storage:** if the database, logs, backups, or config files leak, can someone read the original password?
- **Other security controls:** TLS, brute-force protection, MFA, session management, and authorization remain necessary even when passwords are properly hashed.

**Key message:** a system where "login works" with plaintext passwords only proves the software flow runs; it **does not** prove the system is designed to protect credentials.

## 2. What does NoOpPasswordEncoder actually do?

`NoOpPasswordEncoder` implements the `PasswordEncoder` interface yet intentionally **does not encrypt/hash passwords**.

In terms of behavior:

- `encode(rawPassword)` returns the input password content as is, instead of creating a password hash.
- `matches(rawPassword, encodedPassword)` checks the input password string against the stored value without salted, work-factor hash verification.
- Generates no random salt and applies no tunable computational cost to slow down offline password guessing.
- Kept primarily for compatibility, illustration, or specialized testing scenarios; not a recommended encoder for real accounts.

Equivalent logic example:

```text
Form input:            demo-only-password
NoOpPasswordEncoder:   demo-only-password
Value saved in DB:     demo-only-password

User sends right password -> matches(...) = true
User sends wrong password -> matches(...) = false
```

A test that only checks `matches(...)` succeeds will **fail to detect** that the password was stored in plaintext. Therefore, check both the **stored data format** and the `PasswordEncoder` design.

### "NoOp" is not weak encryption; it is no password protection

The word "encoder" easily misleads people into assuming data was processed safely. Yet if `encode` returns the raw string, anyone reading the database also reads the exact password that can be reused elsewhere. There is no decryption step; the data was **never obscured**.

Even a password made of meaningless characters is unsafe if stored in plaintext: users may reuse it across multiple services, and the system cannot tell whether that string is unique or used elsewhere.

## 3. Where are plaintext passwords dangerous?

Exposure points for credentials are not limited to the `users` table in the database:

1. **SQL dumps, backups, and snapshots.** Administrators, backup tools, or someone accessing the wrong bucket can see every password.
2. **Database permission flaws.** SQL injection or a leaked read-only account suffices to read plaintext passwords; attackers do not even need write permissions.
3. **Logs and monitoring.** If the app logs HTTP bodies, form parameters, exceptions, or user objects, raw passwords can appear across systems outside the database.
4. **Test data or staging environments.** Copying a production database to a less-controlled environment can replicate all plaintext passwords.
5. **Credential reuse and credential stuffing.** Once one system leaks passwords, attackers try those exact username/password pairs on email, banking, or other services.
6. **Staff and third-party integrations.** No malice required: a report, CSV export, dashboard, or ticket containing a password column creates exposure.
7. **Plaintext storage amplifies breach impact.** With well-designed hashes, attackers must guess passwords offline; with plaintext, that step is bypassed completely.

Some applications even send or record passwords in URL query strings, analytics, and request logs. **Never use URLs to transmit passwords**; send credentials only over proper HTTPS channels and avoid keeping unnecessary copies.

> Secure password hashing **does not replace** database access controls, encryption at rest, TLS, or backup protection; it is a separate defensive layer that limits impact when password verifiers are exposed.

## 4. Password hashing differs from encryption, Base64, and general-purpose hashes

| Storage method | Can recover password directly? | Suitable as a password verifier? |
|---|---|---|
| Plaintext / `NoOpPasswordEncoder` | Yes; original data sits directly in storage | **No** |
| Base64, hex, URL encoding | Yes; merely data representation | **No** |
| Decryptable symmetric encryption | Yes with the key; guarding the key becomes a major risk | Normally **not** an appropriate design for password verification |
| Single-pass unsalted SHA-256/MD5 | No direct decrypt API, yet offline guessing is very fast | **No**; too fast and vulnerable to dictionary attacks |
| Dedicated salted, cost-tuned password hashing (BCrypt, PBKDF2, scrypt, Argon2id) | Cannot recover directly; verifies via check function | **Yes**, when using a suitable algorithm and parameters |

**Password hashing** is a one-way process with a random salt and cost parameters forcing attackers to spend significant computation per guess. The application stores a **password verifier** (the hash plus needed metadata), not the original password.

At login:

```text
Account creation:
raw password --password KDF(salt, cost)--> encoded verifier in DB

Login:
raw password from client
         +
encoded verifier from DB
         |
PasswordEncoder.matches(raw, verifier)
         |
true / false (does not decrypt verifier into original password)
```

**Salt** generally **does not need to be secret** and can reside inside the encoded hash. Each verifier creation must use an appropriate salt so two users with the same password do not automatically yield identical stored data. **Pepper**, if used, is a separately managed additional secret; it does not replace salt/work factor and requires clear rotation/recovery strategies.

BCrypt is intentionally more expensive than general-purpose hashes; scrypt and Argon2id also allow tuning memory to make large-scale password-guessing campaigns costly. Choosing algorithms and parameters must balance load capacity, security policy, and library maintainability.

## 5. PasswordEncoder: the encode, matches, and upgradeEncoding contract

In Spring Security, the interface has key operations:

```java
String encode(CharSequence rawPassword);
boolean matches(CharSequence rawPassword, String encodedPassword);
boolean upgradeEncoding(String encodedPassword);
```

This is an illustrative interface signature, not a standalone Java program.

- **`encode(raw)`:** used when creating or changing a password; output is the string stored in the data store.
- **`matches(raw, stored)`:** used during login; takes the newly submitted password and stored verifier, checking whether they correspond. **Do not** call `encode(raw)` and compare two new hashes with string equality when the encoder uses random salts.
- **`upgradeEncoding(stored)`:** can report whether an old verifier needs an algorithm/cost upgrade under the active encoder. Behavior depends on implementation and config; not every encoder supports auto-upgrading.

Common mistake with BCrypt:

```java
// WRONG: two encodes normally use different salts.
String first = encoder.encode(rawPassword);
String second = encoder.encode(rawPassword);
boolean sameHash = first.equals(second);
```

`sameHash` in the example will typically be `false` even though the original password is the same; this is the **expected** behavior of a randomly salted encoder. The right check is:

```java
String stored = encoder.encode(rawPassword);
boolean accepted = encoder.matches(rawPassword, stored);
```

The two snippets are Java fragments with pre-declared variables illustrating the principle; full runnable code is in section 8.

## 6. BCryptPasswordEncoder: replacing NoOp with salted, cost-tuned hashes

`BCryptPasswordEncoder` is a widely supported Spring Security choice for hashing passwords. BCrypt uses a unique salt and a cost parameter to slow password guessing. The encoded string contains the info needed for verification, including BCrypt version/format, cost, salt, and result data.

Spring Security example:

```java
PasswordEncoder encoder = new BCryptPasswordEncoder();

String stored = encoder.encode("demo-only-password");

boolean ok = encoder.matches("demo-only-password", stored);
boolean rejected = encoder.matches("wrong-password", stored);
```

Expected: `ok == true` and `rejected == false`. **There is no single unique BCrypt output** for the same password because salts are randomly generated. Do not hardcode a sample hash value or expect two `encode` calls to match.

### Tuning cost requires measurement

Too low a cost speeds up offline guessing; too high a cost makes login CPU-heavy, raises latency, and pressures the system under request floods. Choose parameters based on current algorithm guidance, measure in the real deployment environment, and pair with rate limiting/account lockout.

**Specific note on BCrypt:** some BCrypt variants have an input limit around **72 bytes**, and behavior beyond the limit varies by implementation. With long Unicode passwords, byte count differs from character count; read docs for your exact version and design consistent input/migration policies—**never silently truncate passwords**. When stronger protection for long passwords or a memory-hard KDF is required, evaluate Argon2id/scrypt based on library and environment support.

### Why not write hashing yourself with MessageDigest?

A `MessageDigest.getInstance("SHA-256")` call is fast, has no built-in salt/cost, and provides no safe upgrade workflow. Rolling your own hash loops, salts, or encryption is not equivalent to a vetted dedicated password KDF. Use `PasswordEncoder` and tested implementations; do not invent a new password scheme just to avoid a dependency.

## 7. DelegatingPasswordEncoder: managing multiple algorithms and the risk of leftover {noop} records

Spring Security provides delegation by **algorithm ID recorded inside the verifier string**, typically created via:

```java
PasswordEncoder encoder =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();
```

This is an illustrative snippet. In common Spring Security 6.x configurations, newly encoded values default to BCrypt and carry an ID prefix:

```text
{bcrypt}<BCrypt string containing cost, salt, and verifier>
```

**The `{bcrypt}` tag is metadata, not the password and not the salt.** When `matches(raw, stored)` runs, `DelegatingPasswordEncoder` reads the ID first and picks the corresponding encoder to check.

### {noop} provides no protection merely by having a prefix

A record like:

```text
{noop}demo-only-password
```

still holds the plaintext password after the prefix. `DelegatingPasswordEncoder` can recognize the `noop` ID and verify with NoOp if that delegate is registered, yet that does not make the legacy data safe.

**Audit point:** using `createDelegatingPasswordEncoder()` ensures **new records** are typically stored with `{bcrypt}`, yet old `{noop}` records may **continue to be accepted for authentication** for compatibility. Swapping the encoder bean does not automatically convert existing plaintext in the database into BCrypt.

| Stored data | Meaning |
|---|---|
| `demo-only-password` | Plaintext without an ID; delegating encoder may fail to determine the algorithm, throwing an invalid ID error unless a fallback is configured |
| `{noop}demo-only-password` | Plaintext with NoOp ID; if the NoOp delegate is permitted, still verifies directly |
| `{bcrypt}$2a$...` or matching BCrypt format | Password verifier using BCrypt; the part after the prefix cannot be treated as the original password |
| `{argon2}...`, `{pbkdf2}...`, etc. | Valid only when the ID and implementation are properly registered for the version |

**Never turn every password entry into a `{bcrypt}`-prefixed string by prepending text.** If the original data is plaintext, prepending a BCrypt prefix does not make it a hash; verification will fail format checks and offer zero protection.

Avoid configuring a fallback decoder that accepts any prefix-less string as plaintext just to "quickly fix" login. That widens the boundary for accepting insecure credentials. Migrating old data requires a plan and exact proof of format before making changes.

## 8. Runnable Java 17+ example: observing NoOp, BCrypt, and Delegating

The demo below uses **Spring Boot 3.3.5 BOM/parent with Spring Security Crypto**, Java 17, and Maven. This is a fixed learning baseline; when building real systems, choose supported Spring Boot/Security versions and review release notes, dependency trees, and cryptographic policies. The demo **requires no Servlet server or database connection**: it tests the `PasswordEncoder` core before integrating into `DaoAuthenticationProvider` or form login.

Structure:

```text
password-encoder-demo/
├── pom.xml
└── src/
    ├── main/java/example/password/PasswordEncoderDemo.java
    └── test/java/example/password/PasswordEncoderDemoTest.java
```

### 8.1. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>password-encoder-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-crypto</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

The Spring Boot parent provides dependency management for Spring Security modules; `exec-maven-plugin` lets Maven run a `main` class without creating a Spring Boot web application.

### 8.2. Java main file

Create `src/main/java/example/password/PasswordEncoderDemo.java`:

```java
package example.password;

import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.NoOpPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public class PasswordEncoderDemo {

    public static void main(String[] args) {
        String raw = "demo-only-password";

        PasswordEncoder noOp = NoOpPasswordEncoder.getInstance();
        String noOpStored = noOp.encode(raw);

        PasswordEncoder modern =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();
        String hash = modern.encode(raw);

        System.out.println("NoOp stores raw: " + raw.equals(noOpStored));
        System.out.println("NoOp accepts raw: " + noOp.matches(raw, noOpStored));
        System.out.println("Modern uses bcrypt: " + hash.startsWith("{bcrypt}"));
        System.out.println("Modern stores raw: " + raw.equals(hash));
        System.out.println("Modern accepts raw: " + modern.matches(raw, hash));
        System.out.println("Modern rejects wrong: " +
            !modern.matches("wrong-password", hash));
        System.out.println("Legacy noop accepted: " +
            modern.matches(raw, "{noop}" + raw));
    }
}
```

Expected **program-only stdout** with the illustrative dependency set:

```text
NoOp stores raw: true
NoOp accepts raw: true
Modern uses bcrypt: true
Modern stores raw: false
Modern accepts raw: true
Modern rejects wrong: true
Legacy noop accepted: true
```

Crucially, look at the last line: the delegating encoder can **read old records with the `noop` ID**. Hence "the app switched its PasswordEncoder bean to Delegating" is not yet proof that all passwords are hashed. The demo intentionally **does not print random password hashes**; if printed, the specific characters would change on every run.

The fixed string `demo-only-password` is strictly sample data and must never be used as a real credential. Printing `NoOp stores raw: true` is a **warning**, not a recommended technique.

### 8.3. JUnit tests

Create `src/test/java/example/password/PasswordEncoderDemoTest.java`:

```java
package example.password;

import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.NoOpPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.junit.jupiter.api.Assertions.*;

class PasswordEncoderDemoTest {

    private static final String RAW = "demo-only-password";

    @Test
    void noOpReallyStoresPlaintext() {
        PasswordEncoder encoder = NoOpPasswordEncoder.getInstance();
        assertEquals(RAW, encoder.encode(RAW));
        assertTrue(encoder.matches(RAW, RAW));
        assertFalse(encoder.matches("wrong-password", RAW));
    }

    @Test
    void delegatingEncoderHashesNewPasswordsAndMatchesThem() {
        PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();
        String stored = encoder.encode(RAW);

        assertTrue(stored.startsWith("{bcrypt}"));
        assertNotEquals(RAW, stored);
        assertTrue(encoder.matches(RAW, stored));
        assertFalse(encoder.matches("wrong-password", stored));
    }

    @Test
    void bcryptUsesSaltRatherThanProducingTheSameHashEveryTime() {
        PasswordEncoder encoder = new BCryptPasswordEncoder();
        String a = encoder.encode(RAW);
        String b = encoder.encode(RAW);

        assertNotEquals(a, b);
        assertTrue(encoder.matches(RAW, a));
        assertTrue(encoder.matches(RAW, b));
    }

    @Test
    void legacyNoOpPrefixRemainsUnprotected() {
        PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();
        String stored = "{noop}" + RAW;

        assertTrue(encoder.matches(RAW, stored));
        assertTrue(stored.contains(RAW));
    }
}
```

The salt test checks that two `encode` calls normally produce different verifiers; because salt generation is random, the probability of a collision is tiny though theoretically non-zero. The test mainly illustrates the salting property, not a mathematical proof of entropy.

Run in the directory containing `pom.xml`:

```bash
java -version
mvn -version
mvn test
mvn -q -DskipTests compile exec:java -Dexec.mainClass=example.password.PasswordEncoderDemo
```

With JDK 17+, Maven, and dependencies resolved successfully, **4 JUnit tests are expected to pass**. Maven's console may print download or plugin logs depending on the environment; the stdout listing above shows `System.out.println` output, not full Maven logs. This is illustrative code for verification; results have not been measured directly on the reader's machine.

If Maven runs with a lower JDK than required, plugins/dependencies fail to download, or `spring-security-crypto` is missing from the classpath, fix the environment before blaming `PasswordEncoder`.

## 9. Proper integration with Spring Security Servlet

In a Spring Boot 3.x application using form login, responsibilities are typically divided as follows:

```text
POST /login
  |
UsernamePasswordAuthenticationFilter
  |
AuthenticationManager / DaoAuthenticationProvider
  |
UserDetailsService -> look up user and stored password verifier
  |
PasswordEncoder.matches(raw from request, verifier in DB)
  |
Success -> SecurityContext/session per configuration
Failure -> authentication failure handler
```

**`PasswordEncoder` does not call the database itself and does not modify stored passwords.** It only provides encoding and verification. `UserDetailsService` or the repository layer fetches the verifier; `AuthenticationProvider` coordinates verification. After successful login, session/context steps belong to Spring Security's authentication flow, not `PasswordEncoder`.

Demo-style configuration for Servlet:

```java
package example.websecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@Configuration
public class DemoUserConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-only-password"))
                .roles("USER")
                .build()
        );
    }
}
```

This is a complete bean class **in a Spring Boot Servlet project with web/security starters**; it is not a standalone web app compiled with `javac` alone. It creates a hashed verifier for the in-memory account instead of storing a raw password like:

```java
// DO NOT use with real accounts:
User.withUsername("alice")
    .password("{noop}demo-only-password")
    .roles("USER")
    .build();
```

With a real database, the registration or password-change layer must call **`encoder.encode(raw)` before saving**. At login, the authentication layer uses **`encoder.matches(raw, stored)`**. A password hash in the DB is not a credential for the app to return to clients. Never let an API endpoint serialize a `passwordHash` field just because "it is already hashed".

If an application uses an external identity provider via OIDC, it usually does not need to store user passwords locally. Handle identities/tokens per trust boundaries rather than creating an extra local password store.

## 10. Migrating a system that already stored plaintext or {noop}

Switching to a new encoder only makes **subsequent encodes** use the new algorithm; it does not automatically transform existing user records. A migration plan requires a baseline, data controls, rollback strategy, and testing.

### Option A — Controlled migration permitted to read plaintext

If the legacy system still holds plaintext passwords and an approved migration runs, you can iterate records **in a secured environment** to generate new password verifiers with `encoder.encode(raw)`, then write updates to the DB within appropriate transactions/controls.

Pay special attention: backups, replicas, logs, snapshots, analytics, and old exports **may still contain plaintext**. Converting the live DB to BCrypt does not erase old copies. The process needs a plan to protect/purge/rotate old data, anomaly monitoring, and notification or password-reset policies if data exposure is suspected.

Never print plaintext, pipe it across multiple systems, or write new intermediate files just for migration. When compromise cannot be ruled out, evaluate credential-reuse risk and whether password resets must be required.

### Option B — Rehash upon successful user login

When you do not want to process all plaintext passwords in bulk, you can allow a **very narrow** legacy mechanism strictly for accounts with verified data format. After a successful login:

1. Obtain the credential from the request over a protected channel and the user's current verifier.
2. Verify via the mechanism permitted for that exact legacy record/version; never treat arbitrary strings as plaintext automatically.
3. If authentication succeeds, generate a new verifier with a salted/cost-tuned password KDF and persist atomically; never log or retain raw credentials longer than needed.
4. Subsequent logins use the new verifier. Monitor the ratio of remaining legacy records and enforce a deadline to remove the old method.
5. For accounts that do not log in during the transition window, apply a mandatory reset policy or another approved mechanism.

**Service-layer pseudocode after authentication has already succeeded**:

```java
if (legacyCredentialVerified && legacyRecord) {
    String strongerVerifier = modernEncoder.encode(rawPassword);
    userRepository.updateVerifierIfUnchanged(
        userId, previouslyStoredVerifier, strongerVerifier
    );
}
```

The variables and methods here **illustrate atomic transactions/concurrency**, not a compilable class: `legacyCredentialVerified` must come from a trusted verification step, `updateVerifierIfUnchanged` must be implemented and tested by the system, and `rawPassword` must only be used inside a trusted request boundary. Never allow a public endpoint to accept a client-sent "new hash" to update credentials without proper verification and authorization.

### What never to do during migration

- **Never** replace records with `{noop}` to bypass login errors.
- **Never** prepend `{bcrypt}` onto plaintext to "migrate to BCrypt".
- **Never** automatically treat ID-less strings as plaintext for all accounts without format inventory and conversion bounds.
- **Never** write raw passwords to logs, tickets, or CSVs to assist migration.
- **Never** consider migration finished while backups, replicas, old hashes, and legacy auth paths remain uncontrolled.
- **Never** broaden access to old data merely for migration convenience.

## 11. When is NoOp still acceptable during learning?

NoOp may be used to **clearly demonstrate the harm of not hashing passwords** in a unit test or isolated runnable example with fake credentials, under these conditions:

- Use only worthless **dummy strings**, never real passwords or real accounts.
- Never deploy the demo as a public service or connect it to a production user store.
- Never store sensitive data or copy a real user DB into a test environment to experiment.
- Clearly note that data produced by `NoOpPasswordEncoder` **is plaintext** and must not be used in production.
- Do not stop the exercise at "NoOp login worked"; compare against BCrypt/delegating encoders to understand why replacement is necessary.
- Production code and production-like integration tests should use real `PasswordEncoder`s and hashed credential fixtures; authentication and password-change flows must be tested under deployment-like behavior.

Even in tiny exercises, **there are safer ways to demo right from the start** using `BCryptPasswordEncoder` or `PasswordEncoderFactories.createDelegatingPasswordEncoder()`. The extra setup cost is tiny compared to the risk of accidentally copying `{noop}` code into a real application.

## 12. Password hashing is only one part of a login policy

Even when the database stores no plaintext, you must still protect:

- **HTTPS/TLS:** protects passwords in transit. A KDF does not encrypt form submissions when clients send raw passwords to the server.
- **CSRF:** for cookie/session websites, form login and state-changing operations require proper CSRF protection; password hashing does not replace CSRF.
- **Rate limiting and credential-stuffing defenses:** password hashing slows offline guessing, not millions of online login requests from attackers. Rate limits, fraud detection, and appropriate lockout/throttling policies are required.
- **MFA/passkeys:** extra protection against password reuse, phishing, and password-only compromise.
- **Authorization:** even after successful authentication, users are not automatically entitled to every resource; enforce ownership/tenant checks and proper roles/scopes.
- **Protecting databases, logs, backups, and secrets:** least-privilege access, appropriate encryption, and data lifecycle procedures.
- **Password change/reset:** verify account ownership, expire reset tokens, block replay, and handle active sessions after reset according to policy.
- **Monitoring and upgrading KDFs:** evaluate encoder cost against infrastructure capacity, audit legacy records, and prepare algorithm-change strategies when security guidance evolves.

Password hashing does not make passwords unguessable. Weak passwords like `123456` are still easy to brute-force offline if verifiers leak, merely taking longer depending on KDF and cost. Encourage strong passwords or phishing-resistant authentication rather than treating hashing as the sole line of defense.

## 13. Common mistakes when configuring Spring Security

| Symptom | Cause worth checking | How to handle |
|---|---|---|
| Login succeeds even though DB stores plaintext | Using `NoOpPasswordEncoder` or `{noop}` | Audit encoders/records, move to salted/cost-tuned KDF, retire legacy on schedule |
| `There is no PasswordEncoder mapped for the id "null"` or unknown ID | Delegating encoder does not recognize stored format | Check actual prefix; never use a global plaintext fallback to mask the error |
| Hashed password always fails login | Re-encoding raw and comparing hash strings; mismatched algorithm/prefix | Use `matches(raw, stored)` and align encoders by ID |
| Two accounts with the same password have different hashes | Random salt | **Usually the right behavior**, not a bug |
| Old users cannot log in after changing encoder | Legacy records lack prefix or encoder lacks migration plan | Identify format, plan rehash/reset |
| Login CPU spikes after raising work factor | Cost too high for live load or system under brute force | Benchmark and enforce rate limits, capacity, monitoring |
| Hash appears in API response | Serializing entity directly without stripping password verifier field | Use minimal DTOs, guard serialization, and test responses |
| Passwords leaked in logs/traces | Logging request form bodies, user objects, auth debug | Redact/sanitize data and restrict observability |
| User changes password yet old session stays alive | Session/logout policy omits invalidation | Design re-authentication, revocation/session invalidation |
| Using `bcrypt` yet accepting old `{noop}` records | Delegating encoder still has noop mapping | Audit records, block new noop records, and migrate all legacy entries |

**Key distinction to remember:** a 401/login redirect alone is not enough to diagnose an encoder; check HTTP method, CSRF, username lookup, `PasswordEncoder`, and the `AuthenticationFailureHandler` branch along the actual flow. Never disable security just to "make tests green".

## 14. Pre-launch checklist for systems with password login

- [ ] No real user passwords are stored in plaintext or `{noop}` form in databases, configs, logs, or unguarded backups.
- [ ] New passwords use a dedicated `PasswordEncoder` like BCrypt or a policy-compliant salted, cost-tuned password KDF.
- [ ] Authentication uses `matches(raw, stored)`; never compare two `encode` outputs with string equality.
- [ ] A classification/migration mechanism exists for old records, with no indefinite plaintext fallback.
- [ ] Verifier data is never exposed in API responses, analytics, logs, or support tools.
- [ ] HTTPS, CSRF (by client type), rate limiting, MFA, and session management are independently designed.
- [ ] Cost is benchmarked in the target environment, login DoS risks are evaluated, and the chosen algorithm handles expected password inputs.
- [ ] Credential-reuse risks and password-reset procedures for data incidents are reviewed.
- [ ] Integration tests cover valid/invalid passwords, old/new verifiers, password changes, session logout, and resource authorization.
- [ ] All NoOp usage in tests is clearly marked "demo-only" and never copied into production configuration.

### Self-check questions

**1.** What does `NoOpPasswordEncoder.encode("abc")` return and why is it dangerous?  
**Answer:** It returns `"abc"`, literally a no-op. Anyone reading the verifier knows the original password without cracking any hash.

**2.** Why not use single-pass `MessageDigest SHA-256` to store passwords?  
**Answer:** General-purpose hashes are too fast and lack built-in salting/cost suited for password storage, making billions of offline guesses far easier than with a password KDF.

**3.** Two BCrypt encodes of the same password give different outputs, yet `matches` returns true for both; is that a contradiction?  
**Answer:** No. Random salt makes verifiers differ; `matches` uses the metadata inside the verifier to compute and check accurately.

**4.** You already use `DelegatingPasswordEncoder`, yet a DB record still holds `{noop}alice-password`. Is it secure?  
**Answer:** Not yet. The data after the prefix is still plaintext and may still be accepted by the NoOp delegate; inventory and migrate/reset passwords per policy.

**5.** Can you prepend `{bcrypt}` before a plaintext password and treat it as a BCrypt hash?  
**Answer:** No. The prefix is only an algorithm tag; you must actually run the password KDF and store a properly formatted verifier.

**6.** When using BCrypt, do you still need HTTPS and online brute-force protections?  
**Answer:** Yes. BCrypt protects exposed verifiers and raises offline guessing costs; it does not encrypt network transport or block online login attacks.

**Conclusion:** `NoOpPasswordEncoder` and plaintext passwords are only fit for **visualizing dummy data paths in isolated illustrative lessons**. Applications serving real users must store **password verifiers generated by a dedicated KDF**, verify via `PasswordEncoder.matches`, manage formats/upgrades carefully, and protect the entire credential lifecycle—from forms, databases, and backups to logs and resets.
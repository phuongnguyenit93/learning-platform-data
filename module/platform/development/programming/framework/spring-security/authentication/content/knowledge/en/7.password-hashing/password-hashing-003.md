# Salt, Cost Factor, and Resistance to Password Guessing

## Objectives

A password is a secret known by the user. When storing it in a system, **never store plaintext passwords**, never use reversible encryption so it can be decrypted back, and never rely solely on a single fast hash such as one-round SHA-256. The standard storage approach is to use a **purpose-built password-hashing function**, generate a unique random *salt* per hash, and configure a *cost factor* (work factor) so that each password guess consumes significant resources.

This lesson belongs to the **Password Hashing** group, *Spring Security - authentication* module, focusing on three topics:

1. **Salt** ensures two identical passwords produce two distinct hash records and destroys the economics of precomputed lookup tables (rainbow tables).
2. **Work factor** slows down every password attempt, especially when an attacker has obtained the hash database and can guess *offline*.
3. **Resisting password guessing** is defense in depth: a slow hash function only protects stored data; defending against *online* login attempts also requires rate limiting, MFA, safe error messages, and monitoring.

Examples use Java 17+, Spring Boot 3.x / Spring Security 6.x. The cost levels in this lesson are **illustrative numbers**, not default production settings for every machine. When deploying, benchmark on real hardware, traffic, and library versions.

## 1. Threat Model: Why Does Password Hashing Matter?

There are two very different types of attacks.

### 1.1. Online Password Guessing (*online guessing*)

An attacker sends many login requests to the server:

~~~text
Attacker -> POST /login (username, try password #1)
         -> POST /login (username, try password #2)
         -> ...
         -> server checks each attempt itself
~~~

The server can control the request rate: rate limiting, throttling per account/IP/risk signal, progressive challenges, MFA, anomaly detection, and uniform error responses. Work factor affects the CPU of **both the server and the attacker**, yet **does not by itself stop** sending many requests. Excessively high cost can even help an attacker exhaust CPU with repeated login requests.

### 1.2. Offline Password Cracking (*offline cracking*)

A SQL injection incident, exposed backup, or misconfigured DB permissions allows an attacker to obtain the table containing password hashes:

~~~text
exposed users table
username      password_hash
alice         $2a$12$...
bob           $2a$12$...
...
          |
          v
Attacker can test passwords on their own machines
without sending requests to our server
~~~

Login API rate limiting **cannot limit** how fast an attacker tests hashes on their own hardware. Each candidate password is checked against the stolen hash data. That is where **unique salts** and **high-cost hashing** make the difference.

No hashing scheme makes a weak password "unguessable". For example, password `123456` is still in common dictionaries. Good hashing **raises attack cost**; it does not replace sufficiently strong passwords, password-reuse prevention, breached-password detection, and MFA.

## 2. Distinguishing Hashing, Encryption, Salt, Pepper, and Work Factor

| Concept | Purpose | Is it secret? | Example |
| --- | --- | --- | --- |
| **Password hashing** | Transform a password into a one-way verification value | Stored hashes in DB must be protected, though the algorithm need not be secret | bcrypt, Argon2id, scrypt, PBKDF2 |
| **Encryption** | Transform data with a key so it can be decrypted | The key must be kept secret | AES used for data needing recovery, not the primary solution for storing passwords |
| **Salt** | Make each password's hash independent, preventing precomputed lookups and linking identical hashes | **No**; usually stored alongside the hash | Unique random salt for each `encode` call |
| **Work factor/cost** | Intentionally make hash creation/verification expensive in time, CPU, or RAM | **No**; usually recorded inside the hash string | bcrypt cost `12`; Argon2id has memory/time/parallelism |
| **Pepper** | Additional secret outside the database, supporting defense in depth | **Yes**; must be stored separate from DB | Key in secret manager/HSM used in a controlled HMAC design |

**Hashing is not encryption.** There is no "decrypt password hash" operation to recover the original password. When users forget their passwords, design a reset flow using valid proof of ownership; never attempt to decrypt hashes.

**Salt is not pepper.** Salt may sit publicly inside the hash string. Pepper is a shared or deployment-scoped secret; if used, it requires secret governance, rotation, recovery, and standard cryptographic design. Do not store pepper in the same password hash table and assume you have an extra secret layer.

## 3. How Does Random Salt Work?

Suppose Alice and Bob choose the same password. If an **unsalted** hash function is applied:

~~~text
H(password) = digest
H(password) = same digest
~~~

Two records can contain the same hash. An attacker can recognize accounts sharing the same password and use a single precomputed result to check hashes in bulk.

With unique salts:

~~~text
Alice:
  password = P
  salt = random_A
  stored = PasswordHash(P, random_A, cost)

Bob:
  password = P
  salt = random_B
  stored = PasswordHash(P, random_B, cost)

random_A != random_B
=> two stored hashes differ with overwhelming probability
~~~

In practice, a password-hashing library typically generates salt using a cryptographic random number generator, then encodes the salt, cost, and result into the stored string. You **do not need to generate salt manually** when using `BCryptPasswordEncoder` or an equivalent implementation properly.

### 3.1. Which Problems Does Salt Solve?

- **Resisting rainbow tables:** a precomputed hash table can no longer be reused efficiently across all passwords because each record has a different salt.
- **Reducing duplicate-password recognition:** two users with the same password usually receive different hashes, so identical passwords cannot be spotted merely by inspecting hash strings.
- **Multiplying cost across accounts:** attackers must perform work per salt/hash rather than sharing all work across accounts.

### 3.2. Which Problems Does Salt NOT Solve?

- Salt **does not turn a weak password into a strong one**. An attacker with hash + salt can still test common passwords against each record.
- Salt **is not a secret key**; you do not need to hide the salt from an attacker to get its protection.
- Salt **does not replace work factor**. `SHA-256(salt || password)` is still far too fast for a password store.
- Salt **does not by itself stop online guessing** against `/login`.
- Self-generated salts with poor randomness, fixed system-wide salts, or salts reused across multiple users can weaken the design.

Never pick a salt from username, email, or a constant in source code: such values are predictable and typically fail randomness/uniqueness guarantees. Do not add an external `SecureRandom` string concatenation if the standard encoder already manages salt internally; improper manual concatenation can break `matches` compatibility.

### 3.3. When Resetting or Changing a Password

Calling `encode(newPassword)` generates a new salt and a new hash value. Never "reuse/patch the old salt" and expect verification to work as before. If the system stores hashes in standard format strings, store the **entire encoded password string** so `matches(raw, storedHash)` later reads the right parameters.

You do not need an extra separate salt column for bcrypt just to run standard Spring Security; the bcrypt string already embeds salt and cost. Legacy schemas may split columns for historical reasons, but migrating them requires a tested migration process.

## 4. Work Factor: Intentionally Making Attempts Resource-Intensive

A SHA-256 computation can run extremely fast on specialized hardware; that is an advantage in many other applications but a **disadvantage** when protecting passwords. Purpose-built password hashing uses an **adaptive one-way** function: operators choose how much work each hash/match operation must perform.

### 4.1. What Is Bcrypt Cost?

In `BCryptPasswordEncoder`, `strength` is bcrypt's *log rounds* (cost). Internal work grows exponentially at roughly `2^cost`; thus, incrementing cost by 1 roughly **doubles** the work involved, rather than adding a fixed amount of time.

*Relative* comparison example, not a benchmark:

| Bcrypt cost | Relative work compared to cost 10 | Notes |
| --- | --- | --- |
| `10` | 1× | Default value of `BCryptPasswordEncoder` in Spring Security 6.x |
| `11` | About 2× | Increased computation |
| `12` | About 4× | Used in example to observe raising cost |
| `13` | About 8× | Must evaluate CPU load |
| `14` | About 16× | Do not pick based on "bigger is always better" |

These ratios describe bcrypt's work structure and **do not promise** latency on real machines/CPUs scales by the exact factor. Runtime also depends on thread scheduling, JVM warm-up, CPU model, request density, and resource contention.

`BCryptPasswordEncoder` supports costs from 4 to 31, defaulting to 10. **Do not choose cost 4 for production just because it is fast**; nor set 20–31 arbitrarily due to denial-of-service risk. Measure on real infrastructure and follow current applicable security guidance.

### 4.2. What Cost Should You Choose?

Spring Security 6.5 documentation recommends tuning adaptive password hashes to take **roughly one second for verification on your system**, while balancing load and UX. OWASP emphasizes a work factor high enough to raise attack cost without causing overload, and notes tuning must be based on testing. Both guidelines provide **performance/risk direction**, not a substitute for measuring in your actual application.

Evaluate at least:

1. CPU and RAM on production machines or an equivalent specification.
2. p50/p95/p99 latency of `matches(...)` after warm-up, not a single measurement.
3. Normal and peak logins/second; concurrent authentication requests.
4. Exposure to synthetic load caused by wrong password/username requests.
5. Total latency combining DB lookup, hash verification, MFA, and network overhead.
6. Existing cost values stored in legacy hashes and versioned upgrade plans.
7. Container CPU/RAM limits along with autoscaling and rate-limit settings.

A reasonable cost for one workload may be too heavy or too light for another. Schedule re-benchmarking when changing instance types, hardware, JDK/Spring Security versions, or security requirements.

### 4.3. What Are the Drawbacks of Increasing Cost?

- The server must do more work on every valid login.
- Wrong password attempts also consume CPU; traffic limits and DoS protections are necessary.
- It can increase login latency, timeouts, and queuing, affecting other services.
- Migrating individual hashes takes planning; changing only the encoder bean does not convert existing hashes into new ones.
- For memory-intensive algorithms such as Argon2id, you must test memory pressure under concurrent logins.

**Do not use a slow password hash to re-authenticate a password on every API request.** Spring Security recommends transitioning after password authentication to short-lived credentials such as a session or an appropriate access token; token/context validation is typically much lighter. Separate token protection and expiration/revocation policies are still required.

## 5. Reading the Bcrypt Format to Locate Salt and Cost

A typical bcrypt string looks like:

~~~text
$2a$12$...............................
^^^^^^^
 $2a$  : bcrypt variant
    12 : cost (illustrative)
~~~

The full form is typically **60 ASCII characters** long, with structure:

~~~text
$2a$12$[22 characters encoding salt][31 characters encoding result]
~~~

The square brackets on the line above are **explanatory notation only**, not a valid hash string. A real hash uses bcrypt's encoding alphabet and contains no brackets. Version may be `$2a$`, `$2b$`, or `$2y$` depending on implementation/settings.

What must be retained is the **entire bcrypt string** (version, cost, salt, hash) in the database. Do not strip the `$2a$12$` prefix, do not store only the last 31 characters, and do not store cost separately and forget compatibility during verification.

Bcrypt uses a **16-byte** random salt; it is encoded into **22 characters** in the encoded string. The parameters represented inside the hash are not secrets requiring extra encryption just to conceal the algorithm. The algorithm is public; security relies on the function's properties, password entropy, and attack cost, not on hiding the cost.

### 5.1. If Generated Hashes Are Random, How Does matches Compare Them?

Suppose:

~~~java
BCryptPasswordEncoder encoder = new BCryptPasswordEncoder(12);
String first = encoder.encode("demo-only");
String second = encoder.encode("demo-only");
~~~

`first` and `second` usually differ because each uses a new salt. Yet:

~~~java
encoder.matches("demo-only", first);  // true
encoder.matches("demo-only", second); // true
~~~

`matches` **reads the parameters/salt from the stored hash**, runs the matching computation, and checks the result. It **does not** call `encode(rawPassword)` with a new random salt and compare strings.

Wrong:

~~~java
// WRONG: encode generates a new salt, so do not compare strings like this.
boolean valid = encoder.encode(inputPassword).equals(storedHash);
~~~

Right:

~~~java
boolean valid = encoder.matches(inputPassword, storedHash);
~~~

Never use Java's `hashCode()`, MD5, or single-round `MessageDigest.getInstance("SHA-256")` for production passwords. They do not provide a suitable work factor for password storage.

## 6. Runnable Java 17+ Program: Two Salts and Increasing Cost

The following example is a **Spring Boot CLI** application with no HTTP endpoints and no database required. It demonstrates:

- Two `encode` calls with the same password return different hashes.
- `matches` still accepts the right password and rejects the wrong password.
- A cost-10 hash is still verified by an encoder configured with cost 12.
- `upgradeEncoding` detects that the old hash has a lower cost than desired.
- There is no "fixed hash" output: salts are generated randomly.

### 6.1. Preparing the Project

Create a project from Spring Initializr:

- Java **17** or **21**, Spring Boot **3.x**, **Maven**.
- Group `com.example`, artifact `password-cost`, package `com.example.demo`.
- Dependency **Spring Security** (`spring-boot-starter-security`). Do not select Spring Web: we only run on the command line.
- Spring Initializr generates `pom.xml` and the Maven Wrapper.

Create **`src/main/java/com/example/demo/PasswordCostApplication.java`**:

~~~java
package com.example.demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;

@SpringBootApplication
public class PasswordCostApplication {

    public static void main(String[] args) {
        SpringApplication.run(PasswordCostApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstrate() {
        return args -> {
            String raw = "Demo-only-password-2026!";

            BCryptPasswordEncoder cost10 =
                new BCryptPasswordEncoder(10);
            BCryptPasswordEncoder cost12 =
                new BCryptPasswordEncoder(12);

            String hashA = cost10.encode(raw);
            String hashB = cost10.encode(raw);
            String hashC = cost12.encode(raw);

            System.out.println("differentSalts="
                + !hashA.equals(hashB));
            System.out.println("correctPassword="
                + cost10.matches(raw, hashA));
            System.out.println("wrongPassword="
                + cost10.matches("wrong-password", hashA));
            System.out.println("oldHashStillMatches="
                + cost12.matches(raw, hashA));
            System.out.println("oldHashNeedsUpgrade="
                + cost12.upgradeEncoding(hashA));
            System.out.println("newHashNeedsUpgrade="
                + cost12.upgradeEncoding(hashC));
        };
    }
}
~~~

### 6.2. Running and Expected Output

From the Maven project directory:

~~~bash
./mvnw spring-boot:run
~~~

Windows PowerShell: `.\mvnw.cmd spring-boot:run`. Aside from Spring Boot logs, the `CommandLineRunner` prints:

~~~text
differentSalts=true
correctPassword=true
wrongPassword=false
oldHashStillMatches=true
oldHashNeedsUpgrade=true
newHashNeedsUpgrade=false
~~~

Explanation:

- `differentSalts=true`: two hashes generated independently with random salts differ in practice (salt collision probability is minuscule). Do not use this test to "prove with absolute certainty" random collisions can never happen.
- `correctPassword=true`: the same password matches hash A.
- `wrongPassword=false`: the wrong password does not match.
- `oldHashStillMatches=true`: `BCryptPasswordEncoder(12)` still verifies the cost-10 hash because the old cost is embedded in the hash.
- `oldHashNeedsUpgrade=true`: the cost-12 encoder recognizes that the cost-10 hash should be considered for rehashing.
- `newHashNeedsUpgrade=false`: the newly generated cost-12 hash already meets the configured cost.

**This output is deterministic in terms of booleans** on the described API version. If you also print `hashA`, `hashB`, or elapsed runtime, those values are **not fixed** across runs.

The demo embeds a dummy password in source code strictly for learning. In production, never hardcode passwords, never log raw values, never return hashes in APIs, and never use demo hashes as real credentials.

### 6.3. Measuring Time Without Inventing Fake Numbers

An **illustrative code snippet inside the same method** once `encoder`, `storedHash`, and `raw` are available:

~~~java
long start = System.nanoTime();
boolean ok = encoder.matches(raw, storedHash);
long elapsedNs = System.nanoTime() - start;

if (!ok) {
    throw new IllegalStateException("Expected valid test password");
}
System.out.println("verifyMillis=" + elapsedNs / 1_000_000.0);
~~~

This snippet **cannot run standalone**, and timing results are **environment-dependent**. For real microbenchmarking, you need JVM warm-up, multiple runs, tools like JMH when appropriate, CPU contention control, and p95/p99 evaluation across concurrency levels. Never conclude "cost 12 is always 250 ms" from a single measurement on a laptop.

## 7. How Does Spring Security Use an Encoder to Authenticate?

In Servlet username/password flows, the typical sequence is:

~~~text
POST /login or Authorization: Basic ...
    |
    v
Authentication filter
    |
    v
AuthenticationManager -> DaoAuthenticationProvider
    |
    +-- UserDetailsService.loadUserByUsername(username)
    |       -> UserDetails.getPassword(): storedHash
    |
    +-- PasswordEncoder.matches(rawPassword, storedHash)
    |       -> true: check account flags and policy next
    |       -> false: authentication failure
    |
    v
Authentication succeeds / exception
    |
    v
SecurityContext + authorization
~~~

**UserDetailsService does not compare passwords itself.** It returns a record (typically containing the hash) by username. `DaoAuthenticationProvider` uses `PasswordEncoder` to verify the proof. Afterward, account status checks, authorities, and SecurityContext management remain separate responsibilities.

Basic encoder bean configuration:

~~~java
@Bean
PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder(12);
}
~~~

This is **configuration code inside a Spring `@Configuration` class**, requiring imports for `Bean`, `PasswordEncoder`, and `BCryptPasswordEncoder`. Cost 12 is illustrative; production requires benchmarking. Password when **creating/changing** an account:

~~~java
String storedHash = passwordEncoder.encode(rawPassword);
accountRepository.savePasswordHash(userId, storedHash);
~~~

This snippet is **not runnable standalone** because `accountRepository` and `userId` belong to the application domain. In practice you need transactions, authorization checks for password changes, auditing, and appropriate password policies. At login, the provider uses `matches`; never hash a second time with a new salt and compare strings.

### 7.1. Stored Hash Format Differs from DelegatingPasswordEncoder

With **plain `BCryptPasswordEncoder`**, hashes look like:

~~~text
$2a$12$...
~~~

With **`DelegatingPasswordEncoder`**, strings typically carry an encoder ID prefix:

~~~text
{bcrypt}$2a$12$...
~~~

`PasswordEncoderFactories.createDelegatingPasswordEncoder()` creates an encoder capable of recognizing the `{id}encodedPassword` format. `id` selects the algorithm; `bcrypt` is one option, while other IDs can support migrations.

Do not manually strip `{bcrypt}` and store half a string, nor feed a plain bcrypt string into a default `DelegatingPasswordEncoder` assuming it will infer the algorithm. Per documentation, missing/unmapped IDs can throw `IllegalArgumentException` if no fallback is configured. Never use `{noop}` or a plaintext-accepting fallback in production to "fix" old hash errors.

A specific `PasswordEncoder` configuration must be used **consistently** across account creation, password change, and login; swapping encoders without a migration path can lock out all users.

## 8. Raising the Work Factor Without Forcing Everyone to Change Passwords Immediately

Bcrypt's compatibility mechanism reads the work factor from the old hash, so an encoder configured with cost 12 can still verify a cost-10 hash. However:

**Changing `new BCryptPasswordEncoder(10)` to `new BCryptPasswordEncoder(12)` does not automatically rewrite every hash in the database.** Old hashes can only be upgraded when a valid raw password is available at a legitimate moment or when the user changes/resets their password. You cannot properly "rehash" from an old hash alone to increase cost.

### 8.1. Controlled Upgrade Process

1. Choose target cost/algorithm after benchmarking.
2. Preserve `matches` compatibility with old hashes during the transition period.
3. When a user logs in successfully with the right password, check `passwordEncoder.upgradeEncoding(storedHash)`.
4. If an upgrade is needed, use the **raw password available only within the active authentication flow** to re-`encode` with a new salt/new cost.
5. Persist the new hash through a secure credential management layer; use optimistic locking/compare-and-set to avoid overwriting a concurrent password change.
6. Clear/do not retain raw passwords long-term, enforce transactions, record appropriate audit metadata; never log raw or encoded hashes.
7. Users who never log back in still retain old hashes: establish a password reset or hash-age policy.

### 8.2. Hooks in Spring Security

`PasswordEncoder` has the `upgradeEncoding(String encodedPassword)` method. In flows using `DaoAuthenticationProvider`, you can register a `UserDetailsPasswordService` to persist upgraded hashes after valid authentication:

~~~java
// Illustrative configuration, not a standalone Java file.
// users: UserDetailsService
// encoder: PasswordEncoder
// updates: UserDetailsPasswordService implemented by the application
DaoAuthenticationProvider provider =
    new DaoAuthenticationProvider(users);

provider.setPasswordEncoder(encoder);
provider.setUserDetailsPasswordService(updates);
~~~

`UserDetailsPasswordService.updatePassword(UserDetails user, String newPassword)` receives the **already encoded password**, persists it to the matching account under a trusted identity, and returns the updated `UserDetails`. You must implement this service for your real repository/domain; calling `setUserDetailsPasswordService(...)` without proper persistence will not update the database by itself.

With `DelegatingPasswordEncoder`, check whether `upgradeEncoding(...)` signals changing the **algorithm ID** or changing **parameters** under the current ID. Never strip the `{id}` prefix arbitrarily; the prefix is part of the format.

### 8.3. Migrating Old Hashes Without a Prefix

Some legacy databases contain SHA-1, older PBKDF2, or plain bcrypt. Do not relabel all records as `{bcrypt}` if they are not actually bcrypt. You need a plan to classify formats based on verified data, map compatible encoders, and migrate after login/reset.

Be careful with legacy formats that are **insufficiently secure**, such as plaintext, MD5, direct SHA-1, or single-round SHA-256. If short-term compatibility is unavoidable, restrict its scope, prioritize resets/upgrades, and set a deadline to remove weak support. Never set `NoOpPasswordEncoder` as the default fallback.

## 9. Which Algorithm Fits: bcrypt, Argon2id, scrypt, PBKDF2?

| Algorithm | Cost mechanism | Strengths | Considerations |
| --- | --- | --- | --- |
| **Argon2id** | RAM + passes + parallelism | Memory-hard, limits parallel hardware advantage in many scenarios | RAM budget, library dependencies, concurrency benchmarks |
| **scrypt** | Memory and CPU via `N/r/p` | Memory-hard; option when Argon2id is unsuitable | High RAM usage, requires benchmarking under concurrent logins |
| **bcrypt** | Log-round cost, primarily CPU | Widely used, built into Spring Security, self-manages salt | 72-byte input limit, CPU throughput |
| **PBKDF2** | Iteration count/HMAC | Standard integration; fits certain compliance/FIPS mandates | CPU-hard, requires proper parameters and implementation |

OWASP currently prefers **Argon2id** for new systems when the environment allows and continues to provide bcrypt guidance for many legacy systems. Spring Security 6.5 supports bcrypt, Argon2, scrypt, and PBKDF2 under `PasswordEncoder`; for `Argon2PasswordEncoder`, Spring documentation notes the Bouncy Castle dependency requirement. **Do not treat cost numbers across algorithms as equivalent**: bcrypt `12` is not directly comparable to PBKDF2 600,000 iterations or Argon2id 19 MiB memory.

When selecting an algorithm, evaluate actively maintained libraries/frameworks, format upgradability, resource constraints, compliance mandates, security testing, and deployment platform. Never invent multi-hash combinations (such as an outer SHA-256 before bcrypt) without expert cryptographic design and review.

### 9.1. Bcrypt's 72-Byte Limit

Many bcrypt implementations impose a limit of **72 bytes of input data**, **not 72 Unicode characters**. With UTF-8, a Vietnamese character or emoji can take multiple bytes. If the limit is exceeded and the library truncates, two passwords differing only in their suffix may verify identically.

If using bcrypt, the application must enforce a **byte-length** policy compatible with the implementation, never silently truncating passwords, and never differing between registration and login screens. Nor should you arbitrarily forbid strong long passphrases: if you need to support passphrases longer than bcrypt's limit, consider a modern algorithm without that limitation or a thoroughly vetted design.

Never blindly pre-hash with SHA-256 before feeding bcrypt to "work around" the limit without evaluating password shucking, null bytes, input encoding, and migration issues; OWASP specifically warns against uncontrolled pre-hashing techniques.

### 9.2. Unicode and Password Normalization

Distinguish username normalization from **password policy**. Passwords are secrets: do not arbitrarily `trim()`, lowercase, strip Vietnamese diacritics, or normalize Unicode on one side without consistent, justified enforcement. Leading/trailing spaces can be part of a real password.

If deciding on Unicode normalization (e.g., NFC) for passwords, define it uniformly across registration, login, and password change/reset, and ensure users are not locked out across version updates. Never "preprocess and try multiple variants" to match a password, as that alters authentication semantics and widens the attack surface.

## 10. Pepper: Complementary, Not a Replacement for Salt/Cost

Pepper is a server-managed secret not stored alongside the hash table. It can add protection when an attacker steals **only the database** without compromising the secret infrastructure. For instance, an HMAC design with a key inside a vault/HSM can raise attack cost if DB data is exposed.

Do not treat pepper as a "shared salt" hardcoded in source code or `application.properties` and committed to the repository. It requires least-privilege access, auditing, rotation, and a recovery plan. If the pepper leaks, you may have to force password changes/resets depending on architecture, since you cannot simply "rotate the pepper" on old hashes without raw passwords.

**Pepper does not fix every problem:**

- Weak passwords still require policies and breached-password checks.
- Too low a work factor still makes each guess relatively cheap if the pepper also leaks.
- Online password spraying still requires rate limiting and MFA.
- If both the server and vault are breached together, an attacker may obtain both hashes and pepper.

For most applications, properly implementing adaptive password hashing with random salts and suitable cost **matters far more** than inventing custom ways to concatenate a pepper into password strings. If pepper is required, adopt a documented, audited cryptographic model with a rotation plan.

## 11. Defending Against Online Guessing: Measures Outside PasswordEncoder

Even with Argon2id or very high bcrypt cost, a login API can still be probed at scale without control layers:

1. **Multi-dimensional rate limiting:** by account identifier, connection address past trusted proxy boundaries, device/risk signals, and system-wide limits. Avoid relying solely on IP due to NAT/proxies, or solely on username since attackers can distribute targets.
2. **Anti-password spraying:** detect one password being tried across many accounts, not just many passwords on one account.
3. **MFA/passkeys:** add a factor hard to steal if a password leaks, preferring phishing-resistant mechanisms where feasible.
4. **Breached passwords:** screen against trusted compromised-password sources without designs that expose raw passwords.
5. **Generic error messages:** do not let unauthenticated callers distinguish nonexistent accounts, disabled accounts, and wrong passwords via observable response bodies or timing.
6. **Resource protection:** concurrency limits, backpressure, timeouts, lookup circuit breakers, and monitoring CPU and latency under heavy bcrypt/Argon2 load.
7. **TLS and secret hygiene:** login over HTTPS, never log passwords, Authorization headers, cookies, hashes, or pepper; protect DB backups with least privilege.
8. **Audit and alerting:** log minimal metadata about failure/success events with proper access controls and retention periods.

Locking accounts after too few wrong attempts can be abused by attackers to cause **denial of service for legitimate users**. Design appropriate adaptive throttling and recovery, rather than turning a public username into an indefinite account-lockout switch.

## 12. Common Mistakes and How to Fix Them

| Mistake | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| Storing plaintext passwords | DB/backup exposure immediately exposes credentials | Use adaptive password hashing |
| Single-round `SHA-256(password)` | Too fast to resist offline guessing | Use properly configured Argon2id/bcrypt/scrypt/PBKDF2 |
| Sharing a fixed salt | Hashes across accounts become correlatable; precomputed results reusable | Unique random salt per `encode`, managed by the library |
| Treating differing hashes as a bug | Encoder uses random salts, so output is intentionally non-deterministic | Verify with `matches`, do not compare two encoded strings |
| `encode(raw).equals(stored)` | `encode` generates a new salt | Use `matches(raw, stored)` |
| Storing only the hash part, dropping cost/salt | Parameters needed for verification are lost | Store the entire encoded string |
| Bcrypt cost too low | Offline guessing is too cheap | Benchmark and raise cost/algorithm safely |
| Bcrypt cost too high | Slow logins, abusable to exhaust CPU | Benchmark concurrency, rate limit, capacity planning |
| Changing encoder bean and assuming DB hashes upgraded | Old hashes do not update automatically | Rehash on successful login/reset with `upgradeEncoding` and persistence |
| Stripping `{bcrypt}` prefix when using delegating encoder | Format mismatches ID mapping | Standardize format, plan migration |
| Storing pepper alongside hashes | DB attacker gets both | Store secret separately in vault/HSM |
| Ignoring bcrypt's 72-byte limit | Long passphrases may be truncated/equivalent | Consistent byte-length policy or choose another algorithm |
| Blocking online login solely via high cost | Work factor does not replace rate limiting | Add rate limits, MFA, security observability |
| Verifying password on every API request | Slow hashing hurts throughput and widens DoS surface | Switch to short-lived session/token after login |
| Logging raw passwords/hashes for debugging | Leaks credentials via logs/traces | Log non-sensitive event codes |

## 13. Scenarios and Self-Check Questions

**Question 1.** Alice and Bob use the same password. Their bcrypt hashes differ. Is the data corrupted or are the passwords different?

**Answer:** Not necessarily. Bcrypt uses different random salts, so the same password produces different hashes. Use `PasswordEncoder.matches` against each respective hash.

**Question 2.** Can salt be stored publicly in a column or inside the hash string?

**Answer:** Yes. Salt is not a secret. Bcrypt normally stores the salt together with the cost and hash. Pepper is the optional secret that must be stored separately.

**Question 3.** If bcrypt cost increases from 10 to 12, can old hashes still be verified?

**Answer:** Yes, with an appropriate `BCryptPasswordEncoder`; the old hash embeds its cost. However, the DB will not rehash automatically until a valid raw password is available in an upgrade or reset flow.

**Question 4.** Why not use single-round `SHA-256(password + salt)`?

**Answer:** Salt helps resist precomputation, but single-round SHA-256 is still far too fast on attack hardware. A high-cost adaptive password-hashing function is required.

**Question 5.** A company sees 20,000 failed logins/minute and raises bcrypt cost to 20. Is that enough to stop brute force?

**Answer:** No; it can also trigger a CPU DoS. You need rate limiting, monitoring, MFA, anti-password spraying, capacity planning, and performance verification.

**Question 6.** The DB data leaked, but the attacker does not have the pepper in the vault. How does pepper help?

**Answer:** It can add protection if pepper is modeled properly, though it does not replace salt/cost, does not help if the vault is also compromised, and requires a rotation/recovery plan.

**Question 7.** A user creates an 80-character Unicode password with bcrypt. Can you assume bcrypt checks all characters?

**Answer:** No. Many bcrypt implementations cap input at **72 bytes**, not characters. Enforce a byte-based policy or pick an algorithm suited for long passphrases without silent truncation.

**Question 8.** `BCryptPasswordEncoder.matches(raw, stored)` returns true. Does that mean the user can access the admin endpoint?

**Answer:** No. It only proves the password matches the stored hash. Account status, authentication mechanism, MFA, and authorization (roles/permissions) are separate checks.

**Question 9.** A hash has prefix `{bcrypt}` but you call `new BCryptPasswordEncoder().matches(raw, prefixedHash)` directly. Why might it fail?

**Answer:** The direct bcrypt encoder expects a bcrypt format starting with `$2a$`/`$2b$`/`$2y$`; `{bcrypt}` is a `DelegatingPasswordEncoder` prefix. Use an encoder matching the stored format or a valid migration.

## 14. Spring Security Adoption Checklist

- [ ] Passwords are never stored in plaintext or reversibly encrypted for decryption at login.
- [ ] Use an adaptive `PasswordEncoder`, preferring actively maintained algorithms matching the threat model.
- [ ] Salt is generated via CSPRNG per hash; never set fixed salts manually.
- [ ] Store the full hash including format, salt, and cost metadata so `matches` works.
- [ ] Cost is benchmarked in a production-like environment measuring p95/p99 and concurrent authentication.
- [ ] Password policy handles length/Unicode consistently, especially bcrypt's 72-byte limit.
- [ ] Account creation/password change flows use `encode`; login uses `matches` rather than comparing newly encoded strings.
- [ ] If using `DelegatingPasswordEncoder`, the `{id}...` format is consistent and migrations are tested.
- [ ] Have a process to raise cost/change algorithms using `upgradeEncoding` and persist new hashes after valid login/reset.
- [ ] If pepper is used, it resides in a secret manager/HSM separate from the DB, with a rotation plan.
- [ ] Login API is protected by TLS, rate limiting, anti-spraying, MFA, and risk observability.
- [ ] Never log passwords, hashes, pepper, or sessions/tokens; restrict access to DB and backups.
- [ ] Include integration tests for right/wrong passwords, old hashes, new costs, long passwords, and concurrent requests.

**Conclusion:** salt gives each password hash record independent randomness, while work factor makes every password guess more expensive once an attacker obtains hashes. Together they **reduce the effectiveness of offline cracking**, though they do not make weak passwords completely safe and do not replace online guessing defenses. In Spring Security, use `PasswordEncoder.encode` when storing, `matches` when verifying, tune cost for real systems, and upgrade hashes along a verified migration path.

## References

- [Spring Security 6.5 — Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security 6.5 — Crypto Module / Password Encoding](https://docs.spring.io/spring-security/reference/6.5/features/integrations/cryptography.html)
- [Spring Security — BCryptPasswordEncoder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/bcrypt/BCryptPasswordEncoder.html)
- [Spring Security — PasswordEncoder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/PasswordEncoder.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 6.5 — UserDetailsPasswordService API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetailsPasswordService.html)
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)

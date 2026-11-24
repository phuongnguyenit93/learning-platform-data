# Salt, Computational Cost, and Resistance to Password Cracking

**Salt** and **computational cost (work factor/cost)** are two complementary mechanisms that protect user passwords when a database containing password hashes is leaked. A salt ensures the same password does not naturally produce the same stored value; a work factor forces every **guess** at a password to pay a substantial computational price. Neither replaces strong, hard-to-guess passwords, access controls, TLS, MFA, or rate limiting.

In Spring Security, developers typically encounter these mechanisms through `PasswordEncoder`: calling `encode(rawPassword)` when creating or changing a password to store an encoded hash, and `matches(rawPassword, storedHash)` to authenticate at login. Suitable password encoders such as bcrypt automatically manage the salt, hash format, and cost parameter; applications should not manually invent `password + salt` string concatenation.

This lesson focuses on **“Salt, Computational Cost, and Resistance to Password Cracking”** under the *Passwords* topic, using Java 17+ and Spring Security 6.x/Spring Boot 3 as examples. The theory and architectural decisions apply equally well to other stacks. The referenced OWASP configuration numbers are **baselines at the time of reference**—always verify current guidance and benchmark on real servers before deploying.

## 1. Threat Model: Who Are We Defending Against, and Under What Conditions?

We must distinguish **two types of password guessing** that have different constraints.

### 1.1. Online Guessing

An attacker repeatedly calls the login endpoint:

```text
Attacker
  |
  | POST /login {username, passwordCandidate}
  v
Authentication filter / provider
  |
  +-- Check account, password hash, policies
  |
  +-- Return success / failure
  |
  v
Attacker can repeat if unrestricted
```

The system can observe and throttle online requests: rate limiting, progressive backoff, credential-stuffing defenses, risk scoring, MFA, monitoring, and alerting. **Salts and work factors do not replace these limits.** In fact, setting a work factor too high can allow attackers to exhaust CPU/RAM by flooding concurrent login requests.

### 1.2. Offline Cracking

An attacker has already obtained a copy of the database or a backup containing password hashes; they no longer need to send each candidate to the server:

```text
Leaked database:
   user_id | password_hash + salt + cost
       |
       v
Attacker downloads data to their own infrastructure
       |
       +-- Pick a candidate password
       +-- Compute password KDF with matching salt/cost
       +-- Compare with stored hash
       +-- Try another candidate or use GPUs/specialized hardware
```

Here, HTTP rate limiting, CAPTCHAs, and account lockouts **cannot limit the number of attempts** on the attacker's own machines. Essential defenses include: unpredictable passwords, a dedicated password KDF, a proper salt, an appropriate cost parameter, and database protection. A pepper stored outside the DB can add another defense layer, but it does not replace the fundamentals above.

**Key takeaway:** Salt primarily reduces the advantage of **precomputation and reusing work** across accounts; cost primarily increases the resources needed for **each individual attempt**. They address two distinct aspects of the same threat model.

## 2. What Is a Salt and What Problem Does It Solve?

A salt is random data freshly generated **for each individual password hash**, typically stored right alongside the hash for verification. It is not a password and **does not need to be kept secret**.

An abstract model:

```text
stored = KDF(password, randomSalt, parameters)
```

At login, the application extracts the stored salt and parameters and verifies the candidate against them. With bcrypt, Argon2id, and suitable encoders, reading and applying the salt is handled by the library via the encoded password format.

### 2.1. Same Password, Different Salts

Suppose Alice and Bob both choose the password `blue-mountain`:

```text
Alice: KDF("blue-mountain", salt_A, cost) -> hash_A
Bob:   KDF("blue-mountain", salt_B, cost) -> hash_B

salt_A != salt_B
=> hash_A and hash_B differ with overwhelming probability
```

Without a salt, an attacker seeing two identical password hashes can infer they share the same raw password. With per-hash salts, that cannot be spotted merely by comparing hash strings. Users who share a weak password **are still at risk** if an attacker tries that candidate against each hash individually.

A salt does not give user A a new password. The raw password remains the same secret known by the user; the salt only makes its stored representation differ.

### 2.2. Salt Makes Rainbow Tables Ineffective

A precomputed table can map common passwords to hash outputs when the algorithm **has no salt**:

```text
"123456"     -> hash_1
"password"   -> hash_2
"welcome"    -> hash_3
...
```

When each hash uses a random salt, a table computed for one salt cannot be reused directly for another salt. An attacker must compute against each specific salt, rendering large-scale precomputation far less useful.

**However:** an attacker can still **compute candidates using the target account's public salt**. Salt does not completely prevent dictionary attacks; it only prevents reusing precomputed work. That is why a strong work factor is also needed.

### 2.3. Salt Length and Generation

Example of a 16-byte (128-bit) salt generated with `SecureRandom` in Java:

```java
SecureRandom random = new SecureRandom();
byte[] salt = new byte[16];
random.nextBytes(salt);
```

This snippet requires importing `java.security.SecureRandom` and is not a complete program. A 16-byte salt is a common practical size suitable for examples; exact policy depends on the KDF/standard in use.

With sufficient entropy, the probability of two random salts colliding for typical user counts is exceedingly small, **though not strictly zero**. Applications must use a CSPRNG—never plain `Random`, timestamps, predictable counters, or a fixed string. Let a trusted password encoder generate the salt whenever the API supports it.

### 2.4. Does Salt Need to Live in an Environment Variable?

No. A salt is not a secret. You must store it to verify passwords later; many hash formats embed the salt directly in the string. What truly needs protection are raw passwords, password hashes (to prevent offline guessing), and any pepper/secret keys.

Never hide a single salt in server config and reuse it for everyone. That forfeits the benefit of **one unique salt per password**.

### 2.5. Is a New Salt Needed Every Time a Password Changes?

**Yes.** When a user sets a new password or the system rehashes to upgrade an algorithm/cost, the encoder normally generates a fresh salt. Never carry over an old salt just to make outputs reproducible. When verifying an **already stored** password, you must use the **stored** salt—never generate a new salt during comparison.

| Event | Salt/Hash |
| --- | --- |
| User registration | Generate new salt; hash password |
| Login with current password | Read salt/cost from stored hash; run `matches` |
| Password change | Hash new password with a new salt |
| Rehash due to work-factor change | After verifying, rehash raw password with new config and new salt |
| Forgot password | Use a legitimate password reset flow; there is no hash decryption step |

## 3. What Is a Work Factor?

A work factor (or cost/effort) is a parameter tuning the resources required to generate or verify a password hash. A good password-protection algorithm **intentionally consumes resources** so that testing millions of candidates becomes expensive.

For example:

- With **bcrypt**, cost `c` scales the work roughly as `2^c`. Increasing cost from 10 to 12 increases the cost-controlled portion of work by roughly **4x**, though total wall-clock time is not guaranteed to scale by exactly 4x on every machine.
- With **PBKDF2**, the main parameter is HMAC iteration count; raising rounds from 300,000 to 600,000 roughly doubles the iteration loop work, excluding other overhead.
- With **scrypt** and **Argon2id**, cost is not CPU alone: the RAM required per attempt is also critical.

A work factor does not “encrypt” the password, lengthen it, or change user privileges. It affects the **cost per guess**, whereas password entropy/length/unpredictability affects the **number of candidates** an attacker may have to try.

### 3.1. Why Not Use Single-Pass SHA-256?

SHA-256, SHA-512, and general-purpose cryptographic digests are optimized to run **fast**. They are great for integrity verification and other designs, but unsuitable as a **direct password storage format**.

```text
Do not use: stored = SHA256(password)
Still insufficient: stored = SHA256(salt || password)

Use: stored = PasswordKDF(password, randomSalt, tunedCost)
```

Adding a salt to a fast hash is better than no salt against precomputation, but **it does not make each guess slow**. Choose a dedicated password hashing algorithm instead of arbitrarily chaining `SHA256` calls as a homegrown substitute for bcrypt/Argon2id.

### 3.2. CPU Cost and Memory-Hardness

GPUs and ASICs can compute enormous numbers of fast hashes in parallel. A CPU-only KDF can still be accelerated significantly by parallel hardware. **Memory-hard KDFs** like Argon2id or scrypt additionally force each attempt to consume substantial RAM, raising hardware scaling costs for attackers.

However, memory-hard KDFs also consume memory on **your server**. If each request allocates tens of MiB and many logins arrive concurrently, you must plan capacity and prevent attackers from abusing this for DoS.

### 3.3. Parameters Differ Across Algorithms

| KDF | Primary Parameters | What to Understand Accurately |
| --- | --- | --- |
| bcrypt | Cost/strength (e.g., 10, 12) | Work roughly doubles per +1 cost; has 72-byte input caveat |
| PBKDF2-HMAC-SHA256 | Iteration count, salt, derived-key length | More rounds slow verification; not memory-hard like Argon2id |
| Argon2id | Memory `m`, passes `t`, parallelism `p` | `m` is **total memory** for one calculation; `p` does not multiply memory by `p` |
| scrypt | `N`, `r`, `p` | Computation and memory depend on the parameter combination; do not call them all “iterations” |

You cannot compare “bcrypt cost 12” with “Argon2id iterations 2” by comparing the numbers 12 and 2. These are different algorithmic definitions; choosing between them requires evaluating resource cost and attack resistance against your real threat model.

## 4. OWASP Configuration Guidelines and How to Use Them Properly

According to the *OWASP Password Storage Cheat Sheet* referenced for this lesson, notable **reference baselines** include:

| Algorithm / Case | OWASP Recommendation at Time of Reference | Notes |
| --- | --- | --- |
| Argon2id | `m=19 MiB, t=2, p=1` is one of the equivalent minimum configs | Balances CPU/RAM; OWASP also lists equivalent m/t pairs |
| scrypt when Argon2id is unavailable | `N=2^17, r=8, p=1` | Substantial memory footprint; assess capacity |
| bcrypt for legacy systems | Work factor at least `10` | Many implementations process only the first 72 input bytes |
| PBKDF2-HMAC-SHA256 when FIPS/compatibility is required | Around `600,000` iterations or higher per guidance | Uses HMAC-SHA256, salt, and parameter storage format |

Source: [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).

**Do not confuse minimum baselines with “the optimal numbers for every application.”** Recommendations evolve over time and across deployment profiles; check the latest documentation before going to production. For new applications, OWASP prefers Argon2id when properly supported; Spring Security also offers BCryptPasswordEncoder, which remains widespread and convenient for learning and supporting existing bcrypt systems.

### 4.1. Argon2id: Understanding m, t, and p

Example `m=19 MiB, t=2, p=1`:

- `m`: total RAM required by one evaluation per the algorithm definition; `19 MiB = 19 × 1024 KiB`.
- `t`: number of passes over the memory blocks/working set.
- `p`: parallelism/lanes, not iteration count and does not automatically double `m`.
- The same configuration can exhibit different execution times on different hardware.

If 200 concurrent verification requests arrive and each evaluation requires roughly 19 MiB, the theoretical working-set memory alone is around `200 × 19 = 3,800 MiB`, excluding JVM/OS, object overhead, provider implementation, and everything else. That is a simple planning estimate, not a real benchmark result.

**Operational rule:** bound concurrency and measure peak memory. Never lower the cost to a weak level just because the server is overloaded; combine capacity planning with rate limiting, queueing, account handling, and authentication policies.

### 4.2. bcrypt: Understanding the Cost Exponent

A bcrypt hash may begin like this:

```text
$2a$12$...(encoded salt and hash portion)
    ^^
    cost 12
```

This is a format illustration; real generated strings contain 53 additional characters after the prefix and never store plaintext passwords there. An encoded bcrypt string typically packs version, cost, salt, and result in one string.

Moving from cost `10` to `12`: the `2^cost` workload factor increases by `2^(12-10) = 4` times. **Do not assume** every login request slows down by exactly 4x, because of surrounding overhead, CPU throttling, load, provider details, VM warmup, and other checks.

**72-byte caveat:** many bcrypt implementations consider at most 72 **bytes** of the raw password. Java's `String.length()` counts UTF-16 code units, not UTF-8 bytes. Check your encoder documentation, long-password policy, and Unicode handling. Never silently truncate raw passwords or blindly pre-hash with SHA-256 before bcrypt without understanding risks such as password shucking.

### 4.3. PBKDF2: Understanding Iterations

PBKDF2 uses a PRF such as HMAC-SHA256 and an iteration count. Given the same password, salt, iterations, and derived-key length, the output is deterministic; changing the salt or parameters normally changes the output.

```text
PBKDF2(
    rawPassword,
    storedSalt,
    iterations=600000,
    outputBits=256
)
```

`600,000` is a sensible reference for examples, **not a magic formula**. Production deployments must store iterations and algorithm ID alongside the hash, manage migrations, and benchmark. Never set `iterations=1000` just to make logins fast while assuming a salt alone suffices.

## 5. Estimating Attack Cost: Understanding an Estimation Model

A simple model highlights two variables:

```text
Guessing time ≈ Number of candidates / Effective guessing rate
```

Hypothetical example **for mathematical illustration only**, not a prediction of real GPUs or production systems:

| Passwords to Test | Assumed Rate | Assumed Time |
| ---: | ---: | ---: |
| 1,000,000 | 10,000 guesses/s | 100 seconds |
| 1,000,000 | 1,000 guesses/s | 1,000 seconds |
| 1,000,000 | 100 guesses/s | 10,000 seconds |
| 100,000,000 | 100 guesses/s | 1,000,000 seconds |

If a higher cost reduces the guessing rate, the time required for the **same** number of candidates increases in this model. However, guesses/s is **not constant**: it varies across Argon2id, bcrypt, PBKDF2, specific cost settings, GPUs/FPGAs, CPUs, device counts, batching strategies, and attacker budgets.

Other reasons a simple formula does not yield exact predictions:

- Attackers usually prioritize common passwords first rather than searching candidates uniformly;
- They do not need to exhaust the full space if the password appears in a common wordlist;
- Distinct salts prevent reusing one computation across hashes, yet attackers can still parallelize across targets;
- A pepper kept outside the DB can deprive an attacker of data needed for offline verification;
- Different encryption layers/storage setups and secret-leak incidents yield different threat models.

**Salt does not increase the entropy of a user-chosen password.** A password like `123456` remains predictable. Slow hashing makes each attempt more expensive, but it does not make a weak password unguessable.

## 6. What Is a Pepper? Do Not Confuse It with a Salt

A **pepper** is an extra secret managed on the server side, typically kept outside the database storing password hashes. It can raise the barrier if an attacker dumps only the DB without compromising the secret store.

| Property | Salt | Pepper |
| --- | --- | --- |
| Is it a secret? | No | **Yes** |
| Usually unique per password? | Yes | Usually shared within a scope |
| Stored next to the hash? | Yes | Should not be |
| Needed during verification? | Yes, read from the stored hash | Yes, if the system uses a pepper |
| Primary protection | Prevents reusing precomputation, differentiates hashes | Adds defense when the DB leaks while the secret stays safe |
| When changed | Newly generated upon rehashing | Requires a rotation, migration/reset plan |

A pepper does not replace a salt and work factor. Do not invent `SHA256(pepper + password)` and consider it a safe password KDF. If using a pepper, choose a vetted scheme, manage the secret via KMS/HSM/vault, and plan ahead for how to rotate it across millions of hashes when the system does not know users' raw passwords.

### 6.1. Salts and Peppers Are Not IVs/Nonces

IVs/nonces serve symmetric encryption like AES-GCM; you must never reuse a nonce under the same key. A password KDF salt has its own requirements, while a pepper is a secret. Never take one constant from a config file and treat it as all three concepts.

## 7. Spring Security: Avoid Manual Salt Handling When Using PasswordEncoder

Core API:

```java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);
    boolean matches(CharSequence rawPassword, String encodedPassword);
    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
```

This is a simplified form illustrating the interface. The package is `org.springframework.security.crypto.password.PasswordEncoder`. There is no `decrypt` because a password hash **is not ciphertext to be decrypted**.

### 7.1. Encode Once When Storing, Call matches on Login

```java
PasswordEncoder encoder = new BCryptPasswordEncoder(12);

String stored = encoder.encode("training-password");

boolean yes = encoder.matches("training-password", stored);
boolean no  = encoder.matches("wrong-password", stored);
```

`yes` is true and `no` is false. `encode` generates a random salt and formats the hash with its cost. Do not store the salt in a separate field unless your algorithm/storage design genuinely requires it; many encoders already embed the salt in the encoded password.

**Very common mistake:**

```java
// WRONG with algorithms that generate a random salt:
encoder.encode(raw).equals(storedHash);

// RIGHT:
encoder.matches(raw, storedHash);
```

Two `encode` calls with the same raw input typically produce two different hashes. `matches` reads the proper salt/cost from the stored hash to verify the candidate.

### 7.2. Where Does Spring Security Check the Password?

In a standard username/password flow:

```text
Login form or HTTP Basic
       |
       v
AuthenticationFilter creates UsernamePasswordAuthenticationToken
       |
       v
AuthenticationManager / ProviderManager
       |
       v
DaoAuthenticationProvider
       |
       +-- UserDetailsService.loadUserByUsername(username)
       |       -> username, stored password hash, authorities, flags
       |
       +-- PasswordEncoder.matches(raw, storedHash)
       +-- Account status checks per provider
       |
       v
Authentication succeeds or AuthenticationException
       |
       v
SecurityContext and Authorization
```

`UserDetailsService` **does not verify raw passwords itself**; it looks up and returns a `UserDetails` containing the hash. `PasswordEncoder` performs the match. The provider evaluates credentials and account state. Controllers do not decrypt passwords for login.

Once a user is logged in, you should not force them to send their password on **every API request** just to re-verify; as Spring Security documentation notes, password KDFs are intentionally resource-intensive. Properly managed short-lived sessions/tokens fit many architectures better, while sensitive actions can require policy-driven re-authentication.

### 7.3. BCryptPasswordEncoder Strength and Format

Configuration:

```java
@Bean
PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder(12);
}
```

A newly created hash typically starts with `$2a$12$` when using the constructor/config shown; the version prefix may vary by implementation. The salt and cost are embedded in the string. Never hardcode an entire hash as expected output: random salts make every encode result vary.

`BCryptPasswordEncoder` can verify a bcrypt hash stored with a lower cost without knowing that cost ahead of time in code, because the cost is encoded inside the hash itself. To upgrade cost, use `upgradeEncoding` when needed together with a proper storage update flow.

### 7.4. DelegatingPasswordEncoder for Migration

Spring Security provides a factory:

```java
PasswordEncoder encoder =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();

String encoded = encoder.encode("training-password");
boolean valid = encoder.matches("training-password", encoded);
```

In the default Spring Security 6.5 configuration illustrated here, `encoded` usually has the `{bcrypt}` prefix. Format:

```text
{id}encodedPassword

{bcrypt}$2a$10$...
{pbkdf2}...
{scrypt}...
```

`id` selects the algorithm delegate, **not a secret**. If the DB stores old bcrypt hashes **without** `{bcrypt}` and the application switches to a delegating encoder without an appropriate default mapping, you may see `There is no PasswordEncoder mapped for the id "null"`. Identify the hash format and plan a migration; do not apply a quick fix using `NoOpPasswordEncoder`.

### 7.5. Argon2id in Spring Security: Watch Dependencies

Spring Security provides `Argon2PasswordEncoder`. An **illustrative** configuration for an environment that already has Argon2 support and its required dependencies:

```java
PasswordEncoder argon2 = new Argon2PasswordEncoder(
    16,        // saltLength bytes
    32,        // hashLength bytes
    1,         // parallelism
    19 * 1024, // memory KiB = 19 MiB
    2          // iterations
);
```

This is a snippet requiring `org.springframework.security.crypto.argon2.Argon2PasswordEncoder` and an appropriate Spring Security version. In common Spring Security 6.x releases, the Argon2 implementation requires **Bouncy Castle** at runtime; inspect your project dependencies rather than assuming JDK 17 alone is enough. For real applications, check **Javadoc, OWASP, and benchmarks** before applying, and bound concurrent authentications to protect RAM. Do not switch the encoder bean to Argon2 carelessly and break verification of existing bcrypt hashes: you need `DelegatingPasswordEncoder` and a migration strategy.

## 8. Standalone Java 17: Observing Per-Hash Salts and PBKDF2 Cost

This code **compiles on plain JDK 17** without Spring Security. It uses `PBKDF2WithHmacSHA256`, `SecureRandom`, and `MessageDigest.isEqual` to illustrate:

1. Two distinct random salts for the same password.
2. A stored hash carrying its salt and iteration count.
3. A valid candidate being accepted using the **stored salt**.
4. A wrong password being rejected.
5. No password decryption operation.
6. The work factor stored as metadata so future versions still know how to verify and rehash.

This is a **mechanism exercise**, not a production replacement for `PasswordEncoder`; production still needs storage formatting, input normalization policies, rate limiting, concurrency bounds, algorithm migration, secret protection, error handling, auditing, and benchmarks.

### 8.1. Complete File: SaltAndCostDemo.java

```java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;

import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public class SaltAndCostDemo {

    private static final int SALT_BYTES = 16;
    private static final int ITERATIONS = 600_000;
    private static final int OUTPUT_BITS = 256;

    record StoredPassword(
        byte[] salt,
        int iterations,
        byte[] hash
    ) {}

    static byte[] derive(
            char[] rawPassword,
            byte[] salt,
            int iterations
    ) throws GeneralSecurityException {

        PBEKeySpec spec = new PBEKeySpec(
            rawPassword, salt, iterations, OUTPUT_BITS
        );

        try {
            return SecretKeyFactory
                .getInstance("PBKDF2WithHmacSHA256")
                .generateSecret(spec)
                .getEncoded();
        } finally {
            spec.clearPassword();
        }
    }

    static StoredPassword create(
            char[] password,
            SecureRandom random
    ) throws GeneralSecurityException {

        byte[] salt = new byte[SALT_BYTES];
        random.nextBytes(salt);

        return new StoredPassword(
            salt,
            ITERATIONS,
            derive(password, salt, ITERATIONS)
        );
    }

    static boolean verify(
            char[] candidate,
            StoredPassword stored
    ) throws GeneralSecurityException {

        byte[] computed = derive(
            candidate,
            stored.salt(),
            stored.iterations()
        );

        try {
            return MessageDigest.isEqual(
                computed,
                stored.hash()
            );
        } finally {
            Arrays.fill(computed, (byte) 0);
        }
    }

    public static void main(String[] args)
            throws GeneralSecurityException {

        SecureRandom random = new SecureRandom();
        char[] raw = "training-password-17".toCharArray();
        char[] wrong = "incorrect-password".toCharArray();

        try {
            StoredPassword alice = create(raw, random);
            StoredPassword bob = create(raw, random);

            System.out.println(
                "salt.bytes=" + alice.salt().length
            );
            System.out.println(
                "cost.iterations=" + alice.iterations()
            );
            System.out.println(
                "hash.bytes=" + alice.hash().length
            );
            System.out.println(
                "alice.verify.correct=" + verify(raw, alice)
            );
            System.out.println(
                "alice.verify.wrong=" + verify(wrong, alice)
            );
            System.out.println(
                "bob.verify.correct=" + verify(raw, bob)
            );
            System.out.println(
                "sameSalt=" + Arrays.equals(
                    alice.salt(), bob.salt()
                )
            );
            System.out.println(
                "sameHash=" + Arrays.equals(
                    alice.hash(), bob.hash()
                )
            );
        } finally {
            Arrays.fill(raw, '\0');
            Arrays.fill(wrong, '\0');
        }
    }
}
```

Run:

```bash
javac SaltAndCostDemo.java
java SaltAndCostDemo
```

**Expected practical output** (`sameSalt`/`sameHash` rely on randomness, so an exception has a minuscule but non-zero probability):

```text
salt.bytes=16
cost.iterations=600000
hash.bytes=32
alice.verify.correct=true
alice.verify.wrong=false
bob.verify.correct=true
sameSalt=false
sameHash=false
```

No raw passwords, actual salts/hashes, or execution timings are printed because random values and runtime durations vary. These are **expectations derived from the code logic**, not a claim of running the JDK while authoring this lesson.

### 8.2. Explaining Why the Output Looks Like This

- `SALT_BYTES=16` corresponds to a 128-bit salt. Each `create` call invokes `SecureRandom.nextBytes` for a fresh salt.
- `ITERATIONS=600_000` is the cost parameter stored alongside the salt/hash in the record. During verification, the code reads `stored.iterations()`; if the application upgrades cost later, older hashes still retain their original parameter.
- `OUTPUT_BITS=256` makes the derived value 32 bytes long.
- `verify(raw, alice)` re-runs the KDF with the right password and **Alice's salt**, so it matches.
- `verify(wrong, alice)` produces a different value with overwhelming probability; a wrong candidate password is rejected.
- Alice and Bob share the same raw password, yet their salts are generated independently, so their stored hashes differ with overwhelming probability.
- `MessageDigest.isEqual` is used to compare byte arrays for verification instead of comparing newly encoded strings.
- `PBEKeySpec.clearPassword()` and `Arrays.fill` help limit the lifetime of password and derived bytes, though literal demo strings still exist in the class; **never hardcode production secrets**.
- `StoredPassword` in this demo holds mutable `byte[]` references without defensive copying; production requires stricter object/storage design and secret lifecycle management. Do not use this record directly for a real database.

**Important:** Never alter `create` to reuse another user's salt for easier debugging. Seeing different actual hashes/salts across runs is the intended behavior.

### 8.3. Evaluate Cost by Measuring, Not Guessing

Never hardcode a claim like “600,000 iterations takes 100 ms.” Speed depends on CPU, JDK provider, VM warmup, thread contention, and load. When measuring:

1. Benchmark on hardware matching production specs;
2. Warm up the JVM and collect enough samples, examining p50/p95/p99 rather than a single run;
3. Isolate password KDF time from JDBC/network/HTTP;
4. Measure CPU and peak RAM under realistic concurrency;
5. Test scenarios with wrong passwords and nonexistent users;
6. Balance response latency against DoS/rate-limit risk;
7. Document algorithm version/cost and review periodic increases;
8. Use a microbenchmark framework like JMH when reliable numbers are needed.

You can write performance tests outside load-sensitive CI, but **never** put fixed timing assertions like `assertTrue(duration < 100ms)` in unit tests running across arbitrary machines: they are chronically flaky.

## 9. Spring Boot 3: Using BCryptPasswordEncoder with Salt and Cost

The following example illustrates Spring Security password hashing instead of manually managing salts and loops via JCA. We use **bcrypt cost 12** as a learning and testing baseline; this is **not a claim that bcrypt is best for every new system** or that cost 12 fits every risk profile.

Project structure:

```text
src/main/java/example/passwordcost/
    PasswordCostApplication.java
    SecurityConfig.java
    DemoController.java

src/test/java/example/passwordcost/
    PasswordCostTest.java
```

### 9.1. Dependencies

In a Spring Boot 3 project already configured with the plugin and a Java 17 toolchain, the `dependencies` block of Groovy `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

This is not a complete build file. With Maven, add the two corresponding starters and `spring-security-test` in test scope. Let the Spring Boot BOM manage compatible Spring Security versions; if upgrading to another framework generation, verify syntax and re-run build/tests.

### 9.2. PasswordCostApplication.java

```java
package example.passwordcost;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PasswordCostApplication {

    public static void main(String[] args) {
        SpringApplication.run(PasswordCostApplication.class, args);
    }
}
```

### 9.3. SecurityConfig.java

```java
package example.passwordcost;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(12);
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-demo-password"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-demo-password"))
            .roles("USER", "ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Here:

1. `new BCryptPasswordEncoder(12)` creates an encoder using bcrypt cost 12, including a random salt generated inside `encode`.
2. When creating in-memory **demo users**, `encoder.encode(...)` produces the stored hashes. Real applications do this at registration/password change without hardcoding passwords in source.
3. `UserDetailsService` loads the hash and authorities. `DaoAuthenticationProvider` in the username/password flow uses `PasswordEncoder.matches` to verify.
4. `HttpSecurity.httpBasic(...)` accepts credentials from the Basic header. HTTP Basic uses only Base64 and does not encrypt traffic; production must use TLS/HTTPS.
5. `authorizeHttpRequests` enforces authorization after authentication. Having the right password does not imply admin privileges.
6. `anyRequest().denyAll()` rejects undeclared routes.
7. The demo exposes only GET endpoints so CSRF is left active; if adding state-changing POST endpoints with cookies/sessions, evaluate CSRF tokens per your threat model.

When using `BCryptPasswordEncoder` directly, hashes typically begin with `$2a$12$...` and do **not** include the `{bcrypt}` prefix of the delegating format. When migrating to `DelegatingPasswordEncoder`, handle legacy hash formats properly; merely swapping the bean does not automatically rewrite stored hashes.

### 9.4. DemoController.java

```java
package example.passwordcost;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    Map<String, String> publicInfo() {
        return Map.of("message", "public");
    }

    @GetMapping("/api/me")
    Map<String, String> currentUser(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @GetMapping("/api/admin")
    Map<String, String> adminOnly() {
        return Map.of("message", "admin");
    }
}
```

The controller receives an `Authentication` already verified by the provider, never reads a password hash from the request, and never encrypts/decrypts passwords itself. Never return `UserDetails.getPassword()` in a response.

### 9.5. Running and Calling the API

macOS/Linux:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Assuming the demo server runs at `http://localhost:8080`:

```bash
# Anonymous public: 200
curl -i http://localhost:8080/public

# Anonymous private: 401
curl -i http://localhost:8080/api/me

# Reader right password: 200
curl -i -u reader:reader-demo-password \
  http://localhost:8080/api/me

# Reader wrong password: 401
curl -i -u reader:incorrect \
  http://localhost:8080/api/me

# Reader logged in but lacks ROLE_ADMIN: 403
curl -i -u reader:reader-demo-password \
  http://localhost:8080/api/admin

# Admin logged in and has ROLE_ADMIN: 200
curl -i -u admin:admin-demo-password \
  http://localhost:8080/api/admin
```

These HTTP status codes are **expected per configuration**. There is no claim that a server/Gradle run was executed here. Demo passwords are for localhost only; `curl -u` can expose passwords in shell history and process lists. Real applications must use HTTPS and manage secrets safely.

## 10. JUnit/MockMvc: Verifying Salt, Cost, and Authentication

Create `src/test/java/example/passwordcost/PasswordCostTest.java`:

```java
package example.passwordcost;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PasswordCostTest {

    @Autowired
    PasswordEncoder encoder;

    @Autowired
    UserDetailsService users;

    @Autowired
    MockMvc mvc;

    @Test
    void costIsStoredInBcryptHash() {
        String hash = encoder.encode("demo-candidate");

        assertThat(hash).startsWith("$2");
        assertThat(hash.substring(4, 6)).isEqualTo("12");
        assertThat(hash).hasSize(60);
    }

    @Test
    void rightAndWrongCandidatesAreDistinct() {
        String hash = encoder.encode("demo-candidate");

        assertThat(encoder.matches("demo-candidate", hash)).isTrue();
        assertThat(encoder.matches("wrong-candidate", hash)).isFalse();
    }

    @Test
    void randomSaltMakesNewHashesUsuallyDifferent() {
        String first = encoder.encode("same-password");
        String second = encoder.encode("same-password");

        assertThat(first).isNotEqualTo(second);
        assertThat(encoder.matches("same-password", first)).isTrue();
        assertThat(encoder.matches("same-password", second)).isTrue();
    }

    @Test
    void strongerEncoderCanIdentifyLowerCostHash() {
        String cost12 = encoder.encode("demo-candidate");

        BCryptPasswordEncoder stronger =
            new BCryptPasswordEncoder(13);

        assertThat(stronger.matches("demo-candidate", cost12))
            .isTrue();
        assertThat(stronger.upgradeEncoding(cost12)).isTrue();
    }

    @Test
    void userStoreDoesNotContainRawPassword() {
        String stored = users.loadUserByUsername("reader")
            .getPassword();

        assertThat(stored).isNotEqualTo("reader-demo-password");
        assertThat(stored.substring(4, 6)).isEqualTo("12");
        assertThat(encoder.matches(
            "reader-demo-password", stored)).isTrue();
    }

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk());
    }

    @Test
    void privateEndpointNeedsAuthentication() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void basicCorrectPasswordAuthenticates() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic(
                    "reader", "reader-demo-password")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("reader"));
    }

    @Test
    void basicWrongPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic(
                    "reader", "incorrect")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void correctPasswordDoesNotGrantAdminRole()
            throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic(
                    "reader", "reader-demo-password")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/admin")
                .with(httpBasic(
                    "admin", "admin-demo-password")))
            .andExpect(status().isOk());
    }
}
```

Run:

```bash
./gradlew test --tests example.passwordcost.PasswordCostTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.passwordcost.PasswordCostTest
```

**Expectation:** 10 test methods pass in the described Spring Boot 3/Spring Security 6.x project with appropriate dependencies. This is an expectation from the code, **not an actual test run record**. Testing that two salts/hashes differ relies on cryptographic randomness, so there is an infinitesimally small collision probability rather than an absolute mathematical certainty.

| Test Group | What Is Verified |
| --- | --- |
| bcrypt format | Cost 12 and metadata in encoded hash |
| `matches` | Valid/invalid passwords against the same stored hash |
| Two encode calls | Random salt usually makes encoded hashes differ |
| `upgradeEncoding` | Recognizes a hash below a newly configured cost |
| User store | Plaintext is not stored; password matches via encoder |
| HTTP Basic | Filter/provider accepts or rejects credentials |
| Admin role | A valid password still requires authorization |

No unit test **proves absolutely** that “a hash cannot be cracked.” These are functional and configuration tests, not strength evaluations against an attacker with GPU infrastructure. You must still review algorithms, parameters, benchmarks, threat models, and operational policies.

### 10.1. Do Not Use @WithMockUser to Test Passwords

`@WithMockUser` creates a fake Authentication in tests to exercise authorization. It bypasses the password provider, so tests can stay green even when `PasswordEncoder` or database hashes are misconfigured. To test passwords, use `httpBasic(...)`, form login tests, or call `AuthenticationManager.authenticate(...)` through the real provider.

### 10.2. Do Not Write Unit Tests Based on Absolute Wall-Clock Time

Avoid:

```java
// Flaky: latency depends on CPU, JIT, load, and CI environment.
assertThat(elapsedMilliseconds).isLessThan(100);
```

Run separate benchmarks and measure p95/p99 per environment; functional tests only need to verify proper hash format, expected cost, true/false matches, and upgrade paths.

## 11. Raising Work Factors Over Time Without Locking Out Users

Most applications keep password hashes for years, during which configurations once deemed strong enough can weaken as hardware advances.

A standard migration strategy:

1. Store **algorithm ID, salt, cost, and hash** in a format inspectable later.
2. User logs in → verify password using the **stored parameters**, never forcing the new cost onto old hashes.
3. If the password is correct, ask the encoder/policy whether the hash needs an upgrade.
4. If needed, compute a new hash from the raw password the user **just validly entered**, generating a fresh salt and using the new cost.
5. Update the DB atomically, control concurrent logins/password changes, and never log raw passwords.
6. Consider invalidating sessions and auditing per policy.
7. For dormant accounts that never log in, consider password resets or an appropriate forced-upgrade policy.
8. Test rollback paths, legacy hash reads, and multi-format support during rolling deployments.

In Spring Security, `PasswordEncoder.upgradeEncoding(encodedPassword)` helps check whether an upgrade is needed; `UserDetailsPasswordService` can be configured so the provider updates the encoded password when the flow supports it. Simply changing the bean from `new BCryptPasswordEncoder(12)` to `new BCryptPasswordEncoder(13)` **does not automatically rewrite all existing password hashes in the database**.

### 11.1. When Should You Use DelegatingPasswordEncoder?

If your database holds multiple generations of hashes such as bcrypt, PBKDF2, or Argon2, a system can store `{id}encodedPassword` and configure versioned mappings. Switching algorithms without versioning/prefixes/migration can lock out users with older hashes. Never delete or bulk-convert hashes by “guessing raw passwords”; hashes have no decrypt operation for that.

### 11.2. Data Needed for Verification

Example stored record:

```text
user_id = u-100
algorithm = bcrypt
cost = 12
salt = (encoded inside the bcrypt hash)
storedHash = $2a$12$...
```

With bcrypt, the encoded string itself already contains version, cost, salt, and result. Separate columns are unnecessary if the library uses a self-describing format. With custom PBKDF2, store algorithm, iteration count, salt, and output length/version explicitly to verify hashes across generations.

### 11.3. A New Hash Does Not Need to Match the Old Hash

When raising the cost, the new encoded hash normally differs even when the raw password has not changed because of the **new salt**. Never compare the new hash string against the old hash string to conclude the password changed or the user typed the wrong password. Correctness relies on `matches`.

## 12. Practical Limits: Defense in Depth

A system with strong password hashes can still suffer account takeover via phishing, credential reuse, malware, compromised password-reset email, session hijacking, or broken authorization.

### 12.1. Defending Against Online Guessing

- Rate limit on reliable signals (user/account, IP, device risk) without creating abusable lockout mechanisms;
- Appropriate MFA/passkeys and step-up verification on high risk;
- Block common/breached passwords per policy;
- Log security events carefully without logging passwords, hashes, or tokens;
- Use error messages that avoid disclosing whether a user exists;
- TLS, proper session cookie flags, and CSRF protection when using cookies/sessions;
- Account for DoS potential when cost is high and adversaries send concurrent login floods.

### 12.2. Defending Against Offline Cracking

- Choose Argon2id/scrypt/bcrypt/PBKDF2 appropriately; **never** store single-pass MD5/SHA-1/SHA-256;
- Unique random salt per password;
- Cost high enough, benchmarked, and raised over time;
- Restrict read permissions on `password_hash`, backups, and logs;
- External pepper when threat model and operational cost justify it;
- Sensible password policies and breached-password checks;
- DB leak incident response: assess scope, reset passwords if warranted, revoke sessions, and notify per obligations.

### 12.3. Defending Against Broken Authorization

A valid password only establishes **authentication**; afterwards the application must still check roles, permissions, and resource ownership/tenant. Even if a user holds `report:read`, that does not mean they may read another tenant's reports. Never let strong hashing excuse skipping per-record authorization.

## 13. Anti-Patterns to Recognize

### 13.1. Using One Shared Salt Across All Accounts

`private static final String SALT = "my-app-salt";` is improper. A shared salt lets attackers reuse computations across accounts and spot identical passwords.

### 13.2. Storing SHA-256(password) Instead of bcrypt/Argon2id

Even a unique salt does not make single-pass SHA-256 slow enough. Use a purpose-built, up-to-date password KDF.

### 13.3. Using Low bcrypt Strength Without Benchmarking

Too low a cost makes offline guessing cheap; too high a cost slows logins and invites DoS. Choose based on hardware, traffic, and threat model.

### 13.4. Assuming “One-Way Hash Means Nobody Can Find the Password”

Attackers can test candidates offline. Weak passwords remain far easier to guess than strong passwords.

### 13.5. Manually Appending Salt When the Encoder Already Handles It

`encoder.encode(password + salt)` when the encoder already salts complicates formatting and breaks verification if the extra salt is not stored and restored consistently. Use the encoder API properly.

### 13.6. Generating a Fresh Salt on Every Login to Compare Against the Stored Hash

Generating a different salt at verification time causes the KDF output to mismatch. `matches` must use the salt and cost from the stored record.

### 13.7. Re-Hashing with encode and Comparing Strings

Bcrypt generates a random salt, so two encode calls usually differ. Use `PasswordEncoder.matches`.

### 13.8. Hardcoding Raw Passwords or Peppers in Source Control

Secrets must not be committed to repositories. Peppers belong in a secret manager with a rotation plan. Hardcoded passwords in tutorials are strictly for local learning.

### 13.9. Logging Hashes or Authorization Headers

Leaked password hashes help attackers guess offline, and Basic headers contain plaintext recoverable via Base64. Never log secrets or hashes.

### 13.10. Assuming DB Encryption Replaces Password Hashing

Encryption at rest adds useful protection, yet if an attacker compromises application access or keys, ciphertext can be decrypted. Login passwords still require a one-way verifier.

### 13.11. Leaving Concurrent Password Checks Unbounded

Memory-hard Argon2id can consume large amounts of RAM under concurrent request spikes. Apply rate limiting, resource controls, and capacity planning.

### 13.12. Arbitrarily Pre-Hashing bcrypt with SHA-256

Bcrypt has a 72-byte input caveat; naively pre-hashing passwords with a fast hash can introduce password shucking or byte-handling bugs. If pre-hashing is unavoidable, follow OWASP guidance on HMAC with a pepper and validate the scheme—never improvise.

### 13.13. Assuming Cost Numbers Across Algorithms Are Directly Comparable

`bcrypt strength=12` is not equivalent to `Argon2id iterations=12`. Evaluate memory, passes, CPU, p95 latency, and attacker parallelizability.

### 13.14. Failing to Version Hashes When Changing Algorithms

Without metadata or algorithm IDs, verifying legacy hashes and upgrading safely becomes brittle. Use self-describing formats or `DelegatingPasswordEncoder`.

### 13.15. Raising Cost Without Considering Dormant Accounts

Old hashes may linger in the DB indefinitely without raw passwords to rehash. Define appropriate reset or migration policies.

### 13.16. Thinking Salt Increases Raw Password Guess Resistance

Salt does not change the entropy of the user's secret. It stops attackers from reusing precomputed work; for very weak passwords, attackers can still guess common candidates.

### 13.17. Making Benchmark Timeouts Universal Pass/Fail Tests

Hash timing varies by machine, load, and JIT. Use disciplined benchmarks; unit and integration tests should not depend on a fixed millisecond threshold.

### 13.18. Testing Only Valid Passwords and Forgetting Invalid/Disabled Cases

You must test authentication failure paths and account status, not only the happy path. A properly formatted hash does not prove your service actually rejects invalid passwords.

## 14. Implementation and Review Checklist

**Password storage design**

- Using a dedicated password KDF instead of single-pass SHA-256/MD5/NoOp?
- Unique random salt per hash generated by a CSPRNG/trusted library?
- Salt/algorithm/cost stored completely so future versions can verify?
- CPU/memory parameters benchmarked on real server hardware?
- No shared salts, and salts not hidden like secrets?
- Password hashes, backups, and logs protected?
- Any pepper managed outside the DB with a rotation strategy?
- Bcrypt 72-byte limit, Unicode, and password length handled per implementation?
- Migration plan ready for raising cost or changing algorithms?

**Login flow**

- `UserDetailsService` loads hash and authorities without comparing raw passwords itself?
- `DaoAuthenticationProvider` and `PasswordEncoder.matches` verify the password properly?
- Disabled/locked accounts rejected?
- Nonexistent usernames and wrong passwords do not leak excess information?
- Never comparing `encode(raw).equals(stored)`?
- Rate limiting and MFA/passkeys applied per risk?
- HTTPS used, sessions/tokens and CSRF protected per threat model?
- Concurrency limits and CPU/RAM monitoring in place against DoS?

**Quality assurance**

- Random salt test: two encoded hashes usually differ and both match properly?
- Cost test: hash format encodes the configured level?
- `upgradeEncoding` test for legacy hashes?
- Tests for valid/invalid passwords, 401 when unauthenticated, and 403 when missing roles?
- Measured p50/p95/p99 latency with production JDK/provider and hardware?
- DB leak and backup access scenarios reviewed in threat model?
- Account password reset, revocation, and auditing mechanisms in place?
- No unverified “time to crack” claims published without measurement conditions and threat model?

## 15. Self-Check Questions and Answers

**1.** Does a salt need to be secret?  
No. Salts are usually stored alongside the hash, since their main purpose is giving each password distinct input/output.

**2.** Does adding a salt make a single pass of SHA-256 slow?  
No. Adding a salt does not turn single-pass SHA-256 into slow password hashing.

**3.** Given the same password and two different salts, what is produced?  
Two different hashes with overwhelming probability under a proper KDF.

**4.** Why do random salts make rainbow tables less useful?  
Because a table precomputed for one salt cannot be reused directly for another; attackers must compute per specific salt.

**5.** What risk does a work factor primarily defend against?  
It raises the computational cost per candidate, especially against offline cracking of leaked hashes.

**6.** What does increasing bcrypt cost from 10 to 12 represent?  
The `2^cost` workload increases by roughly `4` times; wall-clock time also depends on overhead and hardware.

**7.** What are the primary parameters of Argon2id?  
`m` (memory), `t` (passes), `p` (parallelism).

**8.** Why can’t you compare Argon2id t=2 and bcrypt cost=12 just by number size?  
They measure different kinds of cost and must be evaluated via concrete parameters and benchmarks.

**9.** What inputs does `PasswordEncoder.matches` need?  
The candidate raw password and the encoded hash containing or referencing the right salt/cost/algorithm.

**10.** Why is `encoder.encode(raw).equals(stored)` usually wrong?  
A fresh encode generates a new salt, so the new hash differs from the stored hash even for the same raw password.

**11.** How does a pepper differ from a salt?  
A pepper is a secret stored outside the DB, whereas a salt is non-secret and typically unique per hash.

**12.** If an attacker already has the database and hashes, does login rate limiting stop offline guessing?  
No, because they run the KDF on their own machines without sending requests to your server.

**13.** Why can an overly high work factor increase DoS risk?  
Each login request consumes heavy CPU/RAM, letting an attacker send concurrent login floods.

**14.** Can you recover the original password by decrypting a password hash?  
There is no decrypt API. Attackers can try guessing, while legitimate users need password reset when forgotten.

**15.** When you raise bcrypt strength, do all old hashes update automatically?  
No. You need login-time rehashing/migration or a reset strategy.

**16.** If a database containing strong hashes is leaked, is every password guaranteed safe?  
No. Weak passwords can still be guessed, even though each attempt costs more.

**17.** With HTTP Basic, does password hashing protect credentials in transit?  
No. Basic uses Base64; use TLS/HTTPS and protect secrets on the client.

**18.** In performance tests, should you assert every hash finishes under 100 ms?  
There is no universal fixed threshold across machines; benchmark and evaluate latency and concurrency per environment.

## 16. References

- [OWASP – Password Storage Cheat Sheet: salting, work factor, Argon2id, bcrypt, PBKDF2](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [Spring Security 6.5 – Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security – PasswordEncoder Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/crypto/password/PasswordEncoder.html)
- [Spring Security – BCryptPasswordEncoder Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/crypto/bcrypt/BCryptPasswordEncoder.html)
- [Spring Security 6.5 – DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security – Argon2PasswordEncoder Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/crypto/argon2/Argon2PasswordEncoder.html)
- [OWASP – Authentication Cheat Sheet: preventing online password guessing](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [NIST SP 800-63B – Authentication and Protecting Memorized Secrets](https://pages.nist.gov/800-63-4/sp800-63b.html)
- [Java 17 – JCA Reference Guide: PBKDF2, SecureRandom](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html)

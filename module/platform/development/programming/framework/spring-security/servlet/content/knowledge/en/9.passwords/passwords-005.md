# Computational Cost, Input Limits, and Measuring Password Verification Time in Spring Security Servlet

## 1. Problem to Solve

Password-based login must balance three interrelated goals:

1. **Resistance to offline password guessing:** if the hash database is compromised, each password guess must consume significant resources. Never use fast general-purpose hashes like standalone SHA-256 to store passwords.
2. **Response latency and load capacity:** every call to `PasswordEncoder.matches(raw, storedHash)` consumes CPU, and some algorithms also consume substantial memory. Work slow enough to hinder attackers also costs the server resources on legitimate requests.
3. **Input limits and timing observations:** overly long passwords or a flood of login requests can cause overload. You must set deliberate limits, measure realistically in a representative environment, and avoid turning timing differences into an account-enumeration oracle.

In Spring Security Servlet, password verification in the username/password flow is typically handled by `DaoAuthenticationProvider` working with `UserDetailsService` and `PasswordEncoder`. `UserDetailsService` looks up the account and stored hash; `PasswordEncoder.matches` checks the candidate password; the provider decides whether authentication succeeds or fails. Requests using bearer tokens, OAuth2, or other providers may not pass through this password-verification step.

This lesson focuses strictly on **computational cost, input limits, and measuring password verification time**: how to pick a work factor, avoid unexpected costs, design safe limits, and measure without misleading yourself. Illustrative numbers here are **not a standard configuration for every system**.

## 2. Why use a slow password derivation function?

Human-chosen passwords typically have lower entropy than random cryptographic keys. A fast general-purpose hash lets specialized hardware test vast numbers of candidates if hashes are leaked.

Password hashing has a different goal: **raising the cost of every password guess**, typically using a unique salt and tunable cost parameters. Common algorithms:

| Algorithm | Cost parameters to watch | Characteristics |
| --- | --- | --- |
| BCrypt | `strength` / `cost` / work factor | Increasing cost by one step roughly doubles the work rounds. Has a notable input length limit. |
| PBKDF2 | Iteration count, PRF (e.g., HMAC-SHA-256), output length | Primarily CPU-bound; available in Java/JCA ecosystems; higher iterations slow down verification. |
| SCrypt | Work and memory parameters such as `N`, `r`, `p` | Intentionally memory-intensive; cost must be calculated per concurrent request. |
| Argon2id | Memory, iterations, parallelism | Intentionally memory-hard; configuration must balance RAM/CPU and deployment capacity. |

BCrypt, PBKDF2, SCrypt, and Argon2id each have a place depending on policy, dependencies, platform, and compliance requirements. **There is no single optimal cost number for all servers**; running on small containers, target login latency, security requirements, and concurrency levels must be evaluated together.

### 2.1. Salt is not a work factor

**Salt** is a per-password random value, usually generated automatically at encode time, to prevent two identical passwords from sharing identical hash outputs and to defeat precomputed hash tables. Salt does not need to be kept secret and is usually stored alongside the encoded output.

**Work factor** tunes the resource cost per hash/verify operation; salt does not replace work factor. Conversely, a high work factor does not allow omitting salt.

### 2.2. Encode on save, matches on login

Typical lifecycle:

```text
Registration / password change:
  raw password
      |
      +--> check policy limits
      +--> PasswordEncoder.encode(raw)
      +--> store encoded password + required metadata

Login:
  username + raw candidate
      |
      +--> appropriate request/input limits
      +--> look up UserDetails + encoded hash
      +--> PasswordEncoder.matches(raw, encodedHash)
      +--> continue checking account status / creating Authentication
```

Do not encode the candidate password and compare two hash strings with `equals`: with randomly salted encoders, two encodes of the same password usually yield two different strings. `matches` is the proper API for verification.

**Do not log raw passwords, hashes, tokens, or session identifiers** when debugging latency. If diagnostics are needed, record only non-sensitive configuration parameters (under control), aggregate results, and system metrics.

## 3. How does work factor affect time and resources?

### 3.1. BCrypt cost is not a fixed millisecond value

Spring Security example:

```java
PasswordEncoder encoder10 = new BCryptPasswordEncoder(10);
PasswordEncoder encoder12 = new BCryptPasswordEncoder(12);
```

This is a **configuration snippet** requiring imports for `org.springframework.security.crypto.password.PasswordEncoder` and `org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder`; they are not two standalone programs.

The numbers `10` or `12` are **work factor parameters**, not 10 ms or 12 ms. Increasing from 10 to 12 scales the work rounds exponentially (power of two), so time typically increases roughly fourfold under comparable conditions; however, do not assert an exact 4x ratio across every machine, JVM, version, load, or container environment.

The right way to evaluate is to **measure actual `matches` performance on deployment hardware**, including under load. Do not copy "BCrypt time on a laptop" as a production SLA.

### 3.2. Both encode and verify consume resources

Registration and password resets use `encode`; login uses `matches`. Both consume resources according to the cost parameters. In live operation, a login endpoint can be hit repeatedly by the same user or by bots, so **verification load** usually matters more than account-creation encode cost alone.

If high-frequency login requests occur, calculate the total slow hashes per second rather than measuring only single-request latency.

### 3.3. Increasing cost does not equal complete security

Work factor helps resist password guessing against leaked hashes, but **does not replace**:

- MFA on appropriate flows;
- HTTPS and properly protected cookies/sessions;
- rate limiting, abuse detection, and online brute-force controls;
- failed-login controls and error responses that avoid leaking account existence;
- securing hash data in databases/backups;
- controlling password resets and session management.

If you set the work factor too high without limiting verification requests, the system can suffer **denial of service** from its own slow hashing.

## 4. Password limits: distinguishing characters, code points, and UTF-8 bytes

This is easy to miss when applying `@Size` or `String.length()`.

In Java:

- `String.length()` counts **UTF-16 code units**, not always user-perceived characters.
- `String.codePointCount(0, s.length())` counts Unicode code points; an emoji/symbol can still consist of multiple code points.
- `s.getBytes(StandardCharsets.UTF_8).length` is the **UTF-8 byte count**; this length can differ significantly from the code point count.
- "User-perceived characters" as grapheme clusters are yet another concept requiring dedicated Unicode handling if a policy truly relies on that unit.

Illustrative examples:

| Password string | `length()` | Code points | UTF-8 bytes |
| --- | ---: | ---: | ---: |
| `password123` | 11 | 11 | 11 |
| `éééé` (each character is U+00E9) | 4 | 4 | 8 |
| `😀😀` | 4 | 2 | 8 |
| `a\u0301` (a + combining acute) | 2 | 2 | 3 |

The table assumes strings contain the exact code points shown; Unicode can be entered in visually equivalent forms with different byte representations. **Never silently `trim()`, lower-case, or normalize passwords** in one place without doing the exact same when creating the hash, as doing so can lock users out or alter their chosen secret.

### 4.1. Why does BCrypt need a dedicated length policy?

Many traditional BCrypt implementations only process up to around **72 input bytes**, not 72 Unicode characters. Behavior past the limit varies across versions/implementations; some truncate, some reject. If two distinct passwords differ only in the truncated tail, that can create serious risks.

For an application choosing BCrypt directly, verify the **specific implementation** and design consistent behavior across registration, password change, and verification. One easy-to-understand example policy is **rejecting before encode/verify if UTF-8 exceeds 72 bytes**. This is an **illustrative protective policy**, **not a recommended password limit for every application**. A system needing longer Unicode passphrases must choose an appropriate design/algorithm instead of silently truncating secrets.

Do not arbitrarily prepend `SHA-256(password)` before BCrypt. Pre-hashing schemes must be carefully designed and reviewed for format, domain separation, Unicode, compatibility, and migration.

### 4.2. General limits for oversized inputs

Beyond BCrypt specifics, any password verifier needs **practical input limits** to prevent multi-MB/GB requests from wasting memory during JSON/form parsing, normalization, `String` allocation, or buffer creation—especially under concurrent load.

Apply limits at sensible layers:

1. HTTP ingress/proxy/container: bound body size and request rates, blocking anomalous payloads before the application allocates heavily.
2. Application validation: bound passwords by the **specified unit**, e.g. UTF-8 bytes if the algorithm has a byte limit; apply consistently across login/registration/password change.
3. Rate limiting: by account, IP/appropriate signals, paired with anti-abuse rules without opening arbitrary account-lockout channels.
4. Resource quotas: size CPU/RAM capacity properly and protect the system against excessive concurrent verifications.

**Do not default to short maximums like 8–20 characters** merely for UI simplicity. Users rely on password managers or long passphrases; limits should be generous enough for security requirements while fitting the chosen algorithm. With direct BCrypt, resolve the practical tension between long passwords and the 72-byte limit via an explicit design.

### 4.3. Consistent length checks at registration and login

If registration rejects >72 bytes while login silently lets them pass, or vice versa, users can hit confusing errors; if legacy accounts hold hashes created under older rules, plan a proper migration path.

Note: `@Size(max=72)` in Bean Validation typically checks **string length**, not UTF-8 byte count by default. If a byte limit is enforced, write an appropriate validator and test with Unicode strings.

## 5. Designing parameter selection safely

Do not start with "what should BCrypt cost be?"—start with **resource budgets and risk requirements**.

| Step | Action | Why |
| --- | --- | --- |
| 1 | Choose an algorithm/encoder matching the system and security policy | Avoid fast hashes or unvetted schemes. |
| 2 | Define acceptable verification latency at representative load | Login must meet user expectations and SLAs. |
| 3 | Pick a candidate range of cost parameters instead of fixing one immediately | Maximize protection without exceeding operational capacity. |
| 4 | Measure `matches` while idle, under realistic load, and across concurrency levels | Single-threaded numbers miss p95/p99 under contention. |
| 5 | Monitor CPU, GC, RAM, queueing, timeouts, and error rates | Wall-clock time alone does not reveal bottlenecks. |
| 6 | Pair rate limiting/abuse controls before raising cost | Protect against online brute force/DoS bursts. |
| 7 | Document encoder version, password policy, and upgrade/migration strategy | Changing algorithms can break recognition of old hashes. |

With BCrypt, comparing candidate settings like `10` and `12` helps illustrate the trend, but **they should not be treated as an up-to-date production recommendation**. The measurement section below teaches methodology; in real deployments, check current security policies and measure on real hardware.

With Argon2id/SCrypt, monitor **memory consumed per verification**. For instance, if a single hash temporarily needs many MiB and dozens of requests arrive concurrently, aggregate RAM usage can become a bottleneck even before CPU hits 100%.

## 6. Timing measurement: do not measure with a single nanoTime call

A basic timing snippet often looks like:

```java
long started = System.nanoTime();
boolean ok = passwordEncoder.matches(rawPassword, storedHash);
long elapsedNanos = System.nanoTime() - started;
```

This is a **code snippet inside a program with valid variables**, not a full benchmark. `System.nanoTime()` is suited for measuring **relative elapsed intervals** within the same JVM; it does not represent a wall-clock timestamp.

A single measurement can be skewed by:

- JIT compilation, class loading, library initialization;
- JVM warm-up and garbage collection;
- OS scheduling, CPU frequency scaling, thermal throttling;
- other process load, container CPU quotas;
- specific caches/JVM versions/providers and VM configuration;
- network/controller overhead if measured at the HTTP layer instead of around `matches`.

**Never claim encode and matches timings must be equal**, and do not compare runs unfairly if test hashes use different costs or test samples change between iterations.

### 6.1. Minimum measurement approach in a lab environment

1. Create an encoded hash **before** the timing loop; when measuring `matches`, do not include `encode` cost in the measurement.
2. Warm up the JVM/encoder with controlled verification calls.
3. Run multiple iterations on the same raw password/encoded hash and record each duration.
4. Report median, p95, and other percentiles with sufficient samples; with very few samples, p95 is only illustrative.
5. Repeat runs under varying concurrency levels; never mix local laptop numbers with production hardware as if conditions matched.
6. Separate overall HTTP request metrics from isolated `PasswordEncoder.matches` metrics.
7. Never log or record any real passwords or hashes.

A lab program can sample 11 runs to demonstrate **percentile calculation**, but **11 samples cannot certify an SLA, p99, or side-channel resistance**. For rigorous benchmarking, use standard tools like JMH for microbenchmarks and HTTP-layer load tests with sufficient sample counts and traffic.

### 6.2. Encode time, verify time, and response time differ

```text
t_response =
  network / proxy
  + parsing and request filters
  + user lookup/database/cache
  + password verification (matches)
  + success/failure handling
  + response serialization/network
  + scheduling/queueing delays
```

In reality, components can overlap rather than adding strictly linearly; the formula only illustrates timing sources that must be separated. **High latency on `/login` does not by itself prove BCrypt cost is too high.** It could be a slow DB, busy queue, GC, lock contention, cache miss, or network.

## 7. Runnable Spring Security Crypto + Java 17 example: bounded benchmark

This example runs with Maven and Java 17. It measures `PasswordEncoder.matches` on pre-generated BCrypt hashes and applies a **demo-only policy: 8 code points minimum up to 72 UTF-8 bytes maximum**. This is not a mandatory password policy definition. The code contains no real user credentials.

### 7.1. Directory structure

```text
password-cost-lab/
  pom.xml
  src/
    main/java/demo/password/PasswordCostLab.java
    test/java/demo/password/PasswordCostLabTest.java
```

### 7.2. Maven dependencies

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>password-cost-lab</artifactId>
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
            <groupId>org.springframework</groupId>
            <artifactId>spring-jcl</artifactId>
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
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Here the Spring Boot parent only manages versions and build configuration; the runnable class is a **plain Java `main`** calling the Spring Security Crypto library without starting a web server. `spring-jcl` is added explicitly to avoid missing logging components on a minimal classpath.

### 7.3. PasswordCostLab.java program

File `src/main/java/demo/password/PasswordCostLab.java`:

```java
package demo.password;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;

import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class PasswordCostLab {

    // DEMO rule for direct BCrypt; not a global standard.
    static final int MIN_CODE_POINTS = 8;
    static final int MAX_UTF8_BYTES = 72;

    private PasswordCostLab() {}

    static void validateCandidate(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("Missing password");
        }

        int codePoints = raw.codePointCount(0, raw.length());
        int utf8Bytes = raw.getBytes(StandardCharsets.UTF_8).length;

        if (codePoints < MIN_CODE_POINTS || utf8Bytes > MAX_UTF8_BYTES) {
            throw new IllegalArgumentException("Password length not allowed");
        }
    }

    static boolean verify(PasswordEncoder encoder,
                          String raw,
                          String storedEncoded) {
        validateCandidate(raw);
        return encoder.matches(raw, storedEncoded);
    }

    record Timing(long minNanos, long medianNanos, long p95Nanos) {

        double minMs() {
            return minNanos / 1_000_000.0;
        }

        double medianMs() {
            return medianNanos / 1_000_000.0;
        }

        double p95Ms() {
            return p95Nanos / 1_000_000.0;
        }
    }

    static Timing measureVerification(PasswordEncoder encoder,
                                      String raw,
                                      String storedEncoded,
                                      int warmup,
                                      int samples) {
        if (warmup < 0 || samples < 2) {
            throw new IllegalArgumentException("Invalid measurement sizes");
        }

        for (int i = 0; i < warmup; i++) {
            if (!verify(encoder, raw, storedEncoded)) {
                throw new IllegalStateException("Warmup verification failed");
            }
        }

        long[] elapsed = new long[samples];

        for (int i = 0; i < samples; i++) {
            long start = System.nanoTime();
            boolean matched = verify(encoder, raw, storedEncoded);
            elapsed[i] = System.nanoTime() - start;

            if (!matched) {
                throw new IllegalStateException("Verification failed");
            }
        }

        Arrays.sort(elapsed);

        int p95Index = (int) Math.ceil(samples * 0.95) - 1;
        return new Timing(
            elapsed[0],
            elapsed[(samples - 1) / 2],
            elapsed[p95Index]
        );
    }

    public static void main(String[] args) {
        String samplePassword = "Learning42!"; // DEMO data only.
        validateCandidate(samplePassword);

        for (int workFactor : new int[] {10, 12}) {
            PasswordEncoder encoder = new BCryptPasswordEncoder(workFactor);

            // Encode once; DO NOT include encode in matches timing.
            String storedEncoded = encoder.encode(samplePassword);

            boolean valid = verify(encoder, samplePassword, storedEncoded);
            boolean rejected = !verify(
                encoder, samplePassword + "x", storedEncoded
            );

            System.out.printf(
                "cost=%d valid=%b wrongRejected=%b%n",
                workFactor, valid, rejected
            );

            Timing time = measureVerification(
                encoder, samplePassword, storedEncoded, 3, 11
            );

            System.out.printf(
                "cost=%d verify_ms_min=%.1f median=%.1f p95=%.1f%n",
                workFactor, time.minMs(), time.medianMs(), time.p95Ms()
            );
        }
    }
}
```

Explanation:

- `validateCandidate` uses `codePointCount` and UTF-8 byte length, not just `String.length()`.
- `BCryptPasswordEncoder(workFactor)` produces a hash with the corresponding cost; `storedEncoded` is created before measuring `matches`.
- `verify` checks input limits and then calls `matches`; the wrong-password sample has a valid length and is rejected.
- `warmup=3`, `samples=11` are small counts to **observe the mechanism**, insufficient to certify production p95.
- `Arrays.sort` sorts the 11 durations and extracts min, median, and an illustrative p95 index. `System.nanoTime` measures elapsed time.
- Neither hashes nor plaintext passwords are printed. Hardcoded strings are strictly demo data; never place real passwords in source code.

### 7.4. Testing correctness, not timing thresholds

File `src/test/java/demo/password/PasswordCostLabTest.java`:

```java
package demo.password;

import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PasswordCostLabTest {

    @Test
    void rightAndWrongPasswordsHaveDifferentResults() {
        PasswordEncoder encoder = new BCryptPasswordEncoder(10);
        String encoded = encoder.encode("CorrectPass9!");

        assertTrue(PasswordCostLab.verify(
            encoder, "CorrectPass9!", encoded
        ));

        assertFalse(PasswordCostLab.verify(
            encoder, "IncorrectPass9!", encoded
        ));
    }

    @Test
    void rejectsTooShortCandidate() {
        PasswordEncoder encoder = new BCryptPasswordEncoder(10);

        assertThrows(IllegalArgumentException.class, () ->
            PasswordCostLab.verify(encoder, "short", "not-used")
        );
    }

    @Test
    void rejectsUnicodeCandidateExceedingUtf8Limit() {
        PasswordEncoder encoder = new BCryptPasswordEncoder(10);

        // 40 occurrences of 'é' = 40 code points, 80 UTF-8 bytes.
        String tooLong = "é".repeat(40);

        assertThrows(IllegalArgumentException.class, () ->
            PasswordCostLab.verify(encoder, tooLong, "not-used")
        );
    }

    @Test
    void measuresSamplesWithoutTimingThresholdAssertion() {
        PasswordEncoder encoder = new BCryptPasswordEncoder(10);
        String raw = "AnotherPass7!";
        String encoded = encoder.encode(raw);

        PasswordCostLab.Timing result =
            PasswordCostLab.measureVerification(
                encoder, raw, encoded, 1, 3
            );

        assertTrue(result.minNanos() >= 0);
        assertTrue(result.medianNanos() >= result.minNanos());
        assertTrue(result.p95Nanos() >= result.medianNanos());
    }
}
```

The tests do not assert "must run under 100 ms" because CI timings can vary widely. Their purpose is to verify right/wrong password checking, Unicode length limits, and the measurement algorithm structure.

### 7.5. Commands and output

In the `password-cost-lab` directory, with JDK 17+ and Maven installed:

```bash
mvn test
mvn -q compile exec:java -Dexec.mainClass=demo.password.PasswordCostLab
```

`mvn test` is expected to have **4 passing tests** when dependencies and environment are ready. For the main program, logical output lines look like:

```text
cost=10 valid=true wrongRejected=true
cost=10 verify_ms_min=<measured> median=<measured> p95=<measured>
cost=12 valid=true wrongRejected=true
cost=12 verify_ms_min=<measured> median=<measured> p95=<measured>
```

The two lines containing `<measured>` above are **format templates**, not exact stdout. Actual measured values depend on the environment; never fabricate a number and call it a benchmark result. The `valid=true wrongRejected=true` lines are expected to be deterministic when execution succeeds.

**Performance note when running:** Work factor 12 can make the command take noticeably longer than 10. Only run controlled benchmarks; never run unbounded stress tests on a production server.

## 8. Measure one request or the whole system? Only load tests answer operational capacity

### 8.1. CPU time and response time

A `matches` call can consume substantial CPU. When many requests arrive concurrently, waiting for CPU/thread pools raises response latency, even though an isolated verification keeps a similar processing time.

You can make a **very rough** load estimate:

```text
CPU-seconds per second ≈
  requests_verified_per_second × CPU_seconds_per_verification
```

For a **hypothetical** example where each verification consumes 0.10 CPU-second and there are 40 verifications/second, total demand is around 4 CPU-seconds per second. This is a coarse budget calculation, **not a guarantee that exactly 4 vCPUs suffice**, because context switching, CPU limits, worker concurrency, other overhead, and differences between CPU time and elapsed time all apply.

Another perspective is Little's Law: in steady state, the number of operations in the system approximates the arrival rate times the time they spend in the system. However, you must use **total time including queueing**, not confuse it with BCrypt CPU time alone.

### 8.2. Load profiles to test

- **Normal login:** a steady stream of legitimate users.
- **Repeated wrong passwords:** failed verifications still consume resources, designed to deter offline brute force while requiring online protection.
- **Non-existent usernames:** measure separately to spot notable differences between lookup misses and password mismatches—not to build a client oracle.
- **Bursts:** sudden traffic spikes triggered by an event.
- **Mixed workload:** logins + application requests + background jobs + DB, on production-like resources.
- **Multi-instance:** test on the exact container type and CPU quota used in real scaling plans.
- **RAM-intensive tasks:** if using Argon2/SCrypt, track RSS, native memory, OOMs, and concurrency.

Results should include: p50/p95/p99 **response latency**, completed throughput, error rate, CPU utilization, memory, GC, queue depth, and throttling frequency. Never report averages alone.

### 8.3. Abuse protections

On the login endpoint, place rate limiting and abuse detection at appropriate boundaries to prevent verification resources from being exhausted. Criteria can combine IP, account, device, risk, and other signals; do not rely solely on a single easily spoofed key or one that allows locking out arbitrary accounts.

Do not unconditionally generate a dummy password hash on every invalid login just to "equalize timing": that cost can help attackers overload the system. When handling non-existent users, evaluate timing exposure across the authentication provider and entire response pipeline alongside traffic controls.

## 9. Timing side channels: performance timing does not prove constant-time

Distinguish two concerns:

**Latency measurement for performance:** knowing how long verification takes when changing cost, raising load, or swapping hardware.

**Timing information leakage:** if "user exists" and "user does not exist" consistently show distinct timing profiles, attackers may try to infer information. Differences also arise from DB/cache, HTTP responses, exception handling, and the network.

Many cryptographic comparisons aim to avoid secret-dependent variations, yet you cannot look at a snippet or a few `System.nanoTime` numbers and declare an entire login endpoint "constant-time".

Useful practices:

1. Return appropriate generic error messages so "username exists" is not leaked.
2. Avoid starkly different code paths between lookup success/failure if that opens an account-enumeration channel.
3. Use supported authentication mechanisms/providers instead of rolling your own `equals` comparison.
4. Never compare valid/invalid password timings across 5 or 10 samples and subjectively declare them safe.
5. Combine rate limiting, safe logging, and monitoring; never rely on "random sleep" as a sole defense.
6. Evaluate side channels at the layer observable by an attacker (the final response), not solely around a Java method call.

Verification duration **must never be returned directly in responses** making client measurement trivial. Measurements can go to internal metrics with safe metric names and bounded-cardinality tags; never put passwords or usernames in metric labels.

## 10. Strategy for raising work factor when the application already has users

Never change hashes in the database by taking the old hash string and calling `encode(oldHash)`: that produces a hash of a hash, lacks the original password, and breaks normal logins.

Spring Security can inspect parameters/formats via the corresponding encoder and the `PasswordEncoder.upgradeEncoding(String encodedPassword)` API. When designing a migration, consider **rehashing after a successful authentication** using the raw password just supplied by the user, once verified and permitted by policy.

Conceptual flow:

```text
User logs in with valid password
      |
      v
Read stored hash/format
      |
      v
PasswordEncoder.matches(raw, storedHash)
      |
      +-- false -> reject, do not modify hash
      |
      +-- true  -> if old hash/cost needs upgrade:
                       encode(raw) with new configuration
                       save new hash in an appropriate transaction
                   then complete login
```

**This is a policy diagram; not every provider updates the DB automatically by default.** When using `DaoAuthenticationProvider`, you can integrate `UserDetailsPasswordService` to update the encoded password after successful authentication depending on configuration. Legacy passwords/formats require explicit compatibility strategies and testing.

### 10.1. DelegatingPasswordEncoder and id prefixes

Spring Security provides `DelegatingPasswordEncoder` to select an algorithm based on an id in the encoded string, such as `{bcrypt}...`. That is an **algorithm identification format**, not a place holding plaintext.

One way to create an encoder with Spring Security defaults:

```java
PasswordEncoder encoder =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();
```

This snippet requires importing `PasswordEncoder` and `PasswordEncoderFactories` from `org.springframework.security.crypto.password`. Defaults change across versions; check the encoder used for creating new hashes and which legacy ids are accepted. Never assume raw `$2a$...` hashes will automatically be recognized by every `DelegatingPasswordEncoder` when `{id}` is missing.

### 10.2. Never raise work factor without a plan

Raising cost abruptly can cause CPU spikes during peak hours. Test on production-like staging, assess load capacity, roll out gradually, monitor failures/latency, and prepare handling for old hashes.

When using memory-hard hashing, monitor RAM alongside CPU across concurrent verifications. "Slower encode" does not automatically mean "more stable verify" if resources are contended.

## 11. Integrating limit policies with Servlet/Spring Security

In a Servlet application, input may arrive from form login, a JSON registration API, or a password-change controller. Distinguish **account domain validation** from **framework authentication mechanics**.

### 11.1. Registration and password change

The registration controller/service can invoke the standardized password validator before `PasswordEncoder.encode`. Key checks:

- Never silently truncate passwords.
- Never `trim` / lower-case passwords without a consistent policy.
- Enforce byte limits matching the algorithm, especially with direct BCrypt.
- Never store plaintext or expose hashes to clients.
- Never derive work factor solely from user input.
- Rate limit registration/password-change endpoints if they can be spammed.

### 11.2. Login handled by UsernamePasswordAuthenticationFilter

With default form login, requests may be processed **before any controller** by `UsernamePasswordAuthenticationFilter`. Therefore, **a validator placed only inside a registration controller does not automatically protect the login filter**. To enforce limits consistently, place a check before hash verification—such as configuring an appropriate authentication filter/converter or a validator at the authentication boundary with an explicit policy.

Do not write a filter that reads the request body twice and breaks the Servlet input stream. Do not replace `DaoAuthenticationProvider` with a custom class comparing hashes manually. If multiple security filter chains exist, apply the policy to the exact chain handling login requests.

Also maintain HTTP body size limits at the proxy/container and rate-limit requests; a Java validator cannot prevent all resource costs incurred before reaching the controller or filter.

### 11.3. Do not block valid passphrases with unfounded rules

Good password standards favor long passwords, password managers, breached-password checks, and MFA where appropriate rather than forcing arbitrary special-character counts. Given BCrypt's algorithm limit, **document the constraint clearly and consider another algorithm** if business rules must support long Unicode passphrases. The 72-byte limit in this lesson's example merely keeps the demo consistent with traditional BCrypt's limit.

## 12. Analyzing real-world scenarios

| Scenario | Accurate assessment | What to do |
| --- | --- | --- |
| BCrypt cost raised from 10 to 12; login is slower | Work rounds scale exponentially, though actual ms depend on hardware and load | Re-measure in deployment environment, monitor p95/p99 and CPU |
| A password with 60 `é` characters exceeds 72 bytes | Character length and UTF-8 byte length differ | Check bytes, enforce consistent policy/algorithm, never silently truncate |
| User submits a 10 MB password | Can trigger excessive allocation and parsing/hashing | Cap request body early, validate reasonable limits, rate limit |
| `@Size(max=72)` passes yet BCrypt processes truncated data | Validator may measure `String` length, not bytes | Use a byte-aware validator or a suitable alternative design |
| Re-hashing with BCrypt produces a different salt | Usually expected behavior | Use `matches`, never compare two encode outputs |
| Single local verify measures 50 ms | Does not prove this latency holds under high load | Warm up, use many samples, benchmark under concurrency |
| Non-existent username responds faster than wrong password | Potential account-enumeration channel | Inspect provider/lookup, responses, rate limits, and carefully test side channels |
| Login system returns 503 during brute-force wave | Verification cost can cause overload | Rate limiting, capacity planning, queue/resource monitoring |
| Cost migration triggers CPU spike | New hashes cost more; concentrated upgrades add load | Roll out gradually, rehash selectively, and meter/limit |
| API uses JWT yet team benchmarks BCrypt on every request | May be benchmarking the wrong auth path | Identify actual auth mechanism before optimizing |
| Argon2/SCrypt handles 1 request fine yet OOMs at 50 requests | Memory-hard algorithms use significant memory | Measure peak RSS and concurrency, set safe quotas |

## 13. Review checklist and incident diagnostics

Before shipping a password policy to production, answer these questions:

**Algorithms and storage**

- Which `PasswordEncoder`, version, and cost parameters are active? Do encoded strings retain enough info to identify the algorithm/cost?
- Is salt generated by the proper encoder? Are any fast hashes or plaintext passwords still used?
- Does login call `matches` on the stored hash, or accidentally encode and compare strings?
- Is there a cost/algorithm upgrade strategy for old hashes that preserves users' ability to log in?

**Input limits**

- Is request body size bounded before expensive allocations?
- Are password limits based on **UTF-8 bytes**, code points, or another unit? Is the unit explicitly documented?
- How are long Unicode passwords and BCrypt's limit handled?
- Do registration, login, password change, and password reset accept/validate passwords consistently?
- Do you avoid silently truncating/`trim`ming/normalizing passwords without user awareness?

**Measurement and operations**

- Is measured duration capturing `matches`, `encode`, user lookup, or end-to-end HTTP response?
- Did testing include JVM warm-up, enough samples, and concurrent load?
- Are p50/p95/p99, CPU, RAM, GC, queues, throttling, and error rates tracked?
- Are rate limiting and abuse monitoring enabled for login?
- Are passwords, hashes, tokens, and usernames kept out of metrics/logs?
- Have timing imbalances between user-not-found and bad-password been checked without creating a user-enumeration oracle?

## 14. Self-check questions

**Q1.** Why should you not store plain `SHA-256(password)` instead of properly configured BCrypt/Argon2/PBKDF2/SCrypt?

**Answer:** Fast hashes make testing many candidate passwords cheap if the database is breached. Dedicated password hashing introduces salt and computational/memory cost into the derivation to make each guess expensive.

**Q2.** Does BCrypt cost = 12 verify in exactly 12 ms?

**Answer:** No. That is a work factor, not a unit of time. Measure on target hardware and realistic load.

**Q3.** Do two passwords both 50 characters long always have the same UTF-8 byte count?

**Answer:** No. ASCII, accented characters, and emoji typically occupy different byte counts. Moreover, Java's `String.length()` counts UTF-16 code units.

**Q4.** If a password is valid but the app calls `encode(raw)` and compares the new hash with the DB hash using `equals`, what happens?

**Answer:** Two encodes can use different random salts, producing different hash strings for the same raw password. Always use `PasswordEncoder.matches(raw, storedHash)`.

**Q5.** Why is benchmarking `matches` on a single request insufficient to decide production cost?

**Answer:** You must consider JVM/JIT, multiple samples, CPU/RAM quotas, concurrent requests, and end-to-end latency. One idle request does not represent throughput or p95/p99 under load.

**Q6.** To save performance, should you skip password verification for non-existent usernames and fail immediately?

**Answer:** Consider the security impact; timing differences can aid account enumeration. Use supported providers/mechanisms, appropriate error responses, and traffic controls rather than creating an information-leaking fast path.

**Q7.** Why is raising cost alone not a complete defense against online brute force?

**Answer:** Attackers can send many requests, exhausting resources and causing DoS. Combine it with rate limiting, monitoring, MFA, and other controls.

**Q8.** Can hashes be upgraded from an old work factor to a new one without the original password?

**Answer:** You cannot properly recompute the original password's hash under the new settings from the old hash alone; you normally need a valid login to temporarily obtain the raw password and rehash, or a reset/migration workflow.

## 15. Key takeaways

- `PasswordEncoder.matches` is the typical password verification step in `DaoAuthenticationProvider`; cost protects against offline guessing while consuming server resources.
- Work factor **is not milliseconds**. Parameters for BCrypt, PBKDF2, SCrypt, and Argon2id must be chosen after measuring on representative hardware and load.
- Enforce request size and password length limits **in the unit the policy actually requires**; with direct BCrypt, pay close attention to the ~72 UTF-8 byte limit in many implementations.
- Never silently truncate, trim, change case, or normalize passwords inconsistently between registration and verification.
- Measure `matches` after warm-up across many samples, watching median/p95/p99 alongside throughput, CPU, and RAM. Lab latency alone does not prove constant-time execution or an SLA.
- Combine rate limiting and anti-abuse controls, avoid user enumeration/timing oracles, and never write credentials or hashes into logs/metrics.
- When raising cost or changing algorithms, plan versioning, rehashing, and capacity rollout; never re-encode the old hash string itself.

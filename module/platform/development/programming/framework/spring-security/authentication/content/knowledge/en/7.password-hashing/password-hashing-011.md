# Measuring Verification Cost, Input Limits, and Resource Exhaustion Prevention

> **Scope:** Spring Security Authentication — **Password Hashing**. This lesson explains how to measure `PasswordEncoder.matches(...)` cost, choose BCrypt/Argon2id work factors based on real capacity, validate password size and validity, prevent CPU/RAM/thread-pool exhaustion from concurrent verifications, and design benchmarks, rate limiting, admission control, and testing. Java 17+ examples use Spring Security Crypto **6.5.11**, run with Gradle. Timing numbers in the examples **are measured at runtime**, never fabricated or treated as constants across all machines.

## 1. Why Can Password Verification Bottleneck a System?

A password-hashing function such as **bcrypt, Argon2id, scrypt, or PBKDF2** deliberately consumes resources. The goal is making bulk password guessing against leaked hash data expensive. However, both legitimate users and attackers can send requests requiring the backend to verify passwords.

```text
POST /login
   |
   v
Gateway / HTTP server
   |  request-size limit + network rate limit
   v
Authentication endpoint
   |  input validation + per-account quota + admission control
   v
UserDetailsService / credential store
   |  fetch hash and account status
   v
PasswordEncoder.matches(rawPassword, storedHash)
   |  CPU time and/or RAM depending on algorithm
   v
Authentication success / failure / overload response
```

An unconstrained login endpoint can receive hundreds or thousands of wrong-password requests. **Wrong passwords can still force the server to run expensive hashing.** When CPU is saturated, legitimate requests queue up, p95/p99 latency spikes, and requests can time out. With memory-hard algorithms, many parallel hashes also risk exceeding RAM limits.

Three independent questions:

1. **What is the cost of one verification?** Measure `matches(...)` and the full authentication flow on real hardware.
2. **Which inputs are allowed into verification?** Validate request size, password length/UTF-8 bytes, malformed Unicode, and hash format; never turn a gigantic string into a CPU/RAM-intensive task.
3. **How many requests are permitted concurrently or over time?** Combine per-account/per-source rate limiting, concurrency caps, bounded queues, timeouts, MFA/risk signals, and admission control.

**This cannot be solved solely by raising BCrypt cost.** Higher cost makes offline attacks more expensive while simultaneously slowing the server under login traffic. Conversely, lowering cost to absorb overload weakens resistance to offline password guessing.

## 2. Measuring the Right Step in Spring Security

In form-login or HTTP Basic flows, the common path is:

```text
Authentication filter
  -> UsernamePasswordAuthenticationToken (unauthenticated)
  -> AuthenticationManager / ProviderManager
  -> DaoAuthenticationProvider
      |-> UserDetailsService.loadUserByUsername(username)
      |      -> password hash, status, GrantedAuthority
      |-> PasswordEncoder.matches(rawPassword, storedHash)
  -> Authentication succeeds or AuthenticationException
```

Distinguish:

| Operation | When Used | What to Measure |
| --- | --- | --- |
| `encode(raw)` | Registration, password reset/change, post-verify rehash | Time and resources to create a password hash and salt |
| **`matches(raw, encodedHash)`** | Login, password re-verification | **Verification cost**; use a hash **created outside the measured loop** |
| `loadUserByUsername(...)` | Provider loading user | DB latency, connection pool, authority/group queries |
| End-to-end authentication | Filter → manager → provider → response | HTTP p50/p95/p99, queue wait, error rate, CPU/RAM |

Do not run `encode` and `matches` inside the same measured block and call the result "verify time": `encode` creates a new password hash, usually with a new salt. `matches` uses the stored hash.

```java
// Benchmark snippet; encoder, raw, storedHash, and samples are already created.
for (int i = 0; i < samples; i++) {
    long started = System.nanoTime();
    boolean ok = encoder.matches(raw, storedHash);
    long elapsedNanos = System.nanoTime() - started;
    if (!ok) {
        throw new IllegalStateException("Test password must match");
    }
    durations[i] = elapsedNanos;
}
```

`System.nanoTime()` measures elapsed time better than `System.currentTimeMillis()`. Do not print to console, log SQL, instantiate `SecureRandom`, or make network calls inside each measured iteration because that skews results.

### Where Does the Work Factor Live?

With BCrypt:

```java
PasswordEncoder encoder = new BCryptPasswordEncoder(12);
String storedHash = encoder.encode("demo-secret");
boolean ok = encoder.matches("demo-secret", storedHash);
```

This snippet requires imports and an enclosing method/class; it is not a standalone runnable program. Direct BCrypt hashes are typically 60 characters long, containing version, salt, and **cost**:

```text
$2a$12$...salt and hash result portion...
    ^^
    cost stored inside the hash
```

- `new BCryptPasswordEncoder()` defaults to cost **10** in the Spring Security 6.5 branch.
- Raising cost from 10 to 11 roughly doubles algorithmic work; **actual milliseconds** depend on hardware and concurrent load.
- Switching the bean to cost 12 does not automatically turn every old cost-10 hash in the DB into cost 12. `matches` verifies using the **stored hash's** parameters.
- `upgradeEncoding(storedHash)` can signal that a hash should be upgraded; it does not modify the DB by itself. Rehash only from a **validly verified raw password**, never re-hashing the hash string itself.
- With `DelegatingPasswordEncoder`, prefixes like `{bcrypt}` select the algorithm; you may need to measure existing cost-10/12 bcrypt and Argon2id hashes separately in the same DB.

### BCrypt and Argon2id Do Not Consume Resources Identically

| Algorithm | Primary Resource Consumption | Parameters to Benchmark |
| --- | --- | --- |
| BCrypt | Primarily CPU | cost/strength, request concurrency |
| Argon2id | CPU and memory | memory cost, iterations, parallelism, concurrent hashes |
| scrypt | CPU and memory | N, r, p, native/heap memory |
| PBKDF2 | Primarily CPU | iterations, PRF, input limits |

Argon2id is preferred by OWASP for new systems, yet **raising memory cost while increasing concurrency** can trigger OOM before CPU hits 100%. Do not look only at single-operation verify time while ignoring RAM across concurrent operations.

## 3. Measuring Percentiles, Throughput, and Wait Time

A single fast or slow `matches` call is insufficient for capacity conclusions:

| Metric | Meaning |
| --- | --- |
| `p50` | 50% of verifications finish no slower than this value |
| `p95` | 95% of verifications finish no slower than this value |
| `p99` | Slowest 1% tail; especially critical under overload |
| `verify/sec` | Steady-state hash verifications processed per second |
| `in-flight` | Number of hashes currently executing |
| `queue-wait` | Time waiting for resource admission before hashing |
| CPU and CPU throttling | Exceeding core quotas or container CPU throttling? |
| Heap/native RAM, GC | Memory pressure from Argon2/scrypt, parsers, queues? |
| Error/rejection | Are bad passwords, invalid inputs, rate limits, and overload clearly separated? |
| HTTP login p95/p99 | Total user wait from request submission to response |

You must **separate verification time from total request time**:

```text
T_login ≈ T_queue + T_request_processing
T_request_processing includes:
    parse/validate request
    load user from DB/cache
    PasswordEncoder.matches
    status/authorization-related checks
    response/security handling
```

Factors like CPU contention, GC, connection pools, and network cause components to fluctuate, so never deduce bcrypt time by naive subtraction. Instrument each stage separately.

A trustworthy benchmark requires JVM warmup, multiple samples, varied costs, load bounds, and documented hardware/JVM specs. With JMH, you can compare microbenchmarks; afterward run **HTTP load tests on staging** to test the real system. Never take p99 from 10 samples and conclude production SLOs are met.

## 4. Validating Passwords Before Hashing: Byte Limits and Request Size

### 4.1. BCrypt's 72 **UTF-8 Byte** Limit

Traditional BCrypt has a common input limit of **72 bytes**. That is not 72 Unicode characters, nor Java's `String.length() == 72`.

| Test Password | `String.length()` | UTF-8 bytes | Relative to 72-Byte Limit |
| --- | ---: | ---: | --- |
| `"A".repeat(72)` | 72 | 72 | At exact limit |
| `"A".repeat(73)` | 73 | 73 | Exceeds |
| `"界".repeat(24)` | 24 | 72 | At exact limit |
| `"界".repeat(25)` | 25 | 75 | Exceeds |
| `"😀".repeat(18)` | 36 | 72 | At exact limit |
| `"😀".repeat(19)` | 38 | 76 | Exceeds |
| `"é"` precomposed form | 1 | 2 | Differs from decomposed combining form |
| `"e\u0301"` combining form | 2 | 3 | Different bytes unless a normalization policy exists |

`String.length()` counts **UTF-16 code units**. An emoji can occupy two code units and four UTF-8 bytes. Code points do not necessarily match user-perceived characters either, especially with combining marks or multi-code-point emoji sequences.

OWASP recommends capping passwords intended for bcrypt at **72 bytes or fewer if the implementation has a tighter limit**. Some older versions risked ignoring trailing bytes past the limit; Spring Security published advisory **CVE-2025-22228** regarding overlong input validation. Use patched versions and **reject** overlong passwords rather than truncating them.

**Do not do this**:

```java
// Anti-pattern: alters the user's secret and counts characters instead of bytes.
String shortened = rawPassword.substring(
        0, Math.min(rawPassword.length(), 72));
```

Doing so can collapse two distinct passwords onto the same prefix. Never silently trim, lowercase, strip accents, or normalize passwords: registration and login must apply the exact same documented transformation without breaking stored hashes.

### 4.2. Multi-Layer Validation

```text
Client / API caller
    |
    v
Proxy + web server:
  request-body cap; header cap; timeout; rate limit
    |
    v
Request binding/validation:
  null, empty, max UTF-8 bytes, valid Unicode, password policy
    |
    v
Authentication admission:
  per-account/per-IP quota; concurrent hash cap
    |
    v
PasswordEncoder.matches(...)
```

Frontend `maxlength` helps UX but **is not a security control**. Bean Validation `@Size(max=72)` typically counts characters and does not guarantee byte limits. The backend must validate before calling expensive algorithms, consistently across **registration, login, password change, password recovery, and admin-set-password**.

Reject huge bodies at the gateway or container **before** parsers allocate strings. A multi-megabyte password can exhaust memory during HTTP/JSON parsing or regex checks even if the encoder ultimately rejects it.

Avoid regexes prone to **catastrophic backtracking** when validating password policies. If an external password-strength service slows down, enforce timeouts/circuit breakers; never stall login threads indefinitely.

### 4.3. Do Not Apply One Wrong Policy Across Multiple Algorithms

If a product stores both BCrypt and Argon2id inside `DelegatingPasswordEncoder`, a password >72 bytes can be valid for the new algorithm while invalid for bcrypt. Policy must consider the **algorithm of the hash being verified** and the **algorithm creating new hashes**, with a clear migration and UX plan. Do not wrap every encoder in a blanket 72-byte wrapper merely because the system previously used bcrypt.

## 5. Runnable Java 17+ Example: Measuring BCrypt and Gating Verification

This standalone example uses `spring-security-crypto:6.5.11`, requiring no Spring Boot web server. It:

1. Validates passwords in UTF-8 bytes and rejects malformed UTF-16.
2. Generates BCrypt hashes **outside** the `matches` timing loop, warms up, and prints p50/p95 for costs 10 and 11.
3. Simulates a `Semaphore` capping concurrent verifications: when slots are occupied, returns **BUSY** rather than treating it as a wrong password.

### 5.1. Project Files

```text
password-verification-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/PasswordVerificationDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'password-verification-demo'
```

`build.gradle`:

```groovy
plugins {
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
    implementation 'org.springframework.security:spring-security-crypto:6.5.11'
}

application {
    mainClass = 'demo.PasswordVerificationDemo'
}
```

### 5.2. Complete Program

Create `src/main/java/demo/PasswordVerificationDemo.java`:

```java
package demo;

import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Locale;
import java.util.concurrent.Semaphore;

import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class PasswordVerificationDemo {
    private static final int MAX_BCRYPT_BYTES = 72;

    public static void main(String[] args) throws InterruptedException {
        String raw = "demo-passphrase-123";
        PasswordEncoder cost10 = new BCryptPasswordEncoder(10);
        String storedHash = cost10.encode(raw);

        System.out.println("match-good="
                + cost10.matches(raw, storedHash));
        System.out.println("match-wrong="
                + cost10.matches("wrong-password", storedHash));
        System.out.println("ascii72-valid="
                + bcryptInputValid("A".repeat(72)));
        System.out.println("ascii73-valid="
                + bcryptInputValid("A".repeat(73)));
        System.out.println("unicode24-valid="
                + bcryptInputValid("界".repeat(24)));
        System.out.println("unicode25-valid="
                + bcryptInputValid("界".repeat(25)));
        System.out.println("emoji18-valid="
                + bcryptInputValid("😀".repeat(18)));
        System.out.println("emoji19-valid="
                + bcryptInputValid("😀".repeat(19)));

        String invalidUtf16 = String.valueOf((char) 0xD800);
        System.out.println("invalid-unicode-valid="
                + bcryptInputValid(invalidUtf16));

        Semaphore slots = new Semaphore(1);
        GatedVerifier gated = new GatedVerifier(cost10, slots);
        slots.acquire();
        try {
            System.out.println("when-busy="
                    + gated.verify(raw, storedHash));
        } finally {
            slots.release();
        }
        System.out.println("after-release="
                + gated.verify(raw, storedHash));

        for (int cost : new int[] {10, 11}) {
            PasswordEncoder encoder = new BCryptPasswordEncoder(cost);
            Measurement result = measure(encoder, raw, 3, 12);
            System.out.printf(Locale.ROOT,
                    "cost=%d samples=%d p50-ms=%.2f p95-ms=%.2f%n",
                    cost, result.samples(),
                    result.p50Millis(), result.p95Millis());
        }
    }

    private static boolean bcryptInputValid(String input) {
        if (input == null || input.isEmpty()
                || input.length() > MAX_BCRYPT_BYTES) {
            return false;
        }

        try {
            int bytes = StandardCharsets.UTF_8.newEncoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .encode(CharBuffer.wrap(input))
                    .remaining();

            return bytes <= MAX_BCRYPT_BYTES;
        } catch (CharacterCodingException invalidInput) {
            return false;
        }
    }

    private static Measurement measure(
            PasswordEncoder encoder, String raw,
            int warmup, int iterations) {
        if (!bcryptInputValid(raw) || iterations <= 0) {
            throw new IllegalArgumentException("Invalid benchmark setup");
        }

        String storedHash = encoder.encode(raw); // OUTSIDE measured region

        for (int i = 0; i < warmup; i++) {
            if (!encoder.matches(raw, storedHash)) {
                throw new IllegalStateException("Warmup failed");
            }
        }

        long[] measurements = new long[iterations];
        for (int i = 0; i < iterations; i++) {
            long start = System.nanoTime();
            boolean ok = encoder.matches(raw, storedHash);
            measurements[i] = System.nanoTime() - start;
            if (!ok) {
                throw new IllegalStateException("Verification failed");
            }
        }

        Arrays.sort(measurements);
        return new Measurement(
                iterations,
                percentileMs(measurements, 0.50),
                percentileMs(measurements, 0.95));
    }

    private static double percentileMs(long[] sortedNanos, double p) {
        int index = Math.max(0, Math.min(sortedNanos.length - 1,
                (int) Math.ceil(p * sortedNanos.length) - 1));
        return sortedNanos[index] / 1_000_000.0;
    }

    private record Measurement(
            int samples, double p50Millis, double p95Millis) {}

    private enum Outcome {
        MATCH, MISMATCH, BUSY, INVALID_INPUT
    }

    private static final class GatedVerifier {
        private final PasswordEncoder encoder;
        private final Semaphore permits;

        GatedVerifier(PasswordEncoder encoder, Semaphore permits) {
            this.encoder = encoder;
            this.permits = permits;
        }

        Outcome verify(String raw, String storedHash) {
            if (!bcryptInputValid(raw)) {
                return Outcome.INVALID_INPUT;
            }
            if (!permits.tryAcquire()) {
                return Outcome.BUSY;
            }

            try {
                return encoder.matches(raw, storedHash)
                        ? Outcome.MATCH
                        : Outcome.MISMATCH;
            } finally {
                permits.release();
            }
        }
    }
}
```

Run in the project directory with Gradle and JDK 17+:

```bash
gradle run
```

With Gradle Wrapper, use `./gradlew run` on macOS/Linux or `gradlew.bat run` on Windows.

### 5.3. Verifiable Output

Fixed output lines of the program:

```text
match-good=true
match-wrong=false
ascii72-valid=true
ascii73-valid=false
unicode24-valid=true
unicode25-valid=false
emoji18-valid=true
emoji19-valid=false
invalid-unicode-valid=false
when-busy=BUSY
after-release=MATCH
```

Then the program prints **two live-measured lines** starting with `cost=10 samples=12` and `cost=11 samples=12`, each showing `p50-ms` and `p95-ms`. **There is no single fixed millisecond value**, as machines, OS, JVM, and background loads vary.

Explanation:

- `"A"` is one UTF-8 byte; `界` is three bytes; `😀` is four bytes and two UTF-16 code units. That is why `unicode25-valid=false` even though the Java `String` length is only 25.
- `invalid-unicode-valid=false` because `CharsetEncoder` uses `REPORT` instead of silently replacing broken surrogates with question marks.
- `when-busy=BUSY` is a **simulation** holding the permit beforehand; it proves the gate skips calling bcrypt when slots are exhausted, **not a concurrency load test**.
- `after-release=MATCH` proves the permit is released in `finally` and the verifier still works.
- `measure(...)` creates the hash before timing; the loop times `matches(...)` alone. With 12 samples, the p95 figure is only for learning how to measure, **insufficient** for deciding production SLOs/capacity.
- `GatedVerifier` is not yet a Spring Security filter/provider and has no per-account/IP rate limiting. It illustrates the boundary between **wrong password** and **server busy**.

Checking `input.length() > 72` is an **early reject**, because a valid UTF-16 code unit cannot require fewer than one UTF-8 byte. Conversely, `input.length() <= 72` does not guarantee `<= 72` bytes; `CharsetEncoder` must still run.

## 6. Preventing Resource Exhaustion: Control Layers Must Complement Each Other

### 6.1. Rate Limiting: Attempts Over Time

In practice you should have at least these quota types:

- **Per normalized account/username**, independent of source IP: limits brute force against one account from distributed networks.
- **Per IP/source/endpoint**, independent of username: limits one source trying passwords across many accounts.
- **Per entire endpoint/system** during spikes or automation signals; optionally add risk signals and MFA/passkeys.
- **Per action**: login, password change, recovery request, OTP verification, and password creation carry different costs and consequences.

Avoid a single bucket keyed only by **IP + username pair**: attackers can keep rotating pairs to get fresh quotas. Use Redis/gateway for distributed counters, with TTLs and fallback policies if the limiter dependency fails.

Per-account rate limiting, if poorly designed, can be abused to **deliberately lock out accounts**. Consider progressive delays, challenges, and unlock policies rather than permanently locking accounts after a few wrong tries. CAPTCHA is only a supporting layer, not a replacement for quotas.

### 6.2. Concurrency Cap: Hash Operations Running **Right Now**

A `Semaphore` or bounded worker pool controls concurrent `matches` calls:

```text
requests past quota
     |
     v
Admission gate (K slots)
     |                 \
     | permit free      \ no permit
     v                   v
PasswordEncoder        BUSY / 429 or 503 per policy
.matches(...)           DO NOT invoke bcrypt
     |
     v
release permit in finally
```

**Core rule:** when busy, never return `false` directly from `PasswordEncoder.matches(...)` masquerading as a wrong password. Doing so causes `DaoAuthenticationProvider` to treat system overload as `BadCredentialsException`, incrementing failed login counters, triggering lockouts, and polluting audit logs.

Place the gate at the HTTP/authentication service layer **before** calling `AuthenticationManager.authenticate(...)`, integrated with proper failure/entry-point semantics. Return controlled overload responses like 429/503 with appropriate retry/backoff. Never "fail open" for unauthenticated requests.

**Limitation of the demo's Semaphore:** it bounds only **one JVM instance**, without sharing cluster-wide quota. You need distributed rate limiters or upstream admission to prevent N instances from together exceeding total CPU/memory budgets.

### 6.3. Bounded Queues, Timeouts, and Load Shedding

When all K slots are busy, adding an **unbounded** queue accumulates requests, spiking RAM and latency; by the time they run, many clients have timed out. Prefer:

- Bounded queue length or **fail fast**.
- Finite wait time for a slot; never block request threads indefinitely.
- Bounded HTTP concurrent requests, connection pools, and server workers.
- Downstream DB/IdP timeouts and circuit breakers for external services.
- Distinct overload responses separate from authentication failures; clients retry with exponential backoff + jitter.
- Releasing permits in `finally` even on exceptions; do not rely on `Thread.interrupt` to immediately cancel an in-progress hash computation.

Placing admission after the DB lookup means rejected requests still hit the DB. Consider checking early at the endpoint before DB/hashing, while avoiding response differences revealing whether a username exists.

### 6.4. CPU and RAM Must Be Budgeted Separately

Suppose an **arithmetic example**, not a benchmark:

- `30 verifications/second` pass the rate limiter.
- Each operation averages `0.2 CPU-seconds`.
- Ideal compute demand: `30 × 0.2 = 6 CPU-core-seconds per second`, excluding DB/HTTP/GC.

A 4-core pod cannot sustain that CPU workload indefinitely without scaling or adjusting policy. Once saturated, queue wait grows and p95/p99 latency climbs rapidly.

With memory-hard algorithms, if each call needs 64 MiB RAM and 16 run concurrently, hashing alone can demand roughly **1 GiB**, before heap, request buffers, thread stacks, and overhead. These 64 MiB/16 figures illustrate the math, not a universal Argon2id default.

By Little's law in steady state:

```text
Average in-flight ≈ request rate × average time in system

Example:
20 requests/s × 0.25 s = 5 average requests in the system
```

This is **not** a formula to blindly pick `Semaphore(5)`. Queue times, CPU quotas, DB latency, burst peaks, and headroom targets must all be measured.

## 7. Choosing BCrypt Cost Through Controlled Benchmarking

Execution procedure:

1. Pick candidate costs matching security policy (e.g., 10, 11, 12) and a patched encoder version.
2. Prepare test accounts/hashes; never use production passwords or hashes.
3. Warm up the JVM and measure `matches` against **pre-generated** hashes, recording p50/p95/p99, sample count, and duration.
4. Run trials at rising concurrency levels in **authorized staging** to locate CPU saturation.
5. Measure HTTP end-to-end with real authentication filters, DB, rate limiters, network, and logging. Separate hashing CPU from DB wait.
6. Test legacy hashes across **multiple costs**, valid/invalid passwords, nonexistent usernames, overlong inputs, and failure paths.
7. Evaluate throughput, CPU throttling, heap/native RAM, GC, queue wait, error rates, p95/p99, and SLOs.
8. Select cost and in-flight cap K with headroom for peaks/bot spikes/autoscaling. Document benchmark setup (JDK, CPU, pod limits, algorithm, sample count, load).
9. After upgrading JDK/Spring Security/hardware, re-benchmark; never assume old numbers still hold.

Spring Security cites **roughly one second for verification** as a tuning guideline for work factors. OWASP likewise stresses avoiding overly slow hashes that invite DoS; there is no mandatory millisecond figure for every system. Final design depends on real risk and capacity, never defaulting to the maximum cost.

**`upgradeEncoding(...)` and migration:** raising cost only affects new hashes. For old hashes, verify first and then rehash from the verified password at the new cost when policy and transactions permit; never `encode(storedHash)`. With `DelegatingPasswordEncoder`, inspect `{id}`/cost so you do not report a meaningless combined latency.

## 8. When Should You Avoid Re-Hashing Passwords?

Spring Security advises that passwords are **long-term credentials**, and password verification is resource-intensive. Avoid forcing users to submit and verify passwords on **every API request** when the application can use secure sessions or short-lived tokens:

- Form login with `SecurityContext`/session: after authentication, requests with a valid session do not re-run bcrypt.
- OAuth2/OIDC and tokens: tokens verify via their own mechanism without calling `UserDetails.isCredentialsNonExpired` or BCrypt on every request.
- Stateless HTTP Basic: frequent requests may re-verify passwords; consider a better-suited credential model for high-frequency APIs.
- With MFA/passkeys, quotas and admission controls are still required on those verification paths, not only passwords.

**Never cache raw passwords, never cache `matches` results keyed by plaintext, and never store passwords in sessions to re-verify automatically.** If caching `UserDetails` containing hashes, understand credential erasure, invalidation, and TTLs. Caching a user differs from storing an authenticated `Authentication` in a session.

### Nonexistent Usernames and Timing

If the "username not found" path returns immediately while real users run bcrypt, timing differences can enable account enumeration. Some providers use a **dummy password hash** to reduce timing discrepancies; however, that also makes unknown-user attempts consume CPU.

Pair anti-enumeration **together with** rate limiting/admission; never drop timing defenses solely for throughput. Return generic messages for bad credentials while classifying overload, DB outages, and invalid inputs internally for operations.

## 9. Complete Testing: Boundaries, Concurrency, and Failures

### 9.1. Minimum Test Matrix

| Condition | What Must Be Proven |
| --- | --- |
| Right/wrong password | Correct authentication outcome; no hash leakage |
| 72/73 ASCII bytes | Accepted at boundary; rejected above boundary |
| 24/25 `界` characters | 72/75 UTF-8 bytes; does not rely on `String.length()` |
| 18/19 `😀` emojis | 72/76 bytes |
| Unpaired UTF-16 surrogate | Rejected |
| Empty/null or huge password | Expensive algorithm does not run; HTTP-layer body cap |
| Old/new bcrypt cost | Verifies using encoded hash's cost, not only bean cost |
| Malformed hash | Safe rejection; no plaintext fallback |
| Exhausted `Semaphore` slots | Returns BUSY/overload; does not count as bad credentials |
| Exception inside verifier | Permit is released via `finally` |
| One IP trying many usernames | Per-IP quota blocks it |
| Many IPs trying one username | Per-account quota blocks it |
| Burst beyond capacity | Bounded queue, fast response, never hangs indefinitely |
| Slow/failing DB or IdP | Clear timeout/circuit breaker/prioritization |
| Valid session/token | No wasteful repeated password hashing |

For Spring Security HTTP, write integration tests via `MockMvc` or real clients; testing with `@WithMockUser` **does not prove** BCrypt or `DaoAuthenticationProvider` ran, because it pre-populates the security context.

### 9.2. Concurrency Benchmarks Must Run in Staging

- Cold vs. warm JVM, single vs. multiple pods, run long enough to observe GC/CPU throttling.
- Step up load, recording p50/p95/p99, throughput, error rates, and queue wait; stop when hitting safety thresholds.
- Separate unknown usernames, wrong passwords, valid passwords, and legacy hashes; never merge into one histogram and claim "BCrypt takes X ms".
- Use JMH for microbenchmarks; run HTTP load tests in staging with proper tooling. Never run destructive load tests against production.
- Test overload and post-spike recovery: when load drops, queues must drain and permits must not leak.

### 9.3. Metrics and Auditing

Include a `password_verify_duration_seconds` histogram labeled by algorithm/cost (bounded label cardinality), a `hash_inflight` gauge, `auth_queue_wait_seconds`, CPU throttling, memory/GC, `auth_attempts_total` by outcome, rate-limit hits, 429/503 responses, and HTTP login p95/p99.

**Never** put raw passwords, stored hashes, Authorization headers, session cookies, usernames, emails, or IPs into **metric labels**. Investigative details belong in an access-controlled, redacted audit system with defined retention. Distinguish `bad_credentials` from `capacity_rejected` to avoid false account lockouts.

## 10. Common Mistakes

1. **Measuring one bcrypt verification** and publishing a fixed number.
2. **Measuring `encode+matches`** and calling it login verify latency.
3. **Skipping JVM warmup**, sample counts, p95/p99, and concurrency levels.
4. **Continuously raising cost** while CPU/queues are already saturated.
5. **Assuming a new bean cost upgraded all legacy hashes.**
6. **Using `String.length() <= 72`** to allow Unicode bcrypt passwords.
7. **Validating only on the frontend**, skipping backend/login checks.
8. **Truncating long passwords**, discarding part of the user's chosen secret.
9. **Leaving body/JSON/password size unbounded**, exhausting parser/memory before hashing.
10. **Writing complex password regexes** with catastrophic backtracking.
11. **Using only a per-IP limiter** without per-account quotas.
12. **Using only a per-account limiter**, letting one IP probe endless usernames.
13. **Bucketing only by IP+username**, granting each pair a fresh quota.
14. **Leaving in-flight hashing unbounded** while rate limiters still allow huge bursts.
15. **Unbounded queues or infinite semaphore waits**, pinning threads/memory.
16. **Returning false when the server is BUSY**, turning overload into bad passwords and false lockouts.
17. **Forgetting to release permits in `finally`**, gradually degrading the system.
18. **Picking large Argon2id memory costs without budgeting concurrent memory.**
19. **Hashing passwords on every request** despite valid sessions/tokens.
20. **Dropping timing/anti-enumeration defenses just to save CPU.**
21. **Relying on CAPTCHA as the sole defense** against login abuse.
22. **Putting usernames/IPs into metric labels**, causing high cardinality and data leaks.
23. **Load testing with production credentials**, creating security and availability risks.
24. **Failing to test overload, DB timeouts, unknown users, and legacy hashes.**
25. **Ignoring security advisories** for password-encoder libraries when upgrading.

## 11. Reinforcement Exercises

**Exercise A:** run the cost 10 and 11 demo, recording measured p50/p95 and JDK/CPU specs. Repeat several times to observe variance. Never turn a single measurement into a production SLO.

**Exercise B:** replace the test password with 72 ASCII bytes, 24 `界` characters, 18 `😀` emojis, 25 `界` characters, and a broken surrogate. Write unit tests explaining UTF-8 byte thresholds.

**Exercise C:** use JMH to measure `matches` in isolation, then run staging load tests at concurrency 1/4/8/16; compare p95/p99 and CPU utilization.

**Exercise D:** suppose 50 verifications/s at 0.15 CPU-seconds per verification. Compute ideal CPU demand and explain why headroom/DB/GC must be added before sizing pods.

**Exercise E:** extend `GatedVerifier` to count MATCH/MISMATCH/BUSY outcomes; verify BUSY does not increment bad-credentials counters. Trigger an exception and verify the permit is released.

**Exercise F:** design two independent per-account and per-IP quotas. Explain how they block one IP probing many users and many IPs probing one user.

**Exercise G:** given both cost-10 and cost-12 bcrypt hashes in the same DB with a cost-12 bean, measure per-account verification and propose safe verify-then-rehash.

**Exercise H:** assuming Argon2id at 64 MiB/hash, compute memory demand for 2/8/16 concurrent verifications. State the limits of this calculation and which metrics to monitor.

**Exercise I:** during an incident with 100% CPU, rising p99 login latency, and bot traffic, draft a runbook covering quotas/admission, queues, DB, throttling, autoscaling, auditing, and post-spike recovery. Never disable authentication or switch to `NoOpPasswordEncoder` to "reduce load".

### Completion Criteria

Learners can explain **verification cost**, the **72 UTF-8 byte** limit for bcrypt, the difference between per-account rate limiting and concurrency caps, why overload is not a wrong password, how to calculate CPU/RAM budgets, how to run reliable benchmarks, and how to avoid wasteful password hashing on every HTTP request.

## 12. References

- [Spring Security 6.5 — Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html): adaptive hashing, work factor, and why passwords are not verified on every request.
- [Spring Security 6.5.11 — BCryptPasswordEncoder](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/bcrypt/BCryptPasswordEncoder.html): `matches`, `encode`, `upgradeEncoding`, and cost.
- [Spring Security 6.5.11 — DelegatingPasswordEncoder](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/DelegatingPasswordEncoder.html): `{id}` and migration.
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): work factors, BCrypt 72-byte limit, Argon2id, and exhaustion risks.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): login throttling, generic errors, account lockout, and MFA.
- [OWASP — Credential Stuffing Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html): protecting against automated credential testing traffic.
- [Spring Security — CVE-2025-22228](https://spring.io/security/cve-2025-22228/): overlong bcrypt password verification issue in older releases.
- [Java 17 — CharsetEncoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetEncoder.html): validating Unicode with `CodingErrorAction.REPORT`.
- [OpenJDK JMH](https://github.com/openjdk/jmh): JVM microbenchmarking framework.

Measurements in examples must come from **real runs on your own environment**; this lesson does not claim production benchmarks. For Spring Security 7 or custom password encoders, verify the API and input limits of the exact implementation before adoption.
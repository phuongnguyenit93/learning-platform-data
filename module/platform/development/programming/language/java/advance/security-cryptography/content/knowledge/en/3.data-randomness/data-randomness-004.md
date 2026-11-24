# 3.4. The Role of Entropy; Distinguishing SecureRandom from Random and ThreadLocalRandom

## Learning Objectives

By the end of this lesson, you will understand what **entropy** is and why a generator that "looks random" can still be predictable; know how to distinguish `java.util.Random`, `java.util.concurrent.ThreadLocalRandom`, and `java.security.SecureRandom`; pick the right API for secrets/tokens, salts, IVs/nonces, simulations, and multi-threaded workloads; and use Java 17+ to generate random data safely for each purpose.

This lesson covers **data and randomness in Java security-cryptography**. Calling the right generator is a foundation of security, yet it does not replace encryption, key management, authentication, rate limiting, or access control checks.

## 1. Why "Random" Does Not Automatically Mean "Secure"

A game needs fair dice. A server needs a reset token that an attacker cannot guess, even after observing many other tokens. Both problems want a random-looking distribution, yet the second carries an adversarial unpredictability requirement.

Suppose a program emits the sequence `8, 1, 6, 3, 7, 2`. Looking only at those six numbers, you cannot tell whether they came from a physical source, a fixed-seed PRNG, or a hardcoded list. **Superficial statistics are insufficient to establish cryptographic security.** When an adversary knows the algorithm or can guess the seed/state, the sequence can be completely predictable even with a clean histogram.

Terminology:

| Concept | Meaning | Pitfall |
| --- | --- | --- |
| **Entropy** | Uncertainty of a data source, directly tied to how hard a value is to guess | Character count and buffer size do not directly indicate entropy |
| **Entropy source** | Genuine source of unpredictability, usually collected and conditioned by the OS/platform | Timestamp, PID, hostname, or `System.nanoTime()` do not guarantee unpredictability |
| **Seed** | Initial input data used to initialize a generator's state | A 256-bit seed derived from a timestamp is still easy to brute-force |
| **PRNG** | Pseudo-random number generator: deterministic algorithm producing many values from a seed/state | A fairly uniform distribution does not imply unpredictability |
| **CSPRNG/DRBG** | PRNG designed for cryptography; output bits must be unpredictable while internal state stays secret | Still depends on seeding, provider, state handling, and reseed policy |
| **Salt** | Value differing across hashes/derivations, usually public | A salt does not replace a cost-tuned KDF/password hash |
| **Nonce/IV** | Value used in a cryptographic operation; requires uniqueness/unpredictability depending on algorithm | In AES-GCM, reusing a nonce with the same key is a severe flaw |
| **Secret token** | Value conferring authority/authentication | Must be **unpredictable**, kept secret, with TTL/rotation/revocation |

### 1.1. Min-Entropy: The Right Lens for an Adversary Guessing Values

For a random variable `X`, min-entropy is defined by the probability of the **most likely value**:

```text
H_min(X) = -log₂(max_x P[X = x])
```

If a generator always returns the same number, `H_min = 0 bits`. If a six-digit code is chosen uniformly from `000000` to `999999`, the space has one million values and maximum min-entropy is roughly `log₂(1_000_000) = 19.93 bits`. This explains why six-digit OTPs must combine attempt limits, short lifetimes, anti-replay, and transport protection.

An ideal 32-byte random token holds **256 bits** of unpredictable data when drawn from an appropriate source. However, **32 bytes of output do not prove 256 bits of fresh entropy were collected per call**: many CSPRNGs use cryptographic algorithms to expand a secret seed/state into many bytes. Security relies on the initial seed, DRBG design, and environment.

SHA-256 hashing a timestamp produces a 256-bit *output*, yet adds zero bits of entropy if the timestamp is predictable. Base64/hex encoding only changes display format without adding uncertainty. Generating 256 characters from `Random(42)` still has a known seed.

### 1.2. From Entropy to Random Numbers in the Application

```text
OS/entropy source
      │ evaluates and conditions source
      ▼
secret seed (strength depends on real entropy)
      │ initializes
      ▼
security provider's CSPRNG / DRBG
      │ generates nextBytes(...)
      ▼
bytes for tokens, salts, keys, nonces...
```

This diagram is conceptual, not a guarantee that every JDK uses the exact same algorithm or OS interface. A DRBG may continue generating numbers from cryptographic state between reseeds rather than "reading 32 bytes of physical entropy" on every `nextBytes(32)`. That does **not** make it inherently insecure.

Separate two questions: *is the entropy source unpredictable?* and *is the seed-expansion algorithm cryptographically designed?* Running a few simple statistical tests on a sequence cannot replace evaluating both layers.

## 2. Comparison Table of the Three Main APIs

| Property | `Random` | `ThreadLocalRandom` | `SecureRandom` |
| --- | --- | --- | --- |
| Package | `java.util` | `java.util.concurrent` | `java.security` |
| Purpose | Simulations, general random data, reproducible tests | Fast pseudo-random numbers for multi-threaded work | Unpredictable data for security use |
| Nature | In Java 17, `Random` uses an LCG with a 48-bit seed | Per-thread generator optimized for concurrency | Engine via security provider's `SecureRandomSpi`; may be a DRBG |
| Instantiation | `new Random()`, `new Random(42L)` | `ThreadLocalRandom.current()` | `new SecureRandom()` |
| Fixed seed | Same seed + same call sequence → same sequence | Custom seeding via `setSeed` unsupported | Never use weak or fixed seeds in production |
| Concurrency | Thread-safe, yet shared instance can face contention | Designed to reduce contention across threads | Thread-safe; throughput depends on provider/algorithm |
| Cryptographically unpredictable? | **No** | **No** | **Yes**, with secure implementation and seed |
| Tokens/secrets/API keys | **Do not use** | **Do not use** | **Use** with proper length, lifecycle, and storage |
| Appropriate use cases | Games, unit tests, simulations | Parallel simulations, sampling, non-secret jitter | Tokens, salts, IVs/nonces, secret material |

**Selection rule:** if guessing the next number compromises access, leaks secrets, or breaks protocol soundness, use `SecureRandom` or an appropriate cryptographic API. If you only need numbers for load distribution, games, or tests, `Random` and `ThreadLocalRandom` are usually a better fit.

### 2.1. `Random`: Reproducibility Is Both a Feature and a Limit

JDK 17 specifies that `Random` uses a 48-bit seed and a linear congruential formula (LCG). Two instances initialized with the same seed and invoked with the same method sequence return identical results. That enables **reproducible simulations**, yet cannot stop an adversary from deducing the state.

```java
import java.util.Random;

Random a = new Random(2026L);
Random b = new Random(2026L);
boolean same = a.nextInt(1_000) == b.nextInt(1_000);
// same is true because of the same seed and same calls.
```

This is an illustrative snippet meant for inside a method; a standalone runnable example is in Section 6. `new Random()` chooses a seed itself, yet still **provides no cryptographic security guarantee**. `Math.random()` must likewise never be used to create secrets.

`Random` instances are thread-safe, though multiple threads sharing one instance can contend on state and reduce throughput. Optimizing performance leads to `ThreadLocalRandom`; optimizing security requires `SecureRandom`.

### 2.2. `ThreadLocalRandom`: Reduces Contention, Adds No Security

Usage:

```java
import java.util.concurrent.ThreadLocalRandom;

int number = ThreadLocalRandom.current().nextInt(10, 20);
// Number in [10, 20); exact value is not fixed.
```

Whenever a number is needed in the current worker/thread, call `ThreadLocalRandom.current()` on that thread. Never capture thread A's generator and pass it to thread B. This class's `setSeed(long)` API always throws `UnsupportedOperationException`; if parallel tests require reproducible seeds, design explicit per-stream generators.

Common misconception: setting `java.util.secureRandomSeed=true` may alter the initial seed source, yet **does not turn `ThreadLocalRandom`'s algorithm into a CSPRNG**. Its purpose remains performance and non-cryptographic distribution.

Use it for parallel simulations, non-secret random delays/jitter, sampling, or synthetic test data. Never use it for reset tokens, passwords, keys, security-critical nonces, or session IDs.

### 2.3. `SecureRandom`: The Engine Built for Cryptography

`SecureRandom` extends `Random` in Java's class hierarchy, yet **does not use `Random`'s 48-bit LCG algorithm for cryptographic output**. It delegates to the security provider's implementation:

```java
import java.security.SecureRandom;

SecureRandom secure = new SecureRandom();
byte[] bytes = new byte[32];
secure.nextBytes(bytes);
```

`new SecureRandom()` selects a provider/algorithm based on runtime configuration. You may print `secure.getAlgorithm()` and `secure.getProvider().getName()` for diagnostics, yet avoid hardcoding provider names across all machines.

`SecureRandom` guarantees thread safety at the API level: the provider implementation may be internally thread-safe, or the JDK synchronizes calls. **Thread-safe does not mean identical throughput**; depending on provider, reseeding, and entropy source, cost can vary.

## 3. `SecureRandom` Seeding and Lifecycle: The Easiest Place to Go Wrong

### 3.1. Self-Seeding

When a `SecureRandom` created with the default constructor is first used to generate bytes, the provider typically obtains a suitable entropy source automatically. Your application only needs:

```java
SecureRandom secure = new SecureRandom();
byte[] token = new byte[32];
secure.nextBytes(token);
```

**Do not "help" it with a timestamp or constant.** Per Java 17 documentation, for a PRNG-based `SecureRandom`, calling `setSeed` **before the first `nextBytes` or `reseed`** can suppress self-seeding. The caller then becomes responsible for supplying sufficient seed entropy.

```java
// WRONG in production: timestamp can be guessed!
SecureRandom insecure = new SecureRandom();
insecure.setSeed(System.currentTimeMillis());
byte[] secret = new byte[32];
insecure.nextBytes(secret);
```

The snippet above is **an example for recognizing a bug**, not an initialization guide. Similarly, `new SecureRandom(new byte[] {1, 2, 3})` with a fixed seed is not a safe way to generate tokens.

### 3.2. Related APIs and Usage Boundaries

For ordinary secret material, instantiate `SecureRandom` so the provider self-seeds and call `nextBytes(byte[])`. `generateSeed(int)` supplies seed material using the provider's mechanism, not as a mandatory step before `nextBytes`. `setSeed(...)` mixes caller-supplied bytes; calling it with a timestamp or weak seed before self-seeding can destroy unpredictability. `reseed()` requests fresh entropy, yet may be unsupported or wait on the entropy source.

`getInstanceStrong()` selects per the `securerandom.strongAlgorithms` security property, whereas `getInstance("DRBG")` requests a DRBG engine if supported by a provider. Neither automatically guarantees better speed or non-blocking behavior. Lesson 3.5 dives deeper into seeding/reseeding and Lesson 3.6 analyzes DRBGs, strong configuration, and latency benchmarking; here, simply remember: **choose `SecureRandom` for secrets, mind entropy, and never self-seed with predictable values**.

### 3.3. Sharing Instances and Measuring Performance

`SecureRandom` supports concurrent use across threads; a properly initialized instance can be shared. Do not recreate instances repeatedly thinking "each constructor adds fresh entropy." If an application generates huge numbers of tokens, measure latency/throughput against the real provider and OS to isolate initialization/locking costs before optimizing.

**Never** replace `SecureRandom` with `ThreadLocalRandom` merely for speed when output must stay secret. Also do not confuse "many threads" with "many independent entropy sources": thread confinement is a performance tactic, whereas cryptographic unpredictability is a security property.

## 4. Applying Entropy: Tokens, Keys, Salts, Nonces, and OTPs

| Need | What to choose | Rationale and accompanying conditions |
| --- | --- | --- |
| Session ID, API key, reset token, bearer token | `SecureRandom.nextBytes`, Base64URL/hex encoded | Must resist guessing, kept secret, with TTL, rotation, revocation, authorization |
| Random CSRF token | `SecureRandom` / standard security framework | Not a predictable pseudo-random integer |
| AES/HMAC secret key | `KeyGenerator` or proper cryptographic key generation | Must manage storage, lifecycle, rotation, and access control |
| Password hashing salt | `SecureRandom`, unique salt per record | Salt is typically public; must use standard KDF/password hash with proper cost |
| AES-GCM nonce/IV | Workflow guaranteeing **no key–nonce pair reuse** | Can be 12 random bytes within safe limits or a managed counter |
| 6-digit OTP | `SecureRandom.nextInt(1_000_000)` | Only 1 million possibilities: needs TTL, rate limits, anti-replay, attempt lockout |
| Simulation/game/test | `Random(seed)` when reproducibility is needed | No secrecy requirement |
| Parallel simulation/backoff | `ThreadLocalRandom.current()` | Reduces contention, never for secrets |
| Public ID | ID strategy meeting uniqueness, collision, and scale needs | Public IDs do not grant authority; never substitute ID secrecy for authorization |

### 4.1. A Long Token Does Not Mean High Entropy

32 ideal random bytes = 256 bits of data, which encodes in **unpadded Base64URL** to 43 characters. **Those 43 characters do not create 43 × 6 bits of new entropy.** If the seed is weak or the token leaks via logs, URLs, cookies/storage, or analytics, a long string will not save it.

Real-world tokens must travel over HTTPS, usually have expiration, replay protection, and revocation. When verifying bearer tokens, store/handle tokens securely (e.g., storing an appropriate digest to reduce plaintext token exposure on the server) and rate-limit attempts as needed. Never treat a token as just a "random integer."

### 4.2. Salts and Nonces Differ from Secret Keys

**Salt:** generated uniquely per account/derivation to defeat precomputed tables and prevent two users with the same password from producing identical hashes under the same parameters. Salts need not be secret and can be stored alongside the password hash. Never hand-roll `SHA256(password + salt)` instead of a strong KDF.

**Nonce/IV:** constraints depend on the algorithm. For AES-GCM, a 96-bit nonce is standard; encrypted messages require a **unique nonce under the same key**. If generated from 12 bytes of `SecureRandom`, collision probability grows with message count; enforce usage limits or use a nonce-management scheme suited to data volume. **`SecureRandom` is not a proof that random nonces can never collide.**

**Keys:** must be secret, match algorithm strength, and follow storage/rotation policy. Never hash a timestamp or user password into a raw AES key and treat it as 256 bits of entropy. When the input is a password, use a standard password-based KDF with salt and cost.

### 4.3. Why Is `nextInt(bound)` Better Than Modulo?

To draw a bounded integer, use `secure.nextInt(1_000_000)` for the range 0..999999. Avoid `secure.nextInt() % 1_000_000`, which can be negative and introduces modulo bias. The JDK's bounded method handles unbiased range selection per the API.

Six-digit OTP example:

```java
import java.security.SecureRandom;
import java.util.Locale;

SecureRandom secure = new SecureRandom();
int number = secure.nextInt(1_000_000);
String otp = String.format(Locale.ROOT, "%06d", number);
```

This is an **illustrative snippet inside a method**, not a full program. An OTP can start with `0`; preserve string formatting and pair it with TTL, max retry count, and single-use enforcement.

## 5. Choosing the Right API in Common Scenarios

**A. Reproducible Monte Carlo tests.** Use `Random` with a fixed seed and controlled call ordering; do not use `SecureRandom` only to make tests non-deterministic and hard to reproduce. Modern simulations may also evaluate PRNGs in `java.util.random` (Java 17), yet **the `RandomGenerator` interface does not automatically guarantee cryptographic security**.

**B. Multiple workers doing non-security sampling.** Call `ThreadLocalRandom.current()` inside each worker to cut contention. Do not force `ThreadLocalRandom.setSeed`; if parallel tests need exact repeatability, design explicit per-stream seeded PRNGs.

**C. API server issuing reset tokens.** Use `SecureRandom.nextBytes` with sufficient length; encode for transport; store and compare safely; expire promptly, enforce single use, and avoid logging tokens.

**D. Generating IVs for AES-GCM.** May use 12-byte `SecureRandom` within ciphertext-count limits; design against reuse under the same key. Randomness does not replace the uniqueness invariant.

**E. Issuing 6-digit PINs/OTPs.** Pick `SecureRandom`, yet because the possibility space is small, require rate limiting, TTL, retry limits, lockout/risk controls, and anti-replay. Never assume a secure generator alone suffices.

**F. Generating UUIDs.** Java's `UUID.randomUUID()` uses a strong random source for UUID v4, giving 122 random bits after version/variant bits. It fits many identifier needs, yet does not automatically satisfy 256-bit token requirements or replace authorization checks.

## 6. Standalone Java 17+ Program

Create **`EntropyRandomDemo.java`**. The program demonstrates all three APIs while **printing only deterministically verifiable results**, never printing secret tokens or salts.

```java
import java.security.SecureRandom;
import java.util.Base64;
import java.util.Random;
import java.util.concurrent.ThreadLocalRandom;

public final class EntropyRandomDemo {
    private static final SecureRandom SECURE = new SecureRandom();

    private EntropyRandomDemo() {
        // Utility class for the example.
    }

    private static String newToken() {
        byte[] bytes = new byte[32];
        SECURE.nextBytes(bytes);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }

    public static void main(String[] args) {
        // Same Random seed and calls -> reproducible sequence.
        Random first = new Random(2026L);
        Random second = new Random(2026L);
        boolean sameSequence = true;
        for (int i = 0; i < 10; i++) {
            if (first.nextInt(1_000) != second.nextInt(1_000)) {
                sameSequence = false;
            }
        }

        // Efficient per-thread generator for non-security tasks.
        int sample = ThreadLocalRandom.current().nextInt(10, 20);
        boolean validRange = sample >= 10 && sample < 20;

        // Cryptographic generator for sensitive random bytes.
        byte[] salt = new byte[16];
        SECURE.nextBytes(salt);
        String token = newToken();
        byte[] decoded = Base64.getUrlDecoder().decode(token);

        System.out.println("randomRepeatable=" + sameSequence);
        System.out.println("threadLocalRangeValid=" + validRange);
        System.out.println("saltBytes=" + salt.length);
        System.out.println("tokenBytes=" + decoded.length);
        System.out.println("tokenChars=" + token.length());
    }
}
```

Compile and run from the directory containing the file:

```shell
javac EntropyRandomDemo.java
java EntropyRandomDemo
```

Expected stdout:

```text
randomRepeatable=true
threadLocalRangeValid=true
saltBytes=16
tokenBytes=32
tokenChars=43
```

Explanation:

- `randomRepeatable=true` because two `Random` instances share the same seed and call sequence; no hardcoded integer output is asserted.
- `threadLocalRangeValid=true` because `nextInt(10, 20)` returns a value in `[10, 20)`; the program does not require fixed generator output.
- The actual salt is 16 bytes and the raw token is 32 bytes; unpadded Base64URL of 32 bytes yields a 43-character string.
- `SecureRandom` generates fresh bytes without a caller-supplied seed. Secret bytes are never printed and random outputs are never asserted as fixed stdout.
- This example only shows data generation; it does not include password hashing, AES-GCM encryption, or a complete authentication system.

## 7. Pairing `SecureRandom` with Standard Cryptographic APIs

When an **AES key** is needed, prefer Java Cryptography Architecture's `KeyGenerator` instead of inventing custom byte-packing schemes:

```java
import java.security.SecureRandom;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

SecureRandom secure = new SecureRandom();
KeyGenerator generator = KeyGenerator.getInstance("AES");
generator.init(256, secure);
SecretKey key = generator.generateKey();
```

This snippet is **not standalone**; place it inside a method that declares `throws Exception` or handles checked exceptions, with the imports shown. Standard Java 17 supports 256-bit AES keys; specific providers/policies may still impose conditions. Never log keys, and ensure secure storage/rotation.

For AES-GCM, a nonce can be generated like this:

```java
byte[] nonce = new byte[12];
secure.nextBytes(nonce);
// Use nonce only once under the same key when encrypting with AES-GCM.
```

The lines above reuse `secure` from the prior snippet. Managing uniqueness, invocation limits, and key protection cannot be replaced by assuming "random nonces will definitely never collide."

Note: `SecureRandom` is the data source; `KeyGenerator`, `Cipher`, `Mac`, and `Signature` are engines consuming that data according to their protocol/algorithm. Never pass a standard non-cryptographic generator to security engines requiring unpredictability.

## 8. Operational Concerns: Providers, Blocking, and Proper Inspection

To inspect what the runtime uses, create standalone **`SecureRandomInfo.java`**:

```java
import java.security.SecureRandom;
import java.security.Security;

public class SecureRandomInfo {
    public static void main(String[] args) {
        SecureRandom rng = new SecureRandom();
        System.out.println("Algorithm: " + rng.getAlgorithm());
        System.out.println("Provider: " + rng.getProvider().getName());
        System.out.println("Strong candidates: " +
                Security.getProperty("securerandom.strongAlgorithms"));
    }
}
```

Run:

```shell
javac SecureRandomInfo.java
java SecureRandomInfo
```

**Stdout varies across JDKs, operating systems, and provider configurations**, so do not fabricate a fixed algorithm/provider name. Verify an up-to-date JDK, entropy policy, provider behavior, compliance requirements, and latency/throughput measured in the real environment.

For containers/VM snapshots, replicated deployments, and HSM rules, build a threat model covering entropy sources and generator state. Never substitute seeds like container ID, hostname, or timestamp. Providers may restrict algorithms, control reseeding, and lock; evaluate them from documentation and measurement rather than assuming `getInstanceStrong()` is always better.

## 9. Common Mistakes to Avoid

| Mistake | Why it is wrong | Fix |
| --- | --- | --- |
| `new Random(System.currentTimeMillis())` for reset tokens | Seed/time is guessable, algorithm is predictable | Use `SecureRandom` |
| `Math.random()` converted to hex for API keys | No cryptographic security guarantee | Generate sufficient random bytes with a CSPRNG and encode |
| `ThreadLocalRandom` for session IDs | Per-thread and fast does not mean secure | Use `SecureRandom` / security framework |
| `SecureRandom.setSeed(42L)` before `nextBytes` | Weak seed, may suppress self-seeding | Let the provider self-seed |
| `new SecureRandom(new byte[]{1,2,3})` | Known seed, lacks entropy | Use default constructor and standard entropy source |
| Calling `getInstanceStrong()` per request | Can add overhead/blocking without proving superiority | Choose provider by policy and benchmark |
| Manually applying `x % n` | Can introduce bias and negative values | Use `nextInt(n)` with `n > 0` |
| Truncating a 256-bit token to a few characters | Shrinks the guessing space | Keep full designed byte/bit length |
| Checking "two random tokens differ" as proof of entropy | Non-zero collision probability; short tests prove nothing about security | Test shape/contract and evaluate RNG properly |
| Infinite random AES-GCM nonces under one key | Collision probability rises with encryption count | Manage unique nonces and enforce key limits/rotation |
| Logging tokens, keys, seeds, or salts with passwords | Leaks sensitive data, defeats unpredictability | Log minimal metadata, protect credentials |
| Treating public IDs as authorization tokens | Guessable ID does not mean authorized access | Enforce independent authorization; bearer tokens must be unpredictable |

### How to Test Properly

For `Random(seed)` used in simulations, tests can assert deterministic output sequences and seed stability. For `SecureRandom`, test the contract: raw byte length, Base64URL round-trip, character set, expiration/revocation workflows, and secret protection. Never assert a fixed token or treat a couple of bit-count checks as proof of entropy source quality.

If token-issuance logic needs reproducible tests, design an input interface/adapter for tests while keeping the production path on properly initialized `SecureRandom`. In particular, never let a "test seed" slip into production through misconfigured environment variables.

## 10. Summary as Practical Decisions

- **Need randomness for simulation and repeatability?** `Random(seed)`.
- **Need speed and low contention in non-security parallel work?** `ThreadLocalRandom.current()`.
- **Need randomness others cannot guess?** `SecureRandom` or standard cryptographic APIs backed by a CSPRNG.
- **Need keys, salts, tokens, nonces?** Pick the right primitive and its specific invariant: keys must stay secret, salts should be unique per record, tokens need TTL/anti-replay, and nonces need algorithm-specific uniqueness.
- **Need higher "entropy"?** Examine the **source**, seed, and provider initialization; never hash timestamps, add Base64 layers, or call `setSeed` with constants.
- **Need to assess strength?** Use a threat model and verify entropy source and algorithm; output statistical checks alone cannot prove cryptographic security.

Four self-check questions:

1. Why does `new Random(123L)` produce the same sequence across runs, and why is that good for tests yet bad for tokens? **Answer:** Deterministic algorithm from seed; repeatability helps testing, yet attackers can predict output.
2. Is a 6-digit OTP generated by `SecureRandom` completely secure on its own? **Answer:** No, because there are only one million possibilities; you must enforce attempt limits, expiration, anti-replay, and channel protection.
3. Why is `SecureRandom.setSeed(System.nanoTime())` before the first `nextBytes` dangerous? **Answer:** Time is predictable and it can bypass proper automatic seeding.
4. Why does using `ThreadLocalRandom` across 100 threads not equal having 100 CSPRNGs? **Answer:** Per-thread design solves contention, without providing cryptographic unpredictability.

## References

- [Java SE 17 – SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): self-seeding, `setSeed`, `reseed`, `getInstanceStrong`, thread safety, and potential blocking.
- [Java SE 17 – Random](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html): 48-bit seed, LCG, reproducibility, and non-security warning.
- [Java SE 17 – ThreadLocalRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html): per-thread usage, unsupported `setSeed`, and use cases.
- [Java SE 17 – RandomGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html): common interface since Java 17; implementations are not CSPRNGs by default.
- [NIST – Full Entropy Assumption of SP 800-90](https://www.nist.gov/publications/discussion-full-entropy-assumption-sp-800-90-series): role of entropy and min-entropy in evaluating random number generators.
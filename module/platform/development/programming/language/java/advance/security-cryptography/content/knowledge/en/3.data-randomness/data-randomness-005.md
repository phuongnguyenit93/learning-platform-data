# 3.5. Generating Random Bytes, Seeding, Reseeding, and the Impact of Predictable Seeds

In the **Java Advance – Security & Cryptography** module, "randomness" is often a security primitive: session login tokens, recovery codes, keys, salts, nonces/IVs, or challenges. A program can generate 32 bytes that look completely random, yet if the initial state comes from a **predictable seed**, an adversary can narrow down the possibilities to a searchable space. This lesson uses **Java 21** to distinguish entropy sources, PRNG state, initial seeding, and reseeding, then demonstrates proper `SecureRandom` usage.

## Objectives

After this lesson, you will be able to:

1. Generate unpredictable byte arrays using `java.security.SecureRandom` and encode them into strings when needed.
2. Explain **entropy → seed/state → byte generation → reseed** without confusing "output length" with "actual secrecy."
3. Understand when `SecureRandom` self-seeds and the effects of `SecureRandom(byte[])`, `setSeed(...)`, `generateSeed(...)`, and `reseed()`.
4. Explain why timestamps, sequence numbers, PIDs, usernames, hardcoded seeds, or overly small seeds are dangerous if used as the sole source for secrets.
5. Recognize provider limits, use DRBG in Java 21 when explicit reseed policies are needed, and distinguish random **tokens**, **salts**, and **nonces** from **key** generation.
6. Test properly: verify lengths, formats, operational readiness, and entropy sources; never equate a few "distinct" samples with proof of cryptographic security.

## 1. The Nature of Randomness in Security Applications

A computer executes largely deterministic operations. Therefore, many random number generators are built as **pseudorandom generators**: algorithms that expand an initial state into a random-looking byte sequence. Given enough of the state and the algorithm, that sequence can be reproduced; security depends first on the **unpredictability of the initial state** and the quality of the generator.

Conceptual diagram:

```text
OS / device entropy source
                    |
         Sufficiently strong initial seed
                    |
     Cryptographically designed PRNG/DRBG
                    |
         nextBytes(...) -> byte[]
                    |
     Periodic / policy-driven reseed
     with fresh entropy (if supported)
```

**Concepts to distinguish:**

| Concept | Meaning | Key takeaway |
| --- | --- | --- |
| Random bytes | Output byte array from a generator | Random bytes can contain `0x00` or negative values when read as signed `byte`; they are not UTF-8 strings. |
| Seed | Data initializing or augmenting PRNG state | Seed length alone does not indicate its entropy. |
| Entropy | Uncertainty of information to an adversary | A 256-bit representation can still carry only a few unpredictable bits. |
| CSPRNG | Cryptographically suitable pseudorandom generator | Outputs must be unpredictable even if the adversary knows the algorithm. |
| DRBG | A class of CSPRNG based on a deterministic algorithm and initial entropy | May support output limits, reseeding, and prediction resistance. |
| Reseed | Refreshing/supplementing state from fresh entropy via the provider | Not the same operation as fixing a seed to reproduce output. |
| Token/salt/nonce | Values with distinct requirements | Tokens need unpredictability; salts usually need uniqueness and randomness; AEAD nonces require **no reuse with the same key**. |

Entropy limit example: if a seed is merely one of **1,000 timestamp values** that an adversary can bracket, it cannot be treated as "256-bit secrecy" simply because the program hashes the timestamp with SHA-256 to get 32 bytes. A value computed deterministically from 1,000 possibilities still has at most 1,000 states—less than 10 bits of uncertainty. **Hashes and PRNGs do not create new secret entropy from predictable inputs.**

## 2. Pick the Right API Before Talking About Seeds

When data has no security requirement, `Random(seed)` is useful for reproducible experiments, `ThreadLocalRandom.current()` reduces contention across threads, and `SplittableRandom` serves parallel computation/simulation. Those APIs **do not guarantee unpredictability**; `Math.random()` is also unsuitable for tokens or keys.

When you need tokens, salts, nonces, or secret material, use a properly configured `java.security.SecureRandom`; for **keys**, prefer algorithm-specific `KeyGenerator`/`KeyPairGenerator`. The standard usage pattern is:

```java
SecureRandom random = new SecureRandom();
byte[] bytes = new byte[32];
random.nextBytes(bytes);
```

This snippet requires `import java.security.SecureRandom;`. The remainder of this lesson focuses not on re-comparing the whole generator family, but on explaining **self-seeding, the impact of caller-supplied seeds, and proper reseeding when supported by the provider**.

## 3. Full Practice: Generating 32 Bytes for a Token

Create **`SecureBytesDemo.java`**:

```java
import java.security.SecureRandom;
import java.util.Base64;

public class SecureBytesDemo {
    public static void main(String[] args) {
        SecureRandom random = new SecureRandom();

        byte[] token = new byte[32];
        random.nextBytes(token);

        // Convert binary bytes to a string suitable for URLs/cookies.
        String encoded = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(token);

        // Print sizes only: do not log the secret token.
        System.out.println("Byte count: " + token.length);
        System.out.println("Bit count: " + token.length * 8);
        System.out.println("Base64url chars: " + encoded.length());
    }
}
```

Verify JDK 21 with `java -version` and `javac -version`; in the file's directory, run:

```text
mkdir out
javac --release 21 -encoding UTF-8 -d out SecureBytesDemo.java
java -cp out SecureBytesDemo
```

Output for the program above:

```text
Byte count: 32
Bit count: 256
Base64url chars: 43
```

**Why?** `nextBytes(byte[])` fills 32 binary bytes. 32 × 8 = 256 **bits of output data**; actual security still depends on seed and provider. Unpadded Base64url encodes exactly 32 bytes into 43 characters; Base64 itself **does not encrypt secrets**, it only converts representation. The token value differs across runs, so there is no fixed token stdout.

**Do not do the following:**

- Do not call `new String(token, UTF_8)` to "turn random bytes into text": many byte sequences are invalid UTF-8 and may undergo byte substitution on decoding.
- Do not expose real tokens in logs, exceptions, metric labels, unprotected URLs, or debug screenshots.
- Do not use `Random.nextBytes` or `UUID.randomUUID()` interchangeably for every type of secret by intuition. Version 4 UUIDs have a different format and random bit count than 32-byte tokens; choose tokens based on threat model, length, storage, and protocol.
- Do not treat printing "two different tokens" as a cryptographic verification test. A weak source can also produce very different-looking strings.

A `SecureRandom` instance can be **reused**; Java 21 documents that this API is safe for concurrent calls from multiple threads (providers declared thread-safe are used directly, or a wrapper synchronizes engine access). Still, throughput and potential blocking while waiting for entropy depend on the implementation; benchmark in the deployment environment under high load.

## 4. How Is the Initial Seed Created?

For a PRNG-based `SecureRandom`, the Java 21 Javadoc explains:

- Instantiating via `new SecureRandom()` or `SecureRandom.getInstance(...)` typically **does not immediately gather a full seed**. The first `nextBytes(...)` call triggers the PRNG to self-seed from an implementation-defined entropy source, **unless `setSeed(...)` was called beforehand**.
- `new SecureRandom(byte[] seed)` constructs an instance with a caller-supplied seed. If that seed is the sole source and is guessable, output unpredictability can be broken. Exact behavior depends on the provider.
- `random.setSeed(byte[])` or `random.setSeed(long)` supplies caller seed input. Per Java documentation, on an already-seeded state, the new seed **supplements** rather than replaces the prior seed. However, if called before the first self-seeding, you cannot rely on the default automatic entropy gathering.
- `setSeed(long)` accepts only a 64-bit `long`; passing timestamps, counters, PIDs, or constants further restricts the potential state space.

### Comparing Four Initialization Patterns

| Pattern | Assessment | Why |
| --- | --- | --- |
| `new SecureRandom(); random.nextBytes(out);` | **Recommended default** | Provider automatically uses an appropriate entropy source. |
| `SecureRandom.getInstance("DRBG"); ...` | Reasonable when runtime has DRBG and you need DRBG config/inspection | Must verify service/provider availability. |
| `new SecureRandom("known".getBytes(UTF_8));` | **Dangerous** if the guessable seed is the sole entropy source | Known seed or tiny search space. |
| `SecureRandom r = new SecureRandom(); r.setSeed(System.currentTimeMillis()); r.nextBytes(out);` | **Avoid** | Predictable timestamp; calling `setSeed` before self-seeding can skip default entropy gathering. |

A 32-byte seed made from repeated characters or zeros is still weak. Conversely, after a provider **has already safely self-seeded**, calling `setSeed(123)` does not mean the entire state inevitably becomes predictable: the method mixes into existing state. Even so, doing this **adds no reliable security benefit** and causes confusion in audits; avoid manual seeding without a reviewed, intentional design reason.

**Order sensitivity:** `new SecureRandom(); setSeed(weak); nextBytes(out)` differs from `new SecureRandom(); nextBytes(out); setSeed(weak)` regarding when self-seeding occurs. Do not assume every provider shares the same algorithm or identical byte output for a seed, yet **never entrust secret security to a predictable seed source**.

### Distinguishing `nextBytes`, `generateSeed`, and `getSeed`

| Method | Source and purpose |
| --- | --- |
| `nextBytes(byte[])` | Obtains random bytes from the current generator for application use. This is the normal choice. |
| `generateSeed(int)` | Obtains seed bytes using the implementation's seed-generation algorithm; useful for seeding **another** generator when explicitly required. Can be expensive or block. |
| `SecureRandom.getSeed(int)` | Static method fetching seed bytes via the seed-generation mechanism; rarely needed in normal applications. |
| `setSeed(byte[])` / `setSeed(long)` | Caller supplies seed input; **not required** when using `new SecureRandom()`. |
| `reseed()` / `reseed(params)` | Requests the provider to gather fresh entropy to reseed; **may be unsupported**. |

You should not follow a ritual like `generateSeed(32)` → `setSeed(...)` → `nextBytes(...)` every time you issue a token. Under normal configurations, `nextBytes` satisfies the need and the provider manages seeding appropriately.

## 5. Demonstrating Predictable Seeds with a Deterministic Generator

The example below **deliberately uses cryptographically unsafe `java.util.Random`** so Java guarantees reproducible output. Its goal is to show the effect of **the same seed**; it is **not production token-generation code**.

Create **`RepeatableSeedDemo.java`**:

```java
import java.util.Arrays;
import java.util.Random;

public class RepeatableSeedDemo {
    public static void main(String[] args) {
        byte[] first = new byte[16];
        byte[] second = new byte[16];

        new Random(123L).nextBytes(first);
        new Random(123L).nextBytes(second);

        System.out.println("Same bytes: " + Arrays.equals(first, second));
        System.out.println("Bytes generated: " + first.length);
    }
}
```

Run:

```text
javac --release 21 -encoding UTF-8 -d out RepeatableSeedDemo.java
java -cp out RepeatableSeedDemo
```

Exact stdout:

```text
Same bytes: true
Bytes generated: 16
```

Two independent `Random` generators given the same **seed 123** generate **the exact same byte sequence**. If an application uses such a sequence as a token, anyone knowing the seed can predict the token. Even if the seed "changes every time" within a narrow range, an adversary can try all possible seeds.

For `SecureRandom`, **never assume "the same seed always gives the same output" or "the same seed is guaranteed to give different output"**: algorithms, entropy mixing, self-seeding timing, and providers vary. The security lesson here is: if a design relies **solely** on a guessable seed with no additional real entropy, the output lacks strong secrecy regardless of how random it looks.

### Realistic Risk Scenario

Suppose a backend creates tokens like this:

```java
// Anti-pattern example: DO NOT use to generate security tokens.
SecureRandom random = new SecureRandom();
random.setSeed(System.currentTimeMillis());
byte[] token = new byte[32];
random.nextBytes(token);
```

- An adversary observes when an account was created/authenticated and can estimate the server clock within a narrow window.
- If the timestamp-derived seed is the only entropy, the searchable space is tiny compared to 2^256; a 32-byte token size **cannot rescue the design**.
- Reproducing exact bytes depends on provider, state, and API call ordering; this is a **risk analysis**, not a claim that every provider automatically produces identical tokens from the same timestamp.
- If a system runs multiple containers/VMs cloned from a snapshot sharing the same PRNG state without proper reseeding, state reuse/output collision is another operational risk. Configure strong entropy, proper initialization, and test platform clone/restore behavior.

Common bad seeds: `System.currentTimeMillis()`, `System.nanoTime()`, `Thread.currentThread().getId()`, process ID, username, email, incrementing counters, a fixed config string, or hashes of these values. **Hashing a weak seed or concatenating public data does not create new entropy.**

## 6. What Is Reseeding and When Is It Needed?

**Initial seeding** lets a PRNG establish a secret state. **Reseeding** updates that state later, typically with fresh entropy, to adhere to a DRBG lifecycle, limit exposure from a single state over time, and support prediction-resistance requirements in designs offering those guarantees.

In Java 21:

- `SecureRandom.reseed()` asks the engine to pull entropy from its source. Not all providers/algorithms support it; the API may throw `UnsupportedOperationException`.
- `SecureRandom.reseed(SecureRandomParameters)` passes specific parameters if accepted by the implementation.
- `SecureRandom.setSeed(...)` takes **caller-supplied** input; it is not equivalent to the provider gathering fresh entropy itself. Calling `setSeed(0L)` does not count as a secure reseed.
- Some DRBGs automatically reseed when seed age or invocation thresholds are exceeded via internal mechanisms; never assume automatic or manual behavior across **all** implementations.
- `nextBytes`, `generateSeed`, and `reseed` can **all block** waiting for entropy, depending on provider and OS.

For ordinary Java applications, **you do not need to call `reseed()` manually before every token generation**. If an organization has explicit policies for DRBG lifecycles, snapshot-restore points, HSM/FIPS devices, or prediction resistance, select a supporting provider, read its configuration docs, and test. Calling reseed continuously by hand can add latency without delivering imagined security gains.

### Cases to Distinguish

| Scenario | Approach |
| --- | --- |
| Issuing login tokens in a typical Java 21 service | A default-initialized `SecureRandom` and `nextBytes` are usually appropriate. |
| Service running for many months | Verify provider reseed/entropy policy if special security rules apply; never manually seed with timestamps. |
| VM/container restored from snapshot | Assess state-duplication risk, ensure proper entropy and initialization/reseeding after restore. |
| Must prove reseed/prediction resistance per policy | Use a DRBG/provider with matching capability and inspect `getParameters()`. |
| Unit tests needing deterministic results | Use a test double or fixed `Random` **only in non-security tests**; production must keep using a CSPRNG. |

## 7. Java 21 DRBG and Reseed Capability Check Example

Java has included `java.security.DrbgParameters` since Java 9. Java 21 provides mechanisms to request DRBG properties and query **effective parameters**; the `"DRBG"` algorithm depends on the provider. Three main capabilities exist:

- `DrbgParameters.Capability.NONE`: no guarantee of reseed or prediction-resistance support.
- `DrbgParameters.Capability.RESEED_ONLY`: supports reseeding, does not require prediction resistance per generation.
- `DrbgParameters.Capability.PR_AND_RESEED`: supports both reseeding and prediction resistance.

**Prediction resistance** in the DRBG context does not mean "calling `new SecureRandom()` once makes everything unbreakable." It is a specific property/requirement of the DRBG mechanism and entropy source that the provider must support.

Create **`DrbgReseedDemo.java`**:

```java
import java.security.DrbgParameters;
import java.security.SecureRandom;
import java.security.SecureRandomParameters;

public class DrbgReseedDemo {
    public static void main(String[] args) throws Exception {
        SecureRandom drbg = SecureRandom.getInstance("DRBG");
        SecureRandomParameters params = drbg.getParameters();

        boolean canReseed =
                params instanceof DrbgParameters.Instantiation actual
                && actual.getCapability().supportsReseeding();

        System.out.println("Algorithm: " + drbg.getAlgorithm());
        System.out.println("Reseed supported: " + canReseed);

        if (canReseed) {
            drbg.reseed(); // Provider fetches fresh entropy.
        }

        byte[] randomBytes = new byte[16];
        drbg.nextBytes(randomBytes);
        System.out.println("Generated: " + randomBytes.length + " bytes");
    }
}
```

Run:

```text
javac --release 21 -encoding UTF-8 -d out DrbgReseedDemo.java
java -cp out DrbgReseedDemo
```

On a JDK 21 runtime with a `DRBG` provider, the output looks like:

```text
Algorithm: DRBG
Reseed supported: true
Generated: 16 bytes
```

The `Reseed supported` line **depends on provider and configuration** (it can also be `false`); the example avoids calling `reseed()` if the provider does not advertise support. If no provider supplies `DRBG`, `getInstance("DRBG")` can throw `NoSuchAlgorithmException`; inspect the provider list or use `new SecureRandom()` for general random byte generation.

### When Capability Must Be Requested at Instantiation

The following is a **snippet** to embed in a Java program, not a standalone runnable file:

```java
import java.security.DrbgParameters;
import java.security.SecureRandom;

SecureRandom drbg = SecureRandom.getInstance(
        "DRBG",
        DrbgParameters.instantiation(
                128,
                DrbgParameters.Capability.RESEED_ONLY,
                null));
```

The argument `128` is the **requested DRBG security strength in bits**, not the number of bytes to generate. `RESEED_ONLY` sets a minimum capability requirement; the call can fail if no implementation satisfies it. In practice, read `drbg.getParameters()` to inspect effective parameters, since they may be stronger than requested.

`DrbgParameters.nextBytes(strength, predictionResistance, additionalInput)` and `DrbgParameters.reseed(predictionResistance, additionalInput)` target use cases with explicit DRBG configurations. **Additional input** or **personalization strings** do not replace a secret entropy source; never treat a username or public data as "extra seed" thinking it increases security.

## 8. Putting Random Bytes in Context: Tokens, Salts, Nonces, Keys

Even though all call `nextBytes`, each use case has distinct security requirements.

| Purpose | Primary requirement | Typical example |
| --- | --- | --- |
| Session token / reset token | Unpredictable, sufficiently long, securely transmitted/stored, expiration/revocation | 32 bytes from CSPRNG → Base64url (43 characters). |
| Salt for password KDF | Unique per password and sufficiently random; **does not need to be secret** | 16 bytes from CSPRNG; stored alongside KDF parameters and password hash. |
| Nonce/IV for AES-GCM | **Strictly never repeat under the same key**; must obey GCM limits and conventions | Typically 12 bytes for GCM; a good random source lowers collision chance, yet does not mathematically prove zero repeats. |
| Secret key | Right algorithm, size, and key lifecycle | Prefer `KeyGenerator` or proper key management/HSM APIs, typically backed by CSPRNG. |
| Short OTP code | Unbiased randomness, yet **very small space** | 6-digit code has only 1,000,000 possibilities; requires TTL, rate limits, anti-replay. |
| Public identifier | May need uniqueness rather than secrecy | Choose ID design per requirements; never assume ID = secret. |

**Nonce ≠ seed ≠ secret key.** A nonce can be public, yet repeating a nonce in GCM with the same key can break security. A seed initializes/mixes generator state; tokens and keys are outputs that must be protected. Never reuse an instance's seed as if it were a unique nonce across ciphertexts.

Example drawing a bounded integer from `0` to `999_999`:

```java
SecureRandom random = new SecureRandom();
int code = random.nextInt(1_000_000);
String sixDigits = String.format(java.util.Locale.ROOT, "%06d", code);
```

`nextInt(bound)` avoids naive modulo such as `(randomByte & 0xff) % 10`, which introduces distribution bias because 256 is not divisible by 10. This snippet only illustrates generating a 6-digit code; it is not a secure OTP system without expiration, server-side verification, attempt limits, and replay prevention.

### Guidelines for Handling Byte Data Responsibly

- `byte[]` can contain negative numbers if logged as Java `byte` values (`-128..127`); that is merely signed-byte representation, not "broken randomness."
- When storing/transmitting bytes, use properly formatted Base64url/hex and remember encoding does not increase entropy.
- Keep secrets in memory minimally, never log seeds/raw keys; clear sensitive byte arrays when appropriate and feasible (`Arrays.fill`), though zeroing is not guaranteed to scrub all copies or memory managed by the runtime/GC.
- Do not assume `getInstanceStrong()` is always better than `new SecureRandom()` for every application. It selects algorithms via `securerandom.strongAlgorithms` and may block or be expensive; benchmark and evaluate your specific environment.
- Do not pin provider/algorithm names from a developer machine without an explicit compatibility requirement.

## 9. Checking Environment and Providers on Java 21

Always report the **actual runtime**, provider, and algorithm when investigating production issues.

You can run this snippet in `jshell`:

```java
import java.security.SecureRandom;
SecureRandom random = new SecureRandom();
System.out.println(Runtime.version());
System.out.println(random.getAlgorithm());
System.out.println(random.getProvider().getName());
System.out.println(random.getParameters());
```

Output here is **not fixed**: JDK build, vendor, security properties, configured providers, and OS all affect it. `getParameters()` can return `null` for providers that do not expose effective DRBG parameters. Other useful methods: `SecureRandom.getInstance("DRBG")` (if supported by a provider), `SecureRandom.getInstanceStrong()` (if required by policy), and `Security.getProviders()` to list providers.

Self-check checklist:

1. `java -version`, `javac -version`, and `Runtime.version()` must match the target runtime.
2. Identify the actual provider and algorithm with `getProvider()`/`getAlgorithm()`.
3. Inspect startup/entropy sources, reseed policy, and provider limits in containers/VMs/HSMs.
4. Record errors and non-sensitive metadata; **never log seeds, random tokens, or private keys**.
5. Use integration tests and threat-model security reviews; never treat a few sample outputs as proof of a CSPRNG.

## 10. Common Conceptual and Operational Mistakes

| Symptom / claim | What is wrong | How to handle |
| --- | --- | --- |
| "Generating 32 bytes means 256 bits of entropy" | Output could be expanded from a very weak seed | Verify seed/entropy source and provider. |
| "Adding a timestamp makes SecureRandom stronger" | Timestamps are often predictable; calling `setSeed` before `nextBytes` can prevent self-seeding | Remove homemade seeds; rely on provider entropy. |
| "Same seed on SecureRandom always yields the same bytes" | Providers and entropy gathering/mixing differ | Never use `SecureRandom` to generate deterministic test fixtures. |
| "Calling reseed on every request is more secure" | May be unsupported, may block, adds overhead; providers have their own policies | Only call when required by design and provider docs. |
| `UnsupportedOperationException` from `reseed()` | Provider/engine does not support reseeding | Check capability for DRBGs or choose a provider meeting requirements. |
| `NoSuchAlgorithmException: DRBG` | No DRBG service in active providers | Check JDK, provider config, or use `new SecureRandom()` for general needs. |
| Duplicate tokens observed in testing | Could be fixed seed, cloned state, data reuse/caching bug, or system defect | Audit initialization, deployment, uniqueness invariants, and persistence end to end. |
| Long token still brute-forced online | Secret leaked or unlimited guessing allowed; short token with low entropy | Check TTL, rate limiting, authorization, token storage, and transport encryption. |
| Token bytes corrupted after `new String(bytes)` | Arbitrary bytes are not valid UTF-8 text | Use Base64url/hex for binary representation. |
| Using random GCM IVs and assuming collisions are impossible | Randomness makes collisions rare, not mathematically impossible | Design nonce management, bound encryptions per key, and monitor collision risk. |

**Do not infer security from small statistics.** Seeing two distinct tokens only shows two outputs differed; an insecure generator achieves that too. Conversely, a CSPRNG's natural collision probability is non-zero; a single uniqueness check does not prove an RNG is broken either.

**Do not force random output into passwords or keys via ad-hoc tricks.** If you need an AES key, use `KeyGenerator.getInstance("AES")` with a policy-approved length and proper key management. If you need password hashing, use a dedicated password KDF with salt, cost, and parameter management rather than homemade "sha256(password + random)".

## 11. Hands-On Exercises and Evaluation Criteria

**Exercise 1 – Generating tokens:** Run `SecureBytesDemo` on Java 21 multiple times. Explain why the output prints only **32/256/43** instead of printing the real token. If you change 32 bytes to 16 bytes, calculate the unpadded Base64url length yourself and verify.

**Exercise 2 – Entropy analysis:** A system seeds from an approximate minute/second window spanning 2,000 possible milliseconds. If that is the sole entropy, at most how many seeds must an adversary test? Why does hashing the seed with SHA-256 not increase the number of cases? *Hint: 2,000 possibilities is less than 2^11.*

**Exercise 3 – Seed and reproducibility:** Run `RepeatableSeedDemo`. Change one of the two seeds from `123L` to `124L` and explain why the output can differ. Then explain why the `Random(seed)` pattern must never be used to create reset tokens.

**Exercise 4 – Reseeding:** Run `DrbgReseedDemo`. Record algorithm, provider, `getParameters()`, and capability result; explain why `reseed()` must not be called blindly without checking support.

**Exercise 5 – Design review:** Given the three lines `SecureRandom r = new SecureRandom(); r.setSeed(System.currentTimeMillis()); r.nextBytes(token);`, describe when initial self-seeding is bypassed, the timestamp risk, and the corrected version using `new SecureRandom()` + `nextBytes(token)`. Do not claim every provider emits identical bytes for the same timestamp.

**Exercise 6 – Choosing randomness for purpose:** Distinguish a 32-byte secret token, 16-byte salt, 12-byte AES-GCM nonce, and 6-digit OTP. For each, state requirements on secrecy, uniqueness, anti-replay/rate-limiting, and storage.

You have mastered the lesson when you can answer accurately: **"Where do the bytes come from? Is the initial seed unpredictable? When does the provider self-seed or reseed? Which provider/DRBG am I using, and does this data require secrecy or uniqueness?"**

## Official References

- [Java SE 21: `SecureRandom` Javadoc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureRandom.html) — constructors, `nextBytes`, `setSeed`, `generateSeed`, `reseed`, and providers.
- [Java SE 21: `DrbgParameters` Javadoc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/DrbgParameters.html) — reseed/prediction-resistance capabilities and usage examples.
- [Java SE 21: `SecureRandomParameters`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureRandomParameters.html).
- [JDK 21: Java Cryptography Architecture (JCA) Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-cryptography-architecture-jca-reference-guide.html) — RNG/provider architecture and entropy.
- [JDK 21: JDK Providers Documentation](https://docs.oracle.com/en/java/javase/21/security/oracle-providers.html) — algorithms/providers shipped with Oracle JDK.
- [JDK 21: Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/21/docs/specs/security/standard-names.html) — standard security algorithm and service names.
- [NIST SP 800-90A Revision 1](https://csrc.nist.gov/pubs/sp/800/90/a/r1/final) — DRBG models and reseeding.

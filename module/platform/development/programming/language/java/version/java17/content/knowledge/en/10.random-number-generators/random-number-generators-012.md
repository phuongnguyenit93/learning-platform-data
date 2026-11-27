# Distinguishing Simulation PRNGs from SecureRandom for Security Purposes (Java 17)

Java offers several ways to generate pseudo-random numbers: `Random`, `SplittableRandom`, `ThreadLocalRandom`, and algorithms via `RandomGeneratorFactory`. They are useful for simulations, testing, games, or sampling. However, when generating password reset tokens, verification codes, nonces, or encryption keys, the primary requirement is that **an attacker cannot predict the next value**.

That is why Java has `SecureRandom`. Both simulation PRNGs and `SecureRandom` may use deterministic algorithms internally, yet they are designed and initialized for **different purposes**:

- Simulation PRNGs prioritize speed, reproducibility, and statistical properties suited for computation.
- `SecureRandom` targets unpredictability against adversaries, relying on entropy and provider security mechanisms.

Do not pick a generator just because its name includes "random." First determine whether the data needs to be reproducible or unpredictable, then pick the right API.

## 1. Distinguishing by Intended Use

| Criterion | Simulation PRNG | `SecureRandom` |
| --- | --- | --- |
| Goal | Produce number sequences with suitable statistical properties, usually fast and reproducible | Produce unpredictable values in security contexts |
| Seed | Can set a fixed seed to repeat results | Initialized and managed with appropriate entropy sources; do not self-seed predictably |
| Reproducibility | A useful feature for tests and simulations | Should not be designed to regenerate tokens/secrets from a public or fixed seed |
| Internal state | Knowing algorithm and state allows predicting subsequent sequence | Designed to resist state/output prediction by adversaries |
| Performance | Usually very fast; some variants optimized for parallelism | Carries security and provider overhead; performance varies by implementation |
| Example APIs | `Random`, `SplittableRandom`, `ThreadLocalRandom`, `RandomGenerator` | `SecureRandom` |
| Used for | Simulations, tests, sampling, games unrelated to secrets | Tokens, unpredictable nonces, random salts, keys, and security data |

**Practical rule:** if a value is used to grant permissions, verify identity, protect login sessions, or guard secrets, use `SecureRandom` or a high-level cryptographic API designed for that purpose. Do not use `Random` or `Math.random()` for these purposes.

## 2. Simulation PRNGs: Deterministic and Reproducible

A PRNG (*Pseudo-Random Number Generator*) produces a value sequence from internal state using a deterministic algorithm. General model:

\[
S_{n+1}=f(S_n), \qquad X_n=g(S_n)
\]

Where `S` is the state, `f` is the state update rule, and `g` produces the output value `X`. The seed initializes the initial state.

With the same algorithm, same seed, and same call sequence, a simulation PRNG reproduces the same sequence. This is a major advantage in testing:

```java
import java.util.Random;

public class SimulationDemo {
    static int[] simulate(long seed, int count) {
        Random random = new Random(seed);
        int[] results = new int[count];

        for (int i = 0; i < count; i++) {
            results[i] = random.nextInt(6) + 1;
        }
        return results;
    }

    public static void main(String[] args) {
        int[] first = simulate(2026L, 10);
        int[] second = simulate(2026L, 10);

        System.out.println(java.util.Arrays.toString(first));
        System.out.println(java.util.Arrays.equals(first, second));
    }
}
```

Both simulations initialize `Random` with seed `2026` and execute the same call sequence. Hence they yield identical results. When a bug appears in a run, you can save the seed to replay the scenario.

### 2.1. Why Is Reproducibility Unsuitable for Security Tokens?

Suppose an application generates password reset codes with:

```java
Random random = new Random(12345L);
int resetCode = random.nextInt(1_000_000);
```

Every application startup with a fixed seed can reproduce the same sequence. Someone who knows the seed, algorithm, and call count can compute the next code ahead of time.

Even if the seed comes from time:

```java
Random random = new Random(System.currentTimeMillis());
```

initialization time usually lies within a guessable window. If an attacker knows roughly when a token was created, they can test candidate seeds. Seeds derived from user IDs, sequence numbers, timestamps, or public data likewise do not create secrets.

A PRNG can pass several statistical tests and still be predictable. **Statistical quality and cryptographic security are two different properties.**

### 2.2. General-Purpose APIs Are Not CSPRNGs

- `Random` is the traditional PRNG, suited for general problems and seeded tests.
- `SplittableRandom` supports splitting generators for simulations or parallel processing; it is not designed to resist prediction.
- `ThreadLocalRandom` reduces contention when multiple threads need pseudo-random numbers; being thread-bound does not make it a security generator.
- `Math.random()` provides convenient pseudo-random numbers, not an API for generating secrets.
- `RandomGenerator` in Java 17 is a common interface for many generators. An object having type `RandomGenerator` **does not prove** the underlying algorithm is cryptographically secure.

## 3. SecureRandom: Random Number Generator for Security

`java.security.SecureRandom` is the Java API for generating pseudo-random data with properties suitable for security applications. It is commonly described as a *Cryptographically Secure Pseudo-Random Number Generator (CSPRNG)*.

A CSPRNG still has internal state and a deterministic algorithm. The difference is that it is designed to make outputs hard to predict without knowing the secret state, while providing mechanisms to initialize/reseed state from proper entropy sources.

Entropy sources can come from the operating system or cryptographic providers. Collection, state storage, reseeding, and exact algorithms depend on the implementation. Normal applications should use the standard API and let the provider manage these mechanisms rather than writing custom algorithms or manual seeds.

### 3.1. Creating SecureRandom the Standard Way

```java
import java.security.SecureRandom;

public class SecureRandomDemo {
    public static void main(String[] args) {
        SecureRandom secureRandom = new SecureRandom();

        byte[] randomBytes = new byte[16];
        secureRandom.nextBytes(randomBytes);

        for (byte value : randomBytes) {
            System.out.printf("%02x", value & 0xff);
        }
        System.out.println();
    }
}
```

`new SecureRandom()` asks the default provider for a security generator. The generator initializes itself via the implementation's mechanism. For ordinary applications, this is the right starting point.

Do not write a custom PRNG, take time as a seed, or set a fixed seed on `SecureRandom` thinking the result will be safer.

### 3.2. Do Not Self-Seed with Predictable Data

Avoid:

```java
SecureRandom random = new SecureRandom();
random.setSeed(System.currentTimeMillis()); // Does not make the entropy source secure.
```

`setSeed` is not a way to "enable security mode." On `SecureRandom`, this call mixes seed data into state according to implementation rules; it does not turn a predictable time value into secret entropy. If called before self-initialization, supplying a weak seed can affect security depending on the implementation.

In normal applications:

- Let the provider initialize `SecureRandom`.
- Do not seed with timestamps, counters, user IDs, or fixed strings.
- Do not expose internal state or secret seed material.
- Do not reuse the same fixed seed across environments.

If a system has special entropy management requirements, design according to provider and deployment platform guidelines, not by extrapolating from simulation PRNG examples.

## 4. Creating Unpredictable Tokens with SecureRandom

Password reset tokens, authentication tokens, or session keys need sufficient length and practical unpredictability. A common approach is generating random bytes and encoding them into a URL-safe string.

```java
import java.security.SecureRandom;
import java.util.Base64;

public class TokenGenerator {
    private static final SecureRandom RANDOM = new SecureRandom();

    public static String createToken() {
        byte[] bytes = new byte[32]; // 32 bytes = 256 bits
        RANDOM.nextBytes(bytes);

        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }

    public static void main(String[] args) {
        System.out.println(createToken());
    }
}
```

Here:

1. `nextBytes` fills the bytes with data from `SecureRandom`.
2. 32 bytes correspond to 256 bits of random data prior to encoding.
3. URL-safe Base64 converts bytes into a string usable in URLs without `+` or `/` characters.
4. `withoutPadding()` omits trailing padding characters.

Base64 encoding **does not increase entropy**; it only changes representation. Unpredictability comes from the generated bytes, token length, and quality of the random source.

### 4.1. Tokens Must Have Proper Lifecycle Management

Even a sufficiently random token can be abused if managed improperly by the application. For verification or password reset tokens, you typically need:

- Short expiration aligned with business requirements.
- Single use, invalidated immediately after consumption.
- Binding to the right account, purpose, and transaction session.
- Never logging full tokens in logs, analytics URLs, or error messages.
- Attempt limits and request rate limiting.
- Transmission over a secure channel such as HTTPS.
- When storing server-side, consider storing only a hash of the token to limit exposure if the database leaks.

`SecureRandom` solves the **unpredictable value generation** part. It does not replace access control, expiration, rate limiting, or protecting token storage.

## 5. Generating Bounded Integers Without Modulo Bias

A common mistake is taking a random number and applying the modulo operator:

```java
int code = random.nextInt() % 1_000_000;
```

This approach has two problems:

1. The result can be negative.
2. If the count of input values is not divisible by bound, remainders do not occur with equal probability (*modulo bias*).

With `SecureRandom`, use the bounded method:

```java
SecureRandom random = new SecureRandom();

int value = random.nextInt(1_000_000); // 0 to 999999
```

The generator's bounded API selects values in a way that avoids ordinary modulo bias. If you want to generate a 6-digit code:

```java
import java.security.SecureRandom;
import java.util.Locale;

public class OtpGenerator {
    private static final SecureRandom RANDOM = new SecureRandom();

    static String createOtp() {
        int value = RANDOM.nextInt(1_000_000);
        return String.format(Locale.ROOT, "%06d", value);
    }
}
```

The `%06d` format preserves leading zeros so the code always has six digits.

**A six-digit OTP code has only one million possibilities**, equivalent to less than 20 bits of entropy. Even with `SecureRandom`, it still requires short expiration, attempt limits, brute-force protection, and binding to the specific transaction/account. For higher security requirements, choose length and verification flows according to the threat model.

## 6. Using SecureRandom for Salts, Nonces, and Keys

Different cryptographic purposes have different requirements. `SecureRandom` can supply random bytes, yet correct usage also depends on the protocol or cryptographic algorithm.

### 6.1. Salts for Password Storage

A salt is unique random data for each hashed password. Salts usually do not need to be secret, but must be sufficiently unique and created with an appropriate random source:

```java
import java.security.SecureRandom;
import java.util.HexFormat;

public class SaltDemo {
    public static void main(String[] args) {
        SecureRandom random = new SecureRandom();
        byte[] salt = new byte[16];
        random.nextBytes(salt);

        System.out.println(HexFormat.of().formatHex(salt));
    }
}
```

This snippet only generates the salt. In a real authentication system:

- Do not store plaintext passwords or plain SHA-256 hashes.
- Use dedicated password hashing/KDFs with salt, cost/work factors, and proper configuration, such as PBKDF2, scrypt, bcrypt, or Argon2 per chosen standards and libraries.
- Store the salt alongside the hash and parameters needed for verification.
- Never reuse the same salt across all users.

`SecureRandom` produces a suitable byte source; it does not perform password hashing itself.

### 6.2. Nonces

A nonce is a *number used once* in a protocol. Some protocols require unpredictable nonces; others require nonces merely **not to repeat** within the scope of a key or session.

If the specification requires a random/unpredictable nonce, bytes can be generated with `SecureRandom`. If the specification requires uniqueness, enforce uniqueness as prescribed by the protocol; never assume random values alone strictly prevent collisions.

For cipher modes like GCM, nonces/IVs must obey algorithm requirements and must never be reused under the same key per that mode's rules. Follow cryptographic API and protocol guidance rather than guessing sizes or generation schemes from generic examples.

### 6.3. Generating Keys with KeyGenerator

When generating symmetric keys, use the high-level `KeyGenerator` API instead of slicing bytes and assigning them as keys manually:

```java
import java.security.SecureRandom;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

public class AesKeyDemo {
    public static void main(String[] args) throws Exception {
        SecureRandom random = new SecureRandom();

        KeyGenerator keyGenerator = KeyGenerator.getInstance("AES");
        keyGenerator.init(256, random);

        SecretKey key = keyGenerator.generateKey();
        System.out.println(key.getAlgorithm());
        System.out.println(key.getEncoded().length * 8);
    }
}
```

The example requests a 256-bit AES key. Algorithm, key size, and provider must align with cryptographic policies and the deployment environment. In real applications, never print or log key bytes; manage keys using an appropriate secret-management system/KMS.

## 7. SecureRandom Providers and Algorithms

`SecureRandom` is the API, while concrete algorithms are supplied by **providers**. A provider implements security services in the Java Cryptography Architecture (JCA).

You can inspect implementation details:

```java
import java.security.SecureRandom;

public class SecureRandomInfo {
    public static void main(String[] args) {
        SecureRandom random = new SecureRandom();

        System.out.println("Algorithm: " + random.getAlgorithm());
        System.out.println("Provider: " + random.getProvider().getName());
        System.out.println("Parameters: " + random.getParameters());
    }
}
```

Actual algorithm and provider names depend on the JDK, security configuration, operating system, and installed providers. Therefore, do not hardcode assumptions that every Java 17 machine uses the exact same default algorithm.

### 7.1. Selecting an Explicit Algorithm When Required by Deployment

If an application needs a provider-supported algorithm, you can request it by name:

```java
import java.security.SecureRandom;

public class NamedSecureRandom {
    public static void main(String[] args) throws Exception {
        SecureRandom random = SecureRandom.getInstance("DRBG");
        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
    }
}
```

`DRBG` is a family of *Deterministic Random Bit Generators* standardized for cryptographic purposes. Java supports DRBG parameter APIs in modern versions; JDK 17 includes DRBG implementations in common standard providers. Still, algorithm availability and supported parameters depend on the specific provider/runtime. When specifying an explicit name, verify on the target deployment environment and handle `NoSuchAlgorithmException`.

For general needs, `new SecureRandom()` is usually simpler and lets JCA pick the default implementation.

### 7.2. getInstanceStrong() Is Not the Default Choice for Every Application

Java provides:

```java
SecureRandom random = SecureRandom.getInstanceStrong();
```

This method selects an implementation configured as strong according to the `securerandom.strongAlgorithms` security property. Depending on the provider and entropy source, initialization or data generation can exhibit different performance/blocking behavior than `new SecureRandom()`.

Do not infer that `getInstanceStrong()` is always required or always faster/safer than the default implementation in every situation. Use it when specifically required, check provider configuration, and measure operational behavior in the real environment. For most applications, `new SecureRandom()` is the right choice.

## 8. Relationship Between SecureRandom and RandomGenerator in Java 17

Java 17 introduces the `java.util.random` package with the `RandomGenerator` interface and factories for PRNG algorithms. `Random` implements `RandomGenerator`; `SecureRandom` extends `Random`, so it can also be used through that common API.

This **does not mean every RandomGenerator is cryptographically secure**.

Example of a simulation method:

```java
import java.util.random.RandomGenerator;

static int rollDice(RandomGenerator random) {
    return random.nextInt(6) + 1;
}
```

This method only needs a pseudo-random source. You can pass a fixed-seed simulation generator for testing.

However, for a security token generation method, express the requirement via the concrete type:

```java
import java.security.SecureRandom;
import java.util.Base64;

static String createResetToken(SecureRandom secureRandom) {
    byte[] bytes = new byte[32];
    secureRandom.nextBytes(bytes);
    return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(bytes);
}
```

Accepting `SecureRandom` clarifies the API's intent and prevents accidentally passing a simulation PRNG. In larger systems, you can define a dedicated abstraction like `SecureTokenGenerator` to explicitly control token generation sources.

## 9. Thread Safety and Sharing SecureRandom

`SecureRandom` is designed to be safe for use by multiple threads. However, under heavy load, performance characteristics depend on the provider and internal synchronization.

A simple approach is keeping a single instance managed across the application lifecycle:

```java
public final class SecurityRandoms {
    private static final SecureRandom INSTANCE = new SecureRandom();

    private SecurityRandoms() {
    }

    public static SecureRandom get() {
        return INSTANCE;
    }
}
```

There is no need to create a new `SecureRandom` for every byte or every request without a clear reason. Recreating it repeatedly can increase initialization cost and entropy/provider interactions.

If optimization is needed in multithreaded environments, benchmark performance and consult provider documentation. Do not switch to `Random` or `ThreadLocalRandom` merely because they are faster; doing so breaks security requirements.

For simulation PRNGs, `SplittableRandom` can be split so each task uses a dedicated instance. That rule exists for state management and performance; it does not replace `SecureRandom` when resisting prediction is the goal.

## 10. Testing Security Code While Controlling Results

A key difference in test design:

- For simulations, using a fixed seed is a great way to get deterministic results.
- For security tokens, do not pin `SecureRandom`'s seed in production or downgrade to `Random` just to make tests easily repeatable.

You can separate **token processing logic** from **token generation source**:

```java
import java.security.SecureRandom;
import java.util.Base64;

public class ResetTokenService {
    private final SecureRandom random;

    public ResetTokenService(SecureRandom random) {
        this.random = random;
    }

    public String createToken() {
        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }
}
```

In tests, you can verify properties independent of a specific token string:

- Token has URL-safe formatting.
- Required random byte length is produced.
- Token is bound to the right account and expiration.
- Token is single-use and invalidated after use.
- Error paths and attempt limits behave properly.

There is no need to assert that every run emits one fixed token string. For pure logic requiring deterministic outputs, extract it into a separate function and test it independently.

## 11. Mistakes to Avoid

**Using `Random` to generate reset tokens or session IDs.**  
`Random` serves general pseudo-random needs, not cryptographic unpredictability. Use `SecureRandom`.

**Seeding `Random` with a timestamp and treating it as secret.**  
Timestamps and public data can be guessed within a window. Seeds do not create entropy on their own.

**Calling `setSeed` with a fixed number on SecureRandom.**  
Does not make the generator stronger. Adding a weak seed can violate the application's security assumptions.

**Using `random.nextInt() % bound` to generate OTPs.**  
Can produce negative values and skewed distribution. Use `nextInt(bound)`.

**Assuming the `RandomGenerator` interface name implies cryptographic security.**  
The interface only standardizes calling conventions; you must know the concrete implementation and design purpose.

**Assuming a long Base64 token is automatically secure.**  
Base64 only encodes representation. Entropy comes from the underlying bytes, algorithm, and quality of the random source.

**Using a six-digit OTP without attempt limits.**  
A one-million value space can be brute-forced without rate limits, expiration, and single-use enforcement.

**Generating keys manually with `Random` and using them in encryption.**  
Use `KeyGenerator` or suitable key management APIs backed by a secure random source.

**Assuming random nonces always guarantee zero collisions.**  
Randomness does not mean absolute uniqueness. Follow the nonce/IV requirements of the protocol and algorithm.

## 12. Quick Decision Table

| Question | Choice |
| --- | --- |
| Need identical results on every simulation test run? | A PRNG with a fixed seed, e.g. `Random(seed)` or a deterministic generator via factory. |
| Need random data for benchmarking/sampling? | A PRNG suited to statistical and performance requirements. |
| Need to generate password reset tokens or session secrets? | `SecureRandom`. |
| Need to generate nonces or salts from random bytes? | `SecureRandom`, while following protocol/KDF rules. |
| Need to generate AES keys? | `KeyGenerator` with a `SecureRandom` source or suitable key management APIs. |
| Need pseudo-random numbers in a multithreaded app? | `ThreadLocalRandom` or split generators, if not security data. |
| Need to select PRNG algorithms via config in Java 17? | `RandomGeneratorFactory`; verify the implementation exists on the target runtime. |

## 13. Self-Check Questions

**1. Why can simulation PRNGs reproduce results?**  
Because the algorithm deterministically computes the next state from current state; the same seed and same call sequence regenerate the same sequence.

**2. Is a PRNG with good statistical distribution guaranteed to be cryptographically secure?**  
No. Statistical quality does not prove resistance to prediction by an adversary.

**3. Why not use `new Random(System.currentTimeMillis())` to generate tokens?**  
Time can be guessed within a range, and `Random`'s algorithm is not designed to resist prediction.

**4. Is `SecureRandom` true random?**  
Not necessarily. It is an API for a cryptographically secure pseudo-random generator, based on state and entropy/provider mechanisms.

**5. Should you manually seed `SecureRandom` with a timestamp?**  
No. Let the provider initialize itself via appropriate mechanisms; timestamps are not reliable secret entropy.

**6. Why use `nextInt(bound)` instead of modulo?**  
Bounded methods avoid modulo bias and return values within the required range.

**7. Does `RandomGenerator` in Java 17 mean CSPRNG?**  
No. It is a common interface; check the implementation and security requirements.

**8. Should `SecureRandom` be used for all simulations?**  
Not necessary. Simulation PRNGs are usually faster and support reproducibility; use the right tool for the purpose.

**9. Does generating a 32-byte token and Base64-encoding it increase randomness?**  
No. Base64 only changes representation; the byte source has 256 bits prior to encoding if the generator supplies sufficient quality.

**10. Is generating a six-digit OTP with SecureRandom enough to protect the OTP?**  
No. Expiration, attempt limits, single use, account/transaction binding, and transport protection are also required.

## Official References

- [Java SE 17 API — `SecureRandom`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): cryptographically secure pseudo-random generator, seeding, providers, and byte generation methods.
- [Java SE 17 API — `Random`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html): traditional PRNG and reproducibility.
- [Java SE 17 API — `RandomGenerator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html): generator interface in Java 17.
- [Java SE 17 API — `RandomGeneratorFactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGeneratorFactory.html): selecting PRNG implementations via factory.
- [Java SE 17 API — `SplittableRandom`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SplittableRandom.html): splittable generator for parallel computing.
- [Java SE 17 API — `ThreadLocalRandom`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html): thread-bound generator.
- [Java SE 17 API — `KeyGenerator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/KeyGenerator.html): cryptographic key generation API.
- [JEP 273 — DRBG-Based SecureRandom Implementations](https://openjdk.org/jeps/273): support for DRBG mechanisms in Java.
- [Java Cryptography Architecture (JCA) Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html): providers, algorithms, and Java's cryptographic service architecture.

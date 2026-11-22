# `SecureRandom` for Unpredictability Requirements in Java

## 1. Why is “random” not enough for security?

Some tasks only need data that **looks random**: shuffling practice questions, simulating die rolls, generating test data. Other tasks require that an attacker **cannot feasibly predict** the next value, even after observing many previous values. That is a common requirement when generating:

- Password reset tokens or email verification tokens containing secrets.
- Session tokens, API tokens, secret nonces, random access codes.
- Server-generated OTPs (paired with attempt rate limiting).
- Random material for cryptographic operations.

In Java, `java.security.SecureRandom` is the random number generation API intended for security contexts. It draws output from a generator supplied via a **security provider**; with an appropriate cryptographic implementation and sufficiently high-entropy seeding, outputs are designed to resist computational prediction.

`java.util.Random`, `Math.random()`, and `ThreadLocalRandom` are useful for simulations or general applications, yet **do not meet the unpredictability contract required for security secrets**. A generator with “nice” distribution statistics can still be predicted if its state or seed is known. Conversely, `SecureRandom` prioritizes security properties; do not cite a few chaotic-looking outputs as proof that an algorithm is secure.

After this lesson, you will be able to pick the right API, generate byte tokens and OTP codes with `SecureRandom`, understand seed/provider sources, avoid modulo bias, and pair tokens with appropriate operational controls.

## 2. Mental model: general random vs. cryptographic random

| Criterion | `Random`, `ThreadLocalRandom`, `Math.random()` | `SecureRandom` |
|---|---|---|
| Primary goal | Simulation, statistical distribution, speed | Computationally unpredictable values |
| Use for secret tokens | **Do not use** | **Use**, with proper length and token management |
| Fixed seed to reproduce tests | Often useful with `new Random(seed)` | Not an appropriate way to generate real secrets |
| Output guarantees | Algorithm-dependent, no cryptographic security promise | Per chosen cryptographic algorithm/provider |
| Performance | Usually suited for large simulation volumes | May incur higher initialization or entropy cost |
| Always unique outputs? | No | **Also no**; randomness differs from uniqueness guarantees |

**Unpredictable** does not mean **never collides**. Even 256-bit tokens have a nonzero collision probability; if the system mandates unique keys, enforce appropriate data constraints and handle rare collisions.

In implementation terms, many `SecureRandom` algorithms are **CSPRNGs** (*cryptographically secure pseudorandom number generators*): internal state and seeding support producing output streams resistant to prediction. That does not mean every byte is read directly from hardware on every call. Some providers also use other RNG mechanisms; the `SecureRandom` contract abstracts over this choice.

### When must `SecureRandom` be used?

Ask: “If an outsider guesses the next value, can they take over an account, bypass verification, forge a request, or access protected resources?” If the answer is **yes**, this is a classic case requiring `SecureRandom` (alongside other safeguards) rather than a simulation generator.

## 3. Essential APIs and initialization

Start simply, without manually configuring a seed:

```java
import java.security.SecureRandom;

SecureRandom secureRandom = new SecureRandom();
```

This is an illustrative snippet placed inside a class or method. The no-argument constructor picks a default algorithm and provider according to the running Java configuration. Never assume all machines or JDK versions choose the exact same algorithm.

Key methods to know:

| API | Meaning |
|---|---|
| `new SecureRandom()` | Obtains the default generator chosen by Java/provider |
| `nextBytes(byte[] bytes)` | Fills the allocated array with random bytes |
| `nextInt(int bound)` | Uniformly distributed `int` in `[0, bound)`; `bound > 0` |
| `nextLong()` | Draws a random `long` value |
| `generateSeed(int numBytes)` | Generates **seed** bytes, primarily for seeding other generators |
| `getAlgorithm()`, `getProvider()` | Reports the actual algorithm/provider, useful for diagnostics |
| `SecureRandom.getInstance("DRBG")` | Requests a specific algorithm; can throw `NoSuchAlgorithmException` if unsupported |
| `SecureRandom.getInstanceStrong()` | Selects based on `securerandom.strongAlgorithms`; may incur cost/entropy blocking per provider |

**Default choice:** For typical tokens in modern Java applications, `new SecureRandom()` with `nextBytes()` is usually a sensible starting point. If your organization has specific algorithm, compliance, DRBG, FIPS, or provider requirements, configure and verify specifically for your deployment environment. The name `getInstanceStrong()` does not mean switching to it makes every system more secure; the selected algorithm, blocking behavior, and performance depend on configuration.

## 4. Complete example: URL-safe 32-byte secret token

**Goal:** Generate **32 random bytes** (256 output bits), then encode to URL-safe Base64 **without padding**. This format can be used as a secret in URLs or parameters if handled carefully. Base64 only **encodes representation**, not cryptographic encryption; the token value itself remains a secret to protect.

**File `SecureTokenDemo.java` — Java 17+:**

```java
import java.security.SecureRandom;
import java.util.Base64;

public class SecureTokenDemo {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final int TOKEN_BYTES = 32;

    public static String newToken() {
        byte[] bytes = new byte[TOKEN_BYTES];
        RANDOM.nextBytes(bytes);

        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }

    public static void main(String[] args) {
        String token = newToken();

        // Print only verification properties, do not print the real secret.
        System.out.println("tokenLength=" + token.length());
        System.out.println("decodedBytes="
                + Base64.getUrlDecoder().decode(token).length);
        System.out.println("urlSafe="
                + token.matches("[A-Za-z0-9_-]{43}"));
    }
}
```

Compile and run:

```bash
javac SecureTokenDemo.java
java SecureTokenDemo
```

Output:

```text
tokenLength=43
decodedBytes=32
urlSafe=true
```

Printed output is stable because the program checks **shape**, without printing random token contents. Token values change between runs, though **absolute uniqueness across every run is not guaranteed by contract**.

Step-by-step explanation:

1. `new byte[32]` allocates exactly 32 bytes.
2. `RANDOM.nextBytes(bytes)` fills computationally unpredictable bytes per the security provider's guarantees.
3. `Base64.getUrlEncoder()` uses characters `A–Z`, `a–z`, `0–9`, `-`, `_`, better suited for URLs than standard Base64's `+` and `/`.
4. `withoutPadding()` strips trailing `=`; **32 bytes produce an unpadded 43-character Base64URL string**.
5. When restoring original bytes is needed, `Base64.getUrlDecoder().decode(token)` decodes back to exactly 32 bytes.

If every byte has ideal entropy, 32 bytes correspond to a space of about `2^256` values. However, **a 256-bit length does not automatically make the whole system 256-bit secure**: you still need a good entropy/provider source, no token leaks, and proper secret lifecycle handling. Truncating the resulting string to a few characters drastically shrinks the guessing space.

### Why not print tokens to the console?

Reset or session tokens are **bearer secrets**: anyone holding a valid token within its lifetime can exercise the privileges it represents. Logs, telemetry, URL history, error trackers, and analytics can inadvertently retain secret values. The example above intentionally prints only verification attributes, not the token itself.

## 5. Generating a six-digit OTP code: strong randomness still needs extra protection

An OTP in `000000`–`999999` has only **1,000,000 possible values**. `SecureRandom` makes the generated sequence hard for an attacker to predict, yet **does not expand the guessing space** of a six-digit code. Short codes must be paired with short TTLs, attempt limits, single-use verification, and binding to the session/request/recipient.

**File `SecureOtpDemo.java`:**

```java
import java.security.SecureRandom;
import java.util.Locale;

public class SecureOtpDemo {
    private static final SecureRandom RANDOM = new SecureRandom();

    public static String sixDigitCode() {
        int value = RANDOM.nextInt(1_000_000);
        return String.format(Locale.ROOT, "%06d", value);
    }

    public static void main(String[] args) {
        String otp = sixDigitCode();

        System.out.println("otpLength=" + otp.length());
        System.out.println("onlyDigits=" + otp.matches("[0-9]{6}"));
    }
}
```

```bash
javac SecureOtpDemo.java
java SecureOtpDemo
```

Output:

```text
otpLength=6
onlyDigits=true
```

Details often overlooked:

- `nextInt(1_000_000)` returns a number from **0 to 999999**, excluding 1000000; the bound must be positive.
- `%06d` preserves **all 6 digits**, even when the random value is `000042`.
- For an OTP allowed to start with `0`, do not use `100_000 + RANDOM.nextInt(900_000)`: that drops all zero-prefixed codes, leaving only 900,000 possibilities.
- Only use the `100000`–`999999` range if policy **forbids leading zeros**; that is a different business rule.
- **Never** generate the number with `Math.abs(RANDOM.nextInt()) % 1_000_000`: modulo does not guarantee uniformity, `Math.abs(Integer.MIN_VALUE)` stays negative due to overflow, and taking remainders ignores security requirements.

For a bounded range, call `nextInt(bound)` directly so the API picks uniformly without writing biased modulo logic. For example, picking an index in a 10-element list: `RANDOM.nextInt(10)` returns `0`–`9`.

### How are OTPs protected in real systems?

Combine multiple controls: short code validity; appropriate attempt rate limits per account/request/IP; locking or invalidating after too many attempts; binding the code to the exact action, recipient, and time; and single-use consumption per code. Under concurrent requests, the “used” flag must be updated **atomically** to prevent reuse. All validation must occur on the server.

## 6. Token lifecycle: good generation is only the first step

A typical password-reset token flow:

```text
Server
  |
  | SecureRandom.nextBytes(32)
  v
Secret token (Base64URL) ------> Sent privately to account owner
  |
  | SHA-256(token) / appropriate cryptographic hash
  v
Store hash + accountId + purpose + expiresAt + used=false
  |
  | When user submits token back
  v
Hash submitted token -> compare with stored record
  |
  +-- wrong / expired / wrong purpose / already used: reject
  |
  +-- valid: perform action and mark used=true in a safe transaction
```

In real applications, storing a **hash** of a long random token (instead of keeping the raw token in plaintext in the database) limits exposure if the token table leaks. For high-entropy tokens, SHA-256 is commonly appropriate as a lookup digest; low-entropy six-digit OTPs **cannot rely on plain SHA-256 to resist offline brute-forcing if the hash leaks**. OTPs demand dedicated storage and controls, such as server-secret HMACs alongside attempt limits and expiration.

The following standalone code illustrates storing/comparing digests for high-entropy tokens and **does not replace** full authentication layers, TTL checks, or atomic “used” updates.

**File `TokenDigestDemo.java`:**

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;

public class TokenDigestDemo {
    private static byte[] sha256(String text)
            throws NoSuchAlgorithmException {
        return MessageDigest.getInstance("SHA-256")
                .digest(text.getBytes(StandardCharsets.US_ASCII));
    }

    public static void main(String[] args)
            throws NoSuchAlgorithmException {
        byte[] bytes = new byte[32];
        new SecureRandom().nextBytes(bytes);

        String token = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);

        byte[] storedDigest = sha256(token);
        byte[] presentedDigest = sha256(token);

        System.out.println("digestBytes=" + storedDigest.length);
        System.out.println("match="
                + MessageDigest.isEqual(storedDigest, presentedDigest));
    }
}
```

```bash
javac TokenDigestDemo.java
java TokenDigestDemo
```

```text
digestBytes=32
match=true
```

`SHA-256` produces a 32-byte digest; `MessageDigest.isEqual` is the appropriate byte-array comparison API for timing-sensitive values. In this example, `token` is a private value inside the program and is never printed; in a real application, the server stores `storedDigest` and sends the raw token to the user only over a protected channel.

**Do not confuse SHA-256 with user password hashing algorithms.** User-chosen passwords can be guessed, so they usually require specialized KDF algorithms such as Argon2id, scrypt, or PBKDF2 with suitable parameters. Long random tokens and short OTPs are two storage scenarios with different threat models.

## 7. Seeds, entropy, providers, and `getInstanceStrong()`

### 7.1. Seeds govern unpredictability

A CSPRNG needs an initial state with sufficiently strong entropy. A default `SecureRandom` typically self-seeds via an appropriate mechanism/provider when needed; developers do not need to manually seed it from the clock.

**Avoid:**

```java
// Illustrates what should not be used to generate security tokens.
byte[] guessableSeed = {
        1, 2, 3, 4
};
SecureRandom random = new SecureRandom(guessableSeed);
```

Fixed seeds or seeds predictable from time, PID, username, or student ID can undermine unpredictability. Nor is there any basis to assume that merely passing a long `byte[]` gives high entropy. Depending on the provider, seed provisioning and reseed behavior vary; **never use homemade seeds to generate or test real tokens**.

One API detail: `setSeed(...)` on `SecureRandom` may supplement entropy into the existing state rather than necessarily replacing the seed like initializing a regular `Random`. Do not rely on a fixed seed to reproduce the exact same `SecureRandom` sequence across JDKs, providers, or machines. When testing logic that depends on a random source, you can **inject a fake source interface** in tests while keeping a real CSPRNG in production.

### 7.2. Is `getInstanceStrong()` always a better choice?

`SecureRandom.getInstanceStrong()` reads preferred strong algorithms configured in the `securerandom.strongAlgorithms` security property. It can throw `NoSuchAlgorithmException`, and some entropy sources/providers may block during initialization or data generation.

For high-traffic endpoints needing short-lived tokens, do not blindly replace every `new SecureRandom()` with `getInstanceStrong()` without evaluating the algorithm, deployment configuration, throughput, and latency. If organizational policy requires a specific DRBG or provider, select it explicitly per policy and test on the target runtime, including missing-provider handling.

### 7.3. `nextBytes` vs. `generateSeed`

To **generate tokens for immediate use**, the standard method is `nextBytes(byte[])`. `generateSeed(int)` is intended to produce seed bytes, such as for initializing another RNG; its entropy collection and performance depend on the provider. You do not have to call `generateSeed` before `nextBytes` when using `new SecureRandom()`.

### 7.4. Sharing a single `SecureRandom` instance

In modern Java, `SecureRandom` is documented as thread-safe when shared across threads; the class can synchronize operations with providers that do not declare thread safety. Thus, keeping `private static final SecureRandom RANDOM = new SecureRandom();` in the examples is a valid pattern for many applications.

Under very high throughput, benchmark on your actual provider: contention, entropy, and initialization can affect performance. Do not recreate `SecureRandom` inside every loop iteration hoping for “more random” outputs.

## 8. Common mistakes

| Mistake | Impact | Proper practice |
|---|---|---|
| Using `Math.random()` for password-reset tokens | Lacks CSPRNG unpredictability contract | Use `SecureRandom.nextBytes` |
| Using `new Random(System.currentTimeMillis())` for OTPs | Clock-based seed is predictable | Use `SecureRandom.nextInt(bound)` |
| Creating very short tokens thinking `SecureRandom` is enough | Small guessing space | Use enough bytes and protect lifecycle |
| Using `Math.abs(nextInt()) % bound` | Possible bias and `Integer.MIN_VALUE` bug | `nextInt(bound)` |
| Encoding with Base64 and assuming the secret is encrypted | Base64 is trivially decoded | Treat the Base64URL string as a bearer secret |
| Writing raw tokens to logs or analytics | Secret leakage | Log only non-sensitive metadata |
| Issuing OTPs without TTL or attempt limits | Vulnerable to online brute force | TTL, rate limits, lockout/rotation, and single-use |
| Assuming `getInstanceStrong()` is always fast and non-blocking | Possible latency spikes/provider differences | Evaluate in the deployment environment |
| Seeding from timestamps or constant strings | Low-entropy seed | Let the provider supply appropriate entropy |
| Assuming random tokens are always unique | Rare collisions can still occur | Check/enforce uniqueness when required |
| Printing a few tokens and declaring security | “Non-repeating” output does not prove unpredictability | Rely on proper algorithms/providers and system testing |

## 9. How to test properly when outputs must vary

Because CSPRNG output has no fixed value, do not write tests like:

```java
// WRONG: cannot expect a fixed token value.
assert token.equals("abc123");
```

Instead, test deterministic properties:

```java
String token = SecureTokenDemo.newToken();

if (token.length() != 43
        || !token.matches("[A-Za-z0-9_-]{43}")
        || Base64.getUrlDecoder().decode(token).length != 32) {
    throw new AssertionError("Invalid token format");
}
```

This snippet uses the `SecureTokenDemo` class defined in section 4; add `import java.util.Base64` if placed in a separate file. You can also test that tampered or already-used tokens are rejected and verify behavior after expiration.

**Statistical distribution tests** do not prove an RNG is unpredictable. Avoid writing flaky tests like “100 tokens must all be distinct” and treating them as cryptographic proof. To ensure algorithms meet standards or provider configurations, rely on vetted libraries/providers, managed runtime environments, and integration tests covering the secret-handling path.

## 10. Self-check questions

1. **An app shuffles multiple-choice questions; results are not used as secrets. Is `SecureRandom` mandatory?**  
   No. `Random` or an ordinary random source can suffice when there are no security requirements.

2. **An app issues password-reset tokens where outsiders can see a few other users' tokens. What should be used?**  
   A CSPRNG like `SecureRandom`, generating enough entropy bytes and protecting tokens during transit, storage, use, and expiration.

3. **Can `RANDOM.nextInt(6)` return `6`?**  
   No. It returns one of `0, 1, 2, 3, 4, 5`.

4. **Why does `%06d` matter in a six-digit OTP?**  
   Because a random integer `42` must be formatted as `000042` when leading zeros are allowed.

5. **Does Base64URL turn a token into cryptographically encrypted data?**  
   No. It only encodes bytes into a readable/transmittable string; anyone receiving it can decode it without a key.

6. **Why can a `000000`–`999999` OTP still be brute-forced even when generated with `SecureRandom`?**  
   Because there are only 1,000,000 possibilities; you still need TTL, attempt limits, session binding, and single-use enforcement.

7. **Should `SecureRandom.getInstanceStrong()` be used on every request without checking the provider?**  
   No. Algorithm choice and entropy blocking/cost depend on configuration and must be evaluated on the target runtime.

8. **Does `SecureRandom` guarantee that two 32-byte draws will never match?**  
   There is no absolute guarantee. Collision probability is tiny with proper implementation and entropy, yet uniqueness constraints must be handled explicitly if business logic requires them.

## 11. Key takeaway and references

Whenever a task requires **unpredictability**, use `SecureRandom` with a trusted provider and an appropriate entropy source. Use `nextBytes` for long secret tokens; use `nextInt(bound)` for bounded values; never use manual modulo to construct OTPs. `SecureRandom` is the **secret-generation** component—it does not replace authentication, rate limiting, TTLs, secure secret storage, or abuse detection.

Javadoc and official references:

- [Java 21: `java.security.SecureRandom`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureRandom.html)
- [Java 21: `java.util.Base64`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Base64.html)
- [Java 21: `java.security.MessageDigest`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/MessageDigest.html)
- [Java 21 Security Developer's Guide](https://docs.oracle.com/en/java/javase/21/security/)

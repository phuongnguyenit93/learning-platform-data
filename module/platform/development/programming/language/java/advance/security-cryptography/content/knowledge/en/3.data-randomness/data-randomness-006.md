# 3.6 getInstanceStrong, DRBG, and Blocking Behavior of Random Sources

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish **entropy source**, **seed**, **CSPRNG/DRBG**, and the `SecureRandom` API; explain why a pseudorandom generation algorithm remains secure when properly initialized.
2. Understand what `SecureRandom.getInstanceStrong()` actually selects via `securerandom.strongAlgorithms`, and why the word "strong" does not mean "non-blocking" or "suitable for every task."
3. Use `SecureRandom.getInstance("DRBG", DrbgParameters.instantiation(...))`, inspect effective strength/capability, and distinguish reseeding from prediction resistance.
4. Identify calls that may **block** when entropy is needed, measure creation and byte-generation latency properly, and choose suitable designs for latency-sensitive systems.
5. Avoid common security mistakes: predictable seeds, using `Random` for tokens, assuming provider behavior, or forcing reseed/strong on every request.

## 1. Minimum Foundation: Entropy Source, Seed, and DRBG

`SecureRandom` is the JCA engine API; the provider determines the implementation and how entropy is obtained. The **entropy source** supplies unpredictability from the OS/hardware; the **seed/state** is the secret initialization; the **CSPRNG/DRBG** expands that state cryptographically into unpredictable bytes. "Deterministic" in DRBG describes generation from state, **not** that an adversary can predict the state.

```text
Entropy source -> instantiate/reseed -> DRBG state -> nextBytes(...)
```

Generating 32 bytes does not guarantee 256-bit security strength. `nextBytes` produces bytes for the application; `generateSeed` creates seed material; `reseed` can pull additional entropy from the provider; `setSeed` accepts caller data and **creates no new entropy** from timestamps or PIDs. This lesson focuses specifically on **selecting strong/DRBG by policy, inspecting effective capabilities, and measuring latency caused by providers/entropy sources**.

## 2. Three Ways to Obtain `SecureRandom` and Practical Implications

| Way to obtain instance | Who picks the implementation? | When to use | What to verify |
| --- | --- | --- | --- |
| `new SecureRandom()` | Default provider per runtime configuration | Most secure random byte generation needs in applications | Actual algorithm/provider and latency characteristics on target environment |
| `SecureRandom.getInstanceStrong()` | `securerandom.strongAlgorithms` list in **security properties** | Policy/application requires an implementation marked strong by the platform | Algorithm, provider, entropy source, startup/first-call latency, and blocking behavior |
| `SecureRandom.getInstance("DRBG", params)` | JCA searches for a provider supporting `SecureRandom.DRBG` and minimum parameters | Need to explicitly declare strength, reseeding, or prediction resistance | Whether runtime has a DRBG provider and effective capability meets needs |

All three return the **`SecureRandom` API**. They differ in implementation selection and extra constraints; never assume `getInstanceStrong()` is stronger than every DRBG, or that a DRBG will never block.

### 2.1 `getInstanceStrong()` Is Not an Algorithm Name

`getInstanceStrong()` (available since Java 8) reads the property:

```java
String configured = java.security.Security.getProperty(
        "securerandom.strongAlgorithms");
```

This is an **illustrative expression** for use inside a Java method; `Security.getProperty` reads a **security property**, not a regular `System.getProperty`.

The `securerandom.strongAlgorithms` property lists algorithms/providers that the Java distribution deems suitable for generating critical security values, such as long-lived keys. `getInstanceStrong()` consults that list to pick an available implementation. Logical flow:

```text
SecureRandom.getInstanceStrong()
       |
       v
Security.getProperty("securerandom.strongAlgorithms")
       |
       v
Look up platform-configured algorithm/provider list
       |
       v
Selected SecureRandom engine + provider
       |
       v
nextBytes / generateSeed / reseed (behavior depends on provider)
```

One JDK may pick a provider tied to OS randomness facilities; another JDK may pick a different algorithm. Names like `NativePRNGBlocking`, `Windows-PRNG`, or `DRBG` are **runtime-specific**, not a universal mandatory list.

**Important boundary:** the factory method may return quickly while the first `nextBytes` call blocks to gather entropy, or initialization itself may take time. Never infer latency from the word "Strong"; always inspect the provider and measure in practice.

Java SE requires the platform to supply at least one strong implementation, yet `getInstanceStrong()` still declares `NoSuchAlgorithmException` if no configured algorithm can be obtained from active providers. In misconfigured environments, applications must handle errors transparently rather than silently falling back to an insecure generator.

### 2.2 `getInstance("DRBG")` Requests a Specific Engine

`SecureRandom.getInstance("DRBG")` requests a provider registering the `DRBG` algorithm for the `SecureRandom` engine. You can go further with the overload taking `SecureRandomParameters` to specify requirements:

```java
SecureRandom drbg = SecureRandom.getInstance(
        "DRBG",
        DrbgParameters.instantiation(
                128,
                DrbgParameters.Capability.RESEED_ONLY,
                null));
```

This is an **embedded illustrative snippet**; a complete program must import `SecureRandom` and `DrbgParameters` (see Practice 2).

`128` is the **minimum requested** security strength, `RESEED_ONLY` requests reseed capability, and `null` passes no personalization string. If the provider cannot satisfy the request, instantiation fails; do not assume "DRBG" is always available on every Java runtime.

The JDK uses NIST SP 800-90A families such as Hash_DRBG, HMAC_DRBG, or CTR_DRBG depending on provider/configuration. `DRBG` in `getInstance` is the **SecureRandom service algorithm** name, not a direct selector for Hash/HMAC/CTR. To inspect the concrete implementation, check provider documentation and environment configuration.

## 3. DRBG Lifecycle: Instantiate → Generate → Reseed

A DRBG maintains internal state across phases:

1. **Instantiate:** takes an entropy source and parameters to establish secret state. Some implementations initialize lazily, pulling entropy only upon first byte generation.
2. **Generate:** produces bytes from current state via `nextBytes` and updates state; if no fresh entropy access is needed, this is usually faster than reading fresh entropy on every call.
3. **Reseed:** pulls fresh entropy and refreshes state when policy, algorithm limits, or application requirements demand it. This step may wait on the entropy source.
4. **Prediction resistance (PR):** when requested and supported by the provider, byte generation can require fresh entropy to better protect against prior state compromise. Real PR cannot exist merely by flipping a flag without a trustworthy entropy source.

### 3.1 Capability: Minimum Request vs. Effective Features

`DrbgParameters.Capability` has three levels:

| Requested capability | Minimum guarantee | What you can do |
| --- | --- | --- |
| `NONE` | No guaranteed reseed or PR support | Implementation *may* still have higher capabilities than requested |
| `RESEED_ONLY` | Supports reseeding | Can call `reseed(...)`; PR support is not guaranteed |
| `PR_AND_RESEED` | Supports both reseeding and PR | Can request prediction resistance during generate/reseed |

**Do not equate "requested" with "effective."** A provider may return a higher capability than the minimum requested. After obtaining the instance, inspect:

```java
var params = drbg.getParameters();
if (params instanceof DrbgParameters.Instantiation actual) {
    int effectiveStrength = actual.getStrength();
    boolean canReseed = actual.getCapability().supportsReseeding();
    boolean canRequestPR =
            actual.getCapability().supportsPredictionResistance();
}
```

This is an **embedded code snippet** inside a method that already has `SecureRandom drbg` and imports `DrbgParameters`. Returned values describe the **effective** configuration (per API contract), which need not be identical to the requested parameters.

### 3.2 Parameters Used During Generate and Reseed

- `DrbgParameters.instantiation(strength, capability, personalizationString)`: configuration when creating the DRBG; `strength = -1` selects the default instantiation strength.
- `DrbgParameters.nextBytes(strength, predictionResistance, additionalInput)`: parameters for a *single* `nextBytes(bytes, params)` call; `strength = -1` uses effective strength. `predictionResistance=true` requests PR for that call, usable only when supported.
- `DrbgParameters.reseed(predictionResistance, additionalInput)`: parameters for `reseed(params)`; this operation reads entropy per provider mechanics.
- `personalizationString` and `additionalInput` provide context separation and state diversification per the DRBG interface; they **do not replace a secure entropy source** and are not mandatory "secret keys."

If you only requested `RESEED_ONLY`, do not call `nextBytes(..., DrbgParameters.nextBytes(-1, true, ...))` assuming the provider will support it. Raising requested capability/strength can cause `getInstance` to fail. Explicit reseed operations can raise latency due to entropy source interaction.

## 4. Why and When Can Random Sources Block?

**Blocking** means the calling thread waits before the method returns; this differs from "CPU byte generation taking a few milliseconds." Per the Java 17 API, depending on the implementation, **`nextBytes`, `generateSeed`, and `reseed` can all block while gathering entropy**.

Three common situations:

| Situation | What can happen | Note |
| --- | --- | --- |
| First use of PRNG | Seeds from the entropy source, may wait | Fast `new SecureRandom()` does not prove the first `nextBytes` will be fast |
| `generateSeed(n)` or explicit `reseed()` | Provider contacts the seed/entropy source | Do not mechanically replace `nextBytes` with `generateSeed` |
| Requesting PR or provider auto-reseeding | New entropy demand occurs during generate | `DRBG` does not mean "non-blocking"; policy and environment decide |

Commonly discussed OS mechanisms include `/dev/random` and `/dev/urandom` on Unix-like systems, OS randomness APIs on Windows, HSM devices, or software providers. **Do not apply a blanket rule like "`/dev/random` always blocks" or "`/dev/urandom` is always the fix"**: behavior has evolved across kernel versions and provider integrations. Inspect actual JDK/OS configuration and verify by measurement.

For web apps or workers with SLAs, also consider:

- During **startup or first use**, the application may pause waiting for entropy before the first request completes.
- If every request invokes `getInstanceStrong()` or `reseed()`, entropy access and latency can spike dramatically.
- When all threads share one `SecureRandom` instance, Java guarantees **thread-safe concurrent access**; however, the provider may synchronize internally causing contention, so throughput/latency must still be measured.
- In VMs/containers, host dependencies, runtime images, providers, and entropy sources can differ completely from a developer laptop. Inspect thread dumps and call timings rather than guessing from the OS name.

**No API for generating secrets can be guaranteed non-blocking on every runtime.** If the business requires timeouts, isolation, and backpressure, design processing boundaries up front; a caller-side timeout does not guarantee immediate interruption of a native operation waiting on entropy.

## 5. Practice 1: `getInstanceStrong` and URL-Safe Tokens

This program creates a token with `new SecureRandom()`, then inspects the provider chosen by `getInstanceStrong()`. **It does not print the token value**, avoiding secrets in logs.

Save **`StrongRandomDemo.java`** (Java 17+):

```java
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.security.Security;
import java.util.Base64;

public class StrongRandomDemo {
    public static void main(String[] args) {
        String property = Security.getProperty("securerandom.strongAlgorithms");
        System.out.println("strong config present: " +
                (property != null && !property.isBlank()));

        SecureRandom defaultRandom = new SecureRandom();
        byte[] tokenBytes = new byte[32];
        defaultRandom.nextBytes(tokenBytes);
        String token = Base64.getUrlEncoder()
                .withoutPadding().encodeToString(tokenBytes);

        System.out.println("token bytes: " + tokenBytes.length);
        System.out.println("token characters: " + token.length());
        System.out.println("default provider: " +
                defaultRandom.getProvider().getName());

        try {
            SecureRandom strong = SecureRandom.getInstanceStrong();
            byte[] sample = new byte[16];
            strong.nextBytes(sample);
            System.out.println("strong provider: " + strong.getProvider().getName());
            System.out.println("strong algorithm: " + strong.getAlgorithm());
            System.out.println("strong sample bytes: " + sample.length);
        } catch (NoSuchAlgorithmException e) {
            System.out.println("strong implementation unavailable");
        }
    }
}
```

Compile and run:

```bash
javac --release 17 StrongRandomDemo.java
java StrongRandomDemo
```

Example of **one actual run** on Windows/JDK with corresponding providers (provider/algorithm/config lines **may vary**):

```text
strong config present: true
token bytes: 32
token characters: 43
default provider: SUN
strong provider: SunMSCAPI
strong algorithm: Windows-PRNG
strong sample bytes: 16
```

Stable assertions when the program succeeds:

- `32` bytes for the token; unpadded Base64URL produces **43 characters** from 32 bytes regardless of actual byte values.
- `strong.sample` uses 16 bytes without printing secret bytes.
- `default provider`, `strong provider`, and `strong algorithm` **are runtime data**; do not hardcode sample names in portable assertions.
- `NoSuchAlgorithmException` is handled explicitly; if strong config is absent, the unavailable branch executes instead of silently falling back to `java.util.Random`.

A 32-byte token has a **256-bit width**, yet real security still depends on RNG/entropy quality and token lifecycle management. For session tokens, add expiration, revocation, transport/storage protection, and never log tokens.

**Comparison:** `getInstanceStrong()` is not mandatory for generating every token. A verified environment-default `SecureRandom` is a common choice; when policy mandates a specific provider, specify it explicitly and test in the target environment.

## 6. Practice 2: Requesting DRBG Strength/Reseed and Reading Effective Config

This program uses a **reseed-capable DRBG**, generates 32 bytes, and explicitly reseeds to demonstrate the API. In real production code, **manual reseeding on every request is unnecessary**; this illustrates the lifecycle.

Save **`DrbgParametersDemo.java`** (Java 17+):

```java
import java.nio.charset.StandardCharsets;
import java.security.DrbgParameters;
import java.security.SecureRandom;

public class DrbgParametersDemo {
    public static void main(String[] args) throws Exception {
        DrbgParameters.Instantiation requested =
                DrbgParameters.instantiation(
                        128,
                        DrbgParameters.Capability.RESEED_ONLY,
                        "lesson-3.6-v1".getBytes(StandardCharsets.UTF_8));

        SecureRandom random = SecureRandom.getInstance("DRBG", requested);
        if (!(random.getParameters() instanceof DrbgParameters.Instantiation actual)) {
            throw new IllegalStateException("No effective DRBG parameters");
        }

        byte[] bytes = new byte[32];
        random.nextBytes(
                bytes,
                DrbgParameters.nextBytes(
                        -1, false, "operation-1".getBytes(StandardCharsets.UTF_8)));

        System.out.println("algorithm: " + random.getAlgorithm());
        System.out.println("strength >= 128: " + (actual.getStrength() >= 128));
        System.out.println("reseed supported: " +
                actual.getCapability().supportsReseeding());
        System.out.println("generated bytes: " + bytes.length);

        random.reseed(DrbgParameters.reseed(false, null));
        System.out.println("reseed: OK");
    }
}
```

Compile and run:

```bash
javac --release 17 DrbgParametersDemo.java
java DrbgParametersDemo
```

When the runtime has a `DRBG` provider satisfying the requested strength and capability, verified sample output:

```text
algorithm: DRBG
strength >= 128: true
reseed supported: true
generated bytes: 32
reseed: OK
```

**Why are the boolean results `true`?** The factory succeeds only when minimum requested requirements are met; `getParameters()` reports effective settings. The example does not assume strength is exactly 128 or capability is exactly `RESEED_ONLY`: the provider may report a higher level.

Parameter breakdown:

1. `128`: minimum DRBG security strength, not "generate exactly 128 bits."
2. `RESEED_ONLY`: guarantees the reseed API is available; **does not** request prediction resistance.
3. `"lesson-3.6-v1"`: personalization string for context separation, not a secret seed.
4. `nextBytes(-1, false, "operation-1"... )`: uses effective strength, does not request PR for this call; additional input adds no fresh entropy.
5. `reseed(false, null)`: requests fresh entropy to update state; may block depending on entropy source/provider.

If no provider supplies `DRBG` or satisfies the capability, `getInstance` can throw `NoSuchAlgorithmException`. Under binding security policies, **never silently lower strength or fall back to a non-cryptographic RNG** to keep running.

### 6.1 When Prediction Resistance Is Truly Required

An application may request:

```java
DrbgParameters.Instantiation strongRequest =
        DrbgParameters.instantiation(
                256,
                DrbgParameters.Capability.PR_AND_RESEED,
                null);
SecureRandom prDrbg = SecureRandom.getInstance("DRBG", strongRequest);

byte[] output = new byte[32];
prDrbg.nextBytes(output, DrbgParameters.nextBytes(-1, true, null));
```

This is an **illustrative snippet inside a method with `SecureRandom`/`DrbgParameters` imported**, not a standalone runnable file. It **can fail** if the provider does not support 256-bit strength/PR; when it succeeds, `true` requests prediction resistance for that generation call. The provider may need fresh entropy and block the thread while executing. Never assume PR is guaranteed merely because 256 bits of data were requested.

## 7. Practice 3: Measuring Instance Creation and Byte Generation Separately

Measure **constructor/factory**, **first `nextBytes`**, and **subsequent calls** separately because many implementations seed lazily. The program runs in default mode or accepts `strong` as an argument to observe `getInstanceStrong()`.

Save **`RandomLatencyProbe.java`**:

```java
import java.security.SecureRandom;

public class RandomLatencyProbe {
    public static void main(String[] args) throws Exception {
        long start = System.nanoTime();
        SecureRandom random =
                args.length > 0 && args[0].equals("strong")
                ? SecureRandom.getInstanceStrong()
                : new SecureRandom();
        long constructed = System.nanoTime();

        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
        long first = System.nanoTime();

        random.nextBytes(bytes);
        long second = System.nanoTime();

        System.out.println("algorithm: " + random.getAlgorithm());
        System.out.println("provider: " + random.getProvider().getName());
        System.out.printf("construct: %.3f ms%n",
                (constructed - start) / 1_000_000.0);
        System.out.printf("first nextBytes: %.3f ms%n",
                (first - constructed) / 1_000_000.0);
        System.out.printf("second nextBytes: %.3f ms%n",
                (second - first) / 1_000_000.0);
    }
}
```

Compile and run (run `strong` **only in an authorized test environment that can tolerate latency**):

```bash
javac --release 17 RandomLatencyProbe.java
java RandomLatencyProbe
java RandomLatencyProbe strong
```

A default-mode run on a test environment produced:

```text
algorithm: DRBG
provider: SUN
construct: 38.408 ms
first nextBytes: 18.310 ms
second nextBytes: 0.059 ms
```

**All provider names and measured timings vary with JVM, OS, machine load, JIT, entropy source, and warmup state.** These are illustrative measured numbers, definitely not a benchmark or guaranteed threshold. A slower first call can stem from seeding, class loading, or startup factors; a single measurement **does not prove** entropy starvation.

When diagnosing a real system, record:

- JVM/vendor/version, OS, and VM/container environment;
- `getAlgorithm()`, `getProvider().getName()`, and relevant security properties;
- initialization time, first generation, subsequent calls; if reseeding occurs, measure it separately;
- frequency, p95/p99 percentiles, thread dumps/call stacks during stalls, and correlation with startup or load.

Never treat pointing `/dev/random` elsewhere or changing `java.security.egd` as a universal "cure-all": configuration semantics depend on implementation and can weaken system entropy policy. Check provider/JDK documentation and perform a security review before changing it.

## 8. Practical Choices in Applications

| Need | Reasonable starting point | What to avoid |
| --- | --- | --- |
| Session tokens, CSRF tokens, one-time secrets | Verified environment `SecureRandom`; sufficient `nextBytes` length, safe encoding | `Math.random()`, `java.util.Random`, time-based seeds, logging secrets |
| High-value / long-lived keys | Dedicated key-generation APIs and explicit RNG/provider policy; consider `getInstanceStrong()` if policy requires | Assuming strong is fast or identical across all runtimes |
| Specific DRBG strength/capability | `getInstance("DRBG", DrbgParameters.instantiation(...))`, inspect effective parameters | Requesting `PR_AND_RESEED` without evaluating entropy/latency cost |
| Low-latency APIs or high-concurrency startup | Benchmark on target runtime, controlled initialization, avoid unnecessary reseed/factory calls on hot paths | Promising "non-blocking" just because the algorithm is named DRBG |
| HSM/FIPS/provider policies | Select vetted providers via config/overload, test errors and lifecycle | Relying on provider names seen only on developer laptops |

### 8.1 Lifecycle Management and Concurrency

A `SecureRandom` instance is **safe for concurrent calls across threads** under the Java 17 contract. However, a provider may synchronize internally, so high-throughput apps should still measure contention. Creating a new instance per request does not automatically improve security and can increase initialization/entropy overhead.

A common pattern is holding an appropriate `SecureRandom` in a dedicated random-bytes component injected where needed; ensure RNG configuration is verified early at startup. If policy requires strong/HSM, treat initialization failure as an observable configuration/security error rather than silently falling back to an unsuitable RNG.

### 8.2 How to Test When Output Is Random

- Unit tests focus on **format, length, validity constraints, and error handling**, never asserting a fixed token byte value.
- You may inject a mock byte source in pure logic tests (never wired into real secret paths); production always uses a proper `SecureRandom`.
- Two byte generations have negligible collision probability yet are not **mathematically guaranteed distinct**; probabilistic one-off assertions like `assertNotEquals(a, b)` are unnecessary for API contracts.
- Never write raw tokens, seeds, or RNG state to logs/traces/test reports. For observability, log configuration and latency metadata, never secrets.

## 9. Common Mistakes and Fixes

1. **"`getInstanceStrong` never blocks because it's strong."** False: it selects from a property, whereas blocking depends on provider/entropy source; measure creation and generation separately.
2. **"DRBGs are deterministic, so they're insecure."** False: cryptographic DRBGs require unpredictable seeds; "deterministic" describes generation from state, not seed quality.
3. **"32 bytes of output means 256-bit strength."** False: distinguish byte length from provider-guaranteed strength.
4. **"`setSeed(System.nanoTime())` prevents blocking and adds entropy."** False and potentially weakens security, especially if injected before provider self-seeding. Let the provider use trusted entropy.
5. **"Request PR/reseed on every request for maximum security."** Not generally right: entropy/latency cost can be severe; rely on a clear threat model and policy.
6. **"Call `generateSeed(32)` instead of `nextBytes` everywhere."** False: the seed-material API may access entropy differently and is not a universal token-issuance primitive.
7. **"Same Java 17 means identical provider/algorithm/timing."** False: distribution, OS, security config, and hardware determine actual selection.
8. **"If DRBG/strong is missing, fall back to `Random`."** Unacceptable for secrets; fail explicitly or select a policy-approved, verified secure implementation.
9. **"Not sure what blocks, so just add a timeout."** Caller-level timeouts do not necessarily interrupt native calls waiting on entropy. Design thread budgets, isolation, retry/backpressure, and observability.

## 10. Self-Check Questions

**Q1.** How does `getInstanceStrong()` choose an algorithm?  
From the `securerandom.strongAlgorithms` property and available runtime providers/algorithms, not from a single universal "Strong" Java algorithm.

**Q2.** Does a DRBG's `nextBytes` necessarily access OS entropy on every call?  
No. It usually generates from internal state after instantiation, though it may access entropy at instantiation/reseed or when policy/PR requires it.

**Q3.** What does requesting `RESEED_ONLY` guarantee?  
At least reseed capability, **not** prediction resistance; inspect `getParameters()` to see effective capabilities.

**Q4.** What should you inspect to diagnose `SecureRandom` latency in production?  
Algorithm, provider, security properties, JVM/OS, init/first/steady-state timings, reseed timing, and thread stacks; never conclude from a single measurement.

**Q5.** Why avoid `setSeed` with time values?  
Time data has low/predictable entropy; calling it too early can also suppress the PRNG's automatic self-seeding per the API contract.

Remember the model: **entropy source → seed/reseed → DRBG state → `nextBytes`**, while **`getInstanceStrong()` is a platform-policy implementation selector**. A sound choice balances cryptographic security, provider compatibility, and measured latency in the real environment.

## Official References

- [Java 17 — SecureRandom API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): instance selection, seeding, thread safety, and blocking behavior.
- [Java 17 — DrbgParameters API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/DrbgParameters.html): instantiate, nextBytes, reseed, and DRBG configuration.
- [Java 17 — DrbgParameters.Capability](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/DrbgParameters.Capability.html): NONE, RESEED_ONLY, and PR_AND_RESEED.
- [Java 17 — JCA Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html): SecureRandom/provider architecture and security configuration.
- [NIST SP 800-90A Rev. 1](https://csrc.nist.gov/pubs/sp/800/90/a/r1/final): foundational concepts of deterministic random bit generators.

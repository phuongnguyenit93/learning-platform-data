# 2.8 Handling `NoSuchAlgorithmException`, `NoSuchProviderException`, and Parameter Errors in JCA

In the Java Cryptography Architecture (JCA), a cryptographic operation typically proceeds through three stages: **selecting the service type/algorithm and provider**, **initializing with keys/parameters**, and **executing the operation**. Which stage throws an error tells you the right fix: fix configuration, fix input data/keys, or handle verification results. Never lump everything into “encryption error” and try a weaker algorithm.

This lesson focuses on JCA/JCE exceptions when using engines such as `MessageDigest`, `Signature`, `KeyGenerator`, `KeyPairGenerator`, `Mac`, and `Cipher`. Examples run on **Java 17+**; exact algorithms, providers, and runtime rules remain subject to the installed JDK, security policy, and providers.

## 1. Where Do Exceptions Occur in the Execution Flow?

```text
Application config: engine + algorithm/transformation name + provider (optional)
        |
        v
getInstance(...)  --> Missing algorithm?       NoSuchAlgorithmException
        |           --> Named provider missing?  NoSuchProviderException
        |           --> Unsupported padding?     NoSuchPaddingException (Cipher)
        v
init(...)         --> Incompatible key?        InvalidKeyException
        |           --> Invalid parameters?      InvalidAlgorithmParameterException
        |           --> Bad size/value?          InvalidParameterException (API-dependent)
        v
update/doFinal    --> Unauthenticated AEAD?    AEADBadTagException
        |           --> Other runtime error?     Specific API exceptions
        v
Verified result
```

At `getInstance(...)`, JCA looks up an **implementation of the exact engine type** from security providers. The same string can be valid for one engine and meaningless for another: `SHA-256` is a `MessageDigest` name, `HmacSHA256` is a `Mac` name, `AES` is a key/algorithm name for `KeyGenerator`, and `AES/GCM/NoPadding` is a `Cipher` transformation.

| Exception | Checked? | Typically thrown at | Meaning and handling |
| --- | --- | --- | --- |
| `NoSuchAlgorithmException` | Yes | `getInstance(...)` | No implementation for the requested **engine + algorithm/transformation + provider**; check name, engine type, JDK version, and provider capabilities. |
| `NoSuchProviderException` | Yes | `getInstance(algorithm, String providerName)` | The specified provider name **is not registered** in the JVM; check provider configuration/registration before switching algorithms. |
| `NoSuchPaddingException` | Yes | `Cipher.getInstance(...)` | The transformation's padding is unsupported; verify the full `algorithm/mode/padding`, do not swap padding arbitrarily. |
| `InvalidKeyException` | Yes | `Cipher.init(...)`, `Mac.init(...)`, `Signature.initSign/initVerify(...)` | Key has wrong type, size, encoding, or is rejected by the provider. |
| `InvalidAlgorithmParameterException` | Yes | `Cipher.init(..., AlgorithmParameterSpec)`, `KeyPairGenerator.initialize(AlgorithmParameterSpec)` | Incompatible algorithm parameter structure/values (e.g., GCM parameters or unsupported group/curve). |
| `InvalidParameterException` | No | Some `initialize(int)` overloads, `Cipher.init` with wrong `opmode` | Invalid numeric parameter/mode per API contract; it is a `RuntimeException`. |
| `IllegalArgumentException` / `NullPointerException` | No | Input checks and some factories/constructors | Usually caused by null, empty, or malformed program inputs; exact type depends on the **overload**, do not assume every API throws the same one. |
| `InvalidKeySpecException` | Yes | `KeyFactory.generatePrivate/generatePublic`, `SecretKeyFactory.generateSecret` | Unsuitable key representation (`KeySpec`) or cannot be converted to a key for that algorithm. |
| `AEADBadTagException` | Yes | `Cipher.doFinal(...)` during AEAD decryption | Message authentication failed: possibly mismatched ciphertext, key, IV/nonce, tag, or AAD. Never return plaintext or bypass authentication to “salvage” data. |
| `ProviderException` | No | Inside provider | Runtime error in the provider/device; diagnose the environment rather than treating it as normal input validation. |

**Remember:** `GeneralSecurityException` is the superclass of many checked exceptions above, yet it **does not cover** `InvalidParameterException`, `IllegalArgumentException`, or `ProviderException`. Catching `GeneralSecurityException` too early loses specific handling branches; catching `Exception` and swallowing it hides the root cause.

## 2. Accurately Distinguishing “Missing Algorithm” from “Missing Provider”

Using `MessageDigest` as an example:

```java
MessageDigest.getInstance("SHA-256");
// Automatically locates a provider supporting MessageDigest/SHA-256 in JVM configuration.

MessageDigest.getInstance("SHA-256", providerName);
// Requires the exact registered provider named providerName.

MessageDigest.getInstance("SHA-256", providerObject);
// Uses a specific Provider object; this object need not already be registered.
```

The three overloads have different contracts:

1. **No provider specified:** `NoSuchAlgorithmException` when no allowed/available provider supplies a matching implementation. There is no `NoSuchProviderException` because no provider name was requested.
2. **Specifying a `String` name:** `NoSuchProviderException` when the name is not registered; `NoSuchAlgorithmException` when the provider exists but does not supply `MessageDigest/SHA-256`. With `MessageDigest.getInstance(String, String)`, a null/empty provider name causes `IllegalArgumentException`, while a null algorithm causes `NullPointerException`.
3. **Specifying a `Provider` object:** no `NoSuchProviderException` in the signature; a provider can be passed directly even if unregistered. If the implementation is missing, it still throws `NoSuchAlgorithmException`; a null provider object causes `IllegalArgumentException`.

Do not check a provider by name and conclude it supports every algorithm. `Security.getProvider(name) != null` **only proves that provider name is registered**; calling `getInstance` on the exact engine is the real capability check. For `Cipher`, you also need to verify the transformation and `init` because implementation/provider selection may continue during initialization.

### 2.1 Common Confusions

- `MessageDigest.getInstance("AES")` uses the wrong engine: `AES` is a cipher/key algorithm, not a digest.
- `Cipher.getInstance("SHA-256")` uses the wrong engine: `SHA-256` is for hashing, not an encryption transformation.
- `Cipher.getInstance("AES")` omits mode and padding, so it can use provider-dependent defaults that fail security requirements. Configure a full transformation like `AES/GCM/NoPadding` when appropriate to the design.
- Provider names such as `SunJCE`, `SUN`, or HSM/PKCS#11 providers must not be assumed present on every JVM. **Provider names are distinct from algorithm names**.
- “No provider named X” and “provider X exists but does not support algorithm Y” require two different fixes.

## 3. Runnable Example: Diagnosing Lookup Errors

Save with the exact filename **`JcaLookupDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.NoSuchProviderException;
import java.security.Security;
import java.util.HexFormat;

public final class JcaLookupDemo {
    public static void main(String[] args) throws NoSuchAlgorithmException {
        try {
            MessageDigest.getInstance("NO_SUCH_DIGEST_FOR_DEMO_2026");
        } catch (NoSuchAlgorithmException ex) {
            System.out.println("1. MessageDigest algorithm not found");
        }

        String missingProvider = "TRAINING_PROVIDER_NOT_INSTALLED";
        while (Security.getProvider(missingProvider) != null) {
            missingProvider += "_";
        }

        try {
            MessageDigest.getInstance("SHA-256", missingProvider);
        } catch (NoSuchProviderException ex) {
            System.out.println("2. Provider is not registered");
        }

        MessageDigest sha256 = MessageDigest.getInstance("SHA-256");
        byte[] bytes = sha256.digest("abc".getBytes(StandardCharsets.UTF_8));
        System.out.println("3. SHA-256(abc): " + HexFormat.of().formatHex(bytes));
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 JcaLookupDemo.java
java JcaLookupDemo
```

Output on a standard Java 17+ JDK (with no custom provider intentionally registering the demo algorithm name):

```text
1. MessageDigest algorithm not found
2. Provider is not registered
3. SHA-256(abc): ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
```

**Explanation:**

- The first call requests an uninstalled digest algorithm. The exception is thrown **before** hashing any data.
- The second call uses the available algorithm `SHA-256` but requests an unregistered provider name; the `while` loop avoids an accidental collision with an existing provider.
- The final call lets JCA automatically select a provider supporting `SHA-256` and hashes `abc`. `HexFormat` has existed since Java 17, so no external library is needed.

This is a demonstration to **distinguish the two exceptions**, not a mechanism for sequentially probing provider names in production. Applications should configure vetted algorithms and only pin providers when specific technical or compliance requirements demand it.

## 4. At Which Stage Do “Parameter Errors” Arise?

**(a) Java/API input arguments:** `null`, empty names, wrong operation modes, negative sizes. Validate early using `Objects.requireNonNull`, check allowed value sets and lengths, then raise appropriate programming/configuration errors. Do not rely on the same exception type across all engines.

**(b) Algorithm parameters:** `GCMParameterSpec`, `PBEParameterSpec`, `ECGenParameterSpec`, and other `AlgorithmParameterSpec`s. An object may be constructible yet still rejected by the provider at `init`, typically with `InvalidAlgorithmParameterException`. Support for tag sizes, key sizes, curves, or parameter sets can depend on the provider and security policy.

**(c) Keys:** `SecretKey`, `PrivateKey`, and `PublicKey` may have the wrong algorithm, length, or be incompatible with the operation. `InvalidKeyException` occurs when initializing `Cipher`, `Mac`, or `Signature`; do not convert it into `NoSuchAlgorithmException` or silently try another key. If the error occurs while converting a `KeySpec`, check `InvalidKeySpecException`.

**(d) Input message after initialization:** for authenticated encryption (AEAD) such as AES-GCM, `AEADBadTagException` is an **authentication failure**, which does not mean a provider is missing nor necessarily “invalid input parameter”. All of key, nonce/IV, tag, and AAD must match across both ends.

Symbolic example:

```java
// Transformation selection: lookup errors may be NoSuchAlgorithmException
// or NoSuchPaddingException.
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");

// Initialization: wrong key may throw InvalidKeyException;
// unsuitable GCM parameters may throw InvalidAlgorithmParameterException.
cipher.init(Cipher.ENCRYPT_MODE, aesKey, new GCMParameterSpec(128, iv));

// During GCM decryption: doFinal(...) may throw AEADBadTagException
// if data fails authentication. Never bypass this check.
```

The snippet above is **API-by-API illustrative code**, not a standalone program: `aesKey`, `iv`, and calling context must be defined. A full runnable example appears in the next section.

### 4.1 Safe Parameter Checklist for AES-GCM

- Use only valid AES keys, typically **128/192/256 bits** per policy. Never use a raw password or arbitrary UTF-8 string as an AES key; use an appropriate KDF if deriving from a password.
- In the example, use a **12-byte (96-bit)** IV and a **128-bit** tag. That is the widely recommended configuration, though not an assertion that every provider accepts every size combination.
- **Never reuse the same `(key, IV/nonce)` pair when encrypting with GCM.** At high volume, design nonce management to bound collisions; simply generating a random IV in a small demo does not replace that design.
- The IV can be public alongside the ciphertext; the IV is not a secret key. The tag is typically appended at the end of the byte array returned by GCM `Cipher.doFinal`.
- AAD, if used, must match identically between encryption and decryption and be passed via `updateAAD(...)` **before** the data payload.
- Never release unauthenticated plaintext, and never drop the tag, switch modes, or change algorithms to work around `AEADBadTagException`.

## 5. Runnable Example: Separating Initialization Errors from AES-GCM Authentication Errors

This example uses a default provider supporting `AES/GCM/NoPadding`, packs `IV(12 bytes) || ciphertext+tag`, encrypts/decrypts successfully, and intentionally flips a tag bit to observe the failure branch. Save with the exact name **`GcmFailureDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.InvalidAlgorithmParameterException;
import java.security.InvalidKeyException;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.NoSuchPaddingException;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class GcmFailureDemo {
    private static final int IV_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final int TAG_BYTES = TAG_BITS / 8;

    public static void main(String[] args) {
        try {
            KeyGenerator generator = KeyGenerator.getInstance("AES");
            generator.init(128);
            SecretKey key = generator.generateKey();

            byte[] payload = encrypt("Hello JCA".getBytes(StandardCharsets.UTF_8), key);
            byte[] recovered = decrypt(payload, key);
            System.out.println("Decrypted: " + new String(recovered, StandardCharsets.UTF_8));

            byte[] tampered = payload.clone();
            tampered[tampered.length - 1] ^= 1; // Flip one bit of the tag.
            try {
                decrypt(tampered, key);
                throw new AssertionError("Modified tag was still accepted");
            } catch (AEADBadTagException ex) {
                System.out.println("Modified tag: authentication failed");
            }

        } catch (NoSuchAlgorithmException | NoSuchPaddingException ex) {
            throw new IllegalStateException("Algorithm/transformation unavailable", ex);
        } catch (InvalidKeyException | InvalidAlgorithmParameterException ex) {
            throw new IllegalArgumentException("Invalid key or parameters", ex);
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException("Cryptographic processing error", ex);
        }
    }

    private static byte[] encrypt(byte[] plain, SecretKey key)
            throws GeneralSecurityException {
        byte[] iv = new byte[IV_BYTES];
        new SecureRandom().nextBytes(iv);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, iv));
        byte[] ciphertextWithTag = cipher.doFinal(plain);

        byte[] payload = new byte[IV_BYTES + ciphertextWithTag.length];
        System.arraycopy(iv, 0, payload, 0, IV_BYTES);
        System.arraycopy(ciphertextWithTag, 0, payload, IV_BYTES,
                ciphertextWithTag.length);
        return payload;
    }

    private static byte[] decrypt(byte[] payload, SecretKey key)
            throws GeneralSecurityException {
        if (payload == null || payload.length < IV_BYTES + TAG_BYTES) {
            throw new IllegalArgumentException("Payload missing IV or tag");
        }

        byte[] iv = Arrays.copyOfRange(payload, 0, IV_BYTES);
        byte[] ciphertextWithTag = Arrays.copyOfRange(payload, IV_BYTES,
                payload.length);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, iv));
        return cipher.doFinal(ciphertextWithTag);
    }
}
```

```bash
javac -encoding UTF-8 GcmFailureDemo.java
java GcmFailureDemo
```

Output with a typical JDK provider supporting AES-GCM:

```text
Decrypted: Hello JCA
Modified tag: authentication failed
```

Meaning of each branch:

- `NoSuchAlgorithmException` / `NoSuchPaddingException`: the engine or transformation is unavailable in this environment. This is usually a **capability/configuration** error that should be detected at startup.
- `InvalidKeyException` / `InvalidAlgorithmParameterException`: check key source, key type, size, transformation, IV/tag/AAD, and provider. **Do not** fall back to a weaker cipher/mode.
- `AEADBadTagException`: handle as an **unauthenticated message**, returning an appropriate response to the caller without exposing keys, plaintext, or sensitive cryptographic details.
- `IllegalArgumentException` from a payload lacking valid structure is a **program input-validation** error; it differs from checked exceptions thrown by the provider.
- The final `GeneralSecurityException` catch is only for unclassified cases; still preserve `cause` for investigation in trusted systems.

Flipping a bit in the tag triggers an authentication failure on a normal GCM provider; the security principle is to **reject** data when tag verification fails. The example does not cover long-term key storage, key rotation, or cross-version data formats; those require dedicated design in real systems.

## 6. Proper Error-Handling Strategy in Applications

### 6.1 Categorizing by Cause and Timing

| Category | Examples | Recommended action |
| --- | --- | --- |
| **Invalid configuration / capability** | Wrong algorithm, wrong transformation, uninstalled provider, missing HSM provider | Check immediately at startup; log sanitized metadata about engine, algorithm name, provider name, and environment; **fail fast** instead of silently operating with another algorithm. |
| **Invalid data / key / parameters** | Wrong key length, rejected `AlgorithmParameterSpec`, payload missing IV/tag | Verify data source; separate client input errors from internal configuration bugs; handle per API contract. |
| **Authentication failure** | `AEADBadTagException` | Reject message; do not return plaintext; do not retry unauthenticated modes to recover. |
| **Provider / runtime error** | `ProviderException`, cryptographic device error, changed provider capabilities | Collect controlled telemetry, alert, and investigate the environment; retry only when the operation is genuinely safe/idempotent and policy permits. |

Clearly determine **who owns the configuration** before deciding the response. If the application hardcodes `AES/GCM/NoPadding` and the JVM lacks support, that error must usually be fixed at deployment, not blamed on user input. If an API receives a client payload missing an IV, the application can reject the input per contract. For encrypted payloads with a bad tag, never leak enough detail to create an oracle distinguishing failure types.

### 6.2 Startup Configuration Validation Pattern

```java
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.NoSuchProviderException;
import java.security.Security;
import java.util.Set;

public final class DigestFactory {
    private static final Set<String> ALLOWED = Set.of("SHA-256", "SHA-384", "SHA-512");

    public static MessageDigest create(String algorithm, String providerName)
            throws NoSuchAlgorithmException, NoSuchProviderException {
        if (algorithm == null || !ALLOWED.contains(algorithm)) {
            throw new IllegalArgumentException("Digest algorithm outside allowlist");
        }

        // null/blank means let JCA select the provider automatically.
        if (providerName == null || providerName.isBlank()) {
            return MessageDigest.getInstance(algorithm);
        }

        if (Security.getProvider(providerName) == null) {
            throw new NoSuchProviderException("Provider is not registered: "
                    + providerName);
        }
        return MessageDigest.getInstance(algorithm, providerName);
    }
}
```

This is a **helper class that compiles standalone but has no `main`**: call `DigestFactory.create(...)` during application configuration initialization. Algorithm names are restricted by an allowlist; `providerName` is optional when policy permits provider-independent execution. If policy **mandates an HSM/specific provider**, never fall back to the default provider upon catching `NoSuchProviderException`.

Never use untrusted request data to decide algorithms/providers. If migration support is needed, design a **format version + approved algorithm allowlist**; only switch among equivalent policy-compliant configurations, never falling back from modern algorithms to MD5, SHA-1 for security functions, DES, ECB, or unauthenticated modes.

### 6.3 Ordered Diagnostics

1. **Identify the exact API that threw the error:** `MessageDigest`, `Cipher`, `KeyPairGenerator`, or `Signature`? Record whether it was `getInstance`, `init`, or `doFinal` instead of guessing from the exception message alone.
2. **Verify exact names and engine types:** `SHA-256` differs from `HmacSHA256`; `AES/GCM/NoPadding` is a `Cipher` transformation; do not adjust casing by guesswork alone.
3. **If a provider was specified by name:** is `Security.getProvider(providerName)` `null`? If the provider exists, call the exact `getInstance` to verify the service/algorithm. You can list `Security.getProviders()` and `Security.getAlgorithms("MessageDigest")` to inspect the environment, though lists do not replace actual initialization.
4. **Confirm runtime details:** JDK version/vendor, security properties, provider priority, external provider modules/dependencies, HSM/PKCS#11, and dev/test/prod differences. An implementation present on a laptop is not guaranteed to exist in a production container.
5. **If failing at `init`:** compare the `Key`'s algorithm, key size, mode, `AlgorithmParameterSpec`, tag/IV/nonce, policy, and the API overload used.
6. **If failing at `doFinal`:** check payload format, integrity, and AAD. With AEAD, classify authentication failures; never log keys, plaintext, or sensitive cryptographic material.
7. **Log root cause under control:** in internal logs record exception class, stage, non-sensitive algorithm/provider names, correlation ID, and `cause`; for public responses return safe messages without exposing stack traces or provider internals to clients.

The diagnostic snippet below lists only provider/algorithm **names**, outputting no cryptographic material. Run in a trusted environment when needed:

```java
import java.security.Provider;
import java.security.Security;

public class JcaEnvironmentInfo {
    public static void main(String[] args) {
        for (Provider provider : Security.getProviders()) {
            System.out.println("Provider: " + provider.getName());
        }
        System.out.println("Digest algorithms: "
                + Security.getAlgorithms("MessageDigest"));
    }
}
```

Output **depends on the JVM**, so there is no fixed stdout. Never use this list to pick a random “first algorithm that works”.

## 7. Anti-Patterns and Fixes

| Wrong approach | Why it is dangerous / hard to debug | Replacement |
| --- | --- | --- |
| `catch (Exception e) { return null; }` | Swallows root cause, creating `NullPointerException`s far from the source. | Classify exceptions, preserve `cause`, return/throw contextual errors. |
| On `NoSuchAlgorithmException`, fall back to `MD5`, `SHA-1`, `DES`, or `AES/ECB/...`. | Silently lowers security standards; may alter data semantics. | Check configuration, dependencies, and providers; fail fast or migrate under approved policy. |
| Catch `NoSuchProviderException`, drop the provider name, and retry default. | May route operations outside a mandatory HSM/provider. | Only fall back when policy explicitly allows it; otherwise stop and report deployment error. |
| Lump `InvalidKeyException`, `AEADBadTagException`, and `NoSuchAlgorithmException` into “wrong password”. | Hides system bugs, leaks logic, and misleads operations. | Separate configuration, parameter/key, and authentication failure categories. |
| Pass free-form strings from requests directly into `Cipher.getInstance`. | Callers can dictate algorithms/modes outside policy. | Fix configuration or map version codes onto an allowlist. |
| Reuse an IV with the same GCM key or ignore `AEADBadTagException`. | Compromises confidentiality/integrity of data. | Guarantee unique nonces; reject unauthenticated messages. |
| Write keys, plaintext, raw secrets, or full stack traces to public logs. | Leaks sensitive data. | Log error codes/correlation IDs and non-secret config info in protected logs. |

## 8. Knowledge Self-Check

**Scenario A.** `MessageDigest.getInstance("AES")` throws `NoSuchAlgorithmException`. Should you install another provider right away?  
**Answer:** First check the **engine**; `AES` is not a digest. Use `MessageDigest` for `SHA-256` or choose the engine matching your real goal. Do not assume a missing provider by default.

**Scenario B.** `MessageDigest.getInstance("SHA-256", "MyHsm")` throws `NoSuchProviderException`.  
**Answer:** The name `MyHsm` is not registered in the JVM. Check provider installation/initialization, name, and runtime config. If policy mandates an HSM, stop rather than switching providers automatically.

**Scenario C.** A provider named `MyHsm` exists, yet the same call throws `NoSuchAlgorithmException`.  
**Answer:** The provider exists but does not supply the requested `MessageDigest/SHA-256` implementation. Check exact engine, algorithm, provider capabilities, and policy.

**Scenario D.** `Cipher.getInstance("AES/GCM/NoPadding")` succeeds, but `init` fails.  
**Answer:** Investigate `InvalidKeyException` or `InvalidAlgorithmParameterException`, rather than assuming an algorithm is missing. Check the key, tag/nonce, and provider contract.

**Scenario E.** `Cipher.doFinal` during GCM decryption throws `AEADBadTagException`.  
**Answer:** Authentication failed; never return plaintext and never switch to an unauthenticated mode. Investigate payload origin, key, IV/nonce, tag, AAD, and data format.

### Completion Criteria

Learners can: (1) pinpoint the exact stage throwing an error; (2) distinguish the three `getInstance` provider overloads; (3) separate `InvalidKeyException`, `InvalidAlgorithmParameterException`, `InvalidParameterException`, and authentication errors; (4) initialize JCA/JCE with explicit configuration and **without security-downgrading fallbacks**; (5) reproduce, diagnose, and report errors preserving root cause without leaking secrets.

## Official Documentation

- [Java SE 21 — MessageDigest](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/MessageDigest.html): the three `getInstance` overloads and exceptions.
- [Java SE 21 — NoSuchProviderException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/NoSuchProviderException.html): definition when a requested provider is unavailable.
- [Java SE 21 — Cipher](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Cipher.html): transformations, `getInstance`, `init`, GCM/AEAD, and `doFinal`.
- [Java SE 21 — KeyPairGenerator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyPairGenerator.html): `InvalidParameterException` for keysize and `InvalidAlgorithmParameterException` for `AlgorithmParameterSpec`.
- [Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/21/docs/specs/security/standard-names.html): standard algorithm/engine names and transformations.
# 6.2 Specifying Full Transformations Instead of Relying on Provider Defaults

## 1. The Problem: `"AES"` Does Not Describe a Complete Encryption Operation

In the Java Cryptography Architecture (JCA/JCE), the `javax.crypto.Cipher` class is the shared **API (engine)** for many encryption operations. When calling `Cipher.getInstance(...)`, an application requests a **transformation**: the algorithm used together with how it operates and processes data.

For a common block cipher like AES, the three key components are:

1. **Algorithm** — the underlying primitive, e.g., `AES` (128-bit block).
2. **Mode** — how multiple blocks and an IV/nonce are handled, e.g., `ECB`, `CBC`, `GCM`, `CTR`.
3. **Padding** — how incomplete final blocks are handled, e.g., `PKCS5Padding` or `NoPadding`.

Java `Cipher` accepts both `"algorithm/mode/padding"` and `"algorithm"`:

```java
// Illustrative lines inside a method that handles checked exceptions:
Cipher ambiguous = Cipher.getInstance("AES");
Cipher explicit = Cipher.getInstance("AES/GCM/NoPadding");
```

The two calls are **not equivalent**. `"AES"` only names the algorithm; **the provider decides the default mode and padding**. `"AES/GCM/NoPadding"` explicitly requests GCM mode and no block padding. When running on a different JDK/provider or after reordering providers, `"AES"` may no longer mean what the author originally assumed.

**Foundational rule:** For algorithms that have multiple modes/paddings, specify the exact transformation matching the protocol, such as `Cipher.getInstance("AES/GCM/NoPadding")`, and configure the key, IV/nonce, tag, and AAD intentionally. Writing all three parts of the name alone does not automatically make the entire system secure.

Some ciphers have a complete name that **does not use three parts**, such as `ChaCha20-Poly1305`: use that algorithm's standard name, without inventing meaningless `/mode/padding` suffixes. "Full" means leaving no **critical unspecified defaults**, not mechanically counting `/` characters.

## 2. How Does a Provider Affect a Transformation?

### 2.1 Engine API and Providers

`Cipher.getInstance(transformation)` asks JCA/JCE to find a registered provider capable of supplying the requested cipher operation. A provider can be bundled with the JDK (such as `SunJCE` in Oracle/OpenJDK), belong to a third-party library, integrate with the OS, or access an HSM.

```text
Application: Cipher.getInstance("AES/GCM/NoPadding")
                           |
                           v
                  JCA Cipher engine
                           |
           search for matching implementation
                           |
            +--------------+--------------+
            |                             |
     Provider A supports           Provider B does not
            |                             |
        AES-GCM SPI                    skipped
```

If an application requests only `"AES"`, a provider may apply a **default mode/padding**; Java SE does not mandate a single secure default configuration across all providers.

The **Oracle JDK 17 JDK Providers Documentation** notes that `SunJCE` and `SunPKCS11` default to **ECB** with **PKCS5Padding** for many symmetric ciphers. In the case of `SunJCE`, the JCA documentation gives the example that `Cipher.getInstance("AES")` is equivalent to `Cipher.getInstance("AES/ECB/PKCS5Padding")`. That describes the respective provider/JDK release, **not a mandatory contract across all JDKs**.

ECB exposes repeating patterns across blocks under the same key; thus, unintentionally getting ECB from `"AES"` can introduce a vulnerability even when the code compiles, runs, and decrypts cleanly on the developer's machine.

### 2.2 Do Not Rely on `getAlgorithm()` to Infer the Default Mode

```java
Cipher unspecified = Cipher.getInstance("AES");
String requested = unspecified.getAlgorithm(); // Requested name: "AES"
```

`getAlgorithm()` returns the **requested name**, not a normalized report of the exact implicit parameters selected by the provider. `getProvider()` reveals the object's provider (and in some implementations may trigger provider selection), but **the provider name is no substitute for the transformation**. You must read the provider documentation and test the actual mode/parameters when auditing legacy systems.

When using the `Cipher.getInstance("AES/GCM/NoPadding", "SunJCE")` overload, the application depends on a registered provider with that exact name. Only pin a provider when explicitly required, such as for an HSM or compliance certification; otherwise, request the **exact standard transformation** and let JCA locate a compatible provider.

## 3. Comparing Common Cipher Requests

| Transformation | Defined Meaning | Security and Portability Notes |
| --- | --- | --- |
| `"AES"` | AES algorithm only | **Ambiguous**: provider picks default mode/padding. Avoid for encrypting application data. |
| `"AES/ECB/PKCS5Padding"` | AES, ECB, JCE-compatible padding | Syntactically explicit, yet **unsuitable for multi-block data**, because ECB exposes repeating block relationships. |
| `"AES/CBC/PKCS5Padding"` | AES, CBC, specified padding | Requires a valid IV and **separate authentication/integrity**. CBC does not detect deliberate tampering on its own. |
| `"AES/GCM/NoPadding"` | AES, GCM, no block padding | AEAD supporting encryption + authentication tag and AAD. Requires a **unique nonce per key**. |
| `"AES/CTR/NoPadding"` | AES, counter mode, no padding | Requires proper counter/nonce handling and a **separate MAC or authentication mechanism** if tamper resistance is needed. |
| `"AES/CFB/NoPadding"` | AES, CFB, no padding | **Feedback segment** size may be provider-chosen; specify e.g. `AES/CFB8/NoPadding` if the protocol requires CFB8 and the provider supports it. |

### 3.1 Explicit Does Not Automatically Mean Secure

Replacing `"AES"` with `"AES/ECB/PKCS5Padding"` only clarifies which mode/padding is in use—it does not fix ECB's flaw. Given two identical plaintext blocks, ECB with the same key produces two identical ciphertext blocks:

```text
      plaintext block P             plaintext block P
              |                             |
            AES(K)                        AES(K)
              |                             |
      ciphertext block C            ciphertext block C
```

CBC removes that specific trait via chaining and an IV, but CBC **does not provide an authentication tag**. New designs requiring both confidentiality and integrity are generally better served by an AEAD mode such as GCM.

`PKCS5Padding` is the standard name used across many JCE providers even for 128-bit AES blocks; do not deduce from the digit "5" that AES has only an 8-byte block. For GCM, `NoPadding` does not mean "no authentication", nor does it require plaintext length to be a multiple of 16 bytes: GCM's `Cipher.doFinal` returns ciphertext **plus the tag**.

## 4. A Full Transformation Also Needs Full Parameters

`Cipher.getInstance("AES/GCM/NoPadding")` fixes the mode/padding, yet an **interoperable encrypted record** must also specify:

| Component | Consistent Example | Critical Rule |
| --- | --- | --- |
| Transformation | `AES/GCM/NoPadding` | Do not inherit provider default mode/padding. |
| Key size | AES-128, 16-byte key | `KeyGenerator.getInstance("AES")` names the key type in the **KeyGenerator** engine; it is not requesting a default `Cipher` mode. |
| Nonce/IV | 12 bytes | Must **never repeat under the same GCM key**; store/transmit alongside the encrypted data. |
| Tag length | 128 bits | `new GCMParameterSpec(128, nonce)` uses **bits**. |
| AAD | Bytes like `"record:v1"` | Authenticated but unencrypted metadata. Must match byte-for-byte on decryption. |
| Output format | `ciphertext \|\| authentication tag` | Per the `Cipher` GCM API, the tag is appended to ciphertext on encryption and verified on decryption. |
| Encoding/layout | UTF-8 + versioned/length-prefixed binary format | Readers must reconstruct exact bytes rather than guessing OS defaults. |

**Four things very easily missed in code:**

1. `getInstance` only obtains the cipher engine. Call `init` with a valid key and parameters before `doFinal`; `getInstance` succeeding does not prove key/IV/tag validity.
2. In some modes, `init(ENCRYPT_MODE, key)` lets the provider auto-generate an IV. Failing to store/transmit that IV makes future decryption difficult or impossible. For GCM, use an application-controlled nonce generation strategy and pass `GCMParameterSpec` explicitly.
3. GCM's `updateAAD` must be called **before** `update`/`doFinal`. The receiver authenticates using the exact same AAD bytes; if the tag fails (`AEADBadTagException`), reject the entire record.
4. A GCM nonce must be unique per key. Generating random 96-bit nonces carries collision probability once record volume is large enough; multi-writer or high-volume systems need key usage limits, coordinated/partitioned keys, or controlled uniqueness mechanisms rather than assuming `SecureRandom` eliminates all collisions.

## 5. Java 17+ Example: Explicit GCM Encryption and Integrity Verification

Create **`ExplicitTransformationDemo.java`**. The program uses AES-128-GCM, a 12-byte nonce, a 128-bit tag, AAD, and tests two tampering cases. This is a **standalone program**, separate from the short illustrative snippets above.

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class ExplicitTransformationDemo {
    private static final String TRANSFORMATION = "AES/GCM/NoPadding";
    private static final int TAG_BITS = 128;
    private static final int NONCE_BYTES = 12;
    private static final SecureRandom RNG = new SecureRandom();

    private static byte[] encrypt(SecretKey key, byte[] nonce,
                                  byte[] aad, byte[] plaintext)
            throws GeneralSecurityException {
        Cipher cipher = Cipher.getInstance(TRANSFORMATION);
        cipher.init(Cipher.ENCRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad);
        return cipher.doFinal(plaintext);
    }

    private static byte[] decrypt(SecretKey key, byte[] nonce,
                                  byte[] aad, byte[] ciphertextAndTag)
            throws GeneralSecurityException {
        Cipher cipher = Cipher.getInstance(TRANSFORMATION);
        cipher.init(Cipher.DECRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad);
        return cipher.doFinal(ciphertextAndTag);
    }

    private static boolean rejected(SecretKey key, byte[] nonce,
                                    byte[] aad, byte[] ciphertextAndTag)
            throws GeneralSecurityException {
        try {
            decrypt(key, nonce, aad, ciphertextAndTag);
            return false;
        } catch (AEADBadTagException badTag) {
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128);
        SecretKey key = generator.generateKey();

        byte[] nonce = new byte[NONCE_BYTES];
        RNG.nextBytes(nonce);
        byte[] aad = "record:v1".getBytes(StandardCharsets.UTF_8);
        byte[] plaintext = "Hello AES-GCM".getBytes(StandardCharsets.UTF_8);

        Cipher chosen = Cipher.getInstance(TRANSFORMATION);
        System.out.println("Transformation: " + chosen.getAlgorithm());

        byte[] ciphertextAndTag = encrypt(key, nonce, aad, plaintext);
        byte[] recovered = decrypt(key, nonce, aad, ciphertextAndTag);
        System.out.println("Round-trip: " + Arrays.equals(plaintext, recovered));
        System.out.println("Ciphertext+tag bytes: " + ciphertextAndTag.length);

        byte[] changedBody = ciphertextAndTag.clone();
        changedBody[0] ^= 1;
        System.out.println("Tampered body rejected: " +
                rejected(key, nonce, aad, changedBody));

        byte[] changedAad = aad.clone();
        changedAad[0] ^= 1;
        System.out.println("Tampered AAD rejected: " +
                rejected(key, nonce, changedAad, ciphertextAndTag));
    }
}
```

Use JDK 17 or higher:

```bash
javac --release 17 ExplicitTransformationDemo.java
java ExplicitTransformationDemo
```

**Stdout** (the key/nonce bytes are random, but the following lines are stable):

```text
Transformation: AES/GCM/NoPadding
Round-trip: true
Ciphertext+tag bytes: 29
Tampered body rejected: true
Tampered AAD rejected: true
```

Explanation:

- `KeyGenerator.getInstance("AES")` here only selects the **key type**, then `generator.init(128)` specifies 128 bits. There is no reason to append `/GCM/NoPadding` to the **KeyGenerator** algorithm name; the three-part syntax belongs to Cipher requests.
- `"Hello AES-GCM"` is 13 UTF-8 bytes. With a 128-bit (16-byte) GCM tag, `doFinal` on encryption returns **13 + 16 = 29 bytes**.
- Both `encrypt` and `decrypt` explicitly request `AES/GCM/NoPadding` and use the same key, nonce, and AAD, so the recovered data matches byte-for-byte.
- Flipping 1 byte in either the ciphertext or AAD invalidates the authentication tag, so `rejected(...)` returns `true`. Never ignore or swallow tag errors and pass unauthenticated plaintext into business logic.
- Each method instantiates a fresh `Cipher` for a single operation. When reusing a key for a subsequent record, a **different nonce** must be used, and the maximum number of encryptions must be bounded by the security design.

**This is an in-memory example:** a fresh key is generated on each run; to read persisted data across restarts, an application must manage keys in a KMS/HSM/keystore and include metadata such as `version`, `suite ID`, `key ID`, nonce, and ciphertext/tag in a defined format. **Never store a raw secret key alongside ciphertext.** To prevent transplanting ciphertext into another context, bind tenant/object/purpose into AAD; to prevent replay, add state/sequence-number tracking beyond the authentication tag.

## 6. Choosing and Maintaining Transformations in a Project

### 6.1 When Writing New Code

- Start from requirements: if both confidentiality and integrity are needed, prefer a suitable **AEAD** such as AES-GCM.
- Choose **standard names and settings** for each engine: `Cipher.getInstance("AES/GCM/NoPadding")`, AES-128/256 keys per policy, 96-bit nonce, and 128-bit tag if the protocol requires those levels.
- Define the **data format** with clear version/suite/IV/tag and encoding; use only names understood by both encryptor and decryptor.
- Put availability checks into deployment or startup tests. Test initialization with real keys and parameters, followed by round-trip and tamper tests; do not stop at `Cipher.getInstance(...)`.
- Do not hardcode provider names in code unless policy or hardware mandates it; if pinned, document the dependency and test on the target runtime.

### 6.2 When Updating Legacy Applications Using `"AES"`

You must **determine the current format before changing the code**. You cannot simply replace every `Cipher.getInstance("AES")` with GCM and expect records originally encrypted with ECB/CBC and different padding to decrypt automatically.

Safe process:

1. Determine the JDK/provider used during legacy encryption, along with the mode, padding, key, IV/nonce, and ciphertext layout; verify using controlled test fixtures or sample data. Do not treat `getAlgorithm()` as sufficient proof.
2. Define a **legacy-version reader** only when compatibility is truly needed, scoping it tightly with strict error handling; do not try random modes in a loop until decryption succeeds.
3. Define a **new writer** with an explicit transformation, key strategy, and version/suite identifier; prefer AEAD.
4. When migrating legacy data, read using the permitted reader, verify integrity if the legacy format supports it, and write the new record with an appropriate nonce/key. Document the authentication limitations of the legacy data.
5. Stop generating new records with default configurations; plan to retire the legacy reader once migration is complete.

### 6.3 Java SE Support Levels and Providers

Java SE specifies **standard algorithm names** and a subset that **implementations are required to support**. A name appearing in *Standard Algorithm Names* does not automatically guarantee every runtime provides an implementation. Java SE 17 has baseline requirements involving AES-GCM with 128-bit AES keys; for other algorithms or key sizes, check the specification for the exact version and target provider.

What can vary across runtimes includes providers, availability, key/parameter limits, hardware acceleration, and configuration details. Explicit transformation names eliminate ambiguity about the cipher operation, yet **interoperability tests** remain necessary if one side writes with provider A and the other reads with provider B.

## 7. Diagnosing Errors by Problem Category

| Exception / Symptom | Where It Typically Occurs | Reasoning and Resolution |
| --- | --- | --- |
| `NoSuchAlgorithmException` | `Cipher.getInstance` | Algorithm/transformation not resolved by any registered provider/runtime; check spelling, standard name, and registered providers. |
| `NoSuchPaddingException` | `Cipher.getInstance` | Requested padding is unsupported for that transformation/provider. For example, `AES/GCM/PKCS5Padding` is not a valid GCM name. |
| `NoSuchProviderException` | Overload taking provider name | Provider name is absent from the registry; install/register the provider or drop the restriction if unnecessary. |
| `InvalidKeyException` | `Cipher.init` | Key type/size/properties are inappropriate or restricted by policy. |
| `InvalidAlgorithmParameterException` | `Cipher.init` | IV/nonce/tag/algorithm parameters are rejected. |
| `AEADBadTagException` | `Cipher.doFinal` during AEAD decryption | Data, key, nonce, or AAD is incorrect; **reject**, return no plaintext, and do not switch modes to retry. |
| `BadPaddingException` (CBC) | `Cipher.doFinal` | Key/IV/ciphertext/padding may be wrong. Padding **is not an integrity check** and details must not be leaked to untrusted callers. |

**Do not fall back like "if GCM is unavailable, try `AES`".** Because `"AES"` leaves the default mode unspecified by the application, a fallback could silently switch to ECB. When the runtime cannot satisfy a designed suite, fail explicitly or select an alternative suite **approved in the protocol**, with its own version/ID and predefined compatibility rules.

## 8. Code Review Mistakes Often Missed

1. **Algorithm-only selection:** `Cipher.getInstance("AES")` leaves mode/padding up to the provider.
2. **Half-measure fix:** changing to `AES/ECB/PKCS5Padding` for "stability", which still leaks multi-block data patterns.
3. **Using CBC without a MAC:** data can be altered and trigger padding errors; lacks AEAD authenticity.
4. **Failing to save the IV:** having ciphertext without the nonce/IV needed to decrypt; conversely, IVs can be public and must be stored properly.
5. **Reusing a GCM nonce under the same key:** breaks security requirements and can lead to forgery/data disclosure attacks.
6. **Confusing `NoPadding` with "no tag":** GCM still authenticates and appends a tag; a 13-byte plaintext is completely valid.
7. **Calling `updateAAD` after `update`:** violates the Cipher AEAD API contract.
8. **Inferring mode from `getAlgorithm()` or provider name:** neither specifies the implicit mode/padding completely.
9. **Testing only `getInstance`:** failing to test `init`, `doFinal`, tag, nonce, key size, and cross-environment decryption.
10. **Changing mode in code without versioning ciphertext:** old records can no longer be decrypted by the new writer/reader.
11. **Taking transformation from an untrusted file/request:** letting external input choose the cipher operation; use only a fixed suite allowlist.
12. **Logging sensitive keys/nonces/cleartext:** educational print statements must never become production log streams. Nonces are not secret, yet still require integrity and proper context.

## 9. Self-Check Checklist

- [ ] Every `Cipher.getInstance` for stored/transmitted data specifies a standard transformation exact enough for the protocol.
- [ ] The transformation is **chosen for security**, not merely because it runs on the current JDK.
- [ ] Key size, IV/nonce, tag, AAD, and padding/feedback parameters are explicitly specified and tested on the target provider.
- [ ] GCM nonces are unique per key; keys are managed separately with rotation and usage limits planned.
- [ ] Unauthenticated plaintext is never returned; tampering and wrong AAD are rejected.
- [ ] Data includes version/suite/nonce/encoding, so decryption never relies on default modes/padding.
- [ ] No automatic fallback to ECB/CBC when a required suite is missing; errors follow the security contract.
- [ ] Cross-provider/JDK tests and legacy migration cases are covered where needed.

**Self-assessment:**

- Does `Cipher.getInstance("AES")` default to GCM on every JDK? **No.**
- Is `AES/ECB/PKCS5Padding` a full transformation? **Yes**, though that does not make it safe for multi-block data.
- Does `AES/GCM/NoPadding` handle generating and storing the nonce properly? **Not yet.** Application code and the data format are responsible for that.
- Will two parties using the same transformation but different AAD decrypt GCM successfully? **No**, when AAD is authenticated properly.
- Does `KeyGenerator.getInstance("AES")` suffer from the same ambiguity as `Cipher.getInstance("AES")`? **No**: `KeyGenerator` is a key generation engine and has no mode/padding.

## References

- [Java SE 17 — `javax.crypto.Cipher`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): transformation syntax, provider defaults, AEAD, `updateAAD` ordering, GCM nonces, and exceptions.
- [Oracle JDK 17 — JDK Providers Documentation](https://docs.oracle.com/en/java/javase/17/security/oracle-providers.html): **Cipher Transformations** section, `SunJCE`/`SunPKCS11` examples, and provider capabilities.
- [Java SE 17 — Java Cryptography Architecture Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html): engine API, SPI/providers, modes, and padding.
- [Java SE 17 — Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html): standard names and minimum implementation requirements.
- [Java SE 17 — `GCMParameterSpec`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html): `tLen` in bits, IV/nonce.
- [RFC 5116 — Authenticated Encryption with Associated Data](https://www.rfc-editor.org/rfc/rfc5116): concepts of nonce, AAD, and AEAD.

**Learning takeaway:** Calling `Cipher.getInstance("AES")` delegates a critical decision to the provider. Calling `Cipher.getInstance("AES/GCM/NoPadding")` keeps that decision inside your source code and protocol, which must then be completed with proper key, nonce, AAD, tag, storage, and testing.
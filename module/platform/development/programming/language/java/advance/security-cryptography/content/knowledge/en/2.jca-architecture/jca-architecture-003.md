# 2.3 Looking Up Standard Algorithm Names, Aliases, and Provider Support Scope

## Objectives

After this lesson, you will be able to (1) choose the right **service type** and **standard algorithm name** when calling JCA/JCE, (2) distinguish standard names from **aliases** registered by an individual provider, (3) inspect the services of each provider, and (4) verify practical usability instead of guessing from name lists.

In the Java Cryptography Architecture (JCA), an application requests a service by a **service type + algorithm name** pair. For example, `MessageDigest.getInstance("SHA-256")` requests the `MessageDigest` service with the `SHA-256` algorithm. JCA locates a `Provider` that has the corresponding implementation (SPI); JCE is the portion of the API for features such as `Cipher`, `Mac`, and `KeyAgreement`. Both API families share the same provider mechanism.

## 1. Distinguishing Service Type, Standard Name, Alias, and Transformation

| Concept | Meaning | Example |
| --- | --- | --- |
| **Service type / engine** | API functional group; an algorithm name only has meaning within this group | `MessageDigest`, `Signature`, `Mac`, `Cipher`, `KeyFactory` |
| **Standard algorithm name** | Standardized name in *Java Security Standard Algorithm Names*; used to write portable code across providers | `SHA-256`, `SHA256withRSA`, `HmacSHA256`, `PBKDF2WithHmacSHA256` |
| **Provider service name** | Primary name a provider registers for a `Provider.Service`; may be a standard name or a provider extension | `SHA-256` in a `MessageDigest` service |
| **Alias** | Alternative name pointing to the same service in **a specific provider**; must not be assumed to be supported by every provider | `SHA256` may be an alias for `SHA-256` |
| **Cipher transformation** | Encryption algorithm name with mode/padding, in the form `algorithm/mode/padding` | `AES/GCM/NoPadding` |
| **OID** | Numeric identifier of an algorithm in certain ASN.1/X.509 standards; whether an OID is accepted as a JCA name depends on the engine/provider | `1.2.840.113549.1.1.11` is just an OID, not a universal substitute syntax |

Some common engine and name pairs:

| API call | Service type | Name passed in |
| --- | --- | --- |
| `MessageDigest.getInstance("SHA-256")` | `MessageDigest` | `SHA-256` |
| `Mac.getInstance("HmacSHA256")` | `Mac` | `HmacSHA256` |
| `Signature.getInstance("SHA256withRSA")` | `Signature` | `SHA256withRSA` |
| `SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")` | `SecretKeyFactory` | `PBKDF2WithHmacSHA256` |
| `Cipher.getInstance("AES/GCM/NoPadding")` | `Cipher` | full transformation |
| `CertificateFactory.getInstance("X.509")` | `CertificateFactory` | `X.509` |

**Do not swap names across engines:** `SHA-256` is a digest, `HmacSHA256` is a keyed MAC, and `SHA256withRSA` is a signature algorithm name. Nor is `AES` synonymous with an encryption configuration that has a defined mode and padding.

**A standard name does not mean “guaranteed to be installed”.** The specification defines how to name algorithms, while actual implementation coverage comes from the JDK, registered providers, and runtime environment. Standard names are case-insensitive, yet an alias like `SHA256` does not automatically exist merely because `SHA-256` is valid; write the canonical standard form in application code.

## 2. How Does JCA Resolve Algorithm Names Through Providers?

General flow:

`engine.getInstance(name [, provider])` → find a service matching the engine → check primary name/aliases → instantiate implementation → (if needed) initialize with key/parameters → execute operation.

- **No provider specified:** JCA/JCE searches for an implementation among configured providers. `Security.getProviders()` shows the registered providers and global priority order; actual selection can also be affected by per-algorithm priority configuration and selection at initialization time.
- **Provider specified:** `MessageDigest.getInstance("SHA-256", provider)` or `Cipher.getInstance("AES/GCM/NoPadding", provider)` tries the exact provider given; this helps verify each provider's support scope.
- **Provider-local aliases:** one provider may register `Alg.Alias.MessageDigest.SHA256` pointing to `SHA-256`; another provider might not register that alias. The exact registration format is a provider detail.
- **Distinguishing returned names:** `Provider.Service.getAlgorithm()` is the service's registered primary name; `MessageDigest.getAlgorithm()` may preserve the name you requested, including an alias. Do not treat the value returned by an engine as proof of the specification's standard name.

For example, if `p.getService("MessageDigest", "SHA256")` returns a service whose `getAlgorithm()` equals `SHA-256`, you have evidence that **provider `p`** accepts `SHA256` as an alternative name for that service. You must not extrapolate that result to another provider or a different JDK build.

## 3. Lookup APIs and Their Limitations

| Lookup method | What you learn | What is NOT yet proven |
| --- | --- | --- |
| `Security.getProviders()` | Providers registered in the running JVM, list order, and their names/versions | Whether a provider supports a specific algorithm |
| `Security.getAlgorithms("MessageDigest")` | Set of algorithm names advertised by the environment for that engine | Specific provider, complete aliases, or whether operations with keys/parameters will succeed |
| `p.getServices()` | Services advertised by provider `p`; each service has `getType()`, `getAlgorithm()`, `getClassName()` | Every possible alias and every transformation variant |
| `p.getService(type, name)` | Service of **that provider** for a primary name **or alias**; `null` if not found | Whether initialization/operations with keys, modes, padding, or hardware will succeed |
| `Security.getProviders("MessageDigest.SHA-256")` | Providers matching the registration filter (may return `null`) | Which provider the engine will actually select at execution time |
| `MessageDigest.getInstance(name, p)` | Provider `p` can supply an instance for the requested digest name | That any other APIs or variants in the same algorithm family work |
| `Cipher.getInstance(transformation, p)` | Provider `p` accepts the request to create a cipher with that specific transformation | That the key, IV/nonce, key length, policy, device, and `doFinal` will succeed |

There is no public `Provider.Service.getAliases()` API. You can test **a candidate alias** with `getService(type, alias)` or `getInstance(alias, provider)`. Legacy properties of the form `Alg.Alias.<type>.<alias>` (if present) are useful for diagnostics, but iterating over them should not be treated as a standard, complete, or portable way to enumerate all aliases.

For `Cipher`, `p.getService("Cipher", "AES/GCM/NoPadding") == null` **does not mean** the provider cannot perform AES-GCM: a provider may register a `Cipher.AES` service and handle mode/padding when `Cipher.getInstance` parses the transformation. Therefore, test using the full transformation through **the `Cipher.getInstance` API itself**.

## 4. Java 17 Program: Looking Up Providers, Aliases, and Transformations

Create the file `JcaProviderLookup.java`:

```java
import javax.crypto.Cipher;
import javax.crypto.NoSuchPaddingException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.Provider;
import java.security.Security;
import java.util.HexFormat;
import java.util.List;
import java.util.Set;

public class JcaProviderLookup {
    public static void main(String[] args) throws Exception {
        Set<String> digests = Security.getAlgorithms("MessageDigest");
        System.out.println("Registered MessageDigest names: " + digests.size());

        System.out.println("Providers exposing SHA-256 MessageDigest:");
        for (Provider provider : Security.getProviders()) {
            Provider.Service service = provider.getService("MessageDigest", "SHA-256");
            if (service != null) {
                System.out.printf("  %s -> %s%n",
                        provider.getName(), service.getAlgorithm());
            }
        }

        System.out.println("Lookup canonical name and possible alias:");
        for (String name : List.of("SHA-256", "SHA256")) {
            try {
                MessageDigest digest = MessageDigest.getInstance(name);
                System.out.printf("  %s -> algorithm=%s, provider=%s%n",
                        name, digest.getAlgorithm(), digest.getProvider().getName());
            } catch (NoSuchAlgorithmException e) {
                System.out.println("  " + name + " -> unsupported");
            }
        }

        System.out.println("Providers accepting AES/GCM/NoPadding factory:");
        for (Provider provider : Security.getProviders()) {
            try {
                Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding", provider);
                System.out.println("  " + provider.getName() + " -> " + cipher.getAlgorithm());
            } catch (NoSuchAlgorithmException | NoSuchPaddingException e) {
                // This provider does not supply the requested transformation.
            }
        }

        byte[] hash = MessageDigest.getInstance("SHA-256")
                .digest("abc".getBytes(StandardCharsets.UTF_8));
        System.out.println("SHA-256(abc): " + HexFormat.of().formatHex(hash));
    }
}
```

Compile and run in the directory containing the file:

```bash
javac --release 17 JcaProviderLookup.java
java JcaProviderLookup
```

**How to read the output:**

- The number of digests, provider names, and lines in each section **depend on the JDK, providers, and machine configuration**; do not hardcode them as a list that “every Java has”.
- `SHA256` may succeed or print `unsupported`. Even when it succeeds, `algorithm=SHA256` does not prove it is the standard name; it may simply reflect the name passed into the engine.
- The final line is the **deterministic part** (when SHA-256 is available and functioning properly):

```text
SHA-256(abc): ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
```

This code uses `HexFormat` (Java 17+) and does not add/remove/modify JVM providers. It checks the ability to **instantiate** `Cipher`, not actual encryption/decryption capability.

## 5. Checking an Alias for **One Provider**, Avoiding Global Conclusions

The following snippet is illustrative; place it **inside a method declaring `throws NoSuchAlgorithmException`** (or handling the exception) and import `java.security.*`:

```java
Provider p = MessageDigest.getInstance("SHA-256").getProvider();
Provider.Service standard = p.getService("MessageDigest", "SHA-256");
Provider.Service candidate = p.getService("MessageDigest", "SHA256");

boolean sameRegisteredService =
        standard != null
        && candidate != null
        && standard.getAlgorithm().equalsIgnoreCase(candidate.getAlgorithm());

System.out.println(p.getName() + " accepts SHA256 alias: "
        + sameRegisteredService);
```

This is a test against **`p` at the current moment**. It checks whether two names resolve to the same *registered service name* within that provider; to confirm usability, also call `MessageDigest.getInstance("SHA256", p)` and execute `digest`. Do not take an alias list from one JDK or library and hardcode it assuming every environment will accept it.

A service may also expose attributes such as `SupportedKeyClasses` or `SupportedKeyFormats` (depending on engine and provider), read via `service.getAttribute(name)`; this is lookup-assistance metadata, **not a substitute for initializing with a real key**.

## 6. “Supported” Must Be Verified Layer by Layer

Example with `AES/GCM/NoPadding`:

1. **Valid name:** the standard documentation confirms that the components `AES`, `GCM`, `NoPadding` are meaningful. This does not yet indicate which provider is installed.
2. **Service registration:** inspect `p.getServices()` and related names; do not infer full transformation support merely from seeing a `Cipher.AES` entry.
3. **Engine creation:** try `Cipher.getInstance("AES/GCM/NoPadding", p)`. If it throws `NoSuchAlgorithmException`/`NoSuchPaddingException`, that provider does not satisfy the tested factory request.
4. **Initialization and execution:** test `init`, `doFinal`, and decryption/authentication verification using keys and parameters representative of the real environment. `InvalidKeyException`, `InvalidAlgorithmParameterException`, or provider/hardware errors may surface only at this step.

An operational test needs to generate a valid AES key, a random 96-bit nonce, and `GCMParameterSpec(128, nonce)`; encrypt with `Cipher.ENCRYPT_MODE`, then decrypt with `Cipher.DECRYPT_MODE` using the same key/nonce **solely to recover that one test ciphertext** and compare plaintext. In production systems, **never reuse the same nonce for two encryptions under the same GCM key**, and store/transmit the corresponding nonce alongside the ciphertext/tag so decryption can succeed. If an HSM/PKCS#11 provider requires keys to reside in the device, an in-memory `SecretKeySpec` may be rejected even though the transformation is supported.

Using `Cipher.getInstance("AES")` to “test AES-GCM” is out of scope: the name `AES` does not specify mode/padding and can pick unsafe defaults for the application. For symmetric encryption, always specify the designed transformation explicitly.

## 7. A Practical Lookup Workflow for Projects

1. **Identify the engine and required operation.** For example, checksum/hash → `MessageDigest`; keyed MAC → `Mac`; signature → `Signature`; encryption → `Cipher`.
2. **Choose the standard name for the target Java version.** Consult *Java Security Standard Algorithm Names* for the target Java release; verify mode/padding names and parameter requirements too.
3. **Capture runtime info.** Record Java version, relevant provider names/versions, `Security.getProviders()`, requested algorithm name, and exact transformation.
4. **Filter providers and test candidate aliases.** For typical engines use `p.getService(type, name)` and `getInstance(name, p)`; for `Cipher`, test the transformation directly against each provider.
5. **Verify the actual operation.** For digests: hash a test vector; for signatures: sign then verify; for ciphers: round-trip with realistic parameters/keys; for hardware providers: test against the corresponding environment/slot.
6. **Keep standard names in production.** Use aliases or provider-specific names only when there is a clear compatibility reason and test on the target provider/JDK.

### Interpreting Common Errors

| Symptom | Where to check |
| --- | --- |
| `NoSuchAlgorithmException` when calling `getInstance` | Wrong service type/name, missing provider, or the specified provider lacks that service; try the standard name and inspect each provider |
| `NoSuchPaddingException` | The padding in the transformation is not recognized by the implementation; verify full `algorithm/mode/padding` |
| `NoSuchProviderException` on provider-name overload | The provider name is unregistered or misspelled; compare against `Security.getProviders()` |
| `getService("Cipher", "AES/GCM/NoPadding") == null` but `Cipher.getInstance` succeeds | The provider registers at the base algorithm or sub-transformation level; do not treat this as a contradiction |
| Alias works on machine A, fails on machine B | Different provider, JDK version, security configuration, or module/device; switch to the standard name and retest |
| `getInstance` succeeds, `init` fails | Check key length/type, parameters, policy, FIPS, HSM permissions, and specific mode support |
| `getAlgorithms` includes the name, but operations fail | The advertised list does not guarantee every key/parameter combination or device state will work |

**Security note:** the fact that an algorithm is registered does not make it suitable for new designs. MD5, SHA-1 for collision-resistant signatures, DES, and ECB have severe security limitations; their presence in a provider may be purely for compatibility. Evaluate algorithm choice, key sizes, modes, authentication, and nonce management against current security standards.

## 8. Self-Check Exercises

- On your JVM, which providers accept `MessageDigest/SHA-256`? What service name does each provider advertise?
- For **each of those providers**, is `SHA256` accepted as an alias? Distinguish the result of `getService` from `getInstance`.
- Which providers accept `Cipher.getInstance("AES/GCM/NoPadding", p)`? Does the result differ from looking up `p.getService("Cipher", "AES/GCM/NoPadding")`? Explain why.
- If the same code behaves differently on another JDK/machine, what information do you need to record to reproduce and investigate the issue?

## Official Documentation

- [Java SE 17 — Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html): standard names, engines, modes, paddings, and implementation requirements.
- [Java SE 17 — JCA Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html): engine/provider model and how implementations are located.
- [Java SE 17 — `Provider` and `Provider.Service`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Provider.html): service lookup, primary names, and aliases.
- [Java SE 17 — `Cipher`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): transformations, provider selection, and initialization.

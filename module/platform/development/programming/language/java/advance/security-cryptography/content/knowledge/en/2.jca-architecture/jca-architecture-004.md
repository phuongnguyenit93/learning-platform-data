# 2.4 Distinguishing Required Java SE APIs from Algorithms Provided by a Specific JDK

## Objectives

When writing cryptographic applications in Java, you need to answer **three distinct questions**:

1. **Which APIs does Java SE specify?** For example, `MessageDigest`, `Signature`, and `SecureRandom` in `java.security`, or `Cipher` and `Mac` in `javax.crypto`, are standard APIs that application code can program against.
2. **Which algorithms does Java SE require to be implemented?** This is the minimum set specified separately in the **Security Algorithm Implementation Requirements** section of the specification for that *Java SE version*.
3. **What does the actual running JDK/runtime provide?** Available or additionally installed providers determine the list of algorithms, transformations, keystore formats, and certain runtime implementation characteristics.

The three questions are related, not synonymous. **Having the API class** does not guarantee **every algorithm name** works; **having a standardized algorithm name** also does not mean Java SE requires every implementation to support that name.

> In this lesson, examples of the mandatory set use **Java SE 17** as the baseline for concrete verification. For Java SE 21, 25, or other versions, you must check the *exact version of the specification* before drawing conclusions. A JDK is an implementation product of Java SE bundled with tools; extended providers and algorithms can vary across distributions, operating systems, configurations, and update releases.

## 1. Four Layers to Distinguish

| Layer | Meaning | Example | Valid inference |
| --- | --- | --- | --- |
| **Java SE API/engine** | Standard classes, methods, and programming contracts | `MessageDigest.getInstance(String)`, `Cipher.getInstance(String)`, `Security.getProviders()` | You can compile code using the API on the targeted Java SE version, provided appropriate modules/APIs are used. |
| **Standard algorithm name** | Canonical name to request a type of service | `SHA-256`, `SHA3-256`, `ChaCha20-Poly1305`, `RSASSA-PSS`, `PKCS12` | If an implementation supplies that service, use the standard name. **Does not prove the service is mandatory.** |
| **Java SE required implementation** | Services/algorithms and minimum key sizes that *every implementation conforming to that Java SE version* must support | Java SE 17 requires `MessageDigest`/`SHA-256` and `Cipher`/`AES/GCM/NoPadding` with 128-bit AES keys | Reasonable basis to expect portability across **Java SE 17–compliant** implementations under normal configuration. |
| **Runtime provider capability** | Actual algorithms supplied by currently registered providers; may exceed the minimum | `SUN` provider supports `SHA3-256`; `SunJCE` supports `ChaCha20-Poly1305` in Oracle JDK 17 | Available in that runtime/provider; must be verified when deploying to another environment. |

**Note on the word “required”:** The specification requires *the entire Java SE implementation* to provide the minimum services; it does not require **every individual provider** to provide all of those services. One provider might only implement `Signature`, while another only implements `Cipher`.

## 2. JCA Mechanism: Stable API, Algorithms Selected via Providers

An application calls an **engine API** such as `MessageDigest`, `Signature`, or `Cipher`; JCA locates a provider with a matching implementation and delegates operations to the implementation behind the API (Service Provider Interface, commonly called **SPI**).

```text
Application code
    |
    | MessageDigest.getInstance("SHA-256")
    v
Standard Java SE Engine API (MessageDigest)
    |
    | look up MessageDigest/SHA-256 service
    v
JCA provider selection
    |
    +---- Provider A: does not supply the service
    |
    +---- Provider B: supplies SHA-256 --> implementation/SPI
    |
    +---- Provider C: may also supply SHA-256
```

- Without specifying a provider: `MessageDigest.getInstance("SHA-256")` lets the framework locate an implementation among registered providers according to the runtime's selection rules.
- Specifying a provider: `MessageDigest.getInstance("SHA-256", "SomeProvider")` accepts only the named provider; if that provider is absent or does not supply the exact service, the call fails even if another provider supports it.
- `Security.getProviders()` reports registered providers; `getProvider()` on the engine object reports the provider actually selected. Providers like `SUN`, `SunJCE`, `SunRsaSign`, and `SunEC` are concrete implementation names of certain JDK builds, **not mandatory Java SE provider names**.
- A provider can ship with the JDK, come from a third-party library, or integrate with the OS/HSM. “Supported by the JDK” does not necessarily mean the JDK itself implements all of those algorithms from scratch.

Also distinguish two documentation sources: **Java Security Standard Algorithm Names** standardizes names and lists minimum requirements; **JDK Providers Documentation** describes the services implemented by the providers of *a specific JDK*.

## 3. What Does Java SE 17 Actually Require?

Selected representative entries from the **Security Algorithm Implementation Requirements** section of Java SE 17:

| Engine/service | Minimum required by Java SE 17 | Scope to understand accurately |
| --- | --- | --- |
| `MessageDigest` | `SHA-1`, `SHA-256` | `SHA3-256` and `SHA-512` are standard names, but are not in this engine's **minimum list** in Java SE 17. |
| `Cipher` | `AES/GCM/NoPadding`, `AES/CBC/PKCS5Padding`, `AES/CBC/NoPadding`, `AES/ECB/NoPadding`, `AES/ECB/PKCS5Padding` with **128-bit** AES, plus specific listed DESede and RSA transformations | The AES-128 requirement **does not mean** every mode/padding combination or every AES key size is mandatory. AES/ECB is present for compatibility, not as a security recommendation for multi-block data. |
| `Signature` | `SHA1withDSA`, `SHA256withDSA`, `SHA1withRSA`, `SHA256withRSA` | `RSASSA-PSS` has a standard name and is supported by many JDKs, but is not in this Java SE 17 minimum set. |
| `Mac` | `HmacSHA1`, `HmacSHA256` | Another HMAC name appearing in the standard names catalog is not necessarily mandatory. |
| `KeyGenerator` | `AES` (128-bit key), `DESede` (168-bit), `HmacSHA1`, `HmacSHA256` | You cannot infer that all key sizes or all key generation algorithms are guaranteed. |
| `KeyStore` | `PKCS12` | `JKS` and `JCEKS` are well known and may exist in specific JDKs, but are not required minimum formats for this engine. |
| `SecureRandom` | Must have an implementation-supplied default; **no specific algorithm name is mandatory** in the requirements table | Do not assume every Java SE 17 runtime has `SHA1PRNG`, `NativePRNG`, or `DRBG` merely because the `SecureRandom` class exists. |

The table above selects only key engines for comparison; the specification also states requirements for `KeyFactory`, `KeyPairGenerator`, `KeyAgreement`, `CertificateFactory`, `SSLContext`, and other service types. For instance, `KeyStore/PKCS12` and `Signature/SHA256withRSA` belong to the minimum set, while which provider is chosen to implement them still depends on the runtime.

**Two important limits:**

1. “Required support” is a **compatibility** requirement, not an evaluation that an algorithm is **safe for new projects**. Legacy algorithms such as SHA-1 or DESede may appear in the mandatory list for compatibility; that is not a reason to choose them for new cryptographic designs.
2. Obtaining an engine instance only confirms an implementation was found. Calling `init`, generating keys, signing, or decrypting still depends on key size/type, parameters, security policies, token/HSM state, and runtime constraints.

## 4. What Extra Capabilities Can a JDK Provide?

According to Oracle JDK 17's **JDK Providers Documentation**:

- The `SUN` provider lists many `MessageDigest` algorithms such as `SHA-224`, `SHA-384`, `SHA-512`, and `SHA3-256`, beyond the minimum `SHA-1`/`SHA-256`. Having standard names or being present in Oracle JDK 17 **does not elevate them into minimum requirements for all Java SE 17 runtimes**.
- The `SunJCE` provider includes `ChaCha20-Poly1305` transformations, many AES variants, and other `Mac`, `KeyGenerator`, and `SecretKeyFactory` services. `ChaCha20-Poly1305` is a clear example: its name is standardized and Oracle JDK 17 supports it, yet it is not in Java SE 17's minimum `Cipher` table.
- The `SunRsaSign` provider includes `RSASSA-PSS` and other RSA signature algorithms. Availability of `RSASSA-PSS` in your running distribution should be checked separately.
- `SUN` has `KeyStore/JKS`; `SunJCE` has `KeyStore/JCEKS`. These names/formats exist in the JDK ecosystem but do not replace the minimum `PKCS12` contract.

Even with the same algorithm name, providers can still differ in accepted parameters, performance, hardware support, and configuration. An extension of a JDK/provider only becomes an **application dependency** if you actively request or check for it.

## 5. Practice: Query the Runtime Instead of Guessing

Create the file **`JcaAvailability.java`** with the following Java 17+ code. The program checks three Java SE 17 minimum services, prints the provider actually selected, and tests a digest that has a standard name but is not mandatory (`SHA3-256`).

```java
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.Signature;
import javax.crypto.Cipher;

public final class JcaAvailability {
    public static void main(String[] args) throws Exception {
        MessageDigest sha256 = MessageDigest.getInstance("SHA-256");
        Cipher aesGcm = Cipher.getInstance("AES/GCM/NoPadding");
        Signature rsa = Signature.getInstance("SHA256withRSA");

        System.out.println("Java SE 17 minimum: OK");
        System.out.println("SHA-256 provider: " + sha256.getProvider().getName());
        System.out.println("AES/GCM provider: " + aesGcm.getProvider().getName());
        System.out.println("SHA256withRSA provider: " + rsa.getProvider().getName());

        try {
            MessageDigest sha3 = MessageDigest.getInstance("SHA3-256");
            System.out.println("Optional SHA3-256: PRESENT (" +
                    sha3.getProvider().getName() + ")");
        } catch (NoSuchAlgorithmException e) {
            System.out.println("Optional SHA3-256: ABSENT");
        }
    }
}
```

Compile and run (JDK 17 or higher):

```bash
javac --release 17 JcaAvailability.java
java JcaAvailability
```

**Example output** on Oracle JDK 17 with default providers (provider names and the optional line **may differ** on other runtimes):

```text
Java SE 17 minimum: OK
SHA-256 provider: SUN
AES/GCM provider: SunJCE
SHA256withRSA provider: SunRsaSign
Optional SHA3-256: PRESENT (SUN)
```

**How to interpret the output:**

- If the three mandatory lines initialize successfully, the current runtime satisfies *those tested cases*. They are not a full Java SE 17 compliance suite.
- If `SHA3-256` reports `ABSENT`, **do not conclude Java SE 17 is missing an API or non-compliant**; that algorithm is not part of the Java SE 17 minimum.
- If `getInstance` throws an exception for a service that belongs to the minimum set, inspect the JDK build, registered providers, configuration/policy, and deployment environment. Do not automatically infer that the entire Java SE API disappeared.
- The example only obtains **engine objects**; it has not encrypted or signed data yet. For real AES-GCM, you must use a valid key, a unique nonce/IV paired with the key, and handle the authentication tag properly; never reuse a nonce with the same key.

To inspect installed providers and the services advertised by each provider, you can use this **illustrative snippet placed inside a method**:

```java
for (java.security.Provider provider : java.security.Security.getProviders()) {
    System.out.println(provider.getName());
    for (java.security.Provider.Service service : provider.getServices()) {
        if (service.getType().equals("MessageDigest")) {
            System.out.println("  MessageDigest: " + service.getAlgorithm());
        }
    }
}
```

`Security.getAlgorithms("MessageDigest")` also lists digest names registered in the runtime. However, when checking a full **Cipher transformation** (algorithm/mode/padding), call `Cipher.getInstance("...")` instead of only matching strings in the service list: a provider may advertise a base cipher name and supported modes/paddings via attributes rather than listing every transformation as a standalone entry.

## 6. How to Choose APIs, Algorithm Names, and Providers in Applications

### Case A: Need to run on every standard-compliant Java SE 17 implementation

Use **public APIs** and an algorithm from the **minimum list** of that exact Java SE 17 release. For example:

```java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
Signature signature = Signature.getInstance("SHA256withRSA");
```

These are **illustrative calls**; they belong in methods with exception handling, and `Cipher`/`Signature` must be initialized with `init` using appropriate keys and parameters before processing data. Do not specify a provider name if your application has no specific provider requirement.

### Case B: Want to use modern algorithms/extensions outside the minimum set

For example, the application chooses `ChaCha20-Poly1305`, `SHA3-256`, or `RSASSA-PSS` due to protocol or design requirements. You can use the **same standard engine APIs**, provided you:

1. Document the **service type, algorithm name, parameters, and minimum runtime/provider version** required by the application.
2. Verify support on **all target environments**, ideally at startup and in integration tests; report missing-support configuration issues clearly.
3. When a fallback exists, only use fallbacks **permitted by the protocol and security policy**. Never automatically “downgrade” to a weaker algorithm just to avoid errors.
4. Test `init` and real operations too, rather than stopping at `getInstance`.

If the environment requires an HSM, a certified provider, or specific native integration, specifying the provider can be a deliberate, valid choice; in that case, the provider name and installation/registration procedure become part of the deployment contract. Without such a requirement, hardcoding `"SUN"`, `"SunJCE"`, or `"SunRsaSign"` reduces portability.

### Case C: Want to ensure unambiguous transformations and parameters

For `Cipher`, an algorithm-only name such as `Cipher.getInstance("AES")` leaves mode/padding defaults up to the provider. Some providers default to ECB, easily creating an insecure design for multi-block data. Choose a **full transformation** like `AES/GCM/NoPadding` and handle nonce, tag, and key properly. The existence of the standard name `AES` does not guarantee that all transformations or defaults are equally safe.

## 7. Common Mistakes and How to Categorize Diagnostics

| Symptom / assumption | Real issue | How to handle |
| --- | --- | --- |
| “`Cipher` is a Java SE API, so every cipher works.” | Confusing **engine API** with the mandatory algorithm set. | Check the minimum requirements table for your version; if outside it, verify provider/runtime. |
| “If it's in **Standard Names**, every JDK must support it.” | Confusing **standardized names** with **mandatory implementations**. | Check the **Security Algorithm Implementation Requirements** section next. |
| `NoSuchAlgorithmException` | No matching implementation found for the request, or the requested algorithm/provider is absent. | Check spelling/standard name, version, registered providers, and supported services. |
| `NoSuchPaddingException` when getting `Cipher` | Requested padding is unsupported for the chosen transformation/provider. | Use an exact, supported, and well-designed transformation. |
| `NoSuchProviderException` on provider-name overload | The specified provider is not registered. | Check provider installation configuration or remove the provider constraint if unnecessary. |
| `InvalidKeyException` or `InvalidAlgorithmParameterException` at `init` | The algorithm was found, but the key/parameters are invalid. | Check key size, key type, IV/nonce, policy, HSM, and provider requirements. |
| “Since SHA-1/DESede are required to be supported, we should use them in new projects.” | Confusing compatibility goals with security evaluation. | Choose algorithms/key lengths according to current system security standards. |
| “`SHA-256` works with the default provider, so it must work with `SunJCE`.” | A single provider **is not** the entirety of Java SE's provider set. | Use the overload without a provider name unless truly required. |

A special case: policies such as `jdk.tls.disabledAlgorithms` or certificate validation policies can **restrict how an algorithm is used in TLS/certificates** without meaning the engine was removed from JCA. Therefore, distinguish *service availability*, *key/parameter initialization capability*, and *protocol-specific rules*.

## 8. Quick Decision Workflow

1. **Identify the application's Java SE baseline**, such as Java SE 17; distinguish the compilation target (`--release 17`) from the actual runtime JDK.
2. **Choose the standard engine API** for the task (`MessageDigest`, `Cipher`, `Signature`, `Mac`, `KeyStore`, etc.).
3. **Check Standard Algorithm Names** to use the exact name; then **check Implementation Requirements** to see whether that algorithm/transformation/key size belongs to the minimum set.
4. **If outside the minimum set**, read the target JDK's provider documentation, verify with `getInstance` on the real runtime, and test operations with real keys/parameters.
5. **Document dependencies and missing-support handling policy**; do not hardcode provider names or pick weak fallbacks for convenience.
6. **Test across multiple environments** if the application deploys on multiple JDK vendors, OSes, containers, provider configs, or HSMs.

**Knowledge check:**

- Java SE 17 has the `MessageDigest` API; is `SHA3-256` mandatory? **No**. The standard name exists and Oracle JDK 17 may provide it, but the minimum table only lists `SHA-1` and `SHA-256` for `MessageDigest`.
- Java SE 17 requires `AES/GCM/NoPadding` with 128-bit keys; does that imply every JDK must support all AES key sizes and all modes? **No**.
- Do `KeyStore.getInstance("PKCS12")` and `KeyStore.getInstance("JKS")` have the same portability under Java SE 17? **No**. `PKCS12` is a minimum requirement; `JKS` is a format/implementation commonly present in specific JDKs.
- Can an algorithm present in `SunJCE` be used via the standard `Cipher` API? **Yes**, when the provider is registered and supplies that transformation; using the standard API does not turn an extra algorithm into a guarantee across all Java SE implementations.

## Primary Sources for Reference

- [Java SE 17 — Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html): compare **Standard Names** with **Security Algorithm Implementation Requirements**.
- [Java SE 17 — Java Cryptography Architecture (JCA) Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html): engine APIs, SPIs, provider selection, and requesting implementations.
- [Oracle JDK 17 — JDK Providers Documentation](https://docs.oracle.com/en/java/javase/17/security/oracle-providers.html): list of providers, algorithms, and transformations for that JDK.
- [Java SE 17 — Signature API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html): example API doc explicitly listing Java SE–required signature algorithms.

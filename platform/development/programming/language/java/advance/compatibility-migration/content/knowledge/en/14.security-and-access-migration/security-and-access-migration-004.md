
# Security providers, PKCS#11, and differences across distributions

When upgrading Java, an application may **compile completely cleanly** yet fail at runtime when signing digitally, establishing TLS connections, opening keystores, loading private keys, or accessing an HSM. The cause does not necessarily lie in source code: the Java Security Architecture uses **security providers** that can vary by JDK version, distribution vendor, security policy, operating system, native libraries, and deployment configuration.

In particular, systems using **PKCS#11** often have a long integration chain: Java application → JCA/JCE → bridge provider → native PKCS#11 library → token or HSM. A minor update at any link can change available algorithms, provider selection order, login mechanisms, key alias names, or key usability.

This lesson belongs to the topic *Java Advance Compatibility Migration*, section *Security and Access Migration*. The goal is to clearly understand the API contracts, distinguish provider errors from PKCS#11 errors, and design a compatibility verification process across JDK versions and deployment environments.

## 1. What is a security provider?

The **Java Cryptography Architecture (JCA)** provides abstract APIs for security operations, such as:

- `MessageDigest`: computes hash digests.
- `Signature`: digital signing and signature verification.
- `KeyPairGenerator` and `KeyGenerator`: key generation.
- `KeyFactory` and `SecretKeyFactory`: handles key representations.
- `SecureRandom`: supplies random numbers for cryptographic use.
- `KeyStore`: manages key and certificate references.
- `CertificateFactory` and `CertPathValidator`: handle certificates and trust chains.

The **Java Cryptography Extension (JCE)** is the set of cryptographic capabilities such as `Cipher`, `Mac`, and `KeyAgreement`. In modern JDKs, the corresponding APIs are distributed as part of the Java platform.

The APIs above are primarily **engine classes**. They define how applications invoke a capability; **providers** supply implementations for registered algorithms or services.

Example:

~~~java
import java.security.MessageDigest;
import java.util.HexFormat;

public class DigestExample {
    public static void main(String[] args) throws Exception {
        MessageDigest digest =
                MessageDigest.getInstance("SHA-256");

        byte[] output =
                digest.digest("hello".getBytes(
                        java.nio.charset.StandardCharsets.UTF_8));

        System.out.println(HexFormat.of().formatHex(output));
        System.out.println(
                "Provider: " + digest.getProvider().getName());
    }
}
~~~

The code only requests `SHA-256`. The JVM selects a provider supporting that service according to the active selection rules. The chosen provider may differ on another runtime, even though `MessageDigest.getInstance("SHA-256")` still works.

### 1.1. Abstract APIs and executing providers

~~~mermaid
flowchart TD
    A["Java application"] --> B["JCA/JCE engine: Signature, Cipher, KeyStore"]
    B --> C{"Provider selection"}
    C --> D["Software provider"]
    C --> E["PKCS#11 provider"]
    C --> F["Third-party provider"]
    E --> G["Native PKCS#11 library"]
    G --> H["Token / HSM"]
~~~

A provider is not a single algorithm. One provider can register many **service types** and **algorithm names**, such as:

| Service type | Example algorithm/service name | Function |
|---|---|---|
| `MessageDigest` | `SHA-256` | Hashing |
| `Signature` | `SHA256withRSA` | Digital signature |
| `Cipher` | `AES/GCM/NoPadding` | Authenticated encryption |
| `KeyStore` | `PKCS12`, `PKCS11` | Key/certificate management |
| `KeyPairGenerator` | `RSA`, `EC` | Key pair generation |
| `SecureRandom` | Provider-dependent | Randomness |

Distinguish an **algorithm family** from a **transformation** and a **provider-specific alias**. For example, `AES/GCM/NoPadding` is a transformation for `Cipher`; actual support also depends on key size, parameters, and provider/device mechanisms.

### 1.2. Commonly encountered providers

Depending on the JDK, you may encounter names such as:

- `SUN`: basic Java Security services.
- `SunRsaSign`: RSA signature and key handling services.
- `SunEC`: elliptic curve cryptography services.
- `SunJCE`: symmetric cryptography services and related engines.
- `SunJSSE`: TLS/JSSE implementation and related components.
- `SunPKCS11`: bridge to PKCS#11, when the appropriate module and configuration are present.
- Third-party providers or JDK/HSM vendor providers.

**Do not treat the list above as a guaranteed contract across every JDK.** Provider names, order, algorithms, and configuration may vary across OpenJDK-based distributions, customized JDKs, minimal runtimes, release versions, and additionally registered providers.

## 2. What happens when the application does not specify a provider?

Example:

~~~java
Signature signature =
        Signature.getInstance("SHA256withRSA");
~~~

The application requests an algorithm without **pinning the provider**. The Java Security framework selects an appropriate implementation from registered providers, considering provider capabilities and the engine/key context.

In some cases, the actual implementation may be constrained by key type or delayed provider selection. Therefore, do not oversimplify it as "always picks the first provider for every call" without observing the actual engine.

If the application specifies a provider:

~~~java
Signature signature =
        Signature.getInstance("SHA256withRSA", "ExampleProvider");
~~~

then it depends on that provider name and its registered services. If the provider is absent or does not support the algorithm, the call fails.

For systems that must use **keys residing in an HSM**, provider selection can be part of the security policy: do not silently fall back to a software private key just to make tests pass. On the other hand, hardcoding provider names in code paths that do not require hardware can make the application harder to migrate across JDKs.

### 2.1. Inspecting providers at runtime

Java example:

~~~java
import java.security.Provider;
import java.security.Security;

public final class ListSecurityProviders {
    public static void main(String[] args) {
        for (Provider provider : Security.getProviders()) {
            System.out.printf(
                    "%s | version=%s | info=%s%n",
                    provider.getName(),
                    provider.getVersionStr(),
                    provider.getInfo());

            for (Provider.Service service : provider.getServices()) {
                if ("Signature".equals(service.getType())
                        || "KeyStore".equals(service.getType())) {
                    System.out.printf(
                            "  %s : %s%n",
                            service.getType(),
                            service.getAlgorithm());
                }
            }
        }
    }
}
~~~

The output shows the providers and services **registered** at runtime. However, a listed service **does not guarantee** every key type, parameter, token mechanism, or operation will succeed. A PKCS#11 provider might advertise an algorithm while a specific token only accepts certain key attributes or mechanisms.

To observe the provider of a specific instance:

~~~java
import java.security.Signature;

Signature signer = Signature.getInstance("SHA256withRSA");
System.out.println(signer.getProvider().getName());
~~~

For engines with delayed provider selection, simply printing the provider before initializing with a key is not enough to determine the final execution path. Also check after `initSign`/`initVerify` and an actual operation when confirming policy compliance.

### 2.2. Provider order and what not to assume

Providers have priority ordering; Java allows registering via:

~~~java
Security.addProvider(provider);
Security.insertProviderAt(provider, 1);
~~~

However, altering the global order can affect TLS, certificate validation, key generation, and other security flows in the same process. Do not automatically place an HSM provider at the top of all services merely to use a token for signing one document type.

Prioritize:

1. Specifying the provider at call sites where the design requires it.
2. Using keys with clear provenance and control mechanisms.
3. Configuring globally only when justified and impact-assessed.
4. Testing other services after changing provider order.

## 3. What is PKCS#11?

**PKCS#11**, also known as **Cryptoki**, is a standard interface enabling software to interact with devices or services providing cryptographic functions, typically smart cards, USB tokens, or a **Hardware Security Module (HSM)**.

In a typical architecture:

- Java calls JCA/JCE APIs such as `Signature`, `KeyStore`, or `KeyPairGenerator`.
- A PKCS#11-capable provider translates JCA requests into PKCS#11 calls.
- A native library distributed by the device vendor communicates with the token/HSM.
- The device manages slots, sessions, objects, mechanisms, and key usage policies.

~~~mermaid
flowchart LR
    A["Business service"] --> B["Java Signature / KeyStore"]
    B --> C["PKCS#11 JCA provider"]
    C --> D["JNI/native bridge"]
    D --> E["Vendor PKCS#11 library"]
    E --> F["Slot / token / session"]
    F --> G["Private key in HSM"]
~~~

PKCS#11 differs from **PKCS#12**:

| Name | Nature | Common form |
|---|---|---|
| PKCS#11 | API interface to a token/HSM via provider/native library | `KeyStore` type `PKCS11`, HSM session |
| PKCS#12 | Storage format for keys/certificates that can reside in a file | `KeyStore` type `PKCS12`, `.p12`/`.pfx` files |

The fact that an application can open a PKCS#12 file does not prove it integrates PKCS#11 or stores private keys inside an HSM.

### 3.1. Common concepts in PKCS#11

| Concept | Meaning |
|---|---|
| Module/library | Native PKCS#11 library providing the Cryptoki interface |
| Slot | Logical position for an available device/token |
| Token | Device or logical object providing keys and crypto operations |
| Session | Communication session with a token |
| Object | Key, certificate, or data stored in the token |
| Mechanism | Method/algorithm the hardware can execute |
| PIN/login | Authentication mechanism to use protected objects |
| Label/ID | Attributes used to locate objects, not necessarily stable Java aliases |
| Key attributes | Rules governing how a key may sign, decrypt, be exported, or be used |

A token can hold a **non-extractable** private key. In that case, Java may receive a `PrivateKey` object representing a handle/reference, which does not mean the application receives the raw secret key bytes.

### 3.2. Native dependencies are part of the runtime contract

Factors that can break PKCS#11 after migration:

- `.so`/`.dll`/`.dylib` file does not exist at the configured path.
- CPU architecture mismatch (x86-64/ARM64).
- Native library depends on libc or other system libraries.
- Restricted file/device permissions and container policies.
- HSM vendor driver/daemon is not running or cannot connect.
- Token/slot changes after a reboot or when adding devices.
- Vendor PKCS#11 version does not support the new JDK/OS.
- Library uses native mechanisms not permitted by the provider.
- Token requires login or its session has expired.

These failures cannot be resolved solely by editing Java source code or compiler targets.

## 4. SunPKCS11 and differences across JDKs

In many OpenJDK-based distributions, **SunPKCS11** is the bridge provider from JCA/JCE to native PKCS#11 libraries. On modularized JDKs, the corresponding implementation is delivered through the `jdk.crypto.cryptoki` module when that module is present in the runtime.

Key things to understand:

- A JDK may include the `SunPKCS11` provider **without a configured token/HSM yet**.
- A runtime built with `jlink` may have omitted the required module.
- Other distributions may provide a different provider or a different PKCS#11 integration mechanism.
- Provider names and order are not portable APIs guaranteed across every vendor.
- The native library and token must still be installed, permitted, and tested separately.

Do not write instructions claiming "every Java 17 comes with SunPKCS11 working out of the box" without verifying the specific runtime.

### 4.1. Checking modules in the runtime

Example:

~~~bash
java --list-modules
~~~

You can filter in a shell:

~~~bash
java --list-modules | grep 'jdk.crypto.cryptoki'
~~~

On PowerShell:

~~~powershell
java --list-modules | Select-String 'jdk.crypto.cryptoki'
~~~

When building a custom runtime image with `jlink`, ensure the provider module is included, for instance based on the modules your application requires plus `jdk.crypto.cryptoki`. The full module list depends on the application; do not add just a single module and assume the image has all needed capabilities.

### 4.2. Checking provider availability

~~~java
import java.security.Provider;
import java.security.Security;

public class CheckPkcs11 {
    public static void main(String[] args) {
        Provider provider =
                Security.getProvider("SunPKCS11");

        if (provider == null) {
            System.out.println("SunPKCS11 not available");
        } else {
            System.out.println(provider.getName());
        }
    }
}
~~~

`null` may mean the provider is not installed/registered in that runtime, due to custom image configuration, or distribution choices. Do not immediately conclude the token/HSM is broken if even the bridge provider is missing.

## 5. Configuring PKCS#11 and creating a provider

An illustrative SunPKCS11 configuration:

~~~properties
name = InvoiceToken
library = /opt/vendor/pkcs11/libvendorpkcs11.so
slotListIndex = 0
~~~

Meaning:

- `name`: name distinguishing the configuration instance.
- `library`: path to the native PKCS#11 library.
- `slotListIndex`: selects an index in the slot list returned by the native library, **not necessarily a fixed slot ID**.

The path is an example; replace it with a valid library and configuration provided by the vendor. On Windows it may be a path to a `.dll` file; on macOS a `.dylib`. If the vendor uses a virtual HSM/network HSM, library may still be the native client connecting to that service.

### 5.1. slot and slotListIndex differ

A configuration can select using `slot` or `slotListIndex` depending on the provider, yet the two **are not synonymous**:

- `slot` typically refers to the slot ID provided by the PKCS#11 module.
- `slotListIndex` is the positional index in the slot list.

Slot order can change when adding tokens, updating drivers, or rebooting. Therefore, do not treat `slotListIndex = 0` as a durable business identifier.

Obtain token/slot details from vendor tools or administration documentation and test behavior after hardware changes. If an HA system has multiple slots, design explicit selection and failover logic rather than relying on a "first slot" assumption.

### 5.2. Configuring the provider on modern JDKs

Java example using the `Provider.configure` method (available since Java 9):

~~~java
import java.security.Provider;
import java.security.Security;

public class Pkcs11ProviderFactory {
    public static Provider configure(String configFile) {
        Provider base =
                Security.getProvider("SunPKCS11");

        if (base == null) {
            throw new IllegalStateException(
                    "SunPKCS11 provider is unavailable");
        }

        Provider configured = base.configure(configFile);

        // Register globally only if the architecture genuinely requires it.
        Security.addProvider(configured);
        return configured;
    }
}
~~~

The configured instance typically has a name like `SunPKCS11-InvoiceToken` in the corresponding implementation. However, the application should not guess the name by string concatenation when it can hold the returned `Provider` object directly.

Notes:

- The config path may contain system path details, but should never contain PINs or secrets.
- Do not invoke configuration repeatedly without control on every request; providers and sessions have their own lifecycles.
- Some JDK versions, customized runtimes, or other providers have different configuration APIs.
- If using a provider other than SunPKCS11, follow that provider's documentation instead of assuming `configure` accepts the same format.
- Do not insert a provider at the head of the global list without a clear security and compatibility rationale.

### 5.3. When registration in Java security configuration is needed

Providers can also be registered via the runtime's Java security configuration or product provider mechanisms. These registration approaches are part of the deployment environment and must be version-controlled.

Identify:

1. Is the provider pre-installed, declared in security properties, or added programmatically?
2. Are there multiple HSM instances or multiple vendor providers?
3. Does provider order affect Cipher/Signature/JSSE?
4. Does configuration differ among test, staging, and production?
5. Are custom runtime images or Java agents modifying providers?

Do not manually edit `java.security` on production systems outside configuration management. A silent edit can cause runtime environments and CI to use two different provider sets.

## 6. Using a PKCS11 KeyStore

With a configured provider, the token can be accessed via a `KeyStore` of type `PKCS11` if supported by the provider and device.

~~~java
import java.io.Console;
import java.security.KeyStore;
import java.security.Provider;
import java.security.Security;
import java.util.Arrays;
import java.util.Enumeration;

public class ListTokenAliases {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Expected path to SunPKCS11 configuration");
        }

        Provider base = Security.getProvider("SunPKCS11");
        if (base == null) {
            throw new IllegalStateException(
                    "SunPKCS11 not found in this runtime");
        }

        Provider tokenProvider = base.configure(args[0]);
        Console console = System.console();
        if (console == null) {
            throw new IllegalStateException(
                    "Use an approved noninteractive secret mechanism");
        }

        char[] pin = console.readPassword("Token PIN: ");
        try {
            KeyStore keyStore =
                    KeyStore.getInstance("PKCS11", tokenProvider);

            keyStore.load(null, pin);

            Enumeration<String> aliases = keyStore.aliases();
            while (aliases.hasMoreElements()) {
                String alias = aliases.nextElement();
                System.out.println(
                        "Alias available: " + alias);
            }
        } finally {
            Arrays.fill(pin, '\0');
        }
    }
}
~~~

This is an **architectural illustration example**, not complete production operational code:

- The token may require a custom login, custom PIN mechanism, or vendor-specific configuration.
- `System.console()` is usually unavailable in CI, services, or containers.
- `KeyStore.load(null, pin)` is common with SunPKCS11, but must be verified against the actual provider/token.
- Displayed aliases are metadata and may carry internal identifying information; log them only in authorized environments.
- Clearing `char[]` reduces how long the PIN stays in that array, though it does not guarantee every copy or native memory region is cleared.
- Never put PINs in source code, command lines, Git, logs, or PKCS#11 configuration files.
- In production, retrieve secrets from an approved secret management mechanism with access controls.

### 6.1. KeyStore type does not guarantee exportable private keys

A token/HSM may return a `PrivateKey` as an object containing only a reference/handle, while the actual key never leaves the device.

Therefore, never assume:

~~~java
privateKey.getEncoded()
~~~

will return the private key bytes. For non-extractable keys, the result may be `null`. The right design is having the provider perform **signing or decryption on the device** via JCA/JCE, adhering to the token's policies and mechanisms.

### 6.2. Aliases can differ between provider and device

An alias in a Java KeyStore does not necessarily match the label displayed in vendor tools or the object's `CKA_LABEL`. A token can store certificates, public keys, and private keys with different attributes.

When migrating:

- Verify aliases on the exact target token.
- Check the certificate chain, key usage, and identifiers.
- Do not select an alias simply by taking the first entry in `aliases()`.
- Do not pick a key solely because the alias matches if the certificate/public key does not match.
- Use key IDs, certificate fingerprints, or an explicit mapping if the architecture requires it.
- Confirm the key retrieval flow does not require the application to export the private key.

If a vendor changes alias rules after an update, update mappings in a controlled manner.

## 7. Digital signing with an HSM key via JCA

A typical pattern: retrieve the `PrivateKey` handle from a PKCS11 keystore, then call `Signature` with the appropriate provider.

~~~java
import java.security.PrivateKey;
import java.security.Provider;
import java.security.Signature;
import java.nio.charset.StandardCharsets;

public final class TokenSigner {
    public static byte[] sign(
            String data,
            PrivateKey key,
            Provider tokenProvider) throws Exception {

        Signature signature =
                Signature.getInstance(
                        "SHA256withRSA", tokenProvider);

        signature.initSign(key);
        signature.update(
                data.getBytes(StandardCharsets.UTF_8));
        return signature.sign();
    }
}
~~~

The example assumes:

- The key is an RSA private key suitable for SHA-256/RSA signatures.
- The token/provider supports the corresponding service and mechanism.
- The key has the attributes required to perform signing.
- The session, login, and access permissions are ready.

If the device supports only a different mechanism, or the key has usage restrictions, `Signature.getInstance(...)` or `initSign`/`sign` can fail. A provider that registers an algorithm may still reject operations with specific keys or parameters.

### 7.1. Distinguish the selected provider from where the key is stored

When calling:

~~~java
Signature.getInstance("SHA256withRSA")
~~~

the platform may choose a software or PKCS#11 implementation depending on configuration, key, and provider. With an HSM requiring "private key never leaves the device", the design must prove the operation actually executes through the token.

Evidence can include:

- The provider instance used for the signing operation.
- The key object originates from the PKCS11 KeyStore on the right token.
- HSM logs/audit records in the test environment.
- Verifying the key's non-extractable attribute via authorized management mechanisms.
- Controlled permission-revocation or token-disconnect tests verifying that signing fails as expected.

Do not claim "HSM is used" solely from the presence of `SunPKCS11` in `Security.getProviders()`.

### 7.2. Choosing signing algorithms aligned with policy

Signature algorithms can differ in padding, hash, curve, and data normalization. For example, RSA-PSS is not identical to `SHA256withRSA` (typically RSA PKCS#1 v1.5), and has its own parameter requirements.

For payment systems, document signing, certificates, or partner connections, choose algorithms based on **protocol and security policy**, not on whichever name the first provider happens to support.

The set of algorithm names registered by a provider also does not guarantee the token supports every required mechanism. PKCS#11 mechanism mappings can vary by vendor and runtime.

## 8. Cipher, TLS, certificates, and providers: easily confused layers

### 8.1. A Cipher provider is not necessarily a TLS provider

JCA/JCE provides `Cipher`. **JSSE (Java Secure Socket Extension)** provides APIs such as `SSLContext`, `SSLSocket`, and `TrustManagerFactory` for establishing TLS.

An application may use:

- An HSM provider for signatures with a private key.
- Another provider for ciphers or hashes.
- A JSSE implementation to run the TLS handshake.
- A separate truststore to verify certificate chains.

Changing provider order or policy can indirectly affect TLS, yet **supporting a Cipher algorithm does not mean supporting the full TLS protocol**.

### 8.2. HSM can protect private keys for mutual TLS

With mutual TLS (mTLS), the client must present a certificate and sign during the handshake using a private key. The key can reside in a token, while `KeyManagerFactory` or the JSSE integration uses the appropriate KeyStore.

Conceptual flow:

~~~mermaid
sequenceDiagram
    participant App as Java application
    participant JSSE as JSSE/TLS
    participant JCA as JCA PKCS#11 provider
    participant HSM as Token/HSM
    participant Server as TLS peer
    App->>JSSE: Create TLS connection with key manager
    JSSE->>JCA: Request private-key operation
    JCA->>HSM: Sign challenge/handshake data
    HSM-->>JCA: Signature
    JCA-->>JSSE: Signature result
    JSSE->>Server: TLS handshake messages
~~~

Configuring `KeyManagerFactory` and `SSLContext` specifically depends on the JSSE implementation, provider, key/certificate types, and application policy. Do not assume `KeyStore.getInstance("PKCS11")` automatically makes mTLS work without configuring a key manager and trust manager.

### 8.3. KeyStore for keys differs from TrustStore for trust

A **Keystore** holds or references the subject's keys/certificates. A **Truststore** holds the trust anchors/certificates used by the system when authenticating the peer.

In an application, a private key from an HSM may be used for signing, while the truststore resides in a `PKCS12` file or system-managed store. Switching HSM providers does not necessarily require moving every certificate into the HSM.

### 8.4. JDK algorithm restriction policies

Upgrading the JDK can change security properties such as:

~~~text
jdk.tls.disabledAlgorithms
jdk.certpath.disabledAlgorithms
jdk.jar.disabledAlgorithms
~~~

A previously accepted certificate chain or protocol may be rejected due to weak keys, weak signature algorithms, or new policies, **even while the PKCS#11 provider continues working**.

Inspect TLS errors, certificate path validation, and key/cert algorithms separately from provider/token loading errors. Do not relax the entire policy just to let a legacy system connect without a security assessment.

## 9. Differences across JDK distributions

Not all Java builds sharing the same major version deliver an identical security experience. Beyond vendor differences, patch updates within the same JDK line can also alter certificate data, algorithm policies, and fixed bugs.

Aspects to check:

| Aspect | What may differ | Impact |
|---|---|---|
| Provider set | Provider presence/absence, names, or implementations | `getInstance` fails or picks a different provider |
| Provider order | Ordering of security providers | Engine picks a different implementation |
| PKCS#11 bridge | Presence of `jdk.crypto.cryptoki` or other adapters | Unable to configure token |
| Root CA/truststore | Contents and policies of `cacerts` | TLS/cert validation differs |
| Algorithm restrictions | Restricted algorithms/key sizes | Handshake or signature rejected |
| FIPS/validated configuration | Separately configured providers and policies | Algorithm availability and key operations change |
| Native ABI | OS/CPU/libc/vendor client | Cannot load PKCS#11 library |
| HSM vendor support | Whether driver/module version supports the JDK/OS | Session, slot, or mechanism errors |
| Build update | JDK/provider patches | Error behavior and updated policies |
| Custom runtime image | Stripped-down modules | Missing PKCS#11 bridge or other engines |

**Do not use `java -version` alone as sufficient proof.** Add a provider inventory, relevant security properties, module list, native library version, and actual operational test results.

### 9.1. JDK vendor vs. native HSM vendor

A failure can occur at four different layers:

1. **JDK distribution:** module/provider is missing or differs in implementation.
2. **JCA bridge:** provider loads, but service mapping/configuration does not match.
3. **PKCS#11 native module:** DLL/SO fails to load, or session/token/slot errors occur.
4. **HSM/token:** key attributes, PIN, mechanism, quotas, or policy forbid the operation.

Record the layer where the failure occurs; avoid labeling it a "Java 21 bug" when the vendor library was actually built for a different ABI.

### 9.2. FIPS is not an arbitrary toggle flag

A system with FIPS requirements must verify the **validated cryptographic module, version, configuration, protective boundaries, and operational procedures required**. Merely using an HSM or adding `SunPKCS11` does not automatically make the whole application FIPS-compliant.

In environments with special policies:

- Confirm module vendor, operating mode, and certificate/validation applicability.
- Confirm algorithms allowed in that mode.
- Confirm mechanisms for creating, storing, using, and destroying keys.
- Ensure provider fallback does not violate policy.
- Separate technical compatibility testing from formal compliance verification.

Do not automatically weaken JDK TLS/algorithm policies to "increase compatibility".

## 10. Common errors and how to classify them

| Error or symptom | Possible causes | How to isolate |
|---|---|---|
| `NoSuchProviderException` | Provider name absent from registry | Print `Security.getProviders()`, check modules and configuration |
| `NoSuchAlgorithmException` | Service/algorithm not offered by provider | Check services, transformation, and token mechanisms |
| `ProviderException` on init | Bridge/native/token failure | Read cause chain and provider/HSM logs |
| `UnsatisfiedLinkError` | Unable to load native library/ABI | Path, native dependencies, OS/CPU, permissions |
| `IOException` opening keystore | Login/token/keystore or config error | Check cause, driver, slot, PIN procedure |
| `UnrecoverableKeyException` | Cannot retrieve key, auth or permission failure | Alias, login, key attributes, and provider |
| `InvalidKeyException` | Key unusable for algorithm/provider | Key type, allowed usage, and mechanism |
| `InvalidAlgorithmParameterException` | Parameters rejected | IV, padding, PSS params, or mechanism |
| `KeyStoreException` | Invalid keystore/service type or state | `PKCS11` provider configuration |
| TLS handshake failure | Certificate, policy, trust, protocol, or signing problem | JSSE logs, truststore, key manager, and HSM operation |
| `CKR_TOKEN_NOT_PRESENT` | Token absent from slot | Vendor diagnostics and slot mapping |
| `CKR_PIN_INCORRECT` | Incorrect PIN reported by token | Secret management procedure; avoid unlimited retries |
| `CKR_MECHANISM_INVALID` | Token rejects mechanism | Mechanism list and algorithm mapping |
| `CKR_SESSION_COUNT` | Exceeded session limit | Pooling, concurrency, token limits |
| Key alias not visible | Different mapping/object filter/permissions | Enumerate aliases, inspect token object attributes |

The `CKR_*` codes are examples from PKCS#11; not every provider surfaces these exact codes in exceptions. Stack traces may wrap errors across multiple layers.

### 10.1. Successful provider initialization is not enough

Some providers only interact with the token when creating a `KeyStore`, calling `load`, initializing `Signature`, or calling `sign`. Therefore:

~~~java
Provider p = Security.getProvider("SunPKCS11");
~~~

only confirms registry presence; it does not prove session/login/private-key operations will succeed.

Even if `KeyStore.aliases()` can read certificates, signing operations can still fail because the key disallows the corresponding mechanism.

### 10.2. Check the root cause, not just the outermost exception

Example business failure:

~~~text
SigningServiceException
  caused by java.security.ProviderException
    caused by PKCS11Exception: CKR_MECHANISM_INVALID
~~~

Seeing only `SigningServiceException`, one might mistake it for an application code bug. Save the scrubbed cause chain, correlating request ID, and HSM audit events if available.

### 10.3. Watch out for PIN lockouts or session exhaustion

Many devices lock PINs after several wrong attempts and enforce login/session limits. Automated tests should not repeatedly try wrong PINs or open unbounded sessions. Use a separately managed test token and an approved testing procedure.

## 11. Runtime diagnostics and protecting sensitive information

To compare environments, record meaningful metadata:

~~~java
import java.security.Provider;
import java.security.Security;

public class SecurityDiagnostics {
    public static void main(String[] args) {
        System.out.println(
                System.getProperty("java.runtime.version"));
        System.out.println(
                System.getProperty("java.vendor"));

        for (Provider provider : Security.getProviders()) {
            System.out.printf(
                    "%s : %s%n",
                    provider.getName(),
                    provider.getVersionStr());
        }

        System.out.println(
                "TLS restrictions configured: " +
                (Security.getProperty(
                        "jdk.tls.disabledAlgorithms") != null));
    }
}
~~~

This is a cautious logging example; production reports may need policy details for comparison, but must comply with configuration protection rules. Do not automatically dump all security properties, aliases, or key metadata into public logs.

### 11.1. Debug logging

Some JDKs support security debug options such as:

~~~bash
java -Djava.security.debug=help
~~~

The command above lists supported debug options on a specific runtime; help syntax may vary by launcher/JDK. When tracing JSSE, `javax.net.debug` can be used according to the corresponding JDK documentation.

Conditional example in a test environment:

~~~bash
java -Djavax.net.debug=ssl,handshake -jar app.jar
~~~

TLS/PKCS#11 debug logs can contain certificate details, endpoints, mechanisms, or system metadata. Restrict them to authorized environments, scrub secrets, avoid enabling broad debugging in production, and never share raw logs containing sensitive data.

### 11.2. Collecting native/HSM information

When the provider exists yet the token fails, diagnostic tools supplied by the HSM vendor are often needed to verify:

- Native library version, bitness, and dependencies.
- Daemon/network access to the HSM (if required).
- Slot and token label.
- Login status.
- Supported mechanisms/algorithms.
- Key access permissions and session counts.
- Audit events and concurrency limits.

Do not include secrets/PINs in diagnostic output. In many systems, only the HSM team is permitted to run administration tools; the application team must coordinate via operational procedures.

## 12. Designing PKCS#11 tests for migration

Unit tests using only software providers cannot replace end-to-end integration tests with PKCS#11 if production must sign inside an HSM.

A matrix to govern:

| Axis | Test values | Purpose |
|---|---|---|
| JDK | Baseline and target JDK/updates | Catch provider/policy changes |
| Distribution | Vendors supported by the product | Spot implementation differences |
| OS/CPU | Linux/Windows/ARM64, etc. | Verify ABI/native libraries |
| PKCS#11 library | Current and upgraded vendor versions | Detect driver regressions |
| Token type | Test token, hardware model | Verify mechanism/key attributes |
| Key type | RSA, EC, other types if used | Ensure correct algorithm support |
| Algorithm | Signing/encryption algorithms in the contract | Check transformations/parameters |
| Login mode | Interactive, service/managed secret | Verify secret lifecycle |
| Concurrency | 1, multiple requests, peak | Test session limits |
| Failure mode | Token offline, session timeout | Test controlled error/recovery |

### 12.1. Testing levels

**Level 1 — Provider availability**

- Does the JDK have the required module/bridge?
- Is the provider registered or configured successfully?
- Do the service/algorithm names appear?

**Level 2 — Token access**

- Does the native library load?
- Is the token/slot correct?
- Does login work in the test environment?
- Does KeyStore list the expected aliases/certificates?

**Level 3 — Cryptographic operation**

- Sign data using the private key in the token.
- Verify the signature with the corresponding public key/certificate.
- Test the key sizes and parameters used in production.
- Require no export of the private key.
- Reconcile operations with device audit logs if policy requires.

**Level 4 — Application integration**

- Complete mTLS or business-signing flows.
- Certificate chain and trust validation.
- Exception handling, timeouts, and retry strategy.
- Concurrency, session pooling, and failover.
- Monitoring does not leak PINs or key data.

### 12.2. SoftHSM or simulated tokens

A software PKCS#11 simulator such as SoftHSM can be used in CI to test API flows and packaging, but results do not prove compatibility with all hardware HSMs.

Differences may lie in:

- Supported mechanisms.
- Session concurrency.
- Key attributes.
- PIN policies.
- Latency and HA parameters.
- Vendor-specific behavior.

Combine **CI with software test tokens** and **integration tests on production-like vendor devices/environments** before major releases.

### 12.3. Verifying no policy-violating fallback exists

If signing mandates an HSM, verify that an absent token produces an **explicit failure**, without silently falling back to a private key file or software provider. Switching providers simply because "an algorithm was found" is insufficient to preserve the private key boundary.

Fail-closed tests must be designed safely in a test environment—never intentionally disconnect a production HSM.

## 13. JDK upgrade scenario: from software provider to token

Suppose a digital signing service currently uses a PKCS12 file and now needs to move its private key into an HSM:

**Before migration:**

~~~java
KeyStore ks = KeyStore.getInstance("PKCS12");
try (var in = java.nio.file.Files.newInputStream(path)) {
    ks.load(in, password);
}
~~~

**After migration — conceptual flow:**

1. Install the PKCS#11 vendor client on the target OS/container.
2. Verify HSM/token, slot, login, and key attributes.
3. Configure the PKCS#11 provider.
4. Open a `PKCS11`-type `KeyStore` with that provider.
5. Select the right certificate/private key in the token.
6. Call `Signature` with the approved algorithm and provider.
7. Verify the signature with the certificate/public key.
8. Test end-to-end without exporting the private key.

Moving from PKCS12 to PKCS11 is not merely changing the string `"PKCS12"` to `"PKCS11"`. It changes **key provenance**, provisioning processes, access control, secret management, recoverability, and operations.

### 13.1. Keeping the environment reproducible

When receiving a report that "signing failed on the new JDK", require a record with fields:

~~~yaml
runtime:
  java_version: "Target JDK release and update"
  distribution: "Approved vendor"
  os_arch: "Linux-x86_64"
security:
  configured_providers:
    - "Provider names and versions"
  provider_for_signature: "Expected HSM provider"
pkcs11:
  library_version: "Vendor client version"
  token_model: "Test model"
  slot_selection: "Documented configuration"
  mechanism: "Expected signing mechanism"
application:
  artifact_sha256: "Hash of tested artifact"
  key_identity: "Non-secret stable identifier"
tests:
  provider_load: "PASS/FAIL"
  keystore_open: "PASS/FAIL"
  sign_and_verify: "PASS/FAIL"
  mTLS_flow: "PASS/FAIL/NOT_APPLICABLE"
~~~

Never record token PINs, private keys, secret configs, or sensitive information in the record.

### 13.2. Multi-environment rollout

A deployment sequence could be:

1. Inventory current production JDK/providers/native libraries.
2. Stand up a test environment with the target JDK and matching HSM client.
3. Run single-threaded and concurrent tests with test keys.
4. Verify certificates and key mappings.
5. Run business signing/mTLS regression tests.
6. Deploy canary with audit/monitoring.
7. Monitor PKCS#11 errors, signing latency, and session usage.
8. Expand rollout based on defined thresholds, with a rollback plan ready.
9. After rollout, lock in the baseline provider and operational documentation.

Rollback may depend on whether keys were provisioned in the HSM and which data/certificates were already issued. Do not assume reverting to the old application version alone is sufficient; prepare a key and certificate compatibility plan.

## 14. Common mistakes

### 14.1. Only checking Security.getProvider(...)

Provider presence does not mean the native library, token, PIN, and signing mechanisms work. Test actual signing operations.

### 14.2. Pinning provider names at every call site

Hardcoding a vendor-specific provider can make hash/Cipher operations that do not need an HSM non-portable. Constrain the provider only where architecture/policy requires it.

### 14.3. Changing provider order to fix a local issue

Global ordering can cause JSSE, SecureRandom, and other engines to pick new implementations. Prefer fixing the specific call site and checking system-wide impact.

### 14.4. Confusing PKCS#11 with PKCS#12

PKCS12 is a keystore format; PKCS11 is an interface to a token. A `.p12` file cannot be used as proof that a key is protected by an HSM.

### 14.5. Assuming every JDK vendor has the same native bridge

A custom runtime may omit `jdk.crypto.cryptoki`; other vendors may have distinct mechanisms. Verify the module, provider, and native library in the target artifact/runtime.

### 14.6. Hardcoding slotListIndex or aliases as permanent IDs

Slot/alias ordering can shift after driver or token updates. Use proper mappings and key/cert validation procedures.

### 14.7. Ignoring key attributes

Having a private key on a token does not mean signing is allowed with every mechanism. Check policies and key attributes.

### 14.8. Logging PINs for debugging

PINs and secrets must be protected. Use a secret management system, and avoid command-line arguments and logs. Zero out PIN arrays where appropriate, without treating that as a complete security solution.

### 14.9. Blindly relaxing JDK policies

A certificate rejected for weak algorithms should not be "fixed" by disabling `disabledAlgorithms` globally. Replace the certificate, upgrade the algorithm, or follow a controlled migration plan.

### 14.10. Testing only with SoftHSM and claiming production HSM compatibility

Simulated tokens do not fully reflect native drivers, hardware mechanisms, and session behavior. Verify on representative devices and operations.

### 14.11. Ignoring build vs. runtime differences

An application may compile on a new JDK yet run inside a stripped JRE image or on an OS missing the vendor PKCS#11 library. Bytecode compatibility does not guarantee security-provider compatibility.

### 14.12. Not verifying which key was used on the device

Even when a signature is valid, it may have been generated with a different key or provider than expected. For systems mandating an HSM, establish a way to verify key identity and hardware execution.

## 15. Upgrade checklist

### JDK and providers

- [ ] Recorded JDK distribution, version, update, and OS/CPU.
- [ ] Listed security provider names, order, and critical services.
- [ ] Verified `jdk.crypto.cryptoki` module or equivalent bridge is present.
- [ ] Distinguished KeyStore/Cipher/Signature providers from JSSE/TLS providers.
- [ ] Reviewed security properties for restricted algorithms.
- [ ] Documented where providers are registered and configured.

### PKCS#11 and tokens

- [ ] Verified native library path and OS dependencies.
- [ ] Verified slot/slotListIndex, token identity, and key mappings.
- [ ] Verified PIN/secret management per policy.
- [ ] Opened PKCS11 KeyStore and listed matching aliases/certificates.
- [ ] Tested signing operations using the private key on the device.
- [ ] Verified the key is non-extractable where policy requires.
- [ ] Checked mechanisms, key attributes, and certificate chains.
- [ ] Tested session concurrency, timeouts, and failure handling.
- [ ] Avoided logging secrets or triggering PIN lockouts in production.

### Cross-environment compatibility

- [ ] Tested on the minimum JDK and target JDK.
- [ ] Tested across actually supported JDK distributions.
- [ ] Tested with the exact vendor native library and HSM model.
- [ ] Verified custom runtime/jlink images are not missing modules.
- [ ] Verified container permissions, drivers, and network connectivity to the HSM.
- [ ] Ran end-to-end business signing and mTLS flows if used by the product.
- [ ] Verified no fallback violates security requirements.
- [ ] Saved artifact checksums, redacted logs, and test reports.
- [ ] Prepared rollout, canary, monitoring, and rollback plans.

## Conclusion

Security providers form the implementation layer for many Java cryptography engines; PKCS#11 is the interface linking applications to tokens/HSMs through a provider and native library. When upgrading the JDK, these layers can change depending on **the Java distribution, packaged modules, provider order, algorithm policies, OS/CPU, vendor libraries, and HSM mechanisms**.

A reliable migration strategy does not stop at listing `Security.getProviders()` or compiling cleanly. You must confirm **which provider executes which operation**, **where the private key resides**, **which modules/native libraries are in effect**, and **whether end-to-end signing/TLS succeeds on the target environment**. Record results per specific artifact, runtime, and HSM; retain only compatibility options and fallback mechanisms approved by security policy.

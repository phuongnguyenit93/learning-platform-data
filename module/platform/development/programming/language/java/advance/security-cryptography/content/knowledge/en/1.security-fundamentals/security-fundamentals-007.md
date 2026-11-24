# 1.7. Map of JCA, JCE, JSSE, JAAS, PKI, and JDK Tools

## Learning Objectives

After this lesson, you can (1) distinguish Java's security technology layers, (2) locate the right API when hashing, encrypting, signing, establishing TLS connections, or authenticating users, (3) understand why `KeyStore`, certificates, and truststores appear across multiple layers, and (4) use `keytool`, `jarsigner`, and JDK debugging mechanisms to diagnose real-world issues. This is an **architectural map and tool selection guide**, not a guide to designing your own cryptographic protocol.

## 1. Big Picture: What Question Does Each Name Answer?

| Component | Main Role | Representative APIs/Concepts | Example Scenarios |
| --- | --- | --- | --- |
| **JCA** – Java Cryptography Architecture | API and **provider** architecture for cryptographic services, keys, certificates, and certificate validation | `MessageDigest`, `Signature`, `SecureRandom`, `KeyPairGenerator`, `KeyStore`, `CertificateFactory` | SHA-256 hashing, Ed25519 signing/verifying, reading certificates |
| **JCE** – Java Cryptography Extension | Historical name for cryptographic APIs like encryption, MACs, and secret keys; **now integrated into JCA/JDK**, not a competing provider system | `javax.crypto.Cipher`, `Mac`, `KeyGenerator`, `SecretKey`, `GCMParameterSpec` | AES-GCM encryption, HMAC generation |
| **JSSE** – Java Secure Socket Extension | Provides secure network communication via TLS/DTLS, using underlying primitives/providers and trust info | `SSLContext`, `SSLSocket`, `SSLEngine`, `KeyManager`, `TrustManager` | HTTPS client, TLS server, mTLS |
| **JAAS** – Java Authentication and Authorization Service | **Pluggable identity authentication** model and `Subject`/`Principal` representing a user or service | `LoginContext`, `LoginModule`, `CallbackHandler`, `Subject` | Kerberos login or a JAAS-integrated authentication mechanism |
| **PKI** – Public Key Infrastructure | Trust infrastructure around public keys, X.509, CAs, and certificate chains; **not a single standalone library** | `X509Certificate`, `CertPath`, `CertPathBuilder`, `CertPathValidator`, `TrustAnchor` | Deciding whether to trust a server certificate |
| **JDK Tools** | Generating/inspecting keys, certificates, CSRs, JAR signatures, and security diagnostics | `keytool`, `jarsigner`, `jar`, `java -D...debug=...` | Preparing TLS keystores, verifying signed JARs, debugging handshake failures |

**Key connection:** JCE lives within the JCA ecosystem; JSSE uses cryptographic services/providers and typically validates X.509 via PKI; JAAS handles identity authentication at a different layer. A successful HTTPS connection **does not automatically** mean a user is logged in via JAAS.

```text
Java Application
├─ Data / business logic protection
│  └─ JCA + JCE → provider → hash, MAC, encryption, keys, signatures
├─ Network communication
│  └─ JSSE (TLS/DTLS) → KeyManager / TrustManager
│                       └─ PKI/X.509 + JCA services
├─ Identity login/authentication via JAAS
│  └─ LoginContext → LoginModule → Subject/Principal
└─ Operations
   └─ keytool / jarsigner / security properties / TLS debug
```

The same `KeyStore` can be used by a JCA application to read a data-signing key, or by JSSE as a source of TLS private keys/certificates. **Usage role** determines whether it acts as an identity store or a truststore, not merely the file extension.

## 2. JCA: Engine APIs Separated from Provider Implementations

JCA defines *engine* classes following the `getInstance(algorithm)` pattern. Applications request a service by algorithm name; the JDK consults registered **security providers** to locate a matching implementation. This enables adding software providers, HSM/PKCS#11 providers, or specialized providers without rewriting all engine-calling code.

Example:

```java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
byte[] sha256 = digest.digest(data);

Signature verifier = Signature.getInstance("Ed25519");
// verifier.initVerify(publicKey); verifier.update(data); verifier.verify(signature);
```

This is an **illustrative snippet**; `data`/`publicKey`/`signature` must be supplied; a complete runnable program is in Section 8. `MessageDigest` only hashes data, while `Signature` uses asymmetric keys to verify signatures.

Provider resolution flow:

1. Application calls `Cipher.getInstance("AES/GCM/NoPadding")` or `Signature.getInstance("Ed25519")`.
2. JCA checks providers by configured/priority order and service support; a specific provider can be requested when truly needed.
3. Engine returns an implementation object; the application initializes it with keys and parameters before processing data.
4. You can inspect the serving provider via `getProvider()` for diagnostics.

Engine groups to recognize:

| Task | Choose API | Do Not Confuse With |
| --- | --- | --- |
| Keyless hashing | `MessageDigest` | HMAC/signature: a hash alone **does not authenticate the sender** |
| Shared-secret authentication code | `Mac` | Digital signature: HMAC cannot be verified by third parties with a public key |
| Asymmetric signing/verifying | `Signature` | Encryption: signatures do not hide plaintext |
| Encryption/decryption | `Cipher` | Hash: encryption can be decrypted with the proper key |
| Secure random generation | `SecureRandom` | `Random` for simulations/games |
| Symmetric/asymmetric key generation | `KeyGenerator` / `KeyPairGenerator` | `KeyFactory` converts existing key representations |
| Storing/accessing keys/certificates | `KeyStore` | Certificates do not contain the subject's private key |
| Building/validating certificate chains | `CertPathBuilder` / `CertPathValidator` | Merely parsing a certificate with `CertificateFactory` |

Do not treat an algorithm name as guaranteeing an entire secure design: encryption mode, IV/nonce, key length, key lifecycle, disabled algorithms, data sizes, and provider configuration all matter. Specifically, do not rely on ambiguous defaults like `Cipher.getInstance("AES")`; request the full transformation.

You can inspect your JVM's providers directly:

```java
import java.security.Provider;
import java.security.Security;

public class ProvidersDemo {
    public static void main(String[] args) {
        for (Provider p : Security.getProviders()) {
            System.out.println(p.getName() + " " + p.getVersionStr());
        }
    }
}
```

Run via `javac ProvidersDemo.java` then `java ProvidersDemo`. **Provider lists and versions depend on JDK build/vendor/OS**, so there is no fixed stdout. Do not hardcode names like `SunJCE` or `SunJSSE` if your application must run across multiple JVMs/providers, unless explicitly required by deployment constraints.

## 3. JCE: Application Cryptography Within the Same JCA Architecture

The name **JCE** dates back to when encryption features were shipped as an extension. In modern Java, `javax.crypto` is a standard part of the JDK and operates via JCA's provider mechanism. There is no need to "install a separate JCE" on standard Java 17+ for common AES/HMAC usage.

Practical choices:

- **Protecting stored data confidentiality:** typically use authenticated encryption (*AEAD*) like `AES/GCM/NoPadding`. Decrypted data must pass tag verification; ciphertext is accepted only when authentication succeeds.
- **Ensuring integrity and authenticity between parties sharing a secret key:** use `HmacSHA256` (`Mac` API); anyone lacking the key cannot forge a valid MAC.
- **Proving private-key possession over data:** use `Signature` with a key pair; verifiers need the public key **and trust context** to bind a signature to an identity.
- **Storing user passwords:** never use plain SHA-256/HMAC as a password hash. Use a slow password derivation mechanism with a unique salt and appropriate cost parameters (e.g., PBKDF2 via `SecretKeyFactory` when policy fits; systems may use vetted Argon2/bcrypt solutions).

For AES-GCM, remember four components: **secret key**, **unique nonce/IV per encryption under the same key** (typically 12 bytes), **ciphertext**, and **authentication tag** (typically 128 bits). **AAD** (authenticated associated data) may be added: AAD is authenticated but not encrypted. Decryption requires the same key, IV, matching AAD, and ciphertext plus tag. Never reuse a key–nonce pair in GCM; never build nonces with `Random` or constants.

Use `SecureRandom` for secure randomness and `KeyGenerator` for keys. Key distribution, storage, rotation, and revocation must be designed separately; crypto APIs do not solve key management by themselves. Never log private keys, secret keys, tokens, sensitive plaintext, or keystore passwords.

## 4. JSSE: Using TLS for Data in Transit

JSSE resides in `javax.net.ssl`. It provides TLS/DTLS via `SSLContext`, `SSLSocket`/`SSLServerSocket`, `SSLEngine`, and factories. Higher-level APIs like `java.net.http.HttpClient` use TLS for HTTPS calls without most applications managing handshake steps manually.

Common roles:

| Component | Responsibility |
| --- | --- |
| `SSLContext` | TLS configuration/context used to create sockets/engines, holding key/trust managers and session state |
| `KeyManager` | Selects **our own private key + certificate chain** when proving identity to the peer |
| `TrustManager` | Evaluates **the peer's certificate** against trusted certificates/anchors and policy |
| `SSLEngine` | Handles TLS independently of how the application performs I/O; suited for nonblocking models |
| `SSLSocket` | TLS-enabled socket for transferring data over an authenticated handshake channel |

Typical HTTPS flow (simplified model):

1. Client connects to server and exchanges TLS parameters; server presents its X.509 certificate and required chain.
2. Client validates the chain against accepted trust anchors, validity dates, constraints, and algorithm policies; HTTPS clients must also verify that the **hostname** matches the certificate identity (typically in SAN).
3. Handshake establishes session keys; application data is then encrypted and authenticated inside the TLS channel.
4. With **mTLS**, the server also requests a client certificate, and the client picks a matching key/certificate for mutual authentication. This does not replace business authorization requirements.

In standard HTTPS applications, prefer letting `HttpClient` or a standard TLS-capable HTTP library perform certificate and hostname verification. Never disable hostname checks or use a "trust all" `TrustManager` to silence errors. With raw `SSLSocket`, **do not assume endpoint name verification is enabled automatically**: configure proper endpoint identification, e.g., `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` when targeting HTTPS.

High-level HTTPS client snippet (requires network; illustrative only, no fixed stdout):

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

HttpClient client = HttpClient.newHttpClient();
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/")).GET().build();
HttpResponse<Void> response =
        client.send(request, HttpResponse.BodyHandlers.discarding());
System.out.println(response.statusCode());
```

These lines belong inside a method handling exceptions or declaring `throws Exception`. **JSSE is not "PKI"**: TLS is a transport protocol, whereas PKI is the foundation for establishing trust in public keys/certificates across many protocols.

## 5. JAAS: Authenticating a Subject, Not Replacing TLS or Encryption

JAAS uses a configurable authentication architecture. An application invokes `LoginContext` by configuration name; the config specifies `LoginModule`s; modules can gather inputs via `CallbackHandler`, verify via a real mechanism (such as Kerberos), and attach `Principal`/credentials to a `Subject` upon success.

```text
Application → LoginContext("MyApp")
            → Configuration → LoginModules
            → CallbackHandler (if input/verification needed)
            → login succeeds → Subject { Principal, credentials }
            → business logic decides access permissions
```

Conceptual API snippet:

```java
LoginContext context = new LoginContext("MyApp", handler);
context.login();
Subject authenticated = context.getSubject();
// Use principal/credential according to application policy.
context.logout();
```

This is **not a standalone runnable program**: it requires login configuration and an appropriate `handler`, plus imports for `javax.security.auth.Subject` and `javax.security.auth.login.LoginContext`. When implementing a custom `LoginModule`, understand the `initialize`, `login`, `commit`, `abort`, and `logout` lifecycle; never fake success merely because a `Principal` exists.

Distinctions to keep clear:

- **TLS server authentication:** the client knows which server the channel connects to via certificate/hostname; this belongs to JSSE/PKI.
- **JAAS authentication:** the system authenticates a user or entity via login modules; `Subject` represents the authenticated entity.
- **Authorization:** the application decides what that principal may do. JAAS supplies an identity/credential model to support this decision, yet does not generate full API authorization policies, business roles, OAuth2/OIDC, or JWT handling.
- **Kerberos/JGSS:** may involve JAAS in Kerberos-integrated applications; using JSSE does not automatically mean JAAS is required.

On modern JDKs, avoid equating "JAAS authorization" with legacy `SecurityManager`. Applications should define actual authorization mechanisms suited to their framework and architecture.

## 6. PKI/X.509: From Public Key to Trusted Identity

An **asymmetric key pair** consists of a shareable public key and a secret private key. An **X.509 certificate** binds a public key with subject, issuer, serial, validity period, issuer signature, and extensions. A certificate **does not contain the subject's private key**.

Common chain model:

```text
Root CA (configured trust anchor)
    ↓ signs/delegates
Intermediate CA
    ↓ signs
Server leaf certificate (SAN: api.example.com)
    + matching private key (held only by server)
```

Clients do not merely check "does the certificate have a valid signature"; they require a verifiable certification path up to an **accepted trust anchor**. In PKIX, also consider CA basic constraints, key usage/extended key usage, validity times, algorithm policies, and revocation checks (CRL/OCSP) as configured. **Hostname verification is a TLS/HTTPS endpoint identification requirement and must not be inferred from path validation success alone.**

Related APIs:

- `CertificateFactory.getInstance("X.509")`: parses/converts certificates and chains from encoded data.
- `X509Certificate`: inspects subject, issuer, SAN, validity, extensions, and public key.
- `CertPathBuilder.getInstance("PKIX")`: discovers a certification path from the leaf given input data/policies.
- `CertPathValidator.getInstance("PKIX")`: validates a certification path against `PKIXParameters` and `TrustAnchor`.
- `CertStore`: source of candidate certificates/CRLs, not automatically a trusted root list.
- `PKIXRevocationChecker`: configures revocation checking when an appropriate mechanism is required.

Commonly confused concepts:

| Concept | Practical Meaning |
| --- | --- |
| **CSR** – Certificate Signing Request | Request for a certificate; typically contains public key and identifying info, signed by the matching private key; **a CSR is not yet a certificate issued by a trusted CA** |
| **Self-signed certificate** | Signed by its own matching private key; suitable for testing/controlled private CAs, not inherently trusted by external clients |
| **Root CA/trust anchor** | Trust point chosen by administrator, OS, or runtime; meaningful because it is **configured as trusted**, not because it appears in a chain |
| **SAN** – Subject Alternative Name | Holds DNS/IP identities used for modern endpoint matching; setting `CN=localhost` alone is usually insufficient |
| **Certificate chain** | Certificates supporting proof of the issuance path; missing intermediates or wrong key usage causes errors |
| **PEM, DER, PKCS#12** | Data formats/containers; PEM is typically Base64 with headers, DER is ASN.1 binary, PKCS#12 is a container able to hold keys/certificates |

Never import a certificate received from an unknown server into your truststore just to silence an error. Doing so alters your trust anchors and can mask real issues: wrong hostname, missing intermediate, expired certificate, or an unapproved CA.

## 7. KeyStore, Truststore, and the JDK Toolset

`KeyStore` is an API for storing/accessing entries by **alias**. Common uses in Java applications:

- **Identity keystore:** entries holding the application's **private key + certificate chain**. JSSE `KeyManager` reads it to pick an identity to present to servers/clients.
- **Truststore:** holds certificates chosen as trust anchors; `TrustManager` uses it when verifying peers. Both may share the `KeyStore` structure, yet serve different security purposes.
- **PKCS12 (`.p12`/`.pfx`):** typical default keystore format since JDK 9, widely used to exchange keys/certificates. `JKS` is an older Java format; `PKCS11` can point to tokens/HSMs. A file extension alone does not guarantee its contents are properly protected.
- **`cacerts`:** CA store shipped with the JDK for default trust (different JVMs/vendors may configure it differently). Modifying `cacerts` on a shared machine has broad impact; prefer application-specific truststores when appropriate.

### Local Lab: Creating a Self-Signed TLS Identity and Separate Truststore

The commands below are **single-line commands**, run in a test directory on a JDK with `keytool`. They prompt for passwords in the terminal; never put real passwords into CLI arguments or repositories.

**Step 1 – generate an RSA key pair and self-signed certificate for localhost:**

```shell
keytool -genkeypair -alias local-server -keyalg RSA -keysize 3072 -dname "CN=localhost" -ext "SAN=dns:localhost,ip:127.0.0.1" -validity 30 -storetype PKCS12 -keystore server.p12
```

`server.p12` holds the private key and certificate under alias `local-server`. `-ext SAN=...` models localhost identity properly for TLS testing.

**Step 2 – inspect the entry and export only the public certificate:**

```shell
keytool -list -v -keystore server.p12
keytool -exportcert -rfc -alias local-server -keystore server.p12 -file server.crt
keytool -printcert -v -file server.crt
```

`-exportcert` does not export the private key. Verify SAN, issuer = subject in the self-signed case, validity, and fingerprint. A fingerprint is only meaningful when verified through a trusted channel.

**Step 3 – create a truststore trusting only that local certificate:**

```shell
keytool -importcert -alias local-server -file server.crt -keystore client-trust.p12 -storetype PKCS12
keytool -list -v -keystore client-trust.p12
```

When the tool asks whether to trust the certificate, **only confirm in a lab where you generated/verified the fingerprint yourself**. `client-trust.p12` holds the trusted certificate, not the server's private key. This illustrates a local trust anchor; production should use an organization-approved CA and govern issuance, renewal, and revocation.

**Step 4 – picturing a real CA workflow:** `keytool -certreq -alias local-server -keystore server.p12 -file server.csr` generates a CSR for an existing key pair. The CA verifies identity and issues a certificate; you then import the CA chain/certificate reply into the exact entry holding the private key. Do not confuse generating a CSR with being trusted already.

**Other noteworthy tools:**

| Tool/Command | When to Use | Limitations to Remember |
| --- | --- | --- |
| `keytool -list -cacerts` | View the running JDK's default CA store | List depends on distribution/configuration; not identical across all JVMs |
| `keytool -importkeystore ...` | Convert/copy entries between keystores | Verify alias, entry type, passwords, and certificate chain |
| `jarsigner -keystore signing.p12 -signedjar app-signed.jar app.jar signing-alias` | Sign a **JAR** using the private key of the signing alias | Requires `app.jar` and a keystore with private key; not a TLS certificate issuance step |
| `jarsigner -verify -verbose -certs app-signed.jar` | Inspect JAR signatures and protected entries | A valid JAR signature **does not automatically** mean the signer is system-trusted; read warnings/chain |
| `jar tf app.jar` | List JAR contents when inspecting artifacts | Does not replace signature verification |
| `java -Djavax.net.debug=ssl,handshake ...` | Observe TLS handshakes while running an app | Can print sensitive details; use only during controlled debugging |
| `java -Djava.security.debug=certpath ...` | Inspect PKIX certificate validation steps | Verbose logs; manage output and access controls |

`jarsigner` handles **code signing**; `keytool` primarily manages key/certificate material; both rely on JCA/PKI components. Neither replaces TLS for network data exchange.

### Runtime Security Configuration to Recognize

The JDK ships a security config file typically at `<java-home>/conf/security/java.security`. Properties such as `security.provider.N` set provider order; `jdk.tls.disabledAlgorithms` restricts TLS algorithms/protocols; `jdk.certpath.disabledAlgorithms` constrains certificate path validation; `jdk.jar.disabledAlgorithms` governs JAR signatures. Loading, overrides, and defaults vary by version/distribution. **Prefer upgrading the JDK and fixing root certificate/configuration issues; never relax weak-algorithm blocklists as a quick fix.**

Certain JSSE system properties can specify application keystore/truststore, such as `javax.net.ssl.keyStore`, `javax.net.ssl.trustStore`, and their type/password counterparts. Distinguish these **system properties** from **security properties** in `java.security`; not every API/framework uses the default `SSLContext` or default properties.

## 8. Java 17+: Resolving Engines via Providers and Identifying API Boundaries

This example **does not encrypt or sign data again**. Instead, it verifies how engines resolve actual providers and identifies the separate JSSE/JAAS packages. This addresses the **JDK map** question specifically, distinct from the primitive comparison demo in the encryption/hash/MAC/signature lesson.

Create `SecurityApiMapDemo.java`:

```java
import java.security.MessageDigest;
import java.security.Provider;
import javax.crypto.Cipher;
import javax.net.ssl.SSLContext;
import javax.security.auth.login.LoginContext;

public class SecurityApiMapDemo {
    public static void main(String[] args) throws Exception {
        MessageDigest digest =
                MessageDigest.getInstance("SHA-256");
        Cipher aesGcm = Cipher.getInstance("AES/GCM/NoPadding");

        Provider digestProvider = digest.getProvider();
        Provider cipherProvider = aesGcm.getProvider();

        System.out.println("Digest provider resolved: "
                + (digestProvider != null));
        System.out.println("Cipher provider resolved: "
                + (cipherProvider != null));
        System.out.println("JSSE package: "
                + SSLContext.class.getPackageName());
        System.out.println("JAAS package: "
                + LoginContext.class.getPackageName());
    }
}
```

Compile/run on JDK 17+ with standard SHA-256 and AES-GCM providers:

```bash
javac --release 17 SecurityApiMapDemo.java
java SecurityApiMapDemo
```

Stdout:

```text
Digest provider resolved: true
Cipher provider resolved: true
JSSE package: javax.net.ssl
JAAS package: javax.security.auth.login
```

The first/last lines only indicate that engines found providers and classes belong to their respective packages, **not** that TLS verified a certificate, JAAS logged in, or encryption ran correctly. To see exact provider names, print `digestProvider.getName()` and `cipherProvider.getName()`, though names vary by JDK/distribution/configuration. `Cipher.getInstance(...)` only confirms the transformation exists; using the right key, nonce/AAD, and handling tags remain the application's responsibility.

Across the chapter's examples and tools, always separate: **Java engine**, **implementing provider**, **PKI trust config**, and **business authorization**.

## 9. Picking the Right Layer in Real-World Scenarios

**Scenario A – internal config file needing confidentiality and tamper detection:** encrypt using `Cipher` with AEAD (JCE/JCA); keys need secure storage, rotation, access control, and a data format carrying nonce/tag. TLS does not protect content once written to disk.

**Scenario B – calling an HTTPS API:** use `HttpClient` or a standard TLS-capable HTTP client (JSSE); verify certificate chain via PKI and hostname; when mTLS is needed, configure client private key/certificate alongside server trust. Do not use JAAS to "replace" HTTPS certificate validation.

**Scenario C – document whose signing author must be verifiable:** `Signature` signs with a private key and verifies with a public key; to trust "who signed it," distribute trusted public keys or use PKI/certificate policies. `MessageDigest` alone is insufficient.

**Scenario D – integrating Kerberos login:** consider JAAS `LoginContext`/`LoginModule`, `Subject`, and related Kerberos/GSS integration; endpoint permissions still depend on application policy.

**Scenario E – signing internal JARs:** manage signing keys via `keytool`/key management systems, use `jarsigner`, verify signatures and trust chains. Signing a JAR does not encrypt bytecode and does not automatically guarantee loading/running the JAR is safe.

## 10. Troubleshooting Errors and Common Mistakes

| Symptom | Where to Check First | What to Avoid |
| --- | --- | --- |
| `NoSuchAlgorithmException` / `NoSuchPaddingException` | Engine/algorithm/transformation name, registered providers, JDK version | Swapping security algorithms arbitrarily just to "make it run" |
| `AEADBadTagException` | Key, nonce, AAD, ciphertext/tag; tampering, encoding/transport corruption | Ignoring the tag or returning plaintext when auth fails |
| `SSLHandshakeException` with `PKIX path building failed` | Client truststore, root/intermediate CAs, server-sent chain, validity, PKIX policy | Disabling trust validation or blindly importing leaf certificates |
| Hostname/SAN error | Actual accessed DNS/IP vs. certificate SAN | Disabling hostname verification |
| `UnrecoverableKeyException` / unable to pick alias | Password, key entry, entry type, alias, and chain | Logging private keys or passwords to debug |
| TLS fails to negotiate version/cipher suite | Both sides' TLS policies, `jdk.tls.disabledAlgorithms`, provider/JDK | Re-enabling weak SSL/TLS in production |
| JAAS `LoginException` | App name in configuration, LoginModule, CallbackHandler, identity data, auth dependencies | Treating TLS success as proof `login()` ran |
| `jarsigner -verify` shows warnings | Signer certificate, trust, validity period, timestamp, disabled algorithms | Equating "has signature" with "trusted publisher" |

Sensible debugging flow: **identify the failing layer → check exact API/configuration → inspect bounded logs → fix root cause → re-verify**. Avoid leaving TLS/CertPath debugging enabled long-term in production since logs can expose metadata, grow huge, and obscure critical signals.

## 11. Summary Checklist and Self-Check Questions

- **Need a hash?** `MessageDigest`. **Need a MAC?** `Mac`. **Need encryption?** `Cipher`/AEAD. **Need signing?** `Signature`. All live inside JCA (including what was historically called JCE).
- **Need a TLS network channel?** JSSE/standard HTTP client. **Need certificate/chain validation?** PKI/X.509 and `TrustManager`/`CertPath`. **Need pluggable login modules?** JAAS.
- **Need to create/inspect keys, certificates, CSRs?** `keytool`. **Need to sign/verify JARs?** `jarsigner`. **Need handshake debugging?** `javax.net.debug`; for certificate path debugging, consider `java.security.debug=certpath`.
- **Need production deployment?** Use clear trust/identity configs, modern algorithms, secure key storage, hostname verification, rotation, and business authorization; never trust all certificates and never use local self-signed demos as production policy.

Answer for yourself: (1) Why do `AES/GCM` and TLS both encrypt yet not replace each other? (2) Why can a certificate with a valid signature still be rejected by HTTPS? (3) What distinguishes HMAC, digital signatures, and plain SHA-256? (4) If a server requires mTLS, what extra material does the client need? (5) Why does a JAAS `Subject` not automatically grant access to every API?

**Guided answers:** (1) AEAD protects payloads under application keys/nonces; TLS protects network transport sessions with peer authentication. (2) Wrong trust anchor, expiration, SAN/hostname mismatch, key usage, or policy violation. (3) Hash is keyless; HMAC uses a shared secret; signatures use private/public keys. (4) The client needs a matching private key and certificate chain to present; it must still trust the server. (5) The application must enforce authorization according to its own business policies.

## Authoritative Documentation for Deeper Reading

- [Java Cryptography Architecture (JCA) Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-cryptography-architecture-jca-reference-guide.html): providers/engines, keys, and cryptographic operations; explains why JCE belongs to modern JCA.
- [Java Secure Socket Extension (JSSE) Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html): TLS, `SSLContext`, key/trust managers, endpoint identification.
- [JAAS Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-authentication-authorization-service-jaas-reference-guide.html): `LoginContext`, `LoginModule`, `Subject`, authentication configs.
- [Java PKI Programmer's Guide](https://docs.oracle.com/en/java/javase/21/security/java-pki-programmers-guide.html): `CertPathBuilder`, `CertPathValidator`, `TrustAnchor`, PKIX validation.
- [keytool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html) and [jarsigner](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jarsigner.html): tool syntax, signing, and warnings.

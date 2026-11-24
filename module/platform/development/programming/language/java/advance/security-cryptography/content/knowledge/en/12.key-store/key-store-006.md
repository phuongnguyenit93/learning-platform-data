# 12.6. Reading Keys with Certificate Chains and Handling Wrong Aliases or Passwords

Java's `KeyStore` is a **repository of key and certificate entries** accessed through `java.security.KeyStore`. A PKCS#12 (`.p12`/`.pfx`) file can hold a **private key** and its **certificate chain**, or other entries. To use it properly, an application must separate **opening the store with a store password**, **selecting an entry by alias**, **unlocking the entry with a key password**, and **verifying whether the chain/certificates are valid for the intended purpose and trustworthy**.

In lesson **12.6** under **"12. KeyStore"**, we use Java 21 and `keytool` to build a test PKCS#12 store, read a private key with a two-certificate chain, check existing/missing aliases, simulate both kinds of wrong passwords, and analyze exceptions. A runnable Java program shows the real output, and the lesson then explains the demo's limits and what production requires.

## Objectives

After this lesson, you will be able to:

1. Distinguish `KeyStore`, **PKCS12/JKS**, `PrivateKeyEntry`, `SecretKeyEntry`, `TrustedCertificateEntry`, and aliases.
2. Use `KeyStore.getInstance("PKCS12")` and `load(InputStream, char[])` to open a store; understand the difference between **store password** and **entry/key password**.
3. Use `containsAlias`, `isKeyEntry`, `isCertificateEntry`, `getKey`, `getCertificate`, `getCertificateChain`, and `getEntry` in the right scenarios.
4. Read and inspect certificate chains in **leaf → issuer → ...** order, without confusing **reading a chain** with **the chain being trusted under PKIX**.
5. Distinguish **missing alias**, wrong entry type for an alias, **wrong store password**, **wrong key password**, corrupted/wrong-format files, and providers missing an algorithm.
6. Compile/run Java 21 on a fixture with a two-element chain; understand how to protect files, passwords, private keys, logs, and TLS/JSSE configuration after reading.

## 1. The KeyStore Model and What Is Actually Stored

`KeyStore` is an **abstract API**: exact storage layout and behavior are decided by the provider's `KeyStoreSpi`. In our example we explicitly specify `PKCS12` so we do not depend on `KeyStore.getDefaultType()` or environment configuration.

Conceptual structure:

```text
demo.p12 (PKCS12)
|
+-- alias: service-signing
|     type: PrivateKeyEntry
|     privateKey: RSA private key (password-protected per provider)
|     chain[0]: leaf cert CN=service.example.test
|     chain[1]: issuer cert CN=Demo CA
|
+-- alias: demo-ca
      type: PrivateKeyEntry (lab CA with its own private key)
      privateKey: CA signing key used to issue the leaf certificate
      chain[0]: self-signed CA certificate
```

*Note:* Both aliases here are **`PrivateKeyEntry`** because they were created with `keytool -genkeypair`. A CA certificate imported separately into a truststore (without a private key) is normally a **`TrustedCertificateEntry`**. In real systems, **never** place a CA private key into the same file deployed to an application server; they coexist here solely so the lab can easily build a verifiable certificate chain.

| Concept | Meaning | Identification API |
| --- | --- | --- |
| `alias` | Internal entry name, e.g., `service-signing`; **not a verified identity** | `containsAlias(alias)`, `aliases()` |
| `PrivateKeyEntry` | Private key + matching **certificate chain**, used for signing or TLS auth depending on purpose | `isKeyEntry`, `getEntry`, `getKey`, `getCertificateChain` |
| `SecretKeyEntry` | Symmetric key, e.g., AES; has no X.509 chain in the private-key entry sense | `isKeyEntry`, `getEntry` |
| `TrustedCertificateEntry` | A certificate stored per trust policy (contains no private key) | `isCertificateEntry`, `getCertificate` |
| `store password` | Used during `load` to open and/or verify file integrity | `load(input, storePassword)` |
| `key/entry password` | Used when retrieving a protected key from an entry | `getKey(alias, keyPassword)`, `getEntry(alias, ProtectionParameter)` |
| Certificate chain | Leaf certificate and issuer certificates to assist building a validation path | `getCertificateChain(alias)` |
| Trust anchor | CA/public key trusted **independently of data sent by the peer** | `TrustAnchor`, PKIX validator/truststore policy |

A `KeyStore` can serve as an **identity keystore** (holding a server/client's private key) or a **truststore** (holding certificates approved by the organization), yet these two roles should not be combined in hard-to-govern ways.

## 2. Reading Workflow: Four Distinct Steps

Suppose you need the private key and chain under alias `service-signing`:

```text
[Path demo.p12]
    |
    v
KeyStore.getInstance("PKCS12")
    |
    v
load(InputStream, storePassword)    <-- wrong password/file -> load error
    |
    v
containsAlias("service-signing")    <-- false if alias does not exist
    |
    v
isKeyEntry(alias) / getEntry type   <-- wrong entry type -> cannot use as private key
    |
    +--> getKey(alias, keyPassword)        <-- password unlocking entry
    |
    +--> getCertificateChain(alias)        <-- leaf at [0], then issuer...
                  |
                  v
    Verify key matches certificate, purpose, PKIX trust/policy
```

These operations answer **different** questions:

- **`load` succeeds:** the provider read/initialized the KeyStore using the supplied parameters per its supported mechanism. That does not prove all desired aliases exist, nor does it validate any internal certificate against a trusted CA.
- **`containsAlias == true`:** an entry with that name exists; it does not say whether it is a private key, trusted certificate, or secret key.
- **`getKey` succeeds:** the entry provided a key and the password matched. The key may be a `PrivateKey` or `SecretKey`; check its type, algorithm, and usage rights before using it.
- **`getCertificateChain` returns a value:** the file stores a certificate chain. It is **not** a check of CA trust, hostname, validity period, EKU, key usage, revocation, or path constraints.
- **Private key and leaf public key match:** can be verified by a test sign/verify with an appropriate scheme. Even this is not yet a conclusion that the chain belongs to a trusted organization.

**Do not treat an alias as a username.** An alias locates an entry in a file; identity and usage rights must come from trusted sources and application policies.

## 3. Creating a PKCS#12 Fixture with a Two-Certificate Chain

This lab uses **JDK 21** or a newer JDK whose `keytool` supports `-signer`. You need an empty directory for `demo.p12` and the Java file. Below we use **3072-bit RSA**, `SHA256withRSA` signatures, and a **30-day** certificate validity. The self-signed CA is a **test certificate**, not automatically trusted by operating systems/browsers.

### 3.1 Setting a Lab-Only Password

`keytool` supports the `:env` modifier to read passwords from an environment variable. For lab reproducibility, the two commands below set a **dummy password**. Never use this string in real systems; avoid placing real secrets in source code, shell history, or logs.

**Windows PowerShell:**

```powershell
$env:DEMO_KS_PASS = 'DemoOnly-ChangeMe42'
```

**Linux/macOS (Bash):**

```bash
export DEMO_KS_PASS='DemoOnly-ChangeMe42'
```

In production, fetch secrets from a secret manager/KMS, protected input, or controlled deployment mechanism. Environment variables still carry exposure risks via config/process/debugging tools; `:env` only avoids **passing the password directly as a literal argument** `-storepass value` on the command line.

### 3.2 Creating a Temporary CA to Sign the Service Certificate

Run from the demo directory:

```text
keytool -genkeypair -alias demo-ca -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -dname "CN=Demo CA,O=Training,C=VN" -ext "BC:critical=ca:true,pathlen:0" -ext "KU:critical=keyCertSign,cRLSign" -validity 30 -keystore demo.p12 -storetype PKCS12 -storepass:env DEMO_KS_PASS -keypass:env DEMO_KS_PASS -noprompt
```

This creates a test CA key pair; `BC=ca:true` and `keyCertSign` express certificate-signing intent. `keytool` creates a self-signed CA certificate, so **`demo-ca`'s chain has only one element**.

### 3.3 Creating the Service Key and Certificate Signed by the Test CA

```text
keytool -genkeypair -alias service-signing -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -dname "CN=service.example.test,O=Training,C=VN" -ext "SAN=dns:service.example.test" -ext "KU:critical=digitalSignature" -signer demo-ca -signerkeypass:env DEMO_KS_PASS -validity 30 -keystore demo.p12 -storetype PKCS12 -storepass:env DEMO_KS_PASS -keypass:env DEMO_KS_PASS -noprompt
```

`-signer demo-ca` uses the private key at the CA alias to sign the certificate for `service-signing`. Thus the new entry has a **two-certificate chain**: leaf then CA. This lets us test `getCertificateChain` without **granting trust** to the self-signed CA.

In the example, both the store password and key password use `DEMO_KS_PASS` because many PKCS#12 implementations/integrations require or prefer identical passwords. **At the API level, store password and entry password remain two distinct inputs**, even when they share a value in the fixture. JKS and some other providers/stores follow different rules; never assume every PKCS#12 across every JDK supports two independent passwords.

### 3.4 Using `keytool` to Inspect the Structure Before Writing Java

```text
keytool -list -v -alias service-signing -keystore demo.p12 -storetype PKCS12 -storepass:env DEMO_KS_PASS
```

Key lines (minor formatting differences vary by JDK):

```text
Alias name: service-signing
Entry type: PrivateKeyEntry
Certificate chain length: 2
Owner: CN=service.example.test, O=Training, C=VN
Issuer: CN=Demo CA, O=Training, C=VN
...
Owner: CN=Demo CA, O=Training, C=VN
Issuer: CN=Demo CA, O=Training, C=VN
```

Java may select different key providers, yet **alias, entry type, and chain length** confirm the expected structure. `-list -v` prints only metadata/chains and **does not export the private key**.

If you run `-genkeypair` a second time on an existing file/alias, `keytool` rejects the duplicate alias. Perform the lab in a separate directory, never touching real truststores/`cacerts` or production keystores.

## 4. Java 21: Reading Private Key + Certificate Chain and Testing Errors

Create a file named **`KeyStoreReadDemo.java`** in the same directory as `demo.p12`. The program takes a **file path** and an **alias** on the command line, and reads the lab password from `DEMO_KS_PASS`. It prints booleans and chain length, **never printing the private key, password, or secret ciphertext**.

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.Key;
import java.security.KeyStore;
import java.security.MessageDigest;
import java.security.Signature;
import java.security.UnrecoverableKeyException;
import java.security.cert.Certificate;
import java.security.cert.X509Certificate;
import java.util.Arrays;

public final class KeyStoreReadDemo {
    private static KeyStore open(Path file, char[] storePassword)
            throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream input = Files.newInputStream(file)) {
            store.load(input, storePassword);
        }
        return store;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: java KeyStoreReadDemo <file.p12> <alias>");
        }
        String passwordFromEnvironment = System.getenv("DEMO_KS_PASS");
        if (passwordFromEnvironment == null
                || passwordFromEnvironment.isEmpty()) {
            throw new IllegalStateException("Missing DEMO_KS_PASS");
        }

        Path path = Path.of(args[0]);
        String alias = args[1];
        char[] password = passwordFromEnvironment.toCharArray();
        char[] incorrect = "intentionally-wrong".toCharArray();
        try {
            KeyStore store = open(path, password);

            System.out.println("keystore type: " + store.getType());
            System.out.println("alias present: " + store.containsAlias(alias));
            System.out.println("is key entry: " + store.isKeyEntry(alias));
            System.out.println("missing alias: " +
                    !store.containsAlias("not-present"));
            System.out.println("missing key is null: " +
                    (store.getKey("not-present", password) == null));
            System.out.println("missing chain is null: " +
                    (store.getCertificateChain("not-present") == null));

            if (!store.containsAlias(alias) || !store.isKeyEntry(alias)) {
                throw new IllegalStateException("Missing/private key alias");
            }
            Key key = store.getKey(alias, password);
            if (!(key instanceof java.security.PrivateKey privateKey)) {
                throw new IllegalStateException("Not a private key entry");
            }
            Certificate[] chain = store.getCertificateChain(alias);
            if (chain == null || chain.length < 2) {
                throw new IllegalStateException(
                        "Expected leaf and issuer certificates");
            }
            X509Certificate leaf = (X509Certificate) chain[0];
            X509Certificate issuer = (X509Certificate) chain[1];
            System.out.println("certificate chain length: " + chain.length);
            System.out.println("leaf first: " +
                    leaf.equals(store.getCertificate(alias)));
            System.out.println("issuer name linked: " +
                    leaf.getIssuerX500Principal().equals(
                            issuer.getSubjectX500Principal()));
            leaf.verify(issuer.getPublicKey()); // Signature link only.
            System.out.println("issuer signature verifies: true");

            byte[] message = "certificate-key match".getBytes(
                    StandardCharsets.UTF_8);
            Signature signer = Signature.getInstance("SHA256withRSA");
            signer.initSign(privateKey);
            signer.update(message);
            byte[] signature = signer.sign();
            Signature verifier = Signature.getInstance("SHA256withRSA");
            verifier.initVerify(leaf.getPublicKey());
            verifier.update(message);
            System.out.println("private key matches leaf: " +
                    verifier.verify(signature));

            boolean wrongStoreRejected = false;
            try {
                open(path, incorrect);
            } catch (IOException expected) {
                wrongStoreRejected = true;
            }
            System.out.println("wrong store password rejected: " +
                    wrongStoreRejected);

            boolean wrongKeyRejected = false;
            try {
                store.getKey(alias, incorrect);
            } catch (UnrecoverableKeyException expected) {
                wrongKeyRejected = true;
            }
            System.out.println("wrong key password rejected: " +
                    wrongKeyRejected);
        } finally {
            Arrays.fill(password, '\0');
            Arrays.fill(incorrect, '\0');
        }
    }
}
```

**Compile and run:**

```text
javac -version
javac --release 21 -encoding UTF-8 KeyStoreReadDemo.java
java KeyStoreReadDemo demo.p12 service-signing
```

When the file is created properly with the commands above, stdout from the Java program:

```text
keystore type: PKCS12
alias present: true
is key entry: true
missing alias: true
missing key is null: true
missing chain is null: true
certificate chain length: 2
leaf first: true
issuer name linked: true
issuer signature verifies: true
private key matches leaf: true
wrong store password rejected: true
wrong key password rejected: true
```

The programs were tested with a compiler supporting `--release 21` and standard JDK providers; exact error messages from `keytool`/JDK vary by vendor/patch, yet **the Java stdout lines above accurately reflect the created fixture and program conditions**. If you choose a different alias, chain, password, or provider, outputs or exception types may differ; never "fix" expected output by skipping checks.

### 4.1 Key Observations

- `KeyStore.getInstance("PKCS12")` selects the explicit format. `load(InputStream, storePassword)` reads bytes and applies the password per provider policy; `try-with-resources` closes the file stream even if loading fails.
- `containsAlias(alias)` and `isKeyEntry(alias)` check structure before retrieval. `getKey` returns the general `java.security.Key` type, so `instanceof PrivateKey` confirms a private key is present for signing.
- `getCertificateChain(alias)` returns the chain or `null`. For the `PrivateKeyEntry` fixture, the chain length is 2: element **0** is the leaf, element **1** is the issuer. For a self-signed root or another fixture, chain length may be 1; that is not a Java API bug.
- `getCertificate(alias)` returns the leaf certificate for a private-key entry. `leaf.equals(store.getCertificate(alias))` confirms they match in the fixture.
- `leaf.getIssuerX500Principal() == issuer.getSubjectX500Principal()` in code uses `equals` to verify name linkage; `leaf.verify(issuer.getPublicKey())` then checks the leaf's signature with the issuer's public key. **Neither step creates a trust anchor!**
- The program test-signs fresh bytes with the private key and verifies with the **leaf public key**. Returning `true` confirms the key pair matches for `SHA256withRSA` in the fixture; production still requires checking policies, key usages, validity, and trust.
- Alias `not-present` is absent: `containsAlias` returns `false`, while `getKey` and `getCertificateChain` return `null`. That is a normal lookup outcome, **not an automatic exception**.
- Wrong store password is tested via `open(path, incorrect)` → `IOException`; wrong key password is tested **after the store has loaded successfully** via `getKey(alias, incorrect)` → `UnrecoverableKeyException`. The two checks occur at **two distinct stages**.

**Important distinction:** the program only tests wrong passwords on a self-created fixture. Never handle "wrong password" by trying unlimited values or logging full passwords/stack traces to API logs. In real systems, password checks at endpoints/CLIs need retry limits, safe user-facing error messages, and proper resource management.

## 5. `KeyStore.getEntry`: Reading Entries by Exact Type

Beyond `getKey` and `getCertificateChain`, you can read via `KeyStore.getEntry(alias, new KeyStore.PasswordProtection(keyPassword))` and inspect the entry type.

The snippet below is **illustrative**, used **inside a program that already has a loaded `store`**, `alias`, and `keyPassword` (not a standalone class):

```java
KeyStore.Entry entry = store.getEntry(
        alias, new KeyStore.PasswordProtection(keyPassword));

if (entry instanceof KeyStore.PrivateKeyEntry privateEntry) {
    java.security.PrivateKey key = privateEntry.getPrivateKey();
    java.security.cert.Certificate[] chain =
            privateEntry.getCertificateChain();
    // Apply policy before using key; never log private key.
} else if (entry instanceof KeyStore.SecretKeyEntry) {
    throw new IllegalArgumentException("Alias contains a secret key");
} else if (entry instanceof KeyStore.TrustedCertificateEntry) {
    throw new IllegalArgumentException("Alias is certificate only");
} else if (entry == null) {
    throw new IllegalArgumentException("Alias not found");
}
```

`KeyStore.PrivateKeyEntry` represents a private key + chain; `SecretKeyEntry` has no X.509 chain like a private key; `TrustedCertificateEntry` has a certificate without a private key. `KeyStore.PasswordProtection` holds the password for accessing the entry, so it should have a bounded secret lifecycle (call `destroy()` when done).

**Exceptions:** `getEntry` can throw `UnrecoverableEntryException` if protection parameters are insufficient/invalid, including wrong passwords. When calling `getKey` directly, `UnrecoverableKeyException` is typical. These are two API entry points declaring different exception types.

### 5.1 `isKeyEntry` Is Not Enough to Prove "It Is a Private Key"

`isKeyEntry(alias)` returns true for both private-key entries and secret-key entries. If an application needs a server TLS certificate, it requires a **`PrivateKeyEntry` + chain + matching keyUsage/purpose**; an AES `SecretKey` in the KeyStore cannot substitute merely because `isKeyEntry` returns `true`.

Conversely, `isCertificateEntry(alias)` returns true for a **`TrustedCertificateEntry`** alias. For a leaf alias with a private key, it normally returns `false` even though `getCertificate(alias)` returns a leaf certificate. This is a frequent source of confusion when checking keystores with boolean methods.

## 6. How Java Handles Wrong Aliases or Passwords

| Scenario | API | Typical/Documented behavior | How to handle |
| --- | --- | --- | --- |
| Alias does not exist | `containsAlias("missing")` | `false` | Report invalid alias configuration; optionally list aliases safely internally. |
| Alias has no key | `getKey(alias, keyPass)` | `null` if alias is missing or does not represent a key | Check `containsAlias` and entry type; never dereference `null`. |
| Alias has no chain | `getCertificateChain(alias)` | `null` if alias is missing or lacks a chain | Verify exact `PrivateKeyEntry` and business requirements for chains. |
| Alias is certificate-only | `isCertificateEntry(alias)` | May be `true`, `isKeyEntry` is `false` | Never use as a signing private key. |
| Wrong store password | `load(input, storePass)` | Usually `IOException` with password/integrity-related cause | Abort load, distinguish from file/format errors in internal logs; do not assume identical error detail across providers. |
| Wrong key password | `getKey(alias, keyPass)` | `UnrecoverableKeyException` | Do not treat as missing alias; verify secret reference and provider policy. |
| Wrong entry password | `getEntry(alias, protection)` | `UnrecoverableEntryException` / matching subclass | Verify `PasswordProtection`; never ignore error and continue with null key. |
| File missing / unreadable | `Files.newInputStream(path)` | `NoSuchFileException`/`AccessDeniedException` or other `IOException` | Check path, permissions, mounts, working directory. |
| Store type/provider/algorithm unsupported | `KeyStore.getInstance`/`load`/`getKey` | `KeyStoreException` / `NoSuchAlgorithmException` or related error | Check JDK/provider, format, protection algorithms. |
| Certificate unparseable | `load` | Possibly `CertificateException` | Check data, provider, encoding, and trust configuration. |
| Store used before `load` | `getKey`/`aliases` | `KeyStoreException` | Call `load` properly before accessing entries. |
| Password right yet chain untrusted | `getCertificateChain` | Still returns the chain | Perform separate path validation and identity checks. |

### 6.1 Both Passwords May Share One String Yet Are Not Synonymous

There are two distinct protection gates:

```text
demo.p12
   +-- load(storePassword) -----------------> integrity/open
   +-- getKey("service-signing", keyPassword) -> recover private key
```

In the lab, both come from `DEMO_KS_PASS`. For many PKCS#12 files, setting two different values is **not** broadly compatible; some JDKs/providers normalize key password = store password. For JKS or HSMs, rules may differ. Therefore APIs should **keep two configuration fields distinct**, while store-creation workflows must align with actual format/provider capabilities.

**Avoid a dangerous trick:** calling `load(input, null)` just to "read the file without knowing the password". Per the `KeyStore` contract, when no integrity-check password is supplied, **integrity checking may be skipped**; other providers may enforce their own constraints. This is not a fix for wrong passwords and does not replace integrity verification.

### 6.2 Never Guess an Alias from Filename or `CN`

The alias `service-signing` does not have to equal `CN=service.example.test`. Aliases are chosen by the store creator; `CN`/SAN live in the certificate subject/extensions; server identity must be verified from the certificate **per TLS/application policy**, never from the alias.

Some providers apply alias normalization rules (such as lowercasing) or differ in case sensitivity. **Never assume aliases are universally case-sensitive or case-insensitive.** For real stores, inspect the aliases returned by the provider using `keytool -list -keystore ...` or `store.aliases()`, and configure the exact name.

Example code to audit aliases **for internal operational tooling** (never print this to public clients):

```java
java.util.Enumeration<String> names = store.aliases();
while (names.hasMoreElements()) {
    String name = names.nextElement();
    System.out.println(name + ": key=" + store.isKeyEntry(name)
            + ", trustedCert=" + store.isCertificateEntry(name));
}
```

Never print `key.getEncoded()`, `password`, or full certificates/private keys without an explicit requirement. Metadata and aliases can also leak system structure, so keep logs restricted.

## 7. Reading a Certificate Chain Does Not Mean Trust Is Verified

`getCertificateChain(alias)` returns stored certificates in **leaf-first** order; the source may be the PKCS#12 file itself or data supplied by a sender. A self-signed or malformed chain can still parse and be returned.

In the demo:

```text
service-signing:
  [0] CN=service.example.test    <- leaf; public key matches private key
  [1] CN=Demo CA                 <- issuer certificate (test self-signed)
```

`leaf.verify(issuer.getPublicKey())` only checks **the leaf's signature against the supplied issuer public key**; it does not confirm the issuer is trusted. `leaf.checkValidity()` (if called) checks expiration at a point in time, yet does not check hostname, key usage, revocation, or trust anchors.

### 7.1 Actual Steps to Validate a Chain

If you receive a chain and need to know whether **your organization accepts it**, you must define purpose and trust policy, for example:

1. **Trust an independent anchor:** maintain a truststore/root CA/pinned key configured and protected by the organization, never taking a trust anchor from the peer's unverified chain itself.
2. **Build and validate the PKIX path:** verify signatures on every certificate, basic constraints/path length limits, validity periods, algorithms/key strengths, constraints, and appropriate policies.
3. **Verify target identity/name:** e.g., TLS HTTPS requires matching a DNS SAN against the hostname after chain validation; a `CN` that "looks right" is insufficient in modern profiles.
4. **Verify intended usage:** key usage, extended key usage when applicable, application policy, and signer/tenant authorization.
5. **Revocation:** when threat models/policies require it, configure OCSP/CRL or appropriate revocation mechanisms; never assume every `CertPathValidator` call enables and completes revocation automatically.
6. **Manage pin/truststore lifecycle:** expiration, rotation, removal, CA replacement, update access control, and auditing.

Java provides `CertPathValidator`, `CertPathBuilder`, `PKIXParameters`, and `TrustAnchor` for custom PKIX handling. However, for TLS, it is safer to let **JSSE `TrustManager`/`SSLContext`** enforce profile validation and client hostname verification rather than writing ad hoc certificate verifiers.

**Never import the demo CA into a production truststore.** It is a self-signed CA meaningful only for the lab; a chain signature verifying cleanly proves nothing about belonging to a real trusted organization.

### 7.2 Does the Private Key Match the Leaf Certificate?

A properly structured keystore entry should hold a private key matching the leaf's public key. The program uses `SHA256withRSA` to sign a test message with the private key and verify it with the leaf public key. If `verify` returns `true`, the key pair matches **for the chosen RSA signature algorithm**.

This check does not replace certificate chain validation, does not verify issuing authority, and not every key type uses RSA/`SHA256withRSA`. If the real key is EC or Ed25519, select the matching scheme and valid policy; never hardcode `Signature.getInstance("SHA256withRSA")` for all private keys just because the lab code assumes RSA.

## 8. PKCS#12 and KeyStore When Configuring TLS/JSSE

When a Java server must present a TLS certificate with its private key, the typical setup is:

```text
PKCS12 (private key + certificate chain)
    |
    v
KeyManagerFactory (uses key password if provider requires)
    |
    v
SSLContext / SSLEngine / SSLSocket (server certificate + private-key proof)
                       |
                 client verifies:
        truststore + PKIX + hostname/service identity
```

A separate client truststore holds **trusted CAs/public keys** for verifying the server; `TrustManagerFactory` creates the trust managers. A server successfully loading `demo.p12` or retrieving `PrivateKey` **does not prove a TLS handshake will succeed** or that the client trusts the server's certificate.

In TLS, a server certificate also needs matching **`extendedKeyUsage`/`keyUsage`**, valid SANs, and a valid issuer chain up to a trust anchor; you must verify protocol versions/cipher suites, key management, expiration/rotation, and error handling. The lab fixture uses `KU=digitalSignature` and a service SAN for illustration, yet the self-signed CA is untrusted outside the lab, so **never use it as a real TLS certificate**.

If multiple aliases hold private keys, `KeyManager` can choose an alias by algorithm/certificate request. Configuring explicit aliases and certificate chains prevents picking the wrong key, though final selection depends on JSSE/provider and application policy.

## 9. Rules for Protecting KeyStore, Certificate Chains, and Passwords

- **Protect files and backups:** PKCS#12 may use password-based encryption/integrity yet still contains sensitive key material; restrict OS permissions, ownership, backup access, mount/container paths, and service-account read permissions.
- **Never hardcode production secrets:** use KMS/HSM/secret managers or protected inputs. Avoid passwords in source, Git, CLI arguments, CI output, exception messages, and logs. Environment variables are convenient for demos/automation yet can still be exposed.
- **Use `char[]` when APIs support it:** call `Arrays.fill(password, '\0')` after use. This does not guarantee clearing every copy in the JVM/provider; reading via `System.getenv` produces an immutable `String` that cannot be completely wiped.
- **Never print private keys:** `PrivateKey.getEncoded()` (when allowed by the provider) can contain actual private key bytes. Log only aliases/key types/necessary metadata with restricted access.
- **Never brute-force passwords automatically:** wrong passwords must stop and be classified clearly; missing-alias errors differ from password errors, though public responses may need to be uniform to avoid information leaks.
- **Avoid `null` passwords to skip verification:** protect integrity and availability; handle exceptions per policy, check checksums/signatures when appropriate, and never "recover" by disabling validation.
- **Key rotation:** swap entry aliases, private keys, and certificate chains under a rollback-capable procedure, verifying client trust chains before cutover; never deploy a new chain missing an intermediate issuer assuming clients will fetch it automatically.
- **Never assume chains always have length 2 or include the root:** many systems store leaf + intermediates without the root; `getCertificateChain` can have length 1, more than 2, or null. The `length >= 2` check in the demo is a **fixture requirement**, not a general PKIX rule.

## 10. Common Errors Illustrated by the Example

| Symptom | Root cause | Reasonable remediation |
| --- | --- | --- |
| `containsAlias("service-signing") == false` | Wrong alias, wrong store, alias altered during import/conversion | List aliases internally; verify exact file/type and config. |
| `getKey(...) == null` | Alias does not exist or does not represent a key | Distinguish from wrong password; check `containsAlias`, `isKeyEntry`. |
| `getCertificateChain(...) == null` | Alias has no chain / is not a private-key entry | Check entry type, import complete chain, check policy. |
| `getKey` throws `UnrecoverableKeyException` | Wrong entry password or provider cannot recover | Check secret source/config; never try random passwords. |
| `load` throws `IOException` | Wrong store password, corrupted/truncated file, or incompatible format | Check format, path, permissions, password via secure channel; inspect internal cause. |
| `getEntry` throws `UnrecoverableEntryException` | Wrong/incompatible `PasswordProtection` | Check entry type and provider contract. |
| `InvalidKeyException` on signing | Private key incompatible with `Signature` scheme | Check `key.getAlgorithm()`, provider, key usage, scheme. |
| Chain len = 1 in lab | Generated self-signed leaf without `-signer demo-ca`, or used CA alias | Check fixture creation command and `keytool -list -v` output. |
| Leaf has issuer name yet verify fails | Certificate altered, wrong issuer public key, bad signature | Reject chain; build path and verify via PKIX/trust policy. |
| Leaf verifies yet TLS client still rejects | CA not a trust anchor, wrong SAN/EKU/validity/policy | Use proper TLS TrustManager/truststore; never disable hostname/cert checks. |
| Works locally, container fails alias/password | Container mounted wrong file, different secret/config, different JDK/provider | Safely verify file hashes and deployment config without logging secrets. |
| Private key readable yet certificate expired | Keystore storage does not enforce PKIX policy | Monitor expiration, rotate certificates, and validate at TLS/app layers. |

## 11. Self-Practice Exercises

1. **Alias and type:** after creating `demo.p12`, run `keytool -list -v` for `demo-ca` and `service-signing`. Why are both `PrivateKeyEntry` yet have different chain lengths?
2. **Wrong alias:** change the Java argument to `unknown-key`. With the current demo code, which lines flip to `false`, and why does the program stop at the guard instead of calling `getKey` on the wrong alias?
3. **Wrong store password:** set an environment variable with a different password before running Java; predict which exception arises at `load`. Restore the right lab password after observing—never alter production passwords to test.
4. **Wrong key password:** keep the store password right, pass a wrong password solely to `getKey(alias, wrongPassword)`. Why does `containsAlias` stay `true` even though the key cannot be recovered?
5. **Reading the chain:** print the **subject/issuer names** of `chain[0]`/`chain[1]` (on lab data only), identify leaf vs. CA, and explain why `leaf.verify(issuer.getPublicKey())` is not enough to trust the CA.
6. **Entry types:** design a truststore with a certificate-only entry and test `isCertificateEntry`, `getCertificate`, `getCertificateChain`, and `getKey`; note each API's result.
7. **Trust:** if an attacker creates their own CA and signs a fake leaf certificate with a real-looking name, which validation step prevents the client from trusting that chain?
8. **Packaging errors:** rename the file, change the path, revoke read permissions; compare with wrong-alias and wrong-password errors to pinpoint where each fails in the pipeline.
9. **Intermediate chains:** if you have root CA → intermediate CA → leaf, in what order should `getCertificateChain` arrange them? Is it mandatory to store the root certificate in the entry? Why or why not?
10. **Service design:** sketch a TLS server setup with a PKCS12 identity store and client truststore, an alias/cert rotation process, and behavior when a cert expires.

**Completion criteria:** you can clearly state **which file is opened, which store type, which alias, which entry type, which password is used at each stage, whether the key matches the leaf, what order the chain is stored in, and how the chain must be trusted**. Never confuse "successfully read private key + chain" with "certificate validated" or "TLS system is secure".

## References

- [Java SE 21 — `java.security.KeyStore`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyStore.html): `load`, `getKey`, `getEntry`, `getCertificateChain`, `containsAlias`, exceptions, and entry contracts.
- [Java SE 21 — `KeyStore.PrivateKeyEntry`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyStore.PrivateKeyEntry.html): private key, chain, ordering, and entry conditions.
- [Java SE 21 — `java.security.cert.X509Certificate`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/X509Certificate.html): subject, issuer, verify, validity, and extensions.
- [JDK 21 — `keytool` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html): `-genkeypair`, `-signer`, `-list`, `-storetype`, `-storepass:env`.
- [Java SE 21 — `CertPathValidator`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/CertPathValidator.html): PKIX certification path validation (requires trust/policy config).
- [Java SE 21 — `PKIXParameters`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/PKIXParameters.html): trust anchors and validation constraints.
- [Java 21 JSSE Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html): KeyManager/TrustManager, truststores, SSLContext, and TLS certificate validation.
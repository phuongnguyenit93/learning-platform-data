# Keystore Formats in Java

A **keystore format** is a storage format for cryptographic entries such as private keys, certificate chains, trusted certificates, and, depending on the provider, secret keys. The `keytool` utility and the `java.security.KeyStore` API can read, create, list, import, export, and convert keystores between formats supported by the JDK or security providers.

When working with TLS, digital signatures, or application authentication, you need to choose a format compatible with the runtime and the systems you integrate with. In modern Java, **PKCS12 is the default format in the standard JDK configuration starting from JDK 9**; JKS is still encountered in legacy systems, while JCEKS typically appears in Java applications that need to store secret keys according to its corresponding provider.

A keystore is a container. File extensions such as `.jks`, `.p12`, or `.pfx` are merely conventions; they do not prove which format the actual contents belong to. When operating on a keystore, explicitly specify `-storetype` and inspect it with `keytool -list`.

## 1. What types of entries does a keystore store?

A keystore can contain multiple entries identified by aliases. Supported entry types depend on the format and provider.

| Entry type | Contents | Purpose |
|---|---|---|
| `PrivateKeyEntry` | A private key with its corresponding certificate chain | TLS server/client authentication, digital signing |
| `TrustedCertificateEntry` | A trusted certificate, without a private key | Storing a CA or trusted certificate |
| `SecretKeyEntry` | A symmetric secret key | Symmetric encryption/decryption; depends on format/provider |

For example, a TLS server keystore might contain an alias `server` with a private key and certificate chain. A truststore might contain an alias `company-root-ca` with an internal CA certificate.

An alias is the name used to access an entry. A single file can contain multiple aliases and multiple entry types. When inspecting a keystore, verify the alias, entry type, certificate subject/issuer, validity period, and fingerprint rather than only checking whether the file exists.

## 2. How do a keystore and a truststore differ?

A **keystore** typically stores the application's own cryptographic identity, such as a server's private key and certificate chain.

A **truststore** typically stores certificates that the application trusts, such as a root CA or intermediate CA used to verify a peer server's certificate.

These are usage roles, not two different file formats. Both a keystore and a truststore can be JKS, PKCS12, or any other format supported by the provider.

| Component | Typical contents | Used when |
|---|---|---|
| Server keystore | Server private key + certificate chain | Server proves its identity to clients |
| Client keystore | Client private key + certificate chain | Client authenticates via mutual TLS |
| Truststore | Trusted CA/certificate entries | Verifying the peer's certificate |
| Application secret store | Secret key entries | Storing symmetric keys if supported by the provider/format |

Do not place private keys into a truststore just because both contain certificate data. In deployment, private keys must be protected much more strictly than public certificates.

## 3. Common formats

### 3.1. JKS

**JKS (Java KeyStore)** is the traditional keystore format tied to the Java ecosystem. It is commonly used in legacy Java applications and can store private keys with certificate chains or trusted certificate entries.

Characteristics:

- Java-specific format, not a widely interoperable standard container like PKCS12.
- Commonly found in files with the `.jks` extension.
- May require conversion when integrating with systems or tools outside Java.
- You should not assume the JKS provider supports every entry type, especially secret key entries.

JKS was Java's default type prior to JDK 9. Legacy systems may still require JKS, so do not change the format based solely on the file extension or JDK version.

### 3.2. PKCS12

**PKCS12** is a standard container format specified in RFC 7292. It is commonly used to exchange private keys and certificate chains across Java, web servers, operating systems, and certificate management tools.

Characteristics:

- Better interoperability across platforms and tools.
- Commonly uses the `.p12` or `.pfx` extension.
- The default JDK type starting from Java 9 in the standard configuration, controlled by the `keystore.type` security property.
- Suitable for many TLS scenarios and certificate/private key storage.
- Secret key storage support and password protection details depend on the implementation/provider and JDK version.

PKCS12 is a sound choice for new Java projects unless there are special compatibility requirements. When integrating with external systems, still verify the encryption algorithms, MAC, certificate chain, and support in the receiving software.

### 3.3. JCEKS

**JCEKS** is a Java-specific keystore format provided by the JDK's JCE provider. It supports storing secret key entries in addition to other appropriate entry types.

Characteristics:

- Commonly encountered in legacy Java applications that store symmetric secret keys.
- Does not have broad cross-platform interoperability like PKCS12.
- Depends on a provider that supports the `JCEKS` type.
- Compatibility should be evaluated before using it in cross-platform systems.

If an application uses JCEKS to store secret keys, do not convert it to another format and assume entries will be preserved. Test import/export on the exact target JDK/provider and verify each alias and key type after conversion.

### 3.4. Quick comparison

| Criterion | JKS | PKCS12 | JCEKS |
|---|---|---|---|
| Origin | Java-specific | PKCS #12 standard | Java-specific |
| Interoperability | Primarily Java ecosystem | Broader across platforms | Primarily Java ecosystem |
| Private key + certificate chain | Yes | Yes | Yes |
| Trusted certificate | Yes | Yes | Yes |
| Secret key entry | Standard JKS provider does not support like JCEKS | Provider/JDK-dependent | Yes |
| Modern JDK default | No | Yes, from JDK 9 in standard configuration | No |
| General recommendation | Maintain when legacy compatibility requires it | Default choice for most new use cases | Use only when specifically required |

Do not choose a format based solely on the file extension. Check the actual keystore type, provider, entry types, and application requirements.

## 4. Default keystore type in the JDK

Since JDK 9, the default keystore type in the standard security configuration changed from JKS to PKCS12. The default value is controlled by the `keystore.type` security property.

In Java, you can inspect the default value:

```java
import java.security.KeyStore;

public class DefaultKeystoreType {
    public static void main(String[] args) {
        System.out.println(KeyStore.getDefaultType());
    }
}
```

Compile and run on JDK 17+ with the default configuration:

```sh
javac DefaultKeystoreType.java
java DefaultKeystoreType
```

Stdout on a standard JDK with the default PKCS12 property:

```text
pkcs12
```

This value can change if the JDK security configuration or providers are customized. Therefore, do not infer the format solely from the Java version. In deployment scripts, explicitly specify `-storetype` so commands remain reproducible.

`KeyStore.getDefaultType()` only returns the runtime's default type. It does not prove that an existing file on disk actually uses that type.

## 5. Creating a PKCS12 keystore with keytool

Example creating an RSA key pair and self-signed certificate for a test environment:

```sh
keytool -genkeypair -alias app-server -keyalg RSA -keysize 3072 -validity 365 -dname "CN=localhost, OU=Development, O=Example, L=HCMC, C=VN" -ext "SAN=dns:localhost,ip:127.0.0.1" -keystore app-server.p12 -storetype PKCS12
```

Parameters:

- `-genkeypair`: generates a public/private key pair and certificate.
- `-alias app-server`: entry name in the keystore.
- `-keyalg RSA`: key pair generation algorithm.
- `-keysize 3072`: RSA key size.
- `-validity 365`: certificate validity in days.
- `-dname`: subject distinguished name.
- `-ext SAN=...`: adds a Subject Alternative Name for the hostname/IP in the example.
- `-keystore app-server.p12`: output file.
- `-storetype PKCS12`: selects the PKCS12 format.

If you do not pass a password on the command line, `keytool` prompts interactively. This is preferable for manual operations because it avoids exposing secrets in shell history or process listings.

Self-signed certificates are suitable for development and controlled testing. For production TLS, generate a CSR and obtain a certificate from an appropriate CA; do not use self-signed certificates as a default trust solution for external clients.

## 6. Listing and inspecting a keystore

List aliases and entry types:

```sh
keytool -list -keystore app-server.p12 -storetype PKCS12
```

View certificate details, subject, issuer, serial number, validity period, and fingerprints:

```sh
keytool -list -v -keystore app-server.p12 -storetype PKCS12
```

Options:

- `-list`: lists entries.
- `-v`: displays verbose details.
- `-keystore`: specifies the file.
- `-storetype`: specifies the format to read.

When checking before deployment, verify:

1. The file is read using the correct store type.
2. The required alias exists.
3. The entry is `PrivateKeyEntry` or `trustedCertEntry` as expected.
4. The certificate subject and issuer are correct.
5. The certificate is valid (not expired) and has an appropriate chain.
6. The fingerprint matches the value verified through a trusted channel.

Do not share passwords or private keys in logs, screenshots, or documentation.

## 7. Exporting a certificate to PEM

You can export the public certificate from an alias:

```sh
keytool -exportcert -alias app-server -keystore app-server.p12 -storetype PKCS12 -rfc -file app-server-cert.pem
```

`-rfc` requests output in PEM/Base64 format with header and footer. This file contains the public certificate, not the private key.

Distinction:

- **PKCS12** is a container that can hold private keys and certificates.
- **PEM** is a Base64 text representation for a certificate, public key, or private key according to its corresponding structure.
- **DER** is the binary ASN.1 encoding of a certificate/key structure.

Do not rename `.p12` to `.pem` to convert formats. Use an appropriate export/conversion tool and verify the output contents.

## 8. Creating a truststore and importing a CA certificate

To make an application trust a CA, import the CA certificate into a truststore:

```sh
keytool -importcert -alias company-root-ca -file company-root-ca.pem -keystore truststore.p12 -storetype PKCS12
```

`keytool` prompts for confirmation when importing interactively. Before accepting, verify the CA's fingerprint via an independent trusted channel, such as official PKI documentation or a system administrator.

After importing, inspect it:

```sh
keytool -list -v -keystore truststore.p12 -storetype PKCS12
```

The entry imported under the alias `company-root-ca` must be a trusted certificate entry. A truststore can contain multiple CAs/certificates if the application needs to verify multiple systems.

Do not import a certificate merely because it was attached to an email or downloaded from an unverified endpoint. Importing a certificate means configuring a trust anchor; this action directly affects TLS authentication.

## 9. Creating a CA-signed certificate

In production, the common workflow is to generate a private key in a keystore, export a CSR, send it to a CA for signing, and then import the certificate reply along with its chain.

### Step 1: Generate the key pair and keystore

```sh
keytool -genkeypair -alias app-server -keyalg RSA -keysize 3072 -dname "CN=service.example.com" -keystore app-server.p12 -storetype PKCS12
```

### Step 2: Generate a CSR

```sh
keytool -certreq -alias app-server -keystore app-server.p12 -storetype PKCS12 -file app-server.csr
```

Submit the CSR to the CA according to your certificate issuance process. The CSR contains the public key and request metadata; it does not contain the private key.

### Step 3: Import CA certificates/chain if needed

If the CA provides separate root/intermediate certificates, verify their fingerprints and import the CA certificates into the appropriate keystore/truststore per your organization's procedure. The order and method for installing the chain depend on the CA and the structure of the certificate reply.

### Step 4: Import the certificate reply

```sh
keytool -importcert -alias app-server -file app-server-chain.pem -keystore app-server.p12 -storetype PKCS12
```

When the alias already contains a private key, `keytool` uses the certificate reply to attach the certificate and chain to the corresponding private key. The certificate must match the public key in the CSR; otherwise, the import will fail.

### Step 5: Verify the chain

```sh
keytool -list -v -alias app-server -keystore app-server.p12 -storetype PKCS12
```

Check the subject, issuer, validity period, and certificate chain. Ensure the SAN includes the hostname/IP that clients actually use. Common Name alone does not replace SAN in modern TLS configurations.

## 10. Converting JKS to PKCS12

When upgrading legacy Java applications, you may need to convert JKS to PKCS12:

```sh
keytool -importkeystore -srckeystore legacy.jks -srcstoretype JKS -destkeystore modern.p12 -deststoretype PKCS12
```

The tool prompts for the source and destination keystore passwords if they are not provided. You do not need to write passwords directly into interactive commands.

Meaning:

- `-importkeystore`: copies entries from one keystore to another.
- `-srckeystore`: source file.
- `-srcstoretype JKS`: source format.
- `-destkeystore`: destination file.
- `-deststoretype PKCS12`: destination format.

You can select a specific alias using `-srcalias` and set the destination alias name with `-destalias`. If unspecified, `keytool` processes entries according to the command's import rules.

After converting, inspect both files:

```sh
keytool -list -v -keystore legacy.jks -storetype JKS
keytool -list -v -keystore modern.p12 -storetype PKCS12
```

Compare the alias count and alias names, entry types, subject/issuer, certificate validity, fingerprints, certificate chains, and the application's ability to read the private key.

Do not delete the source file immediately after importing. Keep a protected backup until the application has been configured and tested successfully with the new file.

## 11. Keystore password and key password

Common options:

- `-storepass`: password used to open/protect the keystore according to the implementation.
- `-keypass`: password protecting a private key entry when the format/provider supports a separate password.
- `-srcstorepass`: source keystore password during conversion.
- `-deststorepass`: destination keystore password during conversion.

Password behavior depends on the format and provider. JKS can support separate passwords for the keystore and private keys. With common JDK PKCS12 implementations, private keys are typically protected by the PKCS12 store password; do not assume `-keypass` can differ from `-storepass` as with JKS. Check the `keytool` documentation for your specific JDK/provider.

Protection principles:

- Use long, random, unique passwords.
- Do not commit passwords to source control.
- Avoid passing secrets directly on the command line whenever possible.
- Use a secrets manager or an organization-approved secret provisioning mechanism.
- Restrict keystore file read permissions at the operating system level.
- Do not send private keys or keystores containing private keys over insecure channels.
- Maintain procedures for backup, rotation, and certificate revocation.

A keystore password does not replace file access controls. Anyone with read access to the file can copy the container and attempt offline attacks; therefore, protect both the file and the password.

## 12. Using the KeyStore API in Java

Java provides the `java.security.KeyStore` API to read and manipulate keystores. Explicitly specify the type when the format is known:

```java
KeyStore keyStore = KeyStore.getInstance("PKCS12");
```

Reading a file:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;

char[] password = obtainPasswordSecurely();

KeyStore keyStore = KeyStore.getInstance("PKCS12");
try (InputStream input = Files.newInputStream(Path.of("app-server.p12"))) {
    keyStore.load(input, password);
}
```

`KeyStore.getInstance("PKCS12")` requires a provider that supports the PKCS12 type. `load` reads the container and verifies the password according to the implementation. If the file has an invalid format, the password is wrong, or the data is corrupted, the operation may throw an exception.

Commonly used methods:

| Method | Purpose |
|---|---|
| `KeyStore.getInstance(type)` | Creates an instance for the keystore type |
| `load(input, password)` | Loads the keystore |
| `store(output, password)` | Writes the keystore |
| `aliases()` | Lists aliases |
| `containsAlias(alias)` | Checks if an alias exists |
| `getKey(alias, password)` | Retrieves the key if the password and permissions are valid |
| `getCertificate(alias)` | Retrieves the entry's certificate |
| `getCertificateChain(alias)` | Retrieves the certificate chain |
| `isKeyEntry(alias)` | Checks whether the entry contains a key |
| `isCertificateEntry(alias)` | Checks whether it is a trusted certificate entry |
| `setCertificateEntry(alias, cert)` | Adds a trusted certificate |
| `deleteEntry(alias)` | Deletes an entry |

Do not log the result of `getKey()` or private key contents. When working with `char[]` passwords, clear the array contents after use if the application lifecycle permits.

## 13. Java 17+ program to safely list aliases

The following example reads a keystore using a user-specified type. The password is entered via the terminal using `Console.readPassword`, rather than passed in command-line arguments.

Create `KeystoreInspector.java`:

```java
import java.io.Console;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.cert.Certificate;
import java.util.Arrays;
import java.util.Enumeration;

public class KeystoreInspector {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println(
                "Usage: java KeystoreInspector <file> <type>");
            return;
        }

        Console console = System.console();
        if (console == null) {
            throw new IllegalStateException(
                "Run this program from an interactive terminal.");
        }

        char[] password = console.readPassword("Keystore password: ");
        if (password == null) {
            throw new IllegalStateException("No password was entered.");
        }

        try {
            KeyStore keyStore = KeyStore.getInstance(args[1]);

            try (InputStream input =
                     Files.newInputStream(Path.of(args[0]))) {
                keyStore.load(input, password);
            }

            System.out.println("Type: " + keyStore.getType());

            Enumeration<String> aliases = keyStore.aliases();
            while (aliases.hasMoreElements()) {
                String alias = aliases.nextElement();

                String entryType = keyStore.isKeyEntry(alias)
                    ? "key entry"
                    : keyStore.isCertificateEntry(alias)
                        ? "trusted certificate entry"
                        : "other";

                System.out.println(alias + " (" + entryType + ")");

                Certificate certificate = keyStore.getCertificate(alias);
                if (certificate != null) {
                    System.out.println(
                        "  Certificate type: " + certificate.getType());
                }
            }
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
```

Compile:

```sh
javac KeystoreInspector.java
```

Run with a PKCS12 file:

```sh
java KeystoreInspector app-server.p12 PKCS12
```

Run with a JKS file:

```sh
java KeystoreInspector legacy.jks JKS
```

The output lists the aliases and entry types in the file. The exact output depends on the keystore being read. The program must be run in an interactive terminal because `System.console()` may return `null` when run inside an IDE or when stdin is not a console.

This example only displays entry metadata and certificate types; it does not print private keys or passwords to stdout.

## 14. Selecting a provider and checking support

`KeyStore.getInstance(type)` searches registered providers for one that supports the requested type. A type may exist in the standard JDK or be supplied by an additional provider.

You can inspect an instance's provider:

```java
import java.security.KeyStore;

KeyStore store = KeyStore.getInstance("PKCS12");
System.out.println(store.getProvider().getName());
```

The provider determines many implementation details, such as supported entry types, protection algorithms, password handling, and compatibility with files created by other implementations.

When an application runs across multiple JDKs or providers:

1. Verify the type is available in the target environment.
2. Check which provider is actually selected.
3. Test reading files created by the source system.
4. Test loading, listing aliases, and retrieving certificates.
5. Test the actual operations needed, such as retrieving a private key or verifying a chain.
6. Re-test after upgrading the JDK or provider.

Do not rely solely on `KeyStore.getInstance("PKCS12")` succeeding to conclude that all features of a file will be compatible.

## 15. Common errors and troubleshooting

| Symptom | Common cause | Resolution |
|---|---|---|
| `Keystore was tampered with, or password was incorrect` | Wrong password, corrupted file, or failed integrity check | Verify the password, backup copy, and correct store type |
| `Unrecognized keystore format` | Wrong `-storetype` selected or file is not a valid keystore | Identify the actual format and specify the right type |
| `Alias does not exist` | Wrong alias or entry not yet imported | Use `keytool -list` to view exact aliases |
| `Cannot recover key` | Incorrect key password or provider does not support that protection scheme | Check the key password and provider/format behavior |
| Certificate reply does not contain the corresponding public key | Certificate reply does not match the alias's key pair | Generate a CSR from the correct alias and request re-issuance from the CA |
| Import succeeds but application does not trust the certificate | Imported wrong leaf/CA certificate, missing chain, or application uses a different truststore | Inspect the trust chain and actual truststore configuration |
| Missing entries after converting JKS to PKCS12 | Incompatible entry type or provider | Compare aliases/entry types and convert using a supporting provider |
| Legacy application cannot read PKCS12 | Older runtime/provider or configuration only accepts JKS | Upgrade the runtime or maintain a compatible format as required |
| Certificate has expired | Certificate past validity period or incorrect system clock | Check date/time, request/renew the certificate |
| TLS reports hostname mismatch | SAN does not contain the hostname/IP used by the client | Re-issue the certificate with an appropriate SAN |
| `NoSuchAlgorithmException` for type | Provider has not registered the requested type | Check providers and security configuration |
| `System.console()` returns `null` | Program running without an interactive console | Run in a terminal or design an appropriate secret input mechanism |

When investigating errors, check step by step: whether the file exists and is readable, whether the type is correct, whether the password is correct, whether the alias exists, whether the provider supports the entry type, and whether the certificate chain fits the intended purpose.

## 16. Security considerations for keystore operations

- Do not store private keys in repositories or publicly shared directories.
- Restrict file access permissions to the service account that needs them.
- Store passwords in a secrets manager or an approved secret management system.
- Verify CA fingerprints through an independent channel before importing.
- Monitor expiration dates and plan certificate renewals.
- Revoke and replace keys if private key compromise is suspected.
- Back up keystores according to security policy and control read access to backups.
- Do not reuse the same private key across multiple environments if policy requires isolation.
- Verify the certificate chain and hostname when configuring TLS.
- Test backup restoration procedures to ensure recovery is possible during an incident.

An incorrect truststore can cause the application to trust an unintended CA; a compromised keystore can expose the service's private key identity. Treat both as critical security assets.

## 17. Workflow for choosing and converting keystore formats

1. Identify the types of data to store: private keys, certificates, trusted certificates, or secret keys.
2. Identify the JDK/provider and other systems that need to read the file.
3. Prefer PKCS12 for new cases unless other compatibility requirements apply.
4. Keep JKS if legacy applications or target software only support JKS.
5. Use JCEKS when there is a specific requirement for secret keys and provider support.
6. Back up the source file before converting.
7. Convert using `keytool -importkeystore` with explicit source/destination types.
8. Compare aliases, entry types, certificate chains, and fingerprints.
9. Configure the application to use the new file and type.
10. Run TLS/signing/integration tests in a production-equivalent environment.
11. Decommission the old file only after confirming the migration is complete and backups meet policy.

If interoperating with non-Java systems, verify the formats and protection algorithms supported by those systems. Even a standard PKCS12 file can encounter implementation differences in ciphers, MACs, or password encoding.

## 18. Checklist

- [ ] Identified the actual format rather than relying solely on the file extension.
- [ ] Explicitly specified `-storetype` in scripts.
- [ ] Distinguished keystore from truststore by usage role.
- [ ] Checked aliases and entry types.
- [ ] Verified subject, issuer, SAN, validity period, and fingerprint.
- [ ] Chosen a format compatible with the JDK/provider and integrated systems.
- [ ] Verified secret key support if required by the application.
- [ ] Kept passwords and private keys out of source control and logs.
- [ ] Verified CA fingerprint before importing a certificate.
- [ ] Backed up and compared entries after conversion.
- [ ] Tested the application with the new keystore/truststore.
- [ ] Established procedures for renewal, rotation, revocation, and recovery.

## 19. References

- Oracle JDK 21 Tool Reference — The `keytool` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html
- Java Security Standard Algorithm Names — KeyStore Types: https://docs.oracle.com/en/java/javase/21/docs/specs/security/standard-names.html
- Java API — `java.security.KeyStore`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyStore.html
- RFC 7292 — PKCS #12: Personal Information Exchange Syntax v1.1: https://www.rfc-editor.org/rfc/rfc7292

The keystore format determines how Java stores and protects key and certificate entries. For most new applications, PKCS12 is a sound default choice; JKS and JCEKS still have their place when compatibility or specific entry support is required. Always verify the format, provider, aliases, certificate chain, and actual readability before deploying or converting.
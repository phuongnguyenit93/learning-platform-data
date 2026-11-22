# Keystore in Java and How to Manage It with keytool

## 1. What is a Keystore?

A **keystore** is a secure repository managed by the Java Security API. It contains entries related to keys and digital certificates, accessed through the **java.security.KeyStore** class and the **keytool** command-line tool.

A keystore is commonly used to:

- Store private keys along with the certificate chain of an application or server.
- Store trusted certificates to verify external identities.
- Store symmetric secret keys for certain applications.
- Provide key material for TLS/SSL, digital signatures, and other security mechanisms.

A keystore file typically has a .p12, .pfx, or .jks extension, but the file extension does not determine the actual format. The keystore type is determined by the **store type** and the security provider.

A keystore does not perform TLS, encrypt data, or verify certificates by itself. It provides storage for keys and certificates; the application or security library uses those entries to perform the corresponding operations.

## 2. Entry Types in a Keystore

A keystore can contain multiple entries. Each entry is identified by an **alias**.

| Entry type | Contents | Common purpose |
|---|---|---|
| PrivateKeyEntry | Private key and its corresponding certificate chain. | Server/client identity, digital signing. |
| TrustedCertEntry | A trusted certificate, without a private key. | Trust anchor or certificate trusted by the application. |
| SecretKeyEntry | A symmetric secret key such as AES. | Symmetric data encryption/decryption. |

A PrivateKeyEntry typically contains the private key that needs to be protected, the certificate for the corresponding public key, and any intermediate certificates in the chain if present.

Private keys are not exported when using standard certificate export commands. **keytool -exportcert** only exports the certificate containing the public key and identity information; it does not export the private key.

A TrustedCertEntry contains only a certificate that an administrator or application has decided to trust. When importing a CA root certificate into a truststore, keytool typically creates an entry of this type.

An alias helps select an entry when using keytool or the Java API. You should choose names that describe the role and environment, such as server-prod, company-root-ca, or app-signing-key.

## 3. Distinguishing Between Keystore and Truststore

In Java TLS, these two terms describe two different roles:

| Component | What does it contain? | What is it used for? |
|---|---|---|
| Keystore | The application's own private key and certificate chain. | Proving identity when the application acts as a server or a mutual TLS client. |
| Truststore | Certificates that the application accepts as trust anchors. | Verifying the peer's certificate chain. |

For example, when running an HTTPS server:

- The server keystore contains the server's private key and certificate.
- The client truststore contains the CA root or certificate used to verify the server.

For an HTTPS client:

- The client usually needs a truststore to verify the server's certificate.
- If the server requires mutual TLS, the client also needs a keystore containing the client's private key and certificate.

Keystore and truststore are not two separate file formats. Both can use PKCS12 or JKS. The role depends on how the application loads and uses the contents.

It is possible to store both identity and trusted certificates in the same file, but separating them into two files usually makes access control, lifecycle management, and policy enforcement easier.

## 4. Common Keystore Formats

| Store type | Characteristics | When to use |
|---|---|---|
| PKCS12 | Standard format, widely supported across platforms and tools. | Suitable default choice for modern Java projects. |
| JKS | Traditional Java keystore format, proprietary to the Java ecosystem. | Maintaining compatibility with legacy systems. |
| JCEKS | Legacy Java format supporting secret key entries. | Only when compatibility with legacy systems/providers is required. |
| PKCS11 | Accesses keys via a PKCS#11 provider, typically backed by an HSM or smart card. | When private keys must be kept inside a hardware security device. |

Since JDK 9, **PKCS12 is the default keystore type** in the default Java configuration. You can check this using the Java API:

~~~java
System.out.println(java.security.KeyStore.getDefaultType());
~~~

With JDK 24.0.2, the output is:

~~~text
pkcs12
~~~

Even though there is a default, you should explicitly specify **-storetype PKCS12** in keytool commands and **KeyStore.getInstance("PKCS12")** in your application. This ensures the build and runtime do not depend on the environment's default configuration.

Do not rename a file extension from .jks to .p12 to convert its format. To perform a real conversion, you must import/export entries using keytool or an appropriate tool.

## 5. Inspecting a Keystore with keytool

keytool is the key and certificate management utility bundled with the JDK.

View the version and list of commands:

~~~bash
keytool -version
keytool -help
~~~

List entries in a keystore:

~~~bash
keytool -list -keystore server.p12 -storetype PKCS12
~~~

keytool will prompt for the store password if needed. To view details of each entry:

~~~bash
keytool -list -v -keystore server.p12 -storetype PKCS12
~~~

Verbose output can show the alias and entry creation date, entry type, certificate chain length, Subject/Issuer, serial number, validity period, signature algorithm, public key algorithm, certificate fingerprint, and X.509 extensions such as Subject Alternative Name (SAN).

Inspect a specific alias:

~~~bash
keytool -list -v -alias server -keystore server.p12 -storetype PKCS12
~~~

Do not just check that the file exists. Verify that the alias, entry type, certificate chain, validity period, and fingerprint match the intended use.

## 6. Creating a New Keystore with a Key Pair and Self-Signed Certificate

To generate a private/public key pair and a self-signed certificate, use **-genkeypair**.

Example for a development environment:

~~~bash
keytool -genkeypair \
    -alias server \
    -keyalg RSA \
    -keysize 2048 \
    -dname "CN=localhost, OU=Development, O=Example, C=VN" \
    -validity 365 \
    -ext "SAN=dns:localhost,ip:127.0.0.1" \
    -keystore server.p12 \
    -storetype PKCS12
~~~

keytool will prompt you to enter and confirm a password. This command creates the file server.p12 with the alias server, an RSA private key, and a self-signed certificate valid for 365 days.

Meaning of the options:

- **-genkeypair:** generates a public/private key pair and a certificate.
- **-alias:** name of the entry in the keystore.
- **-keyalg:** key generation algorithm, such as RSA or EC.
- **-keysize:** key size, applicable to algorithms that support this option.
- **-dname:** Distinguished Name of the certificate subject.
- **-validity:** certificate validity period in days.
- **-ext SAN=...:** adds Subject Alternative Names for DNS/IP.
- **-keystore:** path to the keystore file.
- **-storetype:** keystore format.

You can use EC with a group that matches your security policy:

~~~bash
keytool -genkeypair \
    -alias server-ec \
    -keyalg EC \
    -groupname secp256r1 \
    -dname "CN=localhost, O=Example, C=VN" \
    -validity 365 \
    -ext "SAN=dns:localhost" \
    -keystore server-ec.p12 \
    -storetype PKCS12
~~~

A self-signed certificate is suitable for testing or controlled environments. It is not automatically trusted by browsers, operating systems, or other clients. For production services, you typically need a certificate issued by a CA that complies with your organization's policy.

## 7. Why is Subject Alternative Name Important?

A TLS certificate needs to identify the hostname or IP address it represents. The **Subject Alternative Name (SAN)** field stores the DNS names or IP addresses protected by the certificate.

Example:

~~~bash
-ext "SAN=dns:api.example.com,dns:www.example.com,ip:192.0.2.10"
~~~

You can add SANs when generating a key pair or when creating a certificate request.

Do not rely solely on the Common Name (CN) for hostname verification. Modern TLS clients rely on SAN for server identity verification. If an application connects by IP address, the certificate must have a matching IP SAN; a DNS SAN does not substitute for an IP SAN.

Check SANs in a certificate:

~~~bash
keytool -list -v -alias server -keystore server.p12 -storetype PKCS12
~~~

In the output, look for the SubjectAlternativeName section. Make sure every hostname that the application actually uses is present in the certificate.

## 8. Creating a Certificate Signing Request (CSR)

In production environments, you typically generate a key pair first and then send a **Certificate Signing Request (CSR)** to a CA to request a certificate.

Generate a CSR from an existing alias:

~~~bash
keytool -certreq \
    -alias server \
    -keystore server.p12 \
    -storetype PKCS12 \
    -file server.csr \
    -ext "SAN=dns:api.example.com,dns:www.example.com"
~~~

The CSR contains the subject information, the public key, and a signature created with the corresponding private key. The private key remains in the keystore and is not sent to the CA.

View the CSR contents:

~~~bash
keytool -printcertreq -file server.csr
~~~

After the CA validates the request, it returns the server certificate and may include an intermediate certificate chain.

Import the certificate reply into the same alias that generated the CSR:

~~~bash
keytool -importcert \
    -alias server \
    -file server-chain.pem \
    -keystore server.p12 \
    -storetype PKCS12
~~~

When the alias is already a PrivateKeyEntry, keytool processes the certificate reply file and attaches the chain to the corresponding private key. If the alias does not already have a private key, importing a certificate typically creates a TrustedCertEntry instead of an identity with a private key.

The certificate reply must match the public key in the CSR, and the chain must be validly constructed. If you import into the wrong alias or import the wrong certificate, keytool may reject it or fail to build the expected chain.

## 9. Importing a CA Certificate into a Truststore

To make an application trust certificates issued by a CA, you typically add the CA root or an organization-approved trust anchor to the truststore.

Before importing, inspect the certificate:

~~~bash
keytool -printcert -file company-root.pem
~~~

Verify the SHA-256 fingerprint through another trusted channel, such as official PKI documentation or the CA administrator. Never trust a certificate just because the file was sent as an email attachment or downloaded from an unverified URL.

Import into the application's dedicated truststore:

~~~bash
keytool -importcert \
    -alias company-root-ca \
    -file company-root.pem \
    -keystore app-truststore.p12 \
    -storetype PKCS12
~~~

keytool displays the certificate details and asks whether to trust it. Confirm only after verifying the fingerprint and issuing source.

Check the truststore after importing:

~~~bash
keytool -list -v \
    -keystore app-truststore.p12 \
    -storetype PKCS12
~~~

The newly imported entry typically has the type TrustedCertEntry. For production truststores, explicitly track which CAs are trusted, their intended purpose, and their expiration dates.

Avoid using **-noprompt** when importing unverified certificates. This option skips the interactive confirmation step and is only appropriate when the pipeline has already verified the fingerprint through a reliable mechanism.

## 10. Exporting and Inspecting a Certificate

To export a certificate from an alias:

~~~bash
keytool -exportcert \
    -alias server \
    -keystore server.p12 \
    -storetype PKCS12 \
    -file server.der
~~~

By default, the output is in binary DER format. Add **-rfc** to export in PEM/Base64 format:

~~~bash
keytool -exportcert \
    -rfc \
    -alias server \
    -keystore server.p12 \
    -storetype PKCS12 \
    -file server.pem
~~~

Print the exported certificate details:

~~~bash
keytool -printcert -file server.pem
~~~

You can use -list -v to view the fingerprint directly from the keystore and compare it with the exported certificate file.

Exporting a certificate does not expose the private key. If you need to move an identity to another keystore, use a password-protected importkeystore workflow and verify the result rather than just copying the public certificate.

## 11. Creating a SecretKeyEntry with keytool

In addition to asymmetric key pairs, a keystore can also hold symmetric secret keys.

Example of generating an AES key:

~~~bash
keytool -genseckey \
    -alias app-aes \
    -keyalg AES \
    -keysize 256 \
    -keystore secrets.p12 \
    -storetype PKCS12
~~~

List the entries:

~~~bash
keytool -list -v -keystore secrets.p12 -storetype PKCS12
~~~

The output will show an entry type of SecretKeyEntry. Supported algorithms and key sizes depend on the security provider, cryptographic policy, and JDK in use.

In your application, retrieve the secret key via the KeyStore API and use it with an appropriate JCA Cipher. Do not log the key, hardcode it in source code, or send it over insecure channels.

Do not reuse the same key for multiple different cryptographic purposes. Your key management design should specify the algorithm, mode, IV/nonce, rotation schedule, and how encrypted data is stored.

## 12. Converting a JKS Keystore to PKCS12

If a project still uses JKS, you can migrate entries using **-importkeystore**.

Example:

~~~bash
keytool -importkeystore \
    -srckeystore legacy.jks \
    -srcstoretype JKS \
    -destkeystore migrated.p12 \
    -deststoretype PKCS12
~~~

keytool prompts for the source and destination keystore passwords. You can import all entries or select a specific alias using -srcalias and -destalias.

After converting, inspect both files:

~~~bash
keytool -list -v -keystore legacy.jks -storetype JKS
keytool -list -v -keystore migrated.p12 -storetype PKCS12
~~~

Compare the number of aliases, entry types, certificate fingerprints and chain lengths, ability to retrieve the private key, and whether the application can load the new file with the new store type.

Do not delete the old keystore immediately after conversion. Keep a secure backup until the application and deployment pipeline have confirmed that the PKCS12 file works properly.

## 13. Managing Aliases, Entries, and Passwords

Some common maintenance commands:

Delete an entry:

~~~bash
keytool -delete -alias old-entry -keystore app.p12 -storetype PKCS12
~~~

Rename an alias:

~~~bash
keytool -changealias \
    -alias old-name \
    -destalias new-name \
    -keystore app.p12 \
    -storetype PKCS12
~~~

Change the store password:

~~~bash
keytool -storepasswd -keystore app.p12 -storetype PKCS12
~~~

Change the password protecting a private key entry:

~~~bash
keytool -keypasswd \
    -alias server \
    -keystore app.p12 \
    -storetype PKCS12
~~~

Commands that do not supply a password on the command line will prompt interactively. Per-entry password behavior depends on the store type and provider; PKCS12 commonly uses the same password for both the store and the private key entry in typical Java configurations. Test compatibility before automating password changes or format conversions.

Do not put real passwords directly in committed scripts, command history, or CI logs. When automation requires a password, retrieve it from a secret manager or the build platform's secure provisioning mechanism, restrict read permissions, and do not print the value to logs.

## 14. Reading a Keystore with the Java KeyStore API

A Java application can load a keystore using the **java.security.KeyStore** class.

Complete example **InspectStore.java**:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;

public class InspectStore {
    public static void main(String[] args) throws Exception {
        char[] password =
                System.getenv("STORE_PASSWORD").toCharArray();

        KeyStore store = KeyStore.getInstance("PKCS12");

        try (InputStream input =
                     Files.newInputStream(Path.of(args[0]))) {
            store.load(input, password);
        }

        String alias = "server";

        System.out.println("type=" + store.getType());
        System.out.println("contains server=" +
                store.containsAlias(alias));
        System.out.println("private key entry=" +
                store.isKeyEntry(alias));
        System.out.println("certificate entry=" +
                store.isCertificateEntry(alias));
        System.out.println("certificate present=" +
                (store.getCertificate(alias) != null));
    }
}
~~~

Compile:

~~~bash
javac --release 17 -encoding UTF-8 InspectStore.java
~~~

The program takes the keystore path as the first argument and the password from the STORE_PASSWORD environment variable. Provide this variable from a secret manager or a secure runtime environment; do not write real passwords into source code or shell history.

For a test keystore where the alias server is a PrivateKeyEntry, the program's stdout is:

~~~text
type=PKCS12
contains server=true
private key entry=true
certificate entry=false
certificate present=true
~~~

The program uses the KeyStore API instead of parsing the file structure manually. Do not parse the raw bytes of a JKS/PKCS12 file directly to extract private keys; use the API and the appropriate security provider.

## 15. Using Keystore and Truststore to Configure TLS

In the Java Secure Socket Extension (JSSE), two commonly used factories are:

- **KeyManagerFactory:** creates KeyManagers from a keystore containing identity/private keys.
- **TrustManagerFactory:** creates TrustManagers from a truststore containing trusted certificates.

Example of initializing an SSLContext:

~~~java
KeyStore identityStore = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(Path.of("server.p12"))) {
    identityStore.load(in, identityPassword);
}

KeyStore trustStore = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(Path.of("truststore.p12"))) {
    trustStore.load(in, trustPassword);
}

KeyManagerFactory kmf = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
kmf.init(identityStore, identityPassword);

TrustManagerFactory tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(trustStore);

SSLContext sslContext = SSLContext.getInstance("TLS");
sslContext.init(
        kmf.getKeyManagers(),
        tmf.getTrustManagers(),
        new java.security.SecureRandom());
~~~

This is the TLS configuration snippet that can be integrated into an application that already has password handling and proper resource management. For a TLS server, KeyManager provides the server's certificate/private key. For a TLS client, TrustManager verifies the server's certificate chain. Mutual TLS may require both sides to provide an identity and verify the peer.

If you only need a client truststore:

~~~java
TrustManagerFactory tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(trustStore);

SSLContext context = SSLContext.getInstance("TLS");
context.init(null, tmf.getTrustManagers(), null);
~~~

Do not disable hostname verification to work around certificate errors. If the hostname does not match, issue a certificate with the correct SAN or fix the endpoint that the client connects to.

## 16. The Default cacerts Keystore

The JDK typically ships with a default truststore named **cacerts**, which contains the CA certificates trusted by the runtime according to the distribution's configuration.

List certificates in cacerts:

~~~bash
keytool -list -cacerts
~~~

You can view detailed output:

~~~bash
keytool -list -v -cacerts
~~~

cacerts resides inside the Java runtime's security directory tree. The exact path depends on the JDK/JRE installation and platform.

Do not modify the shared JDK's cacerts directly just so a single application can trust a custom CA. Runtime updates can overwrite this file and alter the trust policy for many applications.

For an application that requires a private CA, it is standard practice to create a dedicated truststore and configure the application to use that file. This allows updating trust anchors without affecting other applications.

## 17. Passwords, Backups, and Protecting Private Keys

A keystore is only secure when its file, password, and access permissions are properly managed.

Some key principles:

- Restrict read permissions on the keystore file to the appropriate service account.
- Protect private keys with strong passwords and a secret manager.
- Do not commit production keystores or passwords to Git.
- Do not include passwords in logs, exception messages, or telemetry.
- Do not send keystores over email/chat or store them in unencrypted repositories.
- Encrypt backups and control access to them.
- Test that backups can be restored before you need them.
- Plan for key rotation and certificate renewal.
- Revoke certificates if the private key is compromised or no longer authorized for use.

Losing a private key can prevent the application from continuing to use its current certificate, requiring a new key pair and certificate to be generated. Backups must be protected at the same level as the original file; do not leave copies in temporary directories or on unmanaged personal machines.

A keystore password does not replace operating system file permissions. Anyone who can read the file and knows the password can use the private key as permitted by the application.

For systems with high security requirements, consider using an HSM or PKCS#11 token so that private keys do not have to be exported to regular files. Hardware key management requires dedicated provisioning, backup/recovery, and access control procedures.

## 18. Common Errors When Using Keystores

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Keystore was tampered with, or password was incorrect | Wrong store password, corrupted file, or wrong store type/provider. | Verify the password, backup, and store type. |
| Alias does not exist | Wrong alias selected or wrong file imported. | Use keytool -list -v to inspect aliases. |
| TrustedCertEntry created instead of PrivateKeyEntry | Imported a certificate into a new alias that has no private key. | Generate the key pair/CSR first, then import the certificate reply into that same alias. |
| Certificate reply does not contain public key for alias | Certificate does not match the private key that generated the CSR, or wrong alias. | Check the CSR, alias, and the certificate returned by the CA. |
| Certificate chain could not be built | Missing intermediate CA or invalid chain. | Obtain the complete certificate chain and import it into the correct alias. |
| Hostname verification failed | SAN does not include the hostname/IP the client is connecting to. | Issue a certificate with the correct SAN. |
| PKIX path building failed | Truststore is missing the appropriate CA or the chain is not trusted. | Check the chain, trust anchor, and truststore the application is actually using. |
| Keystore type not supported | Runtime/provider does not support the chosen store type. | Choose a compatible PKCS12/JKS type or install the proper provider. |
| Private key password incorrect | Wrong entry password used or format does not support the expected password configuration. | Verify the store type and entry password. |
| Application does not see the new certificate | Application is holding a previously loaded SSLContext/KeyStore. | Reload key material according to the application lifecycle or perform a controlled restart. |
| Untrusted CA imported by mistake | Fingerprint was not verified before importing. | Remove the wrong entry and verify the certificate through an independent channel. |

Do not resolve TLS errors by disabling certificate or hostname verification. First, identify the exact keystore/truststore file, alias, chain, SAN, and trust manager that the application is actually using.

## 19. Keystore Management Workflow in a Project

An operational workflow can include:

1. Determine the file's role: identity keystore, truststore, or secret-key store.
2. Choose PKCS12 unless there is a specific compatibility requirement for another format.
3. Generate the key pair and assign a clear alias.
4. Add SANs matching the service's hostnames/IPs.
5. For production, generate a CSR and send it to the CA; keep the private key in the keystore.
6. Receive the certificate reply and import it into the exact same alias.
7. Import verified CA roots into a dedicated truststore when needed.
8. Inspect entries, fingerprints, chains, validity periods, and algorithms with keytool -list -v.
9. Load the file with the KeyStore API and configure KeyManagerFactory/TrustManagerFactory.
10. Protect passwords, file permissions, backups, and rotation procedures.
11. Test TLS in the target environment and verify hostname verification.
12. Monitor certificate expiration dates and CA trust update schedules.

Record non-secret metadata such as alias, subject, issuer, fingerprint, expiration date, store type, and owner. Never record private keys or passwords in operational documentation.

## 20. Pre-Deployment Checklist

- [ ] Determined whether the keystore stores an identity, trust anchor, or secret key.
- [ ] Selected the appropriate store type, preferring PKCS12 when no legacy constraints exist.
- [ ] Used aliases that clearly describe the role and environment.
- [ ] Verified entry types and certificate chains.
- [ ] Verified that SANs match actual DNS names/IPs.
- [ ] Verified certificate fingerprints through a trusted channel.
- [ ] Imported the certificate reply into the correct private-key alias.
- [ ] Verified that the truststore contains the required CAs.
- [ ] Tested the Java KeyStore API and TLS context.
- [ ] Protected passwords, files, backups, and access permissions.
- [ ] Established renewal, rotation, and certificate revocation procedures.
- [ ] Confirmed that certificate and hostname verification are not disabled.

A keystore provides a centralized place to manage private keys, secret keys, and certificates for Java applications. By choosing the right store type, managing aliases and certificate chains clearly, separating identity from trust where appropriate, and protecting passwords and private keys, applications can use TLS and Java security mechanisms safely and maintainably.
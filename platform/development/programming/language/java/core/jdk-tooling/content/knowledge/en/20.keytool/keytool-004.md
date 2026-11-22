# Generating a Key Pair with keytool

A **key pair** consists of a mathematically related **private key** and **public key**. Java uses key pairs in public-key cryptographic mechanisms such as digital signing, signature verification, and certain data exchange or protection protocols.

The JDK provides the **`keytool`** utility to generate and manage key pairs, certificates, and keystores. The most commonly used command to generate a key pair is **`keytool -genkeypair`**. This command creates a private key, a public key, and a self-signed X.509 certificate, then stores the private key together with the certificate in a keystore.

## 1. How does a key pair work?

A key pair has two components:

- **Private key:** must be kept secret. The owner uses this key to sign data or perform cryptographic operations that require the private key.
- **Public key:** can be shared. The recipient uses the public key to verify signatures or perform operations appropriate for the algorithm.

With digital signatures:

1. The sender generates a signature from the data using the private key.
2. The recipient uses the corresponding public key to verify the signature.
3. If verification succeeds, the signature indicates that the data matches the private key used to sign it and has not been altered since signing, assuming the algorithm and keys are secure.

Public keys are typically distributed via X.509 certificates. A certificate binds a public key to subject information and is signed by a CA or self-signed in testing environments.

**Do not share the private key.** Sending a certificate containing the public key to others is normal; sending a keystore containing a private key or the keystore password can expose the signing identity and allow others to impersonate the key owner.

## 2. Keystore and truststore

`keytool` stores keys and certificates in a **keystore**. A keystore is a file containing entries, each identified by an alias.

Two important entry types:

| Entry type | Contents | Purpose |
| --- | --- | --- |
| `PrivateKeyEntry` | Private key along with its certificate and possibly a certificate chain | Stores the application's key for signing or authentication |
| `trustedCertEntry` | A trusted certificate without a corresponding private key | Stores a CA certificate or a trusted certificate |

A **keystore** typically holds the private key of the application or server itself. A **truststore** typically holds the certificates of CAs or partners that the application trusts. Technically, both can use the same file format; the naming reflects their intended purpose.

### Keystore formats

- **PKCS12:** the standard format, interoperable with many tools and platforms. This is the right choice for new keystores.
- **JKS:** Java's legacy keystore format, which may still be encountered in older systems.

In this guide, commands explicitly specify `-storetype PKCS12` to avoid depending on environment defaults.

## 3. Checking keytool

`keytool` is included with the JDK. Check your environment:

```bash
java -version
keytool -help
keytool -genkeypair -help
```

If the terminal does not recognize `keytool`:

- Verify that a full JDK is installed on the machine.
- Verify that the JDK's `bin` directory is in `PATH`.
- Verify that `JAVA_HOME` points to the JDK root directory.
- Open a new terminal after changing environment variables.

The help output for `keytool -genkeypair` lists options such as `-alias`, `-keyalg`, `-keysize`, `-groupname`, `-sigalg`, `-dname`, `-validity`, `-ext`, `-keystore`, and `-storetype`. Specific options may vary by JDK; check the help output on the exact version being deployed.

## 4. Generating an RSA key pair and storing it in PKCS12

Example of generating an RSA key pair for a development environment. The command creates the keystore `app-signing.p12` and an entry with the alias `app-signing`:

```bash
keytool -genkeypair -alias app-signing -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -validity 365 -storetype PKCS12 -keystore app-signing.p12 -dname "CN=Example Development Key, OU=Engineering, O=Example Org, L=Ho Chi Minh City, ST=Ho Chi Minh City, C=VN"
```

Explanation:

- `-genkeypair`: generates the key pair and certificate.
- `-alias app-signing`: the entry name in the keystore.
- `-keyalg RSA`: selects the RSA algorithm.
- `-keysize 3072`: selects a 3072-bit key size.
- `-sigalg SHA256withRSA`: uses the SHA-256 with RSA signature algorithm for the self-signed certificate.
- `-validity 365`: the certificate is valid for 365 days.
- `-storetype PKCS12`: uses the PKCS12 format.
- `-keystore app-signing.p12`: the output keystore file name.
- `-dname`: the Distinguished Name information of the subject in the certificate.

If you do not pass a password on the command line, `keytool` prompts for the keystore password in the terminal. Enter a strong password and confirm it when prompted. With PKCS12, the password protecting the private key usually must match the keystore password; when the tool asks for a separate key password, press Enter to use the same password if prompted.

Do not put real passwords in shell commands, committed scripts, or CI logs. Interactive entry helps avoid saving passwords directly in command history.

This command creates a self-signed certificate. This is convenient for development, testing, and workflow verification; self-signed certificates are not automatically trusted by operating systems, browsers, or clients.

## 5. Inspecting the newly created keystore and key pair

Use `-list` to view entries:

```bash
keytool -list -keystore app-signing.p12 -storetype PKCS12
```

To view details:

```bash
keytool -list -v -alias app-signing -keystore app-signing.p12 -storetype PKCS12
```

After entering the password, verify the following details:

- The alias is `app-signing`.
- The entry type is `PrivateKeyEntry`.
- The certificate chain length is typically 1 for a newly created self-signed certificate.
- The Owner/Subject contains the declared Distinguished Name.
- The Issuer matches the subject for a self-signed certificate.
- The public key algorithm and key size match your selection.
- The signature algorithm and validity period are appropriate.

For example, the output might show:

```text
Alias name: app-signing
Entry type: PrivateKeyEntry
Certificate chain length: 1
Owner: CN=Example Development Key, ...
Issuer: CN=Example Development Key, ...
Subject Public Key Algorithm: 3072-bit RSA key
Signature algorithm name: SHA256withRSA
```

These are illustrative fields; exact formatting and values depend on the JDK, certificate, and creation time.

## 6. Exporting the public certificate

Public keys are commonly shared as X.509 certificates. Use `-exportcert` to export the certificate for an alias:

```bash
keytool -exportcert -rfc -alias app-signing -keystore app-signing.p12 -storetype PKCS12 -file app-signing.crt
```

- `-exportcert`: exports the certificate associated with the alias.
- `-rfc`: exports in PEM format, with `BEGIN CERTIFICATE` and `END CERTIFICATE` lines.
- `-file app-signing.crt`: the output certificate file.

Read the exported certificate:

```bash
keytool -printcert -file app-signing.crt -v
```

You can share the certificate publicly with parties that need to verify signatures or check identity. The certificate file contains the public key and X.509 metadata; it **does not contain the private key**.

`keytool -exportcert` does not export the private key. Keep the `.p12` file and its password in a securely protected location.

## 7. Generating a key pair using EC

In addition to RSA, `keytool` supports elliptic-curve cryptography (EC). Example of generating an EC key on the `secp256r1` group:

```bash
keytool -genkeypair -alias app-ec -keyalg EC -groupname secp256r1 -sigalg SHA256withECDSA -validity 365 -storetype PKCS12 -keystore app-ec.p12 -dname "CN=Example EC Key, OU=Engineering, O=Example Org, L=Ho Chi Minh City, ST=Ho Chi Minh City, C=VN"
```

Explanation:

- `-keyalg EC`: generates an elliptic curve key pair.
- `-groupname secp256r1`: selects the curve group.
- `-sigalg SHA256withECDSA`: uses ECDSA with SHA-256 to sign the self-signed certificate.
- The alias, validity, keystore, and subject options have the same meaning as in the RSA example.

EC can provide security equivalent to larger RSA key sizes, but compatibility depends on systems and protocols. Choose the algorithm, curve, and size according to your organization's security policy, target platform, and partner requirements.

Do not choose an algorithm solely because the key generation command succeeds; verify that consuming systems support that algorithm and certificate format.

## 8. Adding a Subject Alternative Name (SAN) to a certificate

If a certificate is used for TLS, hostnames should be listed in the **Subject Alternative Name (SAN)**. Specifying only the Common Name (CN) is generally insufficient for modern hostname verification.

Example of generating a development certificate for `localhost`:

```bash
keytool -genkeypair -alias localhost-tls -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -validity 365 -storetype PKCS12 -keystore localhost-tls.p12 -dname "CN=localhost, OU=Development, O=Example Org, L=Ho Chi Minh City, ST=Ho Chi Minh City, C=VN" -ext "SAN=dns:localhost,ip:127.0.0.1"
```

The `-ext` option adds an X.509 extension. In the example:

- `dns:localhost` declares the DNS name.
- `ip:127.0.0.1` declares the loopback IP address.

Verify the SAN:

```bash
keytool -list -v -alias localhost-tls -keystore localhost-tls.p12 -storetype PKCS12
```

Look for the `SubjectAlternativeName` section under certificate extensions.

A self-signed certificate for localhost is suitable for development or controlled testing. It is not automatically trusted by clients in production. Production environments require a certificate issued by an appropriate CA, SAN hostnames matching the service, and a properly configured trust chain.

## 9. Creating a Certificate Signing Request (CSR)

When you need a CA-signed certificate, do not send the private key to the CA. Instead, generate a **Certificate Signing Request (CSR)** from the entry containing the key pair.

Generate a CSR:

```bash
keytool -certreq -alias app-signing -keystore app-signing.p12 -storetype PKCS12 -file app-signing.csr -sigalg SHA256withRSA
```

The CSR contains the public key and subject information for the CA to validate; it is signed with the corresponding private key to prove that the requester possesses the private key.

General workflow:

1. Generate a key pair in the keystore.
2. Generate a CSR using `keytool -certreq`.
3. Submit the CSR to the CA following the enrollment process.
4. The CA verifies the request and issues the certificate along with the required chain.
5. Inspect the received certificate and chain.
6. Import the certificate reply into the same alias that holds the private key.
7. Re-verify the entry and certificate chain using `keytool -list -v`.

When the CA returns the certificate, import the certificate reply into the key pair's alias:

```bash
keytool -importcert -alias app-signing -file app-signing-reply.pem -keystore app-signing.p12 -storetype PKCS12
```

The reply file should contain the certificate issued for the public key in the CSR and the required chain per the CA's instructions. The root/intermediate CA must be trusted and resolved properly so `keytool` can verify the chain. Do not import an untrusted certificate of unknown origin just because the command displays a confirmation prompt.

**Do not generate a new key pair after submitting a CSR** if you intend to use the certificate reply with the current key. If you replace the private key, the old CSR no longer matches the new key.

## 10. Creating a truststore and importing trusted certificates

A truststore typically stores certificates of CAs or partners that the application trusts. Example of importing a root CA certificate into a separate truststore:

```bash
keytool -importcert -alias example-root-ca -file root-ca.crt -keystore app-truststore.p12 -storetype PKCS12
```

`keytool` prompts for confirmation of the certificate. Before answering yes:

1. Obtain the certificate fingerprint from an independent, trusted source, such as the CA's official distribution channel.
2. Compare the fingerprint with the output displayed by `keytool`.
3. Confirm it is the right certificate and the right organization.
4. Only then confirm the import.

List the truststore:

```bash
keytool -list -v -keystore app-truststore.p12 -storetype PKCS12
```

A trusted certificate entry typically has the type `trustedCertEntry`. It contains a trusted certificate, not the application's private key.

Do not import a certificate into a truststore simply because it was attached to an email or downloaded from an unverified address. Adding a certificate to a truststore can cause the application to trust that identity or CA.

## 11. Using a key pair to sign a JAR

A common use case for a key pair is digitally signing a JAR. The `jarsigner` tool uses the private key in a keystore to sign the archive contents.

Example:

```bash
jarsigner -keystore app-signing.p12 -storetype PKCS12 -signedjar app-signed.jar app.jar app-signing
```

Meaning:

- `-keystore app-signing.p12`: keystore containing the private key.
- `-storetype PKCS12`: keystore format.
- `-signedjar app-signed.jar`: name of the signed output JAR.
- `app.jar`: source JAR.
- `app-signing`: alias of the entry containing the private key.

`keytool`/`jarsigner` will prompt for the password when needed. Do not pass real passwords directly in scripts or commands recorded in shell history.

Verify the signature:

```bash
jarsigner -verify -verbose -certs app-signed.jar
```

The signature lets you check whether the JAR contents were modified after signing and which certificate was used. However, a JAR signed with a self-signed certificate may still not be trusted by recipients. Verifying integrity and verifying trusted identity are two different things.

## 12. Aliases, passwords, and protecting the private key

An **alias** is the name used to look up an entry in a keystore. A keystore can hold multiple aliases, for example:

- `app-signing`: JAR signing key.
- `localhost-tls`: key used for TLS development environments.
- `service-client`: client authentication key.
- `example-root-ca`: trusted CA certificate in a truststore.

Common management commands:

| Command | Purpose |
| --- | --- |
| `keytool -list` | List entries in a keystore |
| `keytool -list -v -alias <alias>` | View details of an entry |
| `keytool -exportcert` | Export a public certificate |
| `keytool -importcert` | Import a certificate or chain |
| `keytool -certreq` | Generate a CSR from a key pair |
| `keytool -delete -alias <alias>` | Delete an entry |
| `keytool -changealias` | Rename an alias |
| `keytool -storepasswd` | Change the keystore password |
| `keytool -keypasswd` | Change a private key entry's password when supported by the format |

Protection practices:

- Use strong, unique passwords and store them in an appropriate secret manager.
- Restrict read permissions on keystore files at the OS account level.
- Never commit keystores, private keys, or passwords to Git.
- Never send private keys over chat, email, or ticketing systems.
- Back up keystores using encrypted procedures and access controls.
- Rotate or revoke certificates if a private key is compromised.
- Separate development, test, and production keys.
- Do not reuse a single private key for multiple purposes if security policy requires separation.

If a private key is compromised, changing the keystore password alone is not enough. An attacker may have already copied the private key; handle the certificate, revoke it, or replace the key according to appropriate procedures.

## 13. Common errors when generating a key pair

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `keytool` is not recognized | JDK is not installed or `PATH` does not include `bin` | Check `JAVA_HOME` and `PATH` |
| Alias already exists | The keystore already has an entry with that alias | Choose a different alias or inspect the existing entry before modifying |
| Unable to open keystore | Wrong password or wrong keystore format | Verify the password and `-storetype` |
| Error when using a key password different from the store password with PKCS12 | PKCS12 typically requires the private key password to match the keystore password | Use the same password for both store and key |
| Unsupported algorithm or key size | Provider/JDK does not support the option or security policy blocks it | Check `keytool -genkeypair -help` and provider configuration |
| TLS certificate does not match hostname | SAN is missing the required DNS/IP | Generate a certificate with the correct SAN or request a new certificate from the CA |
| Client does not trust certificate | Self-signed certificate or CA chain is not trusted | Use an appropriate CA and configure the truststore properly |
| Importing certificate reply fails | Certificate does not match the public key in the alias or chain is incomplete | Check the CSR, alias, chain, and CA certificates |
| Shared certificate, but recipient asks for private key | Confusing the public certificate with the key pair | Share only the certificate/public key; transfer private keys only via approved secure processes |
| JAR signature is valid, but trust warning still appears | Self-signed certificate or CA is not trusted by the recipient | Distribute the appropriate certificate chain and use a trusted CA |

## 14. Recommended key pair generation workflow

A basic, repeatable workflow:

1. Define the purpose: JAR signing, TLS server, client authentication, or testing.
2. Choose an algorithm and key size compliant with security policy.
3. Choose a clear alias and create a PKCS12 keystore.
4. Use `keytool -genkeypair` to generate the key pair and certificate.
5. Inspect the entry with `keytool -list -v`.
6. If you need to share the public key, export the certificate with `keytool -exportcert -rfc`.
7. If CA signing is needed, generate a CSR with `keytool -certreq` and import the certificate reply into the same alias.
8. If trusting a CA is needed, verify its fingerprint and import the certificate into the truststore.
9. Test the actual intended usage, such as signing a JAR and verifying the signature.
10. Protect the keystore, passwords, and private key according to operational procedures.

Record the algorithm, alias, keystore type, certificate validity period, and the person/process responsible for management. Do not record private keys or passwords in operational documentation.

## 15. Key takeaways

- A key pair consists of a private key and a public key; the private key must be protected.
- `keytool -genkeypair` creates a key pair and a self-signed certificate, storing them in a keystore.
- Use `-alias` to name the entry, `-keyalg` to choose the algorithm, and `-keysize` or `-groupname` to specify key parameters.
- PKCS12 is the recommended keystore format for new systems and interoperability.
- `keytool -list -v` inspects entries, certificates, algorithms, and validity periods.
- `keytool -exportcert -rfc` exports the certificate containing the public key, not the private key.
- `keytool -certreq` generates a CSR for CA certificate issuance.
- A truststore stores trusted certificates; always verify fingerprints before importing.
- Self-signed certificates are suitable for development/testing, but are not automatically trusted in production.
- Never commit or share a keystore containing a private key; if a private key is compromised, replace the key and handle the associated certificate.

Mastering the `keytool -genkeypair` → inspect keystore → export certificate or generate CSR workflow helps you create and manage Java key pairs for their intended purpose while keeping private keys protected throughout their lifecycle.

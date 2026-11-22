# Viewing Certificates with keytool

## 1. Objective

`keytool` is the keystore and certificate management utility included with the JDK. When you need to inspect an X.509 certificate, you can use `keytool -printcert` to read information from a file, a certificate chain sent by a TLS server, or the signer certificate attached to a signed JAR.

Viewing a certificate typically helps answer the following questions:

- Which subject was the certificate issued to, and which CA issued it?
- Is the certificate still valid or has it expired?
- Is the server's DNS name or IP address listed in the Subject Alternative Name (SAN)?
- Which signature algorithm and public key does the certificate use?
- Does the SHA-256 fingerprint match the value provided through a trusted channel?
- Is the certificate a CA certificate or a server/client certificate?
- Which aliases are in the keystore, and what type of entry does each alias contain?
- Which certificates make up the certificate chain?

`keytool` displays certificate data for an administrator to inspect. Simply seeing a certificate does not automatically prove that it is trusted, matches the hostname, or is authorized for a specific purpose. Those verification steps must be performed separately.

## 2. What Does an X.509 Certificate Contain?

An X.509 certificate binds a subject's identity to a public key. A CA or a self-signing subject generates a signature over the certificate contents so that recipients can verify its integrity and issuing source.

Key fields:

| Field | Meaning |
|---|---|
| Version | X.509 structure version; most modern certificates are v3 |
| Subject / Owner | The identity represented by the certificate |
| Issuer | The CA or subject that signed the certificate |
| Serial number | Certificate identifier assigned by the issuer |
| Valid from / until | Start and end timestamps of the validity period |
| Signature algorithm | The algorithm used to sign the certificate |
| Subject public key algorithm | The public key algorithm and key size |
| SHA-256 fingerprint | Hash of the entire certificate, used to uniquely identify it |
| Subject Alternative Name | DNS names, IP addresses, or additional identities |
| Basic Constraints | Indicates whether the certificate is permitted to act as a CA |
| Key Usage | Permitted cryptographic operations |
| Extended Key Usage | Intended purposes such as serverAuth, clientAuth, or codeSigning |

In `keytool` output, the `Owner` field corresponds to the Subject. Do not confuse Subject with Issuer: the Subject is the entity being certified, while the Issuer is the party that signed the certificate.

## 3. How to Read keytool Output

An X.509 v3 certificate is typically displayed by `keytool -printcert -v` in the following format:

```text
Owner: CN=localhost, O=Example, C=VN
Issuer: CN=Example Test Root CA, O=Example, C=VN
Serial number: 825f5ab58daf3e50
Valid from: Tue Nov 10 23:40:12 GMT+07:00 2026 until: Wed Nov 10 23:40:12 GMT+07:00 2027
Certificate fingerprints:
         SHA1: ...
         SHA256: ...
Signature algorithm name: SHA384withRSA
Subject Public Key Algorithm: 2048-bit RSA key
Version: 3

Extensions:
  BasicConstraints:
    CA:false
  ExtendedKeyUsages:
    serverAuth
  KeyUsage:
    DigitalSignature
    Key_Encipherment
  SubjectAlternativeName:
    DNSName: localhost
    IPAddress: 127.0.0.1
```

How to interpret this:

- `Owner` indicates this certificate is for `localhost`.
- `Issuer` indicates the certificate was signed by the CA `Example Test Root CA`.
- `Valid from` specifies the time range during which the certificate is valid.
- `SHA256` is the fingerprint to use when comparing certificates.
- `Signature algorithm name` describes the algorithm used to sign the certificate.
- `Subject Public Key Algorithm` indicates the public key type and size.
- `CA:false` indicates this certificate was not issued as a CA certificate.
- `serverAuth` indicates the TLS server authentication purpose.
- SAN contains both the DNS name and IP address represented by the certificate.

Exact values vary by certificate. Always read the actual output rather than assuming every certificate has the same extensions or algorithms.

## 4. Viewing a Certificate from a PEM or DER File

This is the most direct approach when you receive a certificate from a CA, a management system, or a server operator.

View a certificate from a PEM file:

```bash
keytool -printcert -file server.pem
```

View full extensions and fingerprints:

```bash
keytool -printcert -file server.pem -v
```

You can also request output in RFC/PEM format:

```bash
keytool -printcert -file server.pem -rfc
```

`-file` specifies the input certificate. `-v` displays more details. `-rfc` outputs the certificate representation in Base64 PEM format.

PEM typically has a header and footer wrapper:

```text
-----BEGIN CERTIFICATE-----
MIID...
-----END CERTIFICATE-----
```

DER is a binary format. The same certificate can be stored in either DER or PEM format. `keytool -printcert -file` can read both formats.

## 5. Distinguishing Between PEM and DER

| Format | Characteristics | Common Indicators |
|---|---|---|
| DER | Binary ASN.1 data | .der or .cer files |
| PEM | Base64-encoded DER wrapped with header/footer | -----BEGIN CERTIFICATE----- |
| PKCS#12 | Container that can hold private keys, certificates, and chains | .p12, .pfx |
| JKS | Java KeyStore format | .jks |

Export a certificate in DER format:

```bash
keytool -exportcert -alias server -keystore server.p12 -storetype PKCS12 -file server.der
```

Export in PEM format:

```bash
keytool -exportcert -alias server -keystore server.p12 -storetype PKCS12 -rfc -file server.pem
```

Then view the certificate:

```bash
keytool -printcert -file server.der -v
keytool -printcert -file server.pem -v
```

`-exportcert` exports only the public certificate, not the private key. A `.p12` or `.jks` file may contain private keys, so it must be protected as a secret. Never send a keystore containing a private key just to share a certificate.

## 6. Viewing Certificates in a Keystore

A keystore can contain multiple entries. First, list the aliases:

```bash
keytool -list -keystore server.p12 -storetype PKCS12
```

View full entry details:

```bash
keytool -list -v -keystore server.p12 -storetype PKCS12
```

View only a specific alias:

```bash
keytool -list -v -alias server -keystore server.p12 -storetype PKCS12
```

`keytool` will prompt for the keystore password if required. For a JKS keystore, specify:

```bash
keytool -list -v -keystore server.jks -storetype JKS
```

Common entry types:

| Entry type | Contents |
|---|---|
| PrivateKeyEntry | Private key and its corresponding certificate chain |
| trustedCertEntry | Public certificate stored as a trusted certificate |
| SecretKeyEntry | Symmetric secret key; not a certificate entry |

When the output shows `Certificate chain length: 2`, the entry holds two certificates in the chain—typically the server certificate and the CA that signed it. It does not mean the keystore contains two private keys.

## 7. Viewing a Certificate Chain

A certificate chain describes the path from the end-entity certificate to intermediate CAs and the root CA.

```text
Server certificate
    Issuer: Intermediate CA
        Issuer: Root CA
```

In a `PrivateKeyEntry`, the first certificate is typically the leaf certificate associated with the private key; subsequent certificates are the CA certificates in the chain.

View the chain of an alias:

```bash
keytool -list -v -alias server -keystore server.p12 -storetype PKCS12
```

View certificates sent by a TLS server:

```bash
keytool -printcert -sslserver example.com:443 -v
```

`-printcert -sslserver` connects to the TLS endpoint and displays the certificates presented by the server. If the server sends intermediate certificates, the output may include multiple sections such as `Certificate #0`, `Certificate #1`, etc.

The root CA is normally trusted by the client via its truststore and does not necessarily need to be sent by the server during the TLS handshake. Therefore, the chain observed over the network may not include the root certificate.

If only the leaf certificate is visible, check whether the server configuration is sending the full intermediate certificates. Missing intermediates can prevent some clients from building a chain to a trusted root.

## 8. Viewing the Certificate Used by an HTTPS Server

When you need to inspect the certificate of a website or API:

```bash
keytool -printcert -sslserver api.example.com:443
```

View details:

```bash
keytool -printcert -sslserver api.example.com:443 -v
```

You can substitute the host and port for your actual endpoint:

```bash
keytool -printcert -sslserver localhost:8443 -v
```

If the command fails to connect, check DNS, firewall, port, proxy, and the TLS listener status. For servers that require SNI or host multiple virtual hosts, verify using the exact hostname that the client actually connects to.

This command shows the certificate presented by the server. It does not replace hostname verification in the client application, truststore policies, revocation checks, or application TLS configuration.

## 9. Viewing a JAR Signing Certificate

A signed JAR can contain a signer certificate and certificate chain in the `META-INF` directory.

View the signer certificate:

```bash
keytool -printcert -jarfile app.jar
```

View full details:

```bash
keytool -printcert -jarfile app.jar -v
```

This command reveals which identity signed the JAR, the certificate's validity period, and which certificates make up the chain.

To verify the signature of the JAR contents, use `jarsigner`:

```bash
jarsigner -verify -verbose -certs app.jar
```

If you need to verify the chain against a specific truststore:

```bash
jarsigner -verify -verbose -certs -keystore truststore.p12 -storetype PKCS12 app.jar
```

`keytool -printcert -jarfile` only inspects signer information. `jarsigner -verify` is what actually verifies the signatures on JAR entries. The result also depends on whether the certificate chain is trusted, whether the certificate is valid for code signing, and whether the timestamp is valid.

## 10. Viewing Certificates in cacerts

The JDK includes a default truststore commonly called `cacerts`. It contains the CA certificates trusted by the Java runtime environment according to the JDK distribution.

List aliases:

```bash
keytool -list -cacerts
```

View details of trusted certificates:

```bash
keytool -list -v -cacerts
```

View a specific alias:

```bash
keytool -list -v -cacerts -alias example-root
```

`cacerts` is typically located under the Java runtime's security directory. Using `-cacerts` lets `keytool` access the default truststore without having to guess its path.

Do not add or remove CAs from `cacerts` just to make a single connection work. Modifying the default truststore affects all applications sharing the same runtime. For individual applications, consider using a dedicated truststore.

## 11. Fields to Check When Viewing a Certificate

Not all certificates serve the same purpose. When reading the output, check the following groups.

### Subject, Issuer, and Identity

`Subject` describes the certified identity. `Issuer` indicates which CA signed the certificate. Compare them to determine whether the certificate is a leaf, intermediate, or root certificate.

For TLS hostnames, check `SubjectAlternativeName` (SAN). The DNS name or IP address accessed by the client must match a corresponding SAN entry. Do not rely solely on the Common Name (CN) for hostname verification.

### Validity Period

Check `Valid from` and `Valid until`. A certificate before its `notBefore` time or past its `notAfter` time may be rejected by clients. An incorrect system clock can also make a certificate appear not yet valid or expired.

### Fingerprint

Prefer the SHA-256 fingerprint. Compare the full fingerprint against a value provided by the organization, CA, or administrator through an independent trusted channel. Do not retrieve the fingerprint from the untrusted connection itself and treat it as identity confirmation.

SHA-1 may still appear in output for legacy compatibility or identification, but it should not be used for new verification decisions.

### Public Key and Signature

Check the public key algorithm, key size, and signature algorithm. Watch out for weak algorithms, keys that are too short, or signatures no longer permitted by security policies.

### Extensions

- `BasicConstraints: CA:true` indicates that the certificate can act as a CA according to the extension.
- `KeyUsage` restricts cryptographic operations such as digital signing or key encipherment.
- `ExtendedKeyUsage` restricts purposes such as `serverAuth`, `clientAuth`, or `codeSigning`.
- `SubjectAlternativeName` contains DNS/IP or other identities.
- `SubjectKeyIdentifier` and `AuthorityKeyIdentifier` assist with chain linking.

Do not conclude a certificate is valid based on a single field alone. Evaluate the entire chain, validity period, hostname, intended purpose, and trust policy.

## 12. Fingerprint: How to Compare Certificates

A fingerprint is a hash of the entire certificate, not just the public key. If a certificate is reissued with a different serial number, validity period, or extensions, its fingerprint changes even if the Subject remains the same.

View SHA-256:

```bash
keytool -printcert -file server.pem -v
```

In the output, look for:

```text
Certificate fingerprints:
    SHA256: ...
```

Compare the fingerprint against an independent trusted source, such as:

- Official announcements from PKI administrators.
- The organization's security administration channel.
- Verified deployment documentation.
- Pinning values published through a controlled process.

Do not accept a certificate simply because its Subject matches the expected organization name. Anyone can generate a self-signed certificate with the same Subject.

## 13. Viewing a Certificate vs. Trust Verification

This is a critical distinction:

- `keytool -printcert` reads and displays certificate contents.
- `keytool -list` shows entries and certificates stored in a keystore.
- `keytool -printcert -sslserver` displays certificates presented by a server.
- `jarsigner -verify` verifies JAR signatures.
- Trust validation determines whether the chain terminates at a trusted CA and satisfies policy requirements.

A certificate can:

- Have a valid signature, yet have an untrusted issuer.
- Be within its validity period, yet have a SAN that does not match the hostname.
- Have a chain, yet be missing an intermediate certificate.
- Be a CA certificate, yet be unsuitable for server authentication.
- Have a matching fingerprint, yet have been revoked.
- Be readable by `keytool`, yet be rejected by the application.

For TLS, verify the chain to a trust anchor, hostname, validity period, key usage/EKU, revocation policy, and client TLS configuration. For JAR signing, verify the signature, signer chain, code-signing purpose, and timestamp according to release policy.

Never use `keytool -printcert` as sole proof that a connection or artifact is safe.

## 14. Importing a Trusted Certificate After Verification

When an organization provides a root CA or a certificate to trust, first inspect the file and confirm the SHA-256 fingerprint via an independent channel:

```bash
keytool -printcert -file organization-root.pem -v
```

Once the certificate is confirmed, import it into a dedicated truststore:

```bash
keytool -importcert -alias organization-root -file organization-root.pem -keystore app-truststore.p12 -storetype PKCS12
```

`keytool` will prompt for trust confirmation and the truststore password. Accept only after the fingerprint matches the verified value.

Inspect the entry after importing:

```bash
keytool -list -v -alias organization-root -keystore app-truststore.p12 -storetype PKCS12
```

The certificate is imported as a `trustedCertEntry`. It does not contain a private key. A dedicated truststore limits the scope of trust to the application instead of modifying `cacerts` for the entire JDK.

Do not import leaf certificates or unknown root certificates just to bypass TLS errors. Identify why the chain is untrusted before changing any trust configuration.

## 15. Practical Example: Creating a Test CA and Viewing the Chain

This example creates a lab-only root CA, a server key pair, a CSR, and a certificate signed by the test CA. Use dummy data only in a local environment; never use this root CA in production.

Create the root CA:

```bash
keytool -genkeypair -alias root-ca -keyalg RSA -keysize 3072 -validity 3650 -dname "CN=Example Test Root CA, O=Example, C=VN" -ext bc=ca:true -ext ku=keyCertSign,cRLSign -keystore root-ca.p12 -storetype PKCS12
```

Export the root certificate in PEM format:

```bash
keytool -exportcert -alias root-ca -keystore root-ca.p12 -storetype PKCS12 -rfc -file root-ca.pem
```

Generate a key pair for the server. The SAN declares the hostname and IP the server will use:

```bash
keytool -genkeypair -alias server -keyalg RSA -keysize 2048 -validity 365 -dname "CN=localhost, O=Example, C=VN" -ext bc=ca:false -ext ku=digitalSignature,keyEncipherment -ext eku=serverAuth -ext san=dns:localhost,ip:127.0.0.1 -keystore server.p12 -storetype PKCS12
```

Generate a certificate signing request (CSR):

```bash
keytool -certreq -alias server -keystore server.p12 -storetype PKCS12 -file server.csr -ext san=dns:localhost,ip:127.0.0.1
```

Have the CA sign the CSR and generate the server certificate:

```bash
keytool -gencert -alias root-ca -keystore root-ca.p12 -storetype PKCS12 -infile server.csr -outfile server-signed.pem -rfc -validity 365 -ext bc=ca:false -ext ku=digitalSignature,keyEncipherment -ext eku=serverAuth -ext san=dns:localhost,ip:127.0.0.1
```

Import the root CA into the server keystore first, then install the certificate reply into the matching alias:

```bash
keytool -importcert -alias root-ca -file root-ca.pem -keystore server.p12 -storetype PKCS12
keytool -importcert -alias server -file server-signed.pem -keystore server.p12 -storetype PKCS12
```

View the leaf certificate:

```bash
keytool -printcert -file server-signed.pem -v
```

View the alias and chain:

```bash
keytool -list -v -alias server -keystore server.p12 -storetype PKCS12
```

Key observations to verify:

- Subject is `localhost`.
- Issuer is `Example Test Root CA`.
- SAN contains `DNSName: localhost` and `IPAddress: 127.0.0.1`.
- The leaf certificate has `CA:false`.
- Extended Key Usage includes `serverAuth`.
- The keystore contains a `PrivateKeyEntry`.
- Certificate chain length is `2`: the server certificate and the root CA.

Export the certificate in DER format and inspect it again:

```bash
keytool -exportcert -alias server -keystore server.p12 -storetype PKCS12 -file server-signed.der
keytool -printcert -file server-signed.der -v
```

The SHA-256 fingerprint of the PEM and DER certificates must be identical because they are two encodings of the same certificate.

## 16. Example: Viewing a Certificate from a TLS Server

When a TLS listener is running on `localhost:8443`, use:

```bash
keytool -printcert -sslserver localhost:8443 -v
```

The output may display:

```text
Certificate #0
Owner: CN=localhost, O=Example, C=VN
Issuer: CN=Example Test Root CA, O=Example, C=VN
Certificate fingerprints:
    SHA256: ...

Certificate #1
Owner: CN=Example Test Root CA, O=Example, C=VN
Issuer: CN=Example Test Root CA, O=Example, C=VN
```

Certificate #0 is the leaf certificate presented by the server. Subsequent certificates may be intermediates or the root if the server sends them.

In a local test on JDK 24.0.2, `keytool -printcert -sslserver localhost:18443 -v` read both the leaf certificate and the root CA from a test TLS server; the TLS handshake completed. The leaf fingerprint matched the fingerprint read from both the PEM and DER files.

If the server does not send the complete chain, check the TLS server configuration and certificate bundle. Do not infer the full chain from the leaf certificate alone.

## 17. Example: Viewing a Signer Certificate in a JAR

Create or obtain a signed JAR, then inspect the signer:

```bash
keytool -printcert -jarfile app.jar -v
```

Verify the signature and chain:

```bash
jarsigner -verify -verbose -certs -keystore truststore.p12 -storetype PKCS12 app.jar
```

In testing on JDK 24.0.2, a JAR signed with a certificate having EKU `codeSigning` and a chain terminating at a root imported into the truststore was inspected: `keytool -printcert -jarfile` displayed the signer certificate and root, and `jarsigner -verify` confirmed the signature.

A JAR without a timestamp may verify today, but it may fail verification after the signer certificate expires. Release pipelines should consider a timestamp authority according to the organization's signing policy.

## 18. Common Errors and Troubleshooting

| Symptom | Common Cause | Resolution |
|---|---|---|
| `Input not an X.509 certificate` | File is not an X.509 certificate or is malformed | Check PEM/DER format and file contents |
| `Keystore was tampered with, or password was incorrect` | Wrong password or store type | Verify password and `-storetype` |
| `Alias does not exist` | Wrong alias or entry not yet imported | Use `keytool -list` to list aliases |
| Incomplete certificate chain | Missing intermediate or incorrect reply import order | Check `Certificate chain length` and import order |
| `Certificate expired` | Validity period has ended | Verify system date and request a new certificate |
| `Not yet valid` | Current time is before `Valid from` | Check system clock and issuance time |
| Hostname mismatch | SAN does not contain the accessed hostname/IP | Issue a certificate with the correct SAN |
| `PKIX path building failed` | Chain does not terminate at a trusted trust anchor | Check root/intermediate certificates and truststore |
| `unable to find valid certification path` | Missing CA or invalid chain | Obtain CA from a trusted source and verify fingerprint |
| `Certificate reply does not contain public key` | Certificate reply imported into mismatched private key alias | Generate CSR from the right alias and import matching reply |
| Unsuitable EKU | Certificate lacks required serverAuth/clientAuth/codeSigning | Issue a certificate with the appropriate purpose |
| TLS handshake failure | Issue with certificate, protocol, cipher, trust, or hostname | Check chain and client/server TLS configuration |
| JAR signature invalid | JAR contents modified after signing or corrupted signature | Rebuild and sign the final artifact |
| JAR reports missing timestamp | No timestamp authority used | Apply timestamping per release policy |

When troubleshooting, distinguish between file-reading errors, keystore errors, chain errors, and application TLS errors. Never import an unknown certificate into a truststore just to make an error disappear.

## 19. Systematic Certificate Inspection Workflow

A practical inspection workflow:

1. Identify the certificate source: file, keystore, TLS server, or signed JAR.
2. Run the appropriate `keytool -printcert` or `keytool -list -v` command.
3. Record the Subject, Issuer, serial number, and validity period.
4. Verify that the SAN matches the actual hostname/IP.
5. Check Basic Constraints, Key Usage, and Extended Key Usage.
6. Verify the public key and signature algorithm against security policies.
7. Compare the SHA-256 fingerprint against an independently verified value.
8. Inspect the chain and identify the trusted root.
9. Check which truststore the application is actually using.
10. Perform a TLS handshake or JAR signature verification in the target runtime environment.
11. Check revocation and timestamping if required by policy.
12. Record the alias, store type, certificate fingerprint, and expiration date for operations.

For production certificates, record the fingerprint and expiration date to renew proactively. Never share private keys or keystores containing private keys in investigation reports.

## 20. Security Best Practices When Using keytool

- Do not send `.p12`, `.pfx`, or `.jks` files containing private keys to unauthorized personnel.
- Never hardcode keystore passwords in source code, tickets, logs, or shared commands.
- Prefer letting `keytool` prompt for passwords interactively in a secure administrative session.
- Import a CA only after verifying its fingerprint from an independent source.
- Do not use self-signed certificates in production simply because `keytool` can read them.
- Do not disable hostname verification or trust validation to work around errors.
- Protect truststore files and restrict permissions to modify CAs.
- Use algorithms and key sizes compliant with current PKI policies.
- Monitor certificate expiration, renewal processes, and revocation.
- Separate public certificates from private keys in file-exchange workflows.

Certificates are public data in many contexts, but the decision to trust a certificate directly affects connection and artifact security. Verify identity and chain before changing any trust configuration.

## 21. Quick Certificate Inspection Checklist

- [ ] Have you identified the right file, alias, TLS endpoint, or JAR?
- [ ] Does Subject/Owner match the expected identity?
- [ ] Does Issuer match the expected CA?
- [ ] Has the serial number been recorded?
- [ ] Is the certificate within its validity period?
- [ ] Does SAN include the hostname/IP accessed by clients?
- [ ] Does the SHA-256 fingerprint match an independent trusted source?
- [ ] Do the public key and signature algorithm meet policy requirements?
- [ ] Are Basic Constraints, Key Usage, and EKU appropriate for the intended purpose?
- [ ] Does the certificate chain include the required intermediates and trusted root?
- [ ] Does the application's truststore contain the correct trust anchor?
- [ ] Have you performed actual TLS/JAR verification if required by the use case?

## 22. Summary

`keytool -printcert` is the primary command for viewing X.509 certificate contents. Use `-file` for PEM/DER certificates, `-sslserver` for certificates presented by a server, and `-jarfile` for signer certificates in a JAR. Use `keytool -list -v` to inspect aliases, entry types, and certificate chains in a keystore.

When reading the output, focus on Subject, Issuer, serial number, validity period, SHA-256 fingerprint, public key, signature algorithm, SAN, Basic Constraints, Key Usage, and Extended Key Usage. Inspect the entire chain rather than only the leaf certificate.

Keep certificate display distinct from trust verification. A certificate must have a trusted chain, be within its validity period, match the hostname, and be suitable for its intended purpose. For JARs, verify signatures with `jarsigner -verify`; for TLS, test with an actual client and configured truststore.

**Official References:**

- [Oracle JDK 24 — keytool command reference](https://docs.oracle.com/en/java/javase/24/docs/specs/man/keytool.html)
- [Oracle JDK 24 — jarsigner command reference](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jarsigner.html)
- [Java SE 24 API — X509Certificate](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/security/cert/X509Certificate.html)
- [Java SE 24 API — Certificate](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/security/cert/Certificate.html)
- [Java SE 24 API — KeyStore](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/security/KeyStore.html)

# Exporting Certificates with keytool

`keytool -exportcert` is a JDK command used to export a digital certificate (X.509 certificate) from a keystore by alias. The command retrieves the certificate associated with the selected entry and writes it to a file or standard output. The default format is binary DER; add `-rfc` to export in Base64 PEM text format.

A certificate contains a public key along with the subject's identity and validity information. `-exportcert` only exports the certificate, not the private key. If the alias points to a key entry that has a certificate chain, the command returns the **first certificate in the chain** (the entity certificate represented by the alias), not the entire chain.

## 1. When Do You Need to Export a Certificate?

Certificates are typically exported to share the public key and certificate details with another system, such as:

- Configuring TLS for a service or server.
- Providing a certificate to a client application, gateway, or reverse proxy.
- Transferring a certificate to another application's truststore after verification.
- Inspecting the subject, issuer, validity period, fingerprint, and extensions.
- Saving a certificate to a file for use with tools such as `keytool`, `openssl`, or a deployment platform.

Exporting a certificate does not modify the entry in the keystore. Nor does it automatically make the certificate trusted. Whether a system accepts a certificate depends on its trust configuration, certification chain, validity period, hostname, intended usage, and verification policy.

A certificate is public data, but it can reveal a hostname, organization name, email address, serial number, or infrastructure details. Share it only where appropriate according to your system's policy.

## 2. Identifying the Keystore and Alias Before Exporting

Before exporting, you need to know the keystore file, keystore type, and the alias containing the certificate. You can list the entries:

~~~sh
keytool -list -keystore app.p12 -storetype PKCS12
~~~

Keytool will prompt for the keystore password if required. To view details for a specific alias:

~~~sh
keytool -list -v -alias server -keystore app.p12 -storetype PKCS12
~~~

The verbose output can show:

- **Entry type**: for example, `PrivateKeyEntry` or `trustedCertEntry`.
- **Certificate chain length**: the number of certificates in the key entry's chain.
- **Owner/Subject** and **Issuer**.
- **Serial number**, `Valid from` period, and fingerprint.
- Extensions such as Subject Alternative Name, Key Usage, and Extended Key Usage.

Common entry types:

| Entry type | Contents | Result when exported |
|---|---|---|
| `PrivateKeyEntry` | Private key and certificate chain | Exports the first certificate in the chain; the private key is not exported |
| `trustedCertEntry` | A certificate stored as a trusted certificate | Exports that certificate |
| `SecretKeyEntry` | Symmetric secret key, no certificate | No certificate to export; the command will fail |

If the alias is incorrect or the entry does not contain a certificate, keytool cannot export the desired certificate. Therefore, verify the alias and entry type before running the command.

## 3. Basic Syntax of keytool -exportcert

General syntax:

~~~sh
keytool -exportcert -alias <alias> -keystore <keystore-file> -file <output-file>
~~~

Example of exporting a certificate from the `server` alias in a PKCS#12 keystore:

~~~sh
keytool -exportcert -alias server -keystore app.p12 -storetype PKCS12 -file server.cer
~~~

If the keystore requires a password, keytool will prompt for it when you run the command without passing `-storepass`. This avoids placing the password directly on the command line or in shell history.

Meaning of key options:

| Option | Meaning |
|---|---|
| `-exportcert` | Selects the export certificate operation |
| `-alias <alias>` | Selects the entry in the keystore |
| `-keystore <file>` | Specifies the source keystore |
| `-file <file>` | Specifies the output certificate file |
| `-storetype <type>` | Specifies the keystore type, e.g., JKS or PKCS12 |
| `-storepass <arg>` | Provides the keystore password |
| `-rfc` | Exports in RFC/PEM text format |
| `-cacerts` | Uses the JDK's default CA certificates keystore |
| `-v` | Displays more detailed information when executing the command |

If the keystore is JKS, you can specify it explicitly:

~~~sh
keytool -exportcert -alias server -keystore app.jks -storetype JKS -file server.cer
~~~

Modern JDKs typically use PKCS#12 as the default keystore type, but you should not rely on the default when working with legacy files or environments with different configurations. Choose the `-storetype` that matches the actual keystore.

If `-file` is omitted, the certificate is written to standard output. With the default DER format, stdout contains binary data and should not be printed directly to the terminal; use `-file` or redirect the binary output to a file. Use `-rfc` if you need text-based PEM output.

## 4. Default DER vs. PEM with -rfc

`keytool -exportcert` exports certificates in **DER binary** format by default. This is ASN.1 binary data encoded using Distinguished Encoding Rules. Files commonly use the `.cer` or `.der` extension, though the extension does not determine the actual content.

Example of exporting DER:

~~~sh
keytool -exportcert -alias server -keystore app.p12 -storetype PKCS12 -file server.der
~~~

Add `-rfc` to export the certificate in Base64 PEM format:

~~~sh
keytool -exportcert -rfc -alias server -keystore app.p12 -storetype PKCS12 -file server.pem
~~~

A PEM file typically has the following structure:

~~~text
-----BEGIN CERTIFICATE-----
MIID...Base64 encoded certificate data...
-----END CERTIFICATE-----
~~~

The Base64 lines in the middle are the text-encoded certificate contents; the header and footer markers identify the PEM data type. The actual content depends on the certificate, so there is no fixed output string.

Comparison of the two formats:

| Characteristic | Default DER | PEM (`-rfc`) |
|---|---|---|
| Data format | Binary | Base64 text with header/footer |
| Readable in a text editor | Not convenient | Yes |
| Common extensions | .cer, .der | .pem, .crt, .cer |
| Used for | Java and tools accepting DER certificates | TLS servers, proxies, tools requiring PEM |
| Size | Usually smaller | Larger due to Base64 encoding and headers |

You cannot determine the format by filename alone. A `.cer` file can contain either DER or PEM. Inspect the file contents or use `keytool -printcert` to confirm.

## 5. Complete Hands-On Example

You can create a test keystore with a self-signed certificate to practice. The following command generates a key pair and stores an entry with the alias `demo` in a PKCS#12 file:

~~~sh
keytool -genkeypair -alias demo -keyalg RSA -keysize 2048 -validity 365 -dname "CN=localhost" -keystore demo.p12 -storetype PKCS12
~~~

Keytool will prompt for a keystore password. In a learning environment, use a test password and do not reuse a real password. The command creates a self-signed certificate for demonstration purposes; this certificate is not automatically trusted by other systems.

Export the certificate in DER format:

~~~sh
keytool -exportcert -alias demo -keystore demo.p12 -storetype PKCS12 -file demo.der
~~~

Export the same certificate in PEM format:

~~~sh
keytool -exportcert -rfc -alias demo -keystore demo.p12 -storetype PKCS12 -file demo.pem
~~~

Both export commands will prompt for the keystore password if required. They produce two files representing the same certificate in two different formats. The files are written to the current directory; ensure the target directory is appropriate and avoid accidentally overwriting files you need to keep.

Inspect the DER certificate contents:

~~~sh
keytool -printcert -file demo.der
~~~

Inspect the PEM certificate contents:

~~~sh
keytool -printcert -file demo.pem
~~~

Both commands display the certificate details in a human-readable format. Specific fields depend on the newly generated certificate, such as Owner/Subject, Issuer, Serial number, Validity, SHA-256 fingerprint, and extensions. Because the serial number, fingerprint, and validity start time are generated per run, do not expect a fixed output.

Check the source entry and chain length:

~~~sh
keytool -list -v -alias demo -keystore demo.p12 -storetype PKCS12
~~~

For the demo key pair, the alias is typically a `PrivateKeyEntry`; the certificate chain length is usually 1 because the certificate is self-signed. The `-exportcert` command extracts the first certificate in that chain.

## 6. Exporting a Certificate from cacerts

The JDK includes a default CA keystore commonly referred to as `cacerts`. You can use the `-cacerts` option to access this keystore instead of specifying a `-keystore` path.

Example of exporting a CA certificate by alias:

~~~sh
keytool -exportcert -cacerts -alias <ca-alias> -rfc -file ca-certificate.pem
~~~

Replace `<ca-alias>` with an actual alias in `cacerts`. You can list the aliases first with:

~~~sh
keytool -list -cacerts
~~~

If the environment requires permissions or a password to read the keystore, follow your machine's authentication mechanism. Do not modify or replace `cacerts` just to export a certificate; exporting only needs to read the entry.

## 7. Certificate Chains: exportcert Returns Only the First Certificate

A key entry can contain a certificate chain consisting of the server/application certificate and intermediate CA certificates. When the alias points to a key entry with a chain, `keytool -exportcert` returns the **first certificate in the chain**, which is the certificate authenticating the public key of the entity represented by the alias.

For example, if the chain consists of:

~~~text
server certificate
        |
        v
intermediate CA
        |
        v
root CA
~~~

Running export from the `server` alias exports only the server certificate. It does not create a file containing all three certificates, nor does it export the private key.

To see how many certificates are in the chain and their order:

~~~sh
keytool -list -v -alias server -keystore app.p12 -storetype PKCS12
~~~

If an application requires the full chain, you must provide the intermediate/root certificates separately according to the target platform and format requirements. You can export each certificate individually if they have their own aliases in the keystore, or use a tool appropriate for the container/format storing the chain. Do not assume a file created by `-exportcert` already contains the full chain.

## 8. Verifying the Certificate After Exporting

After exporting, inspect the file rather than relying solely on the command completing successfully.

Print the certificate details:

~~~sh
keytool -printcert -file server.pem
~~~

Or for DER:

~~~sh
keytool -printcert -file server.der
~~~

Verify the following details:

- **Subject/Owner**: which entity the certificate belongs to.
- **Issuer**: which CA or entity signed the certificate.
- **Serial number**: the certificate identifier issued by the issuer.
- **Validity**: the start and end dates of validity.
- **SHA-256 fingerprint**: the fingerprint of the certificate.
- **Subject Alternative Name (SAN)**: the hostnames/IPs protected by the certificate.
- **Key Usage / Extended Key Usage**: the permitted uses.

When receiving a certificate from another source or preparing to import it into a truststore, compare the SHA-256 fingerprint against a value provided through a trusted channel. A certificate printing its own fingerprint does not prove it is trustworthy; the verifier needs an independent expected fingerprint.

You can inspect the source alias with `keytool -list -v` and compare the Subject, Issuer, serial number, validity period, and fingerprint against the exported file. If they differ, you may have selected the wrong alias, wrong keystore, or wrong output file.

## 9. Passwords and Security When Exporting

`-storepass` allows passing the keystore password, but writing a password directly on the command line can expose secrets via shell history, process listings, logs, or monitoring tools.

When operating interactively, omit `-storepass` so keytool prompts for the password. When automating, use a secret management mechanism appropriate for your platform and consider password-protected mechanisms supported by keytool such as `-protected` when the provider/environment is configured accordingly.

Key principles:

- Do not send a keystore file containing a private key when you only need to share the certificate.
- Do not put keystore passwords into scripts or repositories.
- Only export certificates from the right alias and the right keystore.
- Verify the fingerprint before trusting or importing a certificate.
- Limit sharing certificates that contain internal identifying information when unnecessary.
- Keep the original keystore intact and do not delete the entry after exporting.

An exported certificate is public data, but keystore access operations still need to be protected. Do not confuse exporting a public certificate with exporting a private key.

## 10. Common Errors and Troubleshooting

| Symptom | Common Cause | Resolution |
|---|---|---|
| `Alias <name> does not exist` | Wrong alias or reading the wrong keystore | Use `keytool -list` to check aliases and the file path |
| `Keystore was tampered with, or password was incorrect` | Wrong password or unreadable keystore file | Verify the password, source file, and `-storetype` |
| No certificate to export | Alias is a secret key entry or an entry without a certificate | Check the entry type; select an alias that has a certificate |
| Exported file is unreadable in a text editor | Certificate was exported in binary DER format | Use `-rfc` to generate PEM |
| Target application reports missing intermediate CA | Only the first certificate in the chain was exported | Inspect the chain with `keytool -list -v` and provide the required CA certificates |
| Certificate has the wrong Subject | Wrong alias or keystore selected | Check Subject, Issuer, serial number, and fingerprint before use |
| Certificate is expired or not yet valid | Certificate validity period does not match the current time | Check Validity and obtain a valid certificate |
| TLS hostname mismatch | SAN does not include the hostname the client is accessing | Check Subject Alternative Name and issue a certificate with the right hostname |
| Output file not found | Target directory does not exist or lacks write permission | Create the directory, verify the path, and check write permissions |

## 11. Certificate Export Workflow

When you need to export a certificate from a keystore, follow these steps in order:

1. Identify the keystore file and keystore type (JKS or PKCS12).
2. Use `keytool -list` to find the alias to export.
3. Use `keytool -list -v -alias ...` to check the entry type and chain length.
4. Choose the format: default DER or PEM with `-rfc`.
5. Run `keytool -exportcert` with an explicit alias, keystore, and output file.
6. Avoid passing the password directly on the command line when possible so keytool prompts for it.
7. Use `keytool -printcert` to verify the exported file.
8. Compare the fingerprint against a trusted source before importing or distributing.
9. If the full chain is needed, check and provide the intermediate/root certificates separately.

### Checklist

- [ ] Identified the correct keystore and `-storetype`.
- [ ] Selected the right alias containing the certificate.
- [ ] Confirmed the entry type and chain length.
- [ ] Chose DER or PEM according to the target system's requirements.
- [ ] Used `-file` to save to the correct location.
- [ ] Understood that `-exportcert` returns only the first certificate of a key-entry chain.
- [ ] Verified the certificate with `keytool -printcert`.
- [ ] Checked the fingerprint, Subject, Issuer, validity, and SAN.
- [ ] Protected the keystore password and private key.
- [ ] Confirmed the certificate is provided for the right purpose and trust policy.

`keytool -exportcert` is a direct way to extract a public certificate from an alias in a keystore. Choosing the right alias, DER/PEM format, and verifying the fingerprint ensures the certificate can be transferred to another system without exposing the private key or confusing a single certificate with the entire chain.

## References

- [Oracle JDK 21 — The keytool Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html)
- [Oracle JDK 25 — The keytool Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/keytool.html)